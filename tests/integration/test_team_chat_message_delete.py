"""내 메시지 지우기(soft delete) — PLAN Phase 3 §F.

이 파일이 지키는 **핵심 한 가지**: 삭제는 `event_seq` 를 올려야 한다.

행에 `deleted_at` 만 찍으면 이미 화면을 띄워 둔 클라이언트는 다음 폴링에서 seq 가 그대로인
응답을 받는다 — 그 사람 화면에서는 삭제가 **일어나지 않는다**. 새 시스템 메시지(툼스톤)가
seq 를 올려야 `since=<옛 seq>` 폴링이 변경을 받아 다시 읽는다. 아래 첫 테스트가 정확히 그
상황을 재현한다(삭제 직전 seq 로 폴링 → 변경이 내려와야 한다).
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


def _room_with(client, csrf, member_ids=()):
    return client.post(
        "/api/team-chat/rooms",
        json={"title": "삭제방", "member_user_ids": list(member_ids)},
        headers={"X-CSRF-Token": csrf},
    ).json()["room"]["id"]


def _send(client, csrf, rid, body):
    r = client.post(f"/api/team-chat/rooms/{rid}/messages", json={"body": body},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    return r.json()["seq"]


def _poll(client, rid, since):
    r = client.get(f"/api/team-chat/rooms/{rid}/messages?since={since}")
    assert r.status_code == 200, r.text
    return r.json()


# ── 1. seq 를 올린다(이 기능의 존재 이유) ───────────────────────────────────

def test_delete_bumps_event_seq_so_an_already_rendered_client_re_reads(client, login_as):
    csrf = login_as("user", email="del1@goodmit.co.kr")
    rid = _room_with(client, csrf)
    seq = _send(client, csrf, rid, "지울 말")

    before = _poll(client, rid, 0)["seq"]
    # 기준선: 아무 일도 안 일어나면 그 seq 로 폴링해도 변경이 없다.
    quiet = _poll(client, rid, before)
    assert quiet["messages"] == [] and quiet["seq"] == before

    r = client.post(f"/api/team-chat/rooms/{rid}/messages/{seq}/delete",
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text

    # **여기가 핵심** — 삭제 직전 seq 로 폴링하면 변경이 내려온다.
    after = _poll(client, rid, before)
    assert after["seq"] > before
    assert after["messages"], "툼스톤 시스템 메시지가 내려와야 낡은 클라이언트가 다시 읽는다"
    assert after["messages"][-1]["kind"] == "system"


def test_deleted_message_is_gone_from_a_fresh_read(client, login_as):
    csrf = login_as("user", email="del2@goodmit.co.kr")
    rid = _room_with(client, csrf)
    seq = _send(client, csrf, rid, "사라질 말")
    assert any(m["body"] == "사라질 말" for m in _poll(client, rid, 0)["messages"])

    client.post(f"/api/team-chat/rooms/{rid}/messages/{seq}/delete", headers={"X-CSRF-Token": csrf})

    bodies = [m["body"] for m in _poll(client, rid, 0)["messages"]]
    assert "사라질 말" not in bodies
    assert any("삭제했습니다" in b for b in bodies)


def test_deleting_the_last_message_updates_the_room_list_preview(client, login_as):
    """목록의 한 줄 미리보기는 마지막 메시지다 — 지운 글이 거기 남아 있으면 지운 의미가 없다."""
    csrf = login_as("user", email="del3@goodmit.co.kr")
    rid = _room_with(client, csrf)
    seq = _send(client, csrf, rid, "비밀번호는 1234")
    rooms = client.get("/api/team-chat/rooms").json()["items"]
    assert next(x for x in rooms if x["id"] == rid)["last_preview"] == "비밀번호는 1234"

    client.post(f"/api/team-chat/rooms/{rid}/messages/{seq}/delete", headers={"X-CSRF-Token": csrf})
    rooms = client.get("/api/team-chat/rooms").json()["items"]
    assert "1234" not in next(x for x in rooms if x["id"] == rid)["last_preview"]


# ── 2. 누가 지울 수 있나 ────────────────────────────────────────────────────

def test_only_my_own_message_can_be_deleted(app, client, login_as, make_user):
    csrf = login_as("user", email="dp1@goodmit.co.kr")
    u2 = make_user(email="dp2@goodmit.co.kr", display_name="남의사람")
    rid = _room_with(client, csrf, [u2.id])
    seq = _send(client, csrf, rid, "내 말")

    c2, cs2 = _login_other(app, "dp2@goodmit.co.kr")
    with c2:
        r = c2.post(f"/api/team-chat/rooms/{rid}/messages/{seq}/delete", headers={"X-CSRF-Token": cs2})
        assert r.status_code == 403, r.text
    # 여전히 살아 있다.
    assert any(m["body"] == "내 말" for m in _poll(client, rid, 0)["messages"])


def test_a_non_member_cannot_even_try(app, client, login_as, make_user):
    csrf = login_as("user", email="dn1@goodmit.co.kr")
    rid = _room_with(client, csrf)
    seq = _send(client, csrf, rid, "안쪽 이야기")
    make_user(email="dn2@goodmit.co.kr", display_name="바깥사람")
    c2, cs2 = _login_other(app, "dn2@goodmit.co.kr")
    with c2:
        r = c2.post(f"/api/team-chat/rooms/{rid}/messages/{seq}/delete", headers={"X-CSRF-Token": cs2})
        assert r.status_code == 403, r.text


def test_system_messages_cannot_be_deleted(client, login_as):
    """방 생성·초대·삭제 같은 기록을 지우면 로그가 '무슨 일이 있었는지'를 말하지 못한다."""
    csrf = login_as("user", email="ds1@goodmit.co.kr")
    rid = _room_with(client, csrf)
    system = _poll(client, rid, 0)["messages"][0]
    assert system["kind"] == "system"
    r = client.post(f"/api/team-chat/rooms/{rid}/messages/{system['seq']}/delete",
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 409, r.text


def test_deleting_twice_does_not_stack_tombstones(client, login_as):
    """재시도(느린 네트워크)가 툼스톤을 두 개 만들면 로그가 사고 기록처럼 보인다."""
    csrf = login_as("user", email="dt1@goodmit.co.kr")
    rid = _room_with(client, csrf)
    seq = _send(client, csrf, rid, "두 번 지울 말")
    client.post(f"/api/team-chat/rooms/{rid}/messages/{seq}/delete", headers={"X-CSRF-Token": csrf})
    once = _poll(client, rid, 0)["seq"]
    r = client.post(f"/api/team-chat/rooms/{rid}/messages/{seq}/delete", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    assert _poll(client, rid, 0)["seq"] == once


def test_unknown_seq_is_404(client, login_as):
    csrf = login_as("user", email="du1@goodmit.co.kr")
    rid = _room_with(client, csrf)
    r = client.post(f"/api/team-chat/rooms/{rid}/messages/99999/delete", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 404, r.text


def test_delete_requires_csrf(client, login_as):
    csrf = login_as("user", email="dc1@goodmit.co.kr")
    rid = _room_with(client, csrf)
    seq = _send(client, csrf, rid, "CSRF 없이 지우기")
    assert client.post(f"/api/team-chat/rooms/{rid}/messages/{seq}/delete").status_code == 403
