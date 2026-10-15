"""OpenAI Responses API — API 키와 ChatGPT 계정 연결 (계획 3.14 · 3.16, D-516).

## 두 인증 방식, 한 엔드포인트

  api_key   `Authorization: Bearer <API 키>`. 스트리밍 없이 부르고 `max_output_tokens` 를 보낸다
  chatgpt   `Authorization: Bearer <계정 연결의 access token>`. 공식 미리보기 계약상 `store=false`, `stream=true` 가
            필수이고 `max_output_tokens` · `temperature` · `metadata` · `user` 같은 인자는 보내면 거절된다. 시스템 틀은
            `instructions` 로 보낸다(시스템 역할의 메시지는 거절된다). 완료 이벤트(`response.completed`)를 받아야만
            성공이다 - 도중에 끊긴 스트림의 글자는 잘린 답이라 싣지 않는다

## 왜 SDK 가 아니라 OutboundClient 인가

Anthropic 어댑터와 같은 이유다(`anthropic.py` 머리말). 바깥 호출의 문은 하나이고, 허용 목록과 redirect 금지와 비밀
주입이 거기에만 있다. 계정 연결의 access token 은 비밀 칸의 JSON 묶음에서 `secret_field` 로 꺼내 헤더에 싣는다 -
이 모듈은 토큰 값을 만지지 않는다.

## 실패의 종류 (공식 오류표 - developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery)

  401 (계정 연결)                                         reauth     재로그인 필요(한 번 갱신해 다시 보낸 뒤에도 401 이면)
  401 (API 키)                                            auth       키가 거부됐다
  403 subscription_sharing_user_not_eligible              config     요금제 공유 대상이 아니다 - 다시 시도하지 않는다
  403 그 밖(지역 제한, 권한 범위, 잘못된 경로)             config, auth(API 키)
  404, 400 중 모델을 말하는 것                            config     모델을 다시 골라야 한다
  400 subscription_sharing_unsupported_capability         request    이 요청만 틀렸다
  429 subscription_sharing_usage_limit_exceeded           transient  요금제 사용량 한도 - 화면이 「사용량 관리」를 권한다
  429 insufficient_quota                                  config     API 계정의 크레딧이 없다 - 기다려도 풀리지 않는다
  429 그 밖, 5xx, 503 subscription_sharing_*_unavailable, 시간 초과, 연결 실패   transient

## 출력 토큰 하한(API 키)

추론 모델은 `max_output_tokens` 안에서 생각하는 데 쓴 토큰까지 센다. 연결 확인처럼 한도가 작은 액션은 생각만 하다
글자를 하나도 못 내고 끝날 수 있어 하한(`MIN_OUTPUT_TOKENS`)을 둔다. 글자 수는 런타임이 액션마다 따로 자른다.
"""

from __future__ import annotations

import json
import logging
import time

from app.ai.providers import base
from app.core.http_client import AUTH_BEARER, is_timeout_error, is_transport_error

logger = logging.getLogger("app.ai.providers.openai")

API_BASE = "https://api.openai.com/v1"
RESPONSES_URL = API_BASE + "/responses"
MODELS_URL = API_BASE + "/models"
ALLOWLIST = "services"

MIN_OUTPUT_TOKENS = 1024
#: 추론 모델(`app/ai/catalog.py::is_reasoning_model`)의 출력 토큰 하한(D-570). 도우미 한 차례는 도구 결과를 읽고 생각한 뒤 목록을
#: 쓰는데, 생각에 쓴 토큰이 상한을 먹으면 답이 `incomplete` 로 잘리거나 빈 글이 된다. 키 방식에만 건다 — 계정 방식은 이 인자를
#: 보낼 수 없다. 모델 이름은 카탈로그 한 곳에만 적는다(D-201).
REASONING_OUTPUT_FLOOR = 8192
CHATGPT_ACCESS_FIELD = "access_token"


def output_tokens(model: str | None, requested) -> int:
    """키 방식 요청의 `max_output_tokens` — 액션의 값에 하한 둘(모든 모델 · 추론 모델)을 건다."""
    from app.ai import catalog

    floor = REASONING_OUTPUT_FLOOR if catalog.is_reasoning_model(model) else MIN_OUTPUT_TOKENS
    return max(int(requested or 0), floor)

