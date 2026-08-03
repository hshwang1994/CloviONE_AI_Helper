"""홈 '오늘'·AI 브리핑의 **순수 집계** — DB도 네트워크도 LLM도 모른다 (계획서 Phase 5).

계획서 Phase 5: *"먼저 결정적 집계 엔드포인트로 만들고 LLM 없이 테스트한 뒤 문장만 LLM에
맡긴다."* 이 파일이 그 '먼저'다. 여기 있는 함수는 전부 (입력 → 출력)이라 서버도 픽스처도
없이 값 하나로 고정할 수 있고, 러너가 죽어도 이 층의 숫자는 그대로 나온다.

입력 티켓 dict 의 모양은 `app/tickets/service.py::ticket_view` 가 내는 그대로다
(id/uid/tid/title/status/due/est_wd/priority/difficulty/assignee_user_ids/…).
여기서 새 모양을 만들지 않는다 — 화면이 이미 그 모양을 그리고 있다.

날짜는 전부 'YYYY-MM-DD' **문자열**로 비교한다. 원본(Notion)이 문자열이고 ISO 문자열은
사전순 비교가 곧 날짜순 비교라 파싱이 필요 없다. 시간대 판정(오늘이 며칠인가)은 이 파일
바깥(service.py)에서 Asia/Seoul 로 한 번만 하고, 여기에는 결정된 `today` 만 들어온다.
"""

from __future__ import annotations

STATUS_DONE = "완료"
STATUS_CANCELLED = "취소"
STATUS_BLOCKED = "이슈"
# 끝난 티켓 — '진행 중'·'지연' 계산에서 뺀다(리포트·화면과 같은 어휘).
TERMINAL = frozenset({STATUS_DONE, STATUS_CANCELLED})

# 마감 임박 기본 지평. '이번 주'라고 부르면 실제 로직(오늘+N일 롤링)과 어긋나 헷갈린다.
DUE_SOON_DAYS = 7

# 목록을 통째로 싣지 않는다 — 홈은 '지금 무엇을 볼지'를 정하는 화면이고, 전체 목록은
# 각 화면이 이미 갖고 있다. count 는 항상 진짜 총계이고 items 만 잘린다.
DEFAULT_ITEM_LIMIT = 5

# 트리아지 정렬용 우선순위 등급. frontend/src/lib/priority.js 와 같은 어휘를 쓴다 —
# 한쪽만 고치면 화면의 배지 색과 제안 순서가 서로 다른 말을 한다.
_PRIORITY_RANK = {
    "urgent": 0, "critical": 0, "긴급": 0, "1": 0,
    "high": 1, "높음": 1,
    "medium": 2, "normal": 2, "보통": 2, "2": 2,
    "low": 3, "낮음": 3, "3": 3,
}
_PRIORITY_UNKNOWN = 4


def is_active(ticket: dict) -> bool:
    """아직 끝나지 않은 티켓(완료·취소 제외)."""
    return (ticket.get("status") or "") not in TERMINAL


def is_overdue(ticket: dict, today: str) -> bool:
    """마감이 지났는데 아직 안 끝난 티켓. 마감이 없으면 지연이 아니다."""
    due = ticket.get("due")
    return bool(due) and due < today and is_active(ticket)


def _by_due(rows: list[dict]) -> list[dict]:
    """마감 빠른 순. 마감 없는 건 맨 뒤, 같은 날이면 티켓 번호순(안정적 순서)."""
    return sorted(rows, key=lambda t: (t.get("due") or "9999-99-99", t.get("tid") or 0))


def add_days(iso_date: str, days: int) -> str:
    """'YYYY-MM-DD' + N일. date 모듈을 쓰되 입출력은 문자열로 통일한다."""
    from datetime import date, timedelta

    return (date.fromisoformat(iso_date) + timedelta(days=days)).isoformat()


