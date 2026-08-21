# -*- coding: utf-8 -*-
"""S1 / P-03 (C-2) — 모델을 **속도만으로** 고르지 않는다.

속도는 앞 단계에서 쟀다. 여기서는 «한국어로 부분만 기억하고 검색할 때 그 문서를 찾아 주는가»
를 잰다. 라벨이 없으므로 Corpus 자체로 만든다:

    질의 = 제목의 **연속 부분 구간**(60%) + 어절 하나를 뺀 것
    정답 = 그 문서 하나

이건 완전한 relevance 평가가 아니다 — 그러나 «제목 일부만 기억하는 사용자» 는 이 제품에서
가장 흔한 검색 형태이고, 세 모델을 **같은 질의로** 비교하는 데는 충분하다. 절대값이 아니라
**순위**를 보는 실험이라는 사실을 결과에 적는다.
"""
from __future__ import annotations

import json
import os
import random
import sys
import time

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

CORPUS = sys.argv[1]
OUT = sys.argv[2]
MODELS = [
    ("e5-small", os.path.expanduser("~/s1bench/models/intfloat__multilingual-e5-small"),
     "query: ", "passage: "),
    ("e5-base", os.path.expanduser("~/s1bench/models/intfloat__multilingual-e5-base"),
     "query: ", "passage: "),
    ("bge-m3", os.path.expanduser("~/s1bench/models/BAAI__bge-m3"), "", ""),
]

rows = [json.loads(l) for l in open(CORPUS, encoding="utf-8")]
rows = [r for r in rows if len((r["title"] or "").split()) >= 3]
random.seed(20260821)
sample = random.sample(rows, min(200, len(rows)))


def make_query(title: str) -> str:
    words = title.split()
    if len(words) >= 4:
        drop = random.randrange(len(words))
        words = [w for i, w in enumerate(words) if i != drop]
    keep = max(2, int(len(words) * 0.6))
    start = random.randrange(0, max(1, len(words) - keep + 1))
    return " ".join(words[start:start + keep])


queries = [(r["id"], make_query(r["title"])) for r in sample]
print("질의 %d개 · Corpus %d건" % (len(queries), len(rows)))
print("예시:", queries[0][1], "  <-  ", sample[0]["title"][:40])

result: dict = {"n_queries": len(queries), "corpus": len(rows),
                "note": "제목 부분구간 질의 · 정답=그 문서 하나. 절대값이 아니라 모델 간 순위를 본다.",
                "models": {}}

for name, mdir, qp, dp in MODELS:
    tok = Tokenizer.from_file(os.path.join(mdir, "tokenizer.json"))
    tok.enable_truncation(max_length=512)
    tok.enable_padding(pad_id=1, pad_token="<pad>")
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 8
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    sess = ort.InferenceSession(os.path.join(mdir, "onnx", "model.onnx"), opts,
                                providers=["CPUExecutionProvider"])
    names = {i.name for i in sess.get_inputs()}

    def enc(texts: list[str]) -> np.ndarray:
        encs = tok.encode_batch(texts)
        ids = np.array([e.ids for e in encs], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encs], dtype=np.int64)
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in names:
            feed["token_type_ids"] = np.zeros_like(ids)
        out = sess.run(None, {k: v for k, v in feed.items() if k in names})[0]
        if name == "bge-m3":
            vec = out[:, 0, :]
        else:
            m = mask[..., None].astype(np.float32)
            vec = (out * m).sum(axis=1) / np.clip(m.sum(axis=1), 1e-9, None)
        return (vec / np.clip(np.linalg.norm(vec, axis=1, keepdims=True), 1e-9, None)).astype(np.float32)

    t0 = time.perf_counter()
    docs = np.vstack([enc([dp + (r["text"] or r["title"]) for r in rows[i:i + 16]])
                      for i in range(0, len(rows), 16)])
    qv = np.vstack([enc([qp + q for _i, q in queries[i:i + 16]])
                    for i in range(0, len(queries), 16)])
    dt = time.perf_counter() - t0
    idx = {r["id"]: i for i, r in enumerate(rows)}
    sims = qv @ docs.T
    order = np.argsort(-sims, axis=1)[:, :10]
    r1 = r10 = 0
    mrr = 0.0
    for k, (qid, _q) in enumerate(queries):
        gold = idx[qid]
        ranked = list(order[k])
        if ranked and ranked[0] == gold:
            r1 += 1
        if gold in ranked:
            r10 += 1
            mrr += 1.0 / (ranked.index(gold) + 1)
    result["models"][name] = {
        "dim": int(docs.shape[1]),
        "recall@1": round(r1 / len(queries), 4),
        "recall@10": round(r10 / len(queries), 4),
        "mrr@10": round(mrr / len(queries), 4),
        "encode_seconds": round(dt, 1),
    }
    print("  %-10s dim=%4d  R@1=%.3f  R@10=%.3f  MRR@10=%.3f  (%.0fs)"
          % (name, docs.shape[1], r1 / len(queries), r10 / len(queries),
             mrr / len(queries), dt))
    del sess

json.dump(result, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("wrote", OUT)