CODE_PLAN_LIMIT = "plan_usage_limit"
CODE_NOT_ELIGIBLE = "plan_not_eligible"
CODE_INSUFFICIENT_QUOTA = "insufficient_quota"
CODE_NOT_CONNECTED = "account_not_connected"

# 모델 목록에서 글을 만들지 않는 모델을 거른다. 목록은 사람이 고르기 쉽게 하려는 것이고, 모델 이름은 직접 넣을 수도
# 있다 - 여기 없는 새 계열이 생겨도 막히지 않는다.
NON_TEXT_MODEL_MARKERS = (
    "embedding", "tts", "whisper", "dall-e", "moderation", "transcribe", "realtime", "audio", "image", "search",
)

# 스트림 실패 이벤트의 코드 → 종류. 없는 코드는 일시 장애로 본다(다시 하면 될 수 있다).
STREAM_ERROR_KINDS = {
    "subscription_sharing_usage_limit_exceeded": (base.ERROR_TRANSIENT, CODE_PLAN_LIMIT),
    "subscription_sharing_usage_unavailable": (base.ERROR_TRANSIENT, "plan_usage_unavailable"),
    "subscription_sharing_user_unavailable": (base.ERROR_TRANSIENT, "plan_usage_unavailable"),
    "subscription_sharing_user_not_eligible": (base.ERROR_CONFIG, CODE_NOT_ELIGIBLE),
    "subscription_sharing_unsupported_capability": (base.ERROR_REQUEST, "unsupported_capability"),
    "insufficient_quota": (base.ERROR_CONFIG, CODE_INSUFFICIENT_QUOTA),
    "invalid_prompt": (base.ERROR_REQUEST, "invalid_prompt"),
    "model_not_found": (base.ERROR_CONFIG, "model_not_found"),
}


def _error_fields(response) -> tuple[str, str, str]:
    """(type, code, message) - 없으면 빈 문자열. 원문은 분류에만 쓰고 싣지 않는다."""
    try:
        data = response.json()
    except ValueError:
        return "", "", ""
    error = data.get("error") if isinstance(data, dict) else None
    if not isinstance(error, dict):
        return "", "", ""
    return str(error.get("type") or ""), str(error.get("code") or ""), str(error.get("message") or "")


def classify_status(response, *, chatgpt: bool) -> base.ProviderResult:
    """HTTP 오류 응답 → 실패 종류."""
    status = response.status_code
    kind_type, code, message = _error_fields(response)
    if status == 401:
        if chatgpt:
            return base.failure(base.ERROR_REAUTH, "account_rejected", http_status=status)
        return base.failure(base.ERROR_AUTH, "http_401", http_status=status)
    if status == 403:
        if code == "subscription_sharing_user_not_eligible":
            return base.failure(base.ERROR_CONFIG, CODE_NOT_ELIGIBLE, http_status=status)
        if chatgpt:
            return base.failure(base.ERROR_CONFIG, "account_forbidden", http_status=status)
        return base.failure(base.ERROR_AUTH, "http_403", http_status=status)
    if status == 429:
        if code == "subscription_sharing_usage_limit_exceeded":
            return base.failure(base.ERROR_TRANSIENT, CODE_PLAN_LIMIT, http_status=status)
        if code == CODE_INSUFFICIENT_QUOTA or kind_type == CODE_INSUFFICIENT_QUOTA:
            return base.failure(base.ERROR_CONFIG, CODE_INSUFFICIENT_QUOTA, http_status=status)
        return base.failure(base.ERROR_TRANSIENT, "http_429", http_status=status)
    if status == 404 or (status == 400 and (code == "model_not_found" or "model" in message.lower())):
        return base.failure(base.ERROR_CONFIG, "model_not_found", http_status=status)
    if status >= 500:
        return base.failure(base.ERROR_TRANSIENT, f"http_{status}", http_status=status)
    if code == "subscription_sharing_unsupported_capability":
        return base.failure(base.ERROR_REQUEST, "unsupported_capability", http_status=status)
    return base.failure(base.ERROR_REQUEST, code or f"http_{status}", http_status=status)


