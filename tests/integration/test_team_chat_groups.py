"""그룹 관리 — 이름 변경 · 초대 · 내보내기 · 방장 넘기기 (PLAN Phase 3 §F).

**정한 방장 권한 규칙**(여기가 그 규칙의 정본이다):

  1. 네 동작 모두 **그룹 방의 방장만**. 전체 채팅과 1:1 은 409 — 권한 문제가 아니라 그 방에는
     없는 개념이다(전체 채팅은 멤버십 자체가 없고, 1:1 은 멤버가 정의상 둘이며 제목이 보는
     사람마다 상대 이름으로 계산된다).
  2. **방장 자리는 항상 정확히 한 명.** 그래서 '방장 내려놓기'는 없고 `owner`(넘기기)만 있다.
  3. **방장은 자기를 내보낼 수 없다**(409). 그 경로를 열면 주인 없는 방이 생긴다 — 남은
     사람은 이름 변경도 초대도 파하기도 못 한다.
  4. **방장이 나가면 자동 승계**한다(가장 먼저 들어온 남은 멤버). 남은 사람이 없으면 방을
     파한다. 이 두 갈래가 "방이 주인 없이 남으면 안 된다"를 실제로 보장하는 곳이다.
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


def _group(client, csrf, title="원래이름", members=()):
    r = client.post("/api/team-chat/rooms", json={"title": title, "member_user_ids": list(members)},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    return r.json()["room"]["id"]


def _meta(client, rid):
    r = client.get(f"/api/team-chat/rooms/{rid}/messages?since=0")
    assert r.status_code == 200, r.text
    return r.json()


def _roles(client, rid):
    return {m["user_id"]: m["role"] for m in _meta(client, rid)["members"]}


# ── 1. 이름 변경 ────────────────────────────────────────────────────────────

def test_owner_renames_and_everyone_sees_it(app, client, login_as, make_user):
    csrf = login_as("user", email="gr1@goodmit.co.kr")
    u2 = make_user(email="gr2@goodmit.co.kr", display_name="지알투")
    rid = _group(client, csrf, "옛이름", [u2.id])

    r = client.post(f"/api/team-chat/rooms/{rid}/rename", json={"title": "새이름"},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    assert _meta(client, rid)["room"]["title"] == "새이름"
    # 바뀐 사실이 로그에 남는다 — 어느 날 방 이름이 달라져 있으면 누가 바꿨는지 알 수 있어야 한다.
    assert any("새이름" in m["body"] for m in _meta(client, rid)["messages"] if m["kind"] == "system")
    c2, _ = _login_other(app, "gr2@goodmit.co.kr")
    with c2:
        assert next(x for x in c2.get("/api/team-chat/rooms").json()["items"] if x["id"] == rid)["title"] == "새이름"


def test_rename_is_owner_only(app, client, login_as, make_user):
    csrf = login_as("user", email="ro1@goodmit.co.kr")
    u2 = make_user(email="ro2@goodmit.co.kr", display_name="알오투")
    rid = _group(client, csrf, "그대로", [u2.id])
    c2, cs2 = _login_other(app, "ro2@goodmit.co.kr")
    with c2:
        r = c2.post(f"/api/team-chat/rooms/{rid}/rename", json={"title": "내맘대로"},
                    headers={"X-CSRF-Token": cs2})
        assert r.status_code == 403, r.text
    assert _meta(client, rid)["room"]["title"] == "그대로"


def test_rename_rejects_an_empty_title(client, login_as):
    csrf = login_as("user", email="re1@goodmit.co.kr")
    rid = _group(client, csrf, "이름있음")
    r = client.post(f"/api/team-chat/rooms/{rid}/rename", json={"title": "   "},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 422, r.text
    assert _meta(client, rid)["room"]["title"] == "이름있음"


def test_global_and_direct_rooms_cannot_be_renamed(client, login_as, make_user):
    csrf = login_as("user", email="rg1@goodmit.co.kr")
    gid = client.get("/api/team-chat/rooms").json()["global"]["id"]
    assert client.post(f"/api/team-chat/rooms/{gid}/rename", json={"title": "내방"},
                       headers={"X-CSRF-Token": csrf}).status_code == 409
    u2 = make_user(email="rg2@goodmit.co.kr", display_name="알지투")
    did = client.post("/api/team-chat/rooms/direct", json={"user_id": u2.id},
                      headers={"X-CSRF-Token": csrf}).json()["room"]["id"]
    assert client.post(f"/api/team-chat/rooms/{did}/rename", json={"title": "내방"},
                       headers={"X-CSRF-Token": csrf}).status_code == 409


# ── 2. 초대 ─────────────────────────────────────────────────────────────────

def test_owner_adds_members_and_they_get_a_notification(app, client, login_as, make_user):
    csrf = login_as("user", email="ad1@goodmit.co.kr")
    u2 = make_user(email="ad2@goodmit.co.kr", display_name="나중에온이")
    rid = _group(client, csrf, "커지는방")

    r = client.post(f"/api/team-chat/rooms/{rid}/members/add", json={"user_ids": [u2.id]},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and r.json()["added"] == 1, r.text
    assert u2.id in _roles(client, rid)

    c2, _ = _login_other(app, "ad2@goodmit.co.kr")
    with c2:
        # 초대받은 사람 목록에 방이 나오고, 알림 딥링크가 그 방을 가리킨다.
        assert any(x["id"] == rid for x in c2.get("/api/team-chat/rooms").json()["items"])
        items = c2.get("/api/notifications?type=chat_invited").json()["items"]
        assert items and items[0]["related_route"] == f"/chat-rooms/{rid}"


def test_adding_someone_already_in_the_room_is_a_no_op_not_an_error(client, login_as, make_user):
    """두 방장 후보가 동시에 같은 사람을 부르는 일이 실제로 생긴다 — 그때 요청 전체가
    실패하면 함께 고른 다른 사람들까지 못 들어온다."""
    csrf = login_as("user", email="dup1@goodmit.co.kr")
    u2 = make_user(email="dup2@goodmit.co.kr", display_name="중복초대")
    u3 = make_user(email="dup3@goodmit.co.kr", display_name="새사람")
    rid = _group(client, csrf, "중복방", [u2.id])

    r = client.post(f"/api/team-chat/rooms/{rid}/members/add", json={"user_ids": [u2.id, u3.id]},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and r.json()["added"] == 1, r.text
    roles = _roles(client, rid)
    assert u2.id in roles and u3.id in roles


def test_add_is_owner_only(app, client, login_as, make_user):
    csrf = login_as("user", email="ao1@goodmit.co.kr")
    u2 = make_user(email="ao2@goodmit.co.kr", display_name="에이오투")
    u3 = make_user(email="ao3@goodmit.co.kr", display_name="에이오쓰리")
    rid = _group(client, csrf, "방장만", [u2.id])
    c2, cs2 = _login_other(app, "ao2@goodmit.co.kr")
    with c2:
        r = c2.post(f"/api/team-chat/rooms/{rid}/members/add", json={"user_ids": [u3.id]},
                    headers={"X-CSRF-Token": cs2})
        assert r.status_code == 403, r.text
    assert u3.id not in _roles(client, rid)


# ── 3. 내보내기 ─────────────────────────────────────────────────────────────

def test_owner_removes_a_member_and_the_room_disappears_for_them(app, client, login_as, make_user):
    csrf = login_as("user", email="rm1@goodmit.co.kr")
    u2 = make_user(email="rm2@goodmit.co.kr", display_name="내보낼이")
    rid = _group(client, csrf, "정리방", [u2.id])

    r = client.post(f"/api/team-chat/rooms/{rid}/members/remove", json={"user_id": u2.id},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    assert u2.id not in _roles(client, rid)
    c2, _ = _login_other(app, "rm2@goodmit.co.kr")
    with c2:
        assert all(x["id"] != rid for x in c2.get("/api/team-chat/rooms").json()["items"])
        # 접근 자체가 막힌다(목록에서만 사라지는 게 아니다).
        assert c2.get(f"/api/team-chat/rooms/{rid}/messages?since=0").status_code == 403


def test_owner_cannot_remove_themselves(client, login_as, make_user):
    """이 경로를 열면 주인 없는 방이 생긴다 — 남은 사람은 아무 관리 동작도 못 한다."""
    csrf = login_as("user", email="rs1@goodmit.co.kr")
    u2 = make_user(email="rs2@goodmit.co.kr", display_name="알에스투")
    rid = _group(client, csrf, "주인방", [u2.id])
    me = _meta(client, rid)["you"]["user_id"]
    r = client.post(f"/api/team-chat/rooms/{rid}/members/remove", json={"user_id": me},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 409, r.text
    assert _roles(client, rid)[me] == "owner"


def test_removing_someone_who_is_not_a_member_is_404(client, login_as, make_user):
    csrf = login_as("user", email="rn1@goodmit.co.kr")
    stranger = make_user(email="rn2@goodmit.co.kr", display_name="바깥사람")
    rid = _group(client, csrf, "닫힌방")
    r = client.post(f"/api/team-chat/rooms/{rid}/members/remove", json={"user_id": stranger.id},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 404, r.text


# ── 4. 방장 넘기기 / 방장이 나가기 ──────────────────────────────────────────

def test_transfer_owner_swaps_exactly_two_roles(app, client, login_as, make_user):
    csrf = login_as("user", email="tr1@goodmit.co.kr")
    u2 = make_user(email="tr2@goodmit.co.kr", display_name="새방장")
    rid = _group(client, csrf, "넘기는방", [u2.id])
    me = _meta(client, rid)["you"]["user_id"]

    r = client.post(f"/api/team-chat/rooms/{rid}/owner", json={"user_id": u2.id},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    roles = _roles(client, rid)
    assert roles[u2.id] == "owner" and roles[me] == "member"
    # 넘긴 사람은 더는 관리할 수 없다.
    assert client.post(f"/api/team-chat/rooms/{rid}/rename", json={"title": "되돌리기"},
                       headers={"X-CSRF-Token": csrf}).status_code == 403
    # 새 방장은 할 수 있다.
    c2, cs2 = _login_other(app, "tr2@goodmit.co.kr")
    with c2:
        assert c2.post(f"/api/team-chat/rooms/{rid}/rename", json={"title": "내가방장"},
                       headers={"X-CSRF-Token": cs2}).status_code == 200


def test_transferring_to_yourself_is_409(client, login_as, make_user):
    csrf = login_as("user", email="ts1@goodmit.co.kr")
    u2 = make_user(email="ts2@goodmit.co.kr", display_name="티에스투")
    rid = _group(client, csrf, "자기자신", [u2.id])
    me = _meta(client, rid)["you"]["user_id"]
    r = client.post(f"/api/team-chat/rooms/{rid}/owner", json={"user_id": me},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 409, r.text


def test_owner_leaving_hands_the_room_to_the_earliest_member(app, client, login_as, make_user):
    """예전엔 멤버 행만 지웠다 — 방장이 나가면 아무도 관리할 수 없는 방이 영원히 남았다."""
    csrf = login_as("user", email="ol1@goodmit.co.kr")
    u2 = make_user(email="ol2@goodmit.co.kr", display_name="먼저온이")
    u3 = make_user(email="ol3@goodmit.co.kr", display_name="나중온이")
    rid = _group(client, csrf, "남는방", [u2.id, u3.id])

    assert client.post(f"/api/team-chat/rooms/{rid}/leave", headers={"X-CSRF-Token": csrf}).status_code == 200

    c2, cs2 = _login_other(app, "ol2@goodmit.co.kr")
    with c2:
        roles = {m["user_id"]: m["role"] for m in c2.get(f"/api/team-chat/rooms/{rid}/messages?since=0").json()["members"]}
        owners = [uid for uid, role in roles.items() if role == "owner"]
        assert len(owners) == 1, "주인 없는(또는 둘인) 방이 남으면 안 된다"
        # 새 방장은 실제로 관리할 수 있다.
        me2 = c2.get(f"/api/team-chat/rooms/{rid}/messages?since=0").json()["you"]
        assert me2["can_manage"] == (roles[me2["user_id"]] == "owner")


def test_the_last_member_leaving_disbands_the_room(client, login_as):
    """아무도 없는 방을 살려 두면 목록에서만 사라진 채 DB 에 영원히 남는다."""
    csrf = login_as("user", email="lm1@goodmit.co.kr")
    rid = _group(client, csrf, "혼자방")
    assert client.post(f"/api/team-chat/rooms/{rid}/leave", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert client.get(f"/api/team-chat/rooms/{rid}/messages?since=0").status_code == 404


def test_can_manage_is_the_single_flag_the_screen_reads(app, client, login_as, make_user):
    """프런트가 '그룹인가? 방장인가? 전체인가?'를 다시 계산하면 서버와 어긋나는 순간
    '보이는데 누르면 403'이 된다 — 서버가 한 플래그로 답한다."""
    csrf = login_as("user", email="cm1@goodmit.co.kr")
    u2 = make_user(email="cm2@goodmit.co.kr", display_name="씨엠투")
    gid = client.get("/api/team-chat/rooms").json()["global"]["id"]
    assert _meta(client, gid)["you"]["can_manage"] is False

    did = client.post("/api/team-chat/rooms/direct", json={"user_id": u2.id},
                      headers={"X-CSRF-Token": csrf}).json()["room"]["id"]
    assert _meta(client, did)["you"]["can_manage"] is False

    rid = _group(client, csrf, "관리방", [u2.id])
    assert _meta(client, rid)["you"]["can_manage"] is True
    c2, _ = _login_other(app, "cm2@goodmit.co.kr")
    with c2:
        assert c2.get(f"/api/team-chat/rooms/{rid}/messages?since=0").json()["you"]["can_manage"] is False
