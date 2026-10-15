"""🔴 결과 블록의 이어 보기는 대화 주인의 **지금** 권한으로만 읽는다 (AI 채팅 개선 회차, CLAUDE.md §9.3 권한 · RBAC 음성).

블록에 저장된 인자는 서버가 검증한 값이지만 DB 행이다 — 고쳐졌다고 가정한다. 그래서 이어 보기는 인자를 다시 검증하고, 바꿀 수
있는 칸은 offset · sort 뿐이며, 도구는 지금 권한 · 기능 플래그로 다시 거르고, 읽기는 지금 가시성이다.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest

from app.conversations.models import PROC_DONE, ROLE_ASSISTANT_MSG, ROLE_USER_MSG, Conversation, Message
from app.org.constants import DEFAULT_ORG_ID
from tests.fakes.authz import revoke

pytestmark = pytest.mark.security


def _block(args=None, rid="r1"):
    return {"id": rid, "tool": "my_documents", "kind": "document", "shown": True, "args": args or {}, "total": 3,
            "offset": 0, "returned": 3, "items": []}


@pytest.fixture()
def owner(db, make_user, make_space, make_knowledge_document, login_as):
    user = make_user("paging-owner@goodmit.co.kr", role="user", display_name="주인")
    user.org_id = DEFAULT_ORG_ID
    db.commit()
    space = make_space(name="조직 공간", org_wide=True)
    docs = [make_knowledge_document(space=space, title=f"주인 문서 {i}", created_by=user) for i in range(3)]
    db.commit()
    return {"user": user, "docs": docs}


def _answer(db, user, blocks_, *, deleted=False):
    conversation = Conversation(user_id=user.id, title="블록")
    db.add(conversation)
    db.flush()
    mid = f"m{uuid.uuid4().hex[:12]}"
    question = Message(conversation_id=conversation.id, message_id=mid, role=ROLE_USER_MSG, content="내 문서",
                       processing_status=PROC_DONE)
    db.add(question)
    db.flush()
    reply = Message(conversation_id=conversation.id, message_id=f"a-{mid}-{uuid.uuid4()}", role=ROLE_ASSISTANT_MSG,
                    content="3건입니다.", processing_status=PROC_DONE,
                    structured_payload_json=json.dumps({"results": blocks_}, ensure_ascii=False),
                    deleted_at=datetime(2026, 10, 15) if deleted else None)
    db.add(reply)
    db.commit()
    return question, reply


def test_another_users_message_is_403(client, db, owner, make_user, login_as):
    _q, reply = _answer(db, owner["user"], [_block()])
    make_user("paging-other@goodmit.co.kr", role="user")
    login_as("user", email="paging-other@goodmit.co.kr")
    assert client.get(f"/api/messages/{reply.id}/results/r1").status_code == 403


def test_deleted_reply_user_message_or_unknown_block_is_404(client, db, owner, login_as):
    login_as("user", email="paging-owner@goodmit.co.kr")
    question, reply = _answer(db, owner["user"], [_block()])
    _q2, gone = _answer(db, owner["user"], [_block()], deleted=True)
    assert client.get(f"/api/messages/{gone.id}/results/r1").status_code == 404
    assert client.get(f"/api/messages/{question.id}/results/r1").status_code == 404
    assert client.get(f"/api/messages/{reply.id}/results/r9").status_code == 404
    assert client.get(f"/api/messages/{reply.id}/results/x1").status_code == 422


def test_a_tool_the_user_lost_is_refused(client, db, owner, login_as):
    login_as("user", email="paging-owner@goodmit.co.kr")
    _q, reply = _answer(db, owner["user"], [_block()])
    assert client.get(f"/api/messages/{reply.id}/results/r1").status_code == 200
    revoke(db, "user", "DOCUMENT_READ")
    assert client.get(f"/api/messages/{reply.id}/results/r1").status_code == 403


def test_a_document_that_is_no_longer_visible_disappears(client, db, owner, login_as):
    """다음 쪽은 블록을 만든 때가 아니라 지금 보이는 것이다 — 보관한 문서는 나오지 않는다."""
    login_as("user", email="paging-owner@goodmit.co.kr")
    _q, reply = _answer(db, owner["user"], [_block()])
    owner["docs"][0].archived = True
    db.commit()
    block = client.get(f"/api/messages/{reply.id}/results/r1").json()["block"]
    assert block["total"] == 2
    assert "주인 문서 0" not in [i["title"] for i in block["items"]]


@pytest.mark.parametrize("args", [{"view": "everything"}, {"user_id": "someone"}, {"created_by": "someone"}])
def test_tampered_stored_args_are_rejected(client, db, owner, login_as, args):
    login_as("user", email="paging-owner@goodmit.co.kr")
    _q, reply = _answer(db, owner["user"], [_block(args=args)])
    assert client.get(f"/api/messages/{reply.id}/results/r1").status_code == 422


def test_paging_is_rate_limited_on_its_own_key(client, db, owner, login_as, app, monkeypatch):
    login_as("user", email="paging-owner@goodmit.co.kr")
    _q, reply = _answer(db, owner["user"], [_block()])
    keys = []

    def deny(key):
        keys.append(key)
        return False

    monkeypatch.setattr(app.state.chat_ratelimiter, "allow", deny)
    r = client.get(f"/api/messages/{reply.id}/results/r1")
    assert r.status_code == 429
    assert keys == [f"chat-results:{owner['user'].id}"]
