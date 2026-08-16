"""PA-RC-0015: 경과 시간이 분/시간/일로 자동 승급하는지 — 장애가 길어질수록 안 읽히던
"17976분" 류 문구를 막는 게이트. 경계값이 왔다갔다하지 않는지 직접 못박는다."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.core.elapsed import format_elapsed_korean
from app.observability.models import SYNC_ERROR, SYNC_OK, SyncStatus
from app.observability.router import _notice_for

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


def test_critical_stall_never_shows_a_four_digit_minute_number():
    """🔴 revert-to-verify 대상 — `minutes = int(age // 60)`으로 되돌리면 이 시험이
    "17976분"류 4자리 숫자를 만들며 실패해야 한다."""
    now = datetime(2026, 8, 16, 12, 0, 0)
    row = SyncStatus(
        component="tickets",
        status=SYNC_OK,
        last_success_at=now - timedelta(days=12, hours=13, minutes=20),
    )
    notice = _notice_for(row, "티켓", now)
    assert notice is not None
    assert "일 지났습니다" in notice["message"], notice["message"]
    assert "12일" in notice["message"], notice["message"]
    import re

    assert not re.search(r"\d{4,}분", notice["message"]), notice["message"]


def test_warning_band_unaffected_by_the_upgrade():
    """WARNING 구간(15~60분)은 예전처럼 분 단위로 남는다 — 회귀 없음."""
    now = datetime(2026, 8, 16, 12, 0, 0)
    row = SyncStatus(
        component="tickets", status=SYNC_OK,
        last_success_at=now - timedelta(minutes=22),
    )
    notice = _notice_for(row, "티켓", now)
    assert notice is not None
    assert "22분 지났습니다" in notice["message"], notice["message"]


def test_transient_error_band_still_uses_the_shared_formatter():
    now = datetime(2026, 8, 16, 12, 0, 0)
    row = SyncStatus(
        component="documents", status=SYNC_ERROR,
        last_success_at=now - timedelta(minutes=3),
    )
    notice = _notice_for(row, "문서", now)
    assert notice is not None
    assert "3분 지났습니다" in notice["message"], notice["message"]
