"""개발자 월간 리포트 집계 (spec: 개발자 리포트, 계획 3.7).

## 두 축

- **마감일 축**(담당 · 완료율 · 지연): 마감일이 그 달 안인 티켓. 사용자가 정한 기준이다.
- **완료일 축**(이 달에 끝낸 일): `completed_at` 이 그 달(KST) 안인 티켓. 마감일이 없거나 다른
  달인 티켓도 끝낸 달에 잡힌다.
- 마감일이 없는 **열린** 티켓은 어느 달의 마감일 축에도 안 들어가므로 따로 센다(`no_due`, 지금 기준).
- 완료 상태인데 끝낸 날짜를 모르는 티켓(이관 데이터)은 완료일 축에 못 넣으므로 그 수를 따로 준다.

## 사람은 id 로 묶는다

예전에는 표시 이름으로 묶어 동명이인이 한 줄로 합쳐졌고, 비활성 · 보관 계정의 티켓은 전부
"(미확인 담당자)" 로 뭉쳤다. 이제 담당자 토큰을 **모든** 계정(비활성 · 보관 포함)의 id 로 풀고
(`load_assignee_directory`), 한 티켓 안에서 같은 사람으로 풀리는 토큰(옛 id + 자기 id)은 한 번만 센다.
풀리지 않는 토큰만 "(미확인 담당자)" 한 줄로 모은다. 같은 이름이 두 줄이면 `ambiguous_name` 을
켜서 화면이 이메일을 붙인다.

## 칸은 언제나 합이 맞는다

상태는 일곱 칸(완료 · 진행 · 검증 · 계획 · 보류 · 취소 · 기타)으로 나누고 `assigned` 는 그 합이다.
모르는 상태는 조용히 빠지지 않고 '기타' 로 간다. 비율 반올림은 이 파일의 `pct` 한 곳이다(0.5 는
올린다) - 화면은 계산하지 않고 서버가 준 값과 정의 문장(`definitions`)을 그대로 쓴다.

휴지통 티켓은 세지 않는다(`NativeTicketRepository.list_for_period` 가 거른다).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.notion_mapping.models import UserNotionMapping
from app.users.models import User
from app.work import workflow

STATUS_DONE = "완료"
STATUS_CANCELLED = "취소"
STATUS_HOLD = "보류"
STATUS_VERIFY = "검증"
UNKNOWN_ASSIGNEE_NAME = "(미확인 담당자)"
_UNKNOWN_NAME = UNKNOWN_ASSIGNEE_NAME  # 하위 호환 별칭(내부 사용)
UNKNOWN_KEY = "unknown"

BUCKETS = ("done", "prog", "verify", "plan", "hold", "cancel", "other")

STATE_ACTIVE = "active"
STATE_INACTIVE = "inactive"
STATE_ARCHIVED = "archived"

# 화면이 열 도움말로 그대로 쓰는 계산 정의(계획 3.7). 숫자와 문장이 따로 놀지 않도록 한 곳에 둔다.
DEFINITIONS = {
    "assigned": "마감일이 이 달인 티켓 중 이 사람이 담당한 수입니다. 한 티켓에 여러 사람이 있으면 사람마다 셉니다.",
    "completion_rate": "완료를 담당에서 취소를 뺀 수로 나눠 100을 곱하고 반올림합니다.",
    "overdue": "마감일이 오늘보다 앞인데 완료나 취소가 아닌 티켓입니다.",
    "other": "제품에 없는 상태 값을 가진 티켓입니다. 이관 데이터에서 나옵니다.",
    "completed_done": "끝낸 날짜가 이 달인 완료 티켓입니다. 마감일과 관계없이 끝낸 달에 셉니다.",
    "late_done": "이 달에 끝낸 티켓 중 끝낸 날짜가 마감일보다 뒤인 티켓입니다.",
    "no_due_open": "마감일이 없는 열린 티켓입니다. 어느 달의 마감일 기준에도 들어가지 않아 지금 기준으로 따로 셉니다.",
    "completed_unknown_date": "완료 상태인데 끝낸 날짜를 모르는 티켓입니다. 완료일 기준에 넣을 수 없습니다.",
    "estimate_accuracy_pct": "완료한 티켓의 실제 WD 합을 예상 WD 합으로 나눠 100을 곱하고 반올림합니다. 100보다 크면 예상보다 오래 걸린 것입니다.",
}


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


def pct(num, den) -> int | None:
    """비율(%)을 정수로. 반올림은 **0.5 를 올린다** - 파이썬 `round` 는 짝수 쪽으로 보내서
    (banker's rounding) 같은 12.5% 가 서버에서 12, 화면에서 13 이 됐다."""
    if not den:
        return None
    value = Decimal(num) * Decimal(100) / Decimal(den)
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _round1(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def bucket_of(status: str | None) -> str:
    """상태 → 칸. 어휘의 정본(`workflow`)을 따른다. 모르는 값은 '기타' 다."""
    if status == STATUS_VERIFY:
        return "verify"
    if status == STATUS_HOLD:
        return "hold"
    category = workflow.category_of(status)
    if category == workflow.CAT_DONE:
        return "done"
    if category == workflow.CAT_CANCELED:
        return "cancel"
    if category == workflow.CAT_IN_PROGRESS:
        return "prog"
    if category == workflow.CAT_OPEN:
        return "plan"
    return "other"


# ── 담당자 해석 ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DisplayMaps:
    """활성 사용자 기준 표시 이름/식별자 해석표(검색 색인 · 작업 보드가 쓴다)."""

    id_to_name: dict[str, str] = field(default_factory=dict)   # 담당자 토큰 → 표시 이름
    id_to_user: dict[str, str] = field(default_factory=dict)   # 담당자 토큰 → 앱 user_id
    name_to_user: dict[str, str] = field(default_factory=dict)  # 표시 이름 → 앱 user_id(첫 사람)
    active_names: list[str] = field(default_factory=list)


def load_display_maps(db: Session) -> DisplayMaps:
    """활성 사용자 한 번 조회로 이름·식별자 해석표를 만든다.

    키는 **담당자 토큰**이다(`app/tickets/service.py::assignee_token`) — 옛 소스의 user id
    와 **자기 user id** 를 함께 받는다. 리포트는 비활성 계정까지 푸는 `load_assignee_directory`
    를 쓴다. 이 함수는 활성 사용자만 보는 화면(검색 색인 · 작업 보드)의 몫이다.
    """
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
        id_to_name.setdefault(user_id, display_name)
        id_to_user.setdefault(user_id, user_id)
    return DisplayMaps(
        id_to_name=id_to_name, id_to_user=id_to_user,
        name_to_user=name_to_user, active_names=sorted(set(active_names)),
    )


def _load_name_map(db: Session) -> tuple[dict[str, str], list[str]]:
    """(담당자 토큰 → 이름, 활성 사용자 이름 목록). `load_display_maps` 의 얇은 래퍼다(티켓 화면이 쓴다)."""
    maps = load_display_maps(db)
    return maps.id_to_name, maps.active_names


@dataclass(frozen=True)
class Person:
    user_id: str
    name: str
    email: str
    department: str | None
    state: str


@dataclass(frozen=True)
class AssigneeDirectory:
    by_token: dict[str, Person]
    active_ids: tuple[str, ...]

    def person_ids(self, tokens) -> tuple[set[str], bool]:
        """토큰들 → 사람 id 집합, 그리고 풀리지 않은 토큰이 있었는가."""
        ids: set[str] = set()
        unknown = False
        for token in tokens or ():
            person = self.by_token.get(token)
            if person is None:
                unknown = True
            else:
                ids.add(person.user_id)
        return ids, unknown

    def person(self, user_id: str) -> Person | None:
        return self.by_token.get(user_id)


def load_assignee_directory(db: Session) -> AssigneeDirectory:
    """**모든** 계정(비활성 · 보관 포함)의 토큰 → 사람. 부서 이름도 함께 붙인다."""
    from app.org.models import Department

    rows = db.execute(
        select(
            User.id, User.display_name, User.email, User.active, User.archived_at,
            Department.name, UserNotionMapping.notion_user_id,
        )
        .outerjoin(Department, Department.id == User.department_id)
        .outerjoin(UserNotionMapping, UserNotionMapping.user_id == User.id)
    ).all()
    by_token: dict[str, Person] = {}
    active: set[str] = set()
    for user_id, name, email, is_active, archived_at, dept, notion_id in rows:
        state = STATE_ARCHIVED if archived_at is not None else (STATE_ACTIVE if is_active else STATE_INACTIVE)
        person = by_token.get(user_id) or Person(user_id, name or "", email or "", dept, state)
        by_token[user_id] = person
        if notion_id:
            by_token.setdefault(notion_id, person)
        if state == STATE_ACTIVE:
            active.add(user_id)
    return AssigneeDirectory(by_token=by_token, active_ids=tuple(sorted(active)))


# ── 마감일 축 ─────────────────────────────────────────────────────────────────


def _blank_dev(user_id: str | None = None) -> dict:
    return {
        "user_id": user_id,
        **{b: 0 for b in BUCKETS},
        "assigned": 0, "overdue": 0,
        "est_done": 0.0, "est_all": 0.0, "act_done": 0.0,
        "_diff_sum": 0, "_diff_n": 0,
        "_tickets": [],
    }


def _ticket_detail(t, *, overdue: bool) -> dict:
    """담당자별 상세 목록에 담을 티켓 한 건. 내용을 자세히 담되 민감 정보는 없다."""
    return {
        # 목록 행 키. 자체 티켓은 번호(`tid`)가 없을 수 있어 행 id 를 함께 준다.
        "uid": t.uid or t.page_id,
        "tid": t.number,
        "key": t.key,
        "title": t.title or "(제목 없음)",
        "status": t.status,
        "due": t.due,
        "est_wd": t.est_wd,
        "act_wd": t.act_wd,
        "difficulty": t.difficulty,
        "priority": t.priority,
        # `url` 은 여기 없다 - 티켓 목록·상세와 같은 이유로 걷었다(옛 Notion 주소).
        "overdue": overdue,
    }


def _bump(bucket: dict, ticket, *, overdue: bool) -> None:
    status = ticket.status
    est = ticket.est_wd or 0
    act = ticket.act_wd or 0
    diff = ticket.difficulty
    kind = bucket_of(status)
    bucket["assigned"] += 1
    bucket[kind] += 1
    if kind == "done":
        bucket["est_done"] += est
        bucket["act_done"] += act
    if kind != "cancel":
        bucket["est_all"] += est
        if diff and str(diff).isdigit():
            bucket["_diff_sum"] += int(diff)
            bucket["_diff_n"] += 1
    if overdue:
        bucket["overdue"] += 1
    bucket["_tickets"].append(_ticket_detail(ticket, overdue=overdue))


# 상세 목록 정렬: 마감일 빠른 순, 없으면 뒤로, 같으면 티켓 번호 순, 그래도 같으면 행 id.
def _ticket_sort_key(t: dict):
    return (t.get("due") or "9999-99-99", t.get("tid") or 0, t.get("uid") or "")


def _finalize_dev(person: Person | None, b: dict, *, has_tickets: bool) -> dict:
    net = b["assigned"] - b["cancel"]
    diff_avg = _round1(b["_diff_sum"] / b["_diff_n"]) if b["_diff_n"] else None
    return {
        "name": person.name if person else UNKNOWN_ASSIGNEE_NAME,
        "user_id": person.user_id if person else None,
        "kind": "person" if person else UNKNOWN_KEY,
        "email": person.email if person else None,
        "department": person.department if person else None,
        "state": person.state if person else None,
        "ambiguous_name": False,
        **{k: b[k] for k in BUCKETS},
        "assigned": b["assigned"],
        "overdue": b["overdue"],
        "completion_rate": pct(b["done"], net) if net > 0 else None,
        "est_done": _round1(b["est_done"]),
        "est_all": _round1(b["est_all"]),
        "act_done": _round1(b["act_done"]),
        "act_per_done": _round1(b["act_done"] / b["done"]) if b["done"] else None,
        "estimate_accuracy_pct": pct(b["act_done"], b["est_done"]) if b["est_done"] and b["act_done"] else None,
        "difficulty_avg": diff_avg,
        "has_tickets": has_tickets,
        "tickets": sorted(b["_tickets"], key=_ticket_sort_key),
    }


def _visible(directory: AssigneeDirectory, ticket, visible_user_ids) -> bool:
    if visible_user_ids is None:
        return True
    from app.core.scope import any_assignee_visible

    ids, _ = directory.person_ids(ticket.assignee_ids)
    return any_assignee_visible(iter(ids), visible_user_ids)


def build_period_report(
    db: Session, outbound, settings, *, start: str, end: str, today: date,
    tickets=None, repo=None, visible_user_ids=None,
) -> dict:
    """마감일이 [start, end) 인 티켓을 담당자별로 집계한다(월간 리포트·스프린트 회의 공용 코어).
    반환에 period 는 없다 — 월간 래퍼(build_dev_monthly_report)가 period 와 완료일 축을 덧붙인다.

    tickets 를 주면 그 목록을 그대로 쓴다 — 스프린트 요약이 같은 범위를 두 번 읽지 않게 하려는 것이다.

    ``visible_user_ids`` 는 관리 범위(0024)다. **None 이면 제한 없음.** 값이 있으면:
      * 티켓은 **담당자 중 한 명이라도** 그 집합 안이면 남는다;
      * 담당자가 없는 티켓은 어느 부서에도 속하지 않으므로 빠진다;
      * 팀 합계도 남은 티켓만으로 다시 센다.
    """
    if tickets is None:
        from app.tickets.service import list_period_tickets

        tickets = list_period_tickets(db, outbound, settings, start=start, end=end, repo=repo)
    directory = load_assignee_directory(db)
    today_iso = today.isoformat()

    tickets = [t for t in tickets if _visible(directory, t, visible_user_ids)]

    devs: dict[str, dict] = {}
    unassigned = {**{b: 0 for b in BUCKETS}, "total": 0}
    # 팀 합계는 티켓 단위(중복 없이)로 센다. 담당자별 합은 다중 담당 티켓을 양쪽에 세므로 팀 합계와 다르다.
    team = {"total": 0, **{b: 0 for b in BUCKETS}, "overdue": 0,
            "est_done_total": 0.0, "est_all_total": 0.0}

    for t in tickets:
        kind = bucket_of(t.status)
        est = t.est_wd or 0
        overdue = bool(t.due) and t.due < today_iso and not workflow.is_terminal(t.status)

        team["total"] += 1
        team[kind] += 1
        if kind == "done":
            team["est_done_total"] += est
        if kind != "cancel":
            team["est_all_total"] += est
        if overdue:
            team["overdue"] += 1

        if not t.assignee_ids:
            unassigned["total"] += 1
            unassigned[kind] += 1
            continue

        ids, unknown = directory.person_ids(t.assignee_ids)
        for user_id in sorted(ids):
            # 범위가 걸려 있으면 범위 밖 담당자는 행을 만들지 않는다. 공유 티켓은 남되 남의 부서 사람은 안 새어 나간다.
            if visible_user_ids is not None and user_id not in visible_user_ids:
                continue
            _bump(devs.setdefault(user_id, _blank_dev(user_id)), t, overdue=overdue)
        if unknown and visible_user_ids is None:
            _bump(devs.setdefault(UNKNOWN_KEY, _blank_dev(None)), t, overdue=overdue)

    # 활성 사용자 전원을 포함한다(이번 달 티켓이 없으면 0). 범위가 걸려 있으면 그 안의 사람만.
    # 비활성 · 보관 계정은 이 달에 티켓이 있을 때만 줄이 생긴다.
    for user_id in directory.active_ids:
        if visible_user_ids is not None and user_id not in visible_user_ids:
            continue
        devs.setdefault(user_id, _blank_dev(user_id))

    rows = [
        _finalize_dev(directory.person(key) if key != UNKNOWN_KEY else None, b,
                      has_tickets=b["assigned"] > 0)
        for key, b in devs.items()
    ]
    _mark_ambiguous(rows)
    # 완료 건수 내림차순, 같으면 담당 건수 내림차순, 같으면 이름순, 그래도 같으면 id(동명이인도 순서가 고정된다).
    rows.sort(key=lambda r: (-r["done"], -r["assigned"], r["name"], r["user_id"] or ""))

    return {
        "range": {"start": start, "end_exclusive": end},
        "team": {
            "total": team["total"],
            "done": team["done"],
            "in_progress": team["prog"],
            "verify": team["verify"],
            "plan": team["plan"],
            "hold": team["hold"],
            "cancel": team["cancel"],
            "other": team["other"],
            "overdue": team["overdue"],
            "completion_rate": pct(team["done"], team["total"] - team["cancel"])
            if team["total"] - team["cancel"] > 0 else None,
            "est_done_total": _round1(team["est_done_total"]),
            "est_all_total": _round1(team["est_all_total"]),
        },
        "developers": rows,
        "unassigned": unassigned,
    }


def _mark_ambiguous(rows: list[dict]) -> None:
    counts: dict[str, int] = {}
    for row in rows:
        if row["user_id"]:
            counts[row["name"]] = counts.get(row["name"], 0) + 1
    for row in rows:
        row["ambiguous_name"] = bool(row["user_id"]) and counts.get(row["name"], 0) > 1


# ── 완료일 축 · 마감일 없음 ─────────────────────────────────────────────────────


def _completed_kst_date(completed_at: datetime, tz: str) -> date:
    return completed_at.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz)).date()


