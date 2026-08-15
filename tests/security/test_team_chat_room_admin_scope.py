"""채팅방 관리 경로(이름 변경·초대·내보내기·방장 넘기기)의 범위 판정.

`scripts/check_scope_gates.py` 가 이 네 경로를 잡았다. 읽어 보면 셋은 **오탐**이다 —
방장 판정 한 함수를 이미 지나고, 대상은 전부 *그 방의 기존 멤버*라 새로 열리는 문이 없다.
검사가 못 본 것은 그 함수 이름이 저장소 표준 어휘(`ensure_*`)가 아니었다는 것뿐이다.

**하나는 진짜였다: 초대(`members/add`).** 방장 판정은 지나는데 **초대 대상에 조직 판정이
없었다.** 1:1 은 `create_or_get_direct` 가 이미 막아 둔 구멍인데(3순위 IDOR,
tests/security/test_org_axis.py) 그룹 방 초대는 같은 `user_id` 를 그대로 받았다.
그래서 다른 회사 사람을 id 하나로 내 방에 **끌어들일 수 있었다** — 끌어들이는 순간
그 방의 메시지와 붙여넣기 이미지 전부에 접근권이 생긴다(이미지 서빙이 방 멤버십으로
판정한다). 목록(`/directory`)을 조직으로 좁혀 둔 것이 이 옆문으로 무효화됐다.
방 만들기(`POST /rooms`)의 `member_user_ids` 도 같은 문이라 같은 판정을 지나게 했다.

범위 밖은 **404** — 403 은 "그 계정은 존재한다"를 알려 준다(저장소 규칙).
비멤버·비방장은 그대로 **403**이다: 그건 범위가 아니라 권한 문제이고, 방 자체의 접근 거부는
이 저장소가 의도적으로 403 으로 답한다(tests/security/test_team_chat_images.py 주석).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.security

CSRF = "X-CSRF-Token"


def _login_other(app, email):
    c = TestClient(app, raise_server_exceptions=False)
    c.post("/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD})
    return c, c.get("/api/me").json()["csrf_token"]


def _group(client, csrf, title="회의방", members=()):
    r = client.post("/api/team-chat/rooms",
                    json={"title": title, "member_user_ids": list(members)},
                    headers={CSRF: csrf})
    assert r.status_code == 200, r.text
    return r.json()["room"]["id"]


def _member_ids(client, rid):
    r = client.get(f"/api/team-chat/rooms/{rid}/messages?since=0")
    assert r.status_code == 200, r.text
    return {m["user_id"] for m in r.json()["members"]}


# ── 진짜 구멍: 초대에 조직 판정이 없었다 ────────────────────────────────────

def test_you_cannot_invite_someone_from_another_organization(app, client, login_as, two_orgs):
    """다른 조직 사람을 내 그룹 방에 초대할 수 없다 — **초대되는 순간 대화 전체가 열린다**."""
    csrf = login_as("user", email="orga@goodmit.co.kr")
    rid = _group(client, csrf, "A조직 회의방")
    client.post(f"/api/team-chat/rooms/{rid}/messages",
                json={"body": "A조직 내부 대화"}, headers={CSRF: csrf})

    r = client.post(f"/api/team-chat/rooms/{rid}/members/add",
                    json={"user_ids": [two_orgs.user_b.id]}, headers={CSRF: csrf})
    assert r.status_code == 404, (
        f"다른 조직 사람이 초대된다({r.status_code}) — 그 방의 메시지·이미지 접근권이 생긴다"
    )
    assert two_orgs.user_b.id not in _member_ids(client, rid), "참여자 목록에 남았다"

    # 목록에서 가린 것을 id 로 뚫었는지가 진짜 질문이다 — 실제로 읽히는지 본다.
    c2, _ = _login_other(app, "orgb@goodmit.co.kr")
    with c2:
        assert c2.get(f"/api/team-chat/rooms/{rid}/messages?since=0").status_code == 403, (
            "다른 조직 사람이 A조직 방의 대화를 읽는다"
        )


def test_you_cannot_smuggle_another_organization_in_when_creating_the_room(
    app, client, login_as, two_orgs
):
    """방 만들기의 `member_user_ids` 는 초대와 같은 문이다 — 한쪽만 막으면 소용없다."""
    csrf = login_as("user", email="orga@goodmit.co.kr")
    r = client.post("/api/team-chat/rooms",
                    json={"title": "몰래방", "member_user_ids": [two_orgs.user_b.id]},
                    headers={CSRF: csrf})
    assert r.status_code == 404, f"방을 만들면서 다른 조직 사람을 넣을 수 있다({r.status_code})"

    c2, _ = _login_other(app, "orgb@goodmit.co.kr")
    with c2:
        assert all(x["title"] != "몰래방" for x in c2.get("/api/team-chat/rooms").json()["items"])


def test_the_partial_invite_does_not_leak_either(app, client, login_as, two_orgs, make_user, db):
    """같은 조직 사람과 섞어 보내도 조직 밖은 들어오지 못한다(부분 통과 금지)."""
    from app.org.constants import DEFAULT_ORG_ID

    mate = make_user("orga3@goodmit.co.kr", role="user", display_name="A사람3")
    mate.org_id = DEFAULT_ORG_ID
    db.commit()

    csrf = login_as("user", email="orga@goodmit.co.kr")
    rid = _group(client, csrf, "섞인방")
    r = client.post(f"/api/team-chat/rooms/{rid}/members/add",
                    json={"user_ids": [mate.id, two_orgs.user_b.id]}, headers={CSRF: csrf})
    assert r.status_code == 404, f"섞어 보내면 통과한다({r.status_code})"

    ids = _member_ids(client, rid)
    assert two_orgs.user_b.id not in ids, "다른 조직 사람이 들어왔다"


# ── 오탐 방지: 정상 경로는 **여전히 된다** ──────────────────────────────────

def test_the_owner_can_still_run_all_four_management_actions(app, client, login_as, make_user):
    """네 경로가 한 판정을 지나게 바꿨다 — 방장의 정상 동작이 하나라도 막히면 그건 회귀다."""
    csrf = login_as("user", email="mg1@goodmit.co.kr")
    u2 = make_user(email="mg2@goodmit.co.kr", display_name="엠지투")
    u3 = make_user(email="mg3@goodmit.co.kr", display_name="엠지쓰리")
    rid = _group(client, csrf, "관리방", [u2.id])

    assert client.post(f"/api/team-chat/rooms/{rid}/rename", json={"title": "새이름"},
                       headers={CSRF: csrf}).status_code == 200
    assert client.post(f"/api/team-chat/rooms/{rid}/members/add", json={"user_ids": [u3.id]},
                       headers={CSRF: csrf}).status_code == 200
    assert client.post(f"/api/team-chat/rooms/{rid}/members/remove", json={"user_id": u3.id},
                       headers={CSRF: csrf}).status_code == 200
    assert client.post(f"/api/team-chat/rooms/{rid}/owner", json={"user_id": u2.id},
                       headers={CSRF: csrf}).status_code == 200

    c2, cs2 = _login_other(app, "mg2@goodmit.co.kr")
    with c2:
        assert c2.post(f"/api/team-chat/rooms/{rid}/rename", json={"title": "내가방장"},
                       headers={CSRF: cs2}).status_code == 200


def test_you_can_still_invite_another_team_in_your_own_organization(client, login_as, make_user, db):
    """부서로는 좁히지 않는다 — 다른 팀을 못 부르면 그건 기능 축소지 보안이 아니다."""
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    other_team = Department(name="A팀3", org_id=DEFAULT_ORG_ID)
    db.add(other_team)
    db.flush()
    mate = make_user("orga4@goodmit.co.kr", role="user", display_name="A사람4")
    mate.org_id = DEFAULT_ORG_ID
    mate.department_id = other_team.id
    db.commit()

    csrf = login_as("user", email="orga@goodmit.co.kr")
    rid = _group(client, csrf, "옆팀방")
    r = client.post(f"/api/team-chat/rooms/{rid}/members/add",
                    json={"user_ids": [mate.id]}, headers={CSRF: csrf})
    assert r.status_code == 200, f"같은 조직 다른 팀을 못 부른다: {r.status_code} {r.text[:120]}"
    assert mate.id in _member_ids(client, rid)


def test_an_already_joined_person_from_another_org_can_still_be_removed(
    client, login_as, two_orgs, db
):
    """구멍이 막히기 **전에** 들어온 사람을 내보내는 길은 남아 있어야 한다 —
    내보내기에 조직 판정을 걸면 이미 들어와 있는 사람을 영영 못 뺀다(고치려다 가두는 꼴)."""
    from app.team_chat.models import ChatRoomMember

    csrf = login_as("user", email="orga@goodmit.co.kr")
    rid = _group(client, csrf, "이미들어온방")
    db.add(ChatRoomMember(room_id=rid, user_id=two_orgs.user_b.id, role="member",
                          last_read_seq=0))
    db.commit()

    r = client.post(f"/api/team-chat/rooms/{rid}/members/remove",
                    json={"user_id": two_orgs.user_b.id}, headers={CSRF: csrf})
    assert r.status_code == 200, f"이미 들어온 조직 밖 사람을 못 뺀다: {r.status_code} {r.text[:120]}"
    assert two_orgs.user_b.id not in _member_ids(client, rid)


# ── 권한(403)과 범위(404)를 섞지 않는다 ─────────────────────────────────────

def test_a_member_who_is_not_the_owner_still_gets_403_not_404(app, client, login_as, make_user):
    """비방장은 **권한** 문제다 — 그 방이 있다는 사실은 이미 알고 있으므로 404 로 숨길 게 없다."""
    csrf = login_as("user", email="no1@goodmit.co.kr")
    u2 = make_user(email="no2@goodmit.co.kr", display_name="엔오투")
    rid = _group(client, csrf, "그대로", [u2.id])
    c2, cs2 = _login_other(app, "no2@goodmit.co.kr")
    with c2:
        for path, body in (("rename", {"title": "내맘대로"}),
                           ("members/add", {"user_ids": [u2.id]}),
                           ("members/remove", {"user_id": u2.id}),
                           ("owner", {"user_id": u2.id})):
            r = c2.post(f"/api/team-chat/rooms/{rid}/{path}", json=body, headers={CSRF: cs2})
            assert r.status_code == 403, f"{path} 가 403 이 아니다: {r.status_code}"


def test_a_stranger_cannot_manage_the_room(app, client, login_as, make_user):
    csrf = login_as("user", email="st1@goodmit.co.kr")
    rid = _group(client, csrf, "닫힌방")
    outsider = make_user("st2@goodmit.co.kr", display_name="바깥사람")
    c2, cs2 = _login_other(app, "st2@goodmit.co.kr")
    with c2:
        for path, body in (("rename", {"title": "내맘대로"}),
                           ("members/add", {"user_ids": [outsider.id]}),
                           ("members/remove", {"user_id": "x"}),
                           ("owner", {"user_id": "x"})):
            r = c2.post(f"/api/team-chat/rooms/{rid}/{path}", json=body, headers={CSRF: cs2})
            assert r.status_code == 403, f"{path} 가 비멤버에게 열린다: {r.status_code}"


# ── 전체 채팅(is_global)·팀 방(department_id)의 기존 성질 ───────────────────

def test_the_global_room_is_still_unmanageable_with_409(client, login_as):
    """전체 채팅은 멤버십 자체가 없고 이름이 제품의 일부다 — 권한(403)이 아니라
    '그 방에는 없는 개념'(409)이다. 판정을 한 곳으로 모으면서 이게 403 으로 바뀌면 안 된다."""
    csrf = login_as("user", email="gl1@goodmit.co.kr")
    me = client.get("/api/me").json()["user"]["id"]
    gid = client.get("/api/team-chat/rooms").json()["global"]["id"]
    for path, body in (("rename", {"title": "내방"}),
                       ("members/add", {"user_ids": [me]}),
                       ("members/remove", {"user_id": "x"}),
                       ("owner", {"user_id": "x"})):
        r = client.post(f"/api/team-chat/rooms/{gid}/{path}", json=body, headers={CSRF: csrf})
        assert r.status_code == 409, f"전체 채팅 {path} 가 409 가 아니다: {r.status_code}"


def test_the_team_room_keeps_its_ownerless_shape(client, login_as, make_user, db, app):
    """팀 방(`department_id`)은 부서가 주인이라 **방장이 없다** — 아무도 이름을 바꾸거나
    사람을 넣지 못한다. 1:1·전체 채팅과 달리 종류는 그냥 그룹이라(모델 주석) 관리 경로가
    409 가 아니라 403 으로 답한다. 판정을 모으면서 팀 방에 방장이 생기면 안 된다."""
    from app.org.models import Department
    from app.users.models import User

    make_user("tm1@goodmit.co.kr", display_name="팀사람")
    with app.state.session_factory() as s:
        dept = Department(name="스코프팀", active=True)
        s.add(dept)
        s.flush()
        s.query(User).filter(User.email == "tm1@goodmit.co.kr").one().department_id = dept.id
        s.commit()

    csrf = login_as("user", email="tm1@goodmit.co.kr")
    team = client.get("/api/team-chat/rooms").json()["team"]
    assert team is not None and team["department_id"] is not None

    roles = {m["role"] for m in
             client.get(f"/api/team-chat/rooms/{team['id']}/messages?since=0").json()["members"]}
    assert roles == {"member"}, f"팀 방에 방장이 생겼다: {roles}"
    r = client.post(f"/api/team-chat/rooms/{team['id']}/rename", json={"title": "내팀방"},
                    headers={CSRF: csrf})
    assert r.status_code == 403, f"팀 방 이름이 바뀐다: {r.status_code}"


# RBAC 재감사(2026-08-16, SEC-35와 같은 자리): create_group/create_or_get_direct/팀 방
# 자동생성 셋 다 org_id를 안 채워 방장의 실제 조직과 무관하게 컬럼 기본값(기본 조직)으로
# 저장되고 있었다. ChatRoom.org_id를 읽는 접근 제어는 지금 없어(초대·목록은 전부 멤버십/
# User.org_id로 판정) 활성 유출은 아니지만, board의 Post가 정확히 이 모양으로 뚫렸던
# 전례가 있어 미리 맞게 채워 둔다.
def test_a_group_room_is_stamped_with_its_owners_organization(client, login_as, two_orgs, db):
    from app.team_chat.models import ChatRoom

    csrf = login_as("user", email="orgb@goodmit.co.kr")
    rid = _group(client, csrf, "B조직 회의방")

    stored = db.get(ChatRoom, rid)
    assert stored.org_id == two_orgs.org_b_id, (
        f"B조직 방장이 만든 방이 다른 조직({stored.org_id})으로 저장됐다"
    )
