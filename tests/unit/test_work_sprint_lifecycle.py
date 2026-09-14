"""회차 상태 기계 — planned ↔ active → closed, 그리고 closed 는 종착이다. **축은 팀이다.**

qa-contract-change: 회차의 소유자가 프로젝트에서 팀(`sprints.department_id`, D-482)으로 바뀌었다. 「다른 프로젝트의 회차로는 이월 불가·팀 전체 회차는 언제나 받는다」던 단정이 「같은 팀의 열린 회차로만 이월, 대상이 없으면 백로그」로, 「한 프로젝트에 활성 하나」가 「한 팀에 활성 하나(팀이 다르면 나란히)」로, 「닫힌 회차의 이름·목표 수정 허용」이 「이름만」으로 바뀌었고, 편성 권한(관리 범위 403)과 팀 미정 회차 규칙이 새로 붙었다. 단언은 줄지 않고 늘었다.

## 이 파일이 지키는 것

회차를 닫는 것은 되돌릴 수 없는 동작이고(이월이 실제로 티켓을 옮긴다), 그래서 전이가
아무 데서나 일어나면 안 된다. 이 파일이 못박는 규칙:

  * 닫기는 `/close` 한 곳이다 — `/state` 로는 closed 를 만들 수 없다.
  * planned 는 닫을 수 없다(연 적이 없는 회차에는 이월할 것이 없다 — 잘못 만든
    회차는 삭제가 답이다).
  * closed 는 다시 닫을 수 없고(이월이 한 번 더 돌면 「N건 옮김」이 거짓이 된다), 다시
    열 수도 없다(번다운·활동 기록이 이미 닫힌 시점 기준으로 서 있다).
  * 이월 대상은 자기 자신·닫힌 회차·**다른 팀의 회차**가 될 수 없다. 대상을 안 주면
    안 끝난 티켓은 **백로그로 돌아간다** — 다음 회차가 없어도 닫을 수 있고 그것이 기본이다.
  * 활성 회차는 **팀당 하나**다. 팀이 다르면 같은 기간에 나란히 연다.
  * 닫힌 회차는 **이름만** 고친다. 기간·목표는 기록이다.
  * 편성(열기·닫기·수정·삭제)은 관리 범위가 그 팀을 덮는 사람만 한다 — 보이는데 못
    고치면 403 이다.
  * 팀 미정(레거시) 회차는 열 수 없고, 팀을 정해 주면(NULL → 값) 보통 회차가 된다.

파일 이름이 `test_work_*` 인 이유: `scripts/verify.py` 가 `app/work/service.py` 변경을
그 글롭으로 이 파일에 매핑한다.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select as sa_select

from app.core.errors import ConflictError, ForbiddenError, ValidationAppError
from app.org.constants import DEFAULT_ORG_ID
from app.org.models import Department
from app.projects.models import Project
from app.tickets.models import PROJECT_LINK_OK, Ticket
from app.work import codes as work_codes
from app.work import service
from app.work.models import Sprint, TicketActivity

pytestmark = pytest.mark.unit

TODAY = date(2026, 8, 27)


@pytest.fixture()
def world(db, make_user):
    """팀 둘(A 와 그 아래 A-1, 그리고 B) + 팀별 프로젝트 + 상태별 회차 + 열린 회차의 티켓."""
    team_a = Department(name="라이프 A팀", org_id=DEFAULT_ORG_ID)
    team_b = Department(name="라이프 B팀", org_id=DEFAULT_ORG_ID)
    db.add_all([team_a, team_b])
    db.flush()
    team_a1 = Department(name="라이프 A-1파트", org_id=DEFAULT_ORG_ID, parent_id=team_a.id)
    db.add(team_a1)
    db.flush()

    boss = make_user("sprint-life-boss@goodmit.co.kr", role="admin", display_name="운영자")
    boss.admin_scope = "global"
    # A 팀 사람인데 관리 범위는 A-1 뿐 — A 의 회차는 **보이지만 편성은 못 한다**.
    sub_boss = make_user("sprint-life-sub@goodmit.co.kr", role="admin", display_name="파트장")
    sub_boss.department_id = team_a.id
    sub_boss.admin_scope = "dept"
    sub_boss.scope_dept_id = team_a1.id
    member = make_user("sprint-life-member@goodmit.co.kr", role="user", display_name="팀원")
    member.department_id = team_a.id
    db.commit()

    project = work_codes.insert_with_code(
        db, Project(name="회차 프로젝트", org_id=DEFAULT_ORG_ID, dept_id=team_a.id,
                    notion_page_id="proj-life")
    )
    other = work_codes.insert_with_code(
        db, Project(name="이웃 프로젝트", org_id=DEFAULT_ORG_ID, dept_id=team_b.id,
                    notion_page_id="proj-life2")
    )

    def sprint(name, *, team, state, starts=TODAY - timedelta(days=3)):
        row = Sprint(
            name=name, department_id=team.id if team is not None else None,
            org_id=DEFAULT_ORG_ID, starts_on=starts, ends_on=starts + timedelta(days=7),
            state=state,
        )
        db.add(row)
        db.flush()
        return row

    active = sprint("열린 회차", team=team_a, state="active")
    planned = sprint("계획 회차", team=team_a, state="planned")
    closed = sprint("닫은 회차", team=team_a, state="closed", starts=TODAY - timedelta(days=20))
    sub_sprint = sprint("파트 회차", team=team_a1, state="planned")
    other_sprint = sprint("이웃 회차", team=team_b, state="planned")
    # 🔴 B 팀도 같은 기간에 활성 회차를 갖는다 — 활성 유일은 조직이 아니라 팀 축이다.
    other_active = sprint("이웃 열린 회차", team=team_b, state="active")
    unassigned = sprint("팀 미정 회차", team=None, state="planned")

    def ticket(n, *, status):
        row = Ticket(
            title=f"티켓 {n}", notion_page_id=f"life-page-{n}", project_uid=project.id,
            project_link=PROJECT_LINK_OK, status=status, org_id=DEFAULT_ORG_ID,
            source="notion", notion_ticket_number=n, seq=n, sprint_id=active.id,
        )
        db.add(row)
        db.flush()
        return row

    open_ticket = ticket(1, status="진행")
    done_ticket = ticket(2, status="완료")
    db.commit()
    return {
        "boss": boss, "sub_boss": sub_boss, "member": member,
        "team_a": team_a, "team_a1": team_a1, "team_b": team_b,
        "project": project, "other": other,
        "active": active, "planned": planned, "closed": closed, "sub_sprint": sub_sprint,
        "other_sprint": other_sprint, "other_active": other_active, "unassigned": unassigned,
        "open_ticket": open_ticket, "done_ticket": done_ticket,
    }


def _close(db, world, sprint, target=None, *, actor=None):
    return service.close_sprint_and_carry_over(
        db, actor or world["boss"], sprint_id=sprint.id,
        target_sprint_id=target.id if target is not None else None,
    )


def _sprint_acts(db, ticket_id):
    return db.execute(
        sa_select(TicketActivity).where(
            TicketActivity.ticket_id == ticket_id, TicketActivity.kind == "sprint",
        )
    ).scalars().all()


# ── 닫기의 전제 ──────────────────────────────────────────────────────────────


def test_closing_a_planned_sprint_is_rejected(db, world):
    """연 적이 없는 회차는 닫을 수 없다 — 잘못 만든 회차는 삭제가 답이다."""
    with pytest.raises(ValidationAppError):
        _close(db, world, world["planned"])


def test_closing_a_closed_sprint_again_is_rejected(db, world):
    """🔴 두 번째 닫기는 이월을 한 번 더 돌린다 — 「N건 옮김」이 거짓이 된다."""
    first = _close(db, world, world["active"], target=world["planned"])
    assert first["carried_over"] == 1, first
    with pytest.raises(ConflictError):
        _close(db, world, world["active"], target=world["planned"])


# ── 이월 대상 검증 ──────────────────────────────────────────────────────────


def test_carrying_over_into_itself_is_rejected(db, world):
    """자기 자신으로 이월하면 티켓은 그대로인데 「N건을 옮겼습니다」가 뜬다 — 거짓말이다."""
    with pytest.raises(ValidationAppError):
        _close(db, world, world["active"], target=world["active"])


def test_carrying_over_into_a_closed_sprint_is_rejected(db, world):
    """닫힌 회차로 보내면 받은 쪽에서 그 티켓을 아무도 다시 보지 않는다."""
    with pytest.raises(ValidationAppError):
        _close(db, world, world["active"], target=world["closed"])


def test_carrying_over_into_another_teams_sprint_is_rejected(db, world):
    """🔴 다른 팀의 회차로는 못 보낸다 — 담기(`move`)·생성이 지키는 자격(같은 팀)과 같다.

    하위 파트의 회차도 다른 팀이다. 「A 의 일」을 「A-1 의 회차」로 밀어 넣으면 그 파트의
    회의가 남의 일로 시작한다.
    """
    with pytest.raises(ValidationAppError):
        _close(db, world, world["active"], target=world["other_sprint"])
    with pytest.raises(ValidationAppError):
        _close(db, world, world["active"], target=world["sub_sprint"])
    db.expire_all()
    assert db.get(Sprint, world["active"].id).state == "active", "거절했는데 닫혔다"


def test_carrying_over_into_the_same_teams_next_sprint_works(db, world):
    """반례 — 같은 팀의 열린(계획) 회차로는 보낸다. 끝난 일은 닫힌 회차에 남는다."""
    out = _close(db, world, world["active"], target=world["planned"])
    assert out["carried_over"] == 1, out
    db.expire_all()
    assert db.get(Ticket, world["open_ticket"].id).sprint_id == world["planned"].id
    # 끝난 일은 닫힌 회차에 남는다 — 기록이다.
    assert db.get(Ticket, world["done_ticket"].id).sprint_id == world["active"].id
    assert db.get(Sprint, world["active"].id).state == "closed"


def test_closing_without_a_target_returns_unfinished_work_to_the_backlog(db, world):
    """🔴 대상이 없으면 안 끝난 티켓은 **백로그**다 — 다음 회차가 없어도 닫을 수 있다.

    「다음 회차가 없으면 닫을 수 없다」는 제약을 만들지 않는다. 티켓은 대상 회차 또는
    백로그 둘 중 하나로만 가고, 어느 쪽이든 활동 한 줄이 남는다(유실·애매 상태 없음).
    """
    out = _close(db, world, world["active"])
    assert out["carried_over"] == 1, out
    db.expire_all()
    assert db.get(Ticket, world["open_ticket"].id).sprint_id is None
    assert db.get(Ticket, world["done_ticket"].id).sprint_id == world["active"].id
    assert db.get(Sprint, world["active"].id).state == "closed"
    acts = _sprint_acts(db, world["open_ticket"].id)
    assert any(a.from_value == world["active"].id and a.to_value is None for a in acts), acts


# ── `/state` 의 전이 ────────────────────────────────────────────────────────


def test_a_closed_sprint_cannot_be_reopened(db, world):
    """closed 는 종착이다 — 번다운·이월 기록이 닫힌 시점 기준으로 서 있다."""
    with pytest.raises(ConflictError):
        service.set_sprint_state(
            db, world["boss"], sprint_id=world["closed"].id, state="active"
        )
    with pytest.raises(ConflictError):
        service.set_sprint_state(
            db, world["boss"], sprint_id=world["closed"].id, state="planned"
        )


def test_closing_via_the_state_endpoint_is_rejected(db, world):
    """🔴 닫기는 `/close` 한 곳이다 — `/state` 로 닫으면 이월 없이 닫혀 티켓이 붕 뜬다."""
    with pytest.raises(ValidationAppError):
        service.set_sprint_state(
            db, world["boss"], sprint_id=world["active"].id, state="closed"
        )
    with pytest.raises(ValidationAppError):
        service.set_sprint_state(
            db, world["boss"], sprint_id=world["planned"].id, state="closed"
        )


def test_planned_and_active_transitions_still_work(db, world):
    """반례 — 열기·되돌리기·같은 상태 재설정은 그대로 된다."""
    # 같은 팀에 열린 회차가 이미 있으므로 먼저 닫는다.
    _close(db, world, world["active"])
    opened = service.set_sprint_state(
        db, world["boss"], sprint_id=world["planned"].id, state="active"
    )
    assert opened["state"] == "active"
    idempotent = service.set_sprint_state(
        db, world["boss"], sprint_id=world["planned"].id, state="active"
    )
    assert idempotent["state"] == "active"
    back = service.set_sprint_state(
        db, world["boss"], sprint_id=world["planned"].id, state="planned"
    )
    assert back["state"] == "planned"


def test_a_second_active_sprint_in_the_same_team_conflicts(db, world):
    """한 팀에 열린 회차는 하나뿐이다 — 둘이면 「이번 회차」에 답이 둘이다."""
    with pytest.raises(ConflictError):
        service.set_sprint_state(
            db, world["boss"], sprint_id=world["planned"].id, state="active"
        )


def test_another_team_may_have_its_own_active_sprint_at_the_same_time(db, world):
    """🔴 활성 유일은 **팀 축**이다 — B 팀의 열린 회차가 A 팀 파트의 열기를 막지 않는다.

    B 는 이미 열려 있고(`other_active`), A-1 파트도 자기 회차를 연다. 옛 축(조직당·
    프로젝트당 하나)이었다면 여기서 막혔다.
    """
    db.expire_all()
    assert db.get(Sprint, world["other_active"].id).state == "active"
    opened = service.set_sprint_state(
        db, world["boss"], sprint_id=world["sub_sprint"].id, state="active"
    )
    assert opened["state"] == "active"
    active_teams = {
        s.department_id for s in db.execute(
            sa_select(Sprint).where(Sprint.state == "active")
        ).scalars().all()
    }
    assert {world["team_a"].id, world["team_a1"].id, world["team_b"].id} <= active_teams


def test_an_unassigned_sprint_cannot_be_opened_until_it_has_a_team(db, world):
    """팀 미정(레거시) 회차는 열 수 없다 — 담을 티켓의 자격을 판정할 팀이 없다."""
    with pytest.raises(ValidationAppError):
        service.set_sprint_state(
            db, world["boss"], sprint_id=world["unassigned"].id, state="active"
        )


def test_giving_an_unassigned_sprint_a_team_makes_it_an_ordinary_sprint(db, world):
    """팀을 정해 주면(NULL → 값) 보통 회차가 된다 — 그 뒤 열기는 그 팀의 활성 규칙을 따른다."""
    out = service.update_sprint(
        db, world["boss"], sprint_id=world["unassigned"].id,
        changes={"department_id": world["team_b"].id},
    )
    assert out["department_id"] == world["team_b"].id
    # B 는 이미 열린 회차가 있으니 열기는 충돌한다 — 보통 회차의 규칙 그대로다.
    with pytest.raises(ConflictError):
        service.set_sprint_state(
            db, world["boss"], sprint_id=world["unassigned"].id, state="active"
        )
    # 한 번 정한 팀은 못 바꾼다 — 담긴 티켓의 자격이 통째로 깨진다.
    with pytest.raises(ValidationAppError):
        service.update_sprint(
            db, world["boss"], sprint_id=world["unassigned"].id,
            changes={"department_id": world["team_a"].id},
        )


# ── 수정(PATCH)·삭제 규칙 ───────────────────────────────────────────────────


def test_updating_name_dates_and_goal_works(db, world):
    """오타·기간 실수를 고칠 길이 생겼다 — 보낸 칸만 바뀐다."""
    out = service.update_sprint(
        db, world["boss"], sprint_id=world["active"].id,
        changes={"name": "열린 회차 2기", "goal": "마감을 지킨다."},
    )
    assert (out["name"], out["goal"]) == ("열린 회차 2기", "마감을 지킨다.")
    # 안 보낸 칸은 그대로다.
    assert out["starts_on"] == (TODAY - timedelta(days=3)).isoformat()
    assert out["department_id"] == world["team_a"].id


def test_a_closed_sprint_keeps_its_dates_and_goal(db, world):
    """🔴 닫은 회차는 **이름만** 고친다 — 기간·목표는 그 회차의 기록이다."""
    with pytest.raises(ValidationAppError):
        service.update_sprint(
            db, world["boss"], sprint_id=world["closed"].id,
            changes={"ends_on": (TODAY + timedelta(days=30)).isoformat()},
        )
    with pytest.raises(ValidationAppError):
        service.update_sprint(
            db, world["boss"], sprint_id=world["closed"].id, changes={"goal": "새 목표"}
        )
    # 이름은 기록이 아니라 표기다 — 오타는 닫은 뒤에도 고친다.
    out = service.update_sprint(
        db, world["boss"], sprint_id=world["closed"].id, changes={"name": "닫은 회차(정정)"}
    )
    assert out["name"] == "닫은 회차(정정)"


def test_an_inverted_period_is_rejected(db, world):
    """반쪽만 보내도 합성해서 검증한다 — 시작일이 종료일을 넘으면 거절."""
    with pytest.raises(ValidationAppError):
        service.update_sprint(
            db, world["boss"], sprint_id=world["active"].id,
            changes={"starts_on": (TODAY + timedelta(days=30)).isoformat()},
        )


def test_a_duplicate_name_is_rejected_within_the_team_only(db, world):
    """이름은 **팀 안에서** 유일하다 — 제약 이름이 아니라 사람의 말로 거절한다.

    B 팀은 A 팀의 「열린 회차」와 같은 이름을 가질 수 있다. 팀 A 의 「9-2」와 팀 B 의
    「9-2」는 다른 회차다.
    """
    with pytest.raises(ConflictError):
        service.update_sprint(
            db, world["boss"], sprint_id=world["planned"].id, changes={"name": "열린 회차"}
        )
    out = service.update_sprint(
        db, world["boss"], sprint_id=world["other_sprint"].id, changes={"name": "열린 회차"}
    )
    assert out["name"] == "열린 회차"
    with pytest.raises(ConflictError):
        service.create_sprint(
            db, world["boss"], name="열린 회차", department_id=world["team_a"].id,
            starts_on=TODAY.isoformat(), ends_on=(TODAY + timedelta(days=7)).isoformat(),
        )


def test_creating_a_sprint_needs_a_team_and_nothing_else(db, world):
    """회차는 팀의 것이다 — 팀은 필수이고, 그 팀에 프로젝트가 있어야 한다는 제한은 없다."""
    with pytest.raises(ValidationAppError):
        service.create_sprint(
            db, world["boss"], name="팀 없는 회차", department_id="",
            starts_on=TODAY.isoformat(), ends_on=(TODAY + timedelta(days=7)).isoformat(),
        )
    # A-1 파트에는 프로젝트가 하나도 없다 — 그래도 회차를 먼저 만들 수 있다.
    out = service.create_sprint(
        db, world["boss"], name="파트 다음 회차", department_id=world["team_a1"].id,
        starts_on=TODAY.isoformat(), ends_on=(TODAY + timedelta(days=7)).isoformat(),
    )
    assert out["department_id"] == world["team_a1"].id
    assert out["state"] == "planned"
    assert db.get(Sprint, out["id"]).org_id == DEFAULT_ORG_ID


def test_deleting_a_planned_sprint_detaches_tickets_with_a_trace(db, world):
    """planned 삭제는 담긴 티켓을 **기록을 남기며** 백로그로 뺀다 — FK 에 맡기지 않는다."""
    ticket = db.get(Ticket, world["open_ticket"].id)
    ticket.sprint_id = world["planned"].id
    db.commit()

    out = service.delete_sprint(db, world["boss"], sprint_id=world["planned"].id)
    assert out == {"deleted": True, "name": "계획 회차", "detached": 1}
    db.expire_all()
    assert db.get(Sprint, world["planned"].id) is None
    assert db.get(Ticket, world["open_ticket"].id).sprint_id is None
    acts = _sprint_acts(db, world["open_ticket"].id)
    assert any(a.from_value == world["planned"].id and a.to_value is None for a in acts)


def test_active_and_closed_sprints_cannot_be_deleted(db, world):
    """active 는 닫기로 정리하고, closed 는 기록이라 남긴다."""
    with pytest.raises(ValidationAppError):
        service.delete_sprint(db, world["boss"], sprint_id=world["active"].id)
    with pytest.raises(ValidationAppError):
        service.delete_sprint(db, world["boss"], sprint_id=world["closed"].id)


# ── 편성 권한 — 보이는 것과 고치는 것은 다른 문이다 ────────────────────────


def test_a_visible_sprint_outside_my_management_scope_is_forbidden_not_hidden(db, world):
    """🔴 A 팀 사람이자 A-1 관리자는 A 의 회차를 **보지만 편성은 못 한다** (403).

    404 가 아니다 — 목록에 나오는 회차에 「없습니다」로 답하면 화면이 거짓말을 한다.
    자기 관리 범위(A-1)의 회차는 그대로 편성한다(반례).
    """
    sub = world["sub_boss"]
    assert service.get_scoped_sprint_or_404(db, world["active"].id, sub) is not None
    with pytest.raises(ForbiddenError):
        service.set_sprint_state(db, sub, sprint_id=world["planned"].id, state="active")
    with pytest.raises(ForbiddenError):
        service.update_sprint(db, sub, sprint_id=world["planned"].id, changes={"name": "x"})
    with pytest.raises(ForbiddenError):
        service.delete_sprint(db, sub, sprint_id=world["planned"].id)
    with pytest.raises(ForbiddenError):
        _close(db, world, world["active"], actor=sub)
    with pytest.raises(ForbiddenError):
        service.create_sprint(
            db, sub, name="남의 팀에 만들기", department_id=world["team_a"].id,
            starts_on=TODAY.isoformat(), ends_on=(TODAY + timedelta(days=7)).isoformat(),
        )
    renamed = service.update_sprint(
        db, sub, sprint_id=world["sub_sprint"].id, changes={"name": "파트 회차(정정)"}
    )
    assert renamed["name"] == "파트 회차(정정)"


def test_a_plain_team_member_cannot_plan_at_all(db, world):
    """일반 팀원은 자기 팀 회차를 보지만 편성하지 못한다 — 관리 범위가 없다."""
    member = world["member"]
    assert service.get_scoped_sprint_or_404(db, world["planned"].id, member) is not None
    with pytest.raises(ForbiddenError):
        service.set_sprint_state(db, member, sprint_id=world["planned"].id, state="active")
    with pytest.raises(ForbiddenError):
        service.delete_sprint(db, member, sprint_id=world["planned"].id)
