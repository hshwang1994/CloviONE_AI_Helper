import pytest

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
    client.cookies.set("clovirone_session", "attacker-chosen-token")
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
