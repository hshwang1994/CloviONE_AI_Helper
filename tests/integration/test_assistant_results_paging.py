"""답 아래 결과 블록의 다음 쪽 · 다른 정렬 — `GET /api/messages/{id}/results/{rid}` (AI 채팅 개선 회차).

「361건 중 10건」 뒤로 이어 볼 길이 없던 것을 고친다. 이어 보기는 모델을 부르지 않는다 — 블록에 저장된 서버 검증 인자를 다시
검증하고 `offset` · `sort` 만 바꿔 같은 도구를 READ ONLY 로 다시 돈다. 진실은 문서 화면 API 다.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.ai.models import AiUsageRecord
from app.conversations.models import PROC_DONE, ROLE_ASSISTANT_MSG, ROLE_USER_MSG, Conversation, Message
from app.org.constants import DEFAULT_ORG_ID

pytestmark = [pytest.mark.integration, pytest.mark.real_db]


def _block(tool="my_documents", *, args=None, rid="r1"):
    return {"id": rid, "tool": tool, "kind": "document", "shown": True, "args": args or {}, "total": 12, "offset": 0,
            "returned": 10, "items": []}


@pytest.fixture()
def pager(db, make_user, make_space, make_knowledge_document, login_as, fake_clock):
    user = make_user("pager@goodmit.co.kr", role="user", display_name="쪽 넘김")
    user.org_id = DEFAULT_ORG_ID
    db.commit()
    space = make_space(name="조직 공간", org_wide=True)
    base = fake_clock.now() - timedelta(days=30)
    for i in range(12):
        make_knowledge_document(space=space, title=f"내 문서 {i:02d}", created_by=user, updated_at=base + timedelta(hours=i))
    db.commit()
    csrf = login_as("user", email="pager@goodmit.co.kr")
    return {"user": user, "csrf": csrf, "space": space}


def _answer(db, owner, blocks_):
    conversation = Conversation(user_id=owner.id, title="쪽 넘기기")
    db.add(conversation)
    db.flush()
    mid = f"m{uuid.uuid4().hex[:12]}"
    db.add(Message(conversation_id=conversation.id, message_id=mid, role=ROLE_USER_MSG, content="내가 만든 문서",
                   processing_status=PROC_DONE))
    db.flush()
    reply = Message(conversation_id=conversation.id, message_id=f"a-{mid}-{uuid.uuid4()}", role=ROLE_ASSISTANT_MSG,
                    content="작성하신 문서는 총 12건입니다.", processing_status=PROC_DONE,
                    structured_payload_json=json.dumps({"kind": "assistant", "results": blocks_}, ensure_ascii=False))
    db.add(reply)
    db.commit()
    return reply


def test_next_page_reruns_stored_args(client, db, pager):
    reply = _answer(db, pager["user"], [_block(args={"sort": "recent"})])
    r = client.get(f"/api/messages/{reply.id}/results/r1", params={"offset": 10})
    assert r.status_code == 200, r.text
    block = r.json()["block"]
    truth = client.get("/api/knowledge/documents",
                       params={"mine": "true", "sort": "recent", "limit": 10, "offset": 10}).json()
    assert (block["id"], block["shown"], block["offset"], block["total"]) == ("r1", True, 10, truth["total"])
    assert [i["title"] for i in block["items"]] == [i["title"] for i in truth["items"]]
    assert block["returned"] == 2 and block["truncated"] is False


def test_sort_override_only_where_supported(client, db, pager):
    reply = _answer(db, pager["user"], [_block(), _block("search_documents", args={"query": "문서"}, rid="r2")])
    by_title = client.get(f"/api/messages/{reply.id}/results/r1", params={"offset": 0, "sort": "title"}).json()["block"]
    assert [i["title"] for i in by_title["items"]] == [f"내 문서 {i:02d}" for i in range(10)]
    assert by_title["sort"] == "title"
    assert client.get(f"/api/messages/{reply.id}/results/r1", params={"sort": "bogus"}).status_code == 422
    assert client.get(f"/api/messages/{reply.id}/results/r2", params={"sort": "recent"}).status_code == 422


def test_offset_past_the_tool_bound_is_422(client, db, pager):
    reply = _answer(db, pager["user"], [_block(), _block("search_documents", args={"query": "문서"}, rid="r2")])
    assert client.get(f"/api/messages/{reply.id}/results/r1", params={"offset": 201}).status_code == 422
    assert client.get(f"/api/messages/{reply.id}/results/r2", params={"offset": 41}).status_code == 422
    assert client.get(f"/api/messages/{reply.id}/results/r2", params={"offset": 8}).status_code == 200


def test_paging_never_calls_a_provider_or_records_usage(client, db, pager):
    reply = _answer(db, pager["user"], [_block()])
    before = db.execute(select(func.count()).select_from(AiUsageRecord)).scalar_one()
    for offset in (0, 10):
        assert client.get(f"/api/messages/{reply.id}/results/r1", params={"offset": offset}).status_code == 200
    db.expire_all()
    assert db.execute(select(func.count()).select_from(AiUsageRecord)).scalar_one() == before
