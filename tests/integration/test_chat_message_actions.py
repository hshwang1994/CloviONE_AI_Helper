"""AI-36/AI-68: 메시지 삭제·재생성·피드백(👍/👎) — app/chat/service.py의 새 함수 3개.

재생성은 워커가 실제로 답을 채워야(PROC_DONE) 성립하는데 이 시험은 워커를 돌리지 않으므로,
`db` 세션으로 직접 "이미 완료된 턴"을 만든 뒤 API를 호출한다(retry 시험이 이미 같은
이유로 `client.post(.../messages)`가 만드는 PENDING 상태만 API로 확인하고 나머지는
`db`로 세팅하는 것과 같은 관례).
"""

from __future__ import annotations

import pytest

from app.conversations.models import PROC_DONE, ROLE_ASSISTANT_MSG, Message

pytestmark = pytest.mark.integration

CLIENT_MSG_ID = "m0123456789abcdef0123456789abcdef"


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


def _new_conversation(client, csrf):
    r = client.post("/api/conversations", json={}, headers=_headers(csrf))
    assert r.status_code == 201
    return r.json()["conversation"]


def _answered_turn(db, client, csrf, conv_id, *, content="질문", answer="답변"):
    """사용자 메시지를 보내고, 워커가 했을 일(완료 처리 + 어시스턴트 답변 추가)을 db로
    직접 흉내 낸다 — retry_message가 실패 상태를 요구하는 것과 대칭으로,
    regenerate_message는 완료 상태를 요구하므로 이 헬퍼가 그 상태를 만든다."""
    r = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": content, "client_message_id": CLIENT_MSG_ID},
        headers=_headers(csrf),
    )
    assert r.status_code == 202
    user_msg_id = r.json()["message"]["id"]
    user_msg = db.get(Message, user_msg_id)
    user_msg.processing_status = PROC_DONE
    reply = Message(
        conversation_id=conv_id,
        message_id=f"a-{CLIENT_MSG_ID}-1",
        role=ROLE_ASSISTANT_MSG,
        content=answer,
        processing_status=PROC_DONE,
    )
    db.add(reply)
    db.commit()
    return user_msg_id, reply.id


# ── 삭제 ──────────────────────────────────────────────────────────────────

def test_deleting_a_message_hides_it_from_the_thread(client, login_as, db):
    csrf = login_as("user")
    conv = _new_conversation(client, csrf)
    user_msg_id, reply_id = _answered_turn(db, client, csrf, conv["id"])

    r = client.delete(f"/api/messages/{reply_id}", headers=_headers(csrf))
    assert r.status_code == 200

    items = client.get(f"/api/conversations/{conv['id']}/messages").json()["items"]
    assert reply_id not in {m["id"] for m in items}
    assert user_msg_id in {m["id"] for m in items}  # 짝 메시지는 안 지워짐(설계)


def test_deleting_a_message_twice_is_idempotent(client, login_as, db):
    csrf = login_as("user")
    conv = _new_conversation(client, csrf)
    _, reply_id = _answered_turn(db, client, csrf, conv["id"])

    first = client.delete(f"/api/messages/{reply_id}", headers=_headers(csrf))
    second = client.delete(f"/api/messages/{reply_id}", headers=_headers(csrf))
    assert first.status_code == 200
    assert second.status_code == 200


def test_deleting_unknown_message_returns_404(client, login_as):
    csrf = login_as("user")
    r = client.delete("/api/messages/does-not-exist", headers=_headers(csrf))
    assert r.status_code == 404


def test_cannot_delete_another_users_message(client, login_as, make_user, db):
    other_csrf = login_as("user", email="other@goodmit.co.kr")
    other_conv = _new_conversation(client, other_csrf)
    _, other_reply_id = _answered_turn(db, client, other_csrf, other_conv["id"])

    my_csrf = login_as("user", email="me@goodmit.co.kr")
    r = client.delete(f"/api/messages/{other_reply_id}", headers=_headers(my_csrf))
    # get_owned_conversation()의 기존 관례(다른 사람 대화 = 403) 그대로 — board/tickets/trash의
    # "범위 밖은 404" 관례는 org/dept 스코프 위반용이고, 대화 소유권은 그 관례를 안 쓴다
    # (get_messages/patch_conversation 등 기존 엔드포인트 전부가 이미 이렇게 동작한다).
    assert r.status_code == 403


