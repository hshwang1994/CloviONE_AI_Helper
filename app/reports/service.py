"""개발자 월간 리포트 집계 (spec: 개발자 리포트).

티켓은 TicketRepository(로컬 미러 우선)에서 읽는다 — 소스가 Notion 인지 자체 DB 인지 여기서는
모른다. 담당자는 소스에서 불투명한 user-id 로만 오므로, 앱의 user_notion_mappings 로 사람 이름과
앱 user_id 를 해석한다(해석 브리지는 앱 DB 에만 있다). 이번 달 마감 티켓이 없는 활성 사용자도
0으로 포함해, 리포트가 팀 전원을 보여준다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.notion_mapping.models import UserNotionMapping
from app.users.models import User

STATUS_DONE = "완료"
STATUS_CANCELLED = "취소"
_IN_PROGRESS = {"진행", "검증", "이슈"}
UNKNOWN_ASSIGNEE_NAME = "(미확인 담당자)"
_UNKNOWN_NAME = UNKNOWN_ASSIGNEE_NAME  # 하위 호환 별칭(내부 사용)


def month_range(period: str) -> tuple[str, str]:
    """'YYYY-MM' → (첫날 ISO, 다음 달 첫날 ISO). end 는 배타적."""
    year_s, _, month_s = period.partition("-")
    year, month = int(year_s), int(month_s)
    if not (1 <= month <= 12):
        raise ValueError("월은 1~12 사이여야 합니다.")
    start = f"{year:04d}-{month:02d}-01"
    if month == 12:
        end = f"{year + 1:04d}-01-01"
    else:
        end = f"{year:04d}-{month + 1:02d}-01"
    return start, end


@dataclass(frozen=True)
class DisplayMaps:
    """활성 사용자 기준 표시 이름/식별자 해석표.

    name_to_user 를 함께 두는 이유: 리포트가 담당자를 **표시 이름으로 묶어** 왔는데, 동명이인이
    생기면 두 사람이 한 줄로 합쳐지고 부서 스코핑도 걸 수 없다. 지금은 묶는 키는 그대로 두되
    (응답 계약 유지) 각 행에 user_id 를 실어 앞으로 이름 대신 그 값을 쓸 수 있게 한다.
    """

    id_to_name: dict[str, str] = field(default_factory=dict)   # 소스 user id → 표시 이름
    id_to_user: dict[str, str] = field(default_factory=dict)   # 소스 user id → 앱 user_id
    name_to_user: dict[str, str] = field(default_factory=dict)  # 표시 이름 → 앱 user_id(첫 사람)
    active_names: list[str] = field(default_factory=list)


def load_display_maps(db: Session) -> DisplayMaps:
    """활성 사용자 한 번 조회로 이름·식별자 해석표를 만든다."""
    rows = db.execute(
        select(User.id, User.display_name, UserNotionMapping.notion_user_id)
        .outerjoin(UserNotionMapping, UserNotionMapping.user_id == User.id)
        .where(User.active.is_(True), User.archived_at.is_(None))
    ).all()
    id_to_name: dict[str, str] = {}
    id_to_user: dict[str, str] = {}
    name_to_user: dict[str, str] = {}
    active_names: list[str] = []
    for user_id, display_name, notion_id in rows:
        active_names.append(display_name)
        name_to_user.setdefault(display_name, user_id)
        if notion_id:
            id_to_name[notion_id] = display_name
            id_to_user[notion_id] = user_id
    return DisplayMaps(
        id_to_name=id_to_name, id_to_user=id_to_user,
        name_to_user=name_to_user, active_names=sorted(set(active_names)),
    )


def _load_name_map(db: Session) -> tuple[dict[str, str], list[str]]:
    """(notion_user_id → 이름, 활성 사용자 이름 목록). load_display_maps 의 얇은 래퍼다.

    이름 목록은 이번 달 티켓이 없는 사람도 리포트에 0으로 넣기 위한 것이다.
    """
    maps = load_display_maps(db)
    return maps.id_to_name, maps.active_names


def _blank_dev(user_id: str | None = None) -> dict:
    return {
        "user_id": user_id,
        "done": 0, "prog": 0, "verify": 0, "plan": 0, "cancel": 0,
        "assigned": 0, "overdue": 0,
        "est_done": 0.0, "est_all": 0.0, "act_done": 0.0,
        "_diff_sum": 0, "_diff_n": 0,
        "_tickets": [],
    }


def _ticket_detail(t, *, overdue: bool) -> dict:
    """담당자별 상세 목록에 담을 티켓 한 건. 내용을 자세히 담되 민감 정보는 없다."""
    return {
        "tid": t.number,
        "title": t.title or "(제목 없음)",
        "status": t.status,
        "due": t.due,
        "est_wd": t.est_wd,
        "act_wd": t.act_wd,
        "difficulty": t.difficulty,
        "priority": t.priority,
        "url": t.url,
        "overdue": overdue,
    }


def _bump(bucket: dict, ticket, *, overdue: bool) -> None:
    status = ticket.status
    est = ticket.est_wd or 0
    act = ticket.act_wd or 0
    diff = ticket.difficulty
    bucket["assigned"] += 1
    if status == STATUS_DONE:
        bucket["done"] += 1
        bucket["est_done"] += est
        bucket["act_done"] += act
    elif status == STATUS_CANCELLED:
        bucket["cancel"] += 1
    elif status == "진행" or status == "이슈":
        bucket["prog"] += 1
    elif status == "검증":
        bucket["verify"] += 1
    elif status == "계획":
        bucket["plan"] += 1
    if status != STATUS_CANCELLED:
        bucket["est_all"] += est
        if diff and str(diff).isdigit():
            bucket["_diff_sum"] += int(diff)
            bucket["_diff_n"] += 1
    if overdue:
        bucket["overdue"] += 1
    bucket["_tickets"].append(_ticket_detail(ticket, overdue=overdue))


# 상세 목록 정렬: 마감일 빠른 순, 없으면 뒤로, 같으면 티켓 번호 순.
def _ticket_sort_key(t: dict):
    return (t.get("due") or "9999-99-99", t.get("tid") or 0)


def _finalize_dev(name: str, b: dict, *, has_tickets: bool) -> dict:
    net = b["assigned"] - b["cancel"]
    rate = round(100 * b["done"] / net) if net > 0 else None
    diff_avg = round(b["_diff_sum"] / b["_diff_n"], 1) if b["_diff_n"] else None
    return {
        "name": name,
        # 지금은 묶는 키가 여전히 표시 이름이지만, 각 행에 앱 user_id 를 실어 둔다 —
        # 동명이인이 한 줄로 합쳐지는 문제와 부서 스코핑이 이 값을 필요로 한다.
        "user_id": b.get("user_id"),
        "done": b["done"], "prog": b["prog"], "verify": b["verify"],
        "plan": b["plan"], "cancel": b["cancel"], "assigned": b["assigned"],
        "overdue": b["overdue"],
        "completion_rate": rate,
        "est_done": round(b["est_done"], 1),
        "est_all": round(b["est_all"], 1),
        "act_done": round(b["act_done"], 1),
        "difficulty_avg": diff_avg,
        "has_tickets": has_tickets,
        "tickets": sorted(b["_tickets"], key=_ticket_sort_key),
    }


def build_period_report(
    db: Session, outbound, settings, *, start: str, end: str, today: date,
    tickets=None, repo=None,
) -> dict:
    """마감일이 [start, end) 인 티켓을 담당자별로 집계한다(월간 리포트·스프린트 회의 공용 코어).
    반환에 period 는 없다 — 월간 래퍼(build_dev_monthly_report)가 period 를 덧붙인다.

    tickets 를 주면 그 목록을 그대로 쓴다 — 스프린트 요약이 같은 범위를 두 번 읽지 않게 하려는
    것이다(실시간 소스일 때 왕복이 그대로 비용이다)."""
    if tickets is None:
        from app.tickets.service import list_period_tickets

        tickets = list_period_tickets(db, outbound, settings, start=start, end=end, repo=repo)
    maps = load_display_maps(db)
    id_to_name, active_names = maps.id_to_name, maps.active_names
    today_iso = today.isoformat()

    devs: dict[str, dict] = {}
    unassigned = {"done": 0, "prog": 0, "verify": 0, "plan": 0, "cancel": 0, "total": 0}
    # 팀 합계는 티켓 단위(중복 없이)로 센다. 담당자별 합은 다중 담당 티켓을 양쪽에 세므로 팀 합계와 다르다.
    team = {"total": 0, "done": 0, "in_progress": 0, "verify": 0, "plan": 0, "cancel": 0,
            "overdue": 0, "est_done_total": 0.0, "est_all_total": 0.0}

    for t in tickets:
        status = t.status
        est = t.est_wd or 0
        overdue = bool(t.due) and t.due < today_iso and status not in (STATUS_DONE, STATUS_CANCELLED)

        team["total"] += 1
        if status == STATUS_DONE:
            team["done"] += 1
            team["est_done_total"] += est
        elif status == STATUS_CANCELLED:
            team["cancel"] += 1
        elif status == "검증":
            team["verify"] += 1
        elif status in _IN_PROGRESS:  # 진행, 이슈 (검증은 위에서 분리)
            team["in_progress"] += 1
        elif status == "계획":
            team["plan"] += 1
        if status != STATUS_CANCELLED:
            team["est_all_total"] += est
        if overdue:
            team["overdue"] += 1

        if not t.assignee_ids:
            unassigned["total"] += 1
            if status == STATUS_DONE:
                unassigned["done"] += 1
            elif status == STATUS_CANCELLED:
                unassigned["cancel"] += 1
            elif status in _IN_PROGRESS:
                unassigned["prog" if status != "검증" else "verify"] += 1
            elif status == "계획":
                unassigned["plan"] += 1
            continue

        for aid in t.assignee_ids:
            name = id_to_name.get(aid, _UNKNOWN_NAME)
            _bump(devs.setdefault(name, _blank_dev(maps.id_to_user.get(aid))), t, overdue=overdue)

    # 활성 사용자 전원을 포함한다(이번 달 티켓이 없으면 0).
    for name in active_names:
        devs.setdefault(name, _blank_dev(maps.name_to_user.get(name)))

    rows = [
        _finalize_dev(name, b, has_tickets=b["assigned"] > 0)
        for name, b in devs.items()
    ]
    # 완료 건수 내림차순, 같으면 담당 건수 내림차순, 같으면 이름순.
    rows.sort(key=lambda r: (-r["done"], -r["assigned"], r["name"]))

    return {
        "range": {"start": start, "end_exclusive": end},
        "team": {
            "total": team["total"],
            "done": team["done"],
            "in_progress": team["in_progress"],
            "verify": team["verify"],
            "plan": team["plan"],
            "cancel": team["cancel"],
            "overdue": team["overdue"],
            "est_done_total": round(team["est_done_total"], 1),
            "est_all_total": round(team["est_all_total"], 1),
        },
        "developers": rows,
        "unassigned": unassigned,
    }


def build_dev_monthly_report(
    db: Session, outbound, settings, *, period: str, today: date, repo=None
) -> dict:
    """개발자 월간 리포트 — 'YYYY-MM' 달을 날짜 범위로 바꿔 build_period_report 에 위임하고 period 를 덧붙인다."""
    start, end = month_range(period)
    report = build_period_report(
        db, outbound, settings, start=start, end=end, today=today, repo=repo
    )
    return {"period": period, **report}
