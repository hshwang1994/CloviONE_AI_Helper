"""티켓 상세·댓글·첨부도 범위를 지킨다 (1순위 유출 #2).

`GET /api/tickets/{page_id}` 는 로그인만 하면 **id 하나로** 본문·댓글·첨부 원본 바이트까지
내줬다. 목록에서 가려 둔 것이 단건에서 새는 전형적인 IDOR 다.

## 403 이 아니라 404 다

`403` 은 "그 id 는 존재하지만 너는 못 본다" 를 알려 준다 — id 를 찍어 보며 403/404 를 세면
포탈 전체 티켓의 존재를 열거할 수 있다. 저장소 규칙(`core/scope.py` 모듈 docstring,
채팅 이미지 서빙, `get_scoped_user_or_404`)이 이미 404 로 못박아 놨다.

## 판정 축이 담당자에서 **프로젝트**로 바뀌었다 (0060)

예전에는 담당자의 부서로 판정했고, 담당자를 앱 사용자로 해석하지 못하는 티켓은
**그냥 통과시켰다**(운영 실측 21.5%가 그 상태였다) — 로그인한 누구나 그 티켓을 열고
편집할 수 있는, 이 앱의 가장 큰 우회 경로였다. 이제 티켓은 자기 프로젝트의 ACL 을
물려받으므로 그 예외가 필요 없고, 담당자 매핑 여부는 가시성과 무관하다.

## ⚠️ 목록에 보이는 티켓은 **반드시 열려야 한다**

미할당 트리아지에 뜬 티켓을 상세에서 404 로 막으면 **목록에는 보이는데 누르면 없다고 하는**
화면이 된다. 그건 보안이 아니라 고장이다. 이 결합을 아래 시험이 지킨다.
"""

from __future__ import annotations

import pytest

from tests.fakes.notion import DEFAULT_PROJECTS_DB, FakeNotionTasksDB, project_row, task_row

pytestmark = pytest.mark.security

NID_MINE, NID_THEIRS = "notion-d-mine", "notion-d-theirs"

# 외부 소스의 프로젝트 relation id. Portal 프로젝트가 이 id 로 이 외부 페이지와 짝지어진다.
EXT_OURS, EXT_THEIRS = "px-ours", "px-theirs"


@pytest.fixture()
def notion(fake_http) -> FakeNotionTasksDB:
    return FakeNotionTasksDB(
        rows=[
            task_row(page_id="d-mine", tid=1, title="우리팀 티켓", status="진행",
                     people=[NID_MINE], project_ids=[EXT_OURS]),
            task_row(page_id="d-theirs", tid=2, title="남의팀 티켓", status="진행",
                     people=[NID_THEIRS], project_ids=[EXT_THEIRS]),
            # 우리 프로젝트의 **진짜 미할당** 티켓 — 담당자가 아무도 없다. 트리아지에 뜨고,
            # 뜬 이상 열려야 한다.
            task_row(page_id="d-open", tid=3, title="우리팀 미할당", status="진행",
                     people=[], project_ids=[EXT_OURS]),
            # 담당자는 있는데 앱 계정으로 해석이 안 되는 티켓. 0060 부터 이건 **미할당이 아니라**
            # 정합성 문제(사용자 매핑 필요)이고, 소속은 프로젝트가 정하므로 정상적으로 보인다.
            task_row(page_id="d-unmapped", tid=4, title="매핑 안 된 담당자", status="진행",
                     people=["notion-x"], project_ids=[EXT_OURS]),
        ],
        projects=[project_row(page_id=EXT_OURS, name="우리 프로젝트"),
                  project_row(page_id=EXT_THEIRS, name="남의 프로젝트")],
        projects_db=DEFAULT_PROJECTS_DB,
    ).install(fake_http)


@pytest.fixture()
def world(client, settings, notion, make_user, make_project, db, app):
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department
    from app.tickets.sync import sync_tickets

    (settings.secrets_dir / "notion_report_token").write_text("t", encoding="utf-8")
    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.flush()
    # Portal 프로젝트를 **동기화 전에** 만든다 — 동기화가 그때 소속을 해석한다.
    make_project(name="우리 프로젝트", dept=mine, external_id=EXT_OURS)
    make_project(name="남의 프로젝트", dept=theirs, external_id=EXT_THEIRS)
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
    assert "d-open" in listed, "이 테스트의 전제(트리아지에 보인다)가 깨졌다"

    assert client.get("/api/tickets/d-open").status_code == 200, (
        "트리아지 목록에 보이는 티켓을 누르면 404 가 난다"
    )


