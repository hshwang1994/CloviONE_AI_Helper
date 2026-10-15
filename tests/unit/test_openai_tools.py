"""OpenAI 대화 계약 — 함수 도구를 쓰는 차례 (D-535). 아직 제품에 배선하지 않았고(P9), 고정 응답으로 본다.

못박는 성질:
1. 요청 — 도구는 `{type:"function", name, description, parameters, strict:true}`, `tool_choice`, `parallel_tool_calls` 로 간다.
   API 키는 `max_output_tokens`(하한)와 `include:["reasoning.encrypted_content"]` 를, 계정 연결은 미리보기 계약대로 `stream=true` 만
   보낸다(금지 인자 없음).
2. 되싣기 — 직전 output 항목을 그대로 다음 input 에 싣는다. 추론 항목은 암호화된 내용이 있을 때만(API 키) 되싣고, 계정 연결에서는
   되싣지 않는다. 도구 결과는 `function_call_output{call_id, output}` 이다.
3. 응답 읽기 — `function_call` 항목이 도구 호출이다. 인자가 JSON 이 아니면 지어내지 않고(None) 원문만 들고 있다.
4. 스트림 조립(계정 연결) — 항목 · 인자 조각을 모으고 완료 이벤트의 output 을 정본으로 쓰며, 비면 모은 항목으로 대신한다. 실패 이벤트는
   `generate()` 와 같은 표다(요금제가 도구를 거절하면 `unsupported_capability`).
5. 계정 연결은 401 을 받으면 한 번만 갱신해 다시 보낸다(호출마다).
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.ai.credentials.chatgpt import TokenStatus
from app.ai.providers import base, openai
from app.core.allowlist import AllowlistRegistry
from app.core.http_client import OutboundClient
from app.core.secret_refs import FileSecretReferenceProvider
from tests.fakes.http import FakeHTTP

FORBIDDEN = ("background", "conversation", "max_output_tokens", "max_tool_calls", "metadata", "moderation",
             "multi_agent", "prompt", "prompt_cache_retention", "safety_identifier", "temperature", "top_logprobs",
             "top_p", "truncation", "user", "previous_response_id", "include")

TOOL = base.ToolSpec(
    name="my_work", description="내 업무를 봅니다.",
    parameters={"type": "object", "properties": {"view": {"type": "string", "enum": ["assigned", "requested"]}},
                "required": ["view"], "additionalProperties": False},
)

REASONING = {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "gAAAA-opaque"}
CALL = {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "my_work", "arguments": "{\"view\":\"assigned\"}"}
MESSAGE = {"type": "message", "id": "msg_1", "role": "assistant",
           "content": [{"type": "output_text", "text": "확인해 보겠습니다."}]}


def _sse(*events) -> str:
    return "".join(f"data: {json.dumps(e, ensure_ascii=False)}\n\n" for e in events)


class FakeTokens:
    def __init__(self, status=TokenStatus(True), refreshed=TokenStatus(True)):
        self.status, self.refreshed, self.ensured, self.forced = status, refreshed, 0, 0

    def ensure_fresh(self, **_kw):
        self.ensured += 1
        return self.status

    def force_refresh(self):
        self.forced += 1
        return self.refreshed


@pytest.fixture()
def outbound(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "allowed-services.json").write_text(json.dumps({"hosts": ["api.openai.com:443"]}), encoding="utf-8")
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "ai.openai.api_key").write_text("sk-test-" + "x" * 24, encoding="utf-8")
    (secrets / "ai.openai.chatgpt").write_text(json.dumps({"access_token": "chatgpt-at", "refresh_token": "rt"}),
                                               encoding="utf-8")
    fake = FakeHTTP()
    client = OutboundClient(AllowlistRegistry(config), FileSecretReferenceProvider(secrets), transport=fake.transport())
    yield client, fake
    client.close()


def _body(chatgpt, turns=None, choice=base.TOOL_CHOICE_AUTO, tools=(TOOL,)):
    return openai.converse_body(system="틀", turns=turns or [base.UserTurn("내 일")], tools=list(tools), tool_choice=choice,
                                model="gpt-x", max_output_tokens=64, chatgpt=chatgpt)


# ── 요청 본문 ─────────────────────────────────────────────────────────────────


def test_api_key_body_carries_strict_function_tools_and_encrypted_reasoning():
    body = _body(False)
    assert body["tools"] == [{"type": "function", "name": "my_work", "description": "내 업무를 봅니다.",
                              "parameters": TOOL.parameters, "strict": True}]
    assert body["tool_choice"] == "auto" and body["parallel_tool_calls"] is True
    assert body["store"] is False and body["instructions"] == "틀"
    assert body["max_output_tokens"] == openai.MIN_OUTPUT_TOKENS
    assert body["include"] == ["reasoning.encrypted_content"]
    assert "stream" not in body


@pytest.mark.parametrize("model,requested,expected", [
    ("gpt-x", 64, openai.MIN_OUTPUT_TOKENS),
    ("gpt-4.1", 4000, 4000),
    ("gpt-5", 64, openai.REASONING_OUTPUT_FLOOR),
    ("GPT-5-mini", 2048, openai.REASONING_OUTPUT_FLOOR),
    ("o3", 1000, openai.REASONING_OUTPUT_FLOOR),
    ("o4-mini", 20000, 20000),
    ("gpt-6.1", None, openai.REASONING_OUTPUT_FLOOR),
])
def test_reasoning_models_get_a_higher_output_floor_on_the_api_key_path(model, requested, expected):
    """추론 모델은 생각에 쓴 토큰까지 상한에 센다 — 도우미 답이 생각만 하다 잘리지 않게 하한을 높인다(D-570)."""
    assert openai.output_tokens(model, requested) == expected
    body = openai.converse_body(system="틀", turns=[base.UserTurn("내 일")], tools=[TOOL], tool_choice=base.TOOL_CHOICE_AUTO,
                                model=model, max_output_tokens=requested, chatgpt=False)
    assert body["max_output_tokens"] == expected
    single = openai.request_body(system="틀", user="질문", model=model, max_output_tokens=requested, chatgpt=False)
    assert single["max_output_tokens"] == expected


def test_the_chatgpt_path_never_sends_an_output_limit_even_for_reasoning_models():
    body = openai.converse_body(system="틀", turns=[base.UserTurn("내 일")], tools=[TOOL], tool_choice=base.TOOL_CHOICE_AUTO,
                                model="gpt-5", max_output_tokens=64, chatgpt=True)
    assert "max_output_tokens" not in body
    assert "max_output_tokens" not in openai.request_body(system="틀", user="질문", model="gpt-5", max_output_tokens=64,
                                                          chatgpt=True)


def test_chatgpt_body_keeps_the_preview_contract():
    body = _body(True)
    assert body["stream"] is True and body["store"] is False
    assert [key for key in FORBIDDEN if key in body] == []
    assert body["tools"][0]["strict"] is True


@pytest.mark.parametrize("choice,expected", [
    (base.TOOL_CHOICE_AUTO, "auto"), (base.TOOL_CHOICE_NONE, "none"), (base.TOOL_CHOICE_REQUIRED, "required"),
    (base.forced_tool("ping"), {"type": "function", "name": "ping"}),
])
def test_tool_choice_values(choice, expected):
    assert openai.tool_choice_value(choice) == expected


def test_no_tools_means_no_tool_keys():
    body = _body(False, tools=())
    assert "tools" not in body and "tool_choice" not in body and "parallel_tool_calls" not in body


# ── 되싣기 ────────────────────────────────────────────────────────────────────


def test_the_previous_output_is_replayed_verbatim_with_encrypted_reasoning_for_api_keys():
    first = openai.read_output({"status": "completed", "output": [REASONING, CALL]})
    turns = [base.UserTurn("내 일 알려 줘"), first.as_turn(),
             base.ToolResultsTurn((base.ToolResult("call_1", "<결과>티켓 3건</결과>"),))]
    items = openai.converse_input(turns, chatgpt=False)
    assert items == [
        {"role": "user", "content": [{"type": "input_text", "text": "내 일 알려 줘"}]},
        REASONING, CALL,
        {"type": "function_call_output", "call_id": "call_1", "output": "<결과>티켓 3건</결과>"},
    ]


def test_reasoning_without_encrypted_content_and_any_reasoning_on_chatgpt_is_not_replayed():
    plain = {"type": "reasoning", "id": "rs_2", "summary": []}
    turn = base.AssistantTurn(tool_calls=(), replay=(plain, REASONING, CALL))
    assert openai.converse_input([turn], chatgpt=False) == [REASONING, CALL]
    assert openai.converse_input([turn], chatgpt=True) == [CALL]


def test_an_assistant_turn_without_replay_is_rebuilt():
    turn = base.AssistantTurn(text="앞의 답", tool_calls=(base.ToolCall("call_9", "my_work", {"view": "requested"}),))
    assert openai.converse_input([turn], chatgpt=False) == [
        {"role": "assistant", "content": [{"type": "output_text", "text": "앞의 답"}]},
        {"type": "function_call", "call_id": "call_9", "name": "my_work", "arguments": "{\"view\": \"requested\"}"},
    ]


# ── 응답 읽기 ─────────────────────────────────────────────────────────────────


def test_function_calls_are_read_and_bad_json_is_not_invented():
    result = openai.read_output({"status": "completed", "output": [MESSAGE, CALL,
                                {"type": "function_call", "call_id": "call_2", "name": "my_work", "arguments": "{broken"}],
                                "usage": {"input_tokens": 30, "output_tokens": 8}})
    assert result.ok and result.stop_reason == base.STOP_TOOL_USE and result.text == "확인해 보겠습니다."
    assert result.tool_calls[0] == base.ToolCall("call_1", "my_work", {"view": "assigned"}, "{\"view\":\"assigned\"}")
    assert result.tool_calls[1].arguments is None and result.tool_calls[1].raw_arguments == "{broken"
    assert (result.input_tokens, result.output_tokens) == (30, 8)


def test_plain_text_ends_the_turn_and_incomplete_means_max_tokens():
    done = openai.read_output({"status": "completed", "output": [MESSAGE]})
    assert done.ok and done.tool_calls == () and done.stop_reason == base.STOP_END
    cut = openai.read_output({"status": "incomplete", "output": [MESSAGE]})
    assert cut.stop_reason == base.STOP_MAX_TOKENS
    empty = openai.read_output({"status": "completed", "output": [REASONING]})
    assert not empty.ok and empty.error_kind == base.ERROR_EMPTY


# ── 스트림 조립(계정 연결) ────────────────────────────────────────────────────


def test_a_stream_collects_items_and_arguments_when_completed_has_no_output():
    lines = _sse(
        {"type": "response.output_item.added", "output_index": 0, "item": {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "my_work", "arguments": ""}},
        {"type": "response.function_call_arguments.delta", "output_index": 0, "delta": "{\"view\":"},
        {"type": "response.function_call_arguments.delta", "output_index": 0, "delta": "\"assigned\"}"},
        {"type": "response.completed", "response": {"output": [], "usage": {"input_tokens": 9, "output_tokens": 4}}},
    ).splitlines()
    result = openai.assemble_turn(lines)
    assert result.ok and result.tool_calls == (base.ToolCall("call_1", "my_work", {"view": "assigned"}, "{\"view\":\"assigned\"}"),)
    assert result.replay[0]["call_id"] == "call_1"
    assert (result.input_tokens, result.output_tokens) == (9, 4)


def test_the_completed_output_is_canonical_and_text_comes_from_deltas():
    lines = _sse(
        {"type": "response.output_text.delta", "delta": "연차는 "},
        {"type": "response.output_text.delta", "delta": "팀장 승인 뒤에 씁니다."},
        {"type": "response.completed", "response": {"output": [MESSAGE]}},
    ).splitlines()
    result = openai.assemble_turn(lines)
    assert result.ok and result.text == "연차는 팀장 승인 뒤에 씁니다." and result.replay == (MESSAGE,)


@pytest.mark.parametrize("event,kind,code", [
    ({"type": "response.failed", "response": {"error": {"code": "subscription_sharing_unsupported_capability"}}},
     base.ERROR_REQUEST, "unsupported_capability"),
    ({"type": "error", "error": {"code": "subscription_sharing_usage_limit_exceeded"}}, base.ERROR_TRANSIENT, "plan_usage_limit"),
    ({"type": "response.incomplete"}, base.ERROR_REQUEST, "incomplete"),
])
def test_stream_failures_use_the_generate_table(event, kind, code):
    result = openai.assemble_turn(_sse(event).splitlines())
    assert not result.ok and (result.error_kind, result.error_code) == (kind, code)


def test_a_stream_without_completed_is_a_failure_and_the_deadline_is_a_timeout():
    cut = openai.assemble_turn(_sse({"type": "response.output_text.delta", "delta": "잘린"}).splitlines())
    assert (cut.error_kind, cut.error_code) == (base.ERROR_TRANSIENT, "stream_incomplete")
    ticks = iter([0.0, 11.0])
    late = openai.assemble_turn(_sse({"type": "response.output_text.delta", "delta": "a"}).splitlines(),
                                deadline=10.0, clock=lambda: next(ticks, 99.0))
    assert late.error_code == "timeout"


# ── HTTP ──────────────────────────────────────────────────────────────────────


def test_api_key_converse_over_http(outbound):
    client, fake = outbound
    fake.on(openai.RESPONSES_URL, json_body={"status": "completed", "output": [REASONING, CALL]})
    adapter = openai.OpenAIAdapter(outbound=client, secret_ref="ai.openai.api_key", auth_method=base.AUTH_API_KEY)
    result = adapter.converse(system="s", turns=[base.UserTurn("u")], tools=[TOOL], tool_choice=base.TOOL_CHOICE_AUTO,
                              model="gpt-x", max_output_tokens=100, timeout=10)
    assert result.ok and result.tool_calls[0].id == "call_1" and result.replay == (REASONING, CALL)
    sent = json.loads(fake.requests[0].content)
    assert sent["include"] == ["reasoning.encrypted_content"] and sent["tools"][0]["name"] == "my_work"


def test_chatgpt_converse_refreshes_once_after_a_401(outbound):
    client, fake = outbound
    replies = iter([
        httpx.Response(401, json={"error": {"code": "invalid_token"}}),
        httpx.Response(200, text=_sse({"type": "response.output_text.delta", "delta": "다시"},
                                      {"type": "response.completed", "response": {"output": [MESSAGE]}}),
                       headers={"content-type": "text/event-stream"}),
    ])
    fake.on_handler(openai.RESPONSES_URL, lambda request: next(replies))
    tokens = FakeTokens()
    adapter = openai.OpenAIAdapter(outbound=client, secret_ref="ai.openai.chatgpt", auth_method=base.AUTH_CHATGPT, tokens=tokens)
    result = adapter.converse(system="s", turns=[base.UserTurn("u")], tools=[TOOL], tool_choice=base.TOOL_CHOICE_AUTO,
                              model="m", max_output_tokens=10, timeout=30)
    assert result.ok and result.text == "다시"
    assert tokens.forced == 1 and len(fake.requests) == 2
    assert json.loads(fake.requests[1].content)["stream"] is True


def test_chatgpt_capability_refusal_is_a_request_error_the_runtime_can_read(outbound):
    client, fake = outbound
    fake.on(openai.RESPONSES_URL, status=400, json_body={"error": {"code": "subscription_sharing_unsupported_capability"}})
    adapter = openai.OpenAIAdapter(outbound=client, secret_ref="ai.openai.chatgpt", auth_method=base.AUTH_CHATGPT,
                                   tokens=FakeTokens())
    result = adapter.converse(system="s", turns=[base.UserTurn("u")], tools=[TOOL], tool_choice=base.TOOL_CHOICE_AUTO,
                              model="m", max_output_tokens=10, timeout=30)
    assert (result.error_kind, result.error_code, result.http_status) == (base.ERROR_REQUEST, "unsupported_capability", 400)


def test_incomplete_with_text_keeps_a_truncated_answer():
    """출력 한도에 닿아 끝난 스트림(`response.incomplete`)도 받은 글이 있으면 잘린 답이다 — 예전에는 실패로 버려 마지막
    라운드의 긴 답이 고정 문장(「찾은 자료를 아래에 모았습니다」)으로 바뀌었다. 도구 호출이 걸렸으면 지금처럼 실패다."""
    answered = openai.assemble_turn(_sse(
        {"type": "response.output_text.delta", "delta": "긴 답의 앞부분"},
        {"type": "response.incomplete", "response": {"status": "incomplete", "output": [MESSAGE],
                                                     "incomplete_details": {"reason": "max_output_tokens"}}},
    ).splitlines())
    assert answered.ok and answered.text == "긴 답의 앞부분"
    assert answered.stop_reason == base.STOP_MAX_TOKENS
    with_call = openai.assemble_turn(_sse(
        {"type": "response.output_text.delta", "delta": "확인해 보겠습니다."},
        {"type": "response.output_item.added", "output_index": 1, "item": CALL},
        {"type": "response.incomplete", "response": {}},
    ).splitlines())
    assert not with_call.ok and with_call.error_code == "incomplete"
