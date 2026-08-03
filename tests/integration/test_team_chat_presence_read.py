"""온라인 점 + 1:1 읽음 표시 (PLAN Phase 3 §F).

두 기능이 한 파일에 있는 이유: 둘 다 **참여자 행의 값을 화면에 그대로 내보내는** 일이고,
둘 다 조용히 거짓말하기 쉽다.

  * 온라인 점 — 임계값을 presence 쓰기 스로틀(30초)에 가깝게 잡으면, 실제로 붙어 있는 사람이
    '아직 갱신 안 된' 구간마다 오프라인으로 깜빡인다. 그래서 **2분 이상**으로 못박는다.
  * 읽음 표시 — 1:1 '나에게만 숨김'은 커서의 `last_read_seq` 에 그 시점 event_seq 를 박는다.
    읽음 위치를 '멤버 행과 커서 중 큰 값'으로 계산하면 **상대가 대화를 숨겼을 뿐인데 읽음으로
    표시된다**. 읽지 않은 것을 읽었다고 말하는 순간 이 표시 전체가 못 믿을 값이 된다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.presence import PRESENCE_THROTTLE_SECONDS
from app.team_chat.service import MIN_ONLINE_SECONDS, ONLINE_SECONDS
from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration


def _login_other(app, email):
    c = TestClient(app, raise_server_exceptions=False)
    c.post("/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD})
    return c, c.get("/api/me").json()["csrf_token"]


def _meta(client, rid):
    r = client.get(f"/api/team-chat/rooms/{rid}/messages?since=0")
    assert r.status_code == 200, r.text
    return r.json()


def _member(client, rid, user_id):
    return next(m for m in _meta(client, rid)["members"] if m["user_id"] == user_id)


def _direct(client, csrf, other_id):
    return client.post("/api/team-chat/rooms/direct", json={"user_id": other_id},
                       headers={"X-CSRF-Token": csrf}).json()["room"]["id"]


# ── 1. 임계값 자체 ─────────────────────────────────────────────────────────

def test_online_threshold_is_at_least_two_minutes_and_well_above_the_write_throttle():
    """presence 스로틀이 30초다 — 임계값을 그보다 짧게 잡으면 접속해 있는 사람이 깜빡인다.
    이 두 값은 **함께** 봐야 한다(app/core/presence.py 의 긴 주석이 그 이야기다)."""
    assert ONLINE_SECONDS >= 120.0
    assert ONLINE_SECONDS >= MIN_ONLINE_SECONDS == PRESENCE_THROTTLE_SECONDS * 2


# ── 2. 온라인 점 ────────────────────────────────────────────────────────────

def test_a_member_who_just_opened_the_room_is_online(app, client, login_as, make_user):
    csrf = login_as("user", email="on1@goodmit.co.kr")
    u2 = make_user(email="on2@goodmit.co.kr", display_name="접속중")
    rid = _direct(client, csrf, u2.id)
    c2, _ = _login_other(app, "on2@goodmit.co.kr")
    with c2:
        c2.get(f"/api/team-chat/rooms/{rid}/messages?since=0")  # 상대가 방을 연다
    assert _member(client, rid, u2.id)["online"] is True


def test_a_member_who_polls_within_the_throttle_window_never_flickers(
    app, client, login_as, make_user, fake_clock
):
    """실제로 붙어 있는 사람은 오프라인으로 깜빡이면 안 된다.

    스로틀 때문에 `last_seen` 은 최대 30초 가까이 낡을 수 있다. 임계값이 그와 비슷하면
    바로 그 구간에서 꺼진다 — 여기서 그 구간(59초 낡음)을 만들어 놓고 여전히 온라인인지 본다.
    """
    csrf = login_as("user", email="fl1@goodmit.co.kr")
    u2 = make_user(email="fl2@goodmit.co.kr", display_name="계속접속")
    rid = _direct(client, csrf, u2.id)
    c2, _ = _login_other(app, "fl2@goodmit.co.kr")
    with c2:
        c2.get(f"/api/team-chat/rooms/{rid}/messages?since=0")
        fake_clock.advance(59)
        c2.get(f"/api/team-chat/rooms/{rid}/messages?since=0")  # 스로틀 통과 → last_seen 갱신
        stale = 59.0
        fake_clock.advance(stale)  # 그 뒤로 59초 동안 아무 갱신 없음(폴링은 계속 중)
    assert stale > PRESENCE_THROTTLE_SECONDS, "스로틀보다 낡은 상태를 만들어야 의미가 있는 검사다"
    assert _member(client, rid, u2.id)["online"] is True


def test_someone_just_invited_is_not_shown_as_watching(client, login_as, make_user):
    """멤버 행은 `last_seen = joined_at` 으로 만들어진다 — 그 값을 그대로 믿으면 방금 초대된
    사람이 **초대된 줄도 모르는 채로** 2분 동안 '보는 중'으로 켜져 있다(실제로 그랬다)."""
    csrf = login_as("user", email="jn1@goodmit.co.kr")
    u2 = make_user(email="jn2@goodmit.co.kr", display_name="방금초대")
    rid = client.post("/api/team-chat/rooms", json={"title": "초대방", "member_user_ids": [u2.id]},
                      headers={"X-CSRF-Token": csrf}).json()["room"]["id"]
    assert _member(client, rid, u2.id)["online"] is False


def test_a_member_who_left_the_screen_goes_offline(app, client, login_as, make_user, fake_clock):
    csrf = login_as("user", email="of1@goodmit.co.kr")
    u2 = make_user(email="of2@goodmit.co.kr", display_name="나간사람")
    rid = _direct(client, csrf, u2.id)
    c2, _ = _login_other(app, "of2@goodmit.co.kr")
    with c2:
        c2.get(f"/api/team-chat/rooms/{rid}/messages?since=0")
    fake_clock.advance(ONLINE_SECONDS + 1)
    assert _member(client, rid, u2.id)["online"] is False


# ── 3. 1:1 읽음 표시 ────────────────────────────────────────────────────────

def test_peer_read_position_rises_only_when_they_actually_read(app, client, login_as, make_user):
    csrf = login_as("user", email="rr1@goodmit.co.kr")
    u2 = make_user(email="rr2@goodmit.co.kr", display_name="읽는이")
    rid = _direct(client, csrf, u2.id)
    seq = client.post(f"/api/team-chat/rooms/{rid}/messages", json={"body": "봤어?"},
                      headers={"X-CSRF-Token": csrf}).json()["seq"]

    # 아직 안 읽음.
    assert _member(client, rid, u2.id)["last_read_seq"] < seq

    c2, cs2 = _login_other(app, "rr2@goodmit.co.kr")
    with c2:
        c2.get(f"/api/team-chat/rooms/{rid}/messages?since=0")
        c2.post(f"/api/team-chat/rooms/{rid}/read", json={"seq": seq}, headers={"X-CSRF-Token": cs2})

    assert _member(client, rid, u2.id)["last_read_seq"] >= seq


def test_hiding_the_conversation_does_not_count_as_reading_it(app, client, login_as, make_user):
    """'나에게만 숨김'은 커서에 event_seq 를 박는다 — 그것을 읽음으로 읽으면 거짓말이 된다."""
    csrf = login_as("user", email="hr1@goodmit.co.kr")
    u2 = make_user(email="hr2@goodmit.co.kr", display_name="숨긴이")
    rid = _direct(client, csrf, u2.id)
    seq = client.post(f"/api/team-chat/rooms/{rid}/messages", json={"body": "읽어줘"},
                      headers={"X-CSRF-Token": csrf}).json()["seq"]

    c2, cs2 = _login_other(app, "hr2@goodmit.co.kr")
    with c2:
        r = c2.post(f"/api/team-chat/rooms/{rid}/hide", headers={"X-CSRF-Token": cs2})
        assert r.status_code == 200, r.text

    assert _member(client, rid, u2.id)["last_read_seq"] < seq, "숨김이 읽음으로 둔갑하면 안 된다"


def test_read_positions_are_only_visible_to_room_members(app, client, login_as, make_user):
    csrf = login_as("user", email="rv1@goodmit.co.kr")
    u2 = make_user(email="rv2@goodmit.co.kr", display_name="알브이투")
    rid = _direct(client, csrf, u2.id)
    make_user(email="rv3@goodmit.co.kr", display_name="바깥사람")
    c3, _ = _login_other(app, "rv3@goodmit.co.kr")
    with c3:
        assert c3.get(f"/api/team-chat/rooms/{rid}/messages?since=0").status_code == 403


def test_global_room_has_no_member_rows_so_no_dots_or_receipts(client, login_as):
    """전체 채팅은 멤버십이 없다 — 점도 읽음 표시도 그릴 대상이 없다(빈 배열이 정답)."""
    login_as("user", email="gm1@goodmit.co.kr")
    gid = client.get("/api/team-chat/rooms").json()["global"]["id"]
    assert _meta(client, gid)["members"] == []
