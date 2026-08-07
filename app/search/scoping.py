"""검색 결과에 범위를 건다 — `app/core/scope.py` 의 규칙을 **그대로** 쓴다.

여기서 새 권한 규칙을 만들지 않는다. 목록 화면과 검색이 서로 다른 규칙을 쓰면, 목록에서
가려 둔 것이 검색에서 새거나(유출) 반대로 검색만 텅 비어 아무도 원인을 모른다.

scope.py 의 세 갈래를 그대로 따라간다:

| 범위 | 판정 | 이 파일의 처리 |
|---|---|---|
| 전역(global) | 제한 없음 | `sql_clause` → None, `owner_gate` → None |
| 조직(org) | `org_id` 일치 | `scope_filter` 의 org 분기를 그대로 SQL 로 |
| 부서(dept) | **담당자 집합** 중 한 명이라도 범위 안 | `any_assignee_visible` 로 행마다 판정 |

## 부서 범위만 담당자 집합으로 보는 이유

부서를 스칼라 컬럼 하나로 두면 두 부서가 함께 맡은 티켓이 한쪽에서 통째로 사라진다
(scope.py 모듈 docstring 의 '미결 쟁점 종결'). 그래서 검색 행은 부서가 아니라
**소유자 집합**(`owner_user_ids`)을 들고 있고, 판정은 scope.py 가 이미 가진
`visible_user_ids` + `any_assignee_visible` 조합으로 한다 — 새 함수가 아니다.

반대로 조직·전역 범위에는 담당자 판정을 걸지 **않는다**. 걸면 담당자를 해석하지 못한 행
(작성자 이름이 앱 계정과 안 맞는 오래된 문서 등)이 전역 관리자에게도 안 보이게 된다.
그건 보안이 아니라 그냥 고장이다.
"""

from __future__ import annotations

from sqlalchemy import literal, select
from sqlalchemy.orm import Session

from app.core.scope import (
    Scope,
    any_assignee_visible,
    apply_user_scope,
    scope_filter,
    visible_user_ids,
)
from app.search.models import SearchDocument, split_owner_ids
from app.users.models import User


def sql_clause(scope: Scope):
    """SQL 로 미리 좁힐 수 있는 부분. 없으면 ``None``(= 조건 없음).

    `None` 을 그냥 돌려주는 것이 아니라 `scope_filter` 를 거치게 두는 이유는, org 분기의
    fail-closed 동작(org_id 가 비어 있으면 아무것도 안 보인다)을 여기서 다시 쓰지 않기
    위해서다.

    ## 왜 부서 범위까지 SQL 로 내려왔나 (Z6)

    예전에는 org 분기만 SQL 이었고 부서 범위는 파이썬 판정에만 맡겼다. 그런데 검색은
    후보를 `CANDIDATE_LIMIT` 만큼만 뽑는다. **거르기 전에 자르면** 범위 밖 문서가 상한을
    채운 순간 내 범위 결과가 한 건도 안 남는다. 부서 범위 관리자에게는 "결과가 거의 없다"
    로 보이고 truncated 배지만 뜬다. 오류가 아니라서 아무도 신고하지 않는다.

    그래서 상한보다 **먼저** 걸 수 있는 조건을 여기서 만든다. 규칙은 그대로
    `app/core/scope.py` 것이다:

      * 누가 보이는가 = `apply_user_scope` (부서 서브트리 판정이 거기 한 곳에 있다)
      * 그 사람이 이 문서의 소유자인가 = 소유자 집합에 그 id 가 있는가

    부서원 수만큼 LIKE 를 OR 로 잇지 않는다 — 상관 서브쿼리 하나로 `users` 를 그대로
    쓰므로 사람이 몇 명이든 질의 모양이 같다.

    ## ⚠️ 양끝을 **질의에서 다시 감싸는** 이유

    `join_owner_ids` 는 `,a,b,` 로 저장하지만 그 모양을 DB 가 강제하지는 않는다. 실제로
    콤마 없이 id 하나만 든 행이 있고(`tests/security/test_regular_user_scope.py` 가 그렇게
    심는다), 파이썬 판정(`split_owner_ids`)은 그것도 정상으로 읽는다. 저장 모양만 믿고
    `%,id,%` 를 찾으면 그런 행이 **상한 앞에서 조용히 사라진다** — 고치려던 결함과
    똑같은 모양의 새 결함이다.

    그래서 열 값을 `,` 로 한 번 더 감싼 뒤 찾는다. `a` 는 `,a,` 가 되고 `,a,b,` 는
    `,,a,b,,` 가 되는데 둘 다 `%,a,%` 에 걸린다 — `split_owner_ids` 와 정확히 같은 판정이다.

    ⚠️ 이 절은 **파이썬 판정을 대신하지 않는다.** `row_visible` 이 최종 판정이고 여기는
    상한 앞에서 좁히는 관문이다. 그래서 어느 쪽도 자기 규칙을 새로 만들지 않는다 —
    둘 다 scope.py 를 부른다.
    """
    if scope.is_org:
        return scope_filter(scope, org_column=SearchDocument.org_id)
    if scope.is_dept:
        # LIKE 패턴에 사용자 id 를 이어 붙인다. id 는 UUID 라 `%`/`_` 가 없다 —
        # 와일드카드로 해석될 글자가 애초에 들어올 수 없다.
        haystack = literal(",").concat(SearchDocument.owner_user_ids).concat(literal(","))
        pattern = literal("%,").concat(User.id).concat(literal(",%"))
        return (
            apply_user_scope(select(literal(1)), scope)
            .where(haystack.like(pattern))
            .exists()
        )
    return None


def owner_gate(db: Session, scope: Scope) -> frozenset[str] | None:
    """행 판정에 쓸 '보이는 사용자' 집합. ``None`` 이면 제한 없음.

    부서 범위에서만 계산한다. 부서 하나에 수십~수백 명이라 한 번 읽어 frozenset 으로
    들고 다니는 편이 행마다 조인하는 것보다 싸다(scope.py::visible_user_ids 와 같은 판단).
    """
    if not scope.is_dept:
        return None
    return visible_user_ids(db, scope)


def row_visible(row: SearchDocument, visible: frozenset[str] | None) -> bool:
    """행 하나가 이 범위에 보이는가 — scope.py 의 판정을 그대로 부른다.

    소유자를 하나도 해석하지 못한 행은 부서 범위에서 **안 보인다**(fail-closed).
    미할당 티켓이 부서 화면이 아니라 포탈 전용 버킷에 남는 것과 같은 규칙이다.
    """
    return any_assignee_visible(split_owner_ids(row.owner_user_ids), visible)
