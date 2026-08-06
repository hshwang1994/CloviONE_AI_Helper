"""스프린트 요약도 **내 팀**이다 (1순위 유출 #3).

`GET /api/sprint/summary` 는 담당자별 집계·티켓 목록을 포탈 전체로 돌려줬다 — 즉
**담당자별 생산성이 전사 공개**였다. 사용자가 S4 에서 이 화면을 직접 지목했다
("스프린트 회의, 팀 티켓 등은 기본적으로 본인이 속한 팀 정보를 봐야 한다").

같은 성격의 `dev-monthly` 리포트는 민감 역할 게이트 + 범위를 둘 다 지나는데
이쪽은 **role 게이트조차 없었다** — 로그인만 하면 누구나 볼 수 있었다.
"""

from __future__ import annotations

import pytest

from tests.fakes.notion import DEFAULT_PROJECTS_DB, FakeNotionTasksDB, project_row, task_row

pytestmark = pytest.mark.security

NID_MINE, NID_THEIRS = "notion-s-mine", "notion-s-theirs"
WINDOW = "?start=2026-08-01&end=2026-09-01"


@pytest.fixture()
def notion(fake_http) -> FakeNotionTasksDB:
    return FakeNotionTasksDB(
        rows=[
            task_row(page_id="s-mine", tid=1, title="우리팀 스프린트", status="진행",
                     due="2026-08-10", people=[NID_MINE], est_wd=2.0),
            task_row(page_id="s-theirs", tid=2, title="남의팀 스프린트", status="진행",
                     due="2026-08-11", people=[NID_THEIRS], est_wd=3.0),
        ],
        projects=[project_row(page_id="p1", name="알파")],
        projects_db=DEFAULT_PROJECTS_DB,
    ).install(fake_http)


@pytest.fixture()
def world(client, settings, notion, make_user, db, app):
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department
    from app.tickets.sync import sync_tickets

    (settings.secrets_dir / "notion_report_token").write_text("t", encoding="utf-8")
    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.flush()
    me = make_user("sp-me@goodmit.co.kr", role="user", display_name="나")
    other = make_user("sp-other@goodmit.co.kr", role="user", display_name="남")
    me.department_id = mine.id
    other.department_id = theirs.id
    db.add(UserNotionMapping(user_id=me.id, notion_user_id=NID_MINE, status=STATUS_VERIFIED))
    db.add(UserNotionMapping(user_id=other.id, notion_user_id=NID_THEIRS, status=STATUS_VERIFIED))
    db.commit()
    with app.state.session_factory() as s:
        sync_tickets(s, outbound=app.state.outbound_client, settings=settings,
                     now=app.state.clock.now())
        s.commit()


def _summary(client):
    return client.get("/api/sprint/summary" + WINDOW).json()


def test_the_sprint_board_shows_my_team_not_the_portal(client, login_as, world):
    login_as("user", email="sp-me@goodmit.co.kr")
    body = _summary(client)
    names = {d["name"] for d in body.get("developers", [])}

    assert "나" in names, f"자기 팀 담당자가 집계에 없다: {names}"
    assert "남" not in names, f"남의 팀 담당자별 생산성이 그대로 보인다: {names}"


def test_the_per_assignee_ticket_lists_follow_too(client, login_as, world):
    """집계만 좁히고 티켓 목록을 열어 두면 제목으로 다 새어 나간다."""
    login_as("user", email="sp-me@goodmit.co.kr")
    body = _summary(client)
    titles = {
        t.get("title")
        for group in (body.get("by_assignee") or [])
        for t in (group.get("tickets") or [])
    }
    assert "남의팀 스프린트" not in titles, f"남의 팀 티켓 제목이 보인다: {titles}"


def test_a_global_admin_still_sees_the_whole_portal(client, login_as, world):
    login_as("system_admin")
    names = {d["name"] for d in _summary(client).get("developers", [])}
    assert {"나", "남"} <= names, f"전체 관리자가 전부 못 본다: {names}"
