import pytest

pytestmark = pytest.mark.security


@pytest.mark.parametrize("role", ["user", "operator", "auditor"])
def test_non_admin_roles_cannot_list_users(client, login_as, role):
    csrf = login_as(role)
    r = client.get("/api/admin/users", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 403


@pytest.mark.parametrize("role", ["user", "operator", "auditor"])
def test_non_admin_roles_cannot_create_users(client, login_as, role):
    csrf = login_as(role)
    r = client.post(
        "/api/admin/users",
        json={"email": "sneak@goodmit.co.kr", "display_name": "몰래"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 403


def test_admin_mutations_require_csrf(client, login_as):
    login_as("admin")
    r = client.post(
        "/api/admin/users",
        json={"email": "nocsrf@goodmit.co.kr", "display_name": "노토큰"},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"


def test_unauthenticated_admin_api_rejected(client):
    assert client.get("/api/admin/users").status_code == 401


@pytest.mark.parametrize(
    ("role", "expected"),
    [("user", 403), ("operator", 403), ("auditor", 200), ("admin", 200), ("system_admin", 200)],
)
def test_audit_read_role_matrix(client, login_as, role, expected):
    login_as(role)
    r = client.get("/api/admin/audit")
    assert r.status_code == expected
