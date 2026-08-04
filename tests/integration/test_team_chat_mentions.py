"""@멘션 알림 + 딥링크 (PLAN Phase 3 §F).

딥링크는 **서버가 계산한다**(app/notifications/destinations.py 의 RELATED_DESTINATIONS).
프런트에 유형별 `if` 를 늘리지 않는 것이 그 표를 만든 이유다 — 아래 테스트는 새 유형이
그 표를 지나 `related_route` 로 나온다는 것을 고정한다.
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


def _mentions(c):
    return c.get("/api/notifications?type=chat_mentioned").json()["items"]


def _send(client, csrf, rid, body, cid=None):
    payload = {"body": body}
    if cid:
        payload["client_message_id"] = cid
    r = client.post(f"/api/team-chat/rooms/{rid}/messages", json=payload,
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    return r.json()["seq"]


def test_mentioning_a_member_notifies_them_with_a_deep_link(app, client, login_as, make_user):
    csrf = login_as("user", email="mn1@goodmit.co.kr")
    u2 = make_user(email="mn2@goodmit.co.kr", display_name="불린사람")
    rid = client.post("/api/team-chat/rooms", json={"title": "멘션방", "member_user_ids": [u2.id]},
                      headers={"X-CSRF-Token": csrf}).json()["room"]["id"]

    _send(client, csrf, rid, "@불린사람 이거 봐주세요")

    c2, _ = _login_other(app, "mn2@goodmit.co.kr")
    with c2:
        items = _mentions(c2)
        assert len(items) == 1
        n = items[0]
        assert n["related_object_type"] == "chat_mention"
        # 목적지는 표가 계산한다 — 프런트는 이 경로로 이동만 한다.
        assert n["related_route"] == f"/chat-rooms/{rid}"
        assert "이거 봐주세요" in (n["body"] or "")


def test_mentioning_yourself_notifies_nobody(client, login_as):
    csrf = login_as("user", email="ms1@goodmit.co.kr", )
    me = client.get("/api/me").json()["user"]
    rid = client.post("/api/team-chat/rooms", json={"title": "혼잣말", "member_user_ids": []},
                      headers={"X-CSRF-Token": csrf}).json()["room"]["id"]
    _send(client, csrf, rid, f"@{me['display_name']} 나에게 메모")
    assert _mentions(client) == []


def test_someone_outside_the_room_cannot_be_summoned(app, client, login_as, make_user):
    """방 밖 사람을 부를 수 있으면 열 수도 없는 방의 알림을 받는다."""
    csrf = login_as("user", email="mo1@goodmit.co.kr")
    make_user(email="mo2@goodmit.co.kr", display_name="바깥사람")
    rid = client.post("/api/team-chat/rooms", json={"title": "닫힌방", "member_user_ids": []},
                      headers={"X-CSRF-Token": csrf}).json()["room"]["id"]

    _send(client, csrf, rid, "@바깥사람 여기 좀")

    c2, _ = _login_other(app, "mo2@goodmit.co.kr")
    with c2:
        assert _mentions(c2) == []


def test_the_global_room_can_summon_anyone_in_the_company(app, client, login_as, make_user):
    """전체 채팅에서 멘션이 안 되면 정작 가장 필요한 자리에서 빠진다(그 방은 전원 공개다)."""
    csrf = login_as("user", email="mg1@goodmit.co.kr")
    make_user(email="mg2@goodmit.co.kr", display_name="전사멤버")
    gid = client.get("/api/team-chat/rooms").json()["global"]["id"]

    _send(client, csrf, gid, "@전사멤버 오늘 배포 있습니다")

    c2, _ = _login_other(app, "mg2@goodmit.co.kr")
    with c2:
        items = _mentions(c2)
        assert len(items) == 1 and items[0]["related_route"] == f"/chat-rooms/{gid}"


def test_a_retried_send_does_not_notify_twice(app, client, login_as, make_user):
    """낙관적 전송의 재시도는 같은 client_message_id 로 온다 — 알림이 두 번 가면 안 된다."""
    csrf = login_as("user", email="mr1@goodmit.co.kr")
    u2 = make_user(email="mr2@goodmit.co.kr", display_name="재시도상대")
    rid = client.post("/api/team-chat/rooms", json={"title": "재시도방", "member_user_ids": [u2.id]},
                      headers={"X-CSRF-Token": csrf}).json()["room"]["id"]

    first = _send(client, csrf, rid, "@재시도상대 확인", cid="same-id-1")
    again = _send(client, csrf, rid, "@재시도상대 확인", cid="same-id-1")
    assert first == again

    c2, _ = _login_other(app, "mr2@goodmit.co.kr")
    with c2:
        assert len(_mentions(c2)) == 1


def test_a_message_without_an_at_sign_notifies_nobody(app, client, login_as, make_user):
    csrf = login_as("user", email="mp1@goodmit.co.kr")
    u2 = make_user(email="mp2@goodmit.co.kr", display_name="평범한상대")
    rid = client.post("/api/team-chat/rooms", json={"title": "평범방", "member_user_ids": [u2.id]},
                      headers={"X-CSRF-Token": csrf}).json()["room"]["id"]
    _send(client, csrf, rid, "평범한상대 님 이거 봐주세요")  # '@' 가 없다
    c2, _ = _login_other(app, "mp2@goodmit.co.kr")
    with c2:
        assert _mentions(c2) == []


def test_an_email_in_the_body_is_not_a_mention(app, client, login_as, make_user):
    csrf = login_as("user", email="me1@goodmit.co.kr")
    u2 = make_user(email="me2@goodmit.co.kr", display_name="goodmit")
    rid = client.post("/api/team-chat/rooms", json={"title": "이메일방", "member_user_ids": [u2.id]},
                      headers={"X-CSRF-Token": csrf}).json()["room"]["id"]
    _send(client, csrf, rid, "문의는 helpdesk@goodmit.co.kr 로 주세요")
    c2, _ = _login_other(app, "me2@goodmit.co.kr")
    with c2:
        assert _mentions(c2) == []


# ── 동명이인 (2026-08-04 사용자 지시) ─────────────────────────────────────────

def test_people_with_the_same_name_can_finally_be_mentioned(app, client, login_as, make_user, db):
    """같은 표시 이름 두 사람을 소속으로 갈라 정확히 지목한다.

    예전 동작: 이름이 겹치면 **두 사람 다** 후보에서 빠졌다. 임의로 한 명을 고르면 '누가
    받았는지 모르는 알림'이 되기 때문인데, 그 결과 동명이인은 아무도 부를 수 없었다 —
    그것도 조용히. 부르는 쪽은 알림이 안 갔다는 사실조차 몰랐다.

    이제 겹치는 이름만 `이름(소속)` 형태로 갈린다. 이름만 쓴 `@김하나` 는 여전히 아무에게도
    안 간다 — 애매한 채로 아무나 부르지 않는다는 원칙은 그대로다.
    """
    from app.org.models import Department

    csrf = login_as("user", email="dup0@goodmit.co.kr")
    a = make_user(email="dupa@goodmit.co.kr", display_name="김하나")
    b = make_user(email="dupb@goodmit.co.kr", display_name="김하나")
    # 소속이 곧 두 사람을 가르는 유일한 표지다 — 그것을 실제로 붙여 놓고 확인한다.
    d1, d2 = Department(name="플랫폼팀"), Department(name="인프라팀")
    db.add_all([d1, d2]); db.flush()
    a.department_id, b.department_id = d1.id, d2.id
    db.commit()
    rid = client.post("/api/team-chat/rooms",
                      json={"title": "동명이인방", "member_user_ids": [a.id, b.id]},
                      headers={"X-CSRF-Token": csrf}).json()["room"]["id"]

    # 1) 소속을 붙이면 그 사람 **한 명에게만** 간다.
    _send(client, csrf, rid, "@김하나(플랫폼팀) 이거 봐주세요")
    ca, _ = _login_other(app, "dupa@goodmit.co.kr")
    with ca:
        assert len(_mentions(ca)) == 1, "소속을 붙여 부른 사람이 알림을 못 받았다"
    cb, _ = _login_other(app, "dupb@goodmit.co.kr")
    with cb:
        assert _mentions(cb) == [], "부르지 않은 동명이인에게 알림이 갔다"

    # 2) 이름만 쓰면 여전히 아무에게도 안 간다(애매한 지목을 임의로 해석하지 않는다).
    _send(client, csrf, rid, "@김하나 이건 누구를 부른 걸까")
    with _login_other(app, "dupa@goodmit.co.kr")[0] as ca2:
        assert len(_mentions(ca2)) == 1, "이름만 썼는데 알림이 하나 더 갔다"
    with _login_other(app, "dupb@goodmit.co.kr")[0] as cb2:
        assert _mentions(cb2) == []
