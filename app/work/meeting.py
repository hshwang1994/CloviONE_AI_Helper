"""스프린트 회의 한 판 (지시 4).

## 이 모듈이 대신하는 것

예전 회의 화면(`app/sprints/service.py::build_sprint_summary`)은 **회차를 몰랐다.**
「이번 주 월요일부터 다음 주 월요일까지 마감인 티켓」을 모아 놓고 그것을 스프린트라고
불렀다. 그래서 회의에서 「이번 회차에 뭐 넣기로 했지」를 물으면 답이 없었고, 회차를
닫아도 그 주가 지나면 화면이 저절로 다음 주를 보여 줬다.

이제 회차는 실체가 있다(`sprints` 표). 이 모듈은 **그 회차에 담긴 티켓**만 본다 —
`sprint_id` 한 칸이 그 정의다. 마감일이 회차 밖인 티켓도 회차에 담겼으면 여기 있고,
회차 기간에 마감이지만 안 담긴 티켓은 여기 없다. 두 번째가 요점이다: 안 담긴 일은
회의의 대상이 아니라 **후보**다.

## 여섯 질문에 답한다

지시가 적은 여섯 질문이 이 모듈의 반환값 모양을 그대로 정한다.

    1 정상 진행인가          → `summary` · `burndown` · `health`
    2 어떤 티켓이 문제인가    → `discuss` (지연 · 차단 · 미할당 · 마감 임박 · 범위 변경)
    3 Workload 가 고른가      → `workload`
    4 Scope 가 얼마나 바뀌었나 → `scope` + `discuss.scope_changes`
    5 무엇을 더 넣을까        → `candidates`
    6 무엇을 정했나           → `decisions`

## 「범위 변경」은 계산이 아니라 **기록**이다

회차에 티켓이 몇 개인지는 지금 세면 되지만, 「중간에 몇 개가 들어왔나」는 지금 상태만
봐서는 알 수 없다. 답은 활동 기록에 있다(`ticket_activities`, `kind='sprint'`) — 회차가
시작한 뒤에 이 회차로 들어온 줄과 나간 줄을 센다. 그 기록이 없으면 이 값은 0 이고,
**0 과 「모른다」를 구별해 적는다**(`scope.tracked`).

## 신호의 정본은 서버다

지연은 오늘이 며칠인지에 달린 값이라 화면이 그 자리에서 판정할 수도 있다. 그런데 회의
화면은 **「오늘 논의할 항목」이라는 목록을 만든다** — 목록에 무엇이 들어가는가를 화면이
정하면 KST 09:00 이전에 접속한 사람과 이후에 접속한 사람이 다른 회의를 하게 된다.
그래서 여기서는 서버가 준 `today` 로 판정하고, 화면은 그 목록을 그대로 그린다.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.core.models_base import split_names, utcnow
from app.tickets.models import Ticket, api_page_id
from app.users.models import User
from app.work import workflow
from app.work.resolve import display_key
from app.work.models import (
    DECISION_KIND_ACTION,
    DECISION_KIND_DECISION,
    DECISION_KINDS,
    ACT_SPRINT,
    Sprint,
    SprintDecision,
    TicketActivity,
)

#: 「마감 임박」의 창. 회의는 주 단위라 사흘이면 이번 회의와 다음 회의 사이에 걸린다 —
#: 하루면 회의에서 말할 시간이 없고, 이레면 회차 전체가 임박이 된다.
DUE_SOON_DAYS = 3

#: 회의록 한 줄의 길이 상한. 회의록은 문장이지 문서가 아니다 — 길어지면 티켓 본문이
#: 있어야 할 내용이고, 그때는 `ticket_id` 로 잇는다.
DECISION_BODY_MAX = 2000

#: 「논의할 항목」 한 종류가 실어 나르는 최대 건수. 회의 한 자리에서 볼 수 있는 양이다.
#: 자르면 **자른 사실을 함께 싣는다**(`truncated`) — 안 그러면 다섯 건이 전부인 줄 안다.
DISCUSS_LIMIT = 20


def _row(ticket: Ticket, *, names: dict[str, dict]) -> dict:
    """회의 화면이 한 줄에 그리는 티켓. 판의 카드(`service._card`)와 **같은 이름**을 쓴다.

    두 화면이 같은 티켓을 다른 열쇠말로 받으면 공용 부품(신호 표식·담당자 줄)이 화면마다
    다시 쓰인다.
    """
    tokens = [t for t in split_names(ticket.assignee_notion_ids) if t]
    people = [p for p in ((names or {}).get(t) for t in tokens) if p]
    project_names = [n for n in split_names(ticket.project_names) if n]
    return {
        "id": ticket.id,
        "page_id": api_page_id(ticket),
        "key": display_key(ticket),
        "title": ticket.title,
        "status": ticket.status,
        "category": workflow.category_of(ticket.status),
        "priority": ticket.priority,
        "difficulty": ticket.difficulty,
        "due": ticket.due_date.isoformat() if ticket.due_date else None,
        "est_wd": ticket.est_wd,
        "project_uid": ticket.project_uid,
        "project": project_names[0] if project_names else "",
        "assignees": people,
        "assignee_names": [p["display_name"] for p in people if p.get("display_name")],
        "assignee_tokens": len(tokens),
        "issue": bool(ticket.issue_flag),
        "blocked": bool(ticket.blocked_flag),
        "blocked_reason": ticket.blocked_reason,
        "version": ticket.version,
    }


def _bucket(rows: list[dict]) -> dict:
    """논의 목록 한 종류. **자른 사실을 함께 싣는다.**"""
    return {
        "items": rows[:DISCUSS_LIMIT],
        "total": len(rows),
        "truncated": len(rows) > DISCUSS_LIMIT,
    }


def _remaining(ticket: Ticket) -> float:
    """이 티켓이 아직 지고 있는 공수. 끝났으면 0 이다.

    「예상 WD 를 안 적은 티켓」은 0 이 아니라 **모르는 값**이지만, 여기서는 0 으로 센다 —
    합계에 넣을 다른 수가 없기 때문이다. 그 사실은 `workload[].unestimated` 로 따로
    말한다: 「남은 3WD」와 「남은 3WD + 예상 없는 다섯 건」은 회의에서 다른 이야기다.
    """
    if workflow.category_of(ticket.status) in (workflow.CAT_DONE, workflow.CAT_CANCELED):
        return 0.0
    return float(ticket.est_wd or 0)


def _health(*, total: int, done: int, overdue: int, blocked: int, elapsed: float) -> dict | None:
    """회차 한 판의 건강. 0~100 이고, 티켓이 없으면 **None** 이다.

    빈 회차에 100 점을 주면 「아무 일도 안 담긴 회차」가 화면에서 가장 건강해 보인다.
    모르는 것은 모른다고 적는다(`null` 은 0 이 아니다).

    셈은 셋이다. **진도가 시간을 따라가는가**가 본체이고(회차의 60%가 지났으면 60%가
    끝나 있어야 한다), 지연과 차단이 각각 깎는다. 가중치를 더 늘리고 싶어질 때마다,
    이 값이 답하는 질문이 「지금 회의에서 걱정해야 하는가」 하나뿐임을 떠올린다.
    """
    if total <= 0:
        return None
    progress = done / total
    # 아직 안 지난 회차는 진도를 탓하지 않는다 — 첫날의 0% 는 정상이다.
    pace = 100.0 if elapsed <= 0 else min(100.0, 100.0 * progress / max(elapsed, 0.05))
    score = pace - (overdue / total) * 40.0 - (blocked / total) * 25.0
    score = max(0.0, min(100.0, score))
    return {
        "score": round(score, 1),
        "progress_pct": round(progress * 100, 1),
        "elapsed_pct": round(min(max(elapsed, 0.0), 1.0) * 100, 1),
    }


def _sprint_activities(db: Session, sprint: Sprint) -> list[TicketActivity]:
    """이 회차를 드나든 기록 — 시간순. 범위·추이·번다운이 **같은 목록**을 본다."""
    return list(
        db.execute(
            select(TicketActivity)
            .where(
                TicketActivity.kind == ACT_SPRINT,
                (TicketActivity.to_value == sprint.id)
                | (TicketActivity.from_value == sprint.id),
            )
            .order_by(TicketActivity.seq)
        ).scalars().all()
    )


def _spans(
    sprint: Sprint, *, acts: list[TicketActivity], tickets: dict[str, Ticket], ids: set[str]
) -> dict[str, dict]:
    """티켓마다 **언제 이 회차에 있었는가**.

    번다운의 「그날 남은 일」은 지금 담긴 목록만으로는 못 그린다 — 중간에 들어온 티켓은
    첫날에도 있던 것처럼, 빠진 티켓은 처음부터 없던 것처럼 그려진다. 그 둘이 바로 회의가
    묻는 「범위가 얼마나 바뀌었나」라서, 그것을 지우면 그림이 질문에 답하지 않는다.

    기록이 없는 티켓은 **회차 시작부터 있던 것**으로 본다. 실제로 그렇다 — 회차를 만들 때
    담은 티켓은 그 뒤로 움직인 적이 없다.
    """
    start, end = sprint.starts_on, sprint.ends_on
    joined: dict[str, date] = {}
    left: dict[str, date] = {}
    for act in acts:
        when = act.created_at.date() if act.created_at else None
        if when is None:
            continue
        when = max(when, start)
        if act.to_value == sprint.id:
            joined[act.ticket_id] = when
            left.pop(act.ticket_id, None)
        else:
            left[act.ticket_id] = when
    out: dict[str, dict] = {}
    for ticket_id, ticket in tickets.items():
        here = ticket_id in ids
        gone = None if here else left.get(ticket_id)
        if not here and gone is None:
            continue  # 이 회차와 상관없는 티켓
        category = workflow.category_of(ticket.status)
        done_at = None
        if category == workflow.CAT_DONE:
            # 완료 시각의 정본은 `tickets.completed_at` 이다 — 상태를 쓰는 자리 한 곳이
            # 찍고 지운다(`repository_native._stamp_completion`). `updated_at` 은 제목만
            # 고쳐도 움직여서 「그날 끝난 일」이 뒤로 밀린다.
            #
            # 🔴 그 칸이 생기기 **전에** 끝난 티켓은 시각이 없다. 그때는 회차 시작부터
            # 끝나 있던 것으로 본다. 「모르니까 아직 남아 있다」로 세면 오늘의 잔여가
            # 지금 사실(끝났다)과 어긋나고, 그 어긋남은 화면에서 「완료 1건인데 잔여는
            # 안 줄었다」로 보인다 — 둘 중 하나를 골라야 한다면 **오늘이 맞는 쪽**이다.
            done_at = ticket.completed_at.date() if ticket.completed_at else start
        out[ticket_id] = {
            "joined": min(joined.get(ticket_id, start), end),
            "left": gone,
            "est_wd": float(ticket.est_wd or 0),
            "done_at": done_at,
            "canceled": category == workflow.CAT_CANCELED,
        }
    return out


def _scope_changes(
    db: Session,
    sprint: Sprint,
    *,
    ids: set[str],
    acts: list[TicketActivity],
    names: dict[str, dict],
) -> tuple[dict, list[dict]]:
    """회차가 시작한 뒤 들어오고 나간 티켓.

    지금 상태만 봐서는 알 수 없는 값이라 **활동 기록**에서 읽는다. 기록이 없으면
    0 이 아니라 「모른다」다 — 그 구별을 `tracked` 로 적는다.

    돌려주는 줄은 다른 네 갈래와 **같은 모양**(`_row()`)이다. 예전에는 이 갈래만
    `{ticket_id, page_id, key, title, direction, at}` 이라, 같은 카드 부품으로 그리면
    상태·우선순위·담당자·신호가 전부 빈 채로 나왔다.
    """
    # 회차 시작 **전**의 이동은 계획이지 범위 변경이 아니다. 활동은 naive UTC 이고
    # 회차 경계는 달력일이라, 날짜로 비교한다(하루 경계의 몇 시간은 회의에서 무의미하다).
    start = sprint.starts_on
    added, removed = [], []
    for act in acts:
        when = act.created_at.date() if act.created_at else None
        if when is not None and when < start:
            continue
        (added if act.to_value == sprint.id else removed).append(act)
    scope = {
        # 기록이 하나도 없으면 「안 바뀌었다」가 아니라 「모른다」다.
        "tracked": bool(acts),
        "added": len(added),
        "removed": len(removed),
        "trend": _scope_trend(sprint, added=added, removed=removed) if acts else [],
    }
    if not added and not removed:
        return scope, []
    moved_ids = [a.ticket_id for a in added + removed]
    tickets = {
        t.id: t for t in db.execute(select(Ticket).where(Ticket.id.in_(moved_ids))).scalars().all()
    }
    changes = []
    for act in added + removed:
        ticket = tickets.get(act.ticket_id)
        if ticket is None:
            continue
        row = _row(ticket, names=names)
        # 지금 이 회차에 있는가로 방향을 다시 확인한다 — 들어왔다 나간 티켓이
        # 「추가」로도 「제외」로도 세어지면 회의가 같은 티켓을 두 번 본다.
        row["direction"] = "added" if ticket.id in ids else "removed"
        row["at"] = act.created_at.isoformat() if act.created_at else None
        changes.append(row)
    return scope, changes


def _scope_trend(
    sprint: Sprint, *, added: list[TicketActivity], removed: list[TicketActivity]
) -> list[dict]:
    """일자별 **누적** 들어옴·빠짐. 회의가 묻는 것은 「언제부터 불어났나」다.

    새 API 를 만들지 않는다 — 위에서 이미 읽은 같은 기록을 날짜로 접을 뿐이다.
    """
    def _day(act):
        return max(act.created_at.date(), sprint.starts_on) if act.created_at else sprint.starts_on

    into: dict[date, int] = {}
    out: dict[date, int] = {}
    for act in added:
        into[_day(act)] = into.get(_day(act), 0) + 1
    for act in removed:
        out[_day(act)] = out.get(_day(act), 0) + 1
    trend, in_sum, out_sum = [], 0, 0
    for day in _days(sprint):
        in_sum += into.get(day, 0)
        out_sum += out.get(day, 0)
        trend.append({"date": day.isoformat(), "added": in_sum, "removed": out_sum})
    return trend


def _decision_view(row: SprintDecision, *, people: dict[str, dict], keys: dict[str, dict]) -> dict:
    ticket = keys.get(row.ticket_id or "") or {}
    return {
        "id": row.id,
        "kind": row.kind,
        "body": row.body,
        "ticket_id": row.ticket_id,
        "ticket_key": ticket.get("key"),
        "ticket_page_id": ticket.get("page_id"),
        "assignee_user_id": row.assignee_user_id,
        "assignee": people.get(row.assignee_user_id or ""),
        "due_date": row.due_date.isoformat() if row.due_date else None,
        "done": bool(row.done),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def list_decisions(db: Session, sprint_id: str) -> list[dict]:
    """회의록 한 회차분. 적은 순서대로 읽는다."""
    from app.core.people import avatar_map

    rows = db.execute(
        select(SprintDecision)
        .where(SprintDecision.sprint_id == sprint_id)
        .order_by(SprintDecision.created_at, SprintDecision.id)
    ).scalars().all()
    if not rows:
        return []
    user_ids = [r.assignee_user_id for r in rows if r.assignee_user_id]
    users = {
        u.id: u for u in db.execute(select(User).where(User.id.in_(user_ids))).scalars().all()
    } if user_ids else {}
    avatars = avatar_map(db, list(users))
    people = {
        uid: {
            "user_id": uid,
            "display_name": u.display_name or "",
            "avatar_url": (avatars.get(uid) or {}).get("url"),
            "avatar_default_key": (avatars.get(uid) or {}).get("default_key"),
        }
        for uid, u in users.items()
    }
    ticket_ids = [r.ticket_id for r in rows if r.ticket_id]
    keys = {}
    if ticket_ids:
        for t in db.execute(select(Ticket).where(Ticket.id.in_(ticket_ids))).scalars().all():
            keys[t.id] = {"key": display_key(t), "page_id": api_page_id(t)}
    return [_decision_view(r, people=people, keys=keys) for r in rows]


def meeting(db: Session, user: User, *, sprint_id: str, today: date) -> dict:
    """회의 한 판. 위 여섯 질문의 답을 한 번에 조립한다.

    티켓은 **한 번만 읽는다.** 요약·번다운·업무량·논의 목록이 전부 같은 목록을 본다 —
    질문마다 다시 읽으면 회의 중 새로고침 한 번에 질의가 예닐곱 번 난다.
    """
    from app.work import service as work_service

    sprint = work_service.get_scoped_sprint_or_404(db, sprint_id, user)
    # 🔴 **문이 둘이다.** 회차가 보인다고 그 안의 티켓이 다 보이는 것은 아니다.
    #
    # 팀 전체 회차(`project_id IS NULL`)는 조직 안에서 열려 있는데, 거기 담긴 티켓은
    # 여러 프로젝트에 걸린다. 회차 문만 지나고 `WHERE sprint_id = ?` 로 읽으면 그중
    # 내가 못 보는 프로젝트의 제목·담당자·마감이 회의 화면에 그대로 실린다. 판과 백로그가
    # 쓰는 것과 **같은 절**을 쓴다(D-194) — 여기서 새 규칙을 만들지 않는다.
    tickets = db.execute(
        work_service._visible_tickets_stmt(db, user).where(Ticket.sprint_id == sprint.id)
    ).scalars().all()
    tickets = work_service._drop_trashed(db, list(tickets))
    names = work_service._people(db)
    ids = {t.id for t in tickets}

    done = [t for t in tickets if workflow.category_of(t.status) == workflow.CAT_DONE]
    canceled = [t for t in tickets if workflow.category_of(t.status) == workflow.CAT_CANCELED]
    in_progress = [
        t for t in tickets if workflow.category_of(t.status) == workflow.CAT_IN_PROGRESS
    ]
    # 신호는 **아직 안 끝난 일**에만 붙는다. 끝난 티켓의 차단 깃발은 그때 있었던
    # 사실이지 오늘 회의에서 말할 것이 아니다 — 예전에는 그것까지 세어서 「차단 3건」을
    # 눌러 보면 이미 완료된 티켓이 섞여 나왔다.
    live = [t for t in tickets if not workflow.is_terminal(t.status)]
    overdue = [t for t in tickets if workflow.is_overdue(t.due_date, t.status, today=today)]
    blocked = [t for t in live if t.blocked_flag]
    issues = [t for t in live if t.issue_flag]
    unassigned = [t for t in live if not split_names(t.assignee_notion_ids)]
    horizon = today + timedelta(days=DUE_SOON_DAYS)
    due_soon = [
        t for t in tickets
        if t.due_date and today <= t.due_date <= horizon
        and not workflow.is_terminal(t.status)
    ]
    # 회의 준비 — 이 둘이 비어 있으면 번다운도 「담당자별 남은 WD」도 못 그린다.
    # 그림이 안 나온 **뒤에** 그 사실을 알게 되는 대신, 고칠 목록으로 먼저 보여 준다.
    no_estimate = [t for t in live if t.est_wd is None]
    no_due = [t for t in live if t.due_date is None]

    # 담당자별 남은 공수. **한 티켓에 여럿이면 그 수만큼 센다** — 나누면 「반쯤 담당」이
    # 되어 어느 쪽에도 안 걸리고, 회의에서 「이 사람 일이 몇이냐」에 답이 안 나온다.
    load: dict[str, dict] = {}
    for ticket in tickets:
        rest = _remaining(ticket)
        for token in split_names(ticket.assignee_notion_ids):
            person = names.get(token)
            if not person:
                continue
            slot = load.setdefault(
                person["user_id"],
                {**person, "remaining_wd": 0.0, "open": 0, "unestimated": 0},
            )
            if workflow.category_of(ticket.status) not in (
                workflow.CAT_DONE, workflow.CAT_CANCELED
            ):
                slot["open"] += 1
                if ticket.est_wd is None:
                    slot["unestimated"] += 1
            slot["remaining_wd"] = round(slot["remaining_wd"] + rest, 2)
    workload = sorted(load.values(), key=lambda r: (-r["remaining_wd"], r["display_name"]))

    span = (sprint.ends_on - sprint.starts_on).days or 1
    elapsed = (today - sprint.starts_on).days / span

    # 드나든 기록은 **한 번만** 읽는다 — 범위 요약·추이·번다운이 같은 목록을 본다.
    acts = _sprint_activities(db, sprint)
    by_id = {t.id: t for t in tickets}
    gone_ids = {a.ticket_id for a in acts} - set(by_id)
    if gone_ids:
        # 빠져나간 티켓도 **보이는 것만** 싣는다. 회차 문을 지났다고 그 안을 드나든
        # 남의 프로젝트 티켓까지 열리면 안 된다(위 §문이 둘이다 와 같은 이유).
        for row in db.execute(
            work_service._visible_tickets_stmt(db, user).where(Ticket.id.in_(gone_ids))
        ).scalars().all():
            by_id[row.id] = row
    spans = _spans(sprint, acts=acts, tickets=by_id, ids=ids)
    scope, changes = _scope_changes(db, sprint, ids=ids, acts=acts, names=names)

    # 후보는 **실제 백로그 티켓**이다(지시 4). 같은 프로젝트의, 어느 회차에도 안 담긴,
    # 아직 안 끝난 일. 팀 전체 회차(`project_id IS NULL`)면 프로젝트로 안 좁힌다.
    candidates = work_service.backlog(
        db, user, project_id=sprint.project_id or None
    )["items"][:DISCUSS_LIMIT]

    return {
        "sprint": work_service._sprint_view(sprint),
        # 이전·다음 회차. 화면이 목록을 다시 읽어 스스로 찾으면 두 곳의 정렬이 갈린다.
        "neighbours": _neighbours(db, user, sprint),
        "summary": {
            "total": len(tickets),
            "done": len(done),
            "in_progress": len(in_progress),
            "canceled": len(canceled),
            "overdue": len(overdue),
            "issue": len(issues),
            "blocked": len(blocked),
            "remaining_wd": round(sum(_remaining(t) for t in tickets), 2),
            "planned_wd": round(
                sum(float(t.est_wd or 0) for t in tickets if t not in canceled), 2
            ),
        },
        "health": _health(
            total=len(tickets), done=len(done), overdue=len(overdue),
            blocked=len(blocked), elapsed=elapsed,
        ),
        "burndown": _burndown(sprint=sprint, spans=spans, today=today),
        # 회차가 어디쯤인가 — 시작 전 · 진행 중 · 끝난 뒤. 화면이 날짜를 다시 비교하지
        # 않는다(§불변 9: 「오늘」의 정본은 서버다).
        "phase": (
            "before" if today < sprint.starts_on
            else ("after" if today > sprint.ends_on else "during")
        ),
        "workload": workload,
        "scope": scope,
        # 「오늘 논의할 항목」. 단순 목록 하나가 아니라 **유형별**이다 — 지연과 미할당은
        # 회의에서 하는 말이 다르다(하나는 「왜 늦나」, 하나는 「누가 하나」).
        "discuss": {
            "overdue": _bucket([_row(t, names=names) for t in overdue]),
            "blocked": _bucket([_row(t, names=names) for t in blocked]),
            "issue": _bucket([_row(t, names=names) for t in issues]),
            "unassigned": _bucket([_row(t, names=names) for t in unassigned]),
            "due_soon": _bucket([_row(t, names=names) for t in due_soon]),
            "no_estimate": _bucket([_row(t, names=names) for t in no_estimate]),
            "no_due": _bucket([_row(t, names=names) for t in no_due]),
            "scope_changes": _bucket(changes),
        },
        "candidates": candidates,
        "decisions": list_decisions(db, sprint.id),
        "today": today.isoformat(),
    }


def _neighbours(db: Session, user: User, sprint: Sprint) -> dict:
    """같은 프로젝트의 앞뒤 회차. 없으면 `null` 이다.

    범위 판정을 지난 목록에서 고른다 — 여기서 직접 질의하면 안 보이는 회차의 id 가
    「다음 회차」 단추로 새 나간다.
    """
    from app.work import service as work_service

    rows = work_service.list_sprints(db, user, project_id=sprint.project_id)
    ordered = sorted(rows, key=lambda s: (s["starts_on"], s["name"]))
    at = next((i for i, s in enumerate(ordered) if s["id"] == sprint.id), None)
    if at is None:
        return {"prev": None, "next": None}
    return {
        "prev": ordered[at - 1] if at > 0 else None,
        "next": ordered[at + 1] if at + 1 < len(ordered) else None,
    }


#: 번다운 점 개수 상한. 긴 회차에서 점이 수백 개가 되면 선이 뭉갠다.
MAX_POINTS = 32


def _days(sprint: Sprint) -> list[date]:
    """회차 기간의 날짜 — 양끝 포함. 길면 균등 간격으로 솎되 마지막 날은 항상 남긴다."""
    span = (sprint.ends_on - sprint.starts_on).days
    if span < 0:
        return [sprint.starts_on]
    step = 1 if span + 1 <= MAX_POINTS else span // (MAX_POINTS - 1) + 1
    out = [sprint.starts_on + timedelta(days=i) for i in range(0, span + 1, step)]
    if out[-1] != sprint.ends_on:
        out.append(sprint.ends_on)
    return out


def _burndown(*, sprint: Sprint, spans: dict[str, dict], today: date) -> dict:
    """번다운 — **회차 기간 위의 실제 소진**.

    ## 예전 그림이 무엇이었나

    `app/sprints/burndown.py` 는 「그날 이후로 마감이 남아 있는 업무량」의 분포였고,
    그 파일은 그렇게 그리는 이유를 «완료 시각이 어디에도 없다» 로 적어 두었다.
    **그 전제가 더 이상 사실이 아니다.** `tickets.completed_at` 이 상태를 쓰는 자리
    한 곳에서 찍히고 지워진다(`repository_native._stamp_completion`). 그래서 이제는
    「그날 끝에 아직 안 끝난 일이 얼마였나」를 지어내지 않고 **잴 수 있다.**

    ## 선이 셋이다

      ideal      계획선. 첫날의 범위에서 마지막 날 0 까지 곧게 내려간다
      remaining  실제 잔여. **오늘까지만 그린다** — 내일 얼마가 남을지는 아무도 모른다
      scope      그날 이 회차에 담겨 있던 총량. 이 선이 올라가면 범위가 불어난 것이다

    취소한 티켓은 세 선 어디에도 없다 — 「안 하기로 한 일」은 남은 일도 끝낸 일도 아니다.
    마감일이 없는 티켓도 **센다.** 예전 그림은 마감일이 축이라 그것들을 통째로 뺐고,
    그래서 같은 화면의 「남은 WD」와 그림의 총량이 서로 다른 값이었다.
    """
    live = [s for s in spans.values() if not s["canceled"]]
    days = _days(sprint)

    def _in(span, day):
        return span["joined"] <= day and (span["left"] is None or span["left"] > day)

    start_scope = round(sum(s["est_wd"] for s in live if _in(s, sprint.starts_on)), 1)
    total = round(sum(s["est_wd"] for s in live), 1)
    span_days = (sprint.ends_on - sprint.starts_on).days or 1

    points = []
    for day in days:
        scope = sum(s["est_wd"] for s in live if _in(s, day))
        elapsed = (day - sprint.starts_on).days / span_days
        ideal = start_scope * max(0.0, 1.0 - elapsed)
        point = {
            "date": day.isoformat(),
            "ideal": round(ideal, 1),
            "scope": round(scope, 1),
            "remaining": None,
        }
        if day <= today:
            done = s = 0.0
            for span in live:
                if not _in(span, day):
                    continue
                if span["done_at"] is not None and span["done_at"] <= day:
                    done += span["est_wd"]
                else:
                    s += span["est_wd"]
            point["remaining"] = round(s, 1)
            point["done"] = round(done, 1)
        points.append(point)
    return {"total_est_wd": total, "start_est_wd": start_scope, "points": points}


# ── 회의록 쓰기 ──────────────────────────────────────────────────────────────


def add_decision(
    db: Session,
    user: User,
    *,
    sprint_id: str,
    kind: str,
    body: str,
    ticket_id: str | None = None,
    assignee_user_id: str | None = None,
    due_date: date | None = None,
    now=None,
) -> dict:
    """회의록 한 줄. 회차가 보이는 사람이면 적을 수 있다.

    적는 것을 역할로 막지 않는다 — 회의에 앉은 사람이 곧 적는 사람이고, 「기록은
    관리자만」이면 회의가 끝난 뒤 아무도 안 적는다. 대신 고칠 수 있는 사람은 좁다
    (`_editable_or_403`).

    걸어 두는 티켓은 **보이는 티켓**이어야 한다. 안 그러면 없는 티켓 id 를 넣어 보며
    「그 id 는 있다」를 알아낼 수 있다.
    """
    from app.work import service as work_service

    sprint = work_service.get_scoped_sprint_or_404(db, sprint_id, user)
    text = (body or "").strip()
    if not text:
        raise ValidationAppError("내용을 적어 주세요.")
    if len(text) > DECISION_BODY_MAX:
        raise ValidationAppError(f"내용은 {DECISION_BODY_MAX}자를 넘을 수 없습니다.")
    if kind not in DECISION_KINDS:
        raise ValidationAppError("알 수 없는 종류입니다.")
    if ticket_id:
        ticket = work_service.load_ticket_in_scope_or_404(db, ticket_id, user)
        ticket_id = ticket.id
    if assignee_user_id:
        # 담당은 **활성 사용자**여야 한다. 퇴사자에게 할 일을 걸면 그 줄은 영원히 안 닫힌다.
        target = db.get(User, assignee_user_id)
        if target is None or not target.active or target.archived_at is not None:
            raise ValidationAppError("담당자를 찾을 수 없습니다.")
    row = SprintDecision(
        sprint_id=sprint.id,
        kind=kind,
        body=text,
        ticket_id=ticket_id or None,
        assignee_user_id=assignee_user_id or None,
        due_date=due_date,
        done=False,
        author_user_id=user.id,
        created_at=now or utcnow(),
        updated_at=now or utcnow(),
    )
    db.add(row)
    # **커밋하지 않는다.** 요청 하나가 한 트랜잭션이고 그 커밋은 `get_db` 가 맨 끝에 한다
    # (`app/core/deps.py`). 여기서 먼저 커밋하면 뒤이어 남기는 감사 기록이 실패해도 이
    # 줄만 살아남아, 「누가 적었는지 모르는 회의록」이 생긴다. 나머지 쓰기 경로도 전부
    # `flush` 까지만 한다(`app/work/service.py`).
    db.flush()
    new_id = row.id
    return next(d for d in list_decisions(db, sprint.id) if d["id"] == new_id)


def _editable_or_403(db: Session, user: User, decision_id: str) -> SprintDecision:
    """고치고 지울 수 있는 사람 — 적은 사람, 걸린 담당자, 운영/관리자군.

    회의록은 여러 사람이 함께 보는 글이라 아무나 고치면 「누가 바꿨나」가 사라지고,
    저자만 고칠 수 있으면 그 사람이 자리에 없는 날 오탈자 하나를 못 고친다.

    앞에 문이 하나 더 있다: **회차가 안 보이면 그 회의록도 없는 것으로 본다.** 목록과
    같은 판정이라, 안 보이는 회차의 회의록 id 를 찍어 보며 존재를 알아낼 수 없다.
    """
    from app.core.authz import MODERATOR_ROLES
    from app.work import service as work_service

    row = db.get(SprintDecision, decision_id)
    if row is None:
        raise NotFoundError("회의 기록을 찾을 수 없습니다.")
    work_service.get_scoped_sprint_or_404(db, row.sprint_id, user)
    if user.role in MODERATOR_ROLES:
        return row
    if user.id in (row.author_user_id, row.assignee_user_id):
        return row
    raise ForbiddenError("이 기록을 고칠 권한이 없습니다.")


def update_decision(
    db: Session, user: User, *, decision_id: str, changes: dict, now=None
) -> dict:
    """회의록 한 줄을 고친다. `done` 만 바꾸는 것이 가장 흔한 쓰임이다."""
    row = _editable_or_403(db, user, decision_id)
    if "body" in changes:
        text = (changes["body"] or "").strip()
        if not text:
            raise ValidationAppError("내용을 적어 주세요.")
        if len(text) > DECISION_BODY_MAX:
            raise ValidationAppError(f"내용은 {DECISION_BODY_MAX}자를 넘을 수 없습니다.")
        row.body = text
    if "done" in changes:
        row.done = bool(changes["done"])
    if "due_date" in changes:
        row.due_date = changes["due_date"]
    if "assignee_user_id" in changes:
        target_id = changes["assignee_user_id"] or None
        if target_id:
            target = db.get(User, target_id)
            if target is None or not target.active or target.archived_at is not None:
                raise ValidationAppError("담당자를 찾을 수 없습니다.")
        row.assignee_user_id = target_id
    row.updated_at = now or utcnow()
    db.flush()
    return next(d for d in list_decisions(db, row.sprint_id) if d["id"] == row.id)


def delete_decision(db: Session, user: User, *, decision_id: str) -> None:
    """회의록 한 줄을 지운다. 고칠 수 있는 사람과 **같은 사람**이다."""
    row = _editable_or_403(db, user, decision_id)
    db.delete(row)
    db.flush()


__all__ = [
    "DECISION_BODY_MAX", "DECISION_KIND_ACTION", "DECISION_KIND_DECISION",
    "DISCUSS_LIMIT", "DUE_SOON_DAYS",
    "add_decision", "delete_decision", "list_decisions", "meeting", "update_decision",
]
