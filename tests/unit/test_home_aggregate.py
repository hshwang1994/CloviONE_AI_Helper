"""홈 '오늘'·AI 도우미의 **순수 집계**를 값으로 고정한다 — LLM도 DB도 서버도 없이.

계획서 Phase 5: *"오늘 브리핑 / 스탠드업 초안 / 주간 다이제스트의 숫자와 사실을 내는 순수
집계 함수를 만들고, LLM 없이 단위 테스트로 고정하라."* 이 파일이 그 고정이다.

여기서 통과한다는 것은 곧 "러너가 죽어도 이 숫자들은 그대로 나온다"는 뜻이다 — 이 코드
경로에는 외부 호출이 아예 없다.
"""

from __future__ import annotations

from app.home import aggregate

TODAY = "2026-08-03"          # 월요일
WEEK_START = "2026-08-03"
WEEK_END = "2026-08-10"       # 배타


def t(tid, *, status="진행", due=None, est=None, priority=None, users=()):
    """ticket_view 가 내는 dict 중 집계가 실제로 읽는 필드만."""
    return {
        "id": f"p{tid}", "tid": tid, "title": f"티켓 {tid}",
        "status": status, "due": due, "est_wd": est, "priority": priority,
        "assignee_user_ids": list(users),
    }


# ── 오늘 버킷 ─────────────────────────────────────────────────────────────────

def test_bucket_counts_today_overdue_in_progress_separately():
    rows = [
        t(1, due=TODAY),                       # 오늘 마감 + 진행 중
        t(2, due="2026-07-30"),                # 지연 + 진행 중
        t(3, due="2026-08-06"),                # 곧 마감(7일 내) + 진행 중
        t(4, due="2026-09-30"),                # 지평 밖 + 진행 중
        t(5, due=TODAY, status="완료"),         # 끝남 — 어느 활성 버킷에도 없다
        t(6, due="2026-07-01", status="취소"),  # 끝남 — 지연 아님
        t(7, status="이슈", due="2026-08-05"),  # 막힘 + 곧 마감 + 진행 중
    ]
    b = aggregate.bucket_my_tickets(rows, today=TODAY)

    assert b["due_today"]["count"] == 1
    assert b["overdue"]["count"] == 1
    assert b["due_soon"]["count"] == 2          # 3번, 7번 (오늘 마감은 제외)
    assert b["blocked"]["count"] == 1
    assert b["in_progress"]["count"] == 5       # 완료·취소만 빠진다
    assert b["done_total"] == 1


def test_bucket_count_is_true_total_even_when_items_are_capped():
    """count 는 진짜 총계, items 만 잘린다 — '3건'이라 쓰고 5건을 그리는 어긋남 방지."""
    rows = [t(i, due=TODAY) for i in range(1, 13)]
    b = aggregate.bucket_my_tickets(rows, today=TODAY, limit=5)
    assert b["due_today"]["count"] == 12
    assert len(b["due_today"]["items"]) == 5


def test_bucket_items_sorted_by_due_then_ticket_number():
    rows = [t(9, due="2026-08-05"), t(2, due="2026-08-04"), t(1, due="2026-08-04")]
    items = aggregate.bucket_my_tickets(rows, today=TODAY)["in_progress"]["items"]
    assert [r["tid"] for r in items] == [1, 2, 9]


def test_ticket_without_due_is_never_overdue():
    assert aggregate.is_overdue(t(1, due=None), TODAY) is False
    assert aggregate.bucket_my_tickets([t(1)], today=TODAY)["overdue"]["count"] == 0


def test_bucket_input_list_is_not_mutated():
    rows = [t(2, due="2026-08-05"), t(1, due="2026-08-04")]
    before = [r["tid"] for r in rows]
    aggregate.bucket_my_tickets(rows, today=TODAY)
    assert [r["tid"] for r in rows] == before


# ── 스프린트 내 몫 ────────────────────────────────────────────────────────────