def _exception_result(exc: Exception, *, chatgpt: bool, proxied: bool = False) -> base.ProviderResult:
    from app.core.allowlist import URLNotAllowedError
    from app.core.secret_refs import SecretMissingError

    if isinstance(exc, SecretMissingError):
        if chatgpt:
            return base.failure(base.ERROR_REAUTH, CODE_NOT_CONNECTED)
        return base.failure(base.ERROR_CONFIG, "api_key_missing")
    if isinstance(exc, URLNotAllowedError):
        return base.failure(base.ERROR_CONFIG, "host_not_allowed")
    if is_timeout_error(exc):
        return base.failure(base.ERROR_TRANSIENT, "timeout")
    if is_transport_error(exc):
        # 프록시 뒤라면 닿지 못한 곳이 제공자가 아니라 프록시일 수 있다 - 사람이 볼 곳을 가른다(계획 2.10).
        return base.failure(base.ERROR_TRANSIENT, "proxy_connect" if proxied else "connect")
    # 토큰이나 키 이름이 예외 문자열에 섞일 수 있어 원문을 남기지 않는다.
    logger.warning("OpenAI 호출 실패: %s", type(exc).__name__)
    return base.failure(base.ERROR_TRANSIENT, "unexpected")


def extract_output_text(data) -> str | None:
    """응답 본문에서 글자만 - `output[].content[]` 의 `output_text`. 모양이 다르면 지어내지 않는다."""
    if not isinstance(data, dict):
        return None
    parts: list[str] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for block in item.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "output_text" and isinstance(block.get("text"), str):
                parts.append(block["text"])
    joined = "".join(parts)
    return joined or None


def usage_of(data) -> tuple[int | None, int | None]:
    usage = data.get("usage") if isinstance(data, dict) else None
    if not isinstance(usage, dict):
        return None, None

    def _int(value):
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    return _int(usage.get("input_tokens")), _int(usage.get("output_tokens"))


def _stream_failure(error) -> base.ProviderResult:
    code = str(error.get("code") or "") if isinstance(error, dict) else ""
    kind, mapped = STREAM_ERROR_KINDS.get(code, (base.ERROR_TRANSIENT, "stream_failed"))
    return base.failure(kind, mapped)


def assemble_stream(lines, *, deadline: float | None = None, clock=time.monotonic) -> base.ProviderResult:
    """SSE 줄들 → 결과. `response.output_text.delta` 를 모으고 `response.completed` 에서 사용량을 읽는다.

    `response.failed` · `response.incomplete` · `error` 는 실패다. 완료 이벤트 없이 끊기면 받은 글자가 있어도 실패다.
    ``deadline`` 을 넘기면 시간 초과다(읽기 제한은 줄 사이의 시간이라 전체 시간은 여기서 잰다).
    """
    text: list[str] = []
    for raw in lines:
        if deadline is not None and clock() > deadline:
            return base.failure(base.ERROR_TRANSIENT, "timeout")
        line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            event = json.loads(payload)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        if kind == "response.output_text.delta" and isinstance(event.get("delta"), str):
            text.append(event["delta"])
        elif kind == "response.completed":
            completed = event.get("response") if isinstance(event.get("response"), dict) else {}
            joined = "".join(text) or extract_output_text(completed)
            input_tokens, output_tokens = usage_of(completed)
            if not joined:
                return base.ProviderResult(ok=False, error_kind=base.ERROR_EMPTY, error_code="empty",
                                           input_tokens=input_tokens, output_tokens=output_tokens)
            return base.success(joined, input_tokens=input_tokens, output_tokens=output_tokens)
        elif kind == "response.failed":
            response = event.get("response") if isinstance(event.get("response"), dict) else {}
            return _stream_failure(response.get("error"))
        elif kind == "response.incomplete":
            return base.failure(base.ERROR_REQUEST, "incomplete")
        elif kind == "error":
            return _stream_failure(event.get("error") if isinstance(event.get("error"), dict) else event)
    return base.failure(base.ERROR_TRANSIENT, "stream_incomplete")


def request_body(*, system: str, user: str, model: str, max_output_tokens: int, chatgpt: bool) -> dict:
    """요청 본문. 계정 연결은 미리보기 계약이 금지한 인자를 보내지 않는다."""
    body = {
        "model": model,
        "instructions": system,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": user}]}],
        "store": False,
    }
    if chatgpt:
        body["stream"] = True
    else:
        body["max_output_tokens"] = output_tokens(model, max_output_tokens)
    return body


