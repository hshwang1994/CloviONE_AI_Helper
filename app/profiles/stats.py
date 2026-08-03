"""내 업무량 · 완료 통계의 **순수 집계** — DB도 네트워크도 LLM도 모른다.

`app/home/aggregate.py` 와 같은 층이고 **같은 어휘를 쓴다**(완료/취소/이슈, 지연 판정,
마감일 기준 창 판정). 어휘를 새로 만들면 홈의 '지연 3건'과 통계의 '지연 5건'이 서로 다른
말을 하게 되고, 사용자는 어느 쪽을 믿어야 할지 알 수 없다 — 그래서 여기서는 판정 함수를
직접 정의하지 않고 aggregate 의 것을 부른다.

## 왜 '완료 시각'이 아니라 마감일로 월을 나누는가

티켓 응답(`app/tickets/service.py::ticket_view`)에는 완료 시각이 없다. 소스(Notion)에도
'언제 완료로 바뀌었는가'가 속성으로 없다. 있는 것은 마감일(`due`)뿐이고, 기존 리포트
(`build_period_report`)와 스프린트 진척도 전부 **마감일 기준**으로 창을 자른다.
여기서만 다른 기준을 쓰면 같은 화면 안에서 숫자가 어긋난다. 그래서 '6월 완료 5건' 은
**'마감이 6월인 티켓 중 완료 상태인 것 5건'** 이다 — 화면도 그렇게 쓴다.

입력 티켓 dict 모양은 `ticket_view` 가 내는 그대로다(id/tid/title/status/due/est_wd/
act_wd/priority/…). 여기서 새 모양을 만들지 않는다.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.home.aggregate import (
    DUE_SOON_DAYS,
    STATUS_BLOCKED,
    STATUS_CANCELLED,
    STATUS_DONE,
    add_days,
    is_active,
    is_overdue,
)

DEFAULT_MONTHS = 6
DEFAULT_WEEKS = 4

# 상태·우선순위 분포에서 값이 비었을 때 쓰는 라벨. 빈 문자열을 그대로 그리면 화면에
# 이름 없는 막대가 생겨 무엇인지 알 수 없다.
UNSET_LABEL = "미지정"


def _num(value) -> float:
    """est_wd/act_wd 는 소스에서 None·문자열로 올 수 있다. 숫자가 아니면 0으로 본다."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _round1(value: float) -> float:
    """WD 는 0.5 단위 입력이 쌓여 부동소수 꼬리가 붙는다 — 소수 첫째 자리로 고정."""
    return round(value + 0.0, 1)


def _counts(rows: list[dict], key: str) -> list[dict]:
    """값별 건수 + 예상 공수 합. 건수 많은 순, 같으면 이름순(안정적 순서)."""
    buckets: dict[str, dict] = {}
    for row in rows:
        name = (row.get(key) or "").strip() or UNSET_LABEL
        bucket = buckets.setdefault(name, {"name": name, "count": 0, "est_wd": 0.0})
        bucket["count"] += 1
        bucket["est_wd"] += _num(row.get("est_wd"))
    out = sorted(buckets.values(), key=lambda b: (-b["count"], b["name"]))
    for bucket in out:
        bucket["est_wd"] = _round1(bucket["est_wd"])
    return out


def month_keys(today: str, months: int = DEFAULT_MONTHS) -> list[str]:
    """오늘이 속한 달까지 최근 `months` 개의 'YYYY-MM' (과거 → 현재 순)."""
    anchor = date.fromisoformat(today).replace(day=1)
    keys: list[str] = []
    for back in range(months - 1, -1, -1):
        year, month = anchor.year, anchor.month - back
        while month <= 0:
            month += 12
            year -= 1
        keys.append(f"{year:04d}-{month:02d}")
    return keys


def monthly_completion(
    tickets: list[dict], *, today: str, months: int = DEFAULT_MONTHS
) -> list[dict]:
    """월별(마감일 기준) 배정/완료/취소/진행 + 완료율 + 공수.

    완료율의 분모에서 취소는 뺀다 — 취소된 일을 '못 한 일'로 세면 완료율이 부당하게
    낮아지고, 그러면 사람들이 취소 대신 티켓을 방치하게 된다(지표가 행동을 바꾼다).
    배정이 0건인 달은 완료율을 `null` 로 둔다(0%가 아니다 — 아무 일도 없었을 뿐이다).
    """
    keys = month_keys(today, months)
    index = {key: {
        "month": key, "assigned": 0, "done": 0, "cancelled": 0, "open": 0,
        "overdue": 0, "est_wd": 0.0, "act_wd": 0.0, "completion_rate": None,
    } for key in keys}

    for ticket in tickets:
        due = ticket.get("due") or ""
        bucket = index.get(due[:7])
        if bucket is None:
            continue
        status = ticket.get("status") or ""
        bucket["assigned"] += 1
        bucket["est_wd"] += _num(ticket.get("est_wd"))
        bucket["act_wd"] += _num(ticket.get("act_wd"))
        if status == STATUS_DONE:
            bucket["done"] += 1
        elif status == STATUS_CANCELLED:
            bucket["cancelled"] += 1
        else:
            bucket["open"] += 1
            if is_overdue(ticket, today):
                bucket["overdue"] += 1

    out = []
    for key in keys:
        bucket = index[key]
        net = bucket["assigned"] - bucket["cancelled"]
        bucket["completion_rate"] = round(bucket["done"] / net, 3) if net > 0 else None
        bucket["est_wd"] = _round1(bucket["est_wd"])
        bucket["act_wd"] = _round1(bucket["act_wd"])
        out.append(bucket)
    return out


