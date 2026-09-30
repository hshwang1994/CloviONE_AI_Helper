"""바깥 호출의 프록시 — 시스템 설정이 유닛에 둔 환경 변수를 **명시적으로** 읽는다 (계획 2.10, D-516).

## 무엇이 문제였나

시스템 설정 화면의 `proxy.set`(`app/sysops/actions_system.py`)은 웹과 워커 유닛에 `HTTPS_PROXY` · `HTTP_PROXY` ·
`NO_PROXY` 드롭인을 쓴다. 그런데 `OutboundClient` 는 `trust_env=False` 라 그 값을 보지 않았다. 프록시 뒤의 설치는
AI 제공자에 닿지 못했고, 화면은 「프록시를 설정했습니다」라고 말했다.

## 왜 `trust_env=True` 로 바꾸지 않는가

`trust_env` 는 프록시만 켜지 않는다. `.netrc` 의 자격 증명과 `SSL_CERT_FILE` 같은 다른 환경 영향도 함께 들인다.
바깥 호출의 문은 하나이고 그 문이 무엇을 믿는지는 코드가 정한다. 그래서 프록시 세 값만 여기서 읽어 넘긴다.

## 규칙

- 프록시가 없으면 지금과 똑같이 곧바로 연결한다.
- 허용 목록(SSRF)은 그대로 **목적지**에 걸린다. 프록시는 목적지가 아니라 경로라 허용 목록 대상이 아니고, 대신
  시스템 관리자만 `proxy.set` 으로 정할 수 있다.
- `NO_PROXY` 의 뜻은 httpx 의 환경 변수 해석과 같다. `example.com` 은 그 이름과 하위 이름을, `.example.com` 은 하위
  이름만 뺀다. `*` 는 전부 뺀다.
- 자격 증명이 든 프록시 주소는 받지 않는다(`validate.proxy_url` 이 저장 때 거절한다). 손으로 넣은 값에 들어 있어도
  화면에는 주소와 포트만 보인다.

이 모듈은 httpx 를 들이지 않는다 - 바깥 호출 라이브러리를 부르는 곳은 `app/core/http_client.py` 하나다.
"""

from __future__ import annotations

import ipaddress
import logging
import os
from dataclasses import dataclass
from urllib.parse import urlsplit

logger = logging.getLogger("app.http.proxy")


@dataclass(frozen=True)
class ProxySettings:
    https: str | None = None
    http: str | None = None
    no_proxy: tuple[str, ...] = ()

    @property
    def enabled(self) -> bool:
        return bool(self.https or self.http)

    def display(self) -> str | None:
        """화면에 보일 `호스트:포트`. 자격 증명은 싣지 않는다."""
        url = self.https or self.http
        if not url:
            return None
        parts = urlsplit(url)
        host = parts.hostname or ""
        if ":" in host:
            host = f"[{host}]"
        try:
            port = parts.port
        except ValueError:
            port = None
        return f"{host}:{port}" if port else host


def _first(env, *names: str) -> str | None:
    for name in names:
        value = env.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _usable(url: str | None) -> str | None:
    """프록시 주소로 쓸 수 있으면 그대로, 아니면 None. 값은 로그에 싣지 않는다(자격 증명이 섞였을 수 있다)."""
    if not url:
        return None
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        logger.warning("프록시 환경 변수를 주소로 읽지 못해 쓰지 않는다")
        return None
    return url


def proxy_settings_from_env(env=None) -> ProxySettings:
    """프로세스 환경의 프록시 세 값. 대문자를 먼저 본다(systemd 드롭인이 대문자로 쓴다)."""
    env = os.environ if env is None else env
    raw_no_proxy = _first(env, "NO_PROXY", "no_proxy") or ""
    return ProxySettings(
        https=_usable(_first(env, "HTTPS_PROXY", "https_proxy")),
        http=_usable(_first(env, "HTTP_PROXY", "http_proxy")),
        no_proxy=tuple(item.strip() for item in raw_no_proxy.split(",") if item.strip()),
    )


def _is_ip(text: str) -> bool:
    try:
        ipaddress.ip_address(text)
    except ValueError:
        return False
    return True


def _bypass_pattern(item: str) -> str:
    """`NO_PROXY` 항목 하나 → httpx 라우팅 패턴. httpx 가 환경 변수를 읽을 때와 같은 모양이다."""
    if "://" in item:
        return item
    if _is_ip(item):
        return f"all://[{item}]" if ":" in item else f"all://{item}"
    if item.lower() == "localhost":
        return f"all://{item}"
    return f"all://*{item}"


def mount_plan(settings: ProxySettings) -> list[tuple[str, str | None]]:
    """(라우팅 패턴, 프록시 주소 또는 None) 목록. None 은 「곧바로 연결한다」다. 프록시가 없으면 빈 목록이다.

    httpx 는 더 구체적인 패턴을 먼저 고르므로 예외(호스트 패턴)가 방식 패턴(`https://`)보다 앞선다.
    """
    if not settings.enabled:
        return []
    if "*" in settings.no_proxy:
        return []
    plan: list[tuple[str, str | None]] = [(_bypass_pattern(item), None) for item in settings.no_proxy]
    if settings.http:
        plan.append(("http://", settings.http))
    if settings.https:
        plan.append(("https://", settings.https))
    return plan


__all__ = ["ProxySettings", "mount_plan", "proxy_settings_from_env"]
