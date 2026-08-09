"""The single outbound-HTTP choke point (spec §25.3).

This is the ONLY module in app/ allowed to import httpx — enforced by a
static test. Every outbound request passes the SSRF allowlist at call time,
never follows redirects, ignores proxy environment variables, and injects
authentication from secret references without exposing plaintext.
"""

from __future__ import annotations

import logging
import math
import time

import httpx

from app.core.allowlist import AllowlistRegistry
from app.core.errors import ValidationAppError
from app.core.secret_refs import FileSecretReferenceProvider

logger = logging.getLogger("app.http")

AUTH_NONE = "none"
AUTH_BEARER = "bearer"
AUTH_API_KEY_HEADER = "api_key_header"

AUTH_TYPES = frozenset({AUTH_NONE, AUTH_BEARER, AUTH_API_KEY_HEADER})

DEFAULT_TIMEOUT_SECONDS = 10.0

# ── 429 재시도 (S9) ───────────────────────────────────────────────────────────
#
# Notion 은 초당 평균 3요청으로 제한한다. 문서 동기화 한 번이 최대 251요청이라 429 가 실제로
# 난다. 지금까지는 429 를 그냥 오류로 취급해 **동기화가 통째로 실패**했고, 사용자에게는
# 목록이 낡은 채로 남았다.
#
# **429 에만** 재시도한다. 429 는 "받긴 했지만 처리하지 않았다" 는 뜻이라 같은 요청을 다시
# 보내는 것이 안전하다 — 블록 추가처럼 두 번 하면 안 되는 요청도 마찬가지다.
# 5xx 는 다르다. 서버가 처리했는지 아닌지 알 수 없으므로 재시도하면 **중복 쓰기**가 될 수 있다.
# 그래서 5xx 는 재시도하지 않는다. 애매할 때는 안 하는 쪽이 옳다.
RETRY_STATUS = 429
MAX_RETRY_WAIT_SECONDS = 10.0
# 서버가 이보다 오래 기다리라고 하면 **기다리지 않고 포기**한다. 워커 한 칸이 몇 분씩 잡히면
# 그 사이 다른 잡이 전부 밀린다. 포기하면 SYNC_ERROR 로 남고, 그건 화면이 말해 주는 상태다.


def retry_wait_seconds(response: httpx.Response, attempt: int) -> float | None:
    """다음 재시도까지 기다릴 시간. 기다리지 않아야 하면 None.

    `Retry-After` 를 **먼저** 본다 — 서버가 아는 값이 우리 추측보다 낫다. 없을 때만
    지수 백오프로 물러난다(0.5초, 1초, 2초 …). 헤더가 이상하면 없는 것으로 친다.
    """
    raw = response.headers.get("Retry-After")
    if raw:
        try:
            wanted = float(raw.strip())
        except ValueError:
            # HTTP-date 형식도 표준이지만 Notion 은 초를 준다. 못 읽으면 백오프로 떨어진다 —
            # 여기서 날짜 파서를 들이면 시계 어긋남까지 떠안게 된다.
            wanted = None
        else:
            # CORE-07: `float("nan")`은 ValueError를 안 던진다 — 그리고 NaN과의 비교는
            # IEEE 754상 전부 False라 `wanted < 0`도 `wanted > MAX_RETRY_WAIT_SECONDS`도
            # 둘 다 안 걸려 NaN이 그대로 반환됐다. 호출부의 `time.sleep(nan)`이
            # `ValueError`를 던져 단일 아웃바운드 관문 전체가 죽었다(`inf`는 두 비교
            # 중 하나에 걸려 이미 올바르게 처리된다).
            if math.isnan(wanted):
                wanted = None
            elif wanted < 0:
                return None
            else:
                return None if wanted > MAX_RETRY_WAIT_SECONDS else wanted
    return min(0.5 * (2 ** attempt), MAX_RETRY_WAIT_SECONDS)


class OutboundClient:
    def __init__(
        self,
        allowlists: AllowlistRegistry,
        secrets: FileSecretReferenceProvider,
        transport: httpx.BaseTransport | None = None,
        sleep=None,
    ) -> None:
        self._allowlists = allowlists
        self._secrets = secrets
        # 재시도 대기를 주입 가능하게 둔다. 안 그러면 429 재시도 테스트가 **실제로 몇 초를
        # 자야** 하고, 느린 테스트는 곧 지워지거나 건너뛰어진다.
        self._sleep = sleep or time.sleep
        self._client = httpx.Client(
            transport=transport,
            follow_redirects=False,
            trust_env=False,
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        allowlist: str,
        json: dict | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        auth_type: str = AUTH_NONE,
        secret_ref: str | None = None,
        rate_limit_retries: int = 0,
    ) -> httpx.Response:
        # Enforcement happens here, at call time — registry-save-time checks
        # are UX, this is the security boundary.
        self._allowlists.get(allowlist).check(url)

        final_headers = dict(headers or {})
        if auth_type != AUTH_NONE:
            if auth_type not in AUTH_TYPES:
                raise ValidationAppError(f"알 수 없는 인증 방식입니다: {auth_type}")
            if not secret_ref:
                raise ValidationAppError("인증 방식에 필요한 secret reference가 없습니다.")
            secret = self._secrets.require(secret_ref)
            if auth_type == AUTH_BEARER:
                final_headers["Authorization"] = f"Bearer {secret.reveal()}"
            elif auth_type == AUTH_API_KEY_HEADER:
                final_headers["X-API-Key"] = secret.reveal()

        # 재시도는 **부르는 쪽이 켠다**(기본 0). 여기서 무조건 켜면 n8n 웹훅처럼 두 번 보내면
        # 안 되는 경로까지 함께 재시도하게 되고, 그 판단은 이 파일이 할 수 없다.
        for attempt in range(rate_limit_retries + 1):
            response = self._client.request(
                method, url, json=json, headers=final_headers, timeout=timeout
            )
            if response.status_code != RETRY_STATUS or attempt >= rate_limit_retries:
                return response
            wait = retry_wait_seconds(response, attempt)
            if wait is None:
                # 기다릴 근거가 없거나 너무 오래 기다려야 한다. 조용히 재시도하지 않고
                # 429 를 그대로 돌려준다 — 호출자가 SYNC_ERROR 로 남기고 화면이 말한다.
                logger.warning("429 를 받았고 재시도하지 않는다: %s", url)
                return response
            logger.info("429 를 받아 %.1f초 뒤 재시도한다 (%d/%d): %s",
                        wait, attempt + 1, rate_limit_retries, url)
            self._sleep(wait)
        return response  # pragma: no cover - 루프가 항상 반환한다

    def get(self, url: str, **kwargs) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def close(self) -> None:
        self._client.close()


def is_transport_error(exc: Exception) -> bool:
    return isinstance(exc, httpx.TransportError)


def is_timeout_error(exc: Exception) -> bool:
    return isinstance(exc, httpx.TimeoutException)
