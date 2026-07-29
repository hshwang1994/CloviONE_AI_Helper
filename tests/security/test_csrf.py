import pytest

pytestmark = pytest.mark.security


def test_mutating_request_without_csrf_token_rejected(client, login_as):
    login_as("user")
    r = client.post("/logout")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"


def test_mutating_request_with_wrong_csrf_token_rejected(client, login_as):
    login_as("user")
    r = client.post("/logout", headers={"X-CSRF-Token": "forged-token-value"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"


def test_mutating_request_with_correct_csrf_token_allowed(client, login_as):
    csrf = login_as("user")
    r = client.post("/logout", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200


def test_csrf_token_not_exposed_in_cookies(client, login_as):
    login_as("user")
    assert "csrf" not in "".join(client.cookies.keys()).lower()


def test_change_password_requires_csrf(client, login_as):
    login_as("user")
    r = client.post(
        "/change-password",
        json={"current_password": "x", "new_password": "y"},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"
