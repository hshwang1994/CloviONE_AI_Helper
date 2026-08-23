# -*- coding: utf-8 -*-
"""S10 — **긴 본문에서** 임베딩 모델을 다시 본다 (D-211 상향 경로).

    python scripts/bench/retrieval_model_review.py <corpus 디렉터리> <출력.json>

D-211 이 적어 둔 상향 경로는 이렇다: 「이 품질 측정은 **제목 부분구간** 질의다. S13 이
Notion 본문을 다시 실어 오면 문서가 길어지고, 긴 문서에서는 `bge-m3` 격차가 커질 수
있다. **S10 이 실제 본문으로 다시 재고**, 그때 필요하면 모델만 바꾼다.」

## 그래서 무엇이 달라졌나

S1 의 Corpus 는 중앙값 **96자**였고 질의는 제목 부분구간이었다. 여기 Corpus 는 중앙값
**705자**이고 질의는 세 종류다(어절 경계 · **어절 내부** · 기억나는 대로). 즉 D-211 이
「나중에 다시 재라」고 한 조건 중 **길이는 충족**됐다.

**충족되지 않은 조건도 그대로 적는다**: 이 글은 업무 기록이 아니라 이 저장소의 기술
문서다. 미러에 본문이 없어서(2026-08-23 실측: `document_cache` 0건) 업무 기록으로는
아직 못 잰다 — 그것은 S13 이후의 일이다.

## PG 없이 잰다

`bge-m3` 은 1024차원이라 `vector(384)` 컬럼에 안 들어가고, 카탈로그에 없는 모델이라
제품 Adapter 도 안 받는다(D-201). 모델 **사이의 비교**에는 DB 가 필요 없다 — 정규화된
벡터끼리의 내적이 곧 코사인 유사도다.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open(encoding="utf-8")]


def _tsv(path: Path):
    keys, vectors = [], []
    for line in path.open(encoding="utf-8"):
        key, _sep, body = line.rstrip("\n").partition("\t")
        keys.append(key)
        vectors.append([float(v) for v in body.strip("[]").split(",")])
    return keys, np.asarray(vectors, dtype=np.float32)


def evaluate(chunk_keys, chunk_vectors, query_keys, query_vectors, queries) -> dict:
    index = {key: position for position, key in enumerate(chunk_keys)}
    lookup = {key: position for position, key in enumerate(query_keys)}
    similarity = query_vectors @ chunk_vectors.T
    top = np.argsort(-similarity, axis=1)[:, :10]

    buckets: dict[str, list[int | None]] = {}
    distances: dict[str, list[float]] = {"gold": [], "nearest_non_gold": []}
    for item in queries:
        row = lookup[item["query"]]
        gold = index[item["gold"]]
        ranked = list(top[row])
        position = ranked.index(gold) + 1 if gold in ranked else None
        buckets.setdefault(item["kind"], []).append(position)
        buckets.setdefault("all", []).append(position)
        distances["gold"].append(float(1.0 - similarity[row, gold]))
        for candidate in ranked:
            if candidate != gold:
                distances["nearest_non_gold"].append(float(1.0 - similarity[row, candidate]))
                break

    out: dict = {}
    for kind, positions in buckets.items():
        total = len(positions)
        out[kind] = {
            "n": total,
            "recall@1": round(sum(1 for p in positions if p == 1) / total, 4),
            "recall@10": round(sum(1 for p in positions if p) / total, 4),
            "mrr@10": round(sum(1.0 / p for p in positions if p) / total, 4),
        }
    for name, values in distances.items():
        values = sorted(values)
        out.setdefault("distance", {})[name] = {
            "p10": round(values[int(len(values) * 0.10)], 4),
            "p50": round(values[len(values) // 2], 4),
            "p90": round(values[int(len(values) * 0.90)], 4),
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus_dir")
    parser.add_argument("out_json")
    args = parser.parse_args()

    corpus = Path(args.corpus_dir)
    queries = _rows(corpus / "queries.jsonl")
    summary = json.loads((corpus / "corpus_summary.json").read_text(encoding="utf-8"))
    report: dict = {
        "corpus": summary,
        "note": (
            "S1(D-211)은 중앙값 96자 Corpus 에 제목 부분구간 질의였다. 여기는 중앙값"
            " 705자에 질의 세 종류다. 미러에 업무 본문이 없어(2026-08-23 실측)"
            " 업무 기록으로는 아직 못 잰다 — 그 축은 S13 이후다."
        ),
        "models": {},
    }
    speed = json.loads((corpus / "embed_report_chunks.json").read_text(encoding="utf-8"))

    for name, prefix in (("e5-small", "e5small"), ("bge-m3", "bgem3")):
        chunk_file = corpus / f"{prefix}_chunks.tsv"
        if not chunk_file.is_file():
            continue
        chunk_keys, chunk_vectors = _tsv(chunk_file)
        query_keys, query_vectors = _tsv(corpus / f"{prefix}_queries.tsv")
        scored = evaluate(chunk_keys, chunk_vectors, query_keys, query_vectors, queries)
        scored["dim"] = int(chunk_vectors.shape[1])
        scored["speed"] = speed["models"].get(name, {})
        report["models"][name] = scored

    Path(args.out_json).write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    kinds = ["all", "span", "infix", "recall"]
    print("모델 비교 (MRR@10)      " + " ".join(f"{k:>9s}" for k in kinds))
    for name, values in report["models"].items():
        print(f"  {name:12s} dim={values['dim']:4d} "
              + " ".join(f"{values[k]['mrr@10']:9.4f}" for k in kinds))
    for name, values in report["models"].items():
        print(f"  {name:12s} 거리 정답={values['distance']['gold']} "
              f"최근접오답={values['distance']['nearest_non_gold']}")
        print(f"  {name:12s} 속도 {values['speed']}")
    print("wrote", args.out_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
