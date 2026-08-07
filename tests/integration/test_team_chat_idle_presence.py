"""탭만 열어 두고 간 사람은 '접속 중'이 아니다 — HTTP 경로까지 (X12).

`tests/unit/test_presence_idle.py` 는 판정 함수와 서비스를 본다. 여기서는 **실제 요청**이
그 판정까지 도달하는지를 본다: 라우터가 `idle` 을 안 받거나, 받고도 서비스에 안 넘기면
유닛 테스트는 전부 초록인데 화면은 예전 그대로다(배선이 빠진 채 통과하는 그 모양).

시나리오는 실제로 겪은 그것이다:
  1. 두 사람이 1:1 방을 연다 → 둘 다 접속 중.
  2. 한 사람이 모니터만 끄고 퇴근한다. 탭은 살아 있어 폴링은 계속 온다 —
     다만 이제 그 폴링에는 `idle=1` 이 붙는다.
  3. 온라인 창(2분)이 지나면 상대 화면에서 점이 꺼진다.
  4. 다음 날 아침 마우스를 한 번 움직이면 **즉시** 다시 켜진다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.team_chat.service import ONLINE_SECONDS
from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration


def _login_other(app, email):
    c = TestClient(app, raise_server_exceptions=False)
    c.post("/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD})
    return c


def _members(client, rid):
    r = client.get(f"/api/team-chat/rooms/{rid}/messages?since=0")
    assert r.status_code == 200, r.text
    return r.json()["members"]


def _online(client, rid, user_id):
    return next(m for m in _members(client, rid) if m["user_id"] == user_id)["online"]


def _direct(client, csrf, other_id):
    return client.post(
        "/api/team-chat/rooms/direct", json={"user_id": other_id},
        headers={"X-CSRF-Token": csrf},
    ).json()["room"]["id"]


def test_idle_polling_lets_the_dot_go_out(app, client, login_as, make_user, fake_clock):
    csrf = login_as("user", email="stay@goodmit.co.kr")
    gone = make_user(email="gone@goodmit.co.kr", display_name="퇴근함")
    rid = _direct(client, csrf, gone.id)

    other = _login_other(app, "gone@goodmit.co.kr")
    with other:
        other.get(f"/api/team-chat/rooms/{rid}/messages?since=0")
        assert _online(client, rid, gone.id) is True, "방을 연 사람이 접속 중이 아니다"

        # 모니터만 끄고 갔다. 탭은 살아서 폴링이 계속 오지만 사람은 없다.
        for _ in range(6):
            fake_clock.advance(30)
            r = other.get(f"/api/team-chat/rooms/{rid}/messages?since=0&idle=1")
            assert r.status_code == 200, r.text

    # 폴링이 여섯 번 더 왔지만(3분) 점은 꺼져 있어야 한다.
    assert _online(client, rid, gone.id) is False, (
        "탭만 열어 둔 사람이 여전히 '접속 중' 이다 — 폴링을 존재로 세고 있다"
    )


def test_a_present_person_never_goes_out(app, client, login_as, make_user, fake_clock):
    """반대 방향. 자리에 있는 사람은 절대 꺼지면 안 된다 — 이쪽 오탐이 더 나쁘다."""
    csrf = login_as("user", email="stay2@goodmit.co.kr")
    here = make_user(email="here@goodmit.co.kr", display_name="자리에있음")
    rid = _direct(client, csrf, here.id)

    other = _login_other(app, "here@goodmit.co.kr")
    with other:
        for _ in range(6):
            fake_clock.advance(30)
            other.get(f"/api/team-chat/rooms/{rid}/messages?since=0")
        assert _online(client, rid, here.id) is True


def test_returning_lights_the_dot_back_up(app, client, login_as, make_user, fake_clock):
    csrf = login_as("user", email="stay3@goodmit.co.kr")
    back = make_user(email="back@goodmit.co.kr", display_name="돌아옴")
    rid = _direct(client, csrf, back.id)

    other = _login_other(app, "back@goodmit.co.kr")
    with other:
        other.get(f"/api/team-chat/rooms/{rid}/messages?since=0")
        # 밤새 자리를 비웠다.
        fake_clock.advance(ONLINE_SECONDS * 10)
        other.get(f"/api/team-chat/rooms/{rid}/messages?since=0&idle=1")
        assert _online(client, rid, back.id) is False

        # 아침에 마우스를 한 번 움직였다 → 브라우저가 idle 을 떼고 보낸다.
        fake_clock.advance(1)
        other.get(f"/api/team-chat/rooms/{rid}/messages?since=0")

    assert _online(client, rid, back.id) is True, (
        "돌아온 사람이 바로 안 보이면 유휴 감지가 기능 저하가 된다"
    )


def test_idle_does_not_change_what_the_response_contains(app, client, login_as, make_user):
    """`idle` 은 접속 표시에만 쓴다 — 응답 내용이나 권한을 바꾸면 그건 다른 종류의 결함이다."""
    csrf = login_as("user", email="same@goodmit.co.kr")
    peer = make_user(email="same-peer@goodmit.co.kr")
    rid = _direct(client, csrf, peer.id)
    client.post(
        f"/api/team-chat/rooms/{rid}/messages",
        json={"body": "안녕하세요", "client_message_id": "c1"},
        headers={"X-CSRF-Token": csrf},
    )

    plain = client.get(f"/api/team-chat/rooms/{rid}/messages?since=0").json()
    idle = client.get(f"/api/team-chat/rooms/{rid}/messages?since=0&idle=1").json()
    assert [m["body"] for m in plain["messages"]] == [m["body"] for m in idle["messages"]]
    assert plain["room"]["id"] == idle["room"]["id"]


def test_idle_does_not_open_a_room_you_cannot_see(app, client, login_as, make_user):
    """범위 밖은 404 다 — `idle` 을 붙였다고 그 판정이 흔들리면 안 된다."""
    owner_csrf = login_as("user", email="owner@goodmit.co.kr")
    peer = make_user(email="peer@goodmit.co.kr")
    rid = _direct(client, owner_csrf, peer.id)

    make_user(email="stranger@goodmit.co.kr")
    other = _login_other(app, "stranger@goodmit.co.kr")
    with other:
        r = other.get(f"/api/team-chat/rooms/{rid}/messages?since=0&idle=1")
        assert r.status_code in (403, 404), r.text
