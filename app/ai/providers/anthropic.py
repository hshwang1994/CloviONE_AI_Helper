"""Anthropic Messages API — API 키로만 연결한다 (계획 3.14 · 3.16, D-515).

## 왜 SDK 가 아니라 OutboundClient 인가

바깥으로 나가는 HTTP 는 `app/core/http_client.py::OutboundClient` 한 곳으로만 나간다(불변 §2-2). 허용 목록(SSRF),
redirect 금지, 비밀 주입이 거기에만 있다. SDK 를 들이면 두 번째 문이 생긴다. 요청은 Messages API 하나와 모델 목록
하나뿐이라 SDK 가 줄 것도 많지 않다.

## API 버전

`anthropic-version` 을 코드 상수로 고정한다. 안 박으면 제공자가 기본값을 바꾸는 날 응답 모양이 조용히 달라진다.
제품 릴리스가 이 상수와 의존성을 함께 올린다(계획 3.16).

## 무엇을 어떤 실패로 읽는가(`app/ai/providers/base.py` 의 종류)

  401, 403                      auth       키가 틀렸거나 권한이 없다
  404, 400 중 모델을 말하는 것   config     모델 이름이 없다 - 모델을 다시 골라야 한다
  그 밖의 400, 413, 422          request    이 요청만 틀렸다
  429, 529, 5xx, 시간 초과, 연결  transient  다시 하면 될 수 있다
  저장된 키 없음, 허용 목록 밖    config
"""

from __future__ import annotations

import json
import logging

from app.ai.providers import base
from app.core.http_client import AUTH_API_KEY_HEADER, is_timeout_error, is_transport_error

logger = logging.getLogger("app.ai.providers.anthropic")

MESSAGES_URL = "https://api.anthropic.com/v1/messages"
MODELS_URL = "https://api.anthropic.com/v1/models"
ANTHROPIC_VERSION = "2023-06-01"
ALLOWLIST = "services"


def _error_type(response) -> str:
    try:
        data = response.json()
    except ValueError:
        return ""
    error = data.get("error") if isinstance(data, dict) else None
    return str(error.get("type") or "") if isinstance(error, dict) else ""


def _error_mentions_model(response) -> bool:
    try:
        data = response.json()
    except ValueError:
        return False
    error = data.get("error") if isinstance(data, dict) else None
    message = str(error.get("message") or "") if isinstance(error, dict) else ""
    return "model" in message.lower()


def classify_status(response) -> base.ProviderResult:
    """HTTP 오류 응답 → 실패 종류. 원문은 싣지 않는다."""
    status = response.status_code
    if status in (401, 403):
        return base.failure(base.ERROR_AUTH, f"http_{status}", http_status=status)
    if status == 404 or (status == 400 and _error_mentions_model(response)):
        return base.failure(base.ERROR_CONFIG, "model_not_found", http_status=status)
    if status == 429 or status == 529 or status >= 500:
        return base.failure(base.ERROR_TRANSIENT, f"http_{status}", http_status=status)
    return base.failure(base.ERROR_REQUEST, _error_type(response) or f"http_{status}", http_status=status)


def _exception_result(exc: Exception, *, proxied: bool = False) -> base.ProviderResult:
    from app.core.allowlist import URLNotAllowedError
    from app.core.secret_refs import SecretMissingError

    if isinstance(exc, SecretMissingError):
        return base.failure(base.ERROR_CONFIG, "api_key_missing")
    if isinstance(exc, URLNotAllowedError):
        return base.failure(base.ERROR_CONFIG, "host_not_allowed")
    if is_timeout_error(exc):
        return base.failure(base.ERROR_TRANSIENT, "timeout")
    if is_transport_error(exc):
        # 프록시 뒤라면 닿지 못한 곳이 제공자가 아니라 프록시일 수 있다(계획 2.10).
        return base.failure(base.ERROR_TRANSIENT, "proxy_connect" if proxied else "connect")
    # 키 이름이 예외 문자열에 섞일 수 있어 원문을 남기지 않는다.
    logger.warning("Anthropic 호출 실패: %s", type(exc).__name__)
    return base.failure(base.ERROR_TRANSIENT, "unexpected")


def extract_text(data) -> str | None:
    """`{"content": [{"type": "text", "text": ...}]}` 에서 글자만. 모양이 다르면 지어내지 않고 None."""
    if not isinstance(data, dict):
        return None
    blocks = data.get("content")
    if not isinstance(blocks, list):
        return None
    parts = [
        block.get("text") for block in blocks
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
    ]
    joined = "\n".join(p for p in parts if p)
    return joined or None


