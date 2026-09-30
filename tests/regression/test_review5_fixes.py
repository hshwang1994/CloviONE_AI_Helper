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


# --- 2. AI 실행 값: 다중 대시 문자열이 crash 났다 ------------------------------
#
# 예전 자리는 `app/llm/provider.py::_as_int` 였다. 그 모듈은 D-515 에서 없어졌고, 같은 값(제한 시간, 동시 실행 수)을
# 이제 `app/ai/concurrency.py` 가 접는다. 지키는 원칙은 같다 - 망가진 값은 크래시가 아니라 기본값으로 떨어진다.


def test_a_multi_dash_timeout_degrades_to_the_default():
    """"--5".lstrip("-") 는 "5"라 isdigit() 을 통과하지만 int("--5") 는 ValueError 다."""
    from app.ai.concurrency import DEFAULT_TIMEOUT_SECONDS, clamp_timeout

    assert clamp_timeout("--5") == DEFAULT_TIMEOUT_SECONDS


def test_ordinary_values_still_parse_and_stay_in_range():
    from app.ai.concurrency import (
        DEFAULT_CONCURRENCY,
        MAX_TIMEOUT_SECONDS,
        MIN_TIMEOUT_SECONDS,
        clamp_concurrency,
        clamp_timeout,
    )

    assert clamp_timeout(30) == 30
    assert clamp_timeout("30") == 30
    assert clamp_timeout("-30") == MIN_TIMEOUT_SECONDS
    assert clamp_timeout(10_000) == MAX_TIMEOUT_SECONDS
    assert clamp_concurrency("not a number") == DEFAULT_CONCURRENCY


def test_a_malformed_stored_timeout_falls_back_instead_of_raising():
    """설정 표에 망가진 값이 있어도(손으로 고친 행, 옛 형식) 런타임은 크래시 대신 기본 제한 시간을 쓴다."""
    from app.ai.concurrency import DEFAULT_TIMEOUT_SECONDS
    from app.ai.runtime import config_from_values

    config = config_from_values({"ai_timeout_seconds": "--5"})
    assert config.timeout_seconds == DEFAULT_TIMEOUT_SECONDS
