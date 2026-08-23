# -*- coding: utf-8 -*-
"""S10 — 융합 가중치와 벡터 거리 상한을 **실측으로** 정한다 (D-209 · D-210 · D-212).

    python scripts/bench/retrieval_fusion.py <corpus 디렉터리> <출력.json>

D-209 는 초기값(`w_trgm 1.0 · w_fts 0.5 · w_vector 1.0`)만 주고 «**최종 가중치는 S10 이
실제 relevance 로 다시 정한다 — 여기서 숫자를 지어내지 않는다**» 라고 적었다. 이 파일이
그 자리다.

## 무엇을 재는가

제품의 레인 SQL(`app/ai/retrieval/query.py`)을 **그대로** 부른다. 여기서 SQL 을 다시
쓰면 측정한 것과 운영이 도는 것이 다른 질의가 되고, 그러면 이 숫자로 정한 가중치는
운영과 상관이 없다.

    1) 세 레인을 질의마다 한 번씩 돌려 순위를 받는다 (벡터는 거리까지 함께)
    2) 가중치 격자와 거리 상한 격자를 **파이썬에서** 접는다 — DB 를 다시 안 친다
    3) Recall@1 · Recall@5 · MRR@10 을 질의 종류별로 낸다

## 거리 상한을 함께 재는 이유

최근접 이웃은 **언제나** 답을 낸다. 상한이 없으면 아무 관계 없는 질의에도 근거가
생기고, 그러면 「근거가 없다」가 영원히 성립하지 않는다. 그래서 정답 chunk 까지의 거리
분포와 **정답이 아닌 최근접**까지의 거리 분포를 함께 재고, 둘이 갈라지는 자리를 상한으로
쓴다.

## 측정용 DB 는 따로 만든다

`clovir_s10bench` 를 새로 만들고 alembic 을 돌린 뒤 chunk 를 싣는다. 시험 DB 를 쓰면
그 순간 이 벤치가 시험 결과를 바꿀 수 있다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

BENCH_DB = "clovir_s10bench"
#: 상한을 재려면 상한 **없이** 한 번 받아야 한다. 코사인 거리의 최대는 2 다.
NO_CEILING = 2.0
#: 격자. `w_trgm` 은 1.0 으로 고정한다 — 셋 다 흔들면 배수만 다른 같은 조합이 늘어난다.
FTS_WEIGHTS = (0.0, 0.25, 0.5, 0.75, 1.0)
VECTOR_WEIGHTS = (0.0, 0.5, 1.0, 1.5, 2.0)
CEILINGS = (0.06, 0.08, 0.10, 0.12, 0.14, 0.16, 0.18, 0.20, 0.25, NO_CEILING)


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open(encoding="utf-8")]


def _tsv(path: Path) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for line in path.open(encoding="utf-8"):
        key, _sep, body = line.rstrip("\n").partition("\t")
        out[key] = [float(v) for v in body.strip("[]").split(",")]
    return out


# ── 측정용 DB ────────────────────────────────────────────────────────────────


def _admin_url(base: str) -> str:
    from app.core.db import normalize_database_url

    return normalize_database_url(base)


def build_database(base_url: str, chunks, vectors) -> str:
    from sqlalchemy import create_engine, text

    from app.core.db import normalize_database_url

    admin = create_engine(_admin_url(base_url), isolation_level="AUTOCOMMIT", future=True)
    with admin.connect() as conn:
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :d AND pid <> pg_backend_pid()"
            ),
            {"d": BENCH_DB},
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{BENCH_DB}"'))
        conn.execute(text(f'CREATE DATABASE "{BENCH_DB}"'))
    admin.dispose()

    url = base_url.rsplit("/", 1)[0] + "/" + BENCH_DB
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    os.environ["DATABASE_URL"] = normalize_database_url(url)
    command.upgrade(cfg, "head")

    _load(url, chunks, vectors)
    return url


def _load(url: str, chunks, vectors) -> None:
    """chunk 를 **진짜 스키마에** 싣는다. 벡터가 없는 chunk 는 안 만든다."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.ai import catalog
    from app.ai.models import ANCHOR_TEXT, SOURCE_DOCUMENT, DocumentChunk
    from app.core.db import normalize_database_url
    from app.core.models_base import utcnow
    from app.knowledge.models import Document, KnowledgeSpace
    from app.org.constants import DEFAULT_ORG_ID

    engine = create_engine(normalize_database_url(url), future=True)
    now = utcnow()
    with Session(engine) as db:
        space = KnowledgeSpace(
            org_id=DEFAULT_ORG_ID, name="벤치", slug="bench", owner_kind="organization"
        )
        db.add(space)
        db.flush()
        documents: dict[str, str] = {}
        for row in chunks:
            if row["document"] not in documents:
                doc = Document(space_id=space.id, title=row["title"])
                db.add(doc)
                db.flush()
                documents[row["document"]] = doc.id
            vector = vectors.get(row["id"])
            if vector is None:
                continue
            db.add(DocumentChunk(
                source_kind=SOURCE_DOCUMENT,
                document_id=documents[row["document"]],
                ordinal=row["ordinal"],
                anchor_kind=ANCHOR_TEXT,
                anchor_ref=str(row["ordinal"]),
                anchor_label=row["id"],
                text_body=row["text"],
                text_sha256=hashlib.sha256(row["text"].encode("utf-8")).hexdigest(),
                embedding=tuple(vector),
                parser_version=catalog.PARSER_VERSION,
                embedding_model=catalog.DEFAULT_EMBEDDING_MODEL_ID,
                embedding_version=catalog.EMBEDDING_VERSION,
                indexed_at=now,
                embedded_at=now,
            ))
        db.commit()
    engine.dispose()


