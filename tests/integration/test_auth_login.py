import pytest

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration


def test_login_success_sets_cookie_and_returns_user(client, make_user):
    make_user("hong@goodmit.co.kr", display_name="홍길동")
    r = client.post(
        "/login", json={"email": "hong@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["user"]["email"] == "hong@goodmit.co.kr"
    assert body["user"]["display_name"] == "홍길동"
    assert body["csrf_token"]

    set_cookie = r.headers["set-cookie"]
    assert "clovirone_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=strict" in set_cookie.lower() or "samesite=strict" in set_cookie.lower()

    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "hong@goodmit.co.kr"


def test_login_email_is_normalized(client, make_user):
    make_user("case@goodmit.co.kr")
    r = client.post(
        "/login",
        json={"email": "  CASE@GOODMIT.CO.KR  ", "password": DEFAULT_TEST_PASSWORD},
    )
    assert r.status_code == 200


def test_login_wrong_password_generic_error(client, make_user):
    make_user("wrongpw@goodmit.co.kr")
    r = client.post(
        "/login", json={"email": "wrongpw@goodmit.co.kr", "password": "Bad-Password-1"}
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_credentials"


def test_login_unknown_email_same_error_as_wrong_password(client):
    r = client.post(
        "/login", json={"email": "ghost@goodmit.co.kr", "password": "Bad-Password-1"}
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_credentials"


def test_account_lockout_after_max_failures_and_unlock_after_window(
    client, make_user, fake_clock, settings
):
    make_user("lockme@goodmit.co.kr")
    for _ in range(settings.login_max_failures):
        client.post(
            "/login", json={"email": "lockme@goodmit.co.kr", "password": "Bad-Pass-123"}
        )

    # Correct password now rejected: account locked.
    r = client.post(
        "/login",
        json={"email": "lockme@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "account_locked"

    # After the lock window passes, login succeeds again.
    fake_clock.advance(settings.login_lock_seconds + 1)
    r = client.post(
        "/login",
        json={"email": "lockme@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD},
    )
    assert r.status_code == 200


def test_inactive_user_cannot_login(client, make_user):
    make_user("gone@goodmit.co.kr", active=False)
    r = client.post(
        "/login", json={"email": "gone@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "account_disabled"


def test_login_rate_limit_by_ip(client, fake_clock):
    responses = [
        client.post(
            "/login", json={"email": "nobody@goodmit.co.kr", "password": "x-Bad-Pass-1"}
        )
        for _ in range(12)
    ]
    assert responses[-1].status_code == 429
    assert responses[-1].json()["error"]["code"] == "rate_limited"


def test_missing_fields_rejected(client):
    r = client.post("/login", json={"email": "", "password": ""})
    assert r.status_code == 422


@pytest.mark.parametrize("body", [[1, 2, 3], "x", 42, True])
def test_non_dict_json_body_does_not_crash(client, body):
    # 문법적으로 유효한 JSON이어도 객체가 아니면(list/string/number/...) data.get()이
    # AttributeError로 죽어 인증 없이도 500을 낼 수 있었다 — 깔끔한 4xx여야 한다.
    r = client.post("/login", json=body)
    assert r.status_code == 422
    assert r.json()["error"]["message"]
