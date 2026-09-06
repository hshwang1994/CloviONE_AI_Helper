"""결재 대리 표면이 관리 범위를 지키는가 — P-12a (S5).

## 고쳤던 상태

`/api/admin/approval-delegations` 의 셋(`list`·`create`·`revoke`)이 `principal` 을 **아예
안 받았다.** 같은 파일의 승인 큐는 이미 `visible_user_ids(db, principal.management)` 로
좁히는데 이쪽만 전량이었다.

역할 게이트(`CONSOLE_WRITE_ROLES`)는 이것을 못 막는다 — 거기 들어 있는 `admin` 이
**부서 범위일 수 있기 때문이다**(`users.admin_scope`). 그래서 부서 admin 이 남의 부서
결재 대리를 **만들고 취소**할 수 있었다. 위임은 「A 의 결재 권한을 B 가 쓴다」라, 그것을
남의 부서에 만들 수 있다는 것은 그 부서의 승인 권한을 임의로 배분할 수 있다는 뜻이다.

역할과 범위는 직교한다 — 이 파일이 보는 것은 **범위** 쪽이다.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

pytestmark = pytest.mark.security


@pytest.fixture()
def two_departments(db, make_user):
    """부서 둘 · 그 각각의 부서 범위 admin · 각 부서의 admin 한 명씩."""
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import OrgUnit
    from app.users.models import ADMIN_SCOPE_DEPT

    dept_a = OrgUnit(name="A본부", org_id=DEFAULT_ORG_ID)
    dept_b = OrgUnit(name="B본부", org_id=DEFAULT_ORG_ID)
    db.add_all([dept_a, dept_b])
    db.flush()

    def _member(email, dept, role):
        user = make_user(email, role=role, display_name=email.split("@")[0])
        user.department_id = dept.id
        user.org_id = DEFAULT_ORG_ID
        return user

    boss_a = _member("deleg-boss-a@goodmit.co.kr", dept_a, "admin")
    boss_a.admin_scope = ADMIN_SCOPE_DEPT
    boss_a.scope_dept_id = dept_a.id

    boss_b = _member("deleg-boss-b@goodmit.co.kr", dept_b, "admin")
    boss_b.admin_scope = ADMIN_SCOPE_DEPT
    boss_b.scope_dept_id = dept_b.id

    worker_a = _member("deleg-worker-a@goodmit.co.kr", dept_a, "operator")
    worker_b = _member("deleg-worker-b@goodmit.co.kr", dept_b, "operator")
    db.commit()
    return {
        "dept_a": dept_a, "dept_b": dept_b,
        "boss_a": boss_a, "boss_b": boss_b,
        "worker_a": worker_a, "worker_b": worker_b,
    }


def _make_delegation(db, clock, *, delegator, delegate):
    from app.approvals import delegation

    now = clock.now()
    row = delegation.create(
        db, delegator=delegator, delegate=delegate,
        starts_at=now, ends_at=now + timedelta(days=1),
        reason=None, created_by=delegator.id, now=now, visible=None,
    )
    db.commit()
    return row


def test_a_department_admin_cannot_create_a_delegation_in_another_department(
    client, login_as, db, two_departments
):
    """만들 수 있으면 남의 부서 승인 권한을 임의로 배분할 수 있다."""
    world = two_departments
    csrf = login_as("admin", email=world["boss_a"].email)
    r = client.post(
        "/api/admin/approval-delegations",
        json={
            "delegator_user_id": world["boss_b"].id,
            "delegate_user_id": world["worker_b"].id,
            "starts_at": "2026-08-22T00:00:00",
            "ends_at": "2026-08-23T00:00:00",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 404, (
        f"A본부 admin 이 B본부 결재 대리를 만들었다: {r.status_code} {r.text}"
    )


def test_the_same_admin_can_still_create_one_inside_their_own_department(
    client, login_as, db, two_departments
):
    """위 시험이 「전부 막는 게이트」로 통과하지 못하게 한다."""
    world = two_departments
    csrf = login_as("admin", email=world["boss_a"].email)
    r = client.post(
        "/api/admin/approval-delegations",
        json={
            "delegator_user_id": world["boss_a"].id,
            "delegate_user_id": world["worker_a"].id,
            "starts_at": "2026-08-22T00:00:00",
            "ends_at": "2026-08-23T00:00:00",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 201, f"자기 부서 안에서도 못 만든다: {r.status_code} {r.text}"


def test_a_department_admin_does_not_see_another_departments_delegation(
    client, login_as, db, two_departments, fake_clock
):
    world = two_departments
    row = _make_delegation(db, fake_clock, delegator=world["boss_b"], delegate=world["worker_b"])
    mine = _make_delegation(db, fake_clock, delegator=world["boss_a"], delegate=world["worker_a"])

    csrf = login_as("admin", email=world["boss_a"].email)
    r = client.get("/api/admin/approval-delegations", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    ids = {item["id"] for item in r.json()["items"]}
    assert row.id not in ids, "B본부 결재 대리가 A본부 admin 의 목록에 보인다"
    assert mine.id in ids, "자기 부서 결재 대리까지 사라졌다 — 범위가 너무 좁다"


def test_a_department_admin_cannot_revoke_another_departments_delegation(
    client, login_as, db, two_departments, fake_clock
):
    """목록에서 가린 것을 id 로 취소할 수 있으면 가린 의미가 없다.

    범위 밖은 **403 이 아니라 404** 다 — 403 은 그 id 가 존재한다는 사실을 알려 준다.
    """
    world = two_departments
    row = _make_delegation(db, fake_clock, delegator=world["boss_b"], delegate=world["worker_b"])

    csrf = login_as("admin", email=world["boss_a"].email)
    r = client.post(
        f"/api/admin/approval-delegations/{row.id}/revoke",
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 404, (
        f"A본부 admin 이 B본부 결재 대리를 취소했다: {r.status_code} {r.text}"
    )
    db.refresh(row)
    assert row.revoked_at is None, "요청은 404 였는데 실제로는 취소됐다"


# ── 대리인이 될 수 있는 역할 (perm-22) ──────────────────────────────────────
#
# 범위와 역할은 직교한다. 위쪽 시험들이 **범위**를 보는 것과 달리, 아래 둘은 위임이 역할
# 경계를 도는 문이 되지 않는지를 본다.


def test_a_delegation_cannot_hand_decisions_to_an_auditor(client, login_as, db, make_user):
    """감사자는 이 저장소가 「읽기 전용 가지」로 정의한 역할이라 쓰기 역할 묶음에 절대 들어가지
    않는다(app/core/authz.py). 위임으로 결재 권한이 붙으면 감사자가 자기가 감사할 결정을
    스스로 내리고, 권한 매트릭스 화면이 말하는 것과 실제가 달라진다."""
    boss = make_user("deleg-role-boss@goodmit.co.kr", role="admin", display_name="관리자")
    auditor = make_user("deleg-role-auditor@goodmit.co.kr", role="auditor", display_name="감사자")
    db.commit()

    csrf = login_as("system_admin", email="deleg-role-root@goodmit.co.kr")
    r = client.post(
        "/api/admin/approval-delegations",
        json={
            "delegator_user_id": boss.id,
            "delegate_user_id": auditor.id,
            "starts_at": "2026-08-22T00:00:00",
            "ends_at": "2026-08-23T00:00:00",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 422, f"감사자에게 결재 권한이 위임됐다: {r.status_code} {r.text}"
    assert "감사자" in r.json()["error"]["message"]


def test_a_delegation_to_an_operator_is_still_allowed(client, login_as, db, make_user):
    """오탐 방지 — 위임의 목적이 「평소 결재할 수 없는 운영자가 부재 기간에 결재한다」이므로
    그 길까지 막으면 기능 자체가 사라진다(app/approvals/delegation.py 머리말)."""
    boss = make_user("deleg-role-boss2@goodmit.co.kr", role="admin", display_name="관리자2")
    operator = make_user("deleg-role-op@goodmit.co.kr", role="operator", display_name="운영자")
    db.commit()

    csrf = login_as("system_admin", email="deleg-role-root2@goodmit.co.kr")
    r = client.post(
        "/api/admin/approval-delegations",
        json={
            "delegator_user_id": boss.id,
            "delegate_user_id": operator.id,
            "starts_at": "2026-08-22T00:00:00",
            "ends_at": "2026-08-23T00:00:00",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 201, f"운영자에게 위임할 수 없다: {r.status_code} {r.text}"


def test_a_global_admin_still_sees_and_revokes_everything(
    client, login_as, db, two_departments, fake_clock
):
    """전역 관리자는 그대로다 — 이 수정이 관리 화면을 망가뜨리지 않았다는 반대편 증거."""
    world = two_departments
    row = _make_delegation(db, fake_clock, delegator=world["boss_b"], delegate=world["worker_b"])

    csrf = login_as("system_admin", email="deleg-root@goodmit.co.kr")
    listed = client.get("/api/admin/approval-delegations", headers={"X-CSRF-Token": csrf})
    assert row.id in {item["id"] for item in listed.json()["items"]}

    r = client.post(
        f"/api/admin/approval-delegations/{row.id}/revoke",
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text
    db.refresh(row)
    assert row.revoked_at is not None
