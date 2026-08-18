"""요청 주체의 **범위** — 무엇을 볼 수 있고(Visibility) 무엇을 관리할 수 있는가(Management).

역할(role)과 범위(scope)는 직교한다.
  * **역할**은 *무엇을 할 수 있는가*를 말한다 — 사용자 목록을 열 수 있는가, 설정을 바꿀 수
    있는가. `app/core/authz.py` + `require_roles` 가 담당한다.
  * **범위**는 *누구에게 할 수 있는가*를 말한다. 이 파일이 담당한다.

## 범위는 **하나가 아니라 둘**이다

예전에는 `build_scope()` 하나가 세 가지 질문에 동시에 답했다 — "내 개인 업무는 무엇인가",
"내가 조회할 수 있는 조직 데이터는 어디까지인가", "내가 관리할 수 있는 대상은 누구인가".
한 값이 세 뜻을 겸하면 **"볼 수는 있는데 관리할 수는 없는" 상태를 표현할 방법이 없다.**
A-1 부서 관리자는 상위 A 부서의 프로젝트를 *볼* 수 있어야 하지만 그것을 *고칠* 수는 없어야
하는데, 값이 하나뿐이면 둘 중 하나를 포기해야 한다.

그래서 둘로 쪼갠다:

    visibility_scope(db, user)   일반 사용자로서 조회 가능한 공유 범위
    management_scope(db, user)   관리자 권한으로 관리 가능한 범위

`Principal` 이 둘 다 들고 다니고, 각 API 는 자기 성격에 맞는 쪽을 고른다.
개인 업무(Personal)는 범위가 아니라 `user_id` 로 판정하므로 여기 없다.

## 조회 범위는 줄기(branch)다 — 위아래 양쪽

부서 트리에서 일반 사용자의 조회 범위는 **조상 ∪ 자기 ∪ 후손**이다
(`app/core/org_tree.py::DeptTree.branch`).

    굿모닝아이텍
    ├ A
    │  ├ A-1     ← 이 사람은 GMI 공통·A·A-1 을 본다. A-2·B 는 못 본다.
    │  └ A-2
    └ B

형제 가지는 자동으로 공유하지 않는다. 반대로 **관리 범위는 자기 ∪ 후손**뿐이다 — 하위 팀
사람이 상위 부서 업무를 본다고 해서 상위 부서를 관리하게 되면 안 된다.

## 소속이 불분명하면 넓히지 않고 **닫는다**

`membership_kind` 는 "이 사람이 조직 어디에 붙어 있는가"를 명시한다:

  * `department`   — 특정 부서 소속. 그 부서의 branch 를 본다.
  * `organization` — 조직 직속. 그 조직 전체를 본다.
  * `unassigned`   — **아직 정해지지 않았다.** 조직 데이터를 아무것도 못 본다.

세 번째가 핵심이다. 예전에는 `department_id IS NULL` 을 전역(GLOBAL)으로 폴백했다 —
"부서를 아직 안 정한 신규 입사자가 빈 화면을 보면 안 된다"는 선의였지만, 결과는 **부서를
안 정한 모든 계정이 전 포털을 보는 것**이었다(실측 25명 중 21명). 부서 미지정과 조직 직속은
사람이 구분해 줘야 하는 서로 다른 사실이고, 둘을 코드가 추측하면 그 추측은 언제나 넓히는
쪽으로 틀린다. 그래서 추측하지 않고 닫고, 대신 관리자 진단 화면이 그 계정들을 목록으로
보여 주며 한 번에 지정할 수 있게 한다.

## 범위 밖 단건은 403 이 아니라 404 다

`403 Forbidden` 은 "그 id 는 존재하지만 너는 못 본다"를 알려 준다. 남의 부서 사용자 id 를
찍어 보며 403/404 를 세면 조직도를 통째로 열거할 수 있다 — 목록에서 가린 것이 단건에서
새는 전형적인 IDOR 유출이다. 그래서 **범위 밖 단건 조회는 존재하지 않는 것과 똑같이
404** 로 답한다(팀 채팅 이미지 서빙이 같은 이유로 이미 404 를 쓴다).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy import Select, false, select
from sqlalchemy.orm import Session

from app.core.org_tree import DeptTree
from app.users.models import (
    ADMIN_SCOPE_DEPT,
    ADMIN_SCOPE_GLOBAL,
    ADMIN_SCOPE_ORG,
    MEMBERSHIP_ORGANIZATION,
    ROLE_ADMIN,
    ROLE_AUDITOR,
    ROLE_OPERATOR,
    ROLE_SYSTEM_ADMIN,
    User,
)

logger = logging.getLogger("app.scope")

# 범위 종류. 앞의 셋은 `admin_scope` 컬럼 어휘와 같은 문자열을 쓴다(관리 범위를 그대로
# 담을 수 있어야 한다). `none` 은 컬럼에 없는 계산 결과 전용 값이다 — "아직 정해지지 않아
# 아무것도 안 보인다".
SCOPE_GLOBAL = ADMIN_SCOPE_GLOBAL
SCOPE_ORG = ADMIN_SCOPE_ORG
SCOPE_DEPT = ADMIN_SCOPE_DEPT
SCOPE_NONE = "none"

# 넓은 것부터. `_widest` 가 두 범위를 합칠 때 쓴다.
_RANK = {SCOPE_NONE: 0, SCOPE_DEPT: 1, SCOPE_ORG: 2, SCOPE_GLOBAL: 3}


@dataclass(frozen=True)
class Scope:
    """이 주체가 볼(또는 관리할) 수 있는 범위. **불변**이다 — 요청 처리 중에 넓히지 않는다."""

    kind: str = SCOPE_GLOBAL
    org_id: str | None = None
    # 부서 범위일 때의 부서 id 집합. 그 밖의 kind 에서는 비어 있다.
    dept_ids: frozenset[str] = field(default_factory=frozenset)

    @property
    def is_global(self) -> bool:
        return self.kind == SCOPE_GLOBAL

    @property
    def is_org(self) -> bool:
        return self.kind == SCOPE_ORG

    @property
    def is_dept(self) -> bool:
        return self.kind == SCOPE_DEPT

    @property
    def is_none(self) -> bool:
        return self.kind == SCOPE_NONE

    @property
    def allows_anything(self) -> bool:
        """이 범위로 무엇이든 볼 수 있는가. 빈 부서 집합은 아무것도 못 본다."""
        if self.is_none:
            return False
        if self.is_dept:
            return bool(self.dept_ids)
        if self.is_org:
            return bool(self.org_id)
        return True


GLOBAL_SCOPE = Scope(kind=SCOPE_GLOBAL)
NONE_SCOPE = Scope(kind=SCOPE_NONE)


def _widest(a: Scope, b: Scope) -> Scope:
    """두 범위 중 넓은 쪽. 같은 종류면 합친다.

    관리자에게 쓴다 — 관리 범위를 배정받았다는 것은 그 범위를 **볼 수 있다**는 뜻이기도
    하다. 소속(membership)에서 나온 조회 범위와 관리 범위를 합쳐 최종 조회 범위를 만든다.
    """
    if _RANK[a.kind] != _RANK[b.kind]:
        return a if _RANK[a.kind] > _RANK[b.kind] else b
    if a.is_dept:
        return Scope(
            kind=SCOPE_DEPT,
            org_id=a.org_id or b.org_id,
            dept_ids=a.dept_ids | b.dept_ids,
        )
    if a.is_org and a.org_id != b.org_id:
        # 서로 다른 조직 둘을 합칠 수 있는 표현이 없다. 소속 조직을 남긴다 —
        # 관리 대상 조직은 아래 management_scope 가 따로 들고 있다.
        return a
    return a


@dataclass(frozen=True)
class Principal:
    """요청을 낸 사람 + 그 사람의 두 범위. 라우터가 들고 다니는 값 하나."""

    user_id: str
    role: str
    org_id: str | None
    department_id: str | None
    membership_kind: str
    # 조회 범위 — 일반 사용자로서 볼 수 있는 공유 데이터.
    visibility: Scope
    # 관리 범위 — 관리자 권한으로 고칠 수 있는 대상. 일반 사용자는 SCOPE_NONE.
    management: Scope
    # 이 요청이 쓰는 부서 트리. 경로 표시·범위 재계산이 다시 질의하지 않게 함께 싣는다.
    tree: DeptTree

    @property
    def is_global(self) -> bool:
        """조회가 무제한인가. **관리 무제한과 다르다** — `manages_everything` 을 볼 것."""
        return self.visibility.is_global

    @property
    def manages_everything(self) -> bool:
        return self.management.is_global

    @property
    def can_manage_anything(self) -> bool:
        return self.management.allows_anything


# ── 범위 계산 ────────────────────────────────────────────────────────────────

def _membership_scope(user: User, tree: DeptTree) -> Scope:
    """소속에서 나오는 조회 범위. 역할을 보지 않는다 — 여기는 '이 사람이 어디 사람인가'다.

    ## `department_id` 가 먼저, `membership_kind` 는 그 다음이다

    부서가 배정돼 있으면 그 사람은 그 부서 사람이다 — 물을 것이 없다. 두 컬럼이 서로
    다른 말을 할 수 있는 상태(부서는 있는데 kind 는 unassigned)를 판정에서 아예 없앤다.

    `membership_kind` 는 **부서가 없을 때만** 답할 것이 있다. `department_id IS NULL` 하나로는
    "본부 직속이라 팀이 없다" 와 "아직 안 정했다" 를 구별할 수 없고, 예전 코드는 그 둘을
    똑같이 전역(GLOBAL)으로 폴백해서 부서를 안 정한 계정이 전 포털을 봤다.
    """
    dept_id = getattr(user, "department_id", None)
    org_id = getattr(user, "org_id", None)
    if dept_id:
        branch = tree.branch(dept_id)
        if not branch:
            # 부서가 지워졌거나 트리에 없다 — 판정할 근거가 없고, 근거가 없으면 닫는다.
            return NONE_SCOPE
        return Scope(kind=SCOPE_DEPT, org_id=tree.org_of(dept_id) or org_id, dept_ids=branch)
    if getattr(user, "membership_kind", None) == MEMBERSHIP_ORGANIZATION:
        return Scope(kind=SCOPE_ORG, org_id=org_id) if org_id else NONE_SCOPE
    # unassigned(또는 알 수 없는 값) — 추측하지 않는다.
    return NONE_SCOPE


def management_scope(db: Session, user: User, tree: DeptTree | None = None) -> Scope:
    """관리자 권한으로 **고칠 수 있는** 대상 범위. 일반 사용자는 `SCOPE_NONE`.

    부서 관리 범위는 **자기 ∪ 후손**이다(조상은 포함하지 않는다) — 하위 팀 관리자가 상위
    부서까지 관리하게 되면 그건 승격이지 위임이 아니다.
    """
    tree = tree if tree is not None else DeptTree.load(db)
    role = getattr(user, "role", None)
    if role not in (ROLE_OPERATOR, ROLE_AUDITOR, ROLE_ADMIN, ROLE_SYSTEM_ADMIN):
        return NONE_SCOPE

    kind = getattr(user, "admin_scope", ADMIN_SCOPE_GLOBAL) or ADMIN_SCOPE_GLOBAL

    # 운영자·감사자는 관리 콘솔 사용자이지 조직 관리자가 아니다 — `admin_scope` 의 기본값
    # (`global`, 0024 마이그레이션의 의도된 선택)을 그대로 전역 권한으로 읽으면, 그 컬럼을
    # 한 번도 명시적으로 좁힌 적 없는 운영자가 그 사실만으로 전사 범위가 된다(RBAC 재감사
    # 2026-08-16 실측). 명시적으로 좁힌 값은 그대로 존중하고, "아직 global" 인 경우만 조직으로
    # 닫는다 — 애매하면 좁게 실패한다는 이 파일의 원칙 그대로다.
    if kind == ADMIN_SCOPE_GLOBAL and role in (ROLE_OPERATOR, ROLE_AUDITOR):
        org_id = getattr(user, "org_id", None)
        return Scope(kind=SCOPE_ORG, org_id=org_id) if org_id else NONE_SCOPE

    if kind == ADMIN_SCOPE_GLOBAL:
        return GLOBAL_SCOPE
    if kind == ADMIN_SCOPE_ORG:
        org_id = user.scope_org_id or user.org_id
        return Scope(kind=SCOPE_ORG, org_id=org_id) if org_id else NONE_SCOPE
    if kind == ADMIN_SCOPE_DEPT:
        root = user.scope_dept_id or user.department_id
        managed = tree.descendants(root)
        if not managed:
            return NONE_SCOPE
        return Scope(
            kind=SCOPE_DEPT,
            org_id=tree.org_of(root) or user.scope_org_id or user.org_id,
            dept_ids=managed,
        )
    logger.error(
        "알 수 없는 admin_scope=%r (user=%s). 안전을 위해 아무것도 관리할 수 없는 범위로 처리한다",
        kind, user.id,
    )
    return NONE_SCOPE


def visibility_scope(db: Session, user: User, tree: DeptTree | None = None) -> Scope:
    """일반 사용자로서 **조회할 수 있는** 공유 범위.

    소속에서 나온 범위와 관리 범위 중 **넓은 쪽**이다. 관리 범위를 배정받았다는 것은 그
    대상을 볼 수 있다는 뜻이기도 하기 때문이다(관리하는데 안 보이면 관리할 수 없다).
    """
    tree = tree if tree is not None else DeptTree.load(db)
    return _widest(_membership_scope(user, tree), management_scope(db, user, tree))


def principal_from_user(db: Session, user: User, tree: DeptTree | None = None) -> Principal:
    tree = tree if tree is not None else DeptTree.load(db)
    return Principal(
        user_id=user.id,
        role=user.role,
        org_id=getattr(user, "org_id", None),
        department_id=user.department_id,
        membership_kind=getattr(user, "membership_kind", None) or "",
        visibility=visibility_scope(db, user, tree),
        management=management_scope(db, user, tree),
        tree=tree,
    )


# ── SQL 조립 ─────────────────────────────────────────────────────────────────

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
    if scope.is_none:
        return MATCH_NOTHING
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
    if scope.is_none:
        return False
    if scope.is_org:
        return bool(scope.org_id) and getattr(user, "org_id", None) == scope.org_id
    return bool(scope.dept_ids) and user.department_id in scope.dept_ids


def visible_user_ids(db: Session, scope: Scope) -> frozenset[str] | None:
    """범위 안 사용자 id 집합. 전역이면 ``None``(= 제한 없음).

    사용자 자체를 대상으로 삼는 관리 화면(사용자 관리·대리 보기·쿼터·승인 등)이 쓴다.
    사용자 수가 1000명 규모라 집합을 통째로 들고 오는 편이 조인보다 단순하고 빠르다.
    """
    if scope.is_global:
        return None
    if scope.is_none:
        return frozenset()
    rows = db.execute(apply_user_scope(select(User.id), scope)).scalars().all()
    return frozenset(rows)


def any_assignee_visible(
    assignee_user_ids: Iterable[str | None], visible: frozenset[str] | None
) -> bool:
    """다중 담당자 자원의 가시성 판정 — **담당자 중 한 명이라도** 범위 안이면 보인다.

    스칼라 하나로 정하면 두 부서가 함께 맡은 자원이 한쪽에서 사라진다.

    ⚠️ 티켓은 더 이상 이 판정을 쓰지 않는다. 티켓의 소속은 담당자가 아니라 **프로젝트**다
    (`app/core/ownership.py`). 이 함수는 담당자/작성자 축이 실제 소유 축인 자원에만 남는다.
    """
    if visible is None:
        return True
    return any(uid in visible for uid in assignee_user_ids if uid)
