"""구슬 레이스의 범위 — 다른 조직 · 비구성원 · 비방장 (기능 개선 회차 P5, D-564). 음성 시험이다.

못박는 성질:
1. 다른 조직의 방은 참가자 편집 · 설정 · 시작 · 결과 제출 전부 404 다(존재를 흘리지 않는다).
2. 같은 조직이라도 방에 들어오지 않은 사람은 결과를 올릴 수 없다(403). 방장이 아닌 구성원의 finish · 참가자 편집 · 설정은 403.
3. 결과 제출 · 참가자 편집은 CSRF 를 지난다(403).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.games import marble
from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = [pytest.mark.security, pytest.mark.real_db]


def _login_other(app, email):
    client = TestClient(app, raise_server_exceptions=False)
    client.post("/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD})
    return client, client.get("/api/me").json()["csrf_token"]


def _create(client, csrf):
    r = client.post("/api/games/rooms", json={"title": "구슬", "game_type": "marble_race"}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    return r.json()["room"]["id"]


def test_another_org_sees_nothing_and_non_members_cannot_submit(app, client, login_as, make_user, fake_clock, two_orgs):
    csrf = login_as("user", email="scope-host@goodmit.co.kr")
    rid = _create(client, csrf)
    h = {"X-CSRF-Token": csrf}
    assert client.put(f"/api/games/rooms/{rid}/marble/participants",
                      json={"participants": [{"name": "a"}, {"name": "b"}]}, headers=h).status_code == 200
    assert client.post(f"/api/games/rooms/{rid}/start", headers=h).status_code == 200
    state = client.get(f"/api/games/rooms/{rid}/state?since=0").json()["state"]
    keys = [p["key"] for p in state["participants"]]
    steps = [100, 200]
    body = {"race_id": state["race_id"], "ranking": keys, "finish_steps": steps,
            "digest": marble.digest_of(state["race_id"], keys, steps)}
    fake_clock.advance(seconds=marble.MIN_RACE_SECONDS + 1)

    other, csrf_other = _login_other(app, two_orgs.user_b.email)
    ho = {"X-CSRF-Token": csrf_other}
    assert other.get(f"/api/games/rooms/{rid}/state?since=0").status_code == 404
    assert other.put(f"/api/games/rooms/{rid}/marble/participants", json={"participants": [{"name": "a"}, {"name": "b"}]}, headers=ho).status_code == 404
    assert other.put(f"/api/games/rooms/{rid}/marble/config", json={"winners": 2}, headers=ho).status_code == 404
    assert other.post(f"/api/games/rooms/{rid}/marble/finish", json=body, headers=ho).status_code == 404
    assert other.post(f"/api/games/rooms/{rid}/marble/attest", json=body, headers=ho).status_code == 404

    make_user("scope-stranger@goodmit.co.kr")
    stranger, csrf_stranger = _login_other(app, "scope-stranger@goodmit.co.kr")
    hs = {"X-CSRF-Token": csrf_stranger}
    assert stranger.post(f"/api/games/rooms/{rid}/marble/attest", json=body, headers=hs).status_code == 403, "방 밖"
    assert stranger.post(f"/api/games/rooms/{rid}/marble/finish", json=body, headers=hs).status_code == 403
    assert stranger.put(f"/api/games/rooms/{rid}/marble/config", json={"winners": 2}, headers=hs).status_code == 403

    assert client.post(f"/api/games/rooms/{rid}/marble/finish", json=body).status_code == 403, "CSRF 없음"
    assert client.put(f"/api/games/rooms/{rid}/marble/participants", json={"participants": []}).status_code == 403
    assert client.post(f"/api/games/rooms/{rid}/marble/finish", json=body, headers=h).status_code == 200, "방장 본인은 된다"
