"""개발자 월간 리포트 — 두 축과 사람 id 묶기를 **만든 데이터셋**으로 못박는다 (계획 3.7).

오늘은 KST 2026-07-27 로 고정한다. 확인하는 것:
- 마감일 축의 달 경계(06-30 / 07-01, 07-31 / 08-01)와 연도 경계(2025-12 / 2026-01).
- 완료일 축: 마감일이 없어도 끝낸 달에 잡힌다. KST 23:30 과 다음 날 00:30 이 다른 달로 간다.
- 늦게 끝냄(끝낸 날 > 마감일), 다시 연 티켓(끝낸 날짜 없음)은 완료일 축에 안 들어간다.
- 취소는 완료율 분모에서 빠진다. 모르는 상태는 '기타' 로 가고 칸의 합은 언제나 담당이다.
- 담당자 없음은 미할당, 휴지통 티켓은 두 축 모두에서 빠진다.
- 같은 이름 둘은 두 줄이고 `ambiguous_name`, 비활성 담당자는 자기 줄(`state`)을 갖는다.
- 한 티켓의 두 토큰이 같은 사람이면 한 번만 센다.
- 마감일 없는 열린 티켓은 `no_due` 로 따로 센다.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
from app.reports.service import BUCKETS, build_dev_monthly_report

pytestmark = pytest.mark.regression

TODAY = date(2026, 7, 27)


def _report(db, settings, period="2026-07"):
    return build_dev_monthly_report(db, None, settings, period=period, today=TODAY)


def _row(report, user_id):
    return next(r for r in report["developers"] if r["user_id"] == user_id)


@pytest.fixture()
def world(db, make_user, make_ticket):
    kim1 = make_user("kim1@goodmit.co.kr", display_name="김철수", role="user")
    kim2 = make_user("kim2@goodmit.co.kr", display_name="김철수", role="user")
    lee = make_user("lee@goodmit.co.kr", display_name="이영희", role="user")
    gone = make_user("gone@goodmit.co.kr", display_name="퇴사자", role="user")
    gone.active = False
    db.add(UserNotionMapping(user_id=kim1.id, notion_user_id="notion-kim1", status=STATUS_VERIFIED))
    db.commit()

    def ticket(title, status, due=None, people=(), completed=None, est=None, act=None):
        row = make_ticket(title=title, status=status, due=due, assignees=list(people), est_wd=est, act_wd=act)
        row.completed_at = completed
        db.commit()
        return row

    # 마감일 축 - 달 경계
    ticket("6월 마지막 날", "진행", due="2026-06-30", people=[kim1.id])
    ticket("7월 첫날", "진행", due="2026-07-01", people=[kim1.id])
    ticket("7월 마지막 날", "완료", due="2026-07-31", people=[kim1.id], completed=datetime(2026, 7, 20, 0, 0), est=2, act=3)
    ticket("8월 첫날", "진행", due="2026-08-01", people=[kim1.id])
    # 같은 사람의 두 토큰(옛 id + 자기 id) - 한 번만 센다
    ticket("두 토큰", "검증", due="2026-07-10", people=["notion-kim1", kim1.id])
    # 동명이인 - 다른 사람이다
    ticket("다른 김철수", "완료", due="2026-07-15", people=[kim2.id], completed=datetime(2026, 7, 16, 0, 0))
    # 취소와 모르는 상태
    ticket("취소", "취소", due="2026-07-12", people=[lee.id])
    ticket("옛 상태", "이슈", due="2026-07-13", people=[lee.id])
    ticket("지연", "진행", due="2026-07-05", people=[lee.id])
    # 담당자 없음
    ticket("미할당", "계획", due="2026-07-20")
    # 비활성 담당자
    ticket("퇴사자 일", "진행", due="2026-07-21", people=[gone.id])
    # 완료일 축 - 마감일 없음, KST 경계, 늦게 끝냄, 다시 연 티켓
    ticket("마감 없는 완료", "완료", people=[lee.id], completed=datetime(2026, 7, 10, 3, 0))
    ticket("KST 7월 31일 밤", "완료", people=[lee.id], completed=datetime(2026, 7, 31, 14, 30))
    ticket("KST 8월 1일 새벽", "완료", people=[lee.id], completed=datetime(2026, 7, 31, 15, 30))
    ticket("늦게 끝냄", "완료", due="2026-06-25", people=[lee.id], completed=datetime(2026, 7, 8, 0, 0))
    ticket("다시 연 티켓", "진행", due="2026-09-01", people=[lee.id], completed=None)
    # 마감 없는 열린 티켓
    ticket("마감 없는 진행", "진행", people=[kim2.id])
    # 휴지통
    trashed = ticket("휴지통", "완료", due="2026-07-18", people=[lee.id], completed=datetime(2026, 7, 18, 0, 0))
    from app.trash.models import TRASH_TICKET, TrashItem

    db.add(TrashItem(item_type=TRASH_TICKET, notion_page_id=trashed.id, title="휴지통",
                     deleted_by_user_id=lee.id, deleted_by_name="이영희", deleted_at=datetime(2026, 7, 19)))
    db.commit()
    return {"kim1": kim1.id, "kim2": kim2.id, "lee": lee.id, "gone": gone.id}


def test_the_due_axis_respects_month_boundaries(db, settings, world):
    report = _report(db, settings)
    kim1 = _row(report, world["kim1"])
    titles = [t["title"] for t in kim1["tickets"]]
    assert "7월 첫날" in titles and "7월 마지막 날" in titles
    assert "6월 마지막 날" not in titles and "8월 첫날" not in titles


def test_the_year_change_is_a_month_boundary(db, settings, make_user, make_ticket):
    user = make_user("year@goodmit.co.kr", display_name="연말", role="user")
    make_ticket(title="12월 31일", status="진행", due="2025-12-31", assignees=[user.id])
    make_ticket(title="1월 1일", status="진행", due="2026-01-01", assignees=[user.id])
    dec = _row(_report(db, settings, "2025-12"), user.id)
    jan = _row(_report(db, settings, "2026-01"), user.id)
    assert [t["title"] for t in dec["tickets"]] == ["12월 31일"]
    assert [t["title"] for t in jan["tickets"]] == ["1월 1일"]


def test_two_tokens_of_one_person_count_once(db, settings, world):
    kim1 = _row(_report(db, settings), world["kim1"])
    assert [t["title"] for t in kim1["tickets"]].count("두 토큰") == 1
    assert kim1["verify"] == 1


def test_same_name_people_stay_apart(db, settings, world):
    report = _report(db, settings)
    kims = [r for r in report["developers"] if r["name"] == "김철수"]
    assert {r["user_id"] for r in kims} == {world["kim1"], world["kim2"]}
    assert all(r["ambiguous_name"] for r in kims)
    assert {r["email"] for r in kims} == {"kim1@goodmit.co.kr", "kim2@goodmit.co.kr"}


def test_buckets_always_add_up_and_unknown_status_is_other(db, settings, world):
    report = _report(db, settings)
    for row in report["developers"]:
        assert sum(row[b] for b in BUCKETS) == row["assigned"], row["name"]
    lee = _row(report, world["lee"])
    assert lee["other"] == 1 and lee["cancel"] == 1
    team = report["team"]
    parts = team["done"] + team["in_progress"] + team["verify"] + team["plan"] + team["hold"] + team["cancel"] + team["other"]
    assert parts == team["total"]


def test_cancel_leaves_the_completion_rate_denominator(db, settings, world):
    lee = _row(_report(db, settings), world["lee"])
    # 7월 마감: 취소 1, 이슈(기타) 1, 지연 1 → 분모는 담당 3 - 취소 1 = 2, 완료 0
    assert lee["assigned"] == 3
    assert lee["completion_rate"] == 0
    # 지연은 마감이 지났는데 완료 · 취소가 아닌 것이다. 모르는 상태(이슈)도 끝났다는 증거가 없으므로 지연이다.
    assert lee["overdue"] == 2


def test_unassigned_and_inactive_assignees(db, settings, world):
    report = _report(db, settings)
    assert report["unassigned"]["total"] == 1 and report["unassigned"]["plan"] == 1
    gone = _row(report, world["gone"])
    assert gone["state"] == "inactive" and gone["assigned"] == 1
    assert not any(r["name"] == "(미확인 담당자)" and r["assigned"] for r in report["developers"])


def test_the_completion_axis_uses_kst_months(db, settings, world):
    july = _report(db, settings)
    lee = _row(july, world["lee"])["completed"]
    # 마감 없는 완료 · KST 7/31 밤 · 늦게 끝냄 = 3 (휴지통과 8월 새벽은 빠진다)
    assert lee["done"] == 3, lee
    assert lee["late_done"] == 1
    aug = _row(_report(db, settings, "2026-08"), world["lee"])["completed"]
    assert aug["done"] == 1, "KST 8월 1일 새벽에 끝낸 일이 8월에 안 잡혔다"


def test_trashed_tickets_leave_both_axes(db, settings, world):
    report = _report(db, settings)
    lee = _row(report, world["lee"])
    assert "휴지통" not in [t["title"] for t in lee["tickets"]]
    assert report["completed"]["team"]["done"] == 5  # 7월 마지막 날 · 다른 김철수 · 마감 없음 · 7/31 밤 · 늦게 끝냄


def test_open_tickets_without_due_are_counted_apart(db, settings, world):
    report = _report(db, settings)
    assert _row(report, world["kim2"])["no_due"]["open"] == 1
    assert report["no_due"]["team"]["open"] >= 1


def test_rounding_goes_half_up(db, settings, make_user, make_ticket):
    from app.reports.service import pct

    assert pct(1, 8) == 13  # 12.5 → 13 (짝수 쪽으로 보내면 12 였다)
    assert pct(5, 8) == 63  # 62.5 → 63
    assert pct(0, 0) is None


def test_definitions_travel_with_the_numbers(db, settings, world):
    report = _report(db, settings)
    assert "completion_rate" in report["definitions"]
    assert report["today"] == "2026-07-27" and report["timezone"] == settings.timezone
