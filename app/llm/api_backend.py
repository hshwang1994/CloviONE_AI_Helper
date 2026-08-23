"""같은 요약을 **API 로** (§L). 지금은 꺼져 있다. 전환용이다.

## 왜 지금 안 쓰는데 만들어 두는가

기본은 서버에 로그인된 구독 CLI 다(비용). 하지만 그 방식은 우리가 통제하지 않는 조건에
매달려 있다: 약관, rate limit, CLI 버전. 그중 하나만 어긋나도 하루아침에 못 쓴다.
그때 코드를 새로 쓰는 상태가 되면 안 된다. 그래서 **같은 인터페이스, 같은 프롬프트**로
미리 만들어 둔다.

**프롬프트를 공유하는 것이 핵심이다.** 주입 방어(`prompt.py`)를 백엔드마다 따로 두면
한쪽만 고쳐지는 날이 온다. 도구가 없는 API 쪽이 덜 위험해 보여서 먼저 느슨해지고,
그러다 API 응답이 다른 자동화의 입력이 되면 그 느슨함이 되살아난다.

## 왜 httpx 를 직접 안 쓰는가

불변 §2-2: 바깥으로 나가는 HTTP 는 `app/core/http_client.py` 의 `OutboundClient` **한 곳**
으로만 나간다. SSRF allowlist, redirect 금지, secret 주입이 거기에만 있다. 정적 검사가
`import httpx` 를 이 파일에서 막는다.

## 전환에 필요한 것 (한 줄이 아니라 두 줄인 이유)

  1. `LLM_BACKEND=api` 와 API 키 secret 참조 이름(`LLM_API_SECRET_REF`).
  2. `config/allowed-services.json` 의 `hosts` 에 `api.anthropic.com:443` 추가.

두 번째를 자동으로 열지 않는다. 설정 스위치 하나로 **새 바깥 목적지가 열리는** 것이
이 저장소가 막기로 한 모양이기 때문이다(SSRF allowlist 의 존재 이유가 그것이다).
allowlist 가 막으면 여기서는 평범한 실패로 보이고, 화면은 규칙 요약을 보여준다.

## 정직한 한계

이 파일은 **실제 API 응답으로 검증된 적이 없다.** 키 없이 돌릴 수 없어서다.
모양(`content` 배열의 `text`)은 공개 문서 기준이고, 실제로 켜는 날 첫 응답을 눈으로
확인해야 한다. 확인 안 한 것을 확인한 척 적지 않는다.
"""

from __future__ import annotations

import logging

from app.core.http_client import AUTH_API_KEY_HEADER, is_timeout_error, is_transport_error
from app.llm import cli_backend, prompt, provider

logger = logging.getLogger("app.llm.api")

# 요청 헤더에 박는 API 버전. Notion 과 같은 방식으로 고정한다(app/core/config.py 참조) -
# 버전을 안 박으면 공급자가 기본값을 바꾸는 날 응답 모양이 조용히 달라진다.
ANTHROPIC_VERSION = "2023-06-01"

# 나가는 호출을 어느 allowlist 로 볼 것인가. 러너가 아니라 외부 서비스다.
ALLOWLIST = "services"

UNAUTHORIZED_STATUSES = frozenset({401, 403})


