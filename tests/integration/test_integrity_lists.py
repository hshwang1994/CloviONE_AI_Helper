"""조직 정합성 — 목록과 일괄 작업 (계획 3.2, D-508).

예전 화면은 검사 아홉 개를 50건 표본씩 한 응답에 실었다. 51번째 행부터는 볼 길이 없었고, 고칠
수 있는 것은 소속 미지정 사용자뿐이었다. 여기서 못박는 것:

  * 목록은 **전량**이다. 요약의 건수와 목록의 `total` 이 같고, 검색과 페이지가 선다.
  * 일괄 작업은 **원래 수정 함수**를 부르고 그 함수의 감사 행을 그대로 남긴다.
  * 한 항목이 거절돼도 나머지는 반영되고, 거절된 항목은 사유와 함께 돌아온다.
  * 고치기는 전역 관리자만 한다(운영자 403, 부서 범위 관리자 403). 읽기는 감사자도 한다.
  * 원인 차단: 비활성 부서로 프로젝트를 옮길 수 없고, 소유 없는 공간을 새로 만들 수 없다.

반례를 같은 파일에 둔다: 정상 행은 목록에 없고, 목록 밖 id 는 바뀌지 않는다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.audit.models import AuditLog
from app.core.models_base import join_names
from app.knowledge.models import KnowledgeSpace
from app.org.constants import DEFAULT_ORG_ID
from app.org.models import Department
from app.projects.models import Project
from app.tickets.models import PROJECT_LINK_MISSING, PROJECT_LINK_OK, Ticket
from app.users.models import ADMIN_SCOPE_DEPT, MEMBERSHIP_UNASSIGNED, User
from app.work import codes as work_codes
from app.work.models import Sprint

pytestmark = pytest.mark.integration

TODAY = date(2026, 9, 30)


def _hdr(csrf):
    return {"X-CSRF-Token": csrf}


def _fix(client, csrf, key, **body):
    return client.post(f"/api/admin/integrity/checks/{key}/fix", json=body, headers=_hdr(csrf))


def _list(client, key, **params):
    r = client.get(f"/api/admin/integrity/checks/{key}", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _count(client, key):
    report = client.get("/api/admin/integrity").json()
    return next(f for f in report["findings"] if f["key"] == key)["count"]


@pytest.fixture()
def teams(db):
    live = Department(name="정합성 활성팀", org_id=DEFAULT_ORG_ID, active=True)
    other = Department(name="정합성 다른팀", org_id=DEFAULT_ORG_ID, active=True)
    dead = Department(name="정합성 정리된팀", org_id=DEFAULT_ORG_ID, active=False)
    db.add_all([live, other, dead])
    db.commit()
    return {"live": live, "other": other, "dead": dead}


def _project(db, name, dept=None):
    row = work_codes.insert_with_code(
        db, Project(name=name, org_id=DEFAULT_ORG_ID, dept_id=getattr(dept, "id", None))
    )
    db.flush()
    return row


def _ticket(db, n, *, project=None, sprint=None, title=None):
    row = Ticket(
        title=title or f"정합성 티켓 {n}", notion_page_id=f"integ-list-{n}",
        project_uid=getattr(project, "id", None),
        project_link=PROJECT_LINK_OK if project is not None else PROJECT_LINK_MISSING,
        status="진행", org_id=DEFAULT_ORG_ID, source="notion", notion_ticket_number=n,
        # 채번은 프로젝트가 있을 때만이다(DB 트리거 `tickets_set_canonical_key`).
        seq=n if project is not None else None,
        sprint_id=getattr(sprint, "id", None),
    )
    db.add(row)
    db.flush()
    return row


def _sprint(db, name, team, state="active"):
    row = Sprint(
        name=name, department_id=getattr(team, "id", None), org_id=DEFAULT_ORG_ID,
        starts_on=TODAY - timedelta(days=3), ends_on=TODAY + timedelta(days=4), state=state,
    )
    db.add(row)
    db.flush()
    return row


# ── 목록은 전량이다 ───────────────────────────────────────────────────────────


def test_the_list_is_complete_searchable_and_paged(client, login_as, db):
    for n in range(1, 61):
        _ticket(db, n, title=f"프로젝트 없는 일 {n:02d}")
    _ticket(db, 99, title="찾을 수 있는 특이한 제목")
    db.commit()
    login_as("system_admin")

    assert _count(client, "tickets_without_one_project") == 61
    first = _list(client, "tickets_without_one_project", page=1, page_size=50)
    second = _list(client, "tickets_without_one_project", page=2, page_size=50)
    assert first["total"] == 61 and len(first["items"]) == 50
    assert len(second["items"]) == 11, "51번째 행부터 볼 길이 없다"
    assert not ({i["id"] for i in first["items"]} & {i["id"] for i in second["items"]})

    found = _list(client, "tickets_without_one_project", q="특이한")
    assert found["total"] == 1 and found["items"][0]["title"] == "찾을 수 있는 특이한 제목"
    ordered = _list(client, "tickets_without_one_project", sort="title", order="asc", page_size=3)
    assert [i["title"] for i in ordered["items"]] == [
        "찾을 수 있는 특이한 제목", "프로젝트 없는 일 01", "프로젝트 없는 일 02",
    ]
    assert first["items"][0]["link"].startswith("#/tickets/")
    assert "_search" not in first["items"][0], "내부 검색 키가 응답에 샜다"


def test_an_unknown_check_is_404(client, login_as):
    login_as("system_admin")
    assert client.get("/api/admin/integrity/checks/nope").status_code == 404


def test_trashed_and_vanished_tickets_are_not_counted(client, login_as, db):
    from app.trash.models import TRASH_TICKET, TrashItem

    trashed = _ticket(db, 1, title="휴지통에 넣은 일")
    vanished = _ticket(db, 2, title="옛 소스에서 사라진 일")
    live = _ticket(db, 3, title="남은 일")
    vanished.notion_missing_at = datetime(2026, 9, 1)
    db.add(TrashItem(
        item_type=TRASH_TICKET, notion_page_id=trashed.notion_page_id, title=trashed.title,
        deleted_by_user_id="00000000-0000-0000-0000-000000000000", deleted_at=datetime(2026, 9, 29),
    ))
    db.commit()
    login_as("system_admin")
    titles = {i["title"] for i in _list(client, "tickets_without_one_project")["items"]}
    assert titles == {live.title}, titles


# ── 일괄 작업 — 원래 수정 함수를 부른다 ───────────────────────────────────────


def test_setting_a_project_fixes_the_ticket_and_audits_like_the_ticket_screen(client, login_as, db):
    target = _project(db, "옮겨 갈 프로젝트")
    lost = _ticket(db, 1)
    stray = _ticket(db, 2, project=target, title="이미 정상")
    db.commit()
    csrf = login_as("system_admin")

    r = _fix(client, csrf, "tickets_without_one_project", fix="ticket_project",
             ids=[lost.notion_page_id, stray.notion_page_id], project_id=target.id)
    assert r.status_code == 200, r.text
    assert r.json()["changed"] == 1
    assert [s["id"] for s in r.json()["skipped"]] == [stray.notion_page_id], "목록 밖 id 를 바꿨다"
    assert _count(client, "tickets_without_one_project") == 0
    db.expire_all()
    assert db.get(Ticket, lost.id).project_uid == target.id
    actions = [a.action for a in db.query(AuditLog).filter(AuditLog.object_id == lost.notion_page_id)]
    assert "ticket.update" in actions, "티켓 편집과 같은 감사 행이 없다"
    summary = db.query(AuditLog).filter(AuditLog.action == "integrity.fix").one()
    assert summary.object_id == "tickets_without_one_project"


def test_removing_off_team_tickets_from_an_open_sprint(client, login_as, db, teams):
    mine = _project(db, "활성팀 프로젝트", teams["live"])
    theirs = _project(db, "다른팀 프로젝트", teams["other"])
    sprint = _sprint(db, "활성팀 회차", teams["live"])
    ok = _ticket(db, 1, project=mine, sprint=sprint)
    off = _ticket(db, 2, project=theirs, sprint=sprint)
    db.commit()
    csrf = login_as("system_admin")

    listed = _list(client, "open_sprint_tickets_off_team")
    assert [i["id"] for i in listed["items"]] == [off.notion_page_id]
    r = _fix(client, csrf, "open_sprint_tickets_off_team", fix="remove_from_sprint",
             ids=[off.notion_page_id])
    assert r.status_code == 200 and r.json()["changed"] == 1, r.text
    db.expire_all()
    assert db.get(Ticket, off.id).sprint_id is None
    assert db.get(Ticket, ok.id).sprint_id == sprint.id, "같은 팀 티켓까지 뺐다"
    assert _count(client, "open_sprint_tickets_off_team") == 0


def test_assigning_a_team_to_an_open_sprint(client, login_as, db, teams):
    open_row = _sprint(db, "팀 미정 열린 회차", None, "planned")
    closed_row = _sprint(db, "팀 미정 닫힌 회차", None, "closed")
    db.commit()
    csrf = login_as("system_admin")

    report = client.get("/api/admin/integrity").json()
    assert report["notes"]["closed_sprints_without_team"] == 1
    r = _fix(client, csrf, "sprints_without_team", fix="sprint_team",
             ids=[open_row.id, closed_row.id], department_id=teams["live"].id)
    assert r.status_code == 200, r.text
    assert r.json()["changed"] == 1
    assert r.json()["skipped"][0]["id"] == closed_row.id, "닫힌 회차는 목록에 없어야 한다"
    db.expire_all()
    assert db.get(Sprint, open_row.id).department_id == teams["live"].id
    assert db.get(Sprint, closed_row.id).department_id is None
    assert db.query(AuditLog).filter(AuditLog.action == "sprint.update",
                                     AuditLog.object_id == open_row.id).count() == 1


def test_space_ownership_goes_to_an_active_department_or_the_organization(client, login_as, db, teams):
    unset = KnowledgeSpace(org_id=DEFAULT_ORG_ID, name="소유 없는 공간", slug="integ-unset",
                           owner_kind="unset")
    on_dead = KnowledgeSpace(org_id=DEFAULT_ORG_ID, name="정리된 부서 공간", slug="integ-dead",
                             owner_kind="department", owner_dept_id=teams["dead"].id)
    db.add_all([unset, on_dead])
    db.commit()
    csrf = login_as("system_admin")

    refused = _fix(client, csrf, "spaces_without_ownership", fix="space_owner",
                   ids=[unset.id], department_id=teams["dead"].id)
    assert refused.status_code == 422, "비활성 부서를 새 소유로 받았다"
    r = _fix(client, csrf, "spaces_without_ownership", fix="space_owner",
             ids=[unset.id], department_id=teams["live"].id)
    assert r.status_code == 200 and r.json()["changed"] == 1, r.text
    r = _fix(client, csrf, "spaces_on_inactive_department", fix="space_owner",
             ids=[on_dead.id], organization_direct=True)
    assert r.status_code == 200 and r.json()["changed"] == 1, r.text
    db.expire_all()
    assert (db.get(KnowledgeSpace, unset.id).owner_kind, db.get(KnowledgeSpace, unset.id).owner_dept_id) \
        == ("department", teams["live"].id)
    assert db.get(KnowledgeSpace, on_dead.id).owner_kind == "organization"
    assert db.get(KnowledgeSpace, on_dead.id).owner_dept_id is None
    assert _count(client, "spaces_without_ownership") == 0
    assert _count(client, "spaces_on_inactive_department") == 0


def test_moving_projects_off_an_inactive_department_skips_the_one_held_by_a_sprint(
    client, login_as, db, teams
):
    free = _project(db, "옮길 수 있는 프로젝트", teams["dead"])
    held = _project(db, "회차에 묶인 프로젝트", teams["dead"])
    sprint = _sprint(db, "다른팀 열린 회차", teams["other"])
    _ticket(db, 1, project=held, sprint=sprint)
    db.commit()
    csrf = login_as("system_admin")

    r = _fix(client, csrf, "projects_on_inactive_department", fix="project_department",
             ids=[free.id, held.id], department_id=teams["live"].id)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["changed"] == 1
    assert [s["id"] for s in body["skipped"]] == [held.id]
    assert "회차" in body["skipped"][0]["reason"], "거절 사유를 그대로 돌려주지 않았다"
    db.expire_all()
    assert db.get(Project, free.id).dept_id == teams["live"].id
    assert db.get(Project, held.id).dept_id == teams["dead"].id, "거절된 항목이 반쯤 바뀌었다"
    assert db.query(AuditLog).filter(AuditLog.action == "project.update",
                                     AuditLog.object_id == free.id).count() == 1


def test_people_on_an_inactive_department_can_be_moved(client, login_as, db, teams, make_user):
    stranded = make_user(email="stranded@goodmit.co.kr", display_name="정리된팀 사람")
    stranded.department_id = teams["dead"].id
    stranded.membership_kind = "department"
    unassigned = make_user(email="nobody@goodmit.co.kr", display_name="미지정",
                           membership=MEMBERSHIP_UNASSIGNED)
    db.commit()
    csrf = login_as("system_admin")

    assert _count(client, "users_on_inactive_department") == 1
    r = _fix(client, csrf, "users_on_inactive_department", fix="membership",
             ids=[stranded.id, unassigned.id], department_id=teams["live"].id)
    assert r.status_code == 200 and r.json()["changed"] == 2, r.text
    db.expire_all()
    assert db.get(User, stranded.id).department_id == teams["live"].id
    assert _count(client, "users_on_inactive_department") == 0


def test_a_fix_that_the_check_does_not_offer_is_refused(client, login_as, db):
    _ticket(db, 1)
    db.commit()
    csrf = login_as("system_admin")
    r = _fix(client, csrf, "tickets_with_unmapped_assignees", fix="ticket_project",
             ids=["x"], project_id="y")
    assert r.status_code == 422, r.text
    r = _fix(client, csrf, "tickets_without_one_project", fix="ticket_project", ids=["x"])
    assert r.status_code == 422, "옮길 프로젝트 없이 받았다"


def test_inactive_people_and_archived_projects_are_not_counted(client, login_as, db, teams, make_user):
    from app.core.models_base import utcnow

    closed = make_user(email="closed@goodmit.co.kr", display_name="닫힌 계정", active=False)
    closed.department_id = teams["dead"].id
    gone = _project(db, "보관된 프로젝트", teams["dead"])
    gone.archived_at = utcnow()
    db.commit()
    login_as("system_admin")
    assert _count(client, "users_on_inactive_department") == 0
    assert _count(client, "projects_on_inactive_department") == 0


# ── 권한 ──────────────────────────────────────────────────────────────────────


def test_only_a_global_admin_can_fix(client, login_as, db, teams, make_user):
    lost = _ticket(db, 1)
    target = _project(db, "대상 프로젝트")
    db.commit()

    csrf = login_as("operator")
    r = _fix(client, csrf, "tickets_without_one_project", fix="ticket_project",
             ids=[lost.notion_page_id], project_id=target.id)
    assert r.status_code == 403, r.text

    scoped = make_user(email="scoped-admin@goodmit.co.kr", role="admin", display_name="부서 관리자")
    scoped.department_id = teams["live"].id
    scoped.membership_kind = "department"
    scoped.admin_scope = ADMIN_SCOPE_DEPT
    scoped.scope_dept_id = teams["live"].id
    db.commit()
    csrf = login_as("admin", email="scoped-admin@goodmit.co.kr")
    r = _fix(client, csrf, "tickets_without_one_project", fix="ticket_project",
             ids=[lost.notion_page_id], project_id=target.id)
    assert r.status_code == 403, r.text
    db.expire_all()
    assert db.get(Ticket, lost.id).project_uid is None


def test_an_auditor_can_read_the_lists(client, login_as, db):
    _ticket(db, 1)
    db.commit()
    login_as("auditor")
    assert _list(client, "tickets_without_one_project")["total"] == 1
    assert client.get("/api/admin/integrity/admins").status_code == 200


def test_a_plain_user_cannot_read(client, login_as):
    login_as("user")
    assert client.get("/api/admin/integrity/checks/tickets_without_one_project").status_code == 403


# ── 원인 차단 ─────────────────────────────────────────────────────────────────


def test_a_project_cannot_be_moved_into_an_inactive_department(client, login_as, db, teams):
    row = _project(db, "편집할 프로젝트", teams["live"])
    stays = _project(db, "이미 정리된 부서 프로젝트", teams["dead"])
    db.commit()
    csrf = login_as("system_admin")
    r = client.patch(f"/api/projects/{row.id}", json={"dept_id": teams["dead"].id}, headers=_hdr(csrf))
    assert r.status_code == 422, r.text
    # 이미 그 부서에 있는 프로젝트는 다른 칸을 고칠 수 있다(같은 부서 id 를 다시 보내도 된다).
    r = client.patch(f"/api/projects/{stays.id}", json={"dept_id": teams["dead"].id, "goal": "목표"},
                     headers=_hdr(csrf))
    assert r.status_code == 200, r.text


def test_a_new_space_needs_an_owner(client, login_as):
    csrf = login_as("system_admin")
    r = client.post("/api/knowledge/spaces", json={
        "name": "소유 없는 새 공간", "slug": "integ-new-unset", "owner_kind": "unset",
    }, headers=_hdr(csrf))
    assert r.status_code == 422, r.text


def test_closing_an_account_reports_the_open_work_it_still_holds(client, login_as, db, make_user):
    holder = make_user(email="leaving@goodmit.co.kr", display_name="떠나는 사람")
    project = _project(db, "남은 일 프로젝트")
    open_row = _ticket(db, 1, project=project)
    done_row = _ticket(db, 2, project=project)
    open_row.assignee_notion_ids = join_names([holder.id])
    done_row.assignee_notion_ids = join_names([holder.id])
    done_row.status = "완료"
    db.commit()
    csrf = login_as("system_admin")
    r = client.post(f"/api/admin/users/{holder.id}/disable", headers=_hdr(csrf))
    assert r.status_code == 200, r.text
    assert r.json()["open_ticket_count"] == 1, "끝난 일까지 세거나 남은 일을 못 셌다"