def parse_models(data) -> tuple[dict, ...]:
    """모델 목록 두 모양을 하나로. API 키는 `data[].id`, ChatGPT 요금제는 `models[]`(`slug`, `display_name`,
    `visibility`)다 - 요금제 목록은 `visibility == "list"` 인 것만 사람에게 보인다(공식 안내)."""
    if not isinstance(data, dict):
        return ()
    rows: list[dict] = []
    if isinstance(data.get("models"), list):
        for row in data["models"]:
            if not isinstance(row, dict) or row.get("visibility") not in (None, "list"):
                continue
            slug = row.get("slug") or row.get("id")
            if isinstance(slug, str) and slug:
                rows.append({"id": slug, "label": str(row.get("display_name") or slug)})
    elif isinstance(data.get("data"), list):
        for row in data["data"]:
            ident = row.get("id") if isinstance(row, dict) else None
            if not isinstance(ident, str) or not ident:
                continue
            if any(marker in ident.lower() for marker in NON_TEXT_MODEL_MARKERS):
                continue
            rows.append({"id": ident, "label": ident})
        rows.sort(key=lambda r: r["id"])
    return tuple(rows)


class OpenAIAdapter:
    provider = base.PROVIDER_OPENAI

    def __init__(self, *, outbound, secret_ref: str, auth_method: str, tokens=None, clock=time.monotonic) -> None:
        self._outbound = outbound
        self._secret_ref = secret_ref
        self.auth_method = auth_method
        self._chatgpt = auth_method == base.AUTH_CHATGPT
        self._tokens = tokens
        self._clock = clock

    def _proxied(self) -> bool:
        return bool(getattr(self._outbound, "proxy_display", None))

    def _auth(self) -> dict:
        return {
            "auth_type": AUTH_BEARER, "secret_ref": self._secret_ref,
            "secret_field": CHATGPT_ACCESS_FIELD if self._chatgpt else None,
        }

    def _ready(self) -> base.ProviderResult | None:
        """계정 연결이면 토큰이 쓸 만한지 먼저 본다(만료가 가까우면 갱신한다). 쓸 수 없으면 그 실패를 돌려준다."""
        if not self._chatgpt:
            return None
        if self._tokens is None:
            return base.failure(base.ERROR_CONFIG, "token_manager_missing")
        status = self._tokens.ensure_fresh()
        if status.ok:
            return None
        return base.failure(status.kind, status.code)

    # ── 생성 ─────────────────────────────────────────────────────────────────

    def generate(self, *, system: str, user: str, model: str, max_output_tokens: int,
                 timeout: float) -> base.ProviderResult:
        if self._outbound is None:
            return base.failure(base.ERROR_CONFIG, "no_outbound")
        blocked = self._ready()
        if blocked is not None:
            return blocked
        body = request_body(system=system, user=user, model=model, max_output_tokens=max_output_tokens,
                            chatgpt=self._chatgpt)
        deadline = self._clock() + float(timeout)
        if not self._chatgpt:
            return self._generate_plain(body, timeout)
        result = self._generate_stream(body, timeout, deadline)
        if result.http_status == 401 and self._tokens is not None:
            # 만료 시각 전에 거절됐다(시계가 어긋났거나 제공자가 먼저 끊었다). 한 번만 갱신해 다시 보낸다 - 그래도
            # 401 이면 연결이 끊긴 것이다.
            refreshed = self._tokens.force_refresh()
            if not refreshed.ok:
                return base.failure(refreshed.kind, refreshed.code)
            result = self._generate_stream(body, timeout, deadline)
        return result

    def _generate_plain(self, body: dict, timeout: float) -> base.ProviderResult:
        try:
            response = self._outbound.request(
                "POST", RESPONSES_URL, allowlist=ALLOWLIST, json=body, timeout=float(timeout), **self._auth(),
            )
        except Exception as exc:  # noqa: BLE001 - 실패는 값으로 돌려준다
            return _exception_result(exc, chatgpt=False, proxied=self._proxied())
        if response.status_code >= 400:
            return classify_status(response, chatgpt=False)
        try:
            data = response.json()
        except ValueError:
            return base.failure(base.ERROR_TRANSIENT, "bad_json")
        text = extract_output_text(data)
        input_tokens, output_tokens = usage_of(data)
        if not text:
            return base.ProviderResult(ok=False, error_kind=base.ERROR_EMPTY, error_code="empty",
                                       input_tokens=input_tokens, output_tokens=output_tokens)
        return base.success(text, input_tokens=input_tokens, output_tokens=output_tokens)

    def _generate_stream(self, body: dict, timeout: float, deadline: float) -> base.ProviderResult:
        remaining = max(1.0, deadline - self._clock())
        try:
            with self._outbound.stream(
                "POST", RESPONSES_URL, allowlist=ALLOWLIST, json=body, headers={"Accept": "text/event-stream"},
                timeout=min(float(timeout), remaining), **self._auth(),
            ) as response:
                if response.status_code >= 400:
                    response.read()
                    return classify_status(response, chatgpt=True)
                return assemble_stream(response.iter_lines(), deadline=deadline, clock=self._clock)
        except Exception as exc:  # noqa: BLE001
            return _exception_result(exc, chatgpt=True, proxied=self._proxied())

    # ── 대화(도구) ───────────────────────────────────────────────────────────

    def converse(self, *, system: str, turns, tools, tool_choice: str, model: str, max_output_tokens: int,
                 timeout: float) -> base.ConverseResult:
        """도구를 쓰는 한 번의 호출(D-535). 계정 연결은 호출마다 401 을 한 번 갱신해 다시 보낸다(`generate()` 와 같다)."""
        if self._outbound is None:
            return base.converse_failure(base.ERROR_CONFIG, "no_outbound")
        blocked = self._ready()
        if blocked is not None:
            return base.converse_from_failure(blocked)
        body = converse_body(system=system, turns=turns, tools=tools, tool_choice=tool_choice, model=model,
                             max_output_tokens=max_output_tokens, chatgpt=self._chatgpt)
        deadline = self._clock() + float(timeout)
        if not self._chatgpt:
            return self._converse_plain(body, timeout)
        result = self._converse_stream(body, timeout, deadline)
        if result.http_status == 401 and self._tokens is not None:
            refreshed = self._tokens.force_refresh()
            if not refreshed.ok:
                return base.converse_failure(refreshed.kind, refreshed.code)
            result = self._converse_stream(body, timeout, deadline)
        return result

    def _converse_plain(self, body: dict, timeout: float) -> base.ConverseResult:
        try:
            response = self._outbound.request(
                "POST", RESPONSES_URL, allowlist=ALLOWLIST, json=body, timeout=float(timeout), **self._auth(),
            )
        except Exception as exc:  # noqa: BLE001 - 실패는 값으로 돌려준다
            return base.converse_from_failure(_exception_result(exc, chatgpt=False, proxied=self._proxied()))
        if response.status_code >= 400:
            return base.converse_from_failure(classify_status(response, chatgpt=False))
        try:
            data = response.json()
        except ValueError:
            return base.converse_failure(base.ERROR_TRANSIENT, "bad_json")
        return read_output(data)

    def _converse_stream(self, body: dict, timeout: float, deadline: float) -> base.ConverseResult:
        remaining = max(1.0, deadline - self._clock())
        try:
            with self._outbound.stream(
                "POST", RESPONSES_URL, allowlist=ALLOWLIST, json=body, headers={"Accept": "text/event-stream"},
                timeout=min(float(timeout), remaining), **self._auth(),
            ) as response:
                if response.status_code >= 400:
                    response.read()
                    return base.converse_from_failure(classify_status(response, chatgpt=True))
                return assemble_turn(response.iter_lines(), deadline=deadline, clock=self._clock)
        except Exception as exc:  # noqa: BLE001
            return base.converse_from_failure(_exception_result(exc, chatgpt=True, proxied=self._proxied()))

    # ── 모델 목록 ─────────────────────────────────────────────────────────────

    def list_models(self, *, timeout: float) -> base.ModelList:
        if self._outbound is None:
            return base.ModelList(ok=False, error_kind=base.ERROR_CONFIG, error_code="no_outbound")
        blocked = self._ready()
        if blocked is not None:
            return base.ModelList(ok=False, error_kind=blocked.error_kind, error_code=blocked.error_code)
        try:
            response = self._outbound.request(
                "GET", MODELS_URL, allowlist=ALLOWLIST, timeout=float(timeout), **self._auth(),
            )
        except Exception as exc:  # noqa: BLE001
            failed = _exception_result(exc, chatgpt=self._chatgpt, proxied=self._proxied())
            return base.ModelList(ok=False, error_kind=failed.error_kind, error_code=failed.error_code)
        if response.status_code >= 400:
            failed = classify_status(response, chatgpt=self._chatgpt)
            return base.ModelList(ok=False, error_kind=failed.error_kind, error_code=failed.error_code)
        try:
            data = response.json()
        except ValueError:
            return base.ModelList(ok=False, error_kind=base.ERROR_TRANSIENT, error_code="bad_json")
        return base.ModelList(ok=True, models=parse_models(data))


