"""티켓 상세·댓글·첨부도 범위를 지킨다 (1순위 유출 #2).

`GET /api/tickets/{page_id}` 는 로그인만 하면 **id 하나로** 본문·댓글·첨부 원본 바이트까지
내줬다. 목록에서 가려 둔 것이 단건에서 새는 전형적인 IDOR 다.

## 403 이 아니라 404 다

`403` 은 "그 id 는 존재하지만 너는 못 본다" 를 알려 준다 — id 를 찍어 보며 403/404 를 세면
포탈 전체 티켓의 존재를 열거할 수 있다. 저장소 규칙(`core/scope.py` 모듈 docstring,
채팅 이미지 서빙, `get_scoped_user_or_404`)이 이미 404 로 못박아 놨다.

## ⚠️ 목록에 보이는 티켓은 **반드시 열려야 한다**

담당자를 앱 사용자로 해석할 수 없는 티켓은 미할당 트리아지에 나온다(포탈 전용 버킷).
그걸 상세에서 404 로 막으면 **목록에는 보이는데 누르면 없다고 하는** 화면이 된다.
그건 보안이 아니라 고장이다. 이 결합을 테스트가 지킨다.
"""

from __future__ import annotations

import pytest

from tests.fakes.notion import DEFAULT_PROJECTS_DB, FakeNotionTasksDB, project_row, task_row

pytestmark = pytest.mark.security

NID_MINE, NID_THEIRS = "notion-d-mine", "notion-d-theirs"


@pytest.fixture()
def notion(fake_http) -> FakeNotionTasksDB:
    return FakeNotionTasksDB(
        rows=[
            task_row(page_id="d-mine", tid=1, title="우리팀 티켓", status="진행", people=[NID_MINE]),
            task_row(page_id="d-theirs", tid=2, title="남의팀 티켓", status="진행", people=[NID_THEIRS]),
            task_row(page_id="d-ghost", tid=3, title="담당자 미해석", status="진행", people=["notion-x"]),
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
    me = make_user("td-me@goodmit.co.kr", role="user", display_name="나")
    other = make_user("td-other@goodmit.co.kr", role="user", display_name="남")
    me.department_id = mine.id
    other.department_id = theirs.id
    db.add(UserNotionMapping(user_id=me.id, notion_user_id=NID_MINE, status=STATUS_VERIFIED))
    db.add(UserNotionMapping(user_id=other.id, notion_user_id=NID_THEIRS, status=STATUS_VERIFIED))
    db.commit()
    with app.state.session_factory() as s:
        sync_tickets(s, outbound=app.state.outbound_client, settings=settings,
                     now=app.state.clock.now())
        s.commit()


def test_you_can_open_your_own_team_ticket(client, login_as, world):
    login_as("user", email="td-me@goodmit.co.kr")
    assert client.get("/api/tickets/d-mine").status_code == 200


def test_another_teams_ticket_is_404_not_403(client, login_as, world):
    login_as("user", email="td-me@goodmit.co.kr")
    r = client.get("/api/tickets/d-theirs")
    assert r.status_code == 404, (
        f"남의 팀 티켓이 열린다({r.status_code}) — id 하나로 본문·댓글·첨부까지 나간다"
    )


def test_a_ticket_nobody_owns_stays_openable(client, login_as, world):
    """**미할당 트리아지에 보이는 티켓은 열려야 한다.** 목록에는 있는데 누르면 없다고 하면
    그건 보안이 아니라 고장이다."""
    login_as("user", email="td-me@goodmit.co.kr")
    listed = {t["id"] for t in client.get("/api/tickets/unassigned").json()["tickets"]}
    assert "d-ghost" in listed, "이 테스트의 전제(트리아지에 보인다)가 깨졌다"

    assert client.get("/api/tickets/d-ghost").status_code == 200, (
        "트리아지 목록에 보이는 티켓을 누르면 404 가 난다"
    )


def test_comments_follow_the_same_rule(client, login_as, world):
    login_as("user", email="td-me@goodmit.co.kr")
    assert client.get("/api/tickets/d-theirs/comments").status_code == 404


def test_a_global_admin_can_still_open_anything(client, login_as, world):
    login_as("system_admin")
    assert client.get("/api/tickets/d-theirs").status_code == 200


def test_write_paths_are_scoped_too(client, login_as, world):
    """**읽기만 막으면 소용없다** — API 를 직접 부르면 그만이다 (3순위 IDOR).

    `ensure_can_edit` 의 두 분기가 전 포탈로 열려 있었다:
      * `if not assignees: return` — **미할당이면 조직 무관하게 누구나** 수정·배정·휴지통 이동
      * `if user.role in MODERATOR_ROLES: return` — operator 이상은 전 포탈 티켓 편집

    앞의 것이 특히 넓다. 그리고 상세(GET)를 404 로 막아도 PATCH 는 그대로 통했다 —
    화면에서 가린 것이 API 에서 새는, H2 에서 이미 한 번 겪은 모양이다.
    """
    csrf = login_as("user", email="td-me@goodmit.co.kr")
    r = client.patch(
        "/api/tickets/d-theirs", json={"title": "몰래 수정"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 404, f"남의 팀 티켓이 수정된다: {r.status_code} {r.text[:120]}"


def test_you_can_still_edit_your_own_team_ticket(client, login_as, world):
    """범위를 걸면서 **할 수 있던 일을 뺏지 않는다** — 자기 팀 티켓은 그대로 고쳐진다."""
    csrf = login_as("user", email="td-me@goodmit.co.kr")
    r = client.patch(
        "/api/tickets/d-mine", json={"title": "우리팀 수정"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, f"자기 팀 티켓을 못 고친다: {r.status_code} {r.text[:160]}"