def bucket(rows: list[dict], *, limit: int = DEFAULT_ITEM_LIMIT) -> dict:
    """{count, items} — count 는 진짜 총계, items 만 limit 로 자른다.

    화면이 "3건" 이라고 쓰면서 5건을 그리는 어긋남을 구조적으로 막는다.
    """
    return {"count": len(rows), "items": rows[:limit]}


def bucket_my_tickets(
    tickets: list[dict], *, today: str, horizon_days: int = DUE_SOON_DAYS,
    limit: int = DEFAULT_ITEM_LIMIT,
) -> dict:
    """내 티켓을 오늘 기준으로 나눈다: 오늘 마감 / 지연 / 진행 중 / 곧 마감 / 막힘.

    한 티켓이 여러 버킷에 들어갈 수 있다(오늘 마감이면서 진행 중). 버킷은 '무엇을 먼저 볼지'
    이고 배타적 분류가 아니다 — 배타적으로 만들면 '오늘 마감'을 눌렀을 때 진행 중 목록에서
    사라져 개수가 안 맞는 것처럼 보인다.
    """
    horizon = add_days(today, horizon_days)
    active = [t for t in tickets if is_active(t)]
    due_today = [t for t in active if t.get("due") == today]
    overdue = [t for t in active if is_overdue(t, today)]
    # 곧 마감 = 내일부터 지평까지(오늘은 due_today 가 따로 세므로 중복 표시하지 않는다).
    due_soon = [t for t in active if t.get("due") and today < t["due"] <= horizon]
    blocked = [t for t in active if (t.get("status") or "") == STATUS_BLOCKED]
    return {
        "due_today": bucket(_by_due(due_today), limit=limit),
        "overdue": bucket(_by_due(overdue), limit=limit),
        "in_progress": bucket(_by_due(active), limit=limit),
        "due_soon": bucket(_by_due(due_soon), limit=limit),
        "blocked": bucket(_by_due(blocked), limit=limit),
        "done_total": sum(1 for t in tickets if (t.get("status") or "") == STATUS_DONE),
    }


def _round1(value: float) -> float:
    """WD 합계는 0.5 단위 입력이 쌓여 부동소수 꼬리가 붙는다 — 소수 첫째 자리로 고정한다."""
    return round(value + 0.0, 1)


def sprint_progress(tickets: list[dict], *, start: str, end: str, today: str) -> dict:
    """이번 스프린트 창([start, end))에서 **내 몫**의 진척.

    창 판정은 마감일 기준이다(리포트·스프린트 화면의 build_period_report 와 같은 규칙) —
    같은 화면에서 두 숫자가 다른 기준을 쓰면 사용자가 어느 쪽을 믿어야 할지 알 수 없다.
    완료율의 분모에서 '취소'는 뺀다(취소된 일을 못 한 일로 세면 완료율이 부당하게 낮아진다).
    """
    in_window = [t for t in tickets if t.get("due") and start <= t["due"] < end]
    done = [t for t in in_window if (t.get("status") or "") == STATUS_DONE]
    cancelled = [t for t in in_window if (t.get("status") or "") == STATUS_CANCELLED]
    remaining = [t for t in in_window if is_active(t)]
    overdue = [t for t in in_window if is_overdue(t, today)]
    net = len(in_window) - len(cancelled)
    return {
        "window": {"start": start, "end_exclusive": end},
        "assigned": len(in_window),
        "done": len(done),
        "remaining": len(remaining),
        "cancelled": len(cancelled),
        "overdue": len(overdue),
        "completion_rate": round(100 * len(done) / net) if net > 0 else None,
        "est_wd_total": _round1(sum(t.get("est_wd") or 0 for t in in_window if t not in cancelled)),
        "est_wd_done": _round1(sum(t.get("est_wd") or 0 for t in done)),
    }