# ── 레인 순위 받기 ───────────────────────────────────────────────────────────


def collect(url: str, queries, query_vectors, *, lane_limit: int):
    """질의마다 세 레인의 순위. 벡터 레인은 **거리까지** 함께 받는다."""
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.ai.models import DocumentChunk
    from app.ai.retrieval import query as query_mod
    from app.core.db import normalize_database_url

    engine = create_engine(normalize_database_url(url), future=True)
    out = []
    timing = {"trgm": [], "fts": [], "vector": []}
    with Session(engine) as db:
        labels = dict(
            db.execute(select(DocumentChunk.id, DocumentChunk.anchor_label)).all()
        )

        def run(statement, bucket):
            started = time.perf_counter()
            rows = db.execute(statement).all()
            timing[bucket].append((time.perf_counter() - started) * 1000)
            return rows

        for item in queries:
            text_query = query_mod.normalize_query(item["query"])
            trgm = [
                labels[str(r[0])]
                for r in run(query_mod.trgm_lane(text_query, limit=lane_limit), "trgm")
            ]
            fts = [
                labels[str(r[0])]
                for r in run(query_mod.fts_lane(text_query, limit=lane_limit), "fts")
            ]
            vector_rows = run(
                query_mod.vector_lane(
                    query_vectors[item["query"]], limit=lane_limit, max_distance=NO_CEILING
                ),
                "vector",
            )
            out.append({
                "kind": item["kind"],
                "query": item["query"],
                "gold": item["gold"],
                "trgm": trgm,
                "fts": fts,
                "vector": [(labels[str(r[0])], float(r[1])) for r in vector_rows],
            })
    engine.dispose()
    return out, timing


# ── 점수 ─────────────────────────────────────────────────────────────────────


def rank_of(ranked: list[str], gold: str) -> int | None:
    try:
        return ranked.index(gold) + 1
    except ValueError:
        return None


def score(ranked_lists, *, at=(1, 5), mrr_at=10) -> dict:
    total = len(ranked_lists)
    if not total:
        return {}
    hits = {k: 0 for k in at}
    reciprocal = 0.0
    for ranked, gold in ranked_lists:
        position = rank_of(ranked, gold)
        if position is None:
            continue
        for k in at:
            if position <= k:
                hits[k] += 1
        if position <= mrr_at:
            reciprocal += 1.0 / position
    out = {f"recall@{k}": round(hits[k] / total, 4) for k in at}
    out[f"mrr@{mrr_at}"] = round(reciprocal / total, 4)
    out["n"] = total
    return out


