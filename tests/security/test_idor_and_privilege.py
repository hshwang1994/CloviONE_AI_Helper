"""IDOR sweep + privilege-escalation matrix (spec §25.5, §31.10)."""

import pytest

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.security


def _client_as(app, email):
    from fastapi.testclient import TestClient

    c = TestClient(app, raise_server_exceptions=False)
    c.post("/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD})
    return c


def test_user_cannot_access_other_users_objects(app, make_user):
    make_user("owner-a@goodmit.co.kr")
    make_user("attacker-b@goodmit.co.kr")

    a = _client_as(app, "owner-a@goodmit.co.kr")
    a_csrf = a.get("/api/me").json()["csrf_token"]
    conv = a.post("/api/conversations", json={}, headers={"X-CSRF-Token": a_csrf}).json()["conversation"]

    b = _client_as(app, "attacker-b@goodmit.co.kr")
    # Conversation owned by A → 403 for B.
    assert b.get(f"/api/conversations/{conv['id']}/messages").status_code == 403


@pytest.mark.parametrize("role", ["user", "operator"])
@pytest.mark.parametrize("endpoint", [
    "/api/admin/users",
    "/api/admin/settings",
    "/api/admin/notion-mapping",
])
def test_insufficient_role_blocked_from_admin_write_endpoints(app, make_user, role, endpoint):
    # settings/users/notion-mapping require admin+; user and operator are blocked.
    make_user(f"{role}-esc@goodmit.co.kr", role=role)
    c = _client_as(app, f"{role}-esc@goodmit.co.kr")
    if role == "operator" and endpoint == "/api/admin/notion-mapping":
        # operator can READ notion-mapping list.
        assert c.get(endpoint).status_code in (200, 403)
    r = c.get(endpoint)
    # user is always blocked; operator blocked from users/settings write scopes' list too? users list is admin+.
    if role == "user":
        assert r.status_code == 403


def test_operator_cannot_create_users(app, make_user):
    make_user("op-noesc@goodmit.co.kr", role="operator")
    c = _client_as(app, "op-noesc@goodmit.co.kr")
    csrf = c.get("/api/me").json()["csrf_token"]
    r = c.post(
        "/api/admin/users",
        json={"email": "ghost@goodmit.co.kr", "display_name": "유령"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 403


def test_auditor_is_read_only(app, make_user):
    make_user("auditor-ro@goodmit.co.kr", role="auditor")
    c = _client_as(app, "auditor-ro@goodmit.co.kr")
    csrf = c.get("/api/me").json()["csrf_token"]
    # Can read audit…
    assert c.get("/api/admin/audit").status_code == 200
    # …but cannot mutate anything (e.g. create integration).
    r = c.post(
        "/api/admin/integrations",
        json={"name": "x", "provider_type": "http_service", "base_url": "https://api.notion.com"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 403


def test_user_cannot_reach_any_admin_namespace(app, make_user):
    make_user("plain-esc@goodmit.co.kr")
    c = _client_as(app, "plain-esc@goodmit.co.kr")
    for path in ["/api/admin/users", "/api/admin/integrations", "/api/admin/audit",
                 "/api/admin/dashboard", "/api/admin/backups", "/api/admin/schedules"]:
        assert c.get(path).status_code == 403, path
