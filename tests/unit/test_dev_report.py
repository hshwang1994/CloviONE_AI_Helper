"""개발자 월간 리포트 집계 유닛 테스트.

## 티켓은 이제 자체 DB 표에서 온다 (S14)

예전에는 이 파일이 가짜 Notion 응답을 만들어 리포트에 먹였다. 정본이 이 서버의 `tickets`
표로 옮겨 왔으므로 표본도 그 표에 직접 심는다 — 리포트가 실제로 읽는 자리와 같은 자리다.
집계 규칙(팀 합계·담당자별 분리·검증 버킷·지연 판정·미매핑 폴백)은 티켓이 어디서 오든
같아야 하는 것이라 그대로 남는다.

`build_dev_monthly_report` 는 마감일이 그 달 안인 티켓만 읽는다. 그래서 달 밖의 티켓을
한 건 섞어 두고 그것이 안 세어지는지 함께 본다 — 옛 시험이 요청 바디의 날짜 필터를 눈으로
확인하던 자리를 결과로 대신 확인하는 것이다.

"""

from __future__ import annotations

from datetime import date

import pytest

from app.core.models_base import join_names
from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
from app.org.constants import DEFAULT_ORG_ID
from app.reports.service import build_dev_monthly_report, month_range
from app.tickets.models import PROJECT_LINK_OK, TicketCache

pytestmark = pytest.mark.unit


def _ticket(db, *, tid, title, status, due, people, est=None, act=None, diff=None):
    """티켓 한 건을 자체 DB 표에 심는다. 리포트가 읽는 컬럼만 채운다."""
    db.add(TicketCache(
        notion_page_id=f"n{tid}",
        org_id=DEFAULT_ORG_ID,
        notion_ticket_number=tid,
        url=f"https://example.invalid/{tid}",
        title=title,
        status=status,
        due_date=date.fromisoformat(due),
        est_wd=est,
        act_wd=act,
        difficulty=diff,
        project_link=PROJECT_LINK_OK,
        assignee_notion_ids=join_names(people),
    ))
    db.commit()


def _map(db, user, notion_id):
    db.add(UserNotionMapping(user_id=user.id, notion_user_id=notion_id, status=STATUS_VERIFIED))
    db.commit()


def _report(db, settings, *, period="2026-07", today=date(2026, 7, 27)):
    """리포트 한 벌. `outbound` 는 자체 DB 저장소가 쓰지 않으므로 넘기지 않는다."""
    return build_dev_monthly_report(db, None, settings, period=period, today=today)


def test_month_range_normal_and_december():
    assert month_range("2026-07") == ("2026-07-01", "2026-08-01")
    assert month_range("2026-12") == ("2026-12-01", "2027-01-01")


def test_month_range_rejects_bad_month():
    with pytest.raises(ValueError):
        month_range("2026-13")


def test_aggregates_by_developer_with_names_and_overdue(db, settings, make_user):
    dev = make_user(email="cs@goodmit.co.kr", display_name="김철수", role="admin")
    make_user(email="yh@goodmit.co.kr", display_name="이영희", role="admin")  # 티켓 없음
    _map(db, dev, "notion-cs")

    _ticket(db, tid=1, title="완료건", status="완료", due="2026-07-01",
            people=["notion-cs"], est=3, act=3, diff="4")
    _ticket(db, tid=2, title="지연건", status="진행", due="2026-07-05",
            people=["notion-cs"], est=2, diff="2")
    _ticket(db, tid=3, title="무담당", status="계획", due="2026-07-30", people=[], est=1, diff="1")
    # 달 밖의 티켓. 마감일 창이 실제로 걸리는지 보는 반례다.
    _ticket(db, tid=4, title="다음 달 건", status="진행", due="2026-08-01",
            people=["notion-cs"], est=8, diff="5")

    report = _report(db, settings)

    assert report["team"] == {
        "total": 3, "done": 1, "in_progress": 1, "verify": 0, "plan": 1, "cancel": 0,
        "overdue": 1, "est_done_total": 3.0, "est_all_total": 6.0,
    }
    assert report["unassigned"]["total"] == 1
    assert report["unassigned"]["plan"] == 1

    by_name = {r["name"]: r for r in report["developers"]}
    cs = by_name["김철수"]
    assert cs["done"] == 1 and cs["prog"] == 1 and cs["assigned"] == 2
    assert cs["est_done"] == 3.0 and cs["est_all"] == 5.0 and cs["act_done"] == 3.0
    assert cs["overdue"] == 1
    assert cs["completion_rate"] == 50
    assert cs["difficulty_avg"] == 3.0
    assert cs["has_tickets"] is True

    # 담당자별 상세 티켓 목록이 함께 온다(마감일 순).
    assert len(cs["tickets"]) == 2
    first = cs["tickets"][0]
    assert first["tid"] == 1 and first["title"] == "완료건" and first["status"] == "완료"
    assert first["est_wd"] == 3 and first["act_wd"] == 3 and first["difficulty"] == "4"
    assert first["due"] == "2026-07-01"
    assert cs["tickets"][1]["overdue"] is True  # 지연건

    # 티켓 없는 활성 사용자도 0으로 포함된다.
    yh = by_name["이영희"]
    assert yh["done"] == 0 and yh["assigned"] == 0 and yh["has_tickets"] is False and yh["tickets"] == []

    # 달 밖의 티켓은 어느 칸에도 안 들어갔다.
    assert [t["tid"] for t in cs["tickets"]] == [1, 2]


