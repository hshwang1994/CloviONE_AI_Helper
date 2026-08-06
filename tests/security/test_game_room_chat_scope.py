"""놀이방 **대화**는 방 안 사람에게만 (1순위 유출 #10 정정).

## 계획서의 설명을 정정한다 (PLAN10)

계획서는 "`GET /api/games/rooms/{id}/state` 가 **멤버십 검사 없이** 방 상태·멤버·채팅을
내준다" 고 적었다. 코드를 읽어 보니 절반은 **설계**다:

  * 응답에 `you.in_room` 이 있고 `join(spectate=...)` 이 따로 있다 — **비멤버가 방을 미리
    보고 들어갈지 정하는 로비**가 의도된 동작이다. 그걸 막으면 방 목록에서 아무것도 못 보고
    무작정 들어가야 한다.
  * `touch_presence()` 는 **이미 `if member is None: return`** 으로 막혀 있다 — 엿본 사람이
    접속자로 뜨는 일은 없다(그 걱정은 근거가 없었다).

**진짜 남은 것은 대화다.** `events` 에 `EV_CHAT` 이 섞여 있어 방 안에서 오간 말이 밖으로
나간다. 로비에서 "무슨 게임이 몇 명으로 돌아가는지" 를 보는 것과 "그 사람들이 무슨 말을
했는지" 를 읽는 것은 다른 일이다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.security


def _make_room(client, csrf):
    r = client.post("/api/games/rooms", json={"game_type": "quick_vote", "title": "테스트 방"},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code in (200, 201), r.text
    return r.json()["room"]["id"]


def _say(client, csrf, room_id, text):
    r = client.post(f"/api/games/rooms/{room_id}/chat", json={"text": text},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text


def _kinds(client, room_id):
    body = client.get(f"/api/games/rooms/{room_id}/state").json()
    return [e["kind"] for e in body.get("events", [])], body


def test_a_member_reads_the_room_chat(client, login_as, make_user):
    csrf = login_as("user", email="gm-host@goodmit.co.kr")
    room_id = _make_room(client, csrf)
    _say(client, csrf, room_id, "안에서 한 말")

    kinds, body = _kinds(client, room_id)
    assert "chat" in kinds, f"방 안 사람이 대화를 못 읽는다: {kinds}"
    assert body["you"]["in_room"] is True


def test_an_outsider_sees_the_room_but_not_the_chat(client, login_as, make_user):
    csrf = login_as("user", email="gm-host2@goodmit.co.kr")
    room_id = _make_room(client, csrf)
    _say(client, csrf, room_id, "안에서 한 말")

    login_as("user", email="gm-peek@goodmit.co.kr")
    kinds, body = _kinds(client, room_id)

    # 로비 미리보기는 설계다 — 방 자체는 보여야 한다.
    assert body["room"]["id"] == room_id
    assert body["you"]["in_room"] is False
    assert "chat" not in kinds, f"밖에서 방 안 대화를 읽는다: {kinds}"