class AnthropicApiBackend:
    """CLI 백엔드와 **같은 계약**. 부르는 쪽은 어느 쪽인지 몰라야 한다."""

    name = provider.BACKEND_API

    def __init__(
        self,
        config: provider.LlmConfig,
        *,
        outbound=None,
        nonce_factory=prompt.new_nonce,
    ) -> None:
        self._config = config
        self._outbound = outbound
        self._nonce_factory = nonce_factory

    def summarize(self, *, body: str, task: str = prompt.TASK_WEEKLY) -> provider.LlmResult:
        """본문 → 요약. CLI 백엔드와 마찬가지로 **예외를 던지지 않는다.**"""
        try:
            built = prompt.build_prompt(body=body, nonce=self._nonce_factory(), task=task)
        except prompt.EmptyBodyError:
            return provider.failure(provider.STATUS_EMPTY, self.name)
        except prompt.InvalidNonceError:
            logger.exception("난스 생성이 계약을 어겼다")
            return provider.failure(provider.STATUS_FAILED, self.name)

        if built.delimiter_conflict:
            logger.warning("본문에 구분자 흉내가 있어 걷어냈다")

        return self.run(system=built.system, user=built.user)

    def run(self, *, system: str, user: str) -> provider.LlmResult:
        """조립이 끝난 프롬프트를 실행한다. CLI 백엔드의 `run()` 과 같은 자리다 (D-202)."""
        if self._outbound is None or not self._config.api_secret_ref or not self._config.api_url:
            # 설정이 안 됐다는 사실을 성공처럼 접지 않는다. 화면이 그대로 말한다.
            return provider.failure(provider.STATUS_UNCONFIGURED, self.name)

        # 🔴 모델 기본값을 제품이 정하지 않는다(P-19). API 는 `model` 이 필수라 빈 값이면
        # 400 이 오는데, 그 400 은 "설정 안 됨" 이 아니라 "실패" 로 읽혀 원인이 가려진다.
        model = self._config.api_model or self._config.model
        if not model:
            logger.warning("모델 이름이 설정되지 않아 AI 호출을 하지 않는다")
            return provider.failure(provider.STATUS_UNCONFIGURED, self.name)

        payload = {
            "model": model,
            "max_tokens": self._config.api_max_tokens,
            # 시스템 쪽에 못박는 위치가 CLI 의 `--system-prompt` 와 같은 자리다.
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }

        try:
            response = self._outbound.request(
                "POST",
                self._config.api_url,
                allowlist=ALLOWLIST,
                json=payload,
                headers={"anthropic-version": ANTHROPIC_VERSION},
                timeout=float(cli_backend.clamp_timeout(self._config.timeout_seconds)),
                auth_type=AUTH_API_KEY_HEADER,
                secret_ref=self._config.api_secret_ref,
            )
        except FileNotFoundError:
            # secret 파일이 없다 = 아직 설정 안 됨. 장애가 아니다.
            return provider.failure(provider.STATUS_UNCONFIGURED, self.name)
        except Exception as exc:  # noqa: BLE001 - 요약 하나 때문에 리포트가 죽지 않는다
            if is_timeout_error(exc):
                return provider.failure(provider.STATUS_TIMEOUT, self.name)
            if is_transport_error(exc):
                logger.warning("LLM API 전송 실패")
                return provider.failure(provider.STATUS_FAILED, self.name)
            # secret_ref 이름이 예외 문자열에 섞일 수 있어 원문을 남기지 않는다.
            logger.warning("LLM API 호출 실패: %s", type(exc).__name__)
            return provider.failure(provider.STATUS_FAILED, self.name)

        if response.status_code in UNAUTHORIZED_STATUSES:
            # CLI 의 '로그인 안 됨'과 같은 자리다. 화면 문구도 같은 것을 쓴다.
            return provider.failure(provider.STATUS_NOT_LOGGED_IN, self.name)
        if response.status_code >= 400:
            logger.warning("LLM API HTTP %s", response.status_code)
            return provider.failure(provider.STATUS_FAILED, self.name)

        try:
            data = response.json()
        except ValueError:
            return provider.failure(provider.STATUS_FAILED, self.name)

        text = cli_backend.clean_text(_extract(data))
        if text is None:
            return provider.failure(provider.STATUS_EMPTY, self.name)
        return provider.ok(text, self.name)


def _extract(data) -> str | None:
    """`{"content": [{"type": "text", "text": ...}]}` 에서 글자만.

    모양이 다르면 **지어내지 않고** None 을 돌려준다. 다른 키에서 아무 문자열이나 주워
    오면, 응답 모양이 바뀐 날 엉뚱한 값이 요약문으로 화면에 뜬다.
    """
    if not isinstance(data, dict):
        return None
    blocks = data.get("content")
    if not isinstance(blocks, list):
        return None
    parts = [
        block.get("text")
        for block in blocks
        if isinstance(block, dict) and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    ]
    joined = "\n".join(p for p in parts if p)
    return joined or None
