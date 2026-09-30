"""OpenAI 제공자 — API 키와 ChatGPT 계정 연결 (계획 3.14 · 3.16, D-516).

못박는 성질:
1. 계정 연결의 요청은 미리보기 계약을 지킨다: `store=false`, `stream=true`, 시스템 틀은 `instructions`, 금지된 인자
   (`max_output_tokens`, `temperature`, `metadata`, `user` 등)는 보내지 않는다.
2. 스트림은 완료 이벤트를 받아야 성공이다. 도중에 끊기면 받은 글자가 있어도 실패다.
3. 공식 오류표가 여섯 연결 상태로 옮겨진다 - 요금제 한도는 일시 장애, 요금제 공유 대상 아님은 구성 오류, 계정 연결의
   401 은 재로그인 필요, API 크레딧 없음은 구성 오류다.
4. 계정 연결은 부르기 전에 토큰을 확인하고, 401 을 받으면 한 번만 갱신해 다시 보낸다.
5. 모델 목록은 두 모양(API 키의 `data`, 요금제의 `models`)을 하나로 읽는다.
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
             "top_p", "truncation", "user", "previous_response_id")


def _sse(*events) -> str:
    return "".join(f"data: {json.dumps(e, ensure_ascii=False)}\n\n" for e in events)


COMPLETED = {"type": "response.completed", "response": {"usage": {"input_tokens": 12, "output_tokens": 3}}}


class FakeTokens:
    def __init__(self, status=TokenStatus(True), refreshed=TokenStatus(True)):
        self.status = status
        self.refreshed = refreshed
        self.ensured = 0
        self.forced = 0

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


# ── 요청 본문 ─────────────────────────────────────────────────────────────────


def test_chatgpt_requests_keep_the_preview_contract():
    body = openai.request_body(system="틀", user="질문", model="gpt-x", max_output_tokens=1500, chatgpt=True)
    assert body["store"] is False and body["stream"] is True
    assert body["instructions"] == "틀"
    assert body["input"] == [{"role": "user", "content": [{"type": "input_text", "text": "질문"}]}]
    assert [key for key in FORBIDDEN if key in body] == []
    assert all(item.get("role") != "system" for item in body["input"]), "시스템 역할 메시지는 거절된다"


def test_api_key_requests_cap_output_with_a_floor_for_reasoning_models():
    small = openai.request_body(system="s", user="u", model="m", max_output_tokens=32, chatgpt=False)
    large = openai.request_body(system="s", user="u", model="m", max_output_tokens=4000, chatgpt=False)
    assert small["max_output_tokens"] == openai.MIN_OUTPUT_TOKENS
    assert large["max_output_tokens"] == 4000
    assert "stream" not in small and small["store"] is False


# ── 스트림 ───────────────────────────────────────────────────────────────────


def test_a_completed_stream_is_the_joined_text_with_usage():
    lines = _sse(
        {"type": "response.created"},
        {"type": "response.output_text.delta", "delta": "안녕"},
        {"type": "response.output_text.delta", "delta": "하세요"},
        COMPLETED,
    ).splitlines()
    result = openai.assemble_stream(lines)
    assert result.ok and result.text == "안녕하세요"
    assert (result.input_tokens, result.output_tokens) == (12, 3)


def test_a_stream_without_the_completed_event_is_a_failure_even_with_text():
    lines = _sse({"type": "response.output_text.delta", "delta": "잘린 답"}).splitlines()
    result = openai.assemble_stream(lines)
    assert not result.ok and result.error_kind == base.ERROR_TRANSIENT and result.error_code == "stream_incomplete"


@pytest.mark.parametrize("event, kind, code", [
    ({"type": "response.failed", "response": {"error": {"code": "subscription_sharing_usage_limit_exceeded"}}},
     base.ERROR_TRANSIENT, "plan_usage_limit"),
    ({"type": "response.failed", "response": {"error": {"code": "subscription_sharing_usage_unavailable"}}},
     base.ERROR_TRANSIENT, "plan_usage_unavailable"),
    ({"type": "response.failed", "response": {"error": {"code": "server_error"}}}, base.ERROR_TRANSIENT, "stream_failed"),
    ({"type": "response.incomplete", "response": {}}, base.ERROR_REQUEST, "incomplete"),
    ({"type": "error", "code": "subscription_sharing_user_not_eligible"}, base.ERROR_CONFIG, "plan_not_eligible"),
])
def test_stream_failures_map_to_the_official_error_table(event, kind, code):
    result = openai.assemble_stream(_sse({"type": "response.output_text.delta", "delta": "x"}, event).splitlines())
    assert (result.ok, result.error_kind, result.error_code) == (False, kind, code)


def test_the_stream_deadline_is_a_timeout():
    ticks = iter([0.0, 5.0, 999.0])
    lines = _sse({"type": "response.output_text.delta", "delta": "a"}, {"type": "response.output_text.delta",
                                                                       "delta": "b"}, COMPLETED).splitlines()
    result = openai.assemble_stream(lines, deadline=10.0, clock=lambda: next(ticks, 999.0))
    assert result.error_code == "timeout"


def test_noise_lines_are_ignored():
    lines = ["event: response.output_text.delta", "", ": keep-alive", "data: not json", "data: [DONE]"]
    lines += _sse({"type": "response.output_text.delta", "delta": "ok"}, COMPLETED).splitlines()
    assert openai.assemble_stream(lines).text == "ok"


# ── HTTP 오류 표 ──────────────────────────────────────────────────────────────


def _resp(status, code=None, kind=None, message=""):
    return httpx.Response(status, json={"error": {"code": code, "type": kind, "message": message}})


@pytest.mark.parametrize("response, chatgpt, kind, code", [
    (_resp(401), True, base.ERROR_REAUTH, "account_rejected"),
    (_resp(401), False, base.ERROR_AUTH, "http_401"),
    (_resp(403, "subscription_sharing_user_not_eligible"), True, base.ERROR_CONFIG, "plan_not_eligible"),
    (_resp(403), True, base.ERROR_CONFIG, "account_forbidden"),
    (_resp(403), False, base.ERROR_AUTH, "http_403"),
    (_resp(429, "subscription_sharing_usage_limit_exceeded"), True, base.ERROR_TRANSIENT, "plan_usage_limit"),
    (_resp(429, "insufficient_quota", "insufficient_quota"), False, base.ERROR_CONFIG, "insufficient_quota"),
    (_resp(429, "rate_limit_exceeded"), False, base.ERROR_TRANSIENT, "http_429"),
    (_resp(404), False, base.ERROR_CONFIG, "model_not_found"),
    (_resp(400, "model_not_found"), True, base.ERROR_CONFIG, "model_not_found"),
    (_resp(400, "subscription_sharing_unsupported_capability"), True, base.ERROR_REQUEST, "unsupported_capability"),
    (_resp(503, "subscription_sharing_user_unavailable"), True, base.ERROR_TRANSIENT, "http_503"),
    (_resp(500), False, base.ERROR_TRANSIENT, "http_500"),
])
def test_http_errors_map_to_the_six_states(response, chatgpt, kind, code):
    result = openai.classify_status(response, chatgpt=chatgpt)
    assert (result.error_kind, result.error_code) == (kind, code)


# ── 모델 목록 ─────────────────────────────────────────────────────────────────


def test_model_lists_of_both_shapes_are_read_the_same_way():
    plan = openai.parse_models({"models": [
        {"slug": "gpt-6.1-sol", "display_name": "GPT-6.1 Sol", "visibility": "list"},
        {"slug": "internal-hidden", "display_name": "Hidden", "visibility": "hide"},
    ]})
    assert plan == ({"id": "gpt-6.1-sol", "label": "GPT-6.1 Sol"},)
    api = openai.parse_models({"data": [
        {"id": "text-embedding-3-small"}, {"id": "gpt-z"}, {"id": "gpt-a"}, {"id": "whisper-1"}, {"id": ""},
    ]})
    assert [m["id"] for m in api] == ["gpt-a", "gpt-z"]


# ── 어댑터 ───────────────────────────────────────────────────────────────────


def test_api_key_generation_uses_the_key_slot_without_streaming(outbound):
    client, fake = outbound
    fake.on(openai.RESPONSES_URL, json_body={
        "status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "답"}]}],
        "usage": {"input_tokens": 5, "output_tokens": 1},
    })
    adapter = openai.OpenAIAdapter(outbound=client, secret_ref="ai.openai.api_key", auth_method=base.AUTH_API_KEY)
    result = adapter.generate(system="s", user="u", model="gpt-a", max_output_tokens=100, timeout=10)
    assert result.ok and result.text == "답"
    sent = fake.requests[0]
    assert sent.headers["Authorization"] == "Bearer sk-test-" + "x" * 24
    assert json.loads(sent.content)["max_output_tokens"] == openai.MIN_OUTPUT_TOKENS


def test_chatgpt_generation_streams_with_the_bundle_access_token(outbound):
    client, fake = outbound
    fake.on_handler(openai.RESPONSES_URL, lambda request: httpx.Response(
        200, text=_sse({"type": "response.output_text.delta", "delta": "요금제 답"}, COMPLETED),
        headers={"content-type": "text/event-stream"}, request=request))
    tokens = FakeTokens()
    adapter = openai.OpenAIAdapter(outbound=client, secret_ref="ai.openai.chatgpt", auth_method=base.AUTH_CHATGPT,
                                   tokens=tokens)
    result = adapter.generate(system="s", user="u", model="gpt-6.1-sol", max_output_tokens=1500, timeout=30)
    assert result.ok and result.text == "요금제 답"
    assert tokens.ensured == 1
    sent = fake.requests[0]
    assert sent.headers["Authorization"] == "Bearer chatgpt-at"
    body = json.loads(sent.content)
    assert body["stream"] is True and "max_output_tokens" not in body


def test_chatgpt_refreshes_once_after_a_401_and_retries(outbound):
    client, fake = outbound
    replies = iter([
        httpx.Response(401, json={"error": {"code": "invalid_token"}}),
        httpx.Response(200, text=_sse({"type": "response.output_text.delta", "delta": "다시"}, COMPLETED),
                       headers={"content-type": "text/event-stream"}),
    ])
    fake.on_handler(openai.RESPONSES_URL, lambda request: next(replies))
    tokens = FakeTokens()
    adapter = openai.OpenAIAdapter(outbound=client, secret_ref="ai.openai.chatgpt", auth_method=base.AUTH_CHATGPT,
                                   tokens=tokens)
    result = adapter.generate(system="s", user="u", model="m", max_output_tokens=10, timeout=30)
    assert result.ok and result.text == "다시"
    assert tokens.forced == 1 and len(fake.requests) == 2


def test_chatgpt_reauth_from_the_token_manager_skips_the_call(outbound):
    client, fake = outbound
    tokens = FakeTokens(status=TokenStatus(False, base.ERROR_REAUTH, "refresh_token_expired"))
    adapter = openai.OpenAIAdapter(outbound=client, secret_ref="ai.openai.chatgpt", auth_method=base.AUTH_CHATGPT,
                                   tokens=tokens)
    result = adapter.generate(system="s", user="u", model="m", max_output_tokens=10, timeout=30)
    assert (result.error_kind, result.error_code) == (base.ERROR_REAUTH, "refresh_token_expired")
    assert fake.requests == []


class _ProxiedBroken:
    proxy_display = "proxy.corp.example:3128"

    def request(self, *a, **kw):
        raise httpx.ConnectError("proxy refused")


def test_a_transport_failure_behind_a_proxy_names_the_proxy():
    adapter = openai.OpenAIAdapter(outbound=_ProxiedBroken(), secret_ref="ai.openai.api_key",
                                   auth_method=base.AUTH_API_KEY)
    result = adapter.generate(system="s", user="u", model="m", max_output_tokens=10, timeout=5)
    assert (result.error_kind, result.error_code) == (base.ERROR_TRANSIENT, "proxy_connect")


def test_both_openai_methods_are_offered_and_anthropic_stays_key_only():
    openai_spec = base.provider_spec(base.PROVIDER_OPENAI)
    assert [m.key for m in openai_spec.auth_methods] == [base.AUTH_API_KEY, base.AUTH_CHATGPT]
    assert openai_spec.method(base.AUTH_CHATGPT).account is True
    anthropic_spec = base.provider_spec(base.PROVIDER_ANTHROPIC)
    assert [m.key for m in anthropic_spec.auth_methods] == [base.AUTH_API_KEY]
    assert not any(m.account for m in anthropic_spec.auth_methods), "Anthropic 에 계정 로그인이 생기면 안 된다"