def _usage(data) -> tuple[int | None, int | None]:
    usage = data.get("usage") if isinstance(data, dict) else None
    if not isinstance(usage, dict):
        return None, None

    def _int(value):
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    return _int(usage.get("input_tokens")), _int(usage.get("output_tokens"))


class AnthropicAdapter:
    provider = base.PROVIDER_ANTHROPIC
    auth_method = base.AUTH_API_KEY

    def __init__(self, *, outbound, secret_ref: str) -> None:
        self._outbound = outbound
        self._secret_ref = secret_ref

    def _headers(self) -> dict:
        return {"anthropic-version": ANTHROPIC_VERSION}

    def generate(self, *, system: str, user: str, model: str, max_output_tokens: int,
                 timeout: float) -> base.ProviderResult:
        if self._outbound is None:
            return base.failure(base.ERROR_CONFIG, "no_outbound")
        payload = {
            "model": model,
            "max_tokens": int(max_output_tokens),
            # 시스템 쪽에 못박는다 - 사용자 쪽에 섞으면 문서 속 문장이 지시와 같은 자리에 선다.
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        try:
            response = self._outbound.request(
                "POST", MESSAGES_URL, allowlist=ALLOWLIST, json=payload, headers=self._headers(),
                timeout=float(timeout), auth_type=AUTH_API_KEY_HEADER, secret_ref=self._secret_ref,
            )
        except Exception as exc:  # noqa: BLE001 - 실패는 값으로 돌려준다
            return _exception_result(exc, proxied=bool(getattr(self._outbound, "proxy_display", None)))
        if response.status_code >= 400:
            return classify_status(response)
        try:
            data = response.json()
        except ValueError:
            return base.failure(base.ERROR_TRANSIENT, "bad_json")
        text = extract_text(data)
        input_tokens, output_tokens = _usage(data)
        if not text:
            return base.ProviderResult(
                ok=False, error_kind=base.ERROR_EMPTY, error_code="empty",
                input_tokens=input_tokens, output_tokens=output_tokens,
            )
        return base.success(text, input_tokens=input_tokens, output_tokens=output_tokens)

    def converse(self, *, system: str, turns, tools, tool_choice: str, model: str, max_output_tokens: int,
                 timeout: float) -> base.ConverseResult:
        """도구를 쓰는 한 번의 호출(D-535). 실패의 종류는 `generate()` 와 같은 표다."""
        if self._outbound is None:
            return base.converse_failure(base.ERROR_CONFIG, "no_outbound")
        payload = converse_body(system=system, turns=turns, tools=tools, tool_choice=tool_choice, model=model,
                                max_output_tokens=max_output_tokens)
        try:
            response = self._outbound.request(
                "POST", MESSAGES_URL, allowlist=ALLOWLIST, json=payload, headers=self._headers(),
                timeout=float(timeout), auth_type=AUTH_API_KEY_HEADER, secret_ref=self._secret_ref,
            )
        except Exception as exc:  # noqa: BLE001 - 실패는 값으로 돌려준다
            return base.converse_from_failure(
                _exception_result(exc, proxied=bool(getattr(self._outbound, "proxy_display", None)))
            )
        if response.status_code >= 400:
            return base.converse_from_failure(classify_status(response))
        try:
            data = response.json()
        except ValueError:
            return base.converse_failure(base.ERROR_TRANSIENT, "bad_json")
        return read_turn(data)

    def list_models(self, *, timeout: float) -> base.ModelList:
        if self._outbound is None:
            return base.ModelList(ok=False, error_kind=base.ERROR_CONFIG, error_code="no_outbound")
        try:
            response = self._outbound.request(
                "GET", MODELS_URL + "?limit=100", allowlist=ALLOWLIST, headers=self._headers(),
                timeout=float(timeout), auth_type=AUTH_API_KEY_HEADER, secret_ref=self._secret_ref,
            )
        except Exception as exc:  # noqa: BLE001
            failed = _exception_result(exc, proxied=bool(getattr(self._outbound, "proxy_display", None)))
            return base.ModelList(ok=False, error_kind=failed.error_kind, error_code=failed.error_code)
        if response.status_code >= 400:
            failed = classify_status(response)
            return base.ModelList(ok=False, error_kind=failed.error_kind, error_code=failed.error_code)
        try:
            data = response.json()
        except ValueError:
            return base.ModelList(ok=False, error_kind=base.ERROR_TRANSIENT, error_code="bad_json")
        rows = data.get("data") if isinstance(data, dict) else None
        models = tuple(
            {"id": row["id"], "label": str(row.get("display_name") or row["id"])}
            for row in (rows or [])
            if isinstance(row, dict) and isinstance(row.get("id"), str) and row["id"]
        )
        return base.ModelList(ok=True, models=models)


# ── 대화 — 도구를 쓰는 차례 (D-535) ───────────────────────────────────────────
#
# Messages API 의 도구 왕복이다: 요청 `tools[{name, description, input_schema}]` · `tool_choice`, 응답의 `tool_use` 블록, 다음 요청의
# `tool_result{tool_use_id, content, is_error}`. 응답의 content 블록은 **그대로** 다음 assistant 차례로 되싣는다 — 블록을 다시 조립하면
# 제공자가 붙인 필드를 잃는다. 모든 `tool_use` 에는 결과를 반드시 준다(상한을 넘은 호출도 오류 결과로) — 안 주면 다음 요청이 400 이다.
# 차례는 user · assistant 가 번갈아야 해서 이력은 완결 쌍만 싣는다(런타임의 일).


def tool_choice_body(choice: str) -> dict:
    if choice == base.TOOL_CHOICE_NONE:
        return {"type": "none"}
    if choice == base.TOOL_CHOICE_REQUIRED:
        return {"type": "any"}
    if isinstance(choice, str) and choice.startswith(base.TOOL_CHOICE_PREFIX):
        return {"type": "tool", "name": choice[len(base.TOOL_CHOICE_PREFIX):]}
    return {"type": "auto"}


def converse_messages(turns) -> list[dict]:
    """차례 → `messages`. 사용자 말은 지시 칸, 도구 결과는 데이터 칸이다 — 둘 다 런타임이 이미 칸에 넣은 글이다."""
    out: list[dict] = []
    for turn in turns:
        if isinstance(turn, base.UserTurn):
            out.append({"role": "user", "content": turn.text})
        elif isinstance(turn, base.AssistantTurn):
            if turn.replay:
                content = [dict(block) for block in turn.replay if isinstance(block, dict)]
            else:
                content = [{"type": "text", "text": turn.text}] if turn.text else []
                content += [
                    {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments or {}}
                    for call in turn.tool_calls
                ]
            out.append({"role": "assistant", "content": content})
        elif isinstance(turn, base.ToolResultsTurn):
            out.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": r.call_id, "content": r.content, **({"is_error": True} if r.is_error else {})}
                for r in turn.results
            ]})
    return out