# ── 대화 — 도구를 쓰는 차례 (D-535) ───────────────────────────────────────────
#
# Responses API 의 함수 도구다: 요청 `tools[{type:"function", name, description, parameters, strict:true}]` · `tool_choice` ·
# `parallel_tool_calls`, 응답의 `function_call{call_id, name, arguments}` 항목, 다음 요청의 `function_call_output{call_id, output}`.
# `store=false` 라 제공자가 지난 응답을 기억하지 않는다 — 직전 응답의 output 항목을 **그대로** 다음 input 에 되싣는다. 추론 모델의
# 추론 항목은 암호화된 내용(`include: ["reasoning.encrypted_content"]`)과 함께 되돌려 보내야 다음 차례가 이어진다(공식 안내).
#
# 계정 연결(ChatGPT 요금제)은 미리보기 계약대로 `stream=true` 이고 `max_output_tokens` · `include` 를 보내지 않는다 — 암호화된 추론을
# 받지 못하므로 그 갈래에서는 추론 항목을 되싣지 않는다. 요금제가 함수 도구를 거절하면 400
# `subscription_sharing_unsupported_capability`(`unsupported_capability`)이고, 런타임이 그 사실을 적고 도구 없는 갈래로 접는다.


def tool_choice_value(choice: str):
    if isinstance(choice, str) and choice.startswith(base.TOOL_CHOICE_PREFIX):
        return {"type": "function", "name": choice[len(base.TOOL_CHOICE_PREFIX):]}
    if choice in (base.TOOL_CHOICE_NONE, base.TOOL_CHOICE_REQUIRED):
        return choice
    return base.TOOL_CHOICE_AUTO


