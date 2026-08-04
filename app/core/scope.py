"""요청 주체의 **범위** — 무엇을 볼 수 있는가 (§7.1.A, PLAN Phase 4).

역할(role)과 범위(scope)는 직교한다.
  * **역할**은 *무엇을 할 수 있는가*를 말한다 — 사용자 목록을 열 수 있는가, 설정을 바꿀 수
    있는가. `app/core/authz.py` + `require_roles` 가 담당한다.
  * **범위**는 *누구에게 할 수 있는가*를 말한다 — 전사인가, 한 조직인가, 내 부서 트리인가.
    이 파일이 담당한다.
둘을 한 축으로 뭉개면 '부서 관리자'를 표현할 수 없다. 부서 관리자는 role 로는 admin 이지만
자기 부서 밖은 아예 보이면 안 되기 때문이다.

## 범위 밖 단건은 403 이 아니라 404 다

`403 Forbidden` 은 "그 id 는 존재하지만 너는 못 본다"를 알려 준다. 남의 부서 사용자 id 를
찍어 보며 403/404 를 세면 조직도를 통째로 열거할 수 있다 — 목록에서 가린 것이 단건에서
새는 전형적인 IDOR 유출이다. 그래서 **범위 밖 단건 조회는 존재하지 않는 것과 똑같이
404** 로 답한다(팀 채팅 이미지 서빙이 같은 이유로 이미 404 를 쓴다).

## 다중 담당자 티켓은 담당자 전원의 부서에 보인다 (미결 쟁점 종결)

티켓에 스칼라 `scope_dept_id` 하나만 두고 "대표 담당자의 부서"로 정하면, 두 부서가 함께
맡은 티켓이 **한쪽 부서에서 통째로 사라진다**(그 부서 관리자는 자기 팀이 그 일을 하고
있다는 사실 자체를 못 본다). 그래서 판정은 담당자 **집합**으로 한다: 담당자 중 한 명이라도
그 범위 안이면 보인다. 담당자가 아무도 없는(또는 앱 사용자로 해석되지 않는) 티켓은 어느
부서에도 속하지 않으므로 **포탈 전용 버킷**(미할당 트리아지)에 남고 부서 범위에는 안 나온다.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy import Select, false, select
from sqlalchemy.orm import Session

from app.users.models import (
    ADMIN_SCOPE_DEPT,
    ADMIN_SCOPE_GLOBAL,
    ADMIN_SCOPE_ORG,
    User,
)

# 부서 트리를 전개할 때의 안전 상한. parent_id 에 사이클이 생기면(A→B→A) 순진한 BFS 는
# 영원히 돈다. visited 집합으로 이미 막지만, 깊이 상한도 함께 둬서 데이터가 이상해도
# 요청 하나가 프로세스를 잡아먹지 않게 한다.
MAX_DEPARTMENT_DEPTH = 32

logger = logging.getLogger("app.scope")


@dataclass(frozen=True)
class Scope:
    """이 주체가 볼 수 있는 범위. **불변**이다 — 요청 처리 중에 넓히지 않는다."""

    kind: str = ADMIN_SCOPE_GLOBAL
    org_id: str | None = None
    # 부서 범위일 때, 루트 부서와 그 하위 전부. 그 밖의 kind 에서는 비어 있다.
    dept_ids: frozenset[str] = field(default_factory=frozenset)

    @property
    def is_global(self) -> bool:
        return self.kind == ADMIN_SCOPE_GLOBAL

    @property
    def is_org(self) -> bool:
        return self.kind == ADMIN_SCOPE_ORG

    @property
    def is_dept(self) -> bool:
        return self.kind == ADMIN_SCOPE_DEPT


GLOBAL_SCOPE = Scope(kind=ADMIN_SCOPE_GLOBAL)


@dataclass(frozen=True)
class Principal:
    """요청을 낸 사람 + 그 사람의 범위. 라우터가 들고 다니는 값 하나."""

    user_id: str
    role: str
    org_id: str | None
    department_id: str | None
    scope: Scope

    @property
    def is_global(self) -> bool:
        return self.scope.is_global


def department_subtree_ids(db: Session, root_id: str | None) -> frozenset[str]:
    """``root_id`` 와 그 아래 모든 하위 부서 id.

    부서 트리는 parent_id 자기참조 하나로만 표현한다(closure 테이블 없음, 이유는
    `app/org/models.py::Department` docstring). 전개는 여기 한 곳에서만 하고,
    사이클이 있어도 멈춘다.
    """
    if not root_id:
        return frozenset()

    from app.org.models import Department

    seen: set[str] = {root_id}
    frontier: list[str] = [root_id]
    for _ in range(MAX_DEPARTMENT_DEPTH):
        if not frontier:
            break
        rows = db.execute(
            select(Department.id).where(Department.parent_id.in_(frontier))
        ).scalars().all()
        frontier = [dept_id for dept_id in rows if dept_id not in seen]
        seen.update(frontier)
    return frozenset(seen)


def build_scope(db: Session, user: User) -> Scope:
    """사용자 행에서 범위를 계산한다.

    설정이 불완전하면 **넓히는 쪽이 아니라 좁히는 쪽으로 실패한다**(fail-closed):
      * `admin_scope='dept'` 인데 부서가 비어 있음 → 빈 부서 집합 → 아무 행도 안 보인다
      * `admin_scope` 가 알 수 없는 값(오타 등) → 전역이 아니라 **아무것도 못 보는** 범위

    두 번째가 특히 중요하다. 모르는 값을 global 로 흘려보내면 오타 한 글자가 조용한 권한
    확대가 된다 — 그리고 그런 확대는 아무도 신고하지 않는다(화면이 잘 보이니까).
    반대로 좁게 실패하면 화면이 비고, 그건 30분 안에 신고가 들어온다.
    """
    kind = getattr(user, "admin_scope", ADMIN_SCOPE_GLOBAL) or ADMIN_SCOPE_GLOBAL
    if kind == ADMIN_SCOPE_GLOBAL:
        return GLOBAL_SCOPE
    if kind == ADMIN_SCOPE_ORG:
        return Scope(kind=ADMIN_SCOPE_ORG, org_id=user.scope_org_id or user.org_id)
    if kind == ADMIN_SCOPE_DEPT:
        root = user.scope_dept_id or user.department_id
        return Scope(
            kind=ADMIN_SCOPE_DEPT,
            org_id=user.scope_org_id or user.org_id,
            dept_ids=department_subtree_ids(db, root),
        )
    logger.error(
        "알 수 없는 admin_scope=%r (user=%s). 안전을 위해 아무것도 보이지 않는 범위로 처리한다",
        kind, user.id,
    )
    return Scope(kind=ADMIN_SCOPE_DEPT, org_id=None, dept_ids=frozenset())


def principal_from_user(db: Session, user: User) -> Principal:
    return Principal(
        user_id=user.id,
        role=user.role,
        org_id=getattr(user, "org_id", None),
        department_id=user.department_id,
        scope=build_scope(db, user),
    )


# 범위가 설정됐는데 걸 컬럼이 없거나 범위가 비어 있으면 **닫는다**(fail-closed).
# `sa.false()` 는 SQLite 에서 `0 = 1` 로 컴파일된다 — 조건을 빼먹은 것과 눈으로 구별된다.
MATCH_NOTHING = false()


def scope_filter(scope: Scope, *, org_column=None, dept_column=None):
    """범위를 SQLAlchemy 불리언 절로. 전역이면 ``None``(= 조건 없음).

    ``None`` 을 돌려주는 것이 이 API 의 핵심이다. "전역 = 항상 참" 을 `sa.true()` 로 돌려주면
    부르는 쪽이 그걸 그대로 WHERE 에 붙이게 되고, 조건을 빼먹은 코드와 조건이 항상 참인
    코드가 눈으로 구별되지 않는다. None 이면 부르는 쪽이 `if clause is not None:` 을 쓸
    수밖에 없어 '스코프를 고려했다'가 코드에 남는다.
    """
    if scope.is_global:
        return None
    if scope.is_org:
        if org_column is None or not scope.org_id:
            return MATCH_NOTHING
        return org_column == scope.org_id
    # 부서 범위
    if dept_column is None or not scope.dept_ids:
        return MATCH_NOTHING
    return dept_column.in_(tuple(sorted(scope.dept_ids)))


def apply_user_scope(stmt: Select, scope: Scope) -> Select:
    """``select(User)`` 에 범위를 건다.

    부서 범위에서 `department_id IS NULL` 인 사용자(부서 미배정)는 **보이지 않는다** —
    부서 관리자의 화면이지 전사 화면이 아니다. 전사 미배정 인원은 전역 관리자가 본다.
    """
    clause = scope_filter(scope, org_column=User.org_id, dept_column=User.department_id)
    return stmt if clause is None else stmt.where(clause)


def scope_allows_user(scope: Scope, user: User) -> bool:
    """단건 판정. 목록 필터와 **같은 규칙**이어야 한다 — 두 곳이 갈라지면 목록에 없는데
    단건은 열리는(또는 그 반대) 상태가 된다."""
    if scope.is_global:
        return True
    if scope.is_org:
        return bool(scope.org_id) and getattr(user, "org_id", None) == scope.org_id
    return bool(scope.dept_ids) and user.department_id in scope.dept_ids


def visible_user_ids(db: Session, scope: Scope) -> frozenset[str] | None:
    """범위 안 사용자 id 집합. 전역이면 ``None``(= 제한 없음).

    티켓처럼 '앱 사용자'를 거쳐 스코프가 정해지는 자원에 쓴다. 사용자 수가 1000명 규모라
    집합을 통째로 들고 오는 편이 조인보다 단순하고 빠르다.
    """
    if scope.is_global:
        return None
    rows = db.execute(apply_user_scope(select(User.id), scope)).scalars().all()
    return frozenset(rows)


def any_assignee_visible(
    assignee_user_ids: Iterable[str | None], visible: frozenset[str] | None
) -> bool:
    """다중 담당자 티켓의 가시성 판정 — **담당자 중 한 명이라도** 범위 안이면 보인다.

    스칼라 하나로 정하면 두 부서가 함께 맡은 티켓이 한쪽에서 사라진다(모듈 docstring).
    담당자가 없으면 어느 부서에도 속하지 않으므로 False — 미할당 티켓은 부서 화면이 아니라
    포탈 전용 버킷에서 다룬다.
    """
    if visible is None:
        return True
    return any(uid in visible for uid in assignee_user_ids if uid)