def converse_body(*, system: str, turns, tools, tool_choice: str, model: str, max_output_tokens: int) -> dict:
    body = {
        "model": model,
        "max_tokens": int(max_output_tokens),
        "system": system,
        "messages": converse_messages(turns),
    }
    if tools:
        body["tools"] = [{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools]
        body["tool_choice"] = tool_choice_body(tool_choice)
    return body


def read_turn(data) -> base.ConverseResult:
    """응답 → 결과. 글 블록은 이어 붙이고, `tool_use` 블록은 도구 호출이며, 블록 전체가 되실을 항목이다."""
    if not isinstance(data, dict) or not isinstance(data.get("content"), list):
        return base.converse_failure(base.ERROR_TRANSIENT, "bad_shape")
    blocks = tuple(b for b in data["content"] if isinstance(b, dict))
    texts = [b["text"] for b in blocks if b.get("type") == "text" and isinstance(b.get("text"), str)]
    calls = tuple(
        base.ToolCall(
            id=str(b.get("id") or ""), name=str(b.get("name") or ""),
            arguments=b.get("input") if isinstance(b.get("input"), dict) else None,
            raw_arguments=json.dumps(b.get("input"), ensure_ascii=False) if b.get("input") is not None else "",
        )
        for b in blocks if b.get("type") == "tool_use"
    )
    stop = {"tool_use": base.STOP_TOOL_USE, "max_tokens": base.STOP_MAX_TOKENS}.get(str(data.get("stop_reason") or ""))
    input_tokens, output_tokens = _usage(data)
    return base.finish("\n".join(t for t in texts if t) or None, calls, blocks, stop_reason=stop,
                       input_tokens=input_tokens, output_tokens=output_tokens)
