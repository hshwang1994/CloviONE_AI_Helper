# -*- coding: utf-8 -*-
"""A7 — 사람이 **다르게 말한** 질문으로 문서 단위 검색을 잰다 (D-570). 낱말 검색(A6 전 · 후)과 의미 검색(A7 뒤)을 같은 질문으로 비교한다.

    python scripts/bench/retrieval_paraphrase.py --queries var/bench/lab_paraphrase_queries.json \\
        --as-user <이메일> --label a6-after --no-vector
    python scripts/bench/retrieval_paraphrase.py --queries var/bench/lab_paraphrase_queries.json \\
        --as-user <이메일> --label a7-hybrid

## 질문 파일

    [{"id": "p01", "question": "휴가 쓰려면 어디서 신청해?", "gold": ["연차 휴가 신청 절차"]}, …]

`gold` 는 정답 문서의 **제목**(대소문자 · 공백을 접어 정확히 같은 것)이나 문서 id(UUID) 목록이다. 그중 하나라도 순위에 들면 맞힌
것이다. 랩의 실제 질문은 저장소에 넣지 않는다 — 랩 문서 제목이 들어가므로 `var/bench/lab_paraphrase_queries.json`(gitignore 된
`var/`)에 둔다. 모양 시험용 여섯 개는 `tests/fixtures/ai_paraphrase_sample.json` 이다(제목은 지어낸 것).

## 무엇을 재는가

제품 함수 `app.ai.retrieval.service.retrieve(…, top_k=10, distinct_documents=True)` 를 **그대로** 부른다 — AI 도우미의
`search_documents` 와 같은 문서 단위 순위다. 여기서 SQL 을 다시 쓰면 잰 것과 운영이 도는 것이 다른 질의가 된다.

  * Recall@1 · Recall@5 · MRR@10(정답 문서가 처음 나온 자리)
  * 레인별 후보 수의 평균(`lane_counts` — trgm · fts · vector)과 벡터 레인이 안 돈 까닭의 분포(`vector_status`)
  * 벡터가 있으면 정답 문서의 가장 가까운 조각과 질의 벡터의 코사인 거리 p50 · p90 — 벡터 레인의 바닥
    (`fusion.VECTOR_MAX_DISTANCE`)보다 먼 정답이 몇 개인지도 센다. 바닥이 너무 낮으면 의미 검색이 정답을 버린다.

`--as-user` 의 권한으로 찾는다(가시성 절이 `LIMIT` 앞에 걸린다). 그 사람이 못 보는 정답은 「풀지 못한 정답」으로 따로 적고 점수에서
뺀다.

## 읽기만 한다

세션을 `READ ONLY` 로 열고 끝에 되감는다. 데이터베이스 주소는 `--pg-url` 이 없으면 제품 설정(`Settings().database_url`, 서버의
환경 파일)이다. 결과에는 질문 글과 제목을 싣지 않는다(질문 id · 순위 · 수만) — 결과 파일을 증거 문서에 그대로 옮겨도 랩 문서
제목이 새지 않는다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TOP_K = 10
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


# ── 순수 함수 (tests/unit/test_ai_truth_harness.py) ─────────────────────────────


def norm(text) -> str:
    """제목 대조 꼴 — NFKC · 소문자 · 연속 공백 한 칸."""
    value = unicodedata.normalize("NFKC", str(text or "")).casefold()
    return " ".join(value.split())


def load_queries(path) -> list[dict]:
    """질문 파일을 읽고 모양을 본다. 틀리면 `ValueError`(어느 항목이 왜 틀렸는지)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("질문 파일은 비어 있지 않은 목록이어야 합니다.")
    seen: set[str] = set()
    out: list[dict] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"{index}번째 항목이 객체가 아닙니다.")
        qid, question, gold = item.get("id"), item.get("question"), item.get("gold")
        if not isinstance(qid, str) or not qid.strip():
            raise ValueError(f"{index}번째 항목에 id 가 없습니다.")
        if qid in seen:
            raise ValueError(f"id {qid} 가 두 번 나옵니다.")
        if not isinstance(question, str) or len(question.strip()) < 2:
            raise ValueError(f"{qid} 의 question 이 비었거나 너무 짧습니다.")
        if not isinstance(gold, list) or not gold or not all(isinstance(g, str) and g.strip() for g in gold):
            raise ValueError(f"{qid} 의 gold 는 비어 있지 않은 문자열 목록이어야 합니다.")
        seen.add(qid)
        out.append({"id": qid, "question": question.strip(), "gold": [g.strip() for g in gold]})
    return out


