"""정합성 진단 — 회차의 팀 (D-482).

두 항목이 새로 선다. 둘 다 **API 가 막는 상태**라 정상 경로로는 생기지 않고, 마이그레이션이
근거 없이 귀속하지 않은 레거시(팀 미정)나 직접 수정으로만 생긴다 — 그래서 세는 화면이
있어야 아무도 못 보는 채로 남지 않는다.

  * `sprints_without_team` — 팀이 정해지지 않은 회차. 관리자가 팀을 정하기 전까지 팀
    사용자에게 안 보이고 담기·열기가 막힌다.
  * `open_sprint_tickets_off_team` — 열린 회차에 담긴 다른 팀의 티켓. **닫힌 회차는 과거
    기록이라 세지 않는다** — 프로젝트가 나중에 다른 팀으로 옮겨져도 옛 회차는 오류가 아니다.

반례를 같은 파일에 둔다: 같은 팀 티켓만 담긴 열린 회차와 팀이 있는 회차는 잡히지 않는다.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.integrity import service as integrity
from app.org.constants import DEFAULT_ORG_ID
from app.org.models import Department
from app.projects.models import Project
from app.tickets.models import PROJECT_LINK_OK, Ticket
from app.work import codes as work_codes
from app.work.models import Sprint

pytestmark = pytest.mark.integration

TODAY = date(2026, 8, 27)


@pytest.fixture()
def world(db):
    team_a = Department(name="진단 A팀", org_id=DEFAULT_ORG_ID)
    team_b = Department(name="진단 B팀", org_id=DEFAULT_ORG_ID)
    db.add_all([team_a, team_b])
    db.flush()
    pa = work_codes.insert_with_code(
        db, Project(name="진단 A 프로젝트", org_id=DEFAULT_ORG_ID, dept_id=team_a.id)
    )
    pb = work_codes.insert_with_code(
        db, Project(name="진단 B 프로젝트", org_id=DEFAULT_ORG_ID, dept_id=team_b.id)
    )
    p0 = work_codes.insert_with_code(db, Project(name="진단 공통 프로젝트", org_id=DEFAULT_ORG_ID))
    db.flush()

    def sprint(name, team, state):
        row = Sprint(
            name=name, department_id=team.id if team is not None else None,
            org_id=DEFAULT_ORG_ID, starts_on=TODAY - timedelta(days=3),
            ends_on=TODAY + timedelta(days=4), state=state,
        )
        db.add(row)
        db.flush()
        return row

    open_a = sprint("열린 A 회차", team_a, "active")
    closed_a = sprint("닫힌 A 회차", team_a, "closed")
    unassigned = sprint("팀 미정 회차", None, "planned")
    unassigned_closed = sprint("팀 미정 닫힌 회차", None, "closed")

    def ticket(n, project, sprint_row):
        row = Ticket(
            title=f"진단 티켓 {n}", notion_page_id=f"integ-sprint-{n}",
            project_uid=project.id, project_link=PROJECT_LINK_OK, status="진행",
            org_id=DEFAULT_ORG_ID, source="notion", notion_ticket_number=n, seq=n,
            sprint_id=sprint_row.id,
        )
        db.add(row)
        db.flush()
        return row

    ok = ticket(1, pa, open_a)                 # 같은 팀 — 정상
    off_open = ticket(2, pb, open_a)           # 다른 팀 티켓이 열린 회차에 — 잡힌다
    common_open = ticket(3, p0, open_a)        # 조직 공통 티켓이 열린 회차에 — 잡힌다
    off_closed = ticket(4, pb, closed_a)       # 닫힌 회차 — 기록이라 안 잡힌다
    db.commit()
    return {
        "open_a": open_a, "closed_a": closed_a, "unassigned": unassigned,
        "unassigned_closed": unassigned_closed,
        "ok": ok, "off_open": off_open, "common_open": common_open, "off_closed": off_closed,
    }


def _finding(db, key):
    report = integrity.report(db)
    return next(f for f in report["findings"] if f["key"] == key)


def test_sprints_without_a_team_are_listed_whatever_their_state(db, world):
    finding = _finding(db, "sprints_without_team")
    ids = {i["id"] for i in finding["items"]}
    assert ids == {world["unassigned"].id, world["unassigned_closed"].id}, finding
    assert finding["count"] == 2
    assert finding["fixable_here"] is False
    states = {i["id"]: i["state"] for i in finding["items"]}
    assert states[world["unassigned_closed"].id] == "closed"


def test_off_team_tickets_are_counted_only_in_open_sprints(db, world):
    finding = _finding(db, "open_sprint_tickets_off_team")
    ids = {i["ticket_id"] for i in finding["items"]}
    assert ids == {world["off_open"].id, world["common_open"].id}, finding
    assert finding["count"] == 2
    # 같은 팀 티켓과 닫힌 회차의 티켓은 없다.
    assert world["ok"].id not in ids and world["off_closed"].id not in ids
    row = next(i for i in finding["items"] if i["ticket_id"] == world["off_open"].id)
    assert row["sprint"] == "열린 A 회차" and row["sprint_dept_id"] == world["open_a"].department_id
    assert row["project_dept_id"] != row["sprint_dept_id"]


def test_the_report_carries_both_keys_even_when_clean(db):
    keys = {f["key"] for f in integrity.report(db)["findings"]}
    assert {"sprints_without_team", "open_sprint_tickets_off_team"} <= keys
    clean = _finding(db, "open_sprint_tickets_off_team")
    assert clean["count"] == 0 and clean["items"] == []