def _completed_axis(db, directory, repo, *, since, until, tz, visible_user_ids) -> tuple[dict, dict]:
    """(사람별 {done, est_done, act_done, late_done}, 팀 합계)."""
    per: dict[str, dict] = {}
    team = {"done": 0, "est_done": 0.0, "act_done": 0.0, "late_done": 0}
    for t in repo.list_completed_between(db, since=since, until=until).tickets:
        if not _visible(directory, t, visible_user_ids):
            continue
        late = bool(t.due) and t.completed_at is not None and \
            _completed_kst_date(t.completed_at, tz).isoformat() > t.due
        est, act = t.est_wd or 0, t.act_wd or 0
        team["done"] += 1
        team["est_done"] += est
        team["act_done"] += act
        team["late_done"] += 1 if late else 0
        ids, unknown = directory.person_ids(t.assignee_ids)
        keys = [i for i in sorted(ids) if visible_user_ids is None or i in visible_user_ids]
        if unknown and visible_user_ids is None:
            keys.append(UNKNOWN_KEY)
        for key in keys:
            b = per.setdefault(key, {"done": 0, "est_done": 0.0, "act_done": 0.0, "late_done": 0})
            b["done"] += 1
            b["est_done"] += est
            b["act_done"] += act
            b["late_done"] += 1 if late else 0
    for b in (*per.values(), team):
        b["est_done"] = _round1(b["est_done"])
        b["act_done"] = _round1(b["act_done"])
    return per, team