def converse_input(turns, *, chatgpt: bool) -> list[dict]:
    """차례 → `input` 항목. assistant 차례는 받은 output 항목을 그대로 되싣는다."""
    items: list[dict] = []
    for turn in turns:
        if isinstance(turn, base.UserTurn):
            items.append({"role": "user", "content": [{"type": "input_text", "text": turn.text}]})
        elif isinstance(turn, base.AssistantTurn):
            if turn.replay:
                for item in turn.replay:
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") == "reasoning" and (chatgpt or not item.get("encrypted_content")):
                        # 암호화된 내용이 없는 추론 항목은 store=false 에서 되실을 수 없다(제공자가 그 항목을 기억하지 않는다).
                        continue
                    items.append(dict(item))
            else:
                if turn.text:
                    items.append({"role": "assistant", "content": [{"type": "output_text", "text": turn.text}]})
                for call in turn.tool_calls:
                    items.append({
                        "type": "function_call", "call_id": call.id, "name": call.name,
                        "arguments": call.raw_arguments or json.dumps(call.arguments or {}, ensure_ascii=False),
                    })
        elif isinstance(turn, base.ToolResultsTurn):
            items.extend({"type": "function_call_output", "call_id": r.call_id, "output": r.content} for r in turn.results)
    return items


def converse_body(*, system: str, turns, tools, tool_choice: str, model: str, max_output_tokens: int,
                  chatgpt: bool) -> dict:
    body = {
        "model": model,
        "instructions": system,
        "input": converse_input(turns, chatgpt=chatgpt),
        "store": False,
    }
    if tools:
        body["tools"] = [
            {"type": "function", "name": t.name, "description": t.description, "parameters": t.parameters, "strict": True}
            for t in tools
        ]
        body["tool_choice"] = tool_choice_value(tool_choice)
        body["parallel_tool_calls"] = True
    if chatgpt:
        body["stream"] = True
    else:
        body["max_output_tokens"] = output_tokens(model, max_output_tokens)
        body["include"] = ["reasoning.encrypted_content"]
    return body


