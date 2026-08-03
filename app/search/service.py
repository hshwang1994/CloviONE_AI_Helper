"""통합 검색 실행 — 인덱스 조회 + 범위 필터 + 유형별 묶음 (PLAN Phase 5).

응답은 **유형별 그룹**이다. 한 줄로 섞어 내보내면 화면이 유형을 다시 분류해야 하고, 그
분류 규칙이 백엔드와 어긋나는 순간 아무도 모르게 결과가 사라진다.

## 왜 후보를 넉넉히 뽑아서 파이썬에서 거르는가

부서 범위 판정은 '담당자 집합 중 한 명이라도 범위 안'이다(app/core/scope.py). 이걸 SQL 로
쓰면 부서원 수만큼 LIKE 를 OR 로 잇게 되고, 규칙이 scope.py 와 여기 두 곳에 살게 된다 —
두 곳에 살면 반드시 갈라진다. 코퍼스가 수천 건 규모라 후보 상한(`CANDIDATE_LIMIT`)만큼
뽑아 `any_assignee_visible` 로 거르는 편이 단순하고 규칙이 한 곳에 남는다.
"""

from __future__ import annotations

import logging

from sqlalchemy import literal_column, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.authz import CONSOLE_WRITE_ROLES
from app.core.scope import Principal
from app.search import query as q
from app.search.models import (
    KIND_LABELS,
    KIND_USER,
    SEARCH_KINDS,
    SearchDocument,
)
from app.search.scoping import owner_gate, row_visible, sql_clause

logger = logging.getLogger("app.search")

# 범위 필터 전에 뽑아 둘 후보 수. 부서 범위에서 대부분이 걸러질 수 있으므로 넉넉히 잡는다.
CANDIDATE_LIMIT = 400

# 그룹당 기본 노출 건수와 전체 상한.
DEFAULT_PER_KIND = 8
DEFAULT_TOTAL = 50
MAX_PER_KIND = 50

# 유형별 역할 게이트. **사용자 유형은 사용자 관리 화면을 열 수 있는 역할에게만** 나간다 —
# `/api/admin/users` 가 admin+ 이므로 검색이 그 경계를 우회하면 안 되고, 아무나 사람을
# 조회할 수 있으면 검색창이 조직도 열거 도구가 된다.
KIND_ROLE_GATE: dict[str, frozenset[str]] = {KIND_USER: frozenset(CONSOLE_WRITE_ROLES)}


def allowed_kinds(role: str) -> tuple[str, ...]:
    """이 역할이 결과로 받을 수 있는 유형. 채팅은 애초에 `SEARCH_KINDS` 에 없다."""
    out = []
    for kind in SEARCH_KINDS:
        gate = KIND_ROLE_GATE.get(kind)
        if gate is None or role in gate:
            out.append(kind)
    return tuple(out)


def _fts_candidates(db: Session, expression: str) -> list[int]:
    """`search_index` 에서 관련도(rank) 순 rowid. 실패하면 빈 목록(호출측이 LIKE 로 내려간다)."""
    rows = db.execute(
        text(
            "SELECT rowid FROM search_index WHERE search_index MATCH :m "
            "ORDER BY rank LIMIT :cap"
        ),
        {"m": expression, "cap": CANDIDATE_LIMIT},
    ).scalars().all()
    return [int(r) for r in rows]


def _hit(row: SearchDocument) -> dict:
    """결과 한 줄. **인덱스가 라우트를 들고 있다** — 화면이 유형별 if 를 갖지 않게."""
    return {
        "kind": row.kind,
        "id": row.ref_id,
        "title": row.title or "(제목 없음)",
        "subtitle": row.subtitle or "",
        "route": row.route or "",
        "url": row.url or None,
    }


def _empty(query_text: str, mode: str) -> dict:
    return {"query": query_text, "mode": mode, "total": 0, "truncated": False, "groups": []}


def search(
    db: Session,
    *,
    raw_query: str | None,
    principal: Principal,
    per_kind: int = DEFAULT_PER_KIND,
    total_limit: int = DEFAULT_TOTAL,
) -> dict:
    """범위를 통과한 결과만 유형별로 묶어 돌려준다."""
    text_query = q.normalize(raw_query)
    mode = q.mode_for(text_query)
    if mode == q.MODE_EMPTY:
        return _empty(text_query, mode)

    per_kind = max(1, min(int(per_kind or DEFAULT_PER_KIND), MAX_PER_KIND))
    kinds = allowed_kinds(principal.role)
    if not kinds:
        return _empty(text_query, mode)

    stmt = select(SearchDocument).where(SearchDocument.kind.in_(kinds))
    clause = sql_clause(principal.scope)
    if clause is not None:
        stmt = stmt.where(clause)

    rank_of: dict[str, int] = {}
    if mode == q.MODE_FTS:
        try:
            rowids = _fts_candidates(db, q.fts_expression(text_query))
        except SQLAlchemyError:
            # 인덱스가 없거나(마이그레이션 직후) 질의가 FTS5 문법에 걸렸다. 조용히 0건을
            # 돌려주면 "검색이 안 된다"가 되고 아무도 이유를 모른다 — LIKE 로 내려가되
            # 로그에는 남긴다.
            logger.exception("FTS5 조회 실패 — LIKE 폴백으로 내려간다")
            mode = q.MODE_LIKE
            rowids = []
        if mode == q.MODE_FTS:
            if not rowids:
                return _empty(text_query, mode)
            rowid_col = literal_column("search_documents.rowid")
            stmt = stmt.where(rowid_col.in_(rowids)).add_columns(rowid_col.label("_rowid"))
            rank_of = {str(rid): i for i, rid in enumerate(rowids)}

    if mode == q.MODE_LIKE:
        stmt = stmt.where(q.like_clause(text_query)).order_by(
            SearchDocument.sort_key.desc(), SearchDocument.title
        ).limit(CANDIDATE_LIMIT)
        rows = list(db.execute(stmt).scalars().all())
    else:
        pairs = db.execute(stmt).all()
        # FTS 관련도 순서를 복원한다. IN (…) 은 순서를 보존하지 않는다.
        pairs.sort(key=lambda pair: rank_of.get(str(pair[1]), len(rank_of)))
        rows = [pair[0] for pair in pairs]

    visible = owner_gate(db, principal.scope)
    hits = [row for row in rows if row_visible(row, visible)]

    groups = []
    total = 0
    # `truncated` 는 "이 응답이 전부가 아니다"라는 정직한 신호다. 두 경우에 켠다:
    #   1) 어떤 그룹이 가진 것보다 적게 보여 줬다,
    #   2) 후보 상한(CANDIDATE_LIMIT)에 걸려 **아예 안 본 일치**가 있을 수 있다.
    # 2번을 빼면 화면이 "총 400건"을 마치 전부인 양 말하게 된다.
    truncated = len(rows) >= CANDIDATE_LIMIT
    for kind in kinds:
        items = [row for row in hits if row.kind == kind]
        if not items:
            continue
        shown = items[:per_kind]
        if len(items) > len(shown):
            truncated = True
        groups.append({
            "kind": kind,
            "label": KIND_LABELS.get(kind, kind),
            "total": len(items),
            "items": [_hit(row) for row in shown],
        })
        total += len(items)

    if total > total_limit:
        truncated = True
    return {
        "query": text_query,
        "mode": mode,
        "total": total,
        "truncated": truncated,
        "groups": groups,
    }