def test_an_unmapped_assignee_no_longer_makes_a_ticket_public(client, login_as, world):
    """담당자를 앱 계정으로 해석하지 못해도 그것이 **가시성을 넓히지 않는다** (0060).

    예전에는 이런 티켓을 `ensure_in_scope` 가 무조건 통과시켰다 — 담당자 축으로는 소속을
    판정할 수 없으니 열어 두자는 것이었고, 그 결과 로그인한 누구나 그 티켓을 열 수 있었다.
    이제 소속은 프로젝트가 정하므로 같은 티켓이 **우리 팀에게는 보이고 남의 팀에게는 안 보인다.**
    """
    login_as("user", email="td-me@goodmit.co.kr")
    assert client.get("/api/tickets/d-unmapped").status_code == 200

    login_as("user", email="td-other@goodmit.co.kr")
    assert client.get("/api/tickets/d-unmapped").status_code == 404, (
        "담당자 매핑이 없다는 이유만으로 남의 팀 티켓이 열린다 — 예전의 우회 경로가 살아 있다"
    )


def test_an_unmapped_assignee_ticket_is_not_triage(client, login_as, world):
    """매핑 실패는 **배정 대기가 아니라 정합성 문제**다 — 트리아지 목록에 섞이면 안 된다."""
    login_as("user", email="td-me@goodmit.co.kr")
    listed = {t["id"] for t in client.get("/api/tickets/unassigned").json()["tickets"]}
    assert "d-unmapped" not in listed, (
        "담당자가 있는데 매핑만 안 된 티켓이 미할당으로 잡혔다 — 두 문제가 한 목록에 섞이면 "
        "어느 쪽도 처리되지 않는다"
    )


def test_comments_follow_the_same_rule(client, login_as, world):
    login_as("user", email="td-me@goodmit.co.kr")
    assert client.get("/api/tickets/d-theirs/comments").status_code == 404


def test_a_global_admin_can_still_open_anything(client, login_as, world):
    login_as("system_admin")
    assert client.get("/api/tickets/d-theirs").status_code == 200