def read_output(data, *, streamed_text: str = "") -> base.ConverseResult:
    """응답 본문(또는 완료 이벤트의 response) → 결과. 함수 호출 항목이 도구 호출이고, output 전체가 되실을 항목이다."""
    if not isinstance(data, dict):
        return base.converse_failure(base.ERROR_TRANSIENT, "bad_shape")
    output = tuple(item for item in (data.get("output") or []) if isinstance(item, dict))
    calls = tuple(
        base.ToolCall(
            id=str(item.get("call_id") or item.get("id") or ""), name=str(item.get("name") or ""),
            arguments=base.parse_arguments(item.get("arguments")),
            raw_arguments=item.get("arguments") if isinstance(item.get("arguments"), str) else "",
        )
        for item in output if item.get("type") == "function_call"
    )
    text = streamed_text or extract_output_text(data)
    stop = base.STOP_MAX_TOKENS if data.get("status") == "incomplete" else None
    input_tokens, output_tokens = usage_of(data)
    return base.finish(text or None, calls, output, stop_reason=stop,
                       input_tokens=input_tokens, output_tokens=output_tokens)


def assemble_turn(lines, *, deadline: float | None = None, clock=time.monotonic) -> base.ConverseResult:
    """SSE 줄들 → 대화 결과(계정 연결). `assemble_stream` 과 같은 표로 실패를 읽는다.

    글은 `response.output_text.delta` 로, 항목은 `response.output_item.added` · `…done` 으로, 함수 인자는
    `response.function_call_arguments.delta` · `…done` 으로 모은다. 완료 이벤트(`response.completed`)의 output 이 정본이고, 그것이
    비어 있으면 모은 항목으로 대신한다. 완료 없이 끊기면 받은 것이 있어도 실패다.
    """
    text: list[str] = []
    items: dict[int, dict] = {}
    for raw in lines:
        if deadline is not None and clock() > deadline:
            return base.converse_failure(base.ERROR_TRANSIENT, "timeout")
        line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            event = json.loads(payload)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        index = event.get("output_index")
        if kind == "response.output_text.delta" and isinstance(event.get("delta"), str):
            text.append(event["delta"])
        elif kind in ("response.output_item.added", "response.output_item.done") and isinstance(event.get("item"), dict):
            item = dict(event["item"])
            if kind == "response.output_item.added" and isinstance(index, int) and index in items:
                item = {**items[index], **item}
            if isinstance(index, int):
                items[index] = item
        elif kind == "response.function_call_arguments.delta" and isinstance(index, int) and isinstance(event.get("delta"), str):
            current = items.setdefault(index, {"type": "function_call"})
            current["arguments"] = str(current.get("arguments") or "") + event["delta"]
        elif kind == "response.function_call_arguments.done" and isinstance(index, int) and isinstance(event.get("arguments"), str):
            items.setdefault(index, {"type": "function_call"})["arguments"] = event["arguments"]
        elif kind == "response.completed":
            completed = dict(event.get("response")) if isinstance(event.get("response"), dict) else {}
            if not completed.get("output"):
                completed["output"] = [items[k] for k in sorted(items)]
            return read_output(completed, streamed_text="".join(text))
        elif kind == "response.failed":
            response = event.get("response") if isinstance(event.get("response"), dict) else {}
            return base.converse_from_failure(_stream_failure(response.get("error")))
        elif kind == "response.incomplete":
            # 출력 한도에 닿아 끝났다. 받은 글이 있고 도구 호출이 없으면 잘린 답으로 남긴다(`read_output` 이 status=incomplete 를
            # STOP_MAX_TOKENS 로 읽는다). 예전에는 실패로 버려 마지막 라운드의 긴 답이 고정 문장으로 바뀌었다.
            if text and not any(item.get("type") == "function_call" for item in items.values()):
                response = dict(event.get("response")) if isinstance(event.get("response"), dict) else {}
                response["status"] = "incomplete"
                if not response.get("output"):
                    response["output"] = [items[k] for k in sorted(items)]
                return read_output(response, streamed_text="".join(text))
            return base.converse_failure(base.ERROR_REQUEST, "incomplete")
        elif kind == "error":
            return base.converse_from_failure(_stream_failure(event.get("error") if isinstance(event.get("error"), dict) else event))
    return base.converse_failure(base.ERROR_TRANSIENT, "stream_incomplete")
