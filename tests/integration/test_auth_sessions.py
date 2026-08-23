import pytest

from app.core.sessions import SESSION_COOKIE_NAME
from sqlalchemy import select

from app.auth.models import UserSession
from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration


def _login(client, email):
    r = client.post("/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD})
    assert r.status_code == 200
    return r


def test_unauthenticated_api_request_is_401(client):
    r = client.get("/api/me")
    assert r.status_code == 401


def test_unauthenticated_page_redirects_to_login(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303
    # ?next=<original path> lets a post-login redirect return the user to where
    # they were headed (app/main.py's PageAuthRequired handler) instead of
    # always dropping them on "/".
    assert r.headers["location"] == "/login?next=%2F"


def test_session_fixation_cookie_is_replaced_on_login(client, make_user):
    make_user("fix@goodmit.co.kr")
    client.cookies.set(SESSION_COOKIE_NAME, "attacker-chosen-token")
    r = _login(client, "fix@goodmit.co.kr")
    new_cookie = r.headers["set-cookie"]
    assert "attacker-chosen-token" not in new_cookie
    assert client.get("/api/me").status_code == 200


def test_idle_timeout_expires_session(client, make_user, fake_clock, settings):
    make_user("idle@goodmit.co.kr")
    _login(client, "idle@goodmit.co.kr")
    assert client.get("/api/me").status_code == 200

    fake_clock.advance(settings.session_idle_timeout_seconds + 1)
    assert client.get("/api/me").status_code == 401


def test_idle_timeout_actually_persists_revoked_at(client, make_user, fake_clock, settings, db):
    """CORE-02: 401을 반환하는 것과 그 사실을 저장하는 것은 다른 일이다.

    예전엔 `validate()`가 `record.revoked_at`을 메모리에서만 바꾸고 `None`을 돌려줬는데,
    그 `None`이 `UnauthorizedError`로 이어지면서 `get_db`의 예외 처리가 세션 전체를
    롤백해 그 쓰기까지 함께 사라졌다 — `/api/me`는 (index 조건 `revoked_at IS NULL`이 아직
    안 걸려서) 여전히 401을 냈지만, DB에는 만료된 세션이 영원히 "활성"으로 남아
    `profiles`의 활성 세션 목록·개수를 틀리게 만들고 `retention`이 정리하지도 못했다.
    """
    make_user("idle-persist@goodmit.co.kr")
    _login(client, "idle-persist@goodmit.co.kr")
    fake_clock.advance(settings.session_idle_timeout_seconds + 1)
    assert client.get("/api/me").status_code == 401

    row = db.execute(
        select(UserSession).where(UserSession.user_id.isnot(None)).order_by(UserSession.created_at.desc())
    ).scalars().first()
    assert row is not None
    assert row.revoked_at is not None, "만료된 세션의 revoked_at이 DB에 저장되지 않았다"


def test_absolute_timeout_actually_persists_revoked_at(client, make_user, fake_clock, settings, db):
    """CORE-02의 다른 분기(절대 만료) — 두 분기 모두 커밋해야 한다."""
    make_user("absolute-persist@goodmit.co.kr")
    _login(client, "absolute-persist@goodmit.co.kr")
    fake_clock.advance(settings.session_ttl_seconds)
    assert client.get("/api/me").status_code == 401

    row = db.execute(
        select(UserSession).where(UserSession.user_id.isnot(None)).order_by(UserSession.created_at.desc())
    ).scalars().first()
    assert row is not None
    assert row.revoked_at is not None, "절대 만료된 세션의 revoked_at이 DB에 저장되지 않았다"


def test_activity_keeps_session_alive(client, make_user, fake_clock, settings):
    make_user("active@goodmit.co.kr")
    _login(client, "active@goodmit.co.kr")
    # Touch the session every 10 minutes — never idle long enough to expire.
    for _ in range(4):
        fake_clock.advance(600)
        assert client.get("/api/me").status_code == 200


def test_absolute_timeout_expires_session_despite_activity(
    client, make_user, fake_clock, settings
):
    make_user("absolute@goodmit.co.kr")
    _login(client, "absolute@goodmit.co.kr")
    elapsed = 0
    step = 900  # 15 min activity intervals — under the idle limit
    while elapsed <= settings.session_ttl_seconds:
        fake_clock.advance(step)
        elapsed += step
        response = client.get("/api/me")
        if elapsed >= settings.session_ttl_seconds:
            # expires_at <= now → the session dies exactly at the absolute limit.
            assert response.status_code == 401
            return
        assert response.status_code == 200
    pytest.fail("absolute timeout never triggered")


def test_logout_revokes_session(client, make_user):
    make_user("bye@goodmit.co.kr")
    r = _login(client, "bye@goodmit.co.kr")
    csrf = r.json()["csrf_token"]
    assert client.post("/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert client.get("/api/me").status_code == 401


def test_deactivated_user_session_is_rejected(client, make_user, db):
    user = make_user("suspend@goodmit.co.kr")
    _login(client, "suspend@goodmit.co.kr")
    assert client.get("/api/me").status_code == 200

    user.active = False
    db.commit()
    assert client.get("/api/me").status_code == 401
