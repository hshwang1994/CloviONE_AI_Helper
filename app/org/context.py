"""**지금 어느 부서를 보고 있는가** — 화면이 부서를 고를 때 쓰는 단 하나의 자리 (0060 §18/§32).

## 왜 공용 모듈인가

부서를 고르는 화면이 넷이다: 스프린트(화면 Context), 프로젝트 목록·문서 목록·팀 티켓
목록(필터). 넷이 각자 "고를 수 있는 부서" 를 계산하면 그중 하나는 반드시 범위를 넓게
잡는다 — 그리고 그 화면은 정상으로 보인다(목록이 더 많이 나올 뿐 오류가 없다).

그래서 두 가지를 여기 한 곳에 둔다:

  * `department_options` — 이 사람이 **고를 수 있는** 부서 목록(경로 포함).
  * `department_context` — 고른 값을 **서버가 검증**하고, 그 선택이 만드는 좁은 Scope 까지
    함께 돌려준다.

프런트 선택기만으로 막지 않는다. 범위 밖 id 를 직접 넣으면 **없는 부서와 똑같이 404** 다
(403 은 그 부서가 존재한다는 사실을 알려 준다).

## 필터와 Context 는 좁히는 방향이 다르다

  * **Context**(스프린트) — 고른 부서 **와 그 아래**. 상위는 뺀다: "A-1 스프린트" 를 보면서
    상위 A 공통 업무까지 섞이면 그건 A 스프린트다.
  * **필터**(목록) — 같은 규칙을 쓴다. 목록에서 "A-1" 을 고른 사람은 A-1 팀의 일을 보려는
    것이지 A 본부 공통 업무를 보려는 것이 아니다.

두 쓰임이 같은 규칙이라 함수도 하나다. 갈라져야 할 이유가 생기면 그때 나눈다.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.org_tree import DeptTree


def _allowed(scope, tree: DeptTree) -> frozenset[str]:
    """이 조회 범위에서 고를 수 있는 부서 id 집합."""
    if scope.is_dept:
        return scope.dept_ids
    if scope.is_org:
        return tree.in_org(scope.org_id)
    if scope.is_global:
        return tree.all_ids()
    return frozenset()


def department_options(db: Session, viewer) -> list[dict]:
    """고를 수 있는 부서 — `{id, name, path[]}` 목록. 경로 이름 순.

    `path` 를 함께 싣는 이유: 이름 하나('개발팀')로는 어느 줄기인지 알 수 없고, 조직 개편으로
    같은 이름이 다른 자리에 생기면 구분이 아예 불가능해진다.
    """
    return department_context(db, viewer)["options"]


def department_context(db: Session, viewer, department_id: str | None = None) -> dict:
    """`{selected, options, scope}`.

    `scope` 는 선택을 반영한 **좁힌 조회 범위**다 — 고른 것이 없으면 원래 범위 그대로다.
    부서를 고를 수 없는 사람(조직 직속·전역)은 `selected=None` 이고, 그때는 자기 조회 범위
    전체가 대상이다.
    """
    from app.core.scope import Scope, visibility_scope

    if viewer is None:
        return {"selected": None, "options": [], "scope": None}

    tree = DeptTree.load(db)
    scope = visibility_scope(db, viewer)
    allowed = _allowed(scope, tree)

    options = sorted(
        (
            {
                "id": dept_id,
                "name": (node.name if (node := tree.get(dept_id)) else dept_id),
                "path": [{"id": n.id, "name": n.name} for n in tree.path(dept_id)],
            }
            for dept_id in allowed
        ),
        key=lambda o: [p["name"] for p in o["path"]],
    )

    if department_id and department_id not in allowed:
        raise NotFoundError("부서를 찾을 수 없습니다.")
    selected = department_id or getattr(viewer, "department_id", None)
    if selected and selected not in allowed:
        selected = None

    if selected:
        # ⚠️ `org_id` 를 **일부러 비운다.** 조회 범위에서는 조직 공통(= `dept_id` 가 없는)
        # 자원이 부서 사용자에게도 보이지만(`ownership.project_scope_clause`), **부서를
        # 골랐다는 것은 그 부서의 것을 보겠다는 뜻**이다. 조직 공통까지 남기면 어느 부서를
        # 골라도 그것들이 따라와서, 부서를 고르는 행위 자체가 아무것도 좁히지 못한다.
        #
        # 특히 지금 상태에서 그렇다: 외부에서 동기화된 프로젝트는 `dept_id` 가 NULL 로
        # 들어오므로(사람이 나중에 지정한다) 조직 공통이 다수다. 그 상태에서 필터가
        # 조직 공통을 포함하면 "부서 필터를 걸었는데 목록이 그대로" 가 된다.
        #
        # 좁히기만 하고 넓히지는 않는다 — `dept_ids` 는 조회 범위 안에서 검증한 부서의
        # 후손 집합이다(위 `allowed` 검사).
        effective = Scope(
            kind=scope.kind if scope.is_dept else "dept",
            org_id=None,
            dept_ids=tree.descendants(selected),
        )
    else:
        effective = scope
    return {"selected": selected, "options": options, "scope": effective}


def filter_scope(db: Session, viewer, department_id: str | None):
    """목록 필터용 — 고른 부서로 좁힌 Scope 하나만.

    `department_id` 가 없으면 `None` 을 돌려준다. 목록 코드가 `scope=None` 을 "이 사람의
    기본 조회 범위" 로 읽기 때문이다(`app/tickets/service.py::_project_visibility`) —
    여기서 기본 범위를 다시 계산해 넘기면 그 규약이 두 곳에 생긴다.

    ⚠️ **선택 없음이 곧 자기 부서가 아니다.** `department_context` 는 화면 Context 용이라
    선택이 없으면 본인 부서로 떨어지는데, 목록 필터에서 그러면 "필터를 안 걸었는데 내 팀
    것만 나온다" 가 된다 — 상위 부서 사람이 하위 팀 항목을 못 보게 되는, 조용한 기능 손실이다.
    """
    if not department_id:
        return None
    return department_context(db, viewer, department_id)["scope"]


# ── 회차의 팀 (D-482) ──────────────────────────────────────────────────────────
#
# 회차(`sprints.department_id`)는 **팀이 운영하는 주기**라 조회 규칙이 프로젝트와 다르다.
# 프로젝트는 줄기(조상 ∪ 자기 ∪ 후손)로 보이지만, 회차는 **자기 팀과 그 아래**만 본다 —
# 상위 본부의 회차는 하위 팀 사람의 주기가 아니고, 형제 팀의 회차도 아니다. 상위 권한자
# (관리 범위)와 조직 직속 사람만 아래 팀들의 회차를 함께 본다.
#
# 조회(무엇을 볼 수 있나)와 편성(무엇을 고칠 수 있나)은 다른 질문이다. 조회는 소속 ∪ 관리
# 범위이고, 편성은 **관리 범위만**이다 — A 본부 사람이 A-1 회차를 본다고 그 회차를 열고
# 닫을 수 있으면 안 된다.


def sprint_team_ids(principal) -> frozenset[str] | None:
    """이 사람이 **회차를 볼 수 있는** 팀 id 집합. `None` 은 전부(전역)다."""
    if principal is None:
        return frozenset()
    tree = principal.tree
    if principal.management.is_global:
        return None
    teams: set[str] = set()
    if principal.department_id:
        teams |= tree.descendants(principal.department_id)
    elif principal.visibility.is_org and principal.visibility.org_id:
        # 조직 직속 — 조직의 모든 팀 회차를 본다.
        teams |= tree.in_org(principal.visibility.org_id)
    managed = manageable_team_ids(principal)
    if managed is None:
        return None
    teams |= managed
    return frozenset(teams)


def manageable_team_ids(principal) -> frozenset[str] | None:
    """이 사람이 **회차를 편성할 수 있는** 팀 id 집합. `None` 은 전부(전역)다.

    관리 범위 그대로다 — 부서 범위는 자기 ∪ 후손, 조직 범위는 조직의 모든 팀. 일반
    사용자는 빈 집합이다(회차 편성 권한 `PROJECT_WRITE` 는 역할 게이트가 따로 본다).
    """
    if principal is None:
        return frozenset()
    scope = principal.management
    if scope.is_global:
        return None
    if scope.is_org and scope.org_id:
        return principal.tree.in_org(scope.org_id)
    if scope.is_dept:
        return frozenset(scope.dept_ids)
    return frozenset()


def can_manage_unassigned_sprints(principal, org_id: str | None) -> bool:
    """팀 미정(레거시) 회차는 조직·전역 관리자만 만진다 — 팀을 정해 주는 사람이다."""
    if principal is None:
        return False
    scope = principal.management
    if scope.is_global:
        return True
    return bool(scope.is_org and scope.org_id and org_id and scope.org_id == org_id)


def team_context(db: Session, viewer, department_id: str | None = None) -> dict:
    """작업 보드·스프린트 회의가 고른 **팀** — `{selected, options, manageable, principal}`.

    `options` 는 회차를 볼 수 있는 팀 전부(경로 포함)이고, 각 항목의 `manageable` 이
    「이 팀의 회차를 편성할 수 있는가」다. 범위 밖 id 는 **없는 팀과 똑같이 404** 다.

    기본 선택은 본인 부서(후보에 있을 때), 아니면 후보가 하나뿐일 때 그것, 아니면 없음 —
    없음이면 화면이 고르라고 말한다. 조직 직속 사람의 「없음」을 조직 전체로 넓혀 읽지
    않는다: 회차는 팀의 주기라 「전체」라는 회차 목록은 없다.
    """
    from app.core.scope import principal_from_user

    if viewer is None:
        return {"selected": None, "options": [], "manageable": False, "principal": None}

    tree = DeptTree.load(db)
    principal = principal_from_user(db, viewer, tree)
    visible = sprint_team_ids(principal)
    managed = manageable_team_ids(principal)
    allowed = tree.all_ids() if visible is None else visible

    def _manageable(dept_id: str) -> bool:
        return managed is None or dept_id in managed

    options = sorted(
        (
            {
                "id": dept_id,
                "name": (node.name if (node := tree.get(dept_id)) else dept_id),
                "path": [{"id": n.id, "name": n.name} for n in tree.path(dept_id)],
                "manageable": _manageable(dept_id),
            }
            for dept_id in allowed
        ),
        key=lambda o: [p["name"] for p in o["path"]],
    )

    if department_id and department_id not in allowed:
        raise NotFoundError("팀을 찾을 수 없습니다.")
    selected = department_id or None
    if not selected:
        own = getattr(viewer, "department_id", None)
        if own and own in allowed:
            selected = own
        elif len(options) == 1:
            selected = options[0]["id"]
    return {
        "selected": selected,
        "options": options,
        "manageable": bool(selected) and _manageable(selected),
        "principal": principal,
    }
