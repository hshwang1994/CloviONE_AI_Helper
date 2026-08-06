"""'팀 티켓' 이 **정말 팀 티켓이다** (1순위 유출 #1).

`GET /api/tickets/team` 은 `repo.list_all(db)` 였다 — **포탈 전체 티켓**이다. 화면 이름은
'팀 티켓' 인데 다른 팀 사람의 티켓이 담당자 이름과 함께 전부 보였다. 사용자 지시("스프린트
회의, 팀 티켓 등은 기본적으로 본인이 속한 팀 정보를 봐야 한다")와 정면으로 어긋난다.

## 판정은 담당자 집합

`core/scope.py` 가 이미 종결한 규칙을 그대로 쓴다 — 담당자 중 **한 명이라도** 범위 안이면
보인다(`any_assignee_visible`). 스칼라 하나로 정하면 두 팀이 함께 맡은 티켓이 한쪽에서
통째로 사라진다.

## 담당자를 해석할 수 없는 티켓

부서 화면에는 안 나온다. 그건 미할당 트리아지(`/api/tickets/unassigned`)가 담당하고,
그 버킷은 **앱이 담당자를 모르는 티켓 전부**를 담도록 이미 고쳐 뒀다.
"""

from __future__ import annotations

import pytest

from tests.fakes.notion import DEFAULT_PROJECTS_DB, FakeNotionTasksDB, project_row, task_row

pytestmark = pytest.mark.security

NID_MINE, NID_THEIRS = "notion-mine", "notion-theirs"


@pytest.fixture()
def notion(fake_http) -> FakeNotionTasksDB:
    return FakeNotionTasksDB(
        rows=[
            task_row(page_id="t-mine", tid=1, title="우리팀 티켓", status="진행", people=[NID_MINE]),
            task_row(page_id="t-theirs", tid=2, title="남의팀 티켓", status="진행", people=[NID_THEIRS]),
            task_row(page_id="t-both", tid=3, title="같이 하는 티켓", status="진행",
                     people=[NID_MINE, NID_THEIRS]),
            task_row(page_id="t-ghost", tid=4, title="담당자 미해석", status="진행", people=["notion-ghost"]),
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

    me = make_user("tt-me@goodmit.co.kr", role="user", display_name="나")
    other = make_user("tt-other@goodmit.co.kr", role="user", display_name="남")
    me.department_id = mine.id
    other.department_id = theirs.id
    db.add(UserNotionMapping(user_id=me.id, notion_user_id=NID_MINE, status=STATUS_VERIFIED))
    db.add(UserNotionMapping(user_id=other.id, notion_user_id=NID_THEIRS, status=STATUS_VERIFIED))
    db.commit()

    with app.state.session_factory() as s:
        sync_tickets(s, outbound=app.state.outbound_client, settings=settings,
                     now=app.state.clock.now())
        s.commit()
    return me


def _titles(client):
    return {t["title"] for t in client.get("/api/tickets/team").json()["tickets"]}


def test_a_user_sees_their_own_team_not_the_whole_portal(client, login_as, world):
    login_as("user", email="tt-me@goodmit.co.kr")
    titles = _titles(client)

    assert "우리팀 티켓" in titles, "자기 팀 티켓이 안 보인다"
    assert "남의팀 티켓" not in titles, "화면 이름이 '팀 티켓' 인데 남의 팀 티켓이 보인다"


def test_a_shared_ticket_is_visible_to_both_teams(client, login_as, world):
    """두 팀이 함께 맡은 티켓이 한쪽에서 사라지면 그 팀은 **자기 팀이 그 일을 하고 있다는
    사실 자체를 못 본다**(scope.py 가 종결한 쟁점)."""
    login_as("user", email="tt-me@goodmit.co.kr")
    assert "같이 하는 티켓" in _titles(client)

    login_as("user", email="tt-other@goodmit.co.kr")
    assert "같이 하는 티켓" in _titles(client)


def test_a_global_admin_still_sees_the_whole_portal(client, login_as, world):
    login_as("system_admin")
    titles = _titles(client)
    assert {"우리팀 티켓", "남의팀 티켓", "담당자 미해석"} <= titles
