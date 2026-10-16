"""The single outbound-HTTP choke point (spec §25.3).

This is the ONLY module in app/ allowed to import httpx — enforced by a
static test. Every outbound request passes the SSRF allowlist at call time,
never follows redirects, and injects authentication from secret references
without exposing plaintext.

## 프록시 (계획 2.10, D-516)

`trust_env` 는 여전히 False 다 - `.netrc` 나 `SSL_CERT_FILE` 같은 환경 영향을 들이지 않는다. 시스템 설정이 유닛에 둔
`HTTPS_PROXY` · `HTTP_PROXY` · `NO_PROXY` 세 값만 `app/core/outbound_proxy.py` 가 **명시적으로** 읽어 라우팅으로
넘긴다. 허용 목록은 그대로 목적지에 걸린다. 시험이 전송을 끼우면(`transport=`) 프록시를 쓰지 않는다.

## 폼 본문과 스트리밍 (D-516)

OAuth 토큰 교환은 `application/x-www-form-urlencoded` 본문(`data=`)을 요구하고, ChatGPT 요금제로 부르는 응답
API 는 스트리밍(`stream()`)만 받는다. 둘 다 이 문을 지난다 - 허용 목록, redirect 금지, 비밀 주입이 같다.
비밀 칸이 JSON 묶음이면(`ai.openai.chatgpt`) `secret_field=` 로 그 안의 한 값만 꺼내 헤더에 싣는다.
"""

from __future__ import annotations

import base64
import json as json_mod
import logging
import math
import time
from contextlib import contextmanager

import httpx

from app.core import outbound_proxy
from app.core.allowlist import AllowlistRegistry
from app.core.errors import ValidationAppError
from app.core.secret_refs import FileSecretReferenceProvider, SecretMissingError

logger = logging.getLogger("app.http")

AUTH_NONE = "none"
AUTH_BEARER = "bearer"
AUTH_API_KEY_HEADER = "api_key_header"
# Atlassian Cloud 는 `이메일:API토큰` Basic 만 받는다. Bearer 로 보내면 헤더가 **조용히 무시되고**
# 익명과 똑같은 403 이 온다(실측: 익명·유효 토큰·아무 문자열 셋이 같은 응답이었다). 그래서
# 「인증이 틀렸다」가 「권한이 없다」로 보이고, 그 둘을 구별하지 못하면 하루를 잃는다.
# 시크릿 파일은 `이메일:토큰` 한 줄을 그대로 담는다 — 이메일은 비밀이 아니지만 둘을 갈라 두면
# 짝이 안 맞는 조합이 생기고, 그 조합은 401 이 아니라 위의 403 으로 나타난다.
AUTH_BASIC = "basic"

