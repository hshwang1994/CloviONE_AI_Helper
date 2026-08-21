# -*- coding: utf-8 -*-
"""S1 / P-03 (C) — CPU 임베딩 벤치. ONNX Runtime 만 쓴다(torch 없음).

무엇을 재는가:
  1. **색인 처리량** — 실 Corpus 를 자연 길이 그대로. 배치 8/16/32.
  2. **질의 지연** — 배치 1, 짧은 질의. 검색이 매 요청마다 내는 비용이다.
  3. **고정 256토큰 처리량** — S13 이 Notion 본문을 다시 실어 오면 문서가 길어진다.
     지금 Corpus(중앙값 96자)로만 재면 색인 시간을 **낙관적으로** 틀리게 잰다.
  4. **리랭커 대리 측정** — `bge-reranker-v2-m3` 는 공식 ONNX 가 없다. 백본이 같은
     XLM-R-large(=bge-m3)로 (질의, 문서) 쌍 50개를 태워 **지배적 비용**을 잰다.

산출: `emb_<model>.tsv` (id \t vector literal) + `bench_embed_<model>.json`.
"""
from __future__ import annotations

import json
import os
import resource
import statistics
import sys
import time

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

MODEL_DIR = sys.argv[1]
NAME = sys.argv[2]
CORPUS = sys.argv[3]
OUT_TSV = sys.argv[4]
OUT_JSON = sys.argv[5]
QUERY_PREFIX = os.environ.get("QUERY_PREFIX", "")
DOC_PREFIX = os.environ.get("DOC_PREFIX", "")

onnx_path = os.path.join(MODEL_DIR, "onnx", "model.onnx")
tok = Tokenizer.from_file(os.path.join(MODEL_DIR, "tokenizer.json"))
tok.enable_truncation(max_length=512)

opts = ort.SessionOptions()
opts.intra_op_num_threads = int(os.environ.get("ORT_THREADS", "8"))
opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
t0 = time.perf_counter()
sess = ort.InferenceSession(onnx_path, opts, providers=["CPUExecutionProvider"])
load_ms = (time.perf_counter() - t0) * 1000
inputs = {i.name for i in sess.get_inputs()}
print("%s | load %.0fms | inputs %s" % (NAME, load_ms, sorted(inputs)))


def encode(texts: list[str]) -> tuple[np.ndarray, int]:
    tok.enable_padding(pad_id=1, pad_token="<pad>")
    encs = tok.encode_batch(texts)
    ids = np.array([e.ids for e in encs], dtype=np.int64)
    mask = np.array([e.attention_mask for e in encs], dtype=np.int64)
    feed = {"input_ids": ids, "attention_mask": mask}
    if "token_type_ids" in inputs:
        feed["token_type_ids"] = np.zeros_like(ids)
    out = sess.run(None, {k: v for k, v in feed.items() if k in inputs})[0]
    # mean pooling (e5) / CLS (bge-m3). 둘 다 마스크를 존중한다.
    if NAME.startswith("bge-m3"):
        vec = out[:, 0, :]
    else:
        m = mask[..., None].astype(np.float32)
        vec = (out * m).sum(axis=1) / np.clip(m.sum(axis=1), 1e-9, None)
    vec = vec / np.clip(np.linalg.norm(vec, axis=1, keepdims=True), 1e-9, None)
    return vec.astype(np.float32), int(mask.sum())


rows = [json.loads(l) for l in open(CORPUS, encoding="utf-8")]
texts = [DOC_PREFIX + (r["text"] or r["title"] or " ") for r in rows]
result: dict = {"model": NAME, "onnx_load_ms": round(load_ms, 1),
                "threads": opts.intra_op_num_threads}

# ── 1) 색인 처리량 ────────────────────────────────────────────────────────
vecs = None
for bs in (8, 16, 32):
    t = time.perf_counter()
    parts, tokens = [], 0
    for i in range(0, len(texts), bs):
        v, n = encode(texts[i:i + bs])
        parts.append(v)
        tokens += n
    dt = time.perf_counter() - t
    if vecs is None or bs == 32:
        vecs = np.vstack(parts)
    result.setdefault("index_throughput", {})[f"batch{bs}"] = {
        "docs": len(texts), "seconds": round(dt, 2),
        "docs_per_sec": round(len(texts) / dt, 1),
        "tokens_per_sec": round(tokens / dt, 1),
    }
    print("  batch=%-3d %6.1f docs/s  %8.0f tok/s  (%.1fs)"
          % (bs, len(texts) / dt, tokens / dt, dt))

result["dim"] = int(vecs.shape[1])

# ── 2) 질의 지연 (배치 1) ────────────────────────────────────────────────
queries = [QUERY_PREFIX + (r["title"] or "질의")[:40] for r in rows[:60]]
lat = []
for q in queries:
    t = time.perf_counter()
    encode([q])
    lat.append((time.perf_counter() - t) * 1000)
lat.sort()
result["query_latency_ms"] = {
    "n": len(lat), "p50": round(statistics.median(lat), 2),
    "p95": round(lat[int(len(lat) * 0.95) - 1], 2), "max": round(lat[-1], 2)}
print("  질의 지연 p50=%.1fms p95=%.1fms" % (result["query_latency_ms"]["p50"],
                                          result["query_latency_ms"]["p95"]))

# ── 3) 고정 256 토큰 처리량 ───────────────────────────────────────────────
long_text = (DOC_PREFIX + "".join(r["text"] for r in rows[:40]))[:1200]
chunk = [long_text] * 16
t = time.perf_counter()
_, ntok = encode(chunk)
dt = time.perf_counter() - t
result["chunk_throughput"] = {
    "batch": 16, "tokens_in_batch": ntok, "seconds": round(dt, 3),
    "tokens_per_sec": round(ntok / dt, 1),
    "chunks_per_sec": round(16 / dt, 2)}
print("  긴 청크: %.1f chunk/s  %.0f tok/s (배치 16, %d토큰)"
      % (16 / dt, ntok / dt, ntok))

# ── 4) 리랭커 대리 측정 ───────────────────────────────────────────────────
pairs = [(queries[0] + " </s> " + (r["text"] or " "))[:1200] for r in rows[:50]]
t = time.perf_counter()
_, ptok = encode(pairs)
rr = (time.perf_counter() - t) * 1000
result["rerank_proxy_top50_ms"] = {"ms": round(rr, 1), "tokens": ptok,
                                   "note": "같은 XLM-R-large 백본을 (질의,문서) 50쌍에 태운 값"}
print("  리랭크 대리(top50) %.0fms" % rr)

result["max_rss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
print("  최대 RSS %.0f MB" % result["max_rss_mb"])

with open(OUT_TSV, "w", encoding="utf-8", newline="\n") as fh:
    for r, v in zip(rows, vecs):
        fh.write("%s\t[%s]\n" % (r["id"], ",".join("%.6f" % x for x in v)))
json.dump(result, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("wrote %s %s" % (OUT_TSV, OUT_JSON))
