"""날짜 컬럼이 진짜 날짜다 — **DB 가 틀린 값을 막는다** (S7 · P-14a).

## 이 시험이 지키는 것

옛 규약은 'YYYY-MM-DD' **문자열**이었다. ISO 는 사전순이 날짜순과 같아서 비교가 그냥
됐지만, 문자열은 `'2026-02-31'` 도 `'TBD'` 도 받았다. 앱이 입구마다 검사를 달았는데
**동기화와 마이그레이션은 그 입구를 안 지난다** — 그래서 값 하나가 기간 필터·공수 집계·
번다운을 조용히 왜곡했고, 번다운은 `ValueError` 를 잡아 `[]` 를 돌려주는 바람에
**HTTP 200 에 합계는 채워지고 그래프만 빈** 화면이 나왔다.

이제 컬럼이 `date`/`timestamp` 다. 규약을 문서로 약속하는 대신 **타입이 강제한다**
(D-215 가 `jsonb` 에서 쓴 것과 같은 판단).

## 그리고 화면 계약은 안 바뀌었다

응답은 여전히 'YYYY-MM-DD' 문자열이다. 저장 타입이 바뀌었다고 프런트가 함께 바뀌면
그건 이전이 아니라 재작성이다 — 경계는 `app/core/dates.py` 한 곳이다.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import inspect, text

from app.org.constants import DEFAULT_ORG_ID
from app.projects.models import Project, ProjectMilestone
from app.tickets.models import Ticket
from app.work.models import Sprint

pytestmark = pytest.mark.regression


# 이 목록이 P-14a 의 범위다. `INVENTORY/08_SQLITE.md` 10번이 가리키던 컬럼들이다.
DATE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("tickets", "due_date"),
    ("tickets", "start_date"),
    ("projects", "starts_on"),
    ("projects", "ends_on"),
    ("project_milestones", "due_on"),
    ("project_health_snapshots", "week_of"),
    ("project_weekly_reports", "week_of"),
    ("document_cache", "doc_date"),
    ("document_cache", "orig_date"),
    ("sprints", "starts_on"),
    ("sprints", "ends_on"),
)

TIMESTAMP_COLUMNS: tuple[tuple[str, str], ...] = (
    ("tickets", "notion_created_time"),
    ("tickets", "notion_last_edited"),
    ("projects", "notion_last_edited"),
    ("document_cache", "created_time"),
    ("document_cache", "last_edited"),
)


def _type_of(db, table: str, column: str) -> str:
    for col in inspect(db.get_bind()).get_columns(table):
        if col["name"] == column:
            return str(col["type"]).upper()
    raise AssertionError(f"{table}.{column} 이 없다")


@pytest.mark.parametrize("table,column", DATE_COLUMNS)
def test_every_calendar_day_column_is_a_date(db, table, column):
    assert _type_of(db, table, column) == "DATE", (
        f"{table}.{column} 이 아직 문자열이다 — 그 컬럼에는 '2026-02-31' 이 들어간다"
    )


@pytest.mark.parametrize("table,column", TIMESTAMP_COLUMNS)
def test_every_timestamp_column_is_a_timestamp(db, table, column):
    assert "TIMESTAMP" in _type_of(db, table, column), (
        f"{table}.{column} 이 아직 문자열이다"
    )


def test_the_column_list_above_is_not_vacuous(db):
    """표가 비면 위 두 시험이 **아무것도 확인하지 않고** 통과한다."""
    assert len(DATE_COLUMNS) + len(TIMESTAMP_COLUMNS) == 16


# ── DB 가 실제로 막는가 ─────────────────────────────────────────────────────


def test_the_database_refuses_a_day_that_does_not_exist(db):
    """`2026-02-31` — 정규식은 통과시키고 달력은 통과시키지 않는 값이다.

    옛 컬럼은 이 값을 그대로 받았고, 그 하나가 기간 필터를 조용히 왜곡했다.
    """
    with pytest.raises(Exception) as caught:
        db.execute(text(
            "INSERT INTO tickets (id, notion_page_id, title, due_date,"
            " project_ids, project_names, assignee_notion_ids, source,"
            " synced_at, created_at, updated_at)"
            " VALUES ('bad-1','bad-page-1','틀린 날짜','2026-02-31',"
            " '', '', '', 'notion', now(), now(), now())"
        ))
        db.flush()
    assert "date" in str(caught.value).lower(), caught.value
    db.rollback()


def test_the_database_refuses_a_word_where_a_date_belongs(db):
    with pytest.raises(Exception):
        db.execute(text(
            "INSERT INTO tickets (id, notion_page_id, title, due_date,"
            " project_ids, project_names, assignee_notion_ids, source,"
            " synced_at, created_at, updated_at)"
            " VALUES ('bad-2','bad-page-2','TBD','TBD',"
            " '', '', '', 'notion', now(), now(), now())"
        ))
        db.flush()
    db.rollback()


def test_a_real_date_still_goes_in(db):
    """반대편 — 여기서 실패하면 위 둘은 「전부 거절하는 컬럼」도 통과시킨다."""
    row = Ticket(
        id="ok-1", notion_page_id="ok-page-1", title="정상",
        due_date=date(2026, 8, 22), source="notion",
        notion_last_edited=datetime(2026, 8, 22, 10, 0),
    )
    db.add(row)
    db.flush()
    db.expire(row)
    assert row.due_date == date(2026, 8, 22)
    assert row.notion_last_edited == datetime(2026, 8, 22, 10, 0)


# ── 화면 계약은 그대로다 ────────────────────────────────────────────────────


def test_the_project_api_still_answers_with_iso_strings(client, login_as, db):
    """저장 타입이 바뀌었다고 프런트가 함께 바뀌면 그건 이전이 아니라 재작성이다."""
    project = Project(
        name="기간 있는 프로젝트", org_id=DEFAULT_ORG_ID,
        starts_on=date(2026, 8, 17), ends_on=date(2026, 8, 28),
    )
    db.add(project)
    db.flush()
    milestone = ProjectMilestone(
        project_id=project.id, name="1차 오픈", due_on=date(2026, 8, 25),
        status="planned", sort_order=0,
    )
    db.add(milestone)
    db.commit()

    headers = {"X-CSRF-Token": login_as("admin")}
    body = client.get(f"/api/projects/{project.id}", headers=headers).json()
    assert body["project"]["starts_on"] == "2026-08-17"
    assert body["project"]["ends_on"] == "2026-08-28"

    rows = client.get(f"/api/projects/{project.id}/milestones", headers=headers).json()
    assert rows["items"][0]["due_on"] == "2026-08-25"


def test_the_sprint_api_still_answers_with_iso_strings(client, login_as):
    headers = {"X-CSRF-Token": login_as("admin")}
    made = client.post(
        "/api/work/sprints",
        json={"name": "1차", "starts_on": "2026-08-17", "ends_on": "2026-08-28"},
        headers=headers,
    )
    assert made.status_code == 200, made.text
    assert made.json()["starts_on"] == "2026-08-17"
    assert made.json()["ends_on"] == "2026-08-28"


def test_a_sprint_with_an_impossible_day_is_rejected_with_422_not_500(client, login_as):
    """DB 가 막는 것과 **사용자에게 뭐가 틀렸는지 말하는 것**은 다른 일이다.

    경계에서 안 읽으면 그 실패는 flush 에서 나고, 화면에는 「서버 오류」만 뜬다.
    """
    headers = {"X-CSRF-Token": login_as("admin")}
    r = client.post(
        "/api/work/sprints",
        json={"name": "틀린 기간", "starts_on": "2026-02-31", "ends_on": "2026-03-10"},
        headers=headers,
    )
    assert r.status_code == 422, f"{r.status_code} {r.text}"


def test_a_sprint_window_must_still_be_ordered(client, login_as):
    headers = {"X-CSRF-Token": login_as("admin")}
    r = client.post(
        "/api/work/sprints",
        json={"name": "거꾸로", "starts_on": "2026-08-28", "ends_on": "2026-08-17"},
        headers=headers,
    )
    assert r.status_code == 422, r.text


# ── 동기화가 회차마다 전 행을 흔들지 않는다 ────────────────────────────────


def test_project_sync_does_not_report_a_change_when_nothing_changed(db):
    """`_apply` 는 「같은 값이면 안 쓴다」로 변화를 판정한다.

    소스가 준 **문자열**을 `date` 컬럼과 그대로 비교하면 영영 다르고, 그러면 매 회차
    전 프로젝트의 `updated_at` 이 덮여 목록 정렬(updated_at DESC)이 무너진다.
    오류는 안 난다 — 그래서 시험이 필요하다.
    """
    from app.projects.sync import _apply

    project = Project(
        name="같은 값", org_id=DEFAULT_ORG_ID, starts_on=date(2026, 8, 17),
        notion_last_edited=datetime(2026, 8, 22, 10, 0),
    )
    db.add(project)
    db.flush()

    from app.core.dates import parse_date, parse_dt

    assert _apply(project, "starts_on", parse_date("2026-08-17")) is False
    assert _apply(project, "notion_last_edited", parse_dt("2026-08-22T10:00:00.000Z")) is False
    # 반대편 — 진짜 바뀌면 True 여야 한다.
    assert _apply(project, "starts_on", parse_date("2026-08-18")) is True


def test_sprints_still_hold_a_window_constraint(db):
    """S6 이 건 `starts_on < ends_on` 이 타입 변경 뒤에도 살아 있어야 한다."""
    db.add(Sprint(
        name="거꾸로", org_id=DEFAULT_ORG_ID,
        starts_on=date(2026, 8, 28), ends_on=date(2026, 8, 17), state="planned",
    ))
    with pytest.raises(Exception):
        db.flush()
    db.rollback()