def standup_sections(
    tickets: list[dict], *, today: str, start: str, end: str,
    limit: int = DEFAULT_ITEM_LIMIT,
) -> dict:
    """스탠드업 초안의 **사실 3단**: 최근 끝낸 것 / 오늘 할 것 / 막힌 것.

    한계를 정직하게 적어 둔다: 소스에 '언제 완료했는가'가 없다(티켓 캐시의 시간 정보는
    Notion 생성·수정 시각뿐이고 상태 전이 이력은 어디에도 없다). 그래서 '어제 한 일'을
    지어내지 않고, **이번 스프린트 창 안에서 완료된 것**을 `recently_done` 으로 낸다.
    이름과 뜻이 어긋나지 않게 키 이름부터 그렇게 지었다.
    """
    in_window = [t for t in tickets if t.get("due") and start <= t["due"] < end]
    recently_done = [t for t in in_window if (t.get("status") or "") == STATUS_DONE]
    active = [t for t in tickets if is_active(t)]
    # 오늘 할 일 = 오늘 마감 + 이미 지연된 것(지연을 빼면 '오늘 할 일'이 거짓말이 된다).
    today_plan = [t for t in active if t.get("due") == today or is_overdue(t, today)]
    blocked = [t for t in active if (t.get("status") or "") == STATUS_BLOCKED]
    return {
        "window": {"start": start, "end_exclusive": end},
        "recently_done": bucket(_by_due(recently_done), limit=limit),
        "today_plan": bucket(_by_due(today_plan), limit=limit),
        "blocked": bucket(_by_due(blocked), limit=limit),
    }


def priority_rank(value) -> int:
    """우선순위 → 정렬용 등급(낮을수록 급하다). 모르는 값은 맨 뒤로."""
    return _PRIORITY_RANK.get(str(value or "").strip().lower(), _PRIORITY_UNKNOWN)


def triage_order(tickets: list[dict], *, today: str) -> list[dict]:
    """미할당 티켓을 '먼저 봐야 하는 순'으로 정렬한다(제안만 — 배정하지 않는다).

    순서: 지연 → 우선순위 → 마감 빠른 순 → 티켓 번호. 전부 결정적이라 같은 입력이면
    항상 같은 순서가 나온다(LLM 이 순서를 바꾸지 않는다는 뜻이기도 하다).
    """
    return sorted(
        tickets,
        key=lambda t: (
            0 if is_overdue(t, today) else 1,
            priority_rank(t.get("priority")),
            t.get("due") or "9999-99-99",
            t.get("tid") or 0,
        ),
    )


def assignee_load(tickets: list[dict]) -> dict[str, int]:
    """앱 user_id → 활성 담당 건수. 다중 담당 티켓은 담당자 전원에게 센다(리포트와 동일).

    트리아지가 '누구에게 제안할까'를 정할 때 쓰는 유일한 근거다. 이름이 아니라 user_id 로
    센다 — 표시 이름으로 키잉하면 동명이인이 한 사람으로 합쳐진다(리포트에서 겪은 함정).
    """
    load: dict[str, int] = {}
    for t in tickets:
        if not is_active(t):
            continue
        for uid in t.get("assignee_user_ids") or []:
            load[uid] = load.get(uid, 0) + 1
    return load


def suggest_assignees(
    candidates: list[dict], load: dict[str, int], *, top: int = 3
) -> list[dict]:
    """부하가 가장 적은 후보 상위 N (제안 전용, 자동 배정 없음).

    candidates 는 `/api/tickets/assignees` 와 같은 모양 [{user_id, display_name}] 이다.
    동점이면 이름순으로 끊어 순서가 요청마다 흔들리지 않게 한다.
    """
    ranked = sorted(
        candidates,
        key=lambda c: (load.get(c.get("user_id"), 0), c.get("display_name") or ""),
    )
    return [
        {
            "user_id": c.get("user_id"),
            "display_name": c.get("display_name"),
            "active_tickets": load.get(c.get("user_id"), 0),
        }
        for c in ranked[:top]
    ]
