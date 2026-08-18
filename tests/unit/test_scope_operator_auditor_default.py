"""RBAC 재감사(2026-08-16)로 발견: 범위 계산이 `role == ROLE_USER`만 따로 보고 나머지는
전부(operator/auditor 포함) `admin_scope` 컬럼으로 판정해 왔다. 그 컬럼의 기본값은
`global`(0024 마이그레이션의 의도된 선택)이고, 관리자가 사용자를 운영자/감사자로 바꿀 때
"관리 범위"를 함께 좁히는 것은 강제되지 않는 선택이다 — 그래서 `admin_scope`를 한 번도
명시적으로 좁힌 적 없는 운영자는 그 사실만으로 전역 범위가 됐다(실측:
`tests/integration/test_idea_board.py::test_another_organization_neither_sees_nor_moves_an_idea`
가 이 정확한 증상으로 실패하고 있었다 — 조직 B 운영자가 조직 A의 아이디어를 그대로 봤다).

0060 에서 범위가 조회(visibility)와 관리(management) 둘로 갈렸다. 위 성질은 **관리 범위**의
것이므로 이 파일은 `management_scope()`를 고정한다 — 함수 이름만 바뀌었을 뿐 보호하는 사실은
그대로다. 조회 범위가 그 관리 범위를 물려받는지(관리하는데 안 보이면 관리할 수 없다)도
함께 못박는다.
"""

from __future__ import annotations

import pytest

from app.core.scope import management_scope, visibility_scope
from app.users.models import ADMIN_SCOPE_DEPT, ADMIN_SCOPE_GLOBAL, ADMIN_SCOPE_ORG

pytestmark = pytest.mark.unit


def _department(db, org_id, name="검사팀"):
    from app.org.models import Department

    dept = Department(name=name, org_id=org_id)
    db.add(dept)
    db.commit()
    return dept


@pytest.mark.parametrize("role", ["operator", "auditor"])
def test_operator_and_auditor_default_to_their_own_org_not_global(db, make_user, role):
    """`admin_scope`를 한 번도 안 건드린 운영자/감사자 — 컬럼 기본값(global)을 그대로
    물려받으면 안 된다. 자기 조직으로 좁혀야 한다(전역이 아니다)."""
    user = make_user("op-default@goodmit.co.kr", role=role)
    assert user.admin_scope == ADMIN_SCOPE_GLOBAL, "이 시험의 전제(컬럼 기본값)가 깨졌다"

    scope = management_scope(db, user)

    assert not scope.is_global, f"{role}가 admin_scope를 안 건드렸는데도 전역 범위가 됐다"
    assert scope.is_org
    assert scope.org_id == user.org_id


@pytest.mark.parametrize("role", ["operator", "auditor"])
def test_an_explicitly_narrowed_operator_or_auditor_is_still_respected(db, make_user, role):
    """관리 콘솔이 실제로 org/dept로 좁힌 운영자/감사자 — 그 명시적 설정은 그대로
    존중해야 한다(이 수정이 관리 콘솔의 기존 좁히기 기능을 무력화하면 안 된다)."""
    user = make_user(f"op-narrowed-{role}@goodmit.co.kr", role=role)
    dept = _department(db, user.org_id)
    user.admin_scope = ADMIN_SCOPE_DEPT
    user.scope_dept_id = dept.id
    db.commit()

    scope = management_scope(db, user)

    assert not scope.is_global
    assert scope.kind == ADMIN_SCOPE_DEPT
    assert dept.id in scope.dept_ids


def test_a_true_admin_still_defaults_to_global_unchanged(db, make_user):
    """이 수정은 operator/auditor에만 좁힌다 — admin/system_admin은 예전과 똑같이
    admin_scope 기본값(global)을 그대로 따라야 한다(0024가 의도한 대로, 관리 화면이
    조용히 비면 안 된다는 원래 근거를 이 수정이 건드리면 안 된다)."""
    user = make_user("still-global-admin@goodmit.co.kr", role="admin")
    assert user.admin_scope == ADMIN_SCOPE_GLOBAL

    scope = management_scope(db, user)

    assert scope.is_global, "관리자(admin)의 기본 전역 범위가 이 수정으로 깨졌다"


def test_an_explicitly_global_operator_is_downgraded_to_org_not_left_global(db, make_user):
    """컬럼만 봐서는 '한 번도 안 건드림'과 '일부러 global을 골랐음'을 구분할 수 없다 —
    강한 권한(전역 범위)은 명시적 선택 쪽으로만 좁힌다는 판단을 그대로 실측한다:
    admin_scope='global'을 **명시적으로 다시 대입**해도 결과는 여전히 org 범위다."""
    from app.users.models import ADMIN_SCOPE_GLOBAL as _GLOBAL

    user = make_user("op-explicit-global@goodmit.co.kr", role="operator")
    user.admin_scope = _GLOBAL  # 이미 기본값과 같지만, "명시적으로 다시 씀"을 표현
    db.commit()

    scope = management_scope(db, user)

    assert not scope.is_global
    assert scope.kind == ADMIN_SCOPE_ORG


def test_visibility_inherits_the_management_grant(db, make_user):
    """관리 범위를 배정받았다는 것은 그 대상을 **볼 수 있다**는 뜻이기도 하다.

    부서 관리자가 자기 소속(membership)으로는 아무것도 못 보는 상태(부서 미지정)여도,
    관리하도록 배정된 부서는 조회 범위에 들어와야 한다 — 관리하는데 안 보이면 관리할 수 없다.
    """
    user = make_user("dept-admin@goodmit.co.kr", role="admin", membership="unassigned")
    dept = _department(db, user.org_id, name="관리대상팀")
    user.admin_scope = ADMIN_SCOPE_DEPT
    user.scope_dept_id = dept.id
    db.commit()

    assert user.membership_kind == "unassigned", "이 시험의 전제(소속 미지정)가 깨졌다"
    assert dept.id in management_scope(db, user).dept_ids
    assert dept.id in visibility_scope(db, user).dept_ids
