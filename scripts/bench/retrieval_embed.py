# -*- coding: utf-8 -*-
"""S10 — chunk 와 질의를 **실제 모델**로 벡터로 만든다 (서버에서 실행).

    python scripts/bench/retrieval_embed.py <corpus 디렉터리> --model-root ~/s1bench/models

## 왜 서버에서 도는가

임베딩 런타임(`onnxruntime`·`tokenizers`)과 모델 파일(465MB)이 테스트 서버에만 있고,
측정용 PostgreSQL 은 개발 기계에만 있다. S1 이 `bench_vector.py` 에서 쓴 방식 그대로
**벡터를 TSV 로 건네준다** — 서버가 만들고, 개발 기계가 그것을 PG 에 싣는다.

## e5-small 은 **제품 Adapter 로** 만든다

`LocalOnnxEmbedAdapter` 를 그대로 부른다. 접두사(`query: `/`passage: `)·풀링·정규화·
자르기가 전부 그 안에 있고, 여기서 다시 적으면 **측정한 벡터와 운영이 만드는 벡터가
다른 값**이 된다. 그러면 이 측정으로 정한 가중치는 운영과 상관없는 숫자다.

## bge-m3 은 비교용이라 별도 경로다 (D-211 상향 경로)

카탈로그에 없는 모델이라 제품 Adapter 가 안 받는다(그것이 D-201 의 규칙이다 — 목록에
없는 이름은 거절한다). CLS 풀링에 접두사가 없고 1024차원이라 `vector(384)` 컬럼에도
안 들어간다. 그래서 **PG 없이 numpy 로만** 비교한다.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

BATCH = 32


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open(encoding="utf-8")]


def _write_tsv(path: Path, ids, vectors) -> None:
    with io.open(path, "w", encoding="utf-8", newline="\n") as handle:
        for key, vector in zip(ids, vectors):
            handle.write(key + "\t[" + ",".join(f"{v:.6f}" for v in vector) + "]\n")


# ── 제품 경로 (e5-small) ─────────────────────────────────────────────────────


def embed_with_product(model_root: Path, texts: list[str], kind: str):
    """제품의 Gateway 를 그대로 지난다. 부분 결과는 성공이 아니다(계약)."""
    from app.ai import catalog
    from app.ai.gateway import contract, registry

    config = registry.AiConfig(
        enabled=True, model_root=str(model_root),
        embed_model_id=catalog.DEFAULT_EMBEDDING_MODEL_ID, batch_size=BATCH,
    )
    gateway = contract.Gateway(enabled=True, embed_adapter=registry.build_embed_adapter(config))
    capability = gateway.capabilities().embed
    if not capability.available:
        raise SystemExit(f"임베딩을 쓸 수 없다: {capability.status} {capability.detail}")

    out = []
    started = time.perf_counter()
    for index in range(0, len(texts), BATCH):
        result = gateway.embed(texts[index:index + BATCH], kind=kind)
        if not result.ok:
            raise SystemExit(f"임베딩 실패: {result.status} {result.detail}")
        out.extend(result.vectors)
    return out, time.perf_counter() - started


# ── 비교 경로 (bge-m3) ───────────────────────────────────────────────────────


def embed_with_raw_onnx(model_dir: Path, texts: list[str], *, pooling: str, prefix: str = ""):
    import numpy as np
    import onnxruntime as ort
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
    tokenizer.enable_truncation(max_length=512)
    tokenizer.enable_padding(pad_id=1, pad_token="<pad>")
    options = ort.SessionOptions()
    options.intra_op_num_threads = int(os.environ.get("ORT_THREADS", "8"))
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    session = ort.InferenceSession(
        str(model_dir / "onnx" / "model.onnx"), options, providers=["CPUExecutionProvider"]
    )
    names = {i.name for i in session.get_inputs()}

    out = []
    started = time.perf_counter()
    for index in range(0, len(texts), BATCH):
        batch = [prefix + t for t in texts[index:index + BATCH]]
        encoded = tokenizer.encode_batch(batch)
        ids = np.array([e.ids for e in encoded], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in names:
            feed["token_type_ids"] = np.zeros_like(ids)
        hidden = session.run(None, {k: v for k, v in feed.items() if k in names})[0]
        if pooling == "cls":
            vectors = hidden[:, 0, :]
        else:
            weights = mask[..., None].astype(np.float32)
            vectors = (hidden * weights).sum(axis=1) / np.clip(weights.sum(axis=1), 1e-9, None)
        vectors = vectors / np.clip(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-9, None)
        out.extend(vectors.astype(np.float32).tolist())
    return out, time.perf_counter() - started


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus_dir")
    parser.add_argument("--model-root", default="~/s1bench/models")
    parser.add_argument("--also-bge", action="store_true", help="D-211 상향 경로 비교용")
    # chunk 는 결정적이라 질의만 바뀌면 다시 만들 이유가 없다. bge-m3 은 849건에
    # 10분 넘게 걸리므로 그 시간을 두 번 내지 않는다.
    parser.add_argument("--queries-only", action="store_true")
    args = parser.parse_args()

    corpus = Path(args.corpus_dir)
    model_root = Path(os.path.expanduser(args.model_root))
    chunks = _rows(corpus / "chunks.jsonl")
    queries = _rows(corpus / "queries.jsonl")
    print(f"chunk {len(chunks)}건 · 질의 {len(queries)}개")

    report: dict = {"chunks": len(chunks), "queries": len(queries), "models": {}}

    entry: dict = {"path": "제품 Adapter (app/ai/gateway/adapters/local_embed.py)"}
    if not args.queries_only:
        passages, passage_seconds = embed_with_product(
            model_root, [c["text"] for c in chunks], "passage"
        )
        _write_tsv(corpus / "e5small_chunks.tsv", [c["id"] for c in chunks], passages)
        entry.update({
            "dim": len(passages[0]),
            "chunk_seconds": round(passage_seconds, 1),
            "chunks_per_second": round(len(chunks) / passage_seconds, 1),
        })
    query_vectors, query_seconds = embed_with_product(
        model_root, [q["query"] for q in queries], "query"
    )
    _write_tsv(corpus / "e5small_queries.tsv", [q["query"] for q in queries], query_vectors)
    entry.update({
        "query_seconds": round(query_seconds, 2),
        "query_ms_each": round(query_seconds * 1000 / max(1, len(queries)), 2),
    })
    report["models"]["e5-small"] = entry
    print("e5-small  " + json.dumps(entry, ensure_ascii=False))

    if args.also_bge:
        directory = model_root / "BAAI__bge-m3"
        bge: dict = {
            "path": "비교용 raw ONNX (카탈로그에 없는 모델이라 제품 Adapter 가 안 받는다)"
        }
        if not args.queries_only:
            bge_passages, bge_seconds = embed_with_raw_onnx(
                directory, [c["text"] for c in chunks], pooling="cls"
            )
            _write_tsv(corpus / "bgem3_chunks.tsv", [c["id"] for c in chunks], bge_passages)
            bge.update({
                "dim": len(bge_passages[0]),
                "chunk_seconds": round(bge_seconds, 1),
                "chunks_per_second": round(len(chunks) / bge_seconds, 1),
            })
        bge_queries, bge_query_seconds = embed_with_raw_onnx(
            directory, [q["query"] for q in queries], pooling="cls"
        )
        _write_tsv(corpus / "bgem3_queries.tsv", [q["query"] for q in queries], bge_queries)
        bge.update({
            "query_seconds": round(bge_query_seconds, 2),
            "query_ms_each": round(bge_query_seconds * 1000 / max(1, len(queries)), 2),
        })
        report["models"]["bge-m3"] = bge
        print("bge-m3    " + json.dumps(bge, ensure_ascii=False))

    (corpus / "embed_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
