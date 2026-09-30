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