def test_write_paths_are_scoped_too(client, login_as, world):
    """**읽기만 막으면 소용없다** — API 를 직접 부르면 그만이다 (3순위 IDOR).

    상세(GET)를 404 로 막아도 PATCH 는 그대로 통했다 — 화면에서 가린 것이 API 에서 새는,
    H2 에서 이미 한 번 겪은 모양이다.
    """
    csrf = login_as("user", email="td-me@goodmit.co.kr")
    r = client.patch(
        "/api/tickets/d-theirs", json={"title": "몰래 수정"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 404, f"남의 팀 티켓이 수정된다: {r.status_code} {r.text[:120]}"


def test_an_unassigned_ticket_in_another_teams_project_is_not_editable(client, login_as, world):
    """"미할당이면 누구나 편집" 예외가 **범위 안으로 좁혀졌는지** 확인한다.

    그 예외 자체는 남아 있다(주인 없는 일은 누가 잡아도 된다). 다만 그 '누구나' 는 이제
    "그 프로젝트를 볼 수 있는 사람" 이다 — 예전에는 전 포털이었다.
    """
    csrf = login_as("user", email="td-other@goodmit.co.kr")
    r = client.patch(
        "/api/tickets/d-open", json={"title": "남의 팀 미할당 가로채기"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 404, (
        f"다른 팀 프로젝트의 미할당 티켓이 편집된다: {r.status_code} {r.text[:120]}"
    )


def test_you_can_still_edit_your_own_team_ticket(client, login_as, world):
    """범위를 걸면서 **할 수 있던 일을 뺏지 않는다** — 자기 팀 티켓은 그대로 고쳐진다."""
    csrf = login_as("user", email="td-me@goodmit.co.kr")
    r = client.patch(
        "/api/tickets/d-mine", json={"title": "우리팀 수정"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, f"자기 팀 티켓을 못 고친다: {r.status_code} {r.text[:160]}"


# RBAC 재감사(2026-08-16)로 발견: 범위 판정이 org 범위(admin_scope="org") 관리자를 global 과
# 똑같이 취급했다 — 위 시험들이 지키는 dept 경계와 별개로 이 org 경계는 어떤 시험도 없었다.
# 상세(읽기)뿐 아니라 PATCH(쓰기)도 같은 함수를 지나므로 함께 확인한다.
@pytest.fixture()
def org_notion(fake_http) -> FakeNotionTasksDB:
    return FakeNotionTasksDB(
        rows=[
            task_row(page_id="od-mine", tid=11, title="A조직 티켓", status="진행",
                     people=["notion-od-mine"], project_ids=["px-org-a"]),
            task_row(page_id="od-theirs", tid=12, title="B조직 티켓", status="진행",
                     people=["notion-od-theirs"], project_ids=["px-org-b"]),
        ],
        projects=[project_row(page_id="px-org-a", name="A조직 프로젝트"),
                  project_row(page_id="px-org-b", name="B조직 프로젝트")],
        projects_db=DEFAULT_PROJECTS_DB,
    ).install(fake_http)


@pytest.fixture()
def org_world(client, settings, org_notion, make_user, make_project, db, app):
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Organization
    from app.tickets.sync import sync_tickets
    from app.users.models import MEMBERSHIP_ORGANIZATION

    (settings.secrets_dir / "notion_report_token").write_text("t", encoding="utf-8")
    other_org = Organization(slug="ticket-org-scope-tenant", name="다른 회사", status="active")
    db.add(other_org)
    db.flush()
    make_project(name="A조직 프로젝트", org_id=DEFAULT_ORG_ID, external_id="px-org-a")
    make_project(name="B조직 프로젝트", org_id=other_org.id, external_id="px-org-b")

    boss = make_user("odt-boss@goodmit.co.kr", role="admin", display_name="A조직관리자")
    boss.org_id = DEFAULT_ORG_ID
    boss.admin_scope = "org"
    boss.scope_org_id = DEFAULT_ORG_ID
    mine = make_user("odt-mine@goodmit.co.kr", role="user", display_name="A조직원")
    mine.org_id = DEFAULT_ORG_ID
    mine.membership_kind = MEMBERSHIP_ORGANIZATION
    theirs = make_user("odt-theirs@goodmit.co.kr", role="user", display_name="B조직원")
    theirs.org_id = other_org.id
    theirs.membership_kind = MEMBERSHIP_ORGANIZATION
    db.add(UserNotionMapping(user_id=mine.id, notion_user_id="notion-od-mine", status=STATUS_VERIFIED))
    db.add(UserNotionMapping(user_id=theirs.id, notion_user_id="notion-od-theirs", status=STATUS_VERIFIED))
    db.commit()
    with app.state.session_factory() as s:
        sync_tickets(s, outbound=app.state.outbound_client, settings=settings,
                     now=app.state.clock.now())
        s.commit()


def test_org_scoped_admin_does_not_see_another_organizations_ticket(client, login_as, org_world):
    login_as("admin", email="odt-boss@goodmit.co.kr")
    ids = {t["id"] for t in client.get("/api/tickets/team").json()["tickets"]}
    assert "od-mine" in ids
    assert "od-theirs" not in ids, "org 범위 관리자에게 다른 조직 티켓이 목록에 그대로 보인다"


def test_org_scoped_admin_gets_404_for_another_organizations_ticket(client, login_as, org_world):
    login_as("admin", email="odt-boss@goodmit.co.kr")
    assert client.get("/api/tickets/od-mine").status_code == 200
    assert client.get("/api/tickets/od-theirs").status_code == 404, \
        "목록에서 가린 다른 조직 티켓이 id 하나로 열린다"


def test_org_scoped_admin_cannot_edit_another_organizations_ticket(client, login_as, org_world):
    csrf = login_as("admin", email="odt-boss@goodmit.co.kr")
    r = client.patch(
        "/api/tickets/od-theirs", json={"title": "몰래 수정"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 404, f"org 범위 관리자가 다른 조직 티켓을 수정할 수 있다: {r.status_code} {r.text[:160]}"
