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

from sqlalchemy import column, literal_column, select, table, text
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


# FTS5 인덱스를 원본 표에 붙이기 위한 얇은 이름들. `search_index` 는 가상 표라 ORM 모델이
# 없고, rowid 는 SQLAlchemy 가 자동으로 실어 주지 않는다.
_SEARCH_INDEX = table("search_index", column("rowid"), column("rank"))
_SD_ROWID = literal_column("search_documents.rowid")


def _fts_candidates(db: Session, expression: str, *, conditions) -> list[int]:
    """`search_index` 에서 관련도(rank) 순 rowid. 실패하면 빈 목록(호출측이 LIKE 로 내려간다).

    ⚠️ **조건을 LIMIT 보다 먼저 건다** (Z6). 예전에는 인덱스만 보고 전역 상위 400건을
    뽑은 뒤 그 400건 안에서 범위를 걸렀다 — 범위 밖이 400건을 채우면 내 범위 결과가
    한 건도 안 남는다. 그래서 원본 표를 rowid 로 조인해 **범위와 유형을 질의 안에서**
    거르고, 그 뒤에 상한을 건다.
    """
    stmt = (
        select(_SD_ROWID)
        .select_from(_SEARCH_INDEX)
        .join(SearchDocument, onclause=_SD_ROWID == _SEARCH_INDEX.c.rowid)
        .where(text("search_index MATCH :m").bindparams(m=expression))
    )
    for condition in conditions:
        if condition is not None:
            stmt = stmt.where(condition)
    stmt = stmt.order_by(_SEARCH_INDEX.c.rank).limit(CANDIDATE_LIMIT)
    return [int(r) for r in db.execute(stmt).scalars().all()]


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

    # 유형 게이트와 범위. **후보를 자르기 전에** 걸어야 하는 조건들이다 (Z6) —
    # 두 질의(FTS 후보 뽑기, LIKE 폴백)가 같은 목록을 쓴다.
    kind_clause = SearchDocument.kind.in_(kinds)
    clause = sql_clause(principal.scope)
    narrowing = (kind_clause, clause)

    stmt = select(SearchDocument).where(kind_clause)
    if clause is not None:
        stmt = stmt.where(clause)

    rank_of: dict[str, int] = {}
    if mode == q.MODE_FTS:
        try:
            rowids = _fts_candidates(
                db, q.fts_expression(text_query), conditions=narrowing
            )
        except SQLAlchemyError:
            # 인덱스가 없거나(마이그레이션 직후) 질의가 FTS5 문법에 걸렸다. 조용히 0건을
            # 돌려주면 "검색이 안 된다"가 되고 아무도 이유를 모른다 — LIKE 로 내려가되
            # 로그에는 남긴다.
            logger.exception("FTS5 조회 실패: LIKE 폴백으로 내려간다")
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

    # 최종 판정은 여전히 여기다. 위 SQL 절은 **상한 앞에서 좁히는 관문**이지 판정의
    # 대체가 아니다 — 판정을 SQL 로만 옮기면 소유자를 해석하는 규칙이 scope.py 밖으로
    # 새어 나가고, 그때 목록 화면과 검색이 서로 다른 규칙을 갖게 된다.
    visible = owner_gate(db, principal.scope)
    hits = [row for row in rows if row_visible(row, visible)]

    groups = []
    total = 0
    # `truncated` 는 "이 응답이 전부가 아니다"라는 정직한 신호다. 두 경우에 켠다:
    #   1) 어떤 그룹이 가진 것보다 적게 보여 줬다,
    #   2) 후보 상한(CANDIDATE_LIMIT)에 걸려 **아예 안 본 일치**가 있을 수 있다.
    # 2번을 빼면 화면이 "총 400건"을 마치 전부인 양 말하게 된다.
    #
    # 이제 후보를 뽑을 때 범위가 이미 걸려 있으므로 이 신호는 "**내 범위 안에** 더 있다"를
    # 뜻한다. 예전에는 전역 400건에 걸렸다는 뜻이라 범위 관리자에게는 늘 켜져 있었다 —
    # 볼 것이 한 건뿐인데도 "더 있는데 안 보여 준다"고 말하는 배지였다.
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