def test_verify_status_split_from_in_progress(db, settings, make_user):
    """검증 상태는 팀 합계와 담당자 집계 모두에서 진행 중과 별도 버킷으로 센다."""
    dev = make_user(email="v@goodmit.co.kr", display_name="검증자", role="admin")
    _map(db, dev, "notion-v")
    _ticket(db, tid=10, title="진행건", status="진행", due="2026-07-20",
            people=["notion-v"], est=2, diff="2")
    _ticket(db, tid=11, title="검증건", status="검증", due="2026-07-21",
            people=["notion-v"], est=3, diff="3")
    _ticket(db, tid=12, title="이슈건", status="이슈", due="2026-07-22",
            people=["notion-v"], est=1, diff="1")

    report = _report(db, settings, today=date(2026, 7, 10))
    # 팀 합계: 진행+이슈=2 는 in_progress, 검증=1 은 verify 로 분리.
    assert report["team"]["in_progress"] == 2
    assert report["team"]["verify"] == 1
    # 담당자 집계도 동일하게 분리된다(진행+이슈=2 는 prog, 검증=1 은 verify).
    v = {r["name"]: r for r in report["developers"]}["검증자"]
    assert v["prog"] == 2 and v["verify"] == 1


def test_unmapped_assignee_falls_back_to_placeholder(db, settings, make_user):
    make_user(email="a@goodmit.co.kr", display_name="가나다", role="admin")
    _ticket(db, tid=9, title="미매핑건", status="완료", due="2026-07-02",
            people=["notion-unknown"], est=2, act=2, diff="3")

    report = _report(db, settings)
    by_name = {r["name"]: r for r in report["developers"]}
    assert "(미확인 담당자)" in by_name
    assert by_name["(미확인 담당자)"]["done"] == 1


def test_an_empty_month_is_a_real_zero_not_an_error(db, settings, make_user):
    """티켓이 한 건도 없는 달은 **오류가 아니라 0** 이다.

    옛 시험 두 건이 여기 있던 자리를 대신한다. 그 둘은 토큰이 없거나 Notion 이 401 을
    답할 때 「설정 안 됨」예외가 나오는지를 봤는데, 정본이 자체 DB 로 옮겨 온 지금은 리포트가
    설정 미비로 실패할 수 있는 경로 자체가 없다. 대신 그때와 사용자가 보는 화면이 같은
    상태 — 숫자가 하나도 없는 달 — 가 조용히 깨지지 않는지를 고정한다.
    """
    make_user(email="z@goodmit.co.kr", display_name="아무개", role="admin")

    report = _report(db, settings, period="2026-06")
    assert report["period"] == "2026-06"
    assert report["team"]["total"] == 0
    assert report["unassigned"]["total"] == 0
    assert [r["name"] for r in report["developers"]] == ["아무개"]
    assert report["developers"][0]["has_tickets"] is False
