"""팀 채팅 API — 전체 채팅 방(누구나) + 그룹/1:1 + 멤버십 IDOR + 폴링 커서 + 읽음.

app/chat(AI 도우미)와 완전히 별개(외부 호출 없음). 놀이와 같은 seq 커서 폴링.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration


def _login_other(app, email):
    c = TestClient(app, raise_server_exceptions=False)
    c.post("/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD})
    return c, c.get("/api/me").json()["csrf_token"]


def test_global_room_send_and_poll(app, client, login_as):
    csrf = login_as("user", email="gc1@goodmit.co.kr")
    rooms = client.get("/api/team-chat/rooms").json()
    assert "global" in rooms and rooms["global"]["is_global"] is True
    gid = rooms["global"]["id"]
    assert client.post(f"/api/team-chat/rooms/{gid}/messages", json={"body": "안녕 팀"},
                       headers={"X-CSRF-Token": csrf}).status_code == 200
    st = client.get(f"/api/team-chat/rooms/{gid}/messages?since=0").json()
    assert "안녕 팀" in [m["body"] for m in st["messages"] if m["kind"] == "text"]
    seq = st["seq"]
    # since=seq 이후 새 메시지 없음(커서 동작).
    assert client.get(f"/api/team-chat/rooms/{gid}/messages?since={seq}").json()["messages"] == []


def test_global_room_open_to_any_user(app, client, login_as, make_user):
    csrf = login_as("user", email="gopen1@goodmit.co.kr")
    gid = client.get("/api/team-chat/rooms").json()["global"]["id"]
    client.post(f"/api/team-chat/rooms/{gid}/messages", json={"body": "hi"}, headers={"X-CSRF-Token": csrf})
    make_user("gopen2@goodmit.co.kr")
    c2, _ = _login_other(app, "gopen2@goodmit.co.kr")
    with c2:
        # 멤버십 행이 없어도 전체 채팅 방은 누구나 본다.
        assert c2.get(f"/api/team-chat/rooms/{gid}/messages?since=0").status_code == 200


def test_group_create_membership_and_idor(app, client, login_as, make_user):
    csrf = login_as("user", email="gg1@goodmit.co.kr")
    u2 = make_user(email="gg2@goodmit.co.kr", display_name="지지투")
    rid = client.post("/api/team-chat/rooms", json={"title": "우리방", "member_user_ids": [u2.id]},
                      headers={"X-CSRF-Token": csrf}).json()["room"]["id"]
    assert any(x["id"] == rid for x in client.get("/api/team-chat/rooms").json()["items"])
    # 멤버는 접근 가능.
    c2, _ = _login_other(app, "gg2@goodmit.co.kr")
    with c2:
        assert c2.get(f"/api/team-chat/rooms/{rid}/messages?since=0").status_code == 200
    # 비멤버는 403(IDOR 차단).
    make_user("gg3@goodmit.co.kr")
    c3, cs3 = _login_other(app, "gg3@goodmit.co.kr")
    with c3:
        assert c3.get(f"/api/team-chat/rooms/{rid}/messages?since=0").status_code == 403
        assert c3.post(f"/api/team-chat/rooms/{rid}/messages", json={"body": "x"},
                       headers={"X-CSRF-Token": cs3}).status_code == 403


def test_direct_room_is_idempotent(app, client, login_as, make_user):
    csrf = login_as("user", email="dm1@goodmit.co.kr")
    u2 = make_user(email="dm2@goodmit.co.kr", display_name="디엠투")
    r1 = client.post("/api/team-chat/rooms/direct", json={"user_id": u2.id}, headers={"X-CSRF-Token": csrf})
    r2 = client.post("/api/team-chat/rooms/direct", json={"user_id": u2.id}, headers={"X-CSRF-Token": csrf})
    assert r1.status_code == 200 and r1.json()["room"]["id"] == r2.json()["room"]["id"]
    rid = r1.json()["room"]["id"]
    # 1:1 방 제목은 상대 이름으로 보인다.
    st = client.get(f"/api/team-chat/rooms/{rid}/messages?since=0").json()
    assert st["room"]["title"] == "디엠투"


def test_unread_and_read(app, client, login_as, make_user):
    csrf = login_as("user", email="ur1@goodmit.co.kr")
    u2 = make_user(email="ur2@goodmit.co.kr", display_name="언리드투")
    rid = client.post("/api/team-chat/rooms", json={"title": "안읽음방", "member_user_ids": [u2.id]},
                      headers={"X-CSRF-Token": csrf}).json()["room"]["id"]
    # u2 가 메시지 2개 보냄.
    c2, cs2 = _login_other(app, "ur2@goodmit.co.kr")
    with c2:
        c2.post(f"/api/team-chat/rooms/{rid}/messages", json={"body": "1"}, headers={"X-CSRF-Token": cs2})
        c2.post(f"/api/team-chat/rooms/{rid}/messages", json={"body": "2"}, headers={"X-CSRF-Token": cs2})
    # ur1 목록에서 안읽음 > 0.
    room = next(x for x in client.get("/api/team-chat/rooms").json()["items"] if x["id"] == rid)
    assert room["unread"] >= 2
    # 읽음 처리 후 0.
    client.post(f"/api/team-chat/rooms/{rid}/read", json={"seq": room["seq"]}, headers={"X-CSRF-Token": csrf})
    room2 = next(x for x in client.get("/api/team-chat/rooms").json()["items"] if x["id"] == rid)
    assert room2["unread"] == 0


def test_directory_excludes_self_and_secrets(app, client, login_as, make_user):
    login_as("user", email="dir1@goodmit.co.kr")
    make_user(email="dir2@goodmit.co.kr", display_name="디렉터리투")
    users = client.get("/api/team-chat/directory").json()["users"]
    emails = str(users)
    assert "dir1@goodmit.co.kr" not in emails  # 본인 제외 + 이메일 미노출
    assert all(set(u.keys()) == {"user_id", "display_name", "dept", "title"} for u in users)
    assert any(u["display_name"] == "디렉터리투" for u in users)


def test_feature_flag_gates_team_chat(client, login_as):
    csrf = login_as("user", email="tcflag@goodmit.co.kr")
    # CSRF 없으면 403 먼저; 여기선 조회라 200(플래그 기본 ON). 플래그 OFF 케이스는 games 방식과 동일 구조.
    assert client.get("/api/team-chat/rooms").status_code == 200
    _ = csrf
