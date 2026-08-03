"""스프린트 주간 창(월~다음 주 월) 계산 유닛 테스트."""

from __future__ import annotations

from datetime import date, timedelta

from app.sprints.service import default_sprint_window


def test_default_sprint_window_is_monday_to_next_monday():
    for d in [date(2026, 7, 29), date(2026, 7, 27), date(2026, 8, 2), date(2027, 1, 1)]:
        start, end = default_sprint_window(d)
        monday = d - timedelta(days=d.weekday())
        assert start == monday.isoformat()          # 시작 = 그 주 월요일
        assert end == (monday + timedelta(days=7)).isoformat()  # 끝(배타) = 다음 주 월요일
        assert date.fromisoformat(start).weekday() == 0  # 월요일
