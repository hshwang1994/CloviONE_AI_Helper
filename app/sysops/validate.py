"""특권 헬퍼에 들어가는 값의 검증 (§S).

## 왜 별도 모듈인가

여기를 지나는 값은 **root 로 실행되는 프로세스**에 전달된다. 검증을 액션 구현 옆에 흩어 두면
새 액션을 만들 때마다 한 벌씩 다시 쓰게 되고, 그중 하나만 느슨해도 전체가 뚫린다.
그래서 검증을 한 곳에 모으고, **액션은 이 함수들만 부른다.**

## 정규식보다 파서를 쓴다

IP·타임존은 정규식으로 짜지 않는다. `ipaddress` 와 `zoneinfo` 가 **진짜 파서**라 훨씬 좁고,
"정규식은 통과했는데 시스템은 거부한다" 같은 어긋남이 생기지 않는다. 타임존은 특히 중요하다 —
`../../etc/passwd` 같은 값이 통과해도 `zoneinfo.available_timezones()` 집합에는 없다.

## 이 모듈은 순수 함수다

파일도 프로세스도 건드리지 않으므로 Windows 개발 머신에서도 그대로 테스트된다.
실제 실행(`subprocess`)은 헬퍼에만 있다.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit
from zoneinfo import available_timezones

from app.core.errors import AppError

# RFC 1123 라벨. 밑줄·공백·슬래시가 없다는 것이 핵심이다 — argv 로 넘기므로 셸 확장은
# 애초에 없지만, 값이 설정 파일에 그대로 적히기 때문에 파일 문법을 깨뜨릴 수 있는 문자를 막는다.
_LABEL = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")

MAX_FQDN_LEN = 253
MAX_LABEL_LEN = 63


class InvalidSysopsValueError(AppError):
    status_code = 422
    code = "invalid_sysops_value"
    default_message = "시스템 설정 값이 올바르지 않습니다."


def _fail(message: str) -> None:
    raise InvalidSysopsValueError(message)


def _require_text(value: object, *, field: str, max_len: int) -> str:
    if not isinstance(value, str):
        _fail(f"{field} 는 문자열이어야 합니다.")
    text = value.strip()
    if not text:
        _fail(f"{field} 가 비어 있습니다.")
    if len(text) > max_len:
        _fail(f"{field} 가 너무 깁니다({len(text)}자, 최대 {max_len}자).")
    return text


def hostname(value: object) -> str:
    """짧은 호스트 이름(점 없음). `hostnamectl set-hostname` 에 들어간다."""
    text = _require_text(value, field="호스트 이름", max_len=MAX_LABEL_LEN)
    if not _LABEL.match(text):
        _fail(f"호스트 이름에 쓸 수 없는 문자가 있습니다: {text}")
    return text.lower()


def fqdn(value: object) -> str:
    """정규화된 도메인 이름. 끝점(`example.com.`)은 받아서 떼어 낸다."""
    text = _require_text(value, field="FQDN", max_len=MAX_FQDN_LEN + 1)
    if text.endswith("."):
        text = text[:-1]
    if len(text) > MAX_FQDN_LEN:
        _fail(f"FQDN 이 너무 깁니다({len(text)}자, 최대 {MAX_FQDN_LEN}자).")
    labels = text.split(".")
    if len(labels) < 2:
        _fail(f"FQDN 은 점을 포함해야 합니다: {text}")
    for label in labels:
        if not _LABEL.match(label):
            _fail(f"FQDN 의 이 부분이 올바르지 않습니다: {label}")
    return text.lower()


def ip_address(value: object) -> str:
    """IPv4/IPv6 주소. 정규식이 아니라 파서로 판정한다."""
    text = _require_text(value, field="IP 주소", max_len=45)
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        _fail(f"IP 주소가 올바르지 않습니다: {text}")
        raise  # pragma: no cover - _fail 이 항상 올린다


def host_or_ip(value: object) -> str:
    """NTP 서버처럼 이름과 주소를 모두 받는 자리."""
    text = _require_text(value, field="주소", max_len=MAX_FQDN_LEN)
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        pass
    stripped = text[:-1] if text.endswith(".") else text
    for label in stripped.split("."):
        if not _LABEL.match(label):
            _fail(f"주소가 올바르지 않습니다: {text}")
    return stripped.lower()


def _bounded_list(values: object, *, field: str, max_items: int) -> list:
    if not isinstance(values, (list, tuple)):
        _fail(f"{field} 는 목록이어야 합니다.")
    items = list(values)
    if not items:
        _fail(f"{field} 가 비어 있습니다.")
    if len(items) > max_items:
        # 상한이 없으면 설정 파일 한 줄이 수천 개로 불어나 서비스가 뜨지 않는다.
        _fail(f"{field} 는 최대 {max_items}개까지입니다(지금 {len(items)}개).")
    return items


def dns_servers(values: object) -> list[str]:
    """DNS 서버 목록. **주소만** 받는다 — 이름을 받으면 이름을 풀 방법이 없다."""
    items = _bounded_list(values, field="DNS 서버", max_items=4)
    out = [ip_address(v) for v in items]
    if len(set(out)) != len(out):
        _fail("DNS 서버가 중복됩니다.")
    return out


def ntp_servers(values: object) -> list[str]:
    items = _bounded_list(values, field="NTP 서버", max_items=5)
    out = [host_or_ip(v) for v in items]
    if len(set(out)) != len(out):
        _fail("NTP 서버가 중복됩니다.")
    return out


def timezone(value: object) -> str:
    """시스템이 실제로 아는 타임존인지 **집합 멤버십**으로 판정한다.

    정규식으로 `[A-Za-z/_]+` 같은 것을 쓰면 `../../..` 류가 통과할 여지가 남고, 통과시켜 봐야
    `timedatectl` 이 거절한다. 있는 것만 받는 편이 좁고 오류 메시지도 정확하다.
    """
    text = _require_text(value, field="타임존", max_len=64)
    if text not in available_timezones():
        _fail(f"알 수 없는 타임존입니다: {text}")
    return text


def proxy_url(value: object) -> str:
    """HTTP(S) 프록시 주소.

    ⚠️ **자격증명이 들어간 주소(`http://user:pw@host`)는 거절한다.** 프록시 주소는
    `/etc/environment` 처럼 **전 시스템이 읽는 파일**에 적히고 자식 프로세스 환경에도 실린다.
    거기에 비밀번호를 넣으면 이 저장소가 비밀을 파일 참조로 분리해 둔 이유가 통째로 무너진다.
    프록시 인증이 필요하면 그때 **비밀 참조**로 따로 받는다.
    """
    text = _require_text(value, field="프록시 주소", max_len=255)
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https"):
        _fail(f"프록시는 http 또는 https 여야 합니다: {text}")
    if parts.username or parts.password:
        _fail("프록시 주소에 아이디/비밀번호를 넣을 수 없습니다.")
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        _fail(f"프록시 주소에 경로나 질의를 넣을 수 없습니다: {text}")
    if not parts.hostname:
        _fail(f"프록시 주소에 호스트가 없습니다: {text}")
    host_or_ip(parts.hostname)
    try:
        port = parts.port
    except ValueError:
        _fail(f"프록시 포트가 올바르지 않습니다: {text}")
        raise  # pragma: no cover
    if port is not None and not (1 <= port <= 65535):
        _fail(f"프록시 포트가 범위를 벗어났습니다: {port}")
    return text


def no_proxy(value: object) -> str:
    """프록시 예외 목록. 쉼표로 나뉜 호스트/도메인/주소만 받는다."""
    text = _require_text(value, field="프록시 예외", max_len=512)
    out: list[str] = []
    for raw in text.split(","):
        item = raw.strip()
        if not item:
            continue
        # `.example.com` 처럼 앞점으로 하위 도메인 전체를 뜻하는 표기가 표준이라 허용한다.
        host_or_ip(item[1:] if item.startswith(".") else item)
        out.append(item)
    if not out:
        _fail("프록시 예외 목록이 비어 있습니다.")
    return ",".join(out)