def fuse_one(record, *, w_fts: float, w_vector: float, ceiling: float, k: int) -> list[str]:
    from app.ai.retrieval import fusion

    rankings = {
        fusion.LANE_TRGM: record["trgm"],
        fusion.LANE_FTS: record["fts"],
        fusion.LANE_VECTOR: [key for key, distance in record["vector"] if distance <= ceiling],
    }
    weights = {
        fusion.LANE_TRGM: 1.0, fusion.LANE_FTS: w_fts, fusion.LANE_VECTOR: w_vector,
    }
    scores: dict[str, float] = {}
    for lane, keys in rankings.items():
        weight = weights[lane]
        if not weight:
            continue
        for position, key in enumerate(keys, start=1):
            scores[key] = scores.get(key, 0.0) + weight / (k + position)
    return [key for key, _s in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]


def by_kind(records, ranker) -> dict:
    out = {"all": score([(ranker(r), r["gold"]) for r in records])}
    for kind in sorted({r["kind"] for r in records}):
        subset = [r for r in records if r["kind"] == kind]
        out[kind] = score([(ranker(r), r["gold"]) for r in subset])
    return out


def distance_separation(records) -> dict:
    """정답까지의 거리 vs **정답이 아닌 최근접**까지의 거리. 상한의 근거다."""
    gold, other = [], []
    for record in records:
        ranked = record["vector"]
        for key, distance in ranked:
            if key == record["gold"]:
                gold.append(distance)
                break
        for key, distance in ranked:
            if key != record["gold"]:
                other.append(distance)
                break

    def stats(values):
        if not values:
            return {}
        values = sorted(values)
        return {
            "n": len(values),
            "min": round(values[0], 4),
            "p10": round(values[int(len(values) * 0.10)], 4),
            "p50": round(statistics.median(values), 4),
            "p90": round(values[int(len(values) * 0.90)], 4),
            "max": round(values[-1], 4),
        }

    return {"gold": stats(gold), "nearest_non_gold": stats(other)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus_dir")
    parser.add_argument("out_json")
    parser.add_argument(
        "--pg-url",
        default=os.environ.get(
            "CLOVIR_TEST_PG_URL", "postgresql://cloviradmin:s2devpw@127.0.0.1:55433/postgres"
        ),
    )
    parser.add_argument("--lane-limit", type=int, default=50)
    args = parser.parse_args()

    corpus = Path(args.corpus_dir)
    chunks = _rows(corpus / "chunks.jsonl")
    queries = _rows(corpus / "queries.jsonl")
    chunk_vectors = _tsv(corpus / "e5small_chunks.tsv")
    query_vectors = _tsv(corpus / "e5small_queries.tsv")
    print(f"chunk {len(chunks)} · 질의 {len(queries)} · 벡터 {len(chunk_vectors)}")

    url = build_database(args.pg_url, chunks, chunk_vectors)
    records, timing = collect(url, queries, query_vectors, lane_limit=args.lane_limit)

    from app.ai.retrieval import fusion

    report: dict = {
        "corpus": json.loads((corpus / "corpus_summary.json").read_text(encoding="utf-8")),
        "lane_limit": args.lane_limit,
        "rrf_k": fusion.RRF_K,
        "lane_ms": {
            lane: {
                "p50": round(statistics.median(values), 2),
                "p95": round(sorted(values)[int(len(values) * 0.95)], 2),
            }
            for lane, values in timing.items() if values
        },
        "single_lane": {
            "trgm": by_kind(records, lambda r: r["trgm"]),
            "fts": by_kind(records, lambda r: r["fts"]),
            "vector_no_ceiling": by_kind(records, lambda r: [k for k, _d in r["vector"]]),
        },
        "distance": distance_separation(records),
        "ceiling_sweep": {},
        "weight_sweep": [],
    }

    # 1) 거리 상한 — 가중치는 D-209 초기값으로 고정하고 상한만 흔든다.
    for ceiling in CEILINGS:
        report["ceiling_sweep"][f"{ceiling:g}"] = by_kind(
            records,
            lambda r, c=ceiling: fuse_one(
                r, w_fts=0.5, w_vector=1.0, ceiling=c, k=fusion.RRF_K
            ),
        )["all"]

    # 2) 가중치 격자. **상한 여럿에서** 돈다 — 상한 하나로 고정하면, 그 상한이 벡터
    #    레인을 비우는 값일 때 `w_vector` 가 아무 효과가 없어서 「가중치를 쟀다」가
    #    사실은 「벡터를 끈 채로 쟀다」가 된다. 실제로 한 번 그렇게 나왔다.
    for ceiling in (0.10, 0.14, fusion.VECTOR_MAX_DISTANCE, 0.20):
        for w_fts in FTS_WEIGHTS:
            for w_vector in VECTOR_WEIGHTS:
                scored = by_kind(
                    records,
                    lambda r, f=w_fts, v=w_vector, c=ceiling: fuse_one(
                        r, w_fts=f, w_vector=v, ceiling=c, k=fusion.RRF_K
                    ),
                )
                report["weight_sweep"].append({
                    "ceiling": ceiling, "w_trgm": 1.0, "w_fts": w_fts,
                    "w_vector": w_vector, **scored,
                })

    report["weight_sweep"].sort(key=lambda row: -row["all"]["mrr@10"])

    def pick(ceiling: float, w_fts: float, w_vector: float):
        for row in report["weight_sweep"]:
            if (row["ceiling"], row["w_fts"], row["w_vector"]) == (ceiling, w_fts, w_vector):
                return row
        return None

    # **지금 제품이 쓰는 값**과 D-209 초기값을 같은 표에 나란히 남긴다. 「그래서 무엇이
    # 얼마나 좋아졌나」를 나중에 사람이 다시 계산하지 않아도 되게.
    report["chosen"] = {
        "w_trgm": fusion.WEIGHTS[fusion.LANE_TRGM],
        "w_fts": fusion.WEIGHTS[fusion.LANE_FTS],
        "w_vector": fusion.WEIGHTS[fusion.LANE_VECTOR],
        "vector_max_distance": fusion.VECTOR_MAX_DISTANCE,
        "scores": pick(
            fusion.VECTOR_MAX_DISTANCE,
            fusion.WEIGHTS[fusion.LANE_FTS],
            fusion.WEIGHTS[fusion.LANE_VECTOR],
        ),
        "argmax": report["weight_sweep"][0],
    }
    report["d209_initial"] = pick(fusion.VECTOR_MAX_DISTANCE, 0.5, 1.0)
    report["note"] = (
        "Corpus 는 이 저장소의 한국어 문서다. 미러(web.sqlite3)에 본문이 없어서"
        " (2026-08-23 실측: document_cache 0건 · ticket_cache 31건) 업무 기록으로는"
        " 잴 수 없었다. 어휘 분포가 티켓·회의록과 다르므로 절대값이 아니라"
        " 가중치·상한 사이의 비교로 읽는다. 그리고 이 Corpus 는 한 문서"
        " (docs/DECISIONS.md)가 66%라 주제가 매우 동질적이다 — 그래서 벡터 레인이"
        " 정답과 오답을 거리로 못 가른다(정답 p50 0.1401 · 최근접 오답 p50 0.1375)."
        " 상한의 값은 그 사실 때문에 S9 의 주제 분리 실측(0.1151 대 0.1984)과 함께 읽는다."
    )
    Path(args.out_json).write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    kinds = ["all"] + sorted({r["kind"] for r in records})
    header = " ".join(f"{k:>9s}" for k in kinds)

    def line(label: str, values: dict) -> str:
        return f"  {label:26s}" + " ".join(f"{values[k]['mrr@10']:9.4f}" for k in kinds)

    print("\n단일 레인 (MRR@10)         " + header)
    for lane, values in report["single_lane"].items():
        print(line(lane, values))
    print("\n거리 상한 (융합 MRR@10 · 가중치는 D-209 초기값)")
    for ceiling, values in report["ceiling_sweep"].items():
        print(f"  {ceiling:>5s}  mrr={values['mrr@10']:.4f}  r@1={values['recall@1']:.4f}")
    print(f"\n거리 분포  정답={report['distance']['gold']}")
    print(f"           최근접오답={report['distance']['nearest_non_gold']}")
    print("\n가중치 (MRR@10)            " + header)
    print(line("D-209 초기값 .5/1.0", report["d209_initial"]))
    print(line("S10 채택", report["chosen"]["scores"]))
    print(line("격자 최고", report["chosen"]["argmax"]))
    print("\nwrote", args.out_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
