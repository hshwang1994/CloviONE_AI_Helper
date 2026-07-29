"""개발자 월간 리포트 집계 (spec: 개발자 리포트).

Notion "작업" DB에서 읽은 원시 티켓을 담당자별로 집계한다. 담당자는 Notion에서 불투명한
user-id 로만 오므로, 앱의 user_notion_mappings 로 사람 이름을 해석한다(이름 해석 브리지는
앱 DB 에만 있다). 이번 달 마감 티켓이 없는 활성 사용자도 0으로 포함해, 리포트가 팀 전원을 보여준다.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.notion_mapping.models import UserNotionMapping
from app.reports import notion_source
from app.users.models import User

STATUS_DONE = "완료"
STATUS_CANCELLED = "취소"
_IN_PROGRESS = {"진행", "검증", "이슈"}
_UNKNOWN_NAME = "(미확인 담당자)"


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


def _load_name_map(db: Session) -> tuple[dict[str, str], list[str]]:
    """(notion_user_id → 이름, 활성 사용자 이름 목록) 을 돌려준다.

    이름 목록은 이번 달 티켓이 없는 사람도 리포트에 0으로 넣기 위한 것이다.
    """
    rows = db.execute(
        select(User.display_name, UserNotionMapping.notion_user_id)
        .outerjoin(UserNotionMapping, UserNotionMapping.user_id == User.id)
        .where(User.active.is_(True), User.archived_at.is_(None))
    ).all()
    id_to_name: dict[str, str] = {}
    active_names: list[str] = []
    for display_name, notion_id in rows:
        active_names.append(display_name)
        if notion_id:
            id_to_name[notion_id] = display_name
    return id_to_name, sorted(set(active_names))


def _blank_dev() -> dict:
    return {
        "done": 0, "prog": 0, "verify": 0, "plan": 0, "cancel": 0,
        "assigned": 0, "overdue": 0,
        "est_done": 0.0, "est_all": 0.0, "act_done": 0.0,
        "_diff_sum": 0, "_diff_n": 0,
        "_tickets": [],
    }


def _ticket_detail(t: dict, *, overdue: bool) -> dict:
    """담당자별 상세 목록에 담을 티켓 한 건. 내용을 자세히 담되 민감 정보는 없다."""
    return {
        "tid": t.get("tid"),
        "title": t.get("title") or "(제목 없음)",
        "status": t.get("status"),
        "due": t.get("due"),
        "est_wd": t.get("est_wd"),
        "act_wd": t.get("act_wd"),
        "difficulty": t.get("difficulty"),
        "priority": t.get("priority"),
        "url": t.get("url"),
        "overdue": overdue,
    }


def _bump(bucket: dict, ticket: dict, *, overdue: bool) -> None:
    status = ticket["status"]
    est = ticket["est_wd"] or 0
    act = ticket["act_wd"] or 0
    diff = ticket["difficulty"]
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


def build_dev_monthly_report(
    db: Session, outbound, settings, *, period: str, today: date
) -> dict:
    start, end = month_range(period)
    tickets = notion_source.query_tasks_for_period(
        outbound, settings, start_date=start, end_date=end
    )
    id_to_name, active_names = _load_name_map(db)
    today_iso = today.isoformat()

    devs: dict[str, dict] = {}
    unassigned = {"done": 0, "prog": 0, "verify": 0, "plan": 0, "cancel": 0, "total": 0}
    # 팀 합계는 티켓 단위(중복 없이)로 센다. 담당자별 합은 다중 담당 티켓을 양쪽에 세므로 팀 합계와 다르다.
    team = {"total": 0, "done": 0, "in_progress": 0, "plan": 0, "cancel": 0,
            "overdue": 0, "est_done_total": 0.0, "est_all_total": 0.0}

    for t in tickets:
        status = t["status"]
        est = t["est_wd"] or 0
        overdue = bool(t["due"]) and t["due"] < today_iso and status not in (STATUS_DONE, STATUS_CANCELLED)

        team["total"] += 1
        if status == STATUS_DONE:
            team["done"] += 1
            team["est_done_total"] += est
        elif status == STATUS_CANCELLED:
            team["cancel"] += 1
        elif status in _IN_PROGRESS:
            team["in_progress"] += 1
        elif status == "계획":
            team["plan"] += 1
        if status != STATUS_CANCELLED:
            team["est_all_total"] += est
        if overdue:
            team["overdue"] += 1

        if not t["assignees"]:
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

        for aid in t["assignees"]:
            name = id_to_name.get(aid, _UNKNOWN_NAME)
            _bump(devs.setdefault(name, _blank_dev()), t, overdue=overdue)

    # 활성 사용자 전원을 포함한다(이번 달 티켓이 없으면 0).
    for name in active_names:
        devs.setdefault(name, _blank_dev())

    rows = [
        _finalize_dev(name, b, has_tickets=b["assigned"] > 0)
        for name, b in devs.items()
    ]
    # 완료 건수 내림차순, 같으면 담당 건수 내림차순, 같으면 이름순.
    rows.sort(key=lambda r: (-r["done"], -r["assigned"], r["name"]))

    return {
        "period": period,
        "range": {"start": start, "end_exclusive": end},
        "team": {
            "total": team["total"],
            "done": team["done"],
            "in_progress": team["in_progress"],
            "plan": team["plan"],
            "cancel": team["cancel"],
            "overdue": team["overdue"],
            "est_done_total": round(team["est_done_total"], 1),
            "est_all_total": round(team["est_all_total"], 1),
        },
        "developers": rows,
        "unassigned": unassigned,
    }
