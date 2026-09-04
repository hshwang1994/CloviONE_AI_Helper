import pytest

from app.core.sessions import SESSION_COOKIE_NAME

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
    assert f"{SESSION_COOKIE_NAME}=" in set_cookie
    assert "HttpOnly" in set_cookie
    # 🔴 `strict` 가 아니라 **`lax`** 다. `strict` 는 다른 사이트에서 시작된 이동에 쿠키를
    # 아예 안 실어서, 채팅앱·메일로 받은 티켓·문서 링크를 누른 사람이 **이미 로그인돼 있어도**
    # 매번 로그인 화면을 봤다. `lax` 는 top-level 이동 + 안전한 메서드 한 갈래만 열고,
    # cross-site 하위 요청과 cross-site POST 에는 그대로 안 싣는다.
    # CSRF 는 헤더 토큰이 막는다 — `tests/security/test_csrf_coverage.py` 가 그것을 라우트
    # 전량으로 검사한다. 이 단언을 `strict` 로 되돌리면 그 링크 증상이 그대로 돌아온다.
    assert "samesite=lax" in set_cookie.lower()
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


def test_login_rate_limit_resets_on_success(client, make_user):
    """🔴 성공 로그인은 IP 예산을 되돌린다.

    키가 IP 단위라 사내 NAT 뒤에서는 사무실 전체가 한 예산(분당 10회)을 쓴다 —
    성공까지 토큰을 소모하면 출근 시간대 11번째 사람부터 전부 맞는 자격 증명으로도
    429 를 본다(「요청이 너무 많습니다」 지속 보고의 뿌리 하나).
    """
    make_user("crowd@goodmit.co.kr")
    for i in range(12):
        r = client.post(
            "/login",
            json={"email": "crowd@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD},
        )
        assert r.status_code == 200, (
            f"{i + 1}번째 성공 로그인이 막혔다: {r.status_code} {r.text}"
        )


def test_failures_still_limited_after_a_success(client, make_user):
    """반례 — 리셋은 성공에만 붙는다. 실패 스프레이 예산은 한 글자도 안 바뀐다."""
    make_user("mixed@goodmit.co.kr")
    ok = client.post(
        "/login", json={"email": "mixed@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
    )
    assert ok.status_code == 200
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