def _week_start(iso_date: str) -> date:
    """그 날짜가 속한 주의 월요일. 주는 사람이 일하는 단위라 달력 주로 자른다."""
    day = date.fromisoformat(iso_date)
    return day - timedelta(days=day.weekday())


def weekly_load(
    tickets: list[dict], *, today: str, weeks: int = DEFAULT_WEEKS
) -> list[dict]:
    """앞으로 `weeks` 주의 **남은 일** 분포(활성 티켓만, 마감일 기준).

    끝난 티켓은 업무량이 아니다 — 완료된 일을 앞으로의 부하에 세면 "다음 주에 8건"
    이라는 숫자가 아무 의미도 갖지 못한다.
    지난 주 이전에 마감이었던 활성 티켓은 `overdue` 로, 마감이 없으면 `no_due` 로,
    창 뒤쪽은 `later` 로 따로 센다 — 어느 통에도 안 들어가 사라지는 티켓이 없게 한다.
    """
    active = [t for t in tickets if is_active(t)]
    first_monday = _week_start(today)
    labels = ["이번 주", "다음 주"] + [f"{n}주 뒤" for n in range(2, max(weeks, 2))]

    buckets = []
    for offset in range(weeks):
        start = first_monday + timedelta(days=7 * offset)
        buckets.append({
            "start": start.isoformat(),
            "end_exclusive": (start + timedelta(days=7)).isoformat(),
            "label": labels[offset] if offset < len(labels) else f"{offset}주 뒤",
            "count": 0, "est_wd": 0.0,
        })
    horizon = buckets[-1]["end_exclusive"] if buckets else today
    extra = {"overdue": {"count": 0, "est_wd": 0.0},
             "later": {"count": 0, "est_wd": 0.0},
             "no_due": {"count": 0, "est_wd": 0.0}}

    for ticket in active:
        due = ticket.get("due")
        est = _num(ticket.get("est_wd"))
        if not due:
            extra["no_due"]["count"] += 1
            extra["no_due"]["est_wd"] += est
            continue
        if due >= horizon:
            extra["later"]["count"] += 1
            extra["later"]["est_wd"] += est
            continue
        placed = False
        for bucket in buckets:
            if bucket["start"] <= due < bucket["end_exclusive"]:
                bucket["count"] += 1
                bucket["est_wd"] += est
                placed = True
                break
        if not placed:  # 이번 주 월요일보다 앞 = 지난 마감
            extra["overdue"]["count"] += 1
            extra["overdue"]["est_wd"] += est

    for bucket in buckets:
        bucket["est_wd"] = _round1(bucket["est_wd"])
    for bucket in extra.values():
        bucket["est_wd"] = _round1(bucket["est_wd"])
    return [*buckets], extra


def build_stats(
    tickets: list[dict],
    *,
    today: str,
    months: int = DEFAULT_MONTHS,
    weeks: int = DEFAULT_WEEKS,
    horizon_days: int = DUE_SOON_DAYS,
) -> dict:
    """내 업무량 + 완료 통계 한 벌. 숫자만 낸다(문장·LLM 없음)."""
    active = [t for t in tickets if is_active(t)]
    done = [t for t in tickets if (t.get("status") or "") == STATUS_DONE]
    cancelled = [t for t in tickets if (t.get("status") or "") == STATUS_CANCELLED]
    overdue = [t for t in active if is_overdue(t, today)]
    horizon = add_days(today, horizon_days)
    due_today = [t for t in active if t.get("due") == today]
    due_soon = [t for t in active if t.get("due") and today < t["due"] <= horizon]
    blocked = [t for t in active if (t.get("status") or "") == STATUS_BLOCKED]
    no_due = [t for t in active if not t.get("due")]

    week_buckets, week_extra = weekly_load(tickets, today=today, weeks=weeks)
    net_total = len(tickets) - len(cancelled)

    return {
        "today": today,
        "totals": {
            "all": len(tickets),
            "active": len(active),
            "done": len(done),
            "cancelled": len(cancelled),
            "overdue": len(overdue),
            "due_today": len(due_today),
            "due_soon": len(due_soon),
            "blocked": len(blocked),
            "no_due": len(no_due),
            # 전체 완료율도 취소를 분모에서 뺀다(월별과 같은 규칙).
            "completion_rate": round(len(done) / net_total, 3) if net_total > 0 else None,
        },
        "workload": {
            "est_wd_active": _round1(sum(_num(t.get("est_wd")) for t in active)),
            "est_wd_overdue": _round1(sum(_num(t.get("est_wd")) for t in overdue)),
            "act_wd_done": _round1(sum(_num(t.get("act_wd")) for t in done)),
            "est_wd_done": _round1(sum(_num(t.get("est_wd")) for t in done)),
            "by_status": _counts(tickets, "status"),
            "by_priority": _counts(active, "priority"),
            "by_week": week_buckets,
            "by_week_extra": week_extra,
        },
        "months": monthly_completion(tickets, today=today, months=months),
    }
