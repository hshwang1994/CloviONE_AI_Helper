"""회차 상태 기계 — planned ↔ active → closed, 그리고 closed 는 종착이다.

## 이 파일이 지키는 것

회차를 닫는 것은 되돌릴 수 없는 동작이고(이월이 실제로 티켓을 옮긴다), 그래서 전이가
아무 데서나 일어나면 안 된다. 이 파일이 못박는 규칙:

  * 닫기는 `/close` 한 곳이다 — `/state` 로는 closed 를 만들 수 없다.
  * planned 는 닫을 수 없다(연 적이 없는 회차에는 이월할 것이 없다 — 잘못 만든
    회차는 삭제가 답이다).
  * closed 는 다시 닫을 수 없다(이월이 한 번 더 돌면 「N건 옮김」이 거짓이 된다).
  * closed 는 다시 열 수 없다(번다운·활동 기록이 이미 닫힌 시점 기준으로 서 있다).
  * 이월 대상은 자기 자신·닫힌 회차·**다른 프로젝트의 회차**가 될 수 없다.
    팀 전체 회차(project_id NULL)로는 언제나 보낼 수 있다 — 그 회차는 모두의 것이다.

파일 이름이 `test_work_*` 인 이유: `scripts/verify.py` 가 `app/work/service.py` 변경을
그 글롭으로 이 파일에 매핑한다.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.core.errors import ConflictError, ValidationAppError
from app.org.constants import DEFAULT_ORG_ID
from app.projects.models import Project
from app.tickets.models import PROJECT_LINK_OK, Ticket
from app.work import codes as work_codes
from app.work import service
from app.work.models import Sprint

pytestmark = pytest.mark.unit

TODAY = date(2026, 8, 27)


@pytest.fixture()
def world(db, make_user):
    """프로젝트 둘 + 상태별 회차 + 열린 회차에 담긴 티켓(진행 1 · 완료 1)."""
    boss = make_user("sprint-life-boss@goodmit.co.kr", role="admin", display_name="운영자")
    boss.admin_scope = "global"
    db.commit()

    project = work_codes.insert_with_code(
        db, Project(name="회차 프로젝트", org_id=DEFAULT_ORG_ID, notion_page_id="proj-life")
    )
    other = work_codes.insert_with_code(
        db, Project(name="이웃 프로젝트", org_id=DEFAULT_ORG_ID, notion_page_id="proj-life2")
    )

    def sprint(name, *, project_id, state):
        row = Sprint(
            name=name, project_id=project_id, org_id=DEFAULT_ORG_ID,
            starts_on=TODAY - timedelta(days=3), ends_on=TODAY + timedelta(days=4),
            state=state,
        )
        db.add(row)
        db.flush()
        return row

    active = sprint("열린 회차", project_id=project.id, state="active")
    planned = sprint("계획 회차", project_id=project.id, state="planned")
    closed = sprint("닫은 회차", project_id=project.id, state="closed")
    other_sprint = sprint("이웃 회차", project_id=other.id, state="planned")
    team = sprint("팀 전체 회차", project_id=None, state="planned")

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
        "boss": boss, "project": project, "other": other,
        "active": active, "planned": planned, "closed": closed,
        "other_sprint": other_sprint, "team": team,
        "open_ticket": open_ticket, "done_ticket": done_ticket,
    }


def _close(db, world, sprint, target=None):
    return service.close_sprint_and_carry_over(
        db, world["boss"], sprint_id=sprint.id,
        target_sprint_id=target.id if target is not None else None,
    )


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


def test_carrying_over_into_another_projects_sprint_is_rejected(db, world):
    """다른 프로젝트의 회차로는 못 보낸다 — 담기(`move`)·생성이 지키는 불변식과 같다."""
    with pytest.raises(ValidationAppError):
        _close(db, world, world["active"], target=world["other_sprint"])


def test_carrying_over_into_the_team_sprint_still_works(db, world):
    """반례 — 팀 전체 회차(project_id NULL)로는 언제나 보낼 수 있다."""
    out = _close(db, world, world["active"], target=world["team"])
    assert out["carried_over"] == 1, out
    db.expire_all()
    assert db.get(Ticket, world["open_ticket"].id).sprint_id == world["team"].id
    # 끝난 일은 닫힌 회차에 남는다 — 기록이다.
    assert db.get(Ticket, world["done_ticket"].id).sprint_id == world["active"].id
    assert db.get(Sprint, world["active"].id).state == "closed"


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
    # 같은 프로젝트에 열린 회차가 이미 있으므로 먼저 닫는다.
    _close(db, world, world["active"], target=world["team"])
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


def test_a_second_active_sprint_in_the_same_project_still_conflicts(db, world):
    """기존 동작 유지 — 한 프로젝트에 열린 회차는 하나뿐이다."""
    with pytest.raises(ConflictError):
        service.set_sprint_state(
            db, world["boss"], sprint_id=world["planned"].id, state="active"
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


def test_a_closed_sprints_dates_are_frozen(db, world):
    """닫은 회차의 기간은 못 고친다 — 번다운·이월 기록이 그 축 위에 서 있다."""
    with pytest.raises(ValidationAppError):
        service.update_sprint(
            db, world["boss"], sprint_id=world["closed"].id,
            changes={"ends_on": (TODAY + timedelta(days=30)).isoformat()},
        )
    # 이름·목표는 기록이 아니라 표기다 — 닫은 뒤에도 고친다.
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


def test_a_duplicate_name_is_rejected_with_words(db, world):
    """제약 이름이 아니라 사람의 말로 거절한다."""
    with pytest.raises(ConflictError):
        service.update_sprint(
            db, world["boss"], sprint_id=world["planned"].id, changes={"name": "열린 회차"}
        )


def test_deleting_a_planned_sprint_detaches_tickets_with_a_trace(db, world):
    """planned 삭제는 담긴 티켓을 **기록을 남기며** 백로그로 뺀다 — FK 에 맡기지 않는다."""
    from app.work.models import TicketActivity

    ticket = db.get(Ticket, world["open_ticket"].id)
    ticket.sprint_id = world["planned"].id
    db.commit()

    out = service.delete_sprint(db, world["boss"], sprint_id=world["planned"].id)
    assert out == {"deleted": True, "name": "계획 회차", "detached": 1}
    db.expire_all()
    assert db.get(Sprint, world["planned"].id) is None
    assert db.get(Ticket, world["open_ticket"].id).sprint_id is None
    from sqlalchemy import select as sa_select
    acts = db.execute(
        sa_select(TicketActivity).where(
            TicketActivity.ticket_id == world["open_ticket"].id,
            TicketActivity.kind == "sprint",
        )
    ).scalars().all()
    assert any(a.from_value == world["planned"].id and a.to_value is None for a in acts)


def test_active_and_closed_sprints_cannot_be_deleted(db, world):
    """active 는 닫기로 정리하고, closed 는 기록이라 남긴다."""
    with pytest.raises(ValidationAppError):
        service.delete_sprint(db, world["boss"], sprint_id=world["active"].id)
    with pytest.raises(ValidationAppError):
        service.delete_sprint(db, world["boss"], sprint_id=world["closed"].id)
