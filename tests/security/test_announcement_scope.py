"""공지는 부서/조직 범위 관리자가 손댈 수 없다 (UB-01).

공지는 `audience`(all/admin) 둘 다 **포탈 전체**에 뜬다 — 부서·조직별로 좁혀 보여줄
방법 자체가 없다. 그런데 라우터에 `get_principal`이 아예 없어서, 부서 범위 admin이
`audience=all`·`level=critical`·`dismissible=false`로 전사 배너를 띄우거나 전역 admin의
공지를 지울 수 있었다. 같은 위험을 이미 막아 둔 `quotas/router.py::_ensure_may_touch_global`
과 같은 판정을 공지에도 건다.
"""

from __future__ import annotations

import pytest

from app.users.models import ROLE_ADMIN

pytestmark = pytest.mark.security


def _h(csrf):
    return {"X-CSRF-Token": csrf}


def _create_payload():
    return {
        "title": "전사 배너",
        "body": "본문",
        "level": "critical",
        "audience": "all",
        "dismissible": False,
    }


@pytest.fixture()
def dept_scoped_admin(client, login_as, make_user, db):
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    dept = Department(name="공지테스트팀", org_id=DEFAULT_ORG_ID)
    db.add(dept)
    db.flush()
    boss = make_user("announce-dept-admin@goodmit.co.kr", role=ROLE_ADMIN)
    boss.department_id = dept.id
    db.commit()

    sa_csrf = login_as("system_admin")
    r = client.patch(
        f"/api/admin/users/{boss.id}",
        json={"admin_scope": "dept", "scope_dept_id": dept.id},
        headers=_h(sa_csrf),
    )
    assert r.status_code == 200, r.text
    client.post("/logout", headers=_h(sa_csrf))
    return login_as(ROLE_ADMIN, email="announce-dept-admin@goodmit.co.kr")


def test_dept_scoped_admin_cannot_create_announcement(client, dept_scoped_admin):
    r = client.post(
        "/api/admin/announcements", json=_create_payload(), headers=_h(dept_scoped_admin)
    )
    assert r.status_code == 403, r.text


def test_dept_scoped_admin_cannot_delete_a_global_admins_announcement(
    client, login_as, dept_scoped_admin
):
    sa_csrf = login_as("system_admin")
    row_id = client.post(
        "/api/admin/announcements", json=_create_payload(), headers=_h(sa_csrf)
    ).json()["id"]
    client.post("/logout", headers=_h(sa_csrf))

    login_as(ROLE_ADMIN, email="announce-dept-admin@goodmit.co.kr")
    r = client.delete(f"/api/admin/announcements/{row_id}", headers=_h(dept_scoped_admin))
    assert r.status_code == 403, r.text


def test_dept_scoped_admin_cannot_update_an_announcement(client, login_as, dept_scoped_admin):
    sa_csrf = login_as("system_admin")
    row_id = client.post(
        "/api/admin/announcements", json=_create_payload(), headers=_h(sa_csrf)
    ).json()["id"]
    client.post("/logout", headers=_h(sa_csrf))

    login_as(ROLE_ADMIN, email="announce-dept-admin@goodmit.co.kr")
    r = client.patch(
        f"/api/admin/announcements/{row_id}",
        json={"title": "몰래 수정"},
        headers=_h(dept_scoped_admin),
    )
    assert r.status_code == 403, r.text


def test_global_admin_can_still_manage_announcements(client, login_as):
    """회귀 없음 — 범위를 안 좁힌 관리자는 예전처럼 그대로 된다."""
    csrf = login_as("system_admin")
    created = client.post("/api/admin/announcements", json=_create_payload(), headers=_h(csrf))
    assert created.status_code == 201, created.text
    row_id = created.json()["id"]

    updated = client.patch(
        f"/api/admin/announcements/{row_id}", json={"title": "수정됨"}, headers=_h(csrf)
    )
    assert updated.status_code == 200, updated.text

    deleted = client.delete(f"/api/admin/announcements/{row_id}", headers=_h(csrf))
    assert deleted.status_code == 200, deleted.text
