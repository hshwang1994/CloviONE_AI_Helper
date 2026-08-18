"""UA-13: 부서 부모가 같은 조직인지 확인하지 않던 문제 — 조직 경계를 넘는 트리.

`department_subtree_ids`(app/core/scope.py)는 `parent_id` 자기참조만 따라가는 순수
그래프 순회다 - org 필터가 없다. 그런데 부모 지정 검증(`org/service.py::create_item`,
`org/tree.py::validate_parent`)은 `scope_allows_item`만 봤다 - 전역 관리자에게는
**모든 행이 "범위 안"**이라 이 검사는 전역 관리자가 다른 조직의 부서를 부모로 지정하는
것을 전혀 못 막았다.

실제 피해: org A의 부서를 org B 부서의 부모로 지정하면, org A를 관리하는 dept-scope
관리자의 `department_subtree_ids(root=자기 부서)`가 그 순회를 따라 **org B 부서까지
자기 서브트리에 끌어들인다** - 그 부서에 속한 org B 사용자·티켓 등 전부가 조용히
org A 관리자의 관리 범위로 새어 들어온다(테넌트 격리 붕괴).
"""

from __future__ import annotations

import pytest

from app.core.errors import ValidationAppError
from app.core.scope import ADMIN_SCOPE_ORG, GLOBAL_SCOPE, Scope
from app.org.models import Department
from app.org.service import create_item, update_item

pytestmark = pytest.mark.security


def _org_scope(org_id: str) -> Scope:
    return Scope(kind=ADMIN_SCOPE_ORG, org_id=org_id)


def test_creating_a_department_with_a_parent_from_another_org_is_rejected(db, two_orgs):
    parent_in_a = create_item(db, Department, name="본부", scope=_org_scope(two_orgs.org_a_id))
    db.commit()

    # 전역 관리자가 org B에 부서를 만들면서 org A의 부서를 부모로 지정한다 — 예전엔
    # scope_allows_item(전역이라 항상 True)만 봐서 이게 통과됐다.
    with pytest.raises(ValidationAppError):
        create_item(
            db, Department, name="B신설팀", org_id=two_orgs.org_b_id,
            parent_id=parent_in_a.id, scope=GLOBAL_SCOPE,
        )


def test_reparenting_a_department_to_another_org_is_rejected(db, two_orgs):
    parent_in_a = create_item(db, Department, name="본부", scope=_org_scope(two_orgs.org_a_id))
    child_in_b = create_item(db, Department, name="B신설팀", scope=_org_scope(two_orgs.org_b_id))
    db.commit()

    with pytest.raises(ValidationAppError):
        update_item(db, child_in_b, parent_id=parent_in_a.id, scope=GLOBAL_SCOPE)


def test_same_org_parent_still_works(db, two_orgs):
    """회귀 방지: 같은 조직 안에서는 여전히 부모를 지정할 수 있어야 한다."""
    parent = create_item(db, Department, name="본부", scope=_org_scope(two_orgs.org_a_id))
    child = create_item(
        db, Department, name="A신설팀", parent_id=parent.id, scope=_org_scope(two_orgs.org_a_id),
    )
    assert child.parent_id == parent.id

    other = create_item(db, Department, name="A신설팀2", scope=_org_scope(two_orgs.org_a_id))
    db.commit()
    updated = update_item(db, other, parent_id=parent.id, scope=_org_scope(two_orgs.org_a_id))
    assert updated.parent_id == parent.id


def test_cross_org_parent_never_leaks_into_dept_scope_subtree(db, two_orgs):
    """UA-13의 실제 피해를 직접 증명한다: 부모 지정이 (버그가 있었다면) 통과했더라도
    부서 서브트리 전개가 다른 조직 부서를 끌어들이면 안 된다.

    0060 에서 트리 전개가 `app/core/org_tree.py::DeptTree` 로 옮겨졌다 — 상향(조상)·하향
    (후손)·경로 계산이 한 자리에 모여야 세 개가 서로 다른 답을 내지 않는다. 여기서 보는
    성질은 그대로다."""
    from app.core.org_tree import DeptTree

    parent_in_a = create_item(db, Department, name="본부", scope=_org_scope(two_orgs.org_a_id))
    db.commit()

    with pytest.raises(ValidationAppError):
        create_item(
            db, Department, name="B신설팀", org_id=two_orgs.org_b_id,
            parent_id=parent_in_a.id, scope=GLOBAL_SCOPE,
        )

    # 검증이 막았으니 org B에는 자식이 안 생겼어야 한다 — org A 서브트리가 org B로 안 샌다.
    subtree = DeptTree.load(db).descendants(parent_in_a.id)
    from sqlalchemy import select

    org_b_dept_ids = set(
        db.execute(select(Department.id).where(Department.org_id == two_orgs.org_b_id)).scalars().all()
    )
    assert not (subtree & org_b_dept_ids)
