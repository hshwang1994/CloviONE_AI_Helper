"""스프린트 번다운 (app/sprints/burndown.py).

이 곡선이 주장하는 것은 **오직 마감일 배치**다. 우리에게는 '언제 완료됐는지'가 없으므로
날짜별 실제 이력을 그릴 수 없고, 그리는 척하지도 않는다(모듈 docstring 참고).
아래 테스트는 그 정의를 문자 그대로 고정한다.
"""

from __future__ import annotations

import pytest

from app.sprints.burndown import build_burndown
from app.tickets.repository import TicketDTO

pytestmark = pytest.mark.unit


def t(due, est, status="진행"):
    return TicketDTO(page_id=f"p-{due}-{est}-{status}", due=due, est_wd=est, status=status)


def test_points_cover_the_window_inclusive_of_the_end():
    """마지막 점이 0으로 내려앉는 모습이 있어야 '소진'으로 읽힌다."""
    out = build_burndown([], start="2026-08-03", end="2026-08-10")
    assert [p["date"] for p in out["points"]] == [
        "2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06",
        "2026-08-07", "2026-08-08", "2026-08-09", "2026-08-10",
    ]
    assert out["total_est_wd"] == 0


def test_planned_line_drains_as_due_dates_pass():
    tickets = [t("2026-08-03", 2.0), t("2026-08-05", 3.0)]
    out = build_burndown(tickets, start="2026-08-03", end="2026-08-06")
    planned = {p["date"]: p["planned"] for p in out["points"]}
    assert planned["2026-08-03"] == 5.0
    assert planned["2026-08-04"] == 3.0  # 3일 마감분(2.0)이 빠진다
    assert planned["2026-08-05"] == 3.0
    assert planned["2026-08-06"] == 0.0
    assert out["total_est_wd"] == 5.0


def test_the_gap_between_the_two_lines_is_work_already_finished():
    tickets = [t("2026-08-05", 3.0, "완료"), t("2026-08-05", 2.0, "진행")]
    out = build_burndown(tickets, start="2026-08-03", end="2026-08-06")
    first = out["points"][0]
    assert first["planned"] == 5.0
    assert first["open"] == 2.0  # 완료분은 open 에서 빠진다 → 간격 3.0 = 끝낸 일


def test_cancelled_tickets_are_in_neither_line():
    tickets = [t("2026-08-04", 4.0, "취소"), t("2026-08-04", 1.0)]
    out = build_burndown(tickets, start="2026-08-03", end="2026-08-05")
    assert out["total_est_wd"] == 1.0
    assert out["points"][0] == {"date": "2026-08-03", "planned": 1.0, "open": 1.0}


def test_tickets_without_a_due_date_are_not_shoved_onto_day_one():
    """없는 값을 start 로 밀어 넣으면 첫날 막대가 부풀어 '첫날에 다 몰려 있다'고 거짓말한다."""
    out = build_burndown([t(None, 9.0)], start="2026-08-03", end="2026-08-05")
    assert out["total_est_wd"] == 0
    assert all(p["planned"] == 0 for p in out["points"])


def test_missing_estimates_count_as_zero_not_as_a_crash():
    out = build_burndown([t("2026-08-03", None)], start="2026-08-03", end="2026-08-04")
    assert out["total_est_wd"] == 0


def test_a_long_range_is_thinned_instead_of_drawing_hundreds_of_points():
    out = build_burndown([], start="2026-01-01", end="2026-12-31")
    dates = [p["date"] for p in out["points"]]
    assert len(dates) <= 33
    assert dates[0] == "2026-01-01" and dates[-1] == "2026-12-31"
    assert dates == sorted(dates)


def test_a_broken_range_yields_no_points_rather_than_an_exception():
    assert build_burndown([], start="not-a-date", end="2026-08-10")["points"] == []
    assert build_burndown([], start="2026-08-10", end="2026-08-03")["points"] == []
