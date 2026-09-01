"""스프린트 회의 — **회차를 아는 화면** (지시 4).

qa-contract-replaced-by: tests/unit/test_sprint_burndown.py

## 이 파일이 지키는 것

예전 회의 화면은 회차를 몰랐다. 「이번 주 월요일부터 다음 주 월요일까지 마감인 티켓」을
스프린트라고 불렀고, 그래서 「이번 회차에 뭐 넣기로 했지」에 아무도 답할 수 없었다.
지금은 `sprint_id` 한 칸이 그 정의다 — 그 한 칸이 실제로 경계로 쓰이는가가 이 파일의
첫 단정이다.

나머지 넷:

  * 「오늘 논의할 항목」은 **유형별**이다. 지연·차단·미할당·마감 임박·범위 변경이
    각각 다른 목록이고, 회의에서 하는 말이 서로 다르다.
  * **신호는 서버가 판정한다.** 화면이 브라우저 시계로 「지연」을 세면 같은 회의에서
    두 사람이 다른 목록을 본다.
  * 후보는 **실제 백로그 티켓**이다 — 회차에 담긴 티켓이 후보로 다시 나오면 회의가
    같은 일을 두 번 본다.
  * 빈 회차의 건강은 100 이 아니라 **모른다**. 아무 일도 안 담긴 회차가 화면에서 가장
    건강해 보이면 그 지표는 거짓말이다.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest

from app.core.errors import ForbiddenError, ValidationAppError
from app.org.constants import DEFAULT_ORG_ID
from app.projects.models import Project
from app.tickets.models import PROJECT_LINK_OK, Ticket
from app.work import codes as work_codes
from app.work import meeting
from app.work.models import ACT_SPRINT, Sprint, TicketActivity

pytestmark = pytest.mark.unit

TODAY = date(2026, 8, 27)


@pytest.fixture()
def world(db, make_user):
    """한 회차, 그 안의 티켓 넷, 그리고 회차 밖의 백로그 하나."""
    boss = make_user("meeting-boss@goodmit.co.kr", role="admin", display_name="관리자")
    boss.admin_scope = "global"
    member = make_user("meeting-dev@goodmit.co.kr", role="user", display_name="개발자")
    db.commit()

    project = work_codes.insert_with_code(
        db, Project(name="회의 프로젝트", org_id=DEFAULT_ORG_ID, notion_page_id="proj-meet")
    )
    sprint = Sprint(
        name="8월 넷째 주", project_id=project.id, org_id=DEFAULT_ORG_ID,
        starts_on=TODAY - timedelta(days=4), ends_on=TODAY + timedelta(days=3),
        state="active",
    )
    db.add(sprint)
    db.flush()

    def ticket(n, **kw):
        row = Ticket(
            title=kw.pop("title", f"티켓 {n}"), notion_page_id=f"meet-page-{n}",
            project_uid=project.id, project_link=PROJECT_LINK_OK,
            org_id=DEFAULT_ORG_ID, source="notion", notion_ticket_number=n,
            status=kw.pop("status", "진행"), **kw,
        )
        db.add(row)
        db.flush()
        return row

    late = ticket(1, title="늦은 일", due_date=TODAY - timedelta(days=2), est_wd=2)
    stuck = ticket(2, title="막힌 일", blocked_flag=True, blocked_reason="외부 응답 대기", est_wd=1)
    soon = ticket(3, title="곧 마감", due_date=TODAY + timedelta(days=1), est_wd=3)
    done = ticket(
        4, title="끝난 일", status="완료", due_date=TODAY - timedelta(days=1), est_wd=1,
        # 완료 시각. 실제 경로(`repository_native._stamp_completion`)가 상태를 쓸 때 찍는
        # 값이고, 번다운의 「그날 끝난 일」이 이것을 읽는다.
        completed_at=datetime.combine(TODAY - timedelta(days=1), time(9, 0)),
    )
    for row in (late, stuck, soon, done):
        row.sprint_id = sprint.id
    # 회차 **밖**의 일. 후보로만 나와야 하고 요약에는 안 들어간다.
    ticket(5, title="아직 안 담은 일", status="계획", est_wd=5)
    db.commit()
    return {
        "boss": boss, "member": member, "project": project, "sprint": sprint,
        "late": late, "stuck": stuck, "soon": soon, "done": done,
    }


def _meeting(db, world):
    return meeting.meeting(db, world["boss"], sprint_id=world["sprint"].id, today=TODAY)


# ── 번다운 ──────────────────────────────────────────────────────────────────
#
# 🔴 이 묶음이 `tests/unit/test_sprint_burndown.py` 를 대신한다. 그 파일은 「그날 이후로
# 마감이 남아 있는 업무량」의 분포를 쟀다 — 그것이 번다운이 아니라는 것을 그 모듈 스스로
# 적고 있었고(「완료 시각이 어디에도 없다」), 그 전제가 사실이 아니게 됐다.
# `tickets.completed_at` 이 상태를 쓰는 자리 한 곳에서 찍히므로 실제 소진을 **잰다.**


def _burndown(db, world):
    return _meeting(db, world)["burndown"]["points"]


def test_the_burndown_draws_real_remaining_work_not_a_due_date_histogram(db, world):
    """남은 일 선은 **그날 끝에 안 끝난 공수**다.

    표본: 예상 WD 가 2·1·3·1 이고 그중 1(「끝난 일」)만 완료다. 취소는 없다.
    첫날에는 넷 다 안 끝났으므로 7 이고, 완료가 찍힌 날부터 6 으로 내려간다.
    """
    points = _burndown(db, world)
    assert points[0]["remaining"] == 7.0
    # 마지막으로 그린 점(오늘)에서는 완료분 1 이 빠져 있다.
    drawn = [p for p in points if p["remaining"] is not None]
    assert drawn[-1]["remaining"] == 6.0
    assert drawn[-1]["done"] == 1.0


def test_the_burndown_does_not_draw_the_future(db, world):
    """🔴 오늘 이후의 「남은 일」은 `None` 이다 — 내일 얼마가 남을지는 아무도 모른다.

    이상선과 범위선은 끝까지 그린다(계획이니까). 실제만 오늘에서 멈춘다.
    """
    points = _burndown(db, world)
    future = [p for p in points if p["date"] > TODAY.isoformat()]
    assert future, "이 표본은 회차 종료일이 오늘 뒤라 미래 점이 있어야 한다"
    assert all(p["remaining"] is None for p in future)
    assert all(p["ideal"] is not None and p["scope"] is not None for p in future)


def test_a_ticket_without_a_due_date_still_counts(db, world):
    """마감일이 없는 티켓도 **총량에 든다**.

    옛 그림은 마감일이 축이라 그런 티켓을 통째로 뺐다 — 그래서 같은 화면의 「남은 WD」와
    그림의 총량이 서로 다른 값이었다. 「막힌 일」에는 마감이 없는데도 1인일이 세어진다.
    """
    body = _meeting(db, world)
    assert body["burndown"]["total_est_wd"] == body["summary"]["planned_wd"]


def test_the_ideal_line_falls_to_zero_on_the_last_day(db, world):
    """계획선은 첫날의 범위에서 마지막 날 0 까지 곧게 내려간다."""
    points = _burndown(db, world)
    assert points[0]["ideal"] == 7.0
    assert points[-1]["ideal"] == 0.0


# ── 경계 ────────────────────────────────────────────────────────────────────


def test_the_sprint_is_the_boundary_not_the_week(db, world):
    """🔴 회차에 담긴 것만 센다. 마감이 이번 주여도 안 담겼으면 회의의 대상이 아니다."""
    body = _meeting(db, world)
    assert body["summary"]["total"] == 4
    titles = {r["title"] for r in body["discuss"]["overdue"]["items"]}
    assert "아직 안 담은 일" not in titles


def test_the_candidates_are_real_backlog_tickets(db, world):
    """후보는 **어느 회차에도 안 담긴** 티켓이다.

    회차 안의 티켓이 후보로 다시 나오면 회의가 같은 일을 두 번 보고, 「추가」를 누르면
    아무 일도 안 일어난다.
    """
    body = _meeting(db, world)
    titles = {c["title"] for c in body["candidates"]}
    assert titles == {"아직 안 담은 일"}


# ── 오늘 논의할 항목 ─────────────────────────────────────────────────────────


def test_discussion_is_split_by_type(db, world):
    """단순 목록 하나가 아니라 유형별이다 — 지연과 미할당은 회의에서 하는 말이 다르다.

    뒤의 셋(`issue`·`no_estimate`·`no_due`)은 **회의 준비**다. 예상 WD 나 마감이 비어 있으면
    번다운도 담당자별 남은 WD 도 못 그리는데, 예전에는 그림이 안 나온 **뒤에야** 그 사실을
    알 수 있었다 — 이제 고칠 목록으로 먼저 보인다.
    """
    discuss = _meeting(db, world)["discuss"]
    assert set(discuss) == {
        "overdue", "blocked", "issue", "unassigned", "due_soon",
        "no_estimate", "no_due", "scope_changes",
    }
    assert [r["title"] for r in discuss["overdue"]["items"]] == ["늦은 일"]
    assert [r["title"] for r in discuss["blocked"]["items"]] == ["막힌 일"]
    assert [r["title"] for r in discuss["due_soon"]["items"]] == ["곧 마감"]
    # 담당자를 아무에게도 안 걸었으므로 **안 끝난 것**이 전부 미할당이다.
    # (끝난 티켓은 안 센다 — 오늘 회의에서 담당자를 정할 일이 아니다.)
    assert discuss["unassigned"]["total"] == 3


def test_a_finished_ticket_is_not_overdue(db, world):
    """🔴 지난주에 끝낸 일이 오늘 빨갛게 뜨면 그 색은 아무 행동도 요구하지 않는다.

    「끝난 일」의 마감은 어제지만 지연이 아니다. 서버와 화면이 같은 규칙을 쓴다
    (`app/work/workflow.py::is_overdue` · `frontend/src/lib/ticketSignals.js`).
    """
    body = _meeting(db, world)
    assert body["summary"]["overdue"] == 1
    assert "끝난 일" not in {r["title"] for r in body["discuss"]["overdue"]["items"]}


def test_today_comes_from_the_caller(db, world):
    """「오늘」은 인자다. 이 함수 안에서 시계를 읽지 않는다.

    읽으면 서버의 시간대에 따라 목록이 달라지고, 그 차이는 KST 09:00 이전에만 나타나
    아무도 재현하지 못한다.
    """
    later = meeting.meeting(
        db, world["boss"], sprint_id=world["sprint"].id, today=TODAY + timedelta(days=5)
    )
    # 닷새 뒤에는 「곧 마감」도 지난 일이다.
    assert later["summary"]["overdue"] == 2


# ── 범위 변경 ────────────────────────────────────────────────────────────────


def test_scope_change_is_unknown_without_a_record(db, world):
    """🔴 기록이 없으면 「안 바뀌었다」가 아니라 **모른다**다.

    지금 상태만 봐서는 「중간에 뭐가 들어왔나」를 알 수 없다. 0 으로 적으면 화면이
    「범위가 안 바뀐 안정된 회차」라고 말하는데, 실은 아무것도 모르는 것이다.
    """
    scope = _meeting(db, world)["scope"]
    # 추이도 **빈 목록**이다 — 그릴 것이 없다는 사실과 「0 이다」는 다른 말이고,
    # 화면은 `tracked` 로 그 둘을 가른다.
    assert scope == {"tracked": False, "added": 0, "removed": 0, "trend": []}


def test_a_mid_sprint_addition_is_counted(db, world):
    """회차가 시작한 뒤 들어온 티켓은 범위 변경이다."""
    db.add(
        TicketActivity(
            id="act-scope-1", ticket_id=world["soon"].id, kind=ACT_SPRINT,
            field="sprint_id", from_value=None, to_value=world["sprint"].id,
            created_at=world["sprint"].created_at.replace(year=2026, month=8, day=26),
        )
    )
    db.commit()
    body = _meeting(db, world)
    assert body["scope"]["tracked"] is True
    assert body["scope"]["added"] == 1
    assert [c["title"] for c in body["discuss"]["scope_changes"]["items"]] == ["곧 마감"]


# ── 건강 ────────────────────────────────────────────────────────────────────


def test_an_empty_sprint_has_no_health(db, world, make_user):
    """🔴 빈 회차는 100 점이 아니라 **모른다**다.

    100 을 주면 아무 일도 안 담긴 회차가 화면에서 가장 건강해 보인다. `null` 은 0 이
    아니고, 「모른다」는 「좋다」가 아니다.
    """
    empty = Sprint(
        name="빈 회차", project_id=world["project"].id, org_id=DEFAULT_ORG_ID,
        starts_on=TODAY, ends_on=TODAY + timedelta(days=7), state="planned",
    )
    db.add(empty)
    db.commit()
    body = meeting.meeting(db, world["boss"], sprint_id=empty.id, today=TODAY)
    assert body["health"] is None
    assert body["summary"]["total"] == 0


def test_health_falls_when_work_is_late_or_stuck(db, world):
    """지연과 차단이 점수를 깎는다. 깎이지 않으면 이 지표는 아무 것도 말하지 않는다."""
    body = _meeting(db, world)
    assert body["health"]["score"] < 100
    # 진도는 넷 중 하나가 끝났으니 25% 다.
    assert body["health"]["progress_pct"] == 25.0


# ── 업무량 ──────────────────────────────────────────────────────────────────


def test_finished_work_stops_counting_toward_the_load(db, world):
    """남은 공수는 **남은 것**이다. 끝난 일이 계속 세어지면 회차 끝까지 숫자가 안 준다."""
    body = _meeting(db, world)
    # 2 + 1 + 3 = 6. 「끝난 일」의 1 은 빠진다.
    assert body["summary"]["remaining_wd"] == 6.0


# ── 회의록 ──────────────────────────────────────────────────────────────────


def test_a_decision_survives_the_screen_closing(db, world):
    """회의록은 저장된다 — 이 표가 생긴 이유가 그 한 줄이다."""
    row = meeting.add_decision(
        db, world["member"], sprint_id=world["sprint"].id,
        kind="decision", body="결제 모듈은 다음 회차로 미룬다.",
    )
    assert row["kind"] == "decision"
    again = _meeting(db, world)["decisions"]
    assert [d["body"] for d in again] == ["결제 모듈은 다음 회차로 미룬다."]


def test_an_action_item_may_have_nothing_filled_in(db, world):
    """🔴 담당자도 마감도 티켓도 없이 적을 수 있다.

    필수로 만들면 「담당자 미정」인 할 일을 적을 수 없고, 그러면 사람들은 그것을 아예
    안 적는다. 적는 비용이 말하는 비용보다 크면 기록은 사라진다.
    """
    row = meeting.add_decision(
        db, world["member"], sprint_id=world["sprint"].id,
        kind="action", body="A 팀에 일정 물어보기",
    )
    assert row["assignee_user_id"] is None
    assert row["due_date"] is None
    assert row["ticket_id"] is None
    assert row["done"] is False


def test_a_decision_can_link_a_ticket_that_is_visible(db, world):
    """티켓이 될 만한 것은 이어 둔다 — 화면이 그 줄에서 티켓으로 바로 갈 수 있게.

    `ticket_key` 는 여기서 `None` 이다. 이 픽스처의 티켓은 채번 경로를 안 지나서
    `canonical_key` 가 아직 없기 때문이다(D-282 — 이름은 트리거가 파생한다). 화면이
    가는 데 쓰는 것은 `ticket_page_id` 라, 단정도 그쪽에 건다.
    """
    row = meeting.add_decision(
        db, world["boss"], sprint_id=world["sprint"].id,
        kind="action", body="막힌 일의 담당 팀을 다시 정한다.",
        ticket_id=world["stuck"].id,
    )
    assert row["ticket_id"] == world["stuck"].id
    assert row["ticket_page_id"] == "meet-page-2"


def test_an_empty_body_is_refused(db, world):
    with pytest.raises(ValidationAppError):
        meeting.add_decision(
            db, world["boss"], sprint_id=world["sprint"].id, kind="decision", body="   "
        )


def test_a_body_past_the_cap_is_refused(db, world):
    with pytest.raises(ValidationAppError):
        meeting.add_decision(
            db, world["boss"], sprint_id=world["sprint"].id, kind="decision",
            body="가" * (meeting.DECISION_BODY_MAX + 1),
        )


def test_marking_an_action_done_is_the_common_edit(db, world):
    row = meeting.add_decision(
        db, world["member"], sprint_id=world["sprint"].id, kind="action", body="물어보기"
    )
    after = meeting.update_decision(
        db, world["member"], decision_id=row["id"], changes={"done": True}
    )
    assert after["done"] is True


def test_a_bystander_cannot_edit_someone_elses_note(db, world, make_user):
    """🔴 회의록은 함께 보는 글이라 아무나 고치면 「누가 바꿨나」가 사라진다.

    고칠 수 있는 사람은 적은 사람 · 걸린 담당자 · 운영군뿐이다.
    """
    row = meeting.add_decision(
        db, world["member"], sprint_id=world["sprint"].id, kind="decision", body="정한 것"
    )
    stranger = make_user("meeting-other@goodmit.co.kr", role="user", display_name="남")
    db.commit()
    with pytest.raises(ForbiddenError):
        meeting.update_decision(
            db, stranger, decision_id=row["id"], changes={"body": "몰래 고친 것"}
        )
    with pytest.raises(ForbiddenError):
        meeting.delete_decision(db, stranger, decision_id=row["id"])


# ── 만드는 자리가 기본값을 정한다 (지시 5) ──────────────────────────────────


def _create(db, settings, user, **kw):
    from app.tickets import service as tickets_service
    from app.tickets.schemas import TicketCreate

    payload = TicketCreate(
        title=kw.pop("title", "새 일"), project_id=kw.pop("project_id"),
        est_wd=1.0, due_date="2026-09-30", **kw,
    )
    return tickets_service.create_ticket(db, None, settings, user, payload=payload)


def test_a_plain_new_ticket_lands_in_the_backlog(db, settings, world):
    """🔴 회차를 안 주면 **백로그**다.

    일반 「새 티켓」은 아직 언제 할지 안 정한 일이다. 어딘가의 회차에 자동으로 담기면
    그 회의에 아무도 넣기로 하지 않은 일이 끼어든다.
    """
    from app.tickets.models import Ticket

    out = _create(db, settings, world["boss"], project_id=world["project"].id)
    row = db.get(Ticket, out["ticket"]["uid"])
    assert row.sprint_id is None


def test_creating_inside_a_sprint_context_puts_it_in_that_sprint(db, settings, world):
    """판의 회차 맥락에서 만든 티켓은 그 회차의 일이다.

    이 칸이 없으면 만든 사람이 곧바로 「스프린트에 담기」를 한 번 더 눌러야 하고, 그
    한 번을 빠뜨린 티켓은 회의에서 아무도 못 본다.
    """
    from app.tickets.models import Ticket

    out = _create(
        db, settings, world["boss"],
        project_id=world["project"].id, sprint_id=world["sprint"].id,
    )
    row = db.get(Ticket, out["ticket"]["uid"])
    assert row.sprint_id == world["sprint"].id
    # 회의의 「범위 변경」이 읽는 바로 그 기록이 함께 남는다 — 안 남기면 만들자마자 담긴
    # 티켓만 그 셈에서 조용히 빠진다.
    body = _meeting(db, world)
    assert body["scope"]["tracked"] is True
    assert body["scope"]["added"] == 1


def test_a_sprint_from_another_project_is_refused(db, settings, world):
    """다른 프로젝트의 회차에 담긴 티켓은 그 회의에서 「우리 일이 아닌데 왜 여기 있지」가 된다."""
    from app.org.constants import DEFAULT_ORG_ID
    from app.projects.models import Project
    from app.work import codes as work_codes

    other = work_codes.insert_with_code(
        db, Project(name="다른 프로젝트", org_id=DEFAULT_ORG_ID, notion_page_id="proj-other")
    )
    db.commit()
    with pytest.raises(ValidationAppError):
        _create(
            db, settings, world["boss"],
            project_id=other.id, sprint_id=world["sprint"].id,
        )
