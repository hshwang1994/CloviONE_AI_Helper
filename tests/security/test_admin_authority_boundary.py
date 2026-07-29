"""iter4 High: a plain admin must not manage (reset-password/disable/unlock/
revoke-sessions/edit) a system_admin account — prevents admin→system_admin
takeover (spec §10 authority boundary)."""

import pytest

pytestmark = pytest.mark.security


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


@pytest.fixture()
def sysadmin_target(make_user):
    return make_user("sa-target@goodmit.co.kr", role="system_admin")


def test_admin_cannot_reset_system_admin_password(client, login_as, sysadmin_target):
    csrf = login_as("admin", email="attacker-admin@goodmit.co.kr")
    r = client.post(
        f"/api/admin/users/{sysadmin_target.id}/reset-password",
        json={"password": "Known-Pass-12!"},
        headers=_headers(csrf),
    )
    assert r.status_code == 403


def test_admin_cannot_disable_system_admin(client, login_as, sysadmin_target):
    csrf = login_as("admin", email="attacker2@goodmit.co.kr")
    r = client.post(
        f"/api/admin/users/{sysadmin_target.id}/disable", headers=_headers(csrf)
    )
    assert r.status_code == 403


def test_admin_cannot_unlock_system_admin(client, login_as, sysadmin_target):
    csrf = login_as("admin", email="attacker3@goodmit.co.kr")
    r = client.post(
        f"/api/admin/users/{sysadmin_target.id}/unlock", headers=_headers(csrf)
    )
    assert r.status_code == 403


def test_admin_cannot_revoke_system_admin_sessions(client, login_as, sysadmin_target):
    csrf = login_as("admin", email="attacker4@goodmit.co.kr")
    r = client.post(
        f"/api/admin/users/{sysadmin_target.id}/revoke-sessions", headers=_headers(csrf)
    )
    assert r.status_code == 403


def test_admin_cannot_edit_system_admin_profile(client, login_as, sysadmin_target):
    csrf = login_as("admin", email="attacker5@goodmit.co.kr")
    r = client.patch(
        f"/api/admin/users/{sysadmin_target.id}",
        json={"display_name": "탈취시도"},
        headers=_headers(csrf),
    )
    assert r.status_code == 403


def test_system_admin_can_manage_system_admin(client, login_as, make_user):
    target = make_user("sa-managed2@goodmit.co.kr", role="system_admin")
    csrf = login_as("system_admin")
    r = client.post(
        f"/api/admin/users/{target.id}/reset-password", headers=_headers(csrf)
    )
    assert r.status_code == 200


def test_admin_can_still_manage_normal_users(client, login_as, make_user):
    target = make_user("normal-target@goodmit.co.kr", role="operator")
    csrf = login_as("admin", email="legit-admin2@goodmit.co.kr")
    assert client.post(
        f"/api/admin/users/{target.id}/reset-password", headers=_headers(csrf)
    ).status_code == 200
    assert client.post(
        f"/api/admin/users/{target.id}/disable", headers=_headers(csrf)
    ).status_code == 200
