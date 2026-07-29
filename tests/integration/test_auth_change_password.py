import pytest

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration

NEW_PASSWORD = "N3w-Different-Pass!"


def _login(client, email, password=DEFAULT_TEST_PASSWORD):
    r = client.post("/login", json={"email": email, "password": password})
    assert r.status_code == 200
    return r.json()


def test_must_change_password_blocks_other_apis(client, make_user):
    make_user("fresh@goodmit.co.kr", must_change_password=True)
    _login(client, "fresh@goodmit.co.kr")

    # /api/me stays available (needed by the change-password page)…
    assert client.get("/api/me").status_code == 200
    # …but everything else is blocked with a distinct code.
    r = client.get("/api/profile")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "password_change_required"


def test_change_password_happy_path_revokes_other_sessions(client, app, make_user):
    from fastapi.testclient import TestClient

    make_user("rotate@goodmit.co.kr", must_change_password=True)
    body = _login(client, "rotate@goodmit.co.kr")
    csrf = body["csrf_token"]

    # A second, concurrent session for the same user.
    with TestClient(app, raise_server_exceptions=False) as other:
        other.post(
            "/login",
            json={"email": "rotate@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD},
        )
        assert other.get("/api/me").status_code == 200

        r = client.post(
            "/change-password",
            json={
                "current_password": DEFAULT_TEST_PASSWORD,
                "new_password": NEW_PASSWORD,
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert r.status_code == 200

        # The other session must be revoked (spec §11.3).
        assert other.get("/api/me").status_code == 401

    # Current client received a rotated session and is no longer restricted.
    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["user"]["must_change_password"] is False
    assert client.get("/api/profile").status_code == 200

    # Old password no longer works; new one does.
    r = client.post(
        "/login",
        json={"email": "rotate@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD},
    )
    assert r.status_code == 401
    r = client.post(
        "/login", json={"email": "rotate@goodmit.co.kr", "password": NEW_PASSWORD}
    )
    assert r.status_code == 200


def test_change_password_wrong_current_rejected(client, make_user):
    make_user("wrongcur@goodmit.co.kr")
    csrf = _login(client, "wrongcur@goodmit.co.kr")["csrf_token"]
    r = client.post(
        "/change-password",
        json={"current_password": "Not-The-Password-1", "new_password": NEW_PASSWORD},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 401


def test_change_password_policy_enforced(client, make_user):
    make_user("weakpw@goodmit.co.kr")
    csrf = _login(client, "weakpw@goodmit.co.kr")["csrf_token"]
    r = client.post(
        "/change-password",
        json={"current_password": DEFAULT_TEST_PASSWORD, "new_password": "short"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 422
    assert r.json()["error"]["details"]


def test_change_password_same_as_current_rejected(client, make_user):
    make_user("same@goodmit.co.kr")
    csrf = _login(client, "same@goodmit.co.kr")["csrf_token"]
    r = client.post(
        "/change-password",
        json={
            "current_password": DEFAULT_TEST_PASSWORD,
            "new_password": DEFAULT_TEST_PASSWORD,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 422
