"""팀 채팅 완성도(PLAN §D) — 전체 채팅 안읽음 커서, 방 파하기, 1:1 숨김, 초대 알림.

이미지 업로드/서빙의 접근 통제는 tests/security/test_team_chat_images.py 가 지킨다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.team_chat.models import ChatReadCursor
from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration


def _login_other(app, email):
    c = TestClient(app, raise_server_exceptions=False)
    c.post("/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD})
    return c, c.get("/api/me").json()["csrf_token"]


def _cursors(db, user_id):
    db.expire_all()
    return list(
        db.execute(select(ChatReadCursor).where(ChatReadCursor.user_id == user_id)).scalars().all()
    )


# ── 1. 전체 채팅 방 안읽음 ──────────────────────────────────────────────────

def test_global_room_unread_rises_and_clears(app, client, login_as, make_user):
    """전체 채팅 방은 멤버십 행이 없어 예전엔 unread 가 항상 0이었다 — 이제 개인 커서로 센다."""
    csrf = login_as("user", email="gu1@goodmit.co.kr")
    gid = client.get("/api/team-chat/rooms").json()["global"]["id"]
    # 시작 상태를 확정한다(시드 방의 event_seq 가 0이 아닐 수도 있다).
    start_seq = client.get("/api/team-chat/rooms").json()["global"]["seq"]
    client.post(f"/api/team-chat/rooms/{gid}/read", json={"seq": start_seq},
                headers={"X-CSRF-Token": csrf})
    assert client.get("/api/team-chat/rooms").json()["global"]["unread"] == 0

    # 다른 사람이 전체 채팅에 두 개 보낸다.
    make_user("gu2@goodmit.co.kr")
    c2, cs2 = _login_other(app, "gu2@goodmit.co.kr")
    with c2:
        c2.post(f"/api/team-chat/rooms/{gid}/messages", json={"body": "하나"}, headers={"X-CSRF-Token": cs2})
        c2.post(f"/api/team-chat/rooms/{gid}/messages", json={"body": "둘"}, headers={"X-CSRF-Token": cs2})

    body = client.get("/api/team-chat/rooms").json()
    assert body["global"]["unread"] == 2
    # 사이드바 합계 배지용 값도 같은 응답에 실린다(새 폴링을 만들지 않는다).
    assert body["unread_total"] >= 2

    # 읽으면 0으로 내려간다.
    client.post(f"/api/team-chat/rooms/{gid}/read", json={"seq": body["global"]["seq"]},
                headers={"X-CSRF-Token": csrf})
    assert client.get("/api/team-chat/rooms").json()["global"]["unread"] == 0


def test_global_room_read_does_not_create_membership_rows(app, client, login_as):
    """전체 채팅을 읽어도 ChatRoomMember 를 만들지 않는다 —
    만들면 member_count 의 뜻이 '멤버 수'에서 '한 번이라도 연 사람 수'로 바뀐다."""
    csrf = login_as("user", email="gnm@goodmit.co.kr")
    gid = client.get("/api/team-chat/rooms").json()["global"]["id"]
    client.post(f"/api/team-chat/rooms/{gid}/messages", json={"body": "hi"}, headers={"X-CSRF-Token": csrf})
    seq = client.get("/api/team-chat/rooms").json()["global"]["seq"]
    client.post(f"/api/team-chat/rooms/{gid}/read", json={"seq": seq}, headers={"X-CSRF-Token": csrf})
    summary = client.get("/api/team-chat/rooms").json()["global"]
    assert summary["member_count"] == 0


def test_poll_that_reads_nothing_new_does_not_write_the_cursor(app, client, login_as, db, make_user):
    """폴링은 커서를 쓰지 않는다. 같은 seq 로 읽음을 반복해도 UPDATE 가 나가지 않는다.

    이 앱에서 가장 뜨거운 경로가 쓰기다 — 전체 채팅 위젯이 모든 홈 방문에서 초 단위로 돈다.
    """
    me = make_user("poll1@goodmit.co.kr", display_name="폴러")
    csrf = login_as("user", email="poll1@goodmit.co.kr")
    gid = client.get("/api/team-chat/rooms").json()["global"]["id"]

    # 폴링만 여러 번 — 커서 행이 생기면 안 된다.
    for _ in range(3):
        assert client.get(f"/api/team-chat/rooms/{gid}/messages?since=0").status_code == 200
    assert _cursors(db, me.id) == []

    # 읽을 게 없는 상태에서의 읽음(seq=0)도 빈 행을 만들지 않는다.
    client.post(f"/api/team-chat/rooms/{gid}/read", json={"seq": 0}, headers={"X-CSRF-Token": csrf})
    assert _cursors(db, me.id) == []

    # 실제로 읽을 게 생겨 읽으면 그때 한 행이 생긴다.
    client.post(f"/api/team-chat/rooms/{gid}/messages", json={"body": "새 글"}, headers={"X-CSRF-Token": csrf})
    seq = client.get("/api/team-chat/rooms").json()["global"]["seq"]
    client.post(f"/api/team-chat/rooms/{gid}/read", json={"seq": seq}, headers={"X-CSRF-Token": csrf})
    rows = _cursors(db, me.id)
    assert len(rows) == 1 and rows[0].last_read_seq == seq
    stamped = rows[0].updated_at

    # 같은 seq 로 다시 읽음(프런트가 방을 열어 둔 채 폴링) → 아무것도 쓰지 않는다.
    for _ in range(3):
        client.get(f"/api/team-chat/rooms/{gid}/messages?since={seq}")
        client.post(f"/api/team-chat/rooms/{gid}/read", json={"seq": seq}, headers={"X-CSRF-Token": csrf})
    rows2 = _cursors(db, me.id)
    assert len(rows2) == 1 and rows2[0].updated_at == stamped


# ── 2. 방 파하기(disband) ───────────────────────────────────────────────────

def test_disband_group_removes_it_for_everyone(app, client, login_as, make_user):
    csrf = login_as("user", email="db1@goodmit.co.kr")
    u2 = make_user(email="db2@goodmit.co.kr", display_name="디비투")
    rid = client.post("/api/team-chat/rooms", json={"title": "파할방", "member_user_ids": [u2.id]},
                      headers={"X-CSRF-Token": csrf}).json()["room"]["id"]
    # 파하기 전에 시스템 메시지가 남는지 볼 수 있게 방을 한 번 연다.
    assert client.get(f"/api/team-chat/rooms/{rid}/messages?since=0").status_code == 200

    r = client.post(f"/api/team-chat/rooms/{rid}/disband", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    # 방장 목록에서 사라진다.
    assert all(x["id"] != rid for x in client.get("/api/team-chat/rooms").json()["items"])
    # 방 자체가 더는 열리지 않는다(404).
    assert client.get(f"/api/team-chat/rooms/{rid}/messages?since=0").status_code == 404
    # 다른 멤버에게서도 사라진다.
    c2, _ = _login_other(app, "db2@goodmit.co.kr")
    with c2:
        assert all(x["id"] != rid for x in c2.get("/api/team-chat/rooms").json()["items"])


def test_disband_is_owner_only(app, client, login_as, make_user):
    csrf = login_as("user", email="do1@goodmit.co.kr")
    u2 = make_user(email="do2@goodmit.co.kr", display_name="디오투")
    rid = client.post("/api/team-chat/rooms", json={"title": "방장전용", "member_user_ids": [u2.id]},
                      headers={"X-CSRF-Token": csrf}).json()["room"]["id"]
    c2, cs2 = _login_other(app, "do2@goodmit.co.kr")
    with c2:
        assert c2.post(f"/api/team-chat/rooms/{rid}/disband", headers={"X-CSRF-Token": cs2}).status_code == 403
    # 비멤버는 아예 접근 불가.
    make_user("do3@goodmit.co.kr")
    c3, cs3 = _login_other(app, "do3@goodmit.co.kr")
    with c3:
        assert c3.post(f"/api/team-chat/rooms/{rid}/disband", headers={"X-CSRF-Token": cs3}).status_code == 403


def test_disband_global_room_is_409(client, login_as):
    csrf = login_as("user", email="dg1@goodmit.co.kr")
    gid = client.get("/api/team-chat/rooms").json()["global"]["id"]
    r = client.post(f"/api/team-chat/rooms/{gid}/disband", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 409, r.text
    # 여전히 살아 있다.
    assert client.get("/api/team-chat/rooms").json()["global"]["id"] == gid


def test_disband_direct_room_is_409(client, login_as, make_user):
    """1:1 을 soft-delete 하면 dm_key(unique)가 남아 같은 상대와 다시 대화를 시작할 때
    INSERT → IntegrityError → 재조회도 None → **500**이 된다. 409 로 막고 숨기기로 보낸다."""
    csrf = login_as("user", email="dd1@goodmit.co.kr")
    u2 = make_user(email="dd2@goodmit.co.kr", display_name="디디투")
    rid = client.post("/api/team-chat/rooms/direct", json={"user_id": u2.id},
                      headers={"X-CSRF-Token": csrf}).json()["room"]["id"]
    r = client.post(f"/api/team-chat/rooms/{rid}/disband", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 409, r.text
    # 방은 그대로 살아 있고, 다시 열어도 200(500이 아니다).
    again = client.post("/api/team-chat/rooms/direct", json={"user_id": u2.id},
                        headers={"X-CSRF-Token": csrf})
    assert again.status_code == 200 and again.json()["room"]["id"] == rid


# ── 3. 1:1 '나에게만 숨김' ──────────────────────────────────────────────────

def test_direct_hide_then_reopen_returns_200_and_room_is_back(app, client, login_as, make_user):
    csrf = login_as("user", email="hd1@goodmit.co.kr")
    u2 = make_user(email="hd2@goodmit.co.kr", display_name="숨김투")
    rid = client.post("/api/team-chat/rooms/direct", json={"user_id": u2.id},
                      headers={"X-CSRF-Token": csrf}).json()["room"]["id"]
    assert any(x["id"] == rid for x in client.get("/api/team-chat/rooms").json()["items"])

    assert client.post(f"/api/team-chat/rooms/{rid}/hide", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert all(x["id"] != rid for x in client.get("/api/team-chat/rooms").json()["items"])
    # 상대 목록에는 그대로 있다(내게만 숨김).
    c2, _ = _login_other(app, "hd2@goodmit.co.kr")
    with c2:
        assert any(x["id"] == rid for x in c2.get("/api/team-chat/rooms").json()["items"])

    # 다시 대화 시작 → 200 + 같은 방 + 목록 복귀.
    again = client.post("/api/team-chat/rooms/direct", json={"user_id": u2.id},
                        headers={"X-CSRF-Token": csrf})
    assert again.status_code == 200 and again.json()["room"]["id"] == rid
    assert any(x["id"] == rid for x in client.get("/api/team-chat/rooms").json()["items"])


def test_hidden_direct_reappears_when_a_new_message_arrives(app, client, login_as, make_user):
    """숨김은 '그때까지의 대화'에만 걸린다 — 상대가 말을 걸면 다시 보여야 한다."""
    csrf = login_as("user", email="hr1@goodmit.co.kr")
    u2 = make_user(email="hr2@goodmit.co.kr", display_name="복귀투")
    rid = client.post("/api/team-chat/rooms/direct", json={"user_id": u2.id},
                      headers={"X-CSRF-Token": csrf}).json()["room"]["id"]
    client.post(f"/api/team-chat/rooms/{rid}/hide", headers={"X-CSRF-Token": csrf})
    assert all(x["id"] != rid for x in client.get("/api/team-chat/rooms").json()["items"])

    c2, cs2 = _login_other(app, "hr2@goodmit.co.kr")
    with c2:
        c2.post(f"/api/team-chat/rooms/{rid}/messages", json={"body": "안 자?"}, headers={"X-CSRF-Token": cs2})
    rooms = client.get("/api/team-chat/rooms").json()["items"]
    row = next((x for x in rooms if x["id"] == rid), None)
    assert row is not None and row["unread"] >= 1


def test_hiding_the_global_room_is_409(client, login_as):
    csrf = login_as("user", email="hg1@goodmit.co.kr")
    gid = client.get("/api/team-chat/rooms").json()["global"]["id"]
    assert client.post(f"/api/team-chat/rooms/{gid}/hide", headers={"X-CSRF-Token": csrf}).status_code == 409


# ── 4. 초대 알림 + 딥링크 ───────────────────────────────────────────────────

def test_group_create_notifies_invited_members_only(app, client, login_as, make_user):
    csrf = login_as("user", email="ni1@goodmit.co.kr", )
    u2 = make_user(email="ni2@goodmit.co.kr", display_name="초대받은이")
    rid = client.post("/api/team-chat/rooms", json={"title": "초대방", "member_user_ids": [u2.id]},
                      headers={"X-CSRF-Token": csrf}).json()["room"]["id"]

    # 만든 사람은 자기 방 알림을 받지 않는다.
    mine = client.get("/api/notifications?type=chat_invited").json()["items"]
    assert mine == []

    c2, _ = _login_other(app, "ni2@goodmit.co.kr")
    with c2:
        items = c2.get("/api/notifications?type=chat_invited").json()["items"]
        assert len(items) == 1
        n = items[0]
        assert n["related_object_type"] == "chat_room" and n["related_object_id"] == rid
        # 딥링크 목적지는 서버(app/notifications/destinations.py)가 계산해 준다.
        assert n["related_route"] == f"/chat-rooms/{rid}"


def test_direct_start_notifies_the_other_person_once(app, client, login_as, make_user):
    csrf = login_as("user", email="nd1@goodmit.co.kr")
    u2 = make_user(email="nd2@goodmit.co.kr", display_name="디엠상대")
    rid = client.post("/api/team-chat/rooms/direct", json={"user_id": u2.id},
                      headers={"X-CSRF-Token": csrf}).json()["room"]["id"]
    # 이미 있는 방을 다시 열어도 알림이 또 가지 않는다(중복 알림 방지).
    client.post("/api/team-chat/rooms/direct", json={"user_id": u2.id}, headers={"X-CSRF-Token": csrf})

    c2, _ = _login_other(app, "nd2@goodmit.co.kr")
    with c2:
        items = c2.get("/api/notifications?type=chat_invited").json()["items"]
        assert len(items) == 1
        assert items[0]["related_route"] == f"/chat-rooms/{rid}"


def test_notifications_without_a_destination_have_no_route(client, login_as):
    """목적지 표에 없는 유형은 related_route 가 null 이다 — 없는 화면으로 보내지 않는다."""
    login_as("admin", email="nr1@goodmit.co.kr")
    body = client.get("/api/notifications").json()
    for item in body["items"]:
        if item["related_object_type"] != "chat_room":
            assert item["related_route"] is None
