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

from sqlalchemy.orm import Session

from app.core.scope import Scope, any_assignee_visible, scope_filter, visible_user_ids
from app.search.models import SearchDocument, split_owner_ids


def sql_clause(scope: Scope):
    """SQL 로 미리 좁힐 수 있는 부분. 없으면 ``None``(= 조건 없음).

    부서 범위는 여기서 좁히지 않는다 — 담당자 집합 판정이 파이썬에서 이어진다.
    `None` 을 그냥 돌려주는 것이 아니라 `scope_filter` 를 거치게 두는 이유는, org 분기의
    fail-closed 동작(org_id 가 비어 있으면 아무것도 안 보인다)을 여기서 다시 쓰지 않기
    위해서다.
    """
    if scope.is_org:
        return scope_filter(scope, org_column=SearchDocument.org_id)
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
