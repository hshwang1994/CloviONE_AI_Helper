"""PA-RC-0015: 경과 시간이 분/시간/일로 자동 승급하는지 — 장애가 길어질수록 안 읽히던
"17976분" 류 문구를 막는 게이트. 경계값이 왔다갔다하지 않는지 직접 못박는다."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.elapsed import format_elapsed_korean

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "seconds, expected",
    [
        (60, "1분"),
        (59 * 60, "59분"),
        (60 * 60, "1시간"),  # 60분 경계 — 분에서 시간으로 넘어간다
        (23 * 3600 + 59 * 60, "23시간"),
        (24 * 3600, "1일"),  # 24시간 경계 — 시간에서 일로 넘어간다
        (12 * 86400 + 3600 * 13, "12일"),  # 실측 사고(17976분=12.5일)와 같은 크기
    ],
)
def test_boundaries_do_not_flip_back_and_forth(seconds, expected):
    assert format_elapsed_korean(seconds) == expected


def test_negative_is_treated_as_zero_not_shown_raw():
    # 실제로 발생하면 안 되지만(시계 오차), 사람에게 음수를 보여주는 것보다 안전하다.
    assert format_elapsed_korean(-5) == "0분"


def test_long_stalls_are_never_rendered_as_a_four_digit_minute_number():
    """🔴 revert-to-verify 대상 — `minutes = int(seconds // 60)`으로 되돌리면 이 시험이
    "17976분"류 4자리 숫자를 만들며 실패해야 한다. 실측 사고(12.5일)와 같은 크기다."""
    text = format_elapsed_korean(12 * 86400 + 13 * 3600 + 20 * 60)
    assert text == "12일", text
    assert not re.search(r"\d{4,}분", text), text
    assert "분" not in text, text


def test_the_permanent_mirror_staleness_banner_is_gone():
    """티켓·문서 미러 신선도 알림이 사용자 배너에서 사라졌다는 것을 소스로 못박는다.

    예전에는 이 파일이 `app/observability/router.py::_notice_for` 를 직접 불러
    "지금 티켓 동기화가 멈춰 있습니다" 의 경과 시간 표기를 검사했다. 그 판정 자체가
    없어졌다 — 미러에 쓰는 코드가 사라진 뒤로 `sync_status` 의 마지막 성공 시각은 매일
    조금씩 더 낡아지기만 해서, 판정이 남아 있으면 모든 화면에 영원히 붙는 critical
    배너가 된다. 되살리면 이 시험이 빨개진다.
    """
    from app.observability import router as obs_router

    assert hasattr(obs_router, "_notice_for") is False
    assert hasattr(obs_router, "USER_VISIBLE") is False
    assert hasattr(obs_router, "LATE_AFTER_SECONDS") is False
    assert hasattr(obs_router, "STALLED_AFTER_SECONDS") is False
    src = Path(obs_router.__file__).read_text(encoding="utf-8")
    body = src.split('"""', 2)[-1]
    assert "동기화가" not in body, body
    assert "sync." not in body, body