def first_hit(ranked, gold) -> int | None:
    """순위 목록에서 정답이 처음 나온 자리(1부터). 없으면 None."""
    wanted = set(gold or ())
    for index, key in enumerate(ranked or ()):
        if key in wanted:
            return index + 1
    return None


def score(rows) -> dict:
    """`rows` = [(순위 목록, 정답 집합)] → Recall@1 · Recall@5 · MRR@10."""
    rows = list(rows)
    n = len(rows)
    if not n:
        return {"n": 0, "recall@1": None, "recall@5": None, "mrr@10": None}
    ranks = [first_hit(ranked, gold) for ranked, gold in rows]
    r1 = sum(1 for r in ranks if r == 1) / n
    r5 = sum(1 for r in ranks if r is not None and r <= 5) / n
    mrr = sum((1.0 / r) if r is not None and r <= 10 else 0.0 for r in ranks) / n
    return {"n": n, "recall@1": round(r1, 3), "recall@5": round(r5, 3), "mrr@10": round(mrr, 3)}


def percentile(values, p: float) -> float | None:
    """선형 보간 백분위(p 는 0 ~ 100). 값이 없으면 None."""
    data = sorted(float(v) for v in values if v is not None)
    if not data:
        return None
    if len(data) == 1:
        return round(data[0], 4)
    k = (len(data) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(data) - 1)
    return round(data[lo] + (data[hi] - data[lo]) * (k - lo), 4)


def resolve_gold(gold, titles_to_ids: dict[str, set[str]], visible_ids: set[str]) -> set[str]:
    """정답 표기(제목 · id) → 보이는 문서 id 집합. 제목은 접어서 정확히 같은 것만 받는다."""
    out: set[str] = set()
    for entry in gold or ():
        if _UUID.match(entry):
            if entry in visible_ids:
                out.add(entry)
            continue
        out |= titles_to_ids.get(norm(entry), set())
    return out


def mask_email(text: str) -> str:
    def one(m):
        local, _, domain = m.group(0).partition("@")
        return f"{local[:1]}****{local[-1:]}@{domain}"
    return _EMAIL.sub(one, text or "")


# ── 실행 ─────────────────────────────────────────────────────────────────────


def _visible_titles(db, user) -> tuple[dict[str, set[str]], set[str]]:
    from sqlalchemy import select

    from app.ai.retrieval.service import visible_document_ids
    from app.knowledge.models import Document

    rows = db.execute(select(Document.id, Document.title).where(Document.id.in_(visible_document_ids(db, user)))).all()
    titles: dict[str, set[str]] = {}
    ids: set[str] = set()
    for doc_id, title in rows:
        ids.add(str(doc_id))
        titles.setdefault(norm(title), set()).add(str(doc_id))
    return titles, ids


def _gold_distance(db, vector, gold_ids: set[str]) -> float | None:
    """정답 문서의 가장 가까운 조각과 질의 벡터의 코사인 거리."""
    from sqlalchemy import Float, cast, func, literal, select

    from app.ai.catalog import VECTOR_DIM
    from app.ai.models import DocumentChunk, Vector
    from app.ai.retrieval.query import vector_literal

    if not gold_ids:
        return None
    target = cast(literal(vector_literal(vector)), Vector(VECTOR_DIM))
    distance = DocumentChunk.embedding.op("<=>", return_type=Float)(target)
    value = db.execute(
        select(func.min(distance)).where(DocumentChunk.document_id.in_(sorted(gold_ids)),
                                         DocumentChunk.embedding.isnot(None))
    ).scalar_one_or_none()
    return None if value is None else round(float(value), 4)


