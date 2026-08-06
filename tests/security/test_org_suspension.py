"""조직 정지가 **실제로** 무언가를 한다 (X5).

정지 버튼·상태 표시·감사 로그는 전부 있었는데 **`ORG_SUSPENDED` 를 읽는 코드가 저장소에
하나도 없었다.** 그 조직 사람들은 계속 로그인하고 계속 썼다. 관리자는 실패도 경고도 없이
"했다" 는 확인만 받는다 — **시스템이 하지 않은 일을 했다고 말하는** 부류다.

세 층을 다 본다. 하나라도 빠지면 정지가 무력해진다:

1. **새 로그인**을 막는가 (그리고 이유를 말해 주는가)
2. **이미 로그인해 있던 사람**이 끊기는가 — 안 그러면 최대 8시간 동안 계속 쓴다
3. **`system_admin` 은 살아남는가** — 막으면 정지를 풀 사람이 없어진다(자기 자신을 잠근다)
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.security


@pytest.fixture()
def other_org(db):
    from app.org.models import Organization

    org = Organization(slug="tenant-b", name="다른회사", status="active")
    db.add(org)
    db.commit()
    return org


def _suspend(client, csrf, org_id):
    return client.patch(
        f"/api/admin/organizations/{org_id}",
        json={"status": "suspended"},
        headers={"X-CSRF-Token": csrf},
    )


def test_a_member_of_a_suspended_org_cannot_log_in(client, login_as, make_user, db, other_org):
    member = make_user("sus-member@goodmit.co.kr", role="user", display_name="B사람")
    member.org_id = other_org.id
    db.commit()

    csrf = login_as("system_admin")
    r = _suspend(client, csrf, other_org.id)
    assert r.status_code == 200, r.text
    client.post("/logout", headers={"X-CSRF-Token": csrf})

    from tests.conftest import DEFAULT_TEST_PASSWORD

    r = client.post(
        "/login", json={"email": "sus-member@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
    )
    assert r.status_code == 403, f"정지된 조직 사람이 로그인했다: {r.status_code} {r.text}"
    assert r.json()["error"]["code"] == "organization_suspended", (
        f"이유를 안 알려 준다 — 당사자는 비밀번호를 몇 번 더 넣다 계정이 잠긴다: {r.text}"
    )


def test_an_already_logged_in_member_is_cut_off(client, login_as, make_user, db, other_org):
    """세션이 만료될 때까지 기다리면 **정지는 최대 8시간 뒤에** 효력이 생긴다.

    관리자는 그 동안 정지했다고 믿는다.
    """
    member = make_user("sus-live@goodmit.co.kr", role="user", display_name="B사람")
    member.org_id = other_org.id
    # 정지시킬 운영자를 미리 만들어 둔다(이 세션은 피해자 것으로 써야 하므로 따로 로그인한다).
    make_user("system-admin@goodmit.co.kr", role="system_admin", display_name="포탈운영자")
    db.commit()

    login_as("user", email="sus-live@goodmit.co.kr")
    assert client.get("/api/me").status_code == 200, "정지 전인데 이미 못 쓴다"

    # 다른 클라이언트로 정지시킨다(이 세션은 그대로 둔 채).
    from fastapi.testclient import TestClient

    admin = TestClient(client.app)
    admin.app = client.app
    from tests.conftest import DEFAULT_TEST_PASSWORD

    r = admin.post(
        "/login", json={"email": "system-admin@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
    )
    assert r.status_code == 200, r.text
    r = admin.patch(
        f"/api/admin/organizations/{other_org.id}",
        json={"status": "suspended"},
        headers={"X-CSRF-Token": r.json()["csrf_token"]},
    )
    assert r.status_code == 200, r.text

    assert client.get("/api/me").status_code == 401, (
        "정지했는데 이미 로그인해 있던 사람이 계속 쓴다"
    )


def test_the_portal_operator_does_not_lock_themselves_out(
    client, login_as, db, other_org
):
    """`system_admin` 까지 막으면 **정지를 풀 사람이 없어진다.**"""
    from app.users.models import User
    from sqlalchemy import select

    op = db.execute(
        select(User).where(User.email == "system-admin@goodmit.co.kr")
    ).scalar_one_or_none()

    csrf = login_as("system_admin")
    if op is None:
        op = db.execute(
            select(User).where(User.email == "system-admin@goodmit.co.kr")
        ).scalar_one()
    op.org_id = other_org.id  # 운영자를 그 조직 소속으로 두고 정지시켜 본다
    db.commit()

    r = _suspend(client, csrf, other_org.id)
    assert r.status_code == 200, r.text
    assert client.get("/api/me").status_code == 200, (
        "조직을 정지시킨 운영자가 자기 자신을 잠갔다 — 정지를 풀 수 없다"
    )


def test_reactivating_lets_people_back_in(client, login_as, make_user, db, other_org):
    """오탐 방지 — 되살렸는데 못 들어오면 그건 정지가 아니라 파괴다."""
    member = make_user("sus-back@goodmit.co.kr", role="user", display_name="B사람")
    member.org_id = other_org.id
    db.commit()

    csrf = login_as("system_admin")
    _suspend(client, csrf, other_org.id)
    r = client.patch(
        f"/api/admin/organizations/{other_org.id}",
        json={"status": "active"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text
    client.post("/logout", headers={"X-CSRF-Token": csrf})

    from tests.conftest import DEFAULT_TEST_PASSWORD

    r = client.post(
        "/login", json={"email": "sus-back@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
    )
    assert r.status_code == 200, f"정지를 풀었는데 못 들어온다: {r.status_code} {r.text}"