AUTH_TYPES = frozenset({AUTH_NONE, AUTH_BEARER, AUTH_API_KEY_HEADER, AUTH_BASIC})

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
        proxy: outbound_proxy.ProxySettings | None = None,
    ) -> None:
        self._allowlists = allowlists
        self._secrets = secrets
        # 재시도 대기를 주입 가능하게 둔다. 안 그러면 429 재시도 테스트가 **실제로 몇 초를
        # 자야** 하고, 느린 테스트는 곧 지워지거나 건너뛰어진다.
        self._sleep = sleep or time.sleep
        # 프록시는 시험이 전송을 끼우지 않았을 때만 건다 - 끼운 전송을 프록시 라우팅이 가로채면 시험이 가짜 대신
        # 진짜 네트워크로 나간다. 값은 프로세스가 뜰 때 한 번 읽는다(드롭인은 유닛을 다시 시작해야 반영된다).
        self._proxy = proxy if proxy is not None else outbound_proxy.proxy_settings_from_env()
        mounts = None
        if transport is None:
            plan = outbound_proxy.mount_plan(self._proxy)
            if plan:
                mounts = {
                    pattern: (None if target is None else httpx.HTTPTransport(proxy=target))
                    for pattern, target in plan
                }
        self._client = httpx.Client(
            transport=transport,
            mounts=mounts,
            follow_redirects=False,
            trust_env=False,
        )

    @property
    def proxy_display(self) -> str | None:
        """프록시를 쓰면 `호스트:포트`, 아니면 None. 화면이 「프록시 사용 중」을 말할 때 쓴다(자격 증명 없음)."""
        return self._proxy.display() if self._proxy.enabled else None

    def _secret_text(self, secret_ref: str, secret_field: str | None) -> str:
        """비밀 값 하나. JSON 묶음이면 그 안의 한 필드만 꺼낸다. 값은 어디에도 싣지 않는다."""
        text = self._secrets.require(secret_ref).reveal()
        if not secret_field:
            return text
        try:
            data = json_mod.loads(text)
        except ValueError:
            data = None
        value = data.get(secret_field) if isinstance(data, dict) else None
        if not isinstance(value, str) or not value.strip():
            # 묶음은 있는데 그 값이 비었다(예: 계정 연결을 끊은 뒤). 없는 비밀과 같게 다룬다.
            raise SecretMissingError()
        return value.strip()

    def _prepared_headers(
        self,
        url: str,
        *,
        allowlist: str,
        headers: dict[str, str] | None,
        auth_type: str,
        secret_ref: str | None,
        secret_field: str | None,
    ) -> dict[str, str]:
        # Enforcement happens here, at call time — registry-save-time checks
        # are UX, this is the security boundary.
        self._allowlists.get(allowlist).check(url)

        final_headers = dict(headers or {})
        if auth_type != AUTH_NONE:
            if auth_type not in AUTH_TYPES:
                raise ValidationAppError(f"알 수 없는 인증 방식입니다: {auth_type}")
            if not secret_ref:
                raise ValidationAppError("인증 방식에 필요한 비밀 값이 설정되어 있지 않습니다.")
            secret = self._secret_text(secret_ref, secret_field)
            if auth_type == AUTH_BEARER:
                final_headers["Authorization"] = f"Bearer {secret}"
            elif auth_type == AUTH_API_KEY_HEADER:
                final_headers["X-API-Key"] = secret
            elif auth_type == AUTH_BASIC:
                pair = secret.strip()
                if ":" not in pair:
                    # 값을 오류 메시지에 싣지 않는다. 모양만 말한다.
                    raise ValidationAppError(
                        "Basic 인증 비밀 값은 «사용자:비밀번호» 한 줄이어야 합니다."
                    )
                encoded = base64.b64encode(pair.encode("utf-8")).decode("ascii")
                final_headers["Authorization"] = f"Basic {encoded}"
        return final_headers

    def request(
        self,
        method: str,
        url: str,
        *,
        allowlist: str,
        json: dict | None = None,
        data: dict | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        auth_type: str = AUTH_NONE,
        secret_ref: str | None = None,
        secret_field: str | None = None,
        rate_limit_retries: int = 0,
    ) -> httpx.Response:
        if json is not None and data is not None:
            raise ValidationAppError("JSON 본문과 폼 본문을 함께 보낼 수 없습니다.")
        final_headers = self._prepared_headers(
            url, allowlist=allowlist, headers=headers, auth_type=auth_type, secret_ref=secret_ref,
            secret_field=secret_field,
        )

        # 재시도는 **부르는 쪽이 켠다**(기본 0). 여기서 무조건 켜면 쓰기 웹훅처럼 두 번 보내면
        # 안 되는 경로까지 함께 재시도하게 되고, 그 판단은 이 파일이 할 수 없다.
        for attempt in range(rate_limit_retries + 1):
            response = self._client.request(
                method, url, json=json, data=data, headers=final_headers, timeout=timeout
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

    @contextmanager
    def stream(
        self,
        method: str,
        url: str,
        *,
        allowlist: str,
        json: dict | None = None,
        data: dict | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        auth_type: str = AUTH_NONE,
        secret_ref: str | None = None,
        secret_field: str | None = None,
    ):
        """응답 본문을 한 줄씩 읽는 호출(서버가 보내는 이벤트). `with` 블록이 끝나면 연결을 닫는다.

        재시도는 없다 - 받는 도중에 끊긴 스트림을 다시 보내면 같은 생성을 두 번 부른다. ``timeout`` 은 한 번 읽을
        때마다의 제한이라 전체 시간은 부르는 쪽이 따로 잰다.
        """
        if json is not None and data is not None:
            raise ValidationAppError("JSON 본문과 폼 본문을 함께 보낼 수 없습니다.")
        final_headers = self._prepared_headers(
            url, allowlist=allowlist, headers=headers, auth_type=auth_type, secret_ref=secret_ref,
            secret_field=secret_field,
        )
        with self._client.stream(
            method, url, json=json, data=data, headers=final_headers, timeout=timeout
        ) as response:
            yield response

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
