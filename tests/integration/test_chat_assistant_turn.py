"""AI 도우미 한 차례 — 채팅이 실제로 답하고, 권한이 도구보다 먼저 걸린다 (D-535 · D-537 · D-538).

qa-contract-replaced-by: tests/integration/test_chat_answers_from_retrieval.py
qa-contract-replaced-by: tests/integration/test_chat_handler.py
qa-contract-replaced-by: tests/integration/test_chat_ticket_routing_contract.py
qa-contract-replaced-by: tests/integration/test_chat_notion_refusal.py
qa-contract-replaced-by: tests/unit/test_chat_extract_text.py

## 무엇이 바뀌었나

예전 채팅은 문서 조각만 찾아 0건이면 모델을 부르지 않고 「근거를 찾지 못했다」를 저장했다. 이제 한 차례는 도구를 쓰는
대화다. 옛 파일이 지키던 계약은 그대로 있고 이 파일이 새 모양으로 잰다.

  * 답이 나오고 출처가 함께 나온다 - 출처의 경로는 서버가 만든다
  * 모델이 받는 것은 **권한을 지난 것뿐**이다 - 답 글이 아니라 제공자가 받은 도구 결과 칸에서 본다(D-202)
  * 「찾지 못함」은 정상 답이다(실패가 아니다), 「AI 를 쓸 수 없음」은 요청 자체가 409 다
  * 생성이 막히면 사용자 메시지가 실패로 남아 「다시 시도」가 산다
  * 바깥으로 HTTP 를 보내지 않는다(가짜 제공자 말고는)
  * 한도는 성공한 차례만 한 칸이다 - 라운드가 몇 번이든 차례 하나가 사용 기록 한 행이다(D-537)
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.ai import catalog
from app.ai.gateway import contract
from app.ai.index import service as index_service
from app.ai.models import AiUsageRecord
from app.ai.providers import base
from app.conversations.models import PROC_DONE, PROC_FAILED, Message
from app.jobs.handlers.chat_message import handle_chat_message
from app.jobs.worker import Worker, WorkerContext
from app.knowledge import versions
from app.knowledge.models import Document, KnowledgeSpace
from app.org.constants import DEFAULT_ORG_ID
from tests.fakes.ai import ScriptedToolAdapter, install_runtime, tool_call, unsupported_tools

pytestmark = pytest.mark.integration

MSG_ID = "h0123456789abcdef0123456789abcdef"


class TopicEmbed(contract.EmbedAdapter):
    """주제표로 벡터를 만든다 - 주제에 안 걸리는 글은 어느 주제와도 멀다(벡터 레인이 무엇에나 답하지 않게)."""

    TOPICS = {"leave": ("연차", "휴가", "반차", "보상금")}

    def __init__(self):
        self.name = "topic"
        self.model = catalog.DEFAULT_EMBEDDING_MODEL_ID
        self.dim = catalog.VECTOR_DIM

    def capability(self):
        return contract.available(contract.CAP_EMBED, model=self.model)

    def _vector(self, text: str) -> tuple[float, ...]:
        values = [0.0] * self.dim
        for axis, (_, words) in enumerate(sorted(self.TOPICS.items())):
            if any(word in text for word in words):
                values[axis] = 1.0
        if not any(values):
            values[-1] = 1.0
        norm = sum(v * v for v in values) ** 0.5
        return tuple(v / norm for v in values)

    def embed(self, texts, *, kind=catalog.KIND_PASSAGE):
        return contract.EmbedResult(status=contract.STATUS_OK, model=self.model, dim=self.dim,
                                    vectors=tuple(self._vector(t) for t in texts))


def _gateway() -> contract.Gateway:
    return contract.Gateway(enabled=True, embed_adapter=TopicEmbed())


def _body(*paragraphs: str) -> dict:
    return {"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": p}]} for p in paragraphs
    ]}


@pytest.fixture()
def chatter(db, make_user):
    # **일반 사용자다.** admin 은 `confidential` 을 여는 권한을 가져 아래 권한 시험이 아무것도 증명하지 못한다.
    user = make_user("chatter@goodmit.co.kr", role="user", display_name="채팅 사용자")
    user.org_id = DEFAULT_ORG_ID
    db.flush()
    return user


@pytest.fixture()
def space(db):
    row = KnowledgeSpace(org_id=DEFAULT_ORG_ID, name="사내 규정", slug="rules", owner_kind="organization")
    db.add(row)
    db.flush()
    return row


def _seed_doc(db, space, title, *paragraphs):
    doc = Document(space_id=space.id, title=title, archived=False)
    db.add(doc)
    db.flush()
    versions.snapshot(db, doc, _body(*paragraphs), author_id=None)
    db.flush()
    return doc


@pytest.fixture()
def assistant(app, settings, fake_clock):
    """가짜 제공자를 끼운 진짜 런타임과 그것을 실은 워커. **메시지를 보내기 전에** 부른다 - AI 가 꺼져 있으면 409 다."""

    def build(adapter, gateway=None):
        gateway = gateway or _gateway()
        runtime = install_runtime(app, adapter)
        ctx = WorkerContext(
            settings=settings, clock=fake_clock, outbound_client=app.state.outbound_client,
            extras={"ai_gateway": gateway, "ai_runtime": runtime, "session_factory": app.state.session_factory,
                    "settings_cache": app.state.settings_cache},
        )
        return Worker(app.state.session_factory, fake_clock, {"chat_message": handle_chat_message}, ctx,
                      poll_interval=0.01)

    return build


@pytest.fixture()
def posted(client, login_as, chatter, db):
    db.commit()
    csrf = login_as("user", email="chatter@goodmit.co.kr")
    conv = client.post("/api/conversations", json={}, headers={"X-CSRF-Token": csrf}).json()["conversation"]
    return {"conversation_id": conv["id"], "csrf": csrf}


def _send(client, posted, content, *, message_id=MSG_ID, screen_context=None, expect=202):
    body = {"content": content, "client_message_id": message_id}
    if screen_context is not None:
        body["screen_context"] = screen_context
    r = client.post(f"/api/conversations/{posted['conversation_id']}/messages", json=body,
                    headers={"X-CSRF-Token": posted["csrf"]})
    assert r.status_code == expect, r.text
    return r


def _rows(db, conversation_id):
    return db.execute(
        Message.__table__.select().where(Message.conversation_id == conversation_id).order_by(Message.seq)
    ).mappings().all()


def _replies(db, conversation_id):
    return [r for r in _rows(db, conversation_id) if r["role"] == "assistant"]


def _user_message(db, conversation_id, index=0):
    return [r for r in _rows(db, conversation_id) if r["role"] == "user"][index]


def _stored(row) -> dict:
    return json.loads(row["structured_payload_json"])


def _usage(db, user_id):
    return db.execute(select(AiUsageRecord).where(AiUsageRecord.user_id == user_id)
                      .order_by(AiUsageRecord.created_at)).scalars().all()


# ── 1. 답과 출처 ─────────────────────────────────────────────────────────────


def test_a_document_question_answers_with_document_sources(client, db, space, assistant, posted):
    _seed_doc(db, space, "연차 규정", "연차는 입사 1년 뒤부터 15일이 생긴다.")
    gateway = _gateway()
    index_service.run_once(db, gateway=gateway, limit=50)
    db.commit()
    adapter = ScriptedToolAdapter([tool_call("search_documents", {"query": "연차"}), "연차는 15일입니다."])
    worker = assistant(adapter, gateway)

    _send(client, posted, "연차는 며칠인가요?")
    worker.run_once()

    reply = _replies(db, posted["conversation_id"])
    assert [r["content"] for r in reply] == ["연차는 15일입니다."]
    stored = _stored(reply[0])
    assert stored["kind"] == "assistant"
    assert stored["status"] == "ok"
    assert stored["mode"] == "tools"
    assert [s["title"] for s in stored["sources"]] == ["연차 규정"]
    # 출처는 **눌러서 갈 수 있는 앱 안 주소**다 - 서버가 만든다.
    assert stored["sources"][0]["route"].startswith("/knowledge/")
    # `total` 은 권한 안의 전체 수다 — 화면의 「확인한 내용」이 「N건 중 M건」을 쓴다(D-567).
    assert stored["tools"] == [{"name": "search_documents", "label": "사내 문서 검색", "ok": True, "count": 1,
                                "total": 1, "query": "연차"}]
    assert stored["rounds"] == 2
    assert stored["notice"] is None
    assert _user_message(db, posted["conversation_id"])["processing_status"] == PROC_DONE
    # 도구 결과는 둘째 라운드의 **데이터 칸** 안에 실렸다(D-202).
    result = adapter.tool_results(1)[0].content
    assert "연차는 입사 1년 뒤부터 15일이 생긴다." in result
    assert result.index("<<<CLOVI_DATA:") < result.index("연차는 입사 1년") < result.index("<<<END_CLOVI_DATA:")
    # 첫 라운드는 권한으로 거른 도구 목록과 함께 나갔다.
    first = adapter.converse_calls[0]
    assert first["tool_choice"] == base.TOOL_CHOICE_AUTO
    assert "search_documents" in {t.name for t in first["tools"]}


def test_a_general_question_is_answered_without_any_document(client, db, assistant, posted):
    """「검색 0건 → 모델을 안 부름」 구조가 없다 - 일반 질문은 모델이 바로 답한다."""
    adapter = ScriptedToolAdapter(["SLA 는 서비스 수준 합의입니다."])
    worker = assistant(adapter)

    _send(client, posted, "SLA 가 뭐야?")
    worker.run_once()

    assert [r["content"] for r in _replies(db, posted["conversation_id"])] == ["SLA 는 서비스 수준 합의입니다."]
    assert len(adapter.converse_calls) == 1
    # 오늘 날짜와 묻는 사람, 화면 길잡이는 시스템 쪽 문맥 줄이다.
    system = adapter.converse_calls[0]["system"]
    assert "묻는 사람은 채팅 사용자입니다." in system
    assert "/my-tickets" in system


def test_nothing_found_is_an_answer_not_a_failure(client, db, space, assistant, posted):
    """도구가 0건을 돌려준 답은 정상 답이다 - 같은 질문을 다시 넣어도 같은 결과라 실패로 두지 않는다."""
    gateway = _gateway()
    db.commit()
    adapter = ScriptedToolAdapter([
        tool_call("search_documents", {"query": "주차장 배정"}),
        "사내 문서에서 '주차장 배정'과 맞는 문서를 찾지 못했습니다.",
    ])
    worker = assistant(adapter, gateway)

    _send(client, posted, "사옥 주차장 배정 기준 알려줘")
    worker.run_once()

    reply = _replies(db, posted["conversation_id"])[0]
    stored = _stored(reply)
    assert stored["notice"] == "no_results"
    assert stored["tools"][0]["count"] == 0
    assert "error_notice" not in stored
    assert _user_message(db, posted["conversation_id"])["processing_status"] == PROC_DONE
    note = json.loads(adapter.tool_results(1)[0].content.split("\n")[2])
    assert note["items"] == [] and "찾아본 낱말" in note["note"]


# ── 2. 권한이 도구보다 먼저 걸린다 (면제되지 않는 검증) ─────────────────────


def test_a_document_the_user_cannot_see_never_reaches_the_model(client, db, make_user, assistant, posted):
    """확인 지점은 답 글이 아니라 **제공자가 받은 도구 결과**다 - 모델이 그 문장을 안 쓰기로 했을 수도 있다(D-202)."""
    other = make_user("other@goodmit.co.kr", role="user", display_name="남")
    other.org_id = DEFAULT_ORG_ID
    mine = KnowledgeSpace(org_id=DEFAULT_ORG_ID, name="내 공간", slug="mine", owner_kind="organization")
    db.add(mine)
    db.flush()
    _seed_doc(db, mine, "공개 규정", "연차는 15일이다.")
    secret = _seed_doc(db, mine, "대외비 규정", "특별 연차 보상금은 300만원이다.")
    secret.confidential = True
    secret.created_by = other.id
    db.flush()
    gateway = _gateway()
    index_service.run_once(db, gateway=gateway, limit=50)
    db.commit()
    adapter = ScriptedToolAdapter([
        [tool_call("search_documents", {"query": "연차 보상금"}), tool_call("get_document", {"ref": secret.id})],
        "답입니다.",
    ])
    worker = assistant(adapter, gateway)

    _send(client, posted, "연차 보상금 얼마인가요")
    worker.run_once()

    results = adapter.tool_results(1)
    assert len(results) == 2
    # 검색은 실제로 돌았고 볼 수 있는 문서는 실렸다 - 아무것도 안 실려서 통과하는 시험이 아니다.
    assert "연차는 15일이다." in results[0].content
    payload = "\n".join(r.content for r in results)
    assert "300만원" not in payload
    assert "대외비 규정" not in payload
    # 범위 밖 문서를 콕 집어 읽어도 없는 문서와 **같은** `not_found` 다.
    assert '"error": "not_found"' in results[1].content
    stored = _stored(_replies(db, posted["conversation_id"])[0])
    assert all(s["title"] != "대외비 규정" for s in stored["sources"])


# ── 3. 막힘 · 바깥 호출 · 한도 ───────────────────────────────────────────────


def test_when_generation_is_blocked_the_message_fails_and_says_why(client, db, assistant, posted):
    """키가 거부되면 왜인지 말하고 사용자 메시지는 실패로 남는다 - 「다시 시도」가 산다."""
    adapter = ScriptedToolAdapter([base.converse_failure(base.ERROR_AUTH, "http_401", http_status=401)])
    worker = assistant(adapter)

    _send(client, posted, "연차 며칠인가요")
    worker.run_once()

    reply = _replies(db, posted["conversation_id"])[0]
    assert "AI 연결이 끊겨 있습니다" in reply["content"]
    assert "-fail-" in reply["message_id"]
    assert _stored(reply)["error_notice"] is True
    user_row = _user_message(db, posted["conversation_id"])
    assert user_row["processing_status"] == PROC_FAILED
    assert user_row["error_code"] == "assistant_credential_error"


def test_a_turn_does_not_call_out_to_anything(client, db, space, assistant, posted, fake_http):
    """**아무 데도 HTTP 를 안 보낸다** - 제공자 자리는 가짜이고 도구는 DB 만 읽는다."""
    _seed_doc(db, space, "연차 규정", "연차는 15일이다.")
    gateway = _gateway()
    index_service.run_once(db, gateway=gateway, limit=50)
    db.commit()
    worker = assistant(ScriptedToolAdapter([tool_call("search_documents", {"query": "연차"}), "답입니다."]), gateway)
    fake_http.requests.clear()

    _send(client, posted, "연차 며칠인가요")
    worker.run_once()

    assert fake_http.requests == [], f"채팅이 외부로 나갔다: {[str(r.url) for r in fake_http.requests]}"


def test_quota_counts_only_a_turn_that_answered(client, db, chatter, assistant, posted, fake_clock):
    from app.quotas.service import PERIOD_DAY, used

    adapter = ScriptedToolAdapter([base.converse_failure(base.ERROR_TRANSIENT, "timeout"), "답입니다."])
    worker = assistant(adapter)
    now = fake_clock.now()

    _send(client, posted, "첫 질문", message_id="a" * 32)
    worker.run_once()
    before = used(db, user_id=chatter.id, period=PERIOD_DAY, now=now)

    _send(client, posted, "둘째 질문", message_id="b" * 32)
    worker.run_once()
    after = used(db, user_id=chatter.id, period=PERIOD_DAY, now=now)

    assert (before, after) == (0, 1)


def test_a_multi_round_turn_is_one_usage_row(client, db, space, chatter, assistant, posted):
    """라운드가 셋이어도 사람의 요청 한 번이다 - 사용 기록 한 행, 도구는 이름만(D-537)."""
    _seed_doc(db, space, "연차 규정", "연차는 15일이다.")
    gateway = _gateway()
    index_service.run_once(db, gateway=gateway, limit=50)
    db.commit()
    adapter = ScriptedToolAdapter([
        tool_call("my_work", {"view": "assigned", "include_done": None}),
        tool_call("search_documents", {"query": "연차"}),
        "정리했습니다.",
    ])
    worker = assistant(adapter, gateway)

    _send(client, posted, "내 일이랑 연차 규정 알려줘")
    worker.run_once()

    rows = _usage(db, chatter.id)
    assert len(rows) == 1
    row = rows[0]
    assert (row.action_key, row.status, row.rounds, row.tool_calls, row.mode) == (
        "assistant.chat", "ok", 3, 2, "tools")
    assert json.loads(row.tool_names_json) == ["my_work", "search_documents"]
    assert row.prompt_slot == "assistant"
    # 세 라운드의 토큰을 더한 값이다(가짜 제공자는 라운드마다 10 · 5).
    assert (row.input_tokens, row.output_tokens) == (30, 15)


# ── 4. 처리 중 · 화면 대상 · 대체 모드 · 이력 ─────────────────────────────────


def test_progress_is_committed_while_the_turn_runs(client, db, space, assistant, posted, app):
    """제공자를 부르는 동안 「처리 중」과 진행 문구가 **다른 세션에서** 보인다(커밋했다)."""
    seen: list = []

    def peek(request):
        with app.state.session_factory() as other:
            row = other.execute(select(Message).where(Message.message_id == MSG_ID)).scalar_one()
            seen.append((row.processing_status, json.loads(row.structured_payload_json or "{}").get("progress")))
        return "답입니다."

    worker = assistant(ScriptedToolAdapter([peek]))
    _send(client, posted, "안녕")
    worker.run_once()

    status, progress = seen[0]
    assert status == "processing"
    assert progress["label"] == "질문을 살펴보고 있습니다."


def test_the_screen_target_is_reread_with_the_owners_permission(client, db, space, make_user, assistant, posted):
    """서랍이 보낸 화면 대상은 서버가 다시 읽은 것만 싣는다 - 범위 밖 대상은 아무것도 싣지 않는다."""
    visible = _seed_doc(db, space, "연차 규정", "연차는 입사 1년 뒤부터 15일이 생긴다.")
    other = make_user("owner2@goodmit.co.kr", role="user", display_name="남")
    hidden = _seed_doc(db, space, "대외비 문서", "숨은 내용입니다.")
    hidden.confidential = True
    hidden.created_by = other.id
    db.commit()
    adapter = ScriptedToolAdapter(["답입니다."])
    worker = assistant(adapter)

    _send(client, posted, "이 문서 요약해 줘", screen_context={"kind": "document", "ref": visible.id, "label": "문서"})
    worker.run_once()
    _send(client, posted, "이 문서 요약해 줘", message_id="c" * 32,
          screen_context={"kind": "document", "ref": hidden.id, "label": "문서"})
    worker.run_once()

    first = adapter.converse_calls[0]["turns"][-1].text
    assert "사용자가 지금 보는 화면의 대상입니다." in first
    assert "연차는 입사 1년 뒤부터 15일이 생긴다." in first
    second = adapter.converse_calls[1]["turns"][-1].text
    assert "숨은 내용입니다." not in second
    assert "사용자가 지금 보는 화면의 대상입니다." not in second
    # 화면 대상은 사용자 메시지에 남아 다시 시도에도 같은 대상으로 묻는다.
    assert _stored(_user_message(db, posted["conversation_id"]))["screen_context"]["ref"] == visible.id


def test_a_provider_that_refuses_tools_falls_back_to_server_search(client, db, space, chatter, assistant, posted):
    """도구를 받지 않는 요금제는 능력을 적고 서버 검색 + 도구 없는 한 번으로 답한다. 다음 차례는 처음부터 그 길이다."""
    _seed_doc(db, space, "연차 규정", "연차는 입사 1년 뒤부터 15일이 생긴다.")
    gateway = _gateway()
    index_service.run_once(db, gateway=gateway, limit=50)
    db.commit()
    adapter = ScriptedToolAdapter([unsupported_tools(), "검색 자료로 답했습니다.", "다시 검색 자료로 답했습니다."])
    worker = assistant(adapter, gateway)

    _send(client, posted, "연차 규정 알려줘")
    worker.run_once()

    second = adapter.converse_calls[1]
    assert second["tools"] == ()
    assert "서버가 질문으로 먼저 찾은 사내 자료입니다." in second["turns"][-1].text
    assert "연차는 입사 1년 뒤부터 15일이 생긴다." in second["turns"][-1].text
    stored = _stored(_replies(db, posted["conversation_id"])[0])
    assert stored["mode"] == "search_only"
    assert [s["title"] for s in stored["sources"]] == ["연차 규정"]

    _send(client, posted, "반차는?", message_id="d" * 32)
    worker.run_once()
    assert len(adapter.converse_calls) == 3
    assert adapter.converse_calls[2]["tools"] == ()
    assert _usage(db, chatter.id)[-1].mode == "search_only"


def test_the_next_turn_carries_the_previous_question_and_answer(client, db, assistant, posted):
    adapter = ScriptedToolAdapter(["첫 답입니다.", "둘째 답입니다."])
    worker = assistant(adapter)

    _send(client, posted, "첫 질문", message_id="e" * 32)
    worker.run_once()
    _send(client, posted, "이어서 묻습니다", message_id="f" * 32)
    worker.run_once()

    turns = adapter.converse_calls[1]["turns"]
    assert [type(t).__name__ for t in turns] == ["UserTurn", "AssistantTurn", "UserTurn"]
    assert turns[0].text == "첫 질문"
    assert turns[1].text == "첫 답입니다."
    assert turns[2].text == "이어서 묻습니다"


def test_when_ai_is_off_the_send_is_refused_before_quota_and_queue(client, db, app, chatter, posted):
    """「AI 를 쓸 수 없음」은 답이 아니라 409 다 - 한도를 예약하지 않고 잡도 만들지 않는다(D-538)."""
    from app.jobs.models import Job
    from tests.fakes.ai import configure_ai

    configure_ai(app, enabled=False)
    before = db.execute(select(Job)).scalars().all()
    r = _send(client, posted, "안녕", expect=409)
    body = r.json()
    assert body["error"]["code"] == "ai_unavailable"
    assert body["error"]["details"]["reason"] == "off"
    assert len(db.execute(select(Job)).scalars().all()) == len(before)
    assert [m for m in _rows(db, posted["conversation_id"])] == []



# ── 출처의 순서와 상한 · 닫힌 답 (D-569) ─────────────────────────────────────


def test_sources_cited_in_the_answer_come_first(client, db, space, assistant, posted):
    first = _seed_doc(db, space, "연차 규정", "연차는 입사 1년 뒤부터 15일이 생긴다.")
    second = _seed_doc(db, space, "연차 보상 안내", "쓰지 못한 연차는 보상금으로 받는다.")
    gateway = _gateway()
    index_service.run_once(db, gateway=gateway, limit=50)
    db.commit()
    answer = f"보상은 [연차 보상 안내](/knowledge/{second.id}) 에 있습니다."
    adapter = ScriptedToolAdapter([tool_call("search_documents", {"query": "연차"}), answer])
    worker = assistant(adapter, gateway)

    _send(client, posted, "연차 보상은 어떻게 되나요?")
    worker.run_once()

    stored = _stored(_replies(db, posted["conversation_id"])[0])
    ids = [s["id"] for s in stored["sources"]]
    assert set(ids) == {first.id, second.id}
    assert ids[0] == second.id, "답에 인용된 출처가 앞에 서지 않았다"


def test_the_source_list_is_capped_and_keeps_cited_ones_inside_the_cap():
    from app.ai.assistant import results
    from app.ai.assistant import turn as turn_mod

    many = tuple({"type": "ticket", "id": f"t-{i:03d}", "title": f"티켓 {i}", "route": f"/tickets/t-{i:03d}",
                  "key": f"ABCDEF-{i}"} for i in range(40))
    execution = results.ok("search_tickets", [{"n": i} for i in range(10)], total=40, sources=many)
    plain = turn_mod._sources([execution], "")
    assert len(plain) == turn_mod.MAX_SOURCES == 30
    assert [s["id"] for s in plain[:2]] == ["t-000", "t-001"], "인용이 없으면 도구가 준 순서다"
    cited = turn_mod._sources([execution], "끝으로 ABCDEF-39 와 /tickets/t-035 를 보세요. ABCDEF-3 은 아닙니다.")
    assert [s["id"] for s in cited[:3]] == ["t-003", "t-035", "t-039"]
    assert len(cited) == 30
    # 「ABCDEF-3」 이 「ABCDEF-39」 안에서 걸리지 않는다 — 키는 낱말 경계로 본다.
    only = turn_mod._sources([execution], "ABCDEF-39 만 봅니다.")
    assert only[0]["id"] == "t-039" and only[1]["id"] == "t-000"
    # 출처마다 인용 여부를 싣는다 — 하나도 인용하지 않은 답은 화면이 「찾아본 자료」로 접는다(P-133).
    assert only[0]["cited"] is True and all(s["cited"] is False for s in only[1:])
    assert not any(s["cited"] for s in plain), "인용이 없는 답은 모두 cited=False"


def test_a_source_title_in_the_answer_counts_as_cited_but_short_titles_do_not():
    from app.ai.assistant import results
    from app.ai.assistant import turn as turn_mod

    docs = ({"type": "document", "id": "d-1", "title": "해외 출장 체크리스트", "route": "/knowledge/d-1"},
            {"type": "document", "id": "d-2", "title": "회의록", "route": "/knowledge/d-2"})
    execution = results.ok("search_documents", [{"n": 1}, {"n": 2}], total=2, sources=docs)
    out = turn_mod._sources([execution], "해외 출장 체크리스트를 보면 됩니다. 회의록에는 없습니다.")
    assert [(s["id"], s["cited"]) for s in out] == [("d-1", True), ("d-2", False)]


def test_a_tool_failure_then_a_refused_last_round_closes_with_the_found_sources(client, db, space, assistant, posted):
    """도구 하나가 실패해도 차례는 이어지고, 마지막 라운드(도구 없이 답하라)를 제공자가 거절하면 찾은 자료로 닫는다."""
    from app.ai import runtime as runtime_mod

    _seed_doc(db, space, "연차 규정", "연차는 입사 1년 뒤부터 15일이 생긴다.")
    gateway = _gateway()
    index_service.run_once(db, gateway=gateway, limit=50)
    db.commit()
    refused = base.converse_failure(base.ERROR_REQUEST, "bad_request", http_status=400)
    adapter = ScriptedToolAdapter([
        tool_call("get_ticket", {"key": "ZZZZZZ-1"}),
        tool_call("search_documents", {"query": "연차"}),
        tool_call("search_documents", {"query": "연차 규정"}),
        tool_call("my_work", {"view": "assigned"}),
        refused,
    ])
    worker = assistant(adapter, gateway)

    _send(client, posted, "연차 규정과 내 일을 알려 줘")
    worker.run_once()

    reply = _replies(db, posted["conversation_id"])[0]
    stored = _stored(reply)
    assert reply["content"] == runtime_mod.CLOSE_WITHOUT_ANSWER
    assert stored["notice"] == "closed_without_answer"
    assert [s["title"] for s in stored["sources"]] == ["연차 규정"]
    assert [t["ok"] for t in stored["tools"]][:2] == [False, True], "실패한 도구가 「확인한 내용」에 남아야 한다"
    assert _user_message(db, posted["conversation_id"])["processing_status"] == PROC_DONE


def test_only_list_tools_carry_a_total_for_the_checked_lines():
    from app.ai.assistant import results
    from app.ai.assistant import turn as turn_mod

    listed = results.ok("search_tickets", [{"n": 1}], total=25)
    single = results.ok("get_ticket", [{"n": 1}])
    unknown = results.ok("search_documents", [{"n": 1}], total=None)
    failed = results.error("my_work", results.ERROR_UNAVAILABLE)
    rows = {row["name"]: row for row in turn_mod._tools([listed, single, unknown, failed])}
    assert rows["search_tickets"]["total"] == 25 and rows["search_tickets"]["count"] == 1
    assert rows["get_ticket"]["total"] is None
    assert rows["search_documents"]["total"] is None
    assert rows["my_work"]["total"] is None and rows["my_work"]["ok"] is False


# ── 답을 만드는 동안 지운 대화 ─────────────────────────────────────────────────


def test_deleting_a_conversation_mid_turn_sends_no_failure_notification(client, db, assistant, posted, chatter):
    """답을 만드는 동안 사람이 대화를 지우면 처리기는 조용히 끝난다 — 예전에는 걷힌 행에 답을 쓰다 실패해
    지운 사람에게 「요청 처리에 실패했습니다」 알림이 갔다."""
    from app.jobs.models import STATUS_SUCCEEDED, Job
    from app.notifications.models import Notification

    def delete_meanwhile(request):
        r = client.delete(f"/api/conversations/{posted['conversation_id']}", headers={"X-CSRF-Token": posted["csrf"]})
        assert r.status_code == 200
        return "답입니다."

    worker = assistant(ScriptedToolAdapter([delete_meanwhile]))
    _send(client, posted, "안녕")
    worker.run_once()

    db.expire_all()
    job = db.execute(select(Job).where(Job.conversation_id == posted["conversation_id"])).scalar_one()
    assert job.status == STATUS_SUCCEEDED
    assert _rows(db, posted["conversation_id"]) == []
    assert db.execute(select(Notification).where(Notification.user_id == chatter.id)).scalars().all() == []


def test_a_queued_reply_of_a_deleted_conversation_is_cancelled(client, db, assistant, posted):
    """대기 중인 답 잡은 대화를 지울 때 취소된다 — 걷힌 페이로드로 돌지 않고 AI 사용 한도의 대기 몫도 놓는다."""
    from app.jobs.models import STATUS_CANCELLED, Job

    assistant(ScriptedToolAdapter(["돌지 않는 답"]))
    _send(client, posted, "기다리는 질문")
    r = client.delete(f"/api/conversations/{posted['conversation_id']}", headers={"X-CSRF-Token": posted["csrf"]})
    assert r.status_code == 200
    db.expire_all()
    job = db.execute(select(Job).where(Job.conversation_id == posted["conversation_id"])).scalar_one()
    assert job.status == STATUS_CANCELLED
    assert json.loads(job.payload_json).get("purged") is True


def test_a_purged_payload_finishes_quietly(db, assistant, chatter, fake_clock):
    """지운 대화의 잡이 이미 워커 손에 있었어도(걷힌 페이로드) 실패로 올리지 않는다."""
    from app.jobs import repository as jobs_repo
    from app.jobs.models import STATUS_SUCCEEDED
    from app.notifications.models import Notification

    worker = assistant(ScriptedToolAdapter(["쓰이지 않는 답"]))
    job = jobs_repo.enqueue(db, job_type="chat_message", now=fake_clock.now(), user_id=chatter.id,
                            payload={"conversation_id": "gone", "message_id": "gone", "purged": True},
                            conversation_id=None, message_id="gone", idempotency_key="chatmsg:gone:gone")
    db.commit()
    worker.run_once()
    db.expire_all()
    db.refresh(job)
    assert job.status == STATUS_SUCCEEDED
    assert db.execute(select(Notification).where(Notification.user_id == chatter.id)).scalars().all() == []


# ── 결과 블록 · 의도 제목 · 이어지는 질문 (AI 채팅 개선 회차) ─────────────────────────


def _my_docs(db, space, owner, n):
    docs = []
    for i in range(n):
        doc = _seed_doc(db, space, f"내 문서 {i:02d}", f"본문 {i}")
        doc.created_by = owner.id
        docs.append(doc)
    db.commit()
    return docs


def test_a_shown_list_is_persisted_as_a_compact_block(client, db, space, assistant, posted, chatter):
    """모델이 `show` 를 켠 목록은 답에 블록으로 남는다 — 화면이 그 목록을 그리므로 답 글은 결론만 쓴다. 블록에는 허용 칸만 있고
    (발췌 없음), 그 항목은 출처에서 「보인 것」이라 답 글에 없어도 「찾아본 자료」로 접히지 않는다."""
    _my_docs(db, space, chatter, 3)
    adapter = ScriptedToolAdapter([tool_call("my_documents", {"show": True}), "작성하신 문서는 총 3건입니다."])
    worker = assistant(adapter)
    _send(client, posted, "내가 만든 문서")
    worker.run_once()

    stored = _stored(_replies(db, posted["conversation_id"])[0])
    [block] = stored["results"]
    assert (block["tool"], block["kind"], block["shown"], block["total"], block["returned"]) == (
        "my_documents", "document", True, 3, 3)
    assert block["args"] == {} and block["list_route"] == f"/knowledge?author={chatter.id}&sort=recent"
    assert all("excerpt" not in item and item["route"].startswith("/knowledge/") for item in block["items"])
    assert all(s.get("shown") for s in stored["sources"]) and len(stored["sources"]) == 3
    assert stored["tools"] == [{"name": "my_documents", "label": "내 문서", "ok": True, "count": 3, "total": 3}]


def test_an_unshown_search_stays_searched_only(client, db, space, assistant, posted, chatter):
    """`show` 없이 살펴본 검색은 블록으로 서지 않고(기억에만 남는다) 출처도 「보인 것」이 아니다(D-581 그대로)."""
    _my_docs(db, space, chatter, 2)
    adapter = ScriptedToolAdapter([tool_call("my_documents", {"query": "없는 주제"}), "찾지 못했습니다."])
    worker = assistant(adapter)
    _send(client, posted, "없는 주제 문서")
    worker.run_once()

    stored = _stored(_replies(db, posted["conversation_id"])[0])
    assert [b["shown"] for b in stored["results"]] == [False]
    assert not any(s.get("shown") for s in stored["sources"])


def test_first_reply_sets_the_intent_title(client, db, space, assistant, posted, chatter):
    """첫 답이 끝나면 다듬은 질문(「나에게 할당된 티켓」)이 도구와 인자로 지은 제목(「내 담당 티켓 조회」)으로 바뀐다."""
    adapter = ScriptedToolAdapter([tool_call("my_work", {"view": "assigned", "show": True}), "담당 티켓은 0건입니다."])
    worker = assistant(adapter)
    _send(client, posted, "나에게 할당된 티켓 보여줘")
    assert client.get(f"/api/conversations/{posted['conversation_id']}/messages").json()["conversation"]["title"] == \
        "나에게 할당된 티켓"
    worker.run_once()
    assert client.get(f"/api/conversations/{posted['conversation_id']}/messages").json()["conversation"]["title"] == \
        "내 담당 티켓 조회"


def test_a_rename_during_the_first_turn_is_kept(client, db, space, assistant, posted, chatter):
    """답을 기다리는 동안 사람이 이름을 바꿨으면 의도 제목이 그 이름을 덮지 않는다(조건부 갱신)."""
    def rename_meanwhile(request):
        r = client.patch(f"/api/conversations/{posted['conversation_id']}", json={"title": "내가 붙인 이름"},
                         headers={"X-CSRF-Token": posted["csrf"]})
        assert r.status_code == 200
        return [tool_call("my_work", {"view": "assigned"})]

    worker = assistant(ScriptedToolAdapter([rename_meanwhile, "담당 티켓은 0건입니다."]))
    _send(client, posted, "나에게 할당된 티켓 보여줘")
    worker.run_once()
    assert client.get(f"/api/conversations/{posted['conversation_id']}/messages").json()["conversation"]["title"] == \
        "내가 붙인 이름"


def test_next_page_follow_up_reuses_previous_args(client, db, space, assistant, posted, chatter):
    """「다음 10개」는 앞 차례의 도구 · 인자 · 쪽을 기억 칸(데이터 칸)으로 받아 offset 을 넘긴다 — 글자만 가던 때에는 추측이었다."""
    _my_docs(db, space, chatter, 12)
    seen = {}

    def follow_up(request):
        seen["last"] = request["turns"][-1].text
        return [tool_call("my_documents", {"offset": 10, "show": True})]

    worker = assistant(ScriptedToolAdapter([
        tool_call("my_documents", {"show": True}), "작성하신 문서는 총 12건입니다. 최근 10건을 보여드립니다.",
        follow_up, "나머지 2건입니다.",
    ]))
    _send(client, posted, "내가 만든 문서")
    worker.run_once()
    _send(client, posted, "다음 10개 보여줘.", message_id="h0123456789abcdef0123456789abcd02")
    worker.run_once()

    memory = seen["last"]
    assert memory.startswith("다음 10개 보여줘.")
    assert memory.index("<<<CLOVI_DATA:") < memory.index('"tool": "my_documents"') < memory.index("<<<END_CLOVI_DATA:")
    assert '"total": 12' in memory and '"offset": 0' in memory and '"n": 10' in memory
    second = _stored(_replies(db, posted["conversation_id"])[-1])
    [block] = second["results"]
    assert (block["offset"], block["returned"], block["total"]) == (10, 2, 12)
