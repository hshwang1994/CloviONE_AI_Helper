"""티켓이 **언제 생겼는가** — 날짜별 생성량 (지시 16).

여기서 지키는 것은 넷이다.

1. **날짜는 KST 달력일이다.** `created_at` 은 naive UTC 로 저장돼 있고, 그것을 그대로
   잘라 쓰면 아침에 만든 티켓이 어제 막대에 붙는다. UTC+9 이므로 00:00~08:59(UTC)에
   만든 티켓이 정확히 그 경계에 걸린다.
2. **빈 날도 낸다.** 값이 있는 날만 보내면 「사흘 연속 없었다」와 「사흘이 하루로
   붙었다」가 화면에서 같은 그림이 된다.
3. **창 밖은 안 센다.** 「전체 티켓 수」는 다른 질문이고 다른 화면이 답한다.
4. **기간에 상한이 있다.** 손으로 늘려 전 이력을 한 요청에 담게 하지 않는다.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.core.models_base import join_names
from app.projects import service
from app.tickets.models import PROJECT_LINK_OK, TicketCache

pytestmark = pytest.mark.unit

TZ = "Asia/Seoul"
TODAY = date(2026, 8, 27)


def _ticket(db, project, *, created_at: datetime) -> None:
    db.add(TicketCache(
        notion_page_id=None, title="티켓", status="진행",
        project_uid=project.id, project_link=PROJECT_LINK_OK,
        assignee_notion_ids=join_names([]), source="native",
        created_at=created_at, updated_at=created_at,
    ))


def _counts(result) -> dict:
    return {d["date"]: d["count"] for d in result["days"]}


def test_the_day_is_the_korean_calendar_day_not_the_utc_one(db, make_project):
    """🔴 **이 한 줄이 이 파일의 이유다.**

    UTC 로 08:00 에 만든 티켓은 KST 로 그날 17:00 이다 — 같은 날이다. UTC 로 23:00 에
    만든 티켓은 KST 로 **다음 날** 08:00 이다. 잘라 쓰면 그 둘이 뒤바뀐다.
    """
    project = make_project(name="추이", external_id="px-trend")
    _ticket(db, project, created_at=datetime(2026, 8, 26, 8, 0))    # KST 8/26 17:00
    _ticket(db, project, created_at=datetime(2026, 8, 26, 23, 0))   # KST 8/27 08:00
    db.commit()

    got = _counts(service.ticket_trend(db, project, today=TODAY, days=7, tz=TZ))
    assert got["2026-08-26"] == 1
    assert got["2026-08-27"] == 1, "UTC 23시 티켓이 다음 날로 안 넘어갔다"


def test_empty_days_are_still_in_the_series(db, make_project):
    project = make_project(name="추이", external_id="px-trend")
    _ticket(db, project, created_at=datetime(2026, 8, 25, 3, 0))
    db.commit()

    result = service.ticket_trend(db, project, today=TODAY, days=5, tz=TZ)
    # 5일이면 8/23~8/27 다섯 칸이 전부 있어야 한다.
    assert [d["date"] for d in result["days"]] == [
        "2026-08-23", "2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27",
    ]
    assert _counts(result)["2026-08-24"] == 0


def test_tickets_outside_the_window_are_not_counted(db, make_project):
    """창 밖은 **안 센다.** 세면 「최근 7일에 40건」이라고 적힌 줄이 40건을 안 그린다."""
    project = make_project(name="추이", external_id="px-trend")
    _ticket(db, project, created_at=datetime(2026, 1, 1, 3, 0))    # 창 밖
    _ticket(db, project, created_at=datetime(2026, 8, 26, 3, 0))   # 창 안
    db.commit()

    result = service.ticket_trend(db, project, today=TODAY, days=7, tz=TZ)
    assert result["total"] == 1
    assert sum(d["count"] for d in result["days"]) == result["total"]


def test_the_window_has_a_ceiling_and_a_floor(db, make_project):
    """기간을 손으로 늘려 전 이력을 한 요청에 담게 하지 않는다."""
    project = make_project(name="추이", external_id="px-trend")
    db.commit()

    assert len(service.ticket_trend(db, project, today=TODAY, days=99999, tz=TZ)["days"]) \
        == service.TREND_MAX_DAYS
    assert len(service.ticket_trend(db, project, today=TODAY, days=0, tz=TZ)["days"]) == 1


def test_peak_is_the_busiest_day_in_the_window(db, make_project):
    """가장 몰린 날을 함께 낸다 — 그림을 못 보는 사람이 읽는 값이다."""
    project = make_project(name="추이", external_id="px-trend")
    for _ in range(3):
        _ticket(db, project, created_at=datetime(2026, 8, 26, 3, 0))
    _ticket(db, project, created_at=datetime(2026, 8, 25, 3, 0))
    db.commit()

    assert service.ticket_trend(db, project, today=TODAY, days=7, tz=TZ)["peak"] == 3