def run(args) -> dict:
    from sqlalchemy import text

    from app.ai import catalog
    from app.ai.gateway import contract, registry
    from app.ai.retrieval import fusion
    from app.ai.retrieval.service import retrieve
    from app.core.config import Settings
    from app.core.db import make_engine, make_session_factory
    from app.users.service import get_user_by_email

    queries = load_queries(args.queries)
    settings = Settings()
    engine = make_engine(args.pg_url or settings.database_url)
    factory = make_session_factory(engine)
    gateway = contract.Gateway(enabled=False) if args.no_vector else registry.build_gateway(settings)
    vector_on = bool(gateway.capabilities().embed.available)

    per_query: list[dict] = []
    rows: list[tuple[list[str], set[str]]] = []
    lanes_total: dict[str, int] = {}
    vector_status: dict[str, int] = {}
    distances: list[float] = []
    unresolved: list[str] = []
    with factory() as db:
        try:
            db.execute(text("SET TRANSACTION READ ONLY"))
            db.execute(text("SET LOCAL statement_timeout = 30000"))
            user = get_user_by_email(db, args.as_user)
            if user is None:
                raise SystemExit("그 이메일의 사용자가 없습니다.")
            titles, visible = _visible_titles(db, user)
            for item in queries:
                gold_ids = resolve_gold(item["gold"], titles, visible)
                if not gold_ids:
                    unresolved.append(item["id"])
                    per_query.append({"id": item["id"], "gold_resolved": 0, "rank": None})
                    continue
                result = retrieve(db, user, raw_query=item["question"], gateway=gateway, top_k=TOP_K,
                                  distinct_documents=True)
                ranked = [c.document_id for c in result.citations]
                rows.append((ranked, gold_ids))
                for lane, count in (result.lane_counts or {}).items():
                    lanes_total[lane] = lanes_total.get(lane, 0) + int(count)
                status = result.vector_status or "ok"
                vector_status[status] = vector_status.get(status, 0) + 1
                distance = None
                if vector_on:
                    embedded = gateway.embed([item["question"]], kind=catalog.KIND_QUERY)
                    if embedded.ok and embedded.vectors:
                        distance = _gold_distance(db, embedded.vectors[0], gold_ids)
                        if distance is not None:
                            distances.append(distance)
                per_query.append({"id": item["id"], "gold_resolved": len(gold_ids), "rank": first_hit(ranked, gold_ids),
                                  "lanes": dict(result.lane_counts or {}), "vector_status": result.vector_status,
                                  "gold_distance": distance})
        finally:
            db.rollback()
    engine.dispose()

    measured = len(rows)
    report = {
        "label": args.label,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_user": mask_email(args.as_user),
        "vector": vector_on,
        "queries": len(queries),
        "measured": measured,
        "gold_unresolved": unresolved,
        "scores": score(rows),
        "lanes_mean": {lane: round(total / measured, 2) for lane, total in sorted(lanes_total.items())} if measured else {},
        "vector_status": vector_status,
        "gold_distance": {
            "n": len(distances),
            "p50": percentile(distances, 50),
            "p90": percentile(distances, 90),
            "max_distance": fusion.VECTOR_MAX_DISTANCE,
            "over_max": sum(1 for d in distances if d > fusion.VECTOR_MAX_DISTANCE),
        },
        "per_query": per_query,
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="패러프레이즈 질문으로 문서 단위 검색을 잰다(A7).")
    parser.add_argument("--queries", required=True, help="질문 파일(JSON 목록). 랩 질문은 var/bench/ 에 둔다.")
    parser.add_argument("--as-user", required=True, help="이 사용자의 권한으로 찾는다(이메일)")
    parser.add_argument("--no-vector", action="store_true", help="의미 검색을 끄고 낱말 레인만 잰다")
    parser.add_argument("--label", default="run", help="결과 이름(파일 이름에 들어간다)")
    parser.add_argument("--out", default=None, help="결과 경로(기본: dist/bench/retrieval_paraphrase-<label>.json)")
    parser.add_argument("--pg-url", default=None, help="데이터베이스 주소(기본: 제품 설정의 DATABASE_URL)")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    report = run(args)
    out = Path(args.out) if args.out else ROOT / "dist" / "bench" / f"retrieval_paraphrase-{args.label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    summary = {k: report[k] for k in ("label", "vector", "queries", "measured", "gold_unresolved", "scores",
                                      "lanes_mean", "gold_distance")}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"RETRIEVAL_PARAPHRASE OK → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
