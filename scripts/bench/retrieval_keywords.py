# -*- coding: utf-8 -*-
"""D-536 — 사람이 쓴 **문장** 질문이 낱말 질문만큼 찾히는가 (P8 관문: Recall@5 ≥ 낱말 기준의 0.8).

    python scripts/bench/retrieval_keywords.py <출력.json> [--docs docs] [--pg-url …]

## 무엇을 재는가

S10 의 말뭉치(`retrieval_corpus.py` — 이 저장소의 한국어 문서를 제품 chunk 규칙으로 자른 것)에서 chunk 하나를 골라 그 chunk 의
**내용 낱말 둘 ~ 셋**을 뽑고, 같은 낱말로 질문 두 모양을 만든다:

  * `bare`    낱말만 — 「연차 신청」. 사람이 검색창에 치는 모양이고 이 측정의 **기준**이다.
  * `natural` 문장 — 「연차 신청은 어떻게 하나요?」, 「연차 신청 관련 문서 찾아줘」, 「연차 신청에 대해 알려줘」. AI 에게 쓰는 모양이다.

정답은 그 chunk 하나다. 세 갈래를 잰다(벡터 없이 — 의미 검색 모델이 없는 설치가 흔하고, 낱말 레인이 혼자 짊어지는 경우를 본다):

  * `old_natural` 낱말 없는 옛 레인(검색창 규칙)에 문장 질문 — 고치기 전의 AI 검색
  * `new_natural` 낱말 레인(D-536)에 문장 질문 — 고친 뒤의 AI 검색
  * `new_bare`    낱말 레인에 낱말 질문 — 기준

관문은 `new_natural` 의 Recall@5 ≥ `new_bare` 의 Recall@5 × 0.8 이다. 제품의 레인 SQL(`app/ai/retrieval/query.py`)과 융합
(`fusion.fuse`)을 **그대로** 부른다 — 여기서 SQL 을 다시 쓰면 잰 것과 운영이 도는 것이 다른 질의가 된다.

## 측정용 DB 는 따로 만든다

`retrieval_fusion.py` 와 같은 `clovir_s10bench` 를 새로 만들고 alembic 을 돌린 뒤 chunk 를 싣는다(벡터 없이). 시험 DB 를 쓰면 그
순간 이 측정이 시험 결과를 바꿀 수 있다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SEED = 20261001
QUERIES = 300
GATE = 0.8
_HANGUL_WORD = re.compile(r"^[가-힣]{2,8}$")
TEMPLATES = (
    "{a} {b}은 어떻게 하나요?",
    "{a} {b} 관련 문서 찾아줘",
    "{a} {b}에 대해 알려줘",
    "{a}의 {b} 내용을 알려 주세요",
)


def _load_without_vectors(url: str, chunks) -> None:
    """chunk 를 진짜 스키마에 **벡터 없이** 싣는다(`retrieval_fusion._load` 는 벡터가 없는 chunk 를 건너뛴다)."""
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
        space = KnowledgeSpace(org_id=DEFAULT_ORG_ID, name="벤치", slug="bench", owner_kind="organization")
        db.add(space)
        db.flush()
        documents: dict[str, str] = {}
        for row in chunks:
            if row["document"] not in documents:
                doc = Document(space_id=space.id, title=row["title"])
                db.add(doc)
                db.flush()
                documents[row["document"]] = doc.id
            db.add(DocumentChunk(
                source_kind=SOURCE_DOCUMENT, document_id=documents[row["document"]], ordinal=row["ordinal"],
                anchor_kind=ANCHOR_TEXT, anchor_ref=str(row["ordinal"]), anchor_label=row["id"], text_body=row["text"],
                text_sha256=hashlib.sha256(row["text"].encode("utf-8")).hexdigest(),
                parser_version=catalog.PARSER_VERSION, indexed_at=now,
            ))
        db.commit()
    engine.dispose()


def make_queries(rng: random.Random, chunks: list[dict]) -> list[dict]:
    """chunk 마다 내용 낱말 둘을 골라 낱말 질문과 문장 질문을 만든다. 두 낱말이 **함께** 든 chunk 가 다섯 개를 넘으면 버린다 —
    정답이 흐려지면 순위가 아니라 우연을 잰다."""
    from app.core.search_text import keywords

    flat = {c["id"]: " ".join(c["text"].split()) for c in chunks}
    pool = [c for c in chunks if len(c["text"]) >= 120]
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for chunk in rng.sample(pool, len(pool)):
        if len(out) >= QUERIES:
            break
        words = [w for w in keywords(chunk["text"], limit=40) if _HANGUL_WORD.match(w)]
        if len(words) < 2:
            continue
        a, b = rng.sample(words, 2)
        if (a, b) in seen:
            continue
        holders = [key for key, body in flat.items() if a in body and b in body]
        if chunk["id"] not in holders or len(holders) > 5:
            continue
        seen.add((a, b))
        template = TEMPLATES[len(out) % len(TEMPLATES)]
        out.append({"gold": chunk["id"], "bare": f"{a} {b}", "natural": template.format(a=a, b=b), "holders": len(holders)})
    return out


def rank(db, labels, text: str, words, *, lane_limit: int) -> list[str]:
    from app.ai.retrieval import fusion
    from app.ai.retrieval import query as query_mod

    trgm = [labels[str(r[0])] for r in db.execute(query_mod.trgm_lane(text, keywords=words, limit=lane_limit)).all()]
    fts = [labels[str(r[0])] for r in db.execute(query_mod.fts_lane(text, keywords=words, limit=lane_limit)).all()]
    fused = fusion.fuse({fusion.LANE_TRGM: trgm, fusion.LANE_FTS: fts}, limit=10)
    return [row.key for row in fused]


def score(pairs) -> dict:
    n = len(pairs) or 1
    r1 = sum(1 for ranked, gold in pairs if ranked[:1] == [gold]) / n
    r5 = sum(1 for ranked, gold in pairs if gold in ranked[:5]) / n
    mrr = sum((1.0 / (ranked.index(gold) + 1)) if gold in ranked[:10] else 0.0 for ranked, gold in pairs) / n
    return {"n": len(pairs), "recall@1": round(r1, 3), "recall@5": round(r5, 3), "mrr@10": round(mrr, 3)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("out_json")
    parser.add_argument("--docs", default="docs")
    parser.add_argument("--pg-url", default=os.environ.get(
        "CLOVIR_TEST_PG_URL", "postgresql://cloviradmin:s2devpw@127.0.0.1:55433/postgres"))
    parser.add_argument("--lane-limit", type=int, default=50)
    args = parser.parse_args()

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.ai.models import DocumentChunk
    from app.ai.retrieval import query as query_mod
    from app.core.db import normalize_database_url
    from app.core.search_text import keywords
    from scripts.bench import retrieval_corpus, retrieval_fusion

    chunks = retrieval_corpus.build_chunks(ROOT / args.docs)
    queries = make_queries(random.Random(SEED), chunks)
    retrieval_fusion._load = lambda url, rows, _vectors: _load_without_vectors(url, rows)  # noqa: SLF001 - 벡터 없이 싣는다
    url = retrieval_fusion.build_database(args.pg_url, chunks, {})

    engine = create_engine(normalize_database_url(url), future=True)
    pairs = {"old_natural": [], "new_natural": [], "new_bare": []}
    with Session(engine) as db:
        labels = dict(db.execute(select(DocumentChunk.id, DocumentChunk.anchor_label)).all())
        for item in queries:
            natural = query_mod.normalize_query(item["natural"])
            bare = query_mod.normalize_query(item["bare"])
            pairs["old_natural"].append((rank(db, labels, natural, (), lane_limit=args.lane_limit), item["gold"]))
            pairs["new_natural"].append((rank(db, labels, natural, keywords(item["natural"]), lane_limit=args.lane_limit), item["gold"]))
            pairs["new_bare"].append((rank(db, labels, bare, keywords(item["bare"]), lane_limit=args.lane_limit), item["gold"]))
    engine.dispose()

    report = {"seed": SEED, "chunks": len(chunks), "queries": len(queries), "gate": GATE,
              "scores": {name: score(rows) for name, rows in pairs.items()},
              "samples": queries[:6]}
    base = report["scores"]["new_bare"]["recall@5"]
    got = report["scores"]["new_natural"]["recall@5"]
    report["ratio"] = round(got / base, 3) if base else None
    report["pass"] = bool(base) and got >= base * GATE
    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("chunks", "queries", "scores", "ratio", "pass")}, ensure_ascii=False, indent=1))
    print("RETRIEVAL_KEYWORDS " + ("OK" if report["pass"] else "FAILED"))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
