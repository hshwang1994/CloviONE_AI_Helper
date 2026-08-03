"""내 업무량·완료 통계의 순수 집계 — 값으로 고정한다(DB·네트워크·LLM 없음).

여기서 지키는 규칙 셋:
  * **완료율의 분모에서 취소를 뺀다.** 취소된 일을 '못 한 일'로 세면 사람들이 취소 대신
    티켓을 방치하게 된다(지표가 행동을 바꾼다).
  * **배정 0건인 달의 완료율은 `null`** 이다. 0% 가 아니다 — 아무 일도 없었을 뿐이다.
  * **어느 통에도 안 들어가 사라지는 티켓이 없다.** 주간 부하는 지난 마감·마감 없음·창
    바깥까지 각각 세고, 합이 활성 티켓 수와 정확히 맞는다.
"""

from __future__ import annotations

import pytest

from app.profiles import stats

pytestmark = pytest.mark.unit

TODAY = "2026-08-03"  # 월요일


def t(tid, status="진행", due=None, est=None, act=None, priority=None):
    return {
        "id": f"page-{tid}", "tid": tid, "title": f"티켓 {tid}", "status": status,
        "due": due, "est_wd": est, "act_wd": act, "priority": priority,
    }


def test_month_keys_walks_back_across_the_year_boundary():
    assert stats.month_keys("2026-02-15", months=4) == [
        "2025-11", "2025-12", "2026-01", "2026-02"
    ]


def test_monthly_completion_excludes_cancelled_from_the_denominator():
    tickets = [
        t(1, "완료", "2026-08-10"),
        t(2, "취소", "2026-08-11"),
        t(3, "진행", "2026-08-12"),
    ]
    months = stats.monthly_completion(tickets, today=TODAY, months=1)
    august = months[-1]
    assert august["month"] == "2026-08"
    assert (august["assigned"], august["done"], august["cancelled"], august["open"]) == (3, 1, 1, 1)
    # 분모 = 3 - 1(취소) = 2 → 1/2
    assert august["completion_rate"] == 0.5


def test_month_with_no_tickets_reports_null_rate_not_zero():
    months = stats.monthly_completion([], today=TODAY, months=2)
    assert [m["completion_rate"] for m in months] == [None, None]
    assert [m["assigned"] for m in months] == [0, 0]


def test_monthly_overdue_only_counts_unfinished_past_due():
    tickets = [
        t(1, "완료", "2026-07-01"),   # 지났지만 끝났다 → 지연 아님
        t(2, "진행", "2026-07-02"),   # 지났고 안 끝났다 → 지연
    ]
    july = stats.monthly_completion(tickets, today=TODAY, months=2)[0]
    assert july["month"] == "2026-07"
    assert july["overdue"] == 1


def test_weekly_load_puts_every_active_ticket_in_exactly_one_bucket():
    tickets = [
        t(1, "진행", "2026-07-20"),           # 지난 마감
        t(2, "진행", "2026-08-05"),           # 이번 주
        t(3, "진행", "2026-08-12"),           # 다음 주
        t(4, "진행", None),                    # 마감 없음
        t(5, "진행", "2026-12-01"),           # 창 바깥
        t(6, "완료", "2026-08-05"),           # 끝난 일은 부하가 아니다
    ]
    buckets, extra = stats.weekly_load(tickets, today=TODAY, weeks=4)
    placed = sum(b["count"] for b in buckets) + sum(e["count"] for e in extra.values())
    assert placed == 5  # 활성 5건 전부, 완료 1건은 제외
    assert buckets[0]["label"] == "이번 주" and buckets[0]["count"] == 1
    assert buckets[1]["label"] == "다음 주" and buckets[1]["count"] == 1
    assert extra["overdue"]["count"] == 1
    assert extra["no_due"]["count"] == 1
    assert extra["later"]["count"] == 1


def test_weekly_load_starts_on_monday_of_the_current_week():
    # 수요일에 봐도 이번 주는 월요일부터다 — 사람이 일하는 단위가 달력 주다.
    buckets, _extra = stats.weekly_load([], today="2026-08-05", weeks=2)
    assert buckets[0]["start"] == "2026-08-03"
    assert buckets[0]["end_exclusive"] == "2026-08-10"


def test_workload_sums_only_count_the_right_tickets():
    tickets = [
        t(1, "진행", "2026-08-10", est=2),
        t(2, "진행", "2026-07-01", est=3),     # 지연
        t(3, "완료", "2026-07-05", est=1, act=4),
    ]
    body = stats.build_stats(tickets, today=TODAY)
    load = body["workload"]
    assert load["est_wd_active"] == 5.0     # 활성 두 건
    assert load["est_wd_overdue"] == 3.0
    assert load["act_wd_done"] == 4.0
    assert load["est_wd_done"] == 1.0


def test_totals_are_mutually_consistent():
    tickets = [
        t(1, "진행", TODAY),
        t(2, "이슈", "2026-08-04"),
        t(3, "완료", "2026-08-01"),
        t(4, "취소", "2026-08-02"),
        t(5, "진행", None),
        t(6, "진행", "2026-07-01"),
    ]
    totals = stats.build_stats(tickets, today=TODAY)["totals"]
    assert totals["all"] == 6
    assert totals["active"] == 4          # 완료·취소 제외
    assert totals["done"] == 1 and totals["cancelled"] == 1
    assert totals["due_today"] == 1
    assert totals["overdue"] == 1
    assert totals["blocked"] == 1
    assert totals["no_due"] == 1
    # 전체 완료율도 분모에서 취소를 뺀다: 1 / (6-1)
    assert totals["completion_rate"] == 0.2


def test_missing_or_broken_workday_values_do_not_crash():
    tickets = [t(1, "진행", "2026-08-10", est="이상한값"), t(2, "진행", "2026-08-11", est=None)]
    body = stats.build_stats(tickets, today=TODAY)
    assert body["workload"]["est_wd_active"] == 0.0


def test_unset_status_and_priority_get_a_readable_label():
    body = stats.build_stats([t(1, "", "2026-08-10", priority="")], today=TODAY)
    assert body["workload"]["by_status"][0]["name"] == stats.UNSET_LABEL
    assert body["workload"]["by_priority"][0]["name"] == stats.UNSET_LABEL


def test_empty_input_produces_a_complete_shape():
    """티켓이 0건이어도 화면이 그릴 모양은 온전해야 한다(키가 빠지면 화면이 깨진다)."""
    body = stats.build_stats([], today=TODAY, months=3, weeks=2)
    assert set(body) == {"today", "totals", "workload", "months"}
    assert len(body["months"]) == 3
    assert len(body["workload"]["by_week"]) == 2
    assert body["totals"]["completion_rate"] is None