def _no_due_axis(db, directory, repo, *, visible_user_ids) -> tuple[dict, int]:
    per: dict[str, int] = {}
    team = 0
    for t in repo.list_open_without_due(db).tickets:
        if not t.assignee_ids and visible_user_ids is not None:
            continue
        if not _visible(directory, t, visible_user_ids):
            continue
        team += 1
        ids, unknown = directory.person_ids(t.assignee_ids)
        keys = [i for i in sorted(ids) if visible_user_ids is None or i in visible_user_ids]
        if unknown and visible_user_ids is None:
            keys.append(UNKNOWN_KEY)
        for key in keys:
            per[key] = per.get(key, 0) + 1
    return per, team


def build_dev_monthly_report(
    db: Session, outbound, settings, *, period: str, today: date, repo=None,
    visible_user_ids=None,
) -> dict:
    """개발자 월간 리포트 — 마감일 축(`build_period_report`)에 완료일 축과 마감일 없음을 더한다."""
    from app.home.service import window_utc_bounds
    from app.tickets.service import _repo

    start, end = month_range(period)
    report = build_period_report(
        db, outbound, settings, start=start, end=end, today=today, repo=repo,
        visible_user_ids=visible_user_ids,
    )
    directory = load_assignee_directory(db)
    source = _repo(settings, outbound, repo)
    since, until = window_utc_bounds(settings, start, end)
    completed_per, completed_team = _completed_axis(
        db, directory, source, since=since, until=until, tz=settings.timezone,
        visible_user_ids=visible_user_ids,
    )
    no_due_per, no_due_team = _no_due_axis(db, directory, source, visible_user_ids=visible_user_ids)

    blank = {"done": 0, "est_done": 0.0, "act_done": 0.0, "late_done": 0}
    seen = set()
    for row in report["developers"]:
        key = row["user_id"] or UNKNOWN_KEY
        seen.add(key)
        row["completed"] = dict(completed_per.get(key, blank))
        row["no_due"] = {"open": no_due_per.get(key, 0)}
    # 이 달 마감 티켓은 없지만 이 달에 끝낸 일(또는 마감 없는 열린 일)이 있는 사람도 줄을 갖는다.
    extra = [k for k in (set(completed_per) | set(no_due_per)) if k not in seen]
    for key in sorted(extra):
        person = directory.person(key) if key != UNKNOWN_KEY else None
        row = _finalize_dev(person, _blank_dev(key if person else None), has_tickets=False)
        row["completed"] = dict(completed_per.get(key, blank))
        row["no_due"] = {"open": no_due_per.get(key, 0)}
        report["developers"].append(row)
    _mark_ambiguous(report["developers"])

    unknown_date = source.count_done_without_completion(db) if visible_user_ids is None else None
    return {
        "period": period,
        "today": today.isoformat(),
        "timezone": settings.timezone,
        **report,
        "completed": {"team": completed_team, "unknown_date": unknown_date},
        "no_due": {"team": {"open": no_due_team}},
        "definitions": dict(DEFINITIONS),
    }
