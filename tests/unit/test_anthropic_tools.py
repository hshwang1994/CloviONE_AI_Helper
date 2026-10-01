"""Anthropic 대화 계약 — 도구를 쓰는 차례 (D-535). 아직 제품에 배선하지 않았고(P9 가 런타임에 잇는다), 여기서는 고정 응답으로 본다.

못박는 성질:
1. 요청 — 도구는 `tools[{name, description, input_schema}]` 와 `tool_choice` 로 가고, 도구가 없으면 두 키 모두 없다. 시스템 틀은
   `system` 에만 선다(사용자 쪽에 섞지 않는다).
2. 되싣기 — 응답의 content 블록이 **그대로** 다음 assistant 차례가 되고, 도구 결과는 그 뒤 user 차례의 `tool_result` 다.
3. 응답 읽기 — 글 블록은 이어 붙이고 `tool_use` 블록은 도구 호출이다. 둘 다 없으면 빈 답이다. 인자가 사전이 아니면 지어내지 않는다.
4. 실패 — `generate()` 와 같은 한 표다(401 auth · 모델 config · 429 transient · 그 밖의 400 request).
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.ai.providers import anthropic, base
from app.core.allowlist import AllowlistRegistry
from app.core.http_client import OutboundClient
from app.core.secret_refs import FileSecretReferenceProvider
from tests.fakes.http import FakeHTTP

PING = base.ToolSpec(
    name="search_documents", description="사내 문서를 찾습니다.",
    parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"],
                "additionalProperties": False},
)


@pytest.fixture()
def outbound(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "allowed-services.json").write_text(json.dumps({"hosts": ["api.anthropic.com:443"]}), encoding="utf-8")
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "ai.anthropic.api_key").write_text("sk-ant-test-" + "x" * 24, encoding="utf-8")
    fake = FakeHTTP()
    client = OutboundClient(AllowlistRegistry(config), FileSecretReferenceProvider(secrets), transport=fake.transport())
    yield client, fake
    client.close()


def _adapter(client):
    return anthropic.AnthropicAdapter(outbound=client, secret_ref="ai.anthropic.api_key")


TOOL_USE_REPLY = {
    "id": "msg_1", "type": "message", "role": "assistant", "stop_reason": "tool_use",
    "content": [
        {"type": "text", "text": "문서를 찾아보겠습니다."},
        {"type": "tool_use", "id": "toolu_1", "name": "search_documents", "input": {"query": "연차 신청"}},
    ],
    "usage": {"input_tokens": 40, "output_tokens": 12},
}


# ── 요청 본문 ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("choice,expected", [
    (base.TOOL_CHOICE_AUTO, {"type": "auto"}),
    (base.TOOL_CHOICE_NONE, {"type": "none"}),
    (base.TOOL_CHOICE_REQUIRED, {"type": "any"}),
    (base.forced_tool("ping"), {"type": "tool", "name": "ping"}),
])
def test_tool_choice_maps_to_the_messages_api_shape(choice, expected):
    assert anthropic.tool_choice_body(choice) == expected


def test_tools_go_as_input_schema_and_no_tools_means_no_tool_keys():
    body = anthropic.converse_body(system="틀", turns=[base.UserTurn("질문")], tools=[PING],
                                   tool_choice=base.TOOL_CHOICE_AUTO, model="claude-x", max_output_tokens=2000)
    assert body["system"] == "틀" and body["max_tokens"] == 2000
    assert body["tools"] == [{"name": "search_documents", "description": "사내 문서를 찾습니다.", "input_schema": PING.parameters}]
    assert body["tool_choice"] == {"type": "auto"}
    assert body["messages"] == [{"role": "user", "content": "질문"}]
    bare = anthropic.converse_body(system="틀", turns=[base.UserTurn("질문")], tools=[],
                                   tool_choice=base.TOOL_CHOICE_AUTO, model="claude-x", max_output_tokens=10)
    assert "tools" not in bare and "tool_choice" not in bare


def test_replay_keeps_the_blocks_and_results_follow_as_a_user_turn():
    first = anthropic.read_turn(TOOL_USE_REPLY)
    turns = [
        base.UserTurn("연차 신청은 어떻게 하나요?"),
        first.as_turn(),
        base.ToolResultsTurn((base.ToolResult("toolu_1", "<결과>문서 2건</결과>"), base.ToolResult("toolu_x", "too_many_calls", is_error=True))),
    ]
    messages = anthropic.converse_messages(turns)
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert messages[1]["content"] == TOOL_USE_REPLY["content"], "받은 블록을 다시 조립하지 않고 그대로 되싣는다"
    assert messages[2]["content"] == [
        {"type": "tool_result", "tool_use_id": "toolu_1", "content": "<결과>문서 2건</결과>"},
        {"type": "tool_result", "tool_use_id": "toolu_x", "content": "too_many_calls", "is_error": True},
    ]


def test_an_assistant_turn_without_replay_is_rebuilt_from_text_and_calls():
    turn = base.AssistantTurn(text="앞의 답", tool_calls=(base.ToolCall("toolu_9", "my_work", {"view": "assigned"}),))
    assert anthropic.converse_messages([turn])[0]["content"] == [
        {"type": "text", "text": "앞의 답"},
        {"type": "tool_use", "id": "toolu_9", "name": "my_work", "input": {"view": "assigned"}},
    ]


# ── 응답 읽기 ─────────────────────────────────────────────────────────────────


def test_a_tool_use_reply_is_read_as_calls_with_the_blocks_to_replay():
    result = anthropic.read_turn(TOOL_USE_REPLY)
    assert result.ok and result.stop_reason == base.STOP_TOOL_USE
    assert result.text == "문서를 찾아보겠습니다."
    assert result.tool_calls == (base.ToolCall("toolu_1", "search_documents", {"query": "연차 신청"},
                                                json.dumps({"query": "연차 신청"}, ensure_ascii=False)),)
    assert result.replay == tuple(TOOL_USE_REPLY["content"])
    assert (result.input_tokens, result.output_tokens) == (40, 12)


def test_a_plain_answer_ends_the_turn_and_an_empty_reply_is_empty():
    done = anthropic.read_turn({"content": [{"type": "text", "text": "답입니다."}], "stop_reason": "end_turn"})
    assert done.ok and done.text == "답입니다." and done.tool_calls == () and done.stop_reason == base.STOP_END
    empty = anthropic.read_turn({"content": [], "stop_reason": "end_turn"})
    assert not empty.ok and empty.error_kind == base.ERROR_EMPTY
    broken = anthropic.read_turn({"content": [{"type": "tool_use", "id": "t", "name": "x", "input": "not-a-dict"}]})
    assert broken.ok and broken.tool_calls[0].arguments is None, "사전이 아닌 인자를 지어내서 채우지 않는다"
    assert not anthropic.read_turn({"oops": 1}).ok


# ── HTTP ──────────────────────────────────────────────────────────────────────


def test_two_rounds_over_http_replay_the_first_reply(outbound):
    client, fake = outbound
    replies = iter([
        httpx.Response(200, json=TOOL_USE_REPLY),
        httpx.Response(200, json={"content": [{"type": "text", "text": "연차는 팀장 승인 뒤에 씁니다."}],
                                  "stop_reason": "end_turn", "usage": {"input_tokens": 80, "output_tokens": 20}}),
    ])
    fake.on_handler(anthropic.MESSAGES_URL, lambda request: next(replies))
    adapter = _adapter(client)
    turns = [base.UserTurn("연차 신청은 어떻게 하나요?")]
    first = adapter.converse(system="틀", turns=turns, tools=[PING], tool_choice=base.TOOL_CHOICE_AUTO,
                             model="claude-x", max_output_tokens=2000, timeout=30)
    assert first.ok and first.tool_calls[0].name == "search_documents"
    turns += [first.as_turn(), base.ToolResultsTurn((base.ToolResult("toolu_1", "<결과/>"),))]
    second = adapter.converse(system="틀", turns=turns, tools=[PING], tool_choice=base.TOOL_CHOICE_NONE,
                              model="claude-x", max_output_tokens=2000, timeout=30)
    assert second.ok and second.text == "연차는 팀장 승인 뒤에 씁니다." and second.stop_reason == base.STOP_END
    sent = json.loads(fake.requests[1].content)
    assert sent["tool_choice"] == {"type": "none"}
    assert sent["messages"][1] == {"role": "assistant", "content": TOOL_USE_REPLY["content"]}
    assert sent["messages"][2]["content"][0]["tool_use_id"] == "toolu_1"
    assert fake.requests[0].headers["x-api-key"].startswith("sk-ant-test-")
    assert fake.requests[0].headers["anthropic-version"] == anthropic.ANTHROPIC_VERSION


@pytest.mark.parametrize("status,body,kind,code", [
    (401, {"error": {"type": "authentication_error"}}, base.ERROR_AUTH, "http_401"),
    (404, {"error": {"type": "not_found_error", "message": "model: claude-x"}}, base.ERROR_CONFIG, "model_not_found"),
    (429, {"error": {"type": "rate_limit_error"}}, base.ERROR_TRANSIENT, "http_429"),
    (400, {"error": {"type": "invalid_request_error", "message": "tool_choice none is not supported"}}, base.ERROR_REQUEST,
     "invalid_request_error"),
])
def test_failures_use_the_same_table_as_generate(outbound, status, body, kind, code):
    client, fake = outbound
    fake.on(anthropic.MESSAGES_URL, status=status, json_body=body)
    result = _adapter(client).converse(system="s", turns=[base.UserTurn("u")], tools=[PING],
                                       tool_choice=base.TOOL_CHOICE_AUTO, model="claude-x", max_output_tokens=10, timeout=5)
    assert not result.ok and (result.error_kind, result.error_code, result.http_status) == (kind, code, status)


def test_a_timeout_is_transient(outbound):
    client, fake = outbound
    fake.on_timeout(anthropic.MESSAGES_URL)
    result = _adapter(client).converse(system="s", turns=[base.UserTurn("u")], tools=[], tool_choice=base.TOOL_CHOICE_AUTO,
                                       model="m", max_output_tokens=10, timeout=1)
    assert (result.error_kind, result.error_code) == (base.ERROR_TRANSIENT, "timeout")