def test_sprint_progress_counts_only_tickets_due_inside_the_window():
    rows = [
        t(1, due=WEEK_START, status="완료", est=1),
        t(2, due="2026-08-07", status="진행", est=2),
        t(3, due=WEEK_END, status="진행", est=8),        # 배타 경계 — 창 밖
        t(4, due="2026-08-02", status="완료", est=8),    # 창 앞 — 밖
    ]
    p = aggregate.sprint_progress(rows, start=WEEK_START, end=WEEK_END, today=TODAY)
    assert p["assigned"] == 2
    assert p["done"] == 1
    assert p["remaining"] == 1
    assert p["completion_rate"] == 50
    assert p["est_wd_total"] == 3.0
    assert p["est_wd_done"] == 1.0
    assert p["window"] == {"start": WEEK_START, "end_exclusive": WEEK_END}


def test_sprint_progress_excludes_cancelled_from_completion_denominator():
    rows = [t(1, due=WEEK_START, status="완료"), t(2, due="2026-08-05", status="취소")]
    p = aggregate.sprint_progress(rows, start=WEEK_START, end=WEEK_END, today=TODAY)
    assert p["cancelled"] == 1
    assert p["completion_rate"] == 100        # 취소를 '못 한 일'로 세지 않는다


def test_sprint_progress_completion_rate_is_none_when_nothing_countable():
    p = aggregate.sprint_progress([], start=WEEK_START, end=WEEK_END, today=TODAY)
    assert p["assigned"] == 0 and p["completion_rate"] is None


# ── 스탠드업 3단 ──────────────────────────────────────────────────────────────

def test_standup_sections_split_done_plan_blocked():
    rows = [
        t(1, due="2026-08-04", status="완료"),   # 창 안 완료
        t(2, due=TODAY),                        # 오늘 할 일
        t(3, due="2026-07-31"),                 # 지연 → 오늘 할 일에도 들어간다
        t(4, due="2026-08-06", status="이슈"),   # 막힘
    ]
    s = aggregate.standup_sections(rows, today=TODAY, start=WEEK_START, end=WEEK_END)
    assert s["recently_done"]["count"] == 1
    assert {r["tid"] for r in s["today_plan"]["items"]} == {2, 3}
    assert s["blocked"]["count"] == 1


# ── 트리아지(제안 전용) ────────────────────────────────────────────────────────

def test_triage_order_is_overdue_then_priority_then_due():
    rows = [
        t(1, due="2026-08-20", priority="보통"),
        t(2, due="2026-08-20", priority="긴급"),
        t(3, due="2026-07-30", priority="낮음"),   # 지연 — 우선순위가 낮아도 맨 앞
        t(4, due="2026-08-05", priority="긴급"),
    ]
    assert [r["tid"] for r in aggregate.triage_order(rows, today=TODAY)] == [3, 4, 2, 1]


def test_triage_order_is_stable_for_identical_input():
    rows = [t(5), t(3), t(4)]
    first = [r["tid"] for r in aggregate.triage_order(rows, today=TODAY)]
    second = [r["tid"] for r in aggregate.triage_order(rows, today=TODAY)]
    assert first == second == [3, 4, 5]


def test_assignee_load_counts_every_assignee_of_a_shared_ticket():
    rows = [
        t(1, users=["u1", "u2"]),
        t(2, users=["u1"]),
        t(3, users=["u2"], status="완료"),   # 끝난 건 부하가 아니다
    ]
    assert aggregate.assignee_load(rows) == {"u1": 2, "u2": 1}


def test_suggest_assignees_picks_least_loaded_and_breaks_ties_by_name():
    candidates = [
        {"user_id": "u1", "display_name": "가"},
        {"user_id": "u2", "display_name": "나"},
        {"user_id": "u3", "display_name": "다"},
    ]
    load = {"u1": 3, "u2": 0}          # u3 는 담당 0건(맵에 없음)
    got = aggregate.suggest_assignees(candidates, load, top=2)
    assert [c["user_id"] for c in got] == ["u2", "u3"]
    assert got[0]["active_tickets"] == 0


def test_priority_rank_puts_unknown_values_last():
    assert aggregate.priority_rank("긴급") < aggregate.priority_rank("보통")
    assert aggregate.priority_rank("보통") < aggregate.priority_rank(None)
    assert aggregate.priority_rank("HIGH") == aggregate.priority_rank("높음")
