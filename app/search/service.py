"""통합 검색 실행 — 인덱스 조회 + 범위 필터 + 유형별 묶음 (PLAN Phase 5).

응답은 **유형별 그룹**이다. 한 줄로 섞어 내보내면 화면이 유형을 다시 분류해야 하고, 그
분류 규칙이 백엔드와 어긋나는 순간 아무도 모르게 결과가 사라진다.

## 범위는 **후보를 자르기 전에** 건다 (Z6 / 0060 §25)

판정은 `app/search/scoping.py` 가 `app/core/ownership.py` 의 함수 하나로 한다 — 문서
목록이 쓰는 그 함수다. 여기서 2차 판정을 하지 않는다: 규칙이 두 곳에 살면 반드시 갈라지고,
갈라지는 방향 하나는 유출이다.

상한(`CANDIDATE_LIMIT`) **앞에서** 걸어야 하는 이유는 따로 있다. 범위 밖 행이 상한을 채우면
내 범위 결과가 한 건도 안 남는데, 화면에는 "결과 없음 + truncated 배지" 로만 보인다 —
오류가 아니라서 아무도 신고하지 않는다.
"""

from __future__ import annotations

from sqlalchemy import select
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
from app.search.scoping import not_restricted_clause, sql_clause

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


# 색인은 **원본 표 하나**다. FTS5 시절에는 `search_documents`(사실) + `search_index`
# (가상 표) 둘이었고 SQLite 트리거가 둘을 묶었다 — PG 에는 그 문법이 없고, 무엇보다
# **필요가 없다**: `gin_trgm_ops` 인덱스는 원본 컬럼에 그대로 걸리므로(models.py) 어떤
# 경로로 써도 인덱스가 같이 움직인다. 트리거로 지키던 성질을 인덱스가 공짜로 준다.


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

    # 유형 게이트와 범위. **후보를 자르기 전에** 걸어야 하는 조건들이다 (Z6).
    kind_clause = SearchDocument.kind.in_(kinds)
    clause = sql_clause(principal.visibility)
    # 열람 제한 문서(SEC-10)는 색인에 안 담기지만, 제한을 켠 직후 다음 색인까지의 창을
    # 여기서 닫는다(app/search/scoping.py::not_restricted_clause).
    restricted = not_restricted_clause()

    stmt = select(SearchDocument).where(kind_clause).where(restricted)
    if clause is not None:
        stmt = stmt.where(clause)

    # 본문 조건과 정렬. **두 모드가 같은 질의 하나**로 답한다 — 예전에는 FTS 가상 표에서
    # rowid 를 먼저 뽑아 원본 표에 `IN (…)` 으로 되먹이는 2단 질의였고, 그래서 순서를
    # 파이썬에서 복원해야 했다. `gin_trgm_ops` 는 원본 컬럼에 직접 걸리므로 그 왕복이 없다.
    #
    # ⚠️ **범위·유형 조건은 여전히 LIMIT 보다 먼저 걸린다** (Z6). 그 성질이 이 이식으로
    # 흔들리지 않는 것이 중요하다 — 범위 밖 행이 상한을 채우면 내 범위 결과가 한 건도 안
    # 남는데, 화면에는 오류가 아니라 "결과 없음"으로 보여 아무도 신고하지 않는다.
    stmt = stmt.where(q.clause_for(text_query, mode))
    if mode == q.MODE_TRGM:
        # 관련도 순. 동점이면 최신 것이 먼저다.
        stmt = stmt.order_by(
            q.rank_expression(text_query).desc(),
            SearchDocument.sort_key.desc(),
            SearchDocument.title,
        )
    else:
        # 1~2자 질의는 트라이그램 점수가 의미를 갖지 못한다(창을 만들 수 없다) — 최신 순으로 답한다.
        stmt = stmt.order_by(SearchDocument.sort_key.desc(), SearchDocument.title)
    rows = list(db.execute(stmt.limit(CANDIDATE_LIMIT)).scalars().all())

    # 파이썬 2차 판정은 없다 — 위 `sql_clause` 가 곧 판정이다(0060 §25). 예전에는 담당자
    # 집합이 문자열 안에 있어 SQL 로 정확히 쓸 수 없었고 그래서 두 벌이었다. Ownership 은
    # 컬럼이라 SQL 이 정확히 같은 답을 낸다.
    hits = rows

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
