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
    # S3: 세션 쿠키는 **host-only** 다 — `Domain` 을 붙이지 않는다.
    # 호스트명을 바꾸면서 «옛 이름으로 로그인한 사람이 새 이름에서 다시 로그인해야 한다» 를
    # 없애려고 `Domain=.gooddi.lab` 을 붙이고 싶어지는 자리다. 그러면 그 도메인의 **모든**
    # 호스트로 세션 쿠키가 나간다 — 같은 망의 공유 n8n 을 포함해서. 1회 재로그인이 그것보다
    # 싸다. 이 단언이 그 유혹을 막는다.
    assert "domain=" not in set_cookie.lower()

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


# ADM-05: 잠금 정책이 env 전용이라 관리자가 화면에서 조정할 수 없었다 — session_policy와
# 같은 "DB override, 없으면 env 기본값" 모양으로 신설했다. 이 시험은 저장한 값이 실제
# 로그인 잠금 동작에 즉시 반영되는지(다음 로그인 시도부터, 별도로 굳는 지점 없음) 끝까지
# 확인한다 — 설정 화면에 값만 보이고 실제 판정은 여전히 env를 쓰는 반쪽 배선을 잡기 위해서다.
def test_lockout_policy_override_applies_immediately(client, make_user, fake_clock, login_as):
    make_user("override-lock@goodmit.co.kr")
    admin_csrf = login_as("admin", email="lockout-policy-admin@goodmit.co.kr")

    r = client.put(
        "/api/admin/settings/lockout_policy",
        json={"value": {"max_failures": 2, "lock_seconds": 120}},
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert r.status_code == 200, r.text

    # env 기본값(5회)이 아니라 저장한 값(2회)만에 잠긴다.
    for _ in range(2):
        client.post(
            "/login", json={"email": "override-lock@goodmit.co.kr", "password": "Bad-Pass-123"}
        )
    r = client.post(
        "/login",
        json={"email": "override-lock@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "account_locked"

    # env 기본값(900초)이 아니라 저장한 값(120초)이 지나면 풀린다.
    fake_clock.advance(121)
    r = client.post(
        "/login",
        json={"email": "override-lock@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD},
    )
    assert r.status_code == 200, r.text


def test_lockout_policy_falls_back_to_env_default_when_unset(client, make_user, settings):
    """아무도 이 설정을 저장하지 않은 설치는 예전(env)과 똑같이 동작해야 한다."""
    make_user("no-override-lock@goodmit.co.kr")
    for _ in range(settings.login_max_failures):
        client.post(
            "/login", json={"email": "no-override-lock@goodmit.co.kr", "password": "Bad-Pass-123"}
        )
    r = client.post(
        "/login",
        json={"email": "no-override-lock@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "account_locked"


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