# ── 피드백 ────────────────────────────────────────────────────────────────

def test_feedback_up_and_down_and_clear(client, login_as, db):
    csrf = login_as("user")
    conv = _new_conversation(client, csrf)
    _, reply_id = _answered_turn(db, client, csrf, conv["id"])

    up = client.patch(f"/api/messages/{reply_id}/feedback", json={"feedback": "up"},
                       headers=_headers(csrf))
    assert up.status_code == 200
    assert up.json()["message"]["feedback"] == "up"

    down = client.patch(f"/api/messages/{reply_id}/feedback", json={"feedback": "down"},
                         headers=_headers(csrf))
    assert down.json()["message"]["feedback"] == "down"

    cleared = client.patch(f"/api/messages/{reply_id}/feedback", json={"feedback": None},
                            headers=_headers(csrf))
    assert cleared.json()["message"]["feedback"] is None


def test_feedback_rejects_invalid_value(client, login_as, db):
    csrf = login_as("user")
    conv = _new_conversation(client, csrf)
    _, reply_id = _answered_turn(db, client, csrf, conv["id"])
    r = client.patch(f"/api/messages/{reply_id}/feedback", json={"feedback": "sideways"},
                      headers=_headers(csrf))
    assert r.status_code in (400, 422)


def test_feedback_on_a_user_message_is_rejected(client, login_as, db):
    csrf = login_as("user")
    conv = _new_conversation(client, csrf)
    user_msg_id, _ = _answered_turn(db, client, csrf, conv["id"])
    r = client.patch(f"/api/messages/{user_msg_id}/feedback", json={"feedback": "up"},
                      headers=_headers(csrf))
    assert r.status_code == 409


# ── 재생성 ────────────────────────────────────────────────────────────────

def test_regenerate_replaces_the_previous_answer(client, login_as, db):
    csrf = login_as("user")
    conv = _new_conversation(client, csrf)
    user_msg_id, old_reply_id = _answered_turn(db, client, csrf, conv["id"], answer="첫 답변")

    r = client.post(f"/api/messages/{user_msg_id}/regenerate", headers=_headers(csrf))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["message"]["processing_status"] == "pending"
    assert body["job_id"]

    items = client.get(f"/api/conversations/{conv['id']}/messages").json()["items"]
    assert old_reply_id not in {m["id"] for m in items}, "이전 답변이 여전히 보인다"


def test_regenerate_requires_a_completed_message(client, login_as):
    csrf = login_as("user")
    conv = _new_conversation(client, csrf)
    r = client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={"content": "아직 처리 중", "client_message_id": CLIENT_MSG_ID},
        headers=_headers(csrf),
    )
    msg_id = r.json()["message"]["id"]
    regen = client.post(f"/api/messages/{msg_id}/regenerate", headers=_headers(csrf))
    assert regen.status_code == 409


def test_regenerate_blocked_once_the_conversation_has_moved_on(client, login_as, db):
    """🔴 revert-to-verify 대상 — _is_last_turn 가드가 없으면 이 시험이 실패해야 한다."""
    csrf = login_as("user")
    conv = _new_conversation(client, csrf)
    user_msg_id, _ = _answered_turn(db, client, csrf, conv["id"])

    later = client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={"content": "다음 질문", "client_message_id": "m1111111111111111111111111111aaaa"},
        headers=_headers(csrf),
    )
    assert later.status_code == 202

    regen = client.post(f"/api/messages/{user_msg_id}/regenerate", headers=_headers(csrf))
    assert regen.status_code == 409, "대화가 이어졌는데도 이전 턴을 재생성할 수 있었다"


def test_regenerate_unknown_message_returns_404(client, login_as):
    csrf = login_as("user")
    r = client.post("/api/messages/does-not-exist/regenerate", headers=_headers(csrf))
    assert r.status_code == 404
