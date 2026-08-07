"""Regression tests pinned to the app/llm + app/mail audit (round 5) findings.

각 테스트는 고쳐진 코드 경로가 아니라 결함 진술 그 자체를 재현한다. mail_send.py 의
render 실패 경로는 tests/integration/test_mail_delivery.py 에 있다 (그 파일이 이미
mail_send 워커 경로 전체를 다루는 자리라 거기서 함께 본다).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.regression


# --- 1. app/mail/config.py: timeout_seconds 가 port 처럼 방어되지 않았다 -------


def test_smtp_config_falls_back_instead_of_raising_on_bad_timeout():
    """모듈 docstring: '모양이 이상하면 기본값으로 떨어진다 ... 예외를 던지면 로그인
    화면 렌더가 통째로 죽는다'. port 는 isdigit() 로 이미 이 계약을 지키지만
    timeout_seconds 는 지키지 않았다."""
    from app.mail.config import smtp_config

    config = smtp_config({"enabled": True, "host": "x", "timeout_seconds": "20abc"})
    assert config.timeout_seconds == 20, "쓰레기 값이면 기본값(20)으로 떨어져야 한다"


def test_smtp_config_accepts_a_normal_numeric_timeout():
    from app.mail.config import smtp_config

    config = smtp_config({"enabled": True, "host": "x", "timeout_seconds": "45"})
    assert config.timeout_seconds == 45


class _FakeSettingsCache:
    """config_from_cache 가 받는 SettingsCache 의 최소 흉내."""

    def __init__(self, value):
        self._value = value

    def current_value(self, key):
        return self._value


def test_config_from_cache_does_not_raise_on_a_malformed_cached_value():
    """registry.py 검증을 거치지 않은 값(레거시 행, 수동 DB 편집)이 캐시에 들어와도
    config_from_cache 는 config_from_db 처럼 기본값으로 떨어져야 한다 - 이 함수는
    router.py 상태 화면과 health 진단이 직접 부른다."""
    from app.mail.config import config_from_cache

    cache = _FakeSettingsCache(
        {"enabled": True, "host": "x", "timeout_seconds": "20abc"}
    )
    config = config_from_cache(cache)
    assert config.timeout_seconds == 20


# --- 2. app/llm/provider.py::_as_int: 다중 대시 문자열이 crash 났다 -----------


def test_as_int_degrades_to_none_on_a_multi_dash_string():
    """"--5".lstrip("-") 는 "5"라 isdigit() 을 통과하지만 int("--5") 는 ValueError.
    _as_int 의 나머지 분기(전부 실패-안전)와 같은 원칙으로 None 을 돌려줘야 한다."""
    from app.llm.provider import _as_int

    assert _as_int("--5") is None


def test_as_int_still_parses_ordinary_ints_and_signed_strings():
    from app.llm.provider import _as_int

    assert _as_int(30) == 30
    assert _as_int("30") == 30
    assert _as_int("-30") == -30
    assert _as_int("not a number") is None


def test_resolve_config_does_not_raise_on_a_malformed_timeout_env():
    """resolve_config 가 명시적 env 매핑(테스트, 향후 리팩터, pydantic 을 거치지 않는
    호출부)으로 불려도 크래시 대신 기본 타임아웃으로 떨어져야 한다."""
    from app.llm.provider import DEFAULT_TIMEOUT_SECONDS, resolve_config

    config = resolve_config(None, env={"LLM_TIMEOUT_SECONDS": "--5"})
    assert config.timeout_seconds == DEFAULT_TIMEOUT_SECONDS
