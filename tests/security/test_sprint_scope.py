"""스프린트 회의도 **범위를 지킨다** — 문이 둘이다 (D-194 · 지시 4).

## 이 파일이 바뀐 이유

예전 이 파일은 `GET /api/sprint/summary` 를 봤다. 그 API 는 「그 주에 마감인 티켓 묶음」을
스프린트라고 불렀고, 담당자별 생산성을 포탈 전체로 돌려주던 자리였다(1순위 유출 #3).
지시 4 회차에서 그 API 를 걷고 회차를 아는 화면으로 갈아탔다 — 이 제품에는 이제
`sprints` 표가 있고, 「스프린트」에 뜻이 둘이면 두 화면이 같은 말로 다른 것을 센다.

그 API 가 없어졌다고 이 파일이 없어지지는 않는다. **지키던 성질을 새 문에 다시 건다.**

## 문이 둘인 것이 요점이다

회차가 보이는가와 그 안의 티켓이 보이는가는 **다른 질문**이다.

  1. 회차 자체 — `get_scoped_sprint_or_404`. 안 보이는 회차는 404 다(403 이 아니다:
     존재를 알리면 id 를 찍어 남의 팀 회차 목록을 열거할 수 있다).
  2. 회차 안의 티켓 — 팀 전체 회차(`project_id IS NULL`)는 조직 안에서 열려 있는데,
     거기 담긴 티켓은 여러 프로젝트에 걸린다. 회차 문만 지나고 `WHERE sprint_id = ?` 로
     읽으면 그중 내가 못 보는 프로젝트의 제목·담당자·마감이 회의 화면에 그대로 실린다.

두 번째가 이 파일의 핵심 단정이다 — 첫 번째만 걸어 두고 통과했다고 믿기 쉬운 자리다.

## 양쪽을 함께 본다

「안 보인다」만 확인하면 **전부 안 보이는 구현**도 통과한다. 그래서 각 단정에 「우리 팀
것은 보인다」를 함께 둔다.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest

from app.org.constants import DEFAULT_ORG_ID
from app.org.models import Department
from app.projects.models import Project
from app.tickets.models import PROJECT_LINK_OK, Ticket
from app.work import codes as work_codes
from app.work.models import Sprint

pytestmark = pytest.mark.security

BOSS = "sprint-scope-boss@goodmit.co.kr"
TODAY = date(2026, 8, 27)


@pytest.fixture()
def world(db, make_user):
    """부서 둘 + 각 팀 프로젝트 + **팀 전체 회차 하나에 양쪽 티켓이 담긴** 상태.

    양쪽을 한 회차에 담는 것이 이 픽스처의 요점이다. 프로젝트별 회차만 만들면 첫 번째
    문(회차 가시성)이 두 번째 문을 가려 버려서, 티켓 절이 빠져 있어도 시험이 통과한다.
    """
    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.commit()

    boss = make_user(BOSS, role="admin", display_name="팀관리자")
    boss.department_id = mine.id
    boss.admin_scope = "dept"
    boss.scope_dept_id = mine.id
    db.commit()

    def project(name, dept, page):
        # 코드는 제품의 생성기가 짓는다(D-282). 시험이 읽기 좋은 값을 고르면 그 문자열은
        # `ck_projects_code_shape` 가 INSERT 를 거절할 때까지 안 보이게 갈라진다.
        return work_codes.insert_with_code(
            db,
            Project(name=name, org_id=DEFAULT_ORG_ID, dept_id=dept.id, notion_page_id=page),
        )

    ours = project("우리 프로젝트", mine, "sp-proj-ours")
    yours = project("남의 프로젝트", theirs, "sp-proj-theirs")

    # 팀 전체 회차 — `project_id` 가 없다. 조직 안에서 **누구에게나 보인다.**
    open_sprint = Sprint(
        name="전사 8월 회차", project_id=None, org_id=DEFAULT_ORG_ID,
        starts_on=TODAY - timedelta(days=3), ends_on=TODAY + timedelta(days=4),
        state="active",
    )
    # 남의 팀 프로젝트에 묶인 회차 — 이 사람에게는 **없는 것**이어야 한다.
    theirs_sprint = Sprint(
        name="남의팀 8월 회차", project_id=yours.id, org_id=DEFAULT_ORG_ID,
        starts_on=TODAY - timedelta(days=3), ends_on=TODAY + timedelta(days=4),
        state="planned",
    )
    db.add_all([open_sprint, theirs_sprint])
    db.flush()

    def ticket(page_id, proj, number, title, sprint):
        row = Ticket(
            title=title, notion_page_id=page_id, project_uid=proj.id,
            project_link=PROJECT_LINK_OK, status="진행", org_id=DEFAULT_ORG_ID,
            source="notion", notion_ticket_number=number, seq=number,
            sprint_id=sprint.id, est_wd=2.0, due_date=TODAY + timedelta(days=1),
        )
        db.add(row)
        db.flush()
        db.refresh(row)
        return row

    ours_ticket = ticket("sp-page-ours", ours, 31, "우리팀 일", open_sprint)
    theirs_ticket = ticket("sp-page-theirs", yours, 32, "남의팀 일", open_sprint)
    db.commit()
    return {
        "boss": boss, "ours": ours, "yours": yours,
        "open_sprint": open_sprint, "theirs_sprint": theirs_sprint,
        "ours_ticket": ours_ticket, "theirs_ticket": theirs_ticket,
    }


def _hdr(login_as):
    return {"X-CSRF-Token": login_as("admin", email=BOSS)}


def _meeting(client, login_as, sprint_id):
    return client.get(f"/api/work/sprints/{sprint_id}/meeting", headers=_hdr(login_as))


def test_a_sprint_outside_my_scope_is_not_found(client, login_as, world):
    """403 이 아니라 404 다. 존재를 알리면 id 를 찍어 남의 팀 회차를 열거할 수 있다."""
    res = _meeting(client, login_as, world["theirs_sprint"].id)
    assert res.status_code == 404, res.text


def test_a_shared_sprint_still_hides_tickets_i_cannot_see(client, login_as, world):
    """🔴 **문이 둘이다.** 회차가 보인다고 그 안의 티켓이 다 보이는 것은 아니다.

    이 단정이 없으면 「회차 게이트만 지나고 `WHERE sprint_id = ?` 로 읽는」 구현이 통과한다.
    그 구현에서는 팀 전체 회차 하나가 남의 팀 프로젝트 전체의 제목·담당자·마감을 실어 나른다.
    """
    body = _meeting(client, login_as, world["open_sprint"].id).json()
    titles = {
        row["title"]
        for bucket in body["discuss"].values()
        for row in bucket["items"]
    }
    assert "우리팀 일" in titles, f"우리 팀 티켓이 안 보인다 — 검사가 헛돈다: {titles}"
    assert "남의팀 일" not in titles, f"남의 팀 티켓 제목이 회의 화면에 실렸다: {titles}"


def test_the_summary_counts_only_what_i_can_see(client, login_as, world):
    """제목을 가리고 **숫자만** 남겨도 유출이다.

    「이 회차에 티켓이 몇이고 남은 공수가 얼마인가」는 그 팀의 상태를 그대로 말한다 —
    `sprint_scope` 가 같은 판단을 이미 적어 뒀다.
    """
    body = _meeting(client, login_as, world["open_sprint"].id).json()
    assert body["summary"]["total"] == 1, body["summary"]
    assert body["summary"]["remaining_wd"] == 2.0, body["summary"]


def test_the_candidates_stay_inside_my_scope(client, login_as, world, db):
    """후보 목록은 백로그를 그대로 읽는다 — 그쪽 범위 절을 우회하지 않는다."""
    stray = Ticket(
        title="남의팀 백로그", notion_page_id="sp-page-backlog", project_uid=world["yours"].id,
        project_link=PROJECT_LINK_OK, status="계획", org_id=DEFAULT_ORG_ID,
        source="notion", notion_ticket_number=33, seq=33,
    )
    mine = Ticket(
        title="우리팀 백로그", notion_page_id="sp-page-backlog-ours", project_uid=world["ours"].id,
        project_link=PROJECT_LINK_OK, status="계획", org_id=DEFAULT_ORG_ID,
        source="notion", notion_ticket_number=34, seq=34,
    )
    db.add_all([stray, mine])
    db.commit()
    body = _meeting(client, login_as, world["open_sprint"].id).json()
    titles = {c["title"] for c in body["candidates"]}
    assert "우리팀 백로그" in titles, f"우리 팀 후보가 없다 — 검사가 헛돈다: {titles}"
    assert "남의팀 백로그" not in titles, f"남의 팀 백로그가 후보로 나왔다: {titles}"


def test_a_global_admin_sees_both(client, login_as, world):
    """반례 — 좁히기가 **전부 안 보이는 구현**이 아님을 확인한다."""
    body = client.get(
        f"/api/work/sprints/{world['open_sprint'].id}/meeting",
        headers={"X-CSRF-Token": login_as("system_admin")},
    ).json()
    assert body["summary"]["total"] == 2, body["summary"]


def _join_sprint_activity(db, ticket, sprint, *, hours=0):
    """회차 시작 **뒤에** 이 티켓이 회차로 들어온 기록 한 줄.

    픽스처에 넣지 않고 시험 안에서 심는다 — 픽스처에 넣으면 `scope.tracked` 가 파일
    전체에서 참이 되어 다른 시험의 전제가 바뀐다.
    """
    from app.work import activity as work_activity
    from app.work.models import ACT_SPRINT

    stamp = datetime.combine(sprint.starts_on + timedelta(days=1), time(10 + hours, 0))
    work_activity.record(
        db, ticket_id=ticket.id, kind=ACT_SPRINT, field="sprint_id",
        from_value=None, to_value=sprint.id, now=stamp,
    )


def test_scope_changes_hide_tickets_i_cannot_see(client, login_as, world, db):
    """🔴 범위 변경 갈래도 **같은 문**을 지난다.

    이 갈래는 활동 기록에서 티켓을 다시 읽는다 — 그 읽기가 가시성 절을 안 지나면
    팀 전체 회차를 드나든 남의 팀 티켓의 제목·담당자·마감이 이 갈래로만 샌다. 위
    `test_a_shared_sprint_still_hides_...` 는 픽스처에 sprint 활동이 없어 이 경로에
    닿지 못했다(조기 반환) — 그래서 여기서 활동을 심어 경로를 연다.
    """
    _join_sprint_activity(db, world["ours_ticket"], world["open_sprint"])
    _join_sprint_activity(db, world["theirs_ticket"], world["open_sprint"], hours=1)
    db.commit()

    body = _meeting(client, login_as, world["open_sprint"].id).json()
    titles = {row["title"] for row in body["discuss"]["scope_changes"]["items"]}
    assert "우리팀 일" in titles, f"우리 팀 변경이 안 보인다 — 검사가 헛돈다: {titles}"
    assert "남의팀 일" not in titles, f"남의 팀 티켓이 범위 변경 갈래로 샜다: {titles}"
    # 제목을 가려도 숫자는 유출이다 — 셈도 보이는 티켓만 센다.
    assert body["scope"]["added"] == 1, body["scope"]


def test_a_global_admin_sees_scope_changes_for_both(client, login_as, world, db):
    """반례 — 좁히기가 **전부 숨기는 구현**이 아님을 확인한다."""
    _join_sprint_activity(db, world["ours_ticket"], world["open_sprint"])
    _join_sprint_activity(db, world["theirs_ticket"], world["open_sprint"], hours=1)
    db.commit()

    body = client.get(
        f"/api/work/sprints/{world['open_sprint'].id}/meeting",
        headers={"X-CSRF-Token": login_as("system_admin")},
    ).json()
    titles = {row["title"] for row in body["discuss"]["scope_changes"]["items"]}
    assert {"우리팀 일", "남의팀 일"} <= titles, titles
    assert body["scope"]["added"] == 2, body["scope"]


def test_a_note_on_a_sprint_i_cannot_see_is_not_found(client, login_as, world):
    """쓰기도 같은 문을 지난다. 목록만 좁히고 쓰기를 열어 두면 좁힌 의미가 없다."""
    res = client.post(
        f"/api/work/sprints/{world['theirs_sprint'].id}/decisions",
        json={"kind": "decision", "body": "남의 회의에 적기"},
        headers=_hdr(login_as),
    )
    assert res.status_code == 404, res.text


def test_a_note_on_a_visible_sprint_persists_across_requests(client, login_as, world):
    """🔴 반례이자 **커밋 경로 시험**이다.

    막는 쪽만 보면 「전부 404 인 구현」도 통과한다. 그리고 서비스가 `flush` 까지만 하므로
    (커밋은 `get_db` 가 요청 끝에 한다) 실제로 남는지는 **다음 요청**에서만 확인된다 —
    같은 세션 안에서 되읽는 유닛 시험으로는 이 성질이 안 보인다.
    """
    posted = client.post(
        f"/api/work/sprints/{world['open_sprint'].id}/decisions",
        json={"kind": "action", "body": "다음 회의 전에 담당 팀을 정합니다."},
        headers=_hdr(login_as),
    )
    assert posted.status_code == 200, posted.text

    again = _meeting(client, login_as, world["open_sprint"].id).json()
    assert [d["body"] for d in again["decisions"]] == ["다음 회의 전에 담당 팀을 정합니다."]
    assert again["decisions"][0]["kind"] == "action"
