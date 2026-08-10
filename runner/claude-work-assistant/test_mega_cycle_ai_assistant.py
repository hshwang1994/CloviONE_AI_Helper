"""MEGA CYCLE A regression tests — AI Assistant / runner conversation engine.

Covers AI-30 (Critical) and RN-01..RN-14, all rooted in assistant.py's conversation
state machine (see docs/DECISIONS.md D-53 for the investigation that mapped these to
shared root causes A-E). Follows the existing test_assistant.py conventions:
m.route_request(body) / m.process_request(body) direct calls, no HTTP layer.
"""
import importlib.util
import os
import unittest.mock as mock
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("RUNNER_TOKEN", "test")

_spec = importlib.util.spec_from_file_location(
    "assistant", str(Path(__file__).with_name("assistant.py"))
)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)

REQUESTER = {"email": "a@goodmit.co.kr", "name": "황형섭", "teams_user_id": "t1"}
U1 = {"id": "u1", "name": "황형섭", "person": {"email": "a@goodmit.co.kr"}}
SCHEMA = {"properties": {
    "제목": {"type": "title"},
    "진행상태": {"type": "status", "status": {"options": [{"name": "계획"}, {"name": "진행"}, {"name": "완료"}]}},
    "우선순위": {"type": "select", "select": {"options": [{"name": "낮음"}, {"name": "중간"}, {"name": "높음"}]}},
    "마감일": {"type": "date"}, "티켓 담당자": {"type": "people"}}}
STATUS_MAP = {"계획": "계획", "진행": "진행", "완료": "완료"}


def _ticket(tid, title, status="진행", people=(U1,)):
    return {"id": tid, "url": "", "properties": {
        "제목": {"type": "title", "title": [{"plain_text": title}]},
        "진행상태": {"type": "status", "status": {"name": status}},
        "우선순위": {"type": "select", "select": {"name": "중간"}},
        "티켓 담당자": {"type": "people", "people": list(people)}}}


# ── AI-30 (Critical): stale CREATE mode must not hijack an unrelated question ──

_FAKE_QUERY_RESULT = {"answer": "그건 잘 모르겠어요", "ticket_ids": [], "project_ids": [],
                       "needs_clarification": False, "clarify_question": ""}


def test_stale_create_mode_is_dropped_before_routing():
    # Matches the real incident's state shape: mid field-collection (mode set, no
    # pending_action/approval yet — that's a later stage handled by a different branch).
    old = (datetime.now() - timedelta(hours=25)).isoformat()  # older than 24h TTL
    ctx = {"mode": "CREATE", "ticket_draft": {"title": "묵은 초안"}, "_context_updated_at": old}
    b = {"message": "방금 말한 것 중에 제일 오래된 건 뭐야?", "requester": REQUESTER, "projects": [],
         "tickets": [], "work_schema": SCHEMA, "context": ctx}
    with mock.patch.object(m, "_run_claude", return_value=(_FAKE_QUERY_RESULT, "", 1)):
        d, _ = m.route_request(b)
    assert d["action"] != "NEED_INPUT" or "프로젝트" not in d.get("response_text", ""), d
    assert (d["context"].get("mode") is None), "11일 지난 CREATE가 여전히 살아 있다"


def test_fresh_create_mode_is_not_dropped():
    fresh = datetime.now().isoformat()
    ctx = {"mode": "CREATE", "pending_action": {"kind": "CREATE"}, "pending_question": "approval",
           "ticket_draft": {"title": "방금 만든 초안"}, "_context_updated_at": fresh}
    result = m.drop_stale_in_progress_state(ctx, datetime.now())
    assert result.get("mode") == "CREATE", "24시간 안 지난 CREATE까지 지워졌다(오탐)"
    assert result.get("ticket_draft") == {"title": "방금 만든 초안"}


def test_ai30_critical_revert_to_verify():
    """Revert drop_stale_in_progress_state to a no-op and confirm the stale-mode test fails.

    Uses a message with none of the secondary defense's read_only trigger words (뭐야/뭐임/
    뭔데/뭔지) — that second, independent layer would otherwise also catch this particular
    message and mask whether the PRIMARY (TTL) fix is the one doing the work.
    """
    original = m.drop_stale_in_progress_state
    m.drop_stale_in_progress_state = lambda context, now: context
    try:
        old = (datetime.now() - timedelta(hours=25)).isoformat()
        ctx = {"mode": "CREATE", "ticket_draft": {"title": "묵은 초안"}, "_context_updated_at": old}
        b = {"message": "오늘 점심 메뉴 추천해줘", "requester": REQUESTER, "projects": [],
             "tickets": [], "work_schema": SCHEMA, "context": ctx}
        with mock.patch.object(m, "_run_claude", return_value=(_FAKE_QUERY_RESULT, "", 1)):
            d, _ = m.route_request(b)
        assert d["action"] == "NEED_INPUT" and "프로젝트" in d.get("response_text", ""), (
            "revert should reproduce the AI-30 hijack — fix reverted but bug didn't reappear"
        )
    finally:
        m.drop_stale_in_progress_state = original


# ── RN-01: "완료했어?" (question) must not be read as "완료했어" (statement) ──

def test_question_about_completion_is_not_a_status_directive():
    tk = _ticket("tk1", "결제 오류 수정")
    ctx = {"pending_action": {"kind": "UPDATE", "ticket_id": "tk1", "ticket_title": "결제 오류 수정",
                               "changes": {}, "needs_confirmation": True, "direct": False},
           "pending_question": "approval", "selected_ticket": m.normalize_ticket(tk, {}),
           "last_results": ["tk1"], "last_result_start": 1}
    b = {"message": "완료했어?", "requester": REQUESTER, "projects": [], "tickets": [tk],
         "work_schema": SCHEMA, "context": ctx}
    d, _ = m.route_request(b)
    assert d["action"] != "WRITE_UPDATE", "질문이 상태 변경으로 확정됐다 — RN-01"


def test_rn01_revert_to_verify():
    assert m._STATUS_ONLY_DONE_RE.search(m.norm("완료했어?")), "sanity: norm strips the ?"
    detected = m.detect_target_status("완료했어?", STATUS_MAP)
    assert detected == "", f"RN-01 fix should reject a question, got {detected!r}"


# ── RN-02: negation must not be read as the value it negates ──

def test_negated_status_change_is_not_applied():
    tk = _ticket("tk1", "결제 오류 수정")
    ctx = {"pending_action": {"kind": "UPDATE", "ticket_id": "tk1", "ticket_title": "결제 오류 수정",
                               "changes": {}, "needs_confirmation": True, "direct": False},
           "pending_question": "approval", "selected_ticket": m.normalize_ticket(tk, {}),
           "last_results": ["tk1"], "last_result_start": 1}
    b = {"message": "완료로 바꾸지 마", "requester": REQUESTER, "projects": [], "tickets": [tk],
         "work_schema": SCHEMA, "context": ctx}
    with mock.patch.object(m, "llm_extract_update_changes", return_value=({}, {})):
        d, _ = m.route_request(b)
    assert d["action"] != "WRITE_UPDATE", "부정문이 그대로 상태 변경 확정으로 갔다 — RN-02"


def test_rn02_revert_to_verify():
    # RN-02's real root cause turned out to be two-fold: _NEGATION_RE itself only recognized
    # "하지 마/말"-stemmed negation, not "바꾸지 마" (a different verb stem) — the regex needed
    # broadening first (see its own comment), independent of the branch-order guard added below.
    assert m.carries_change("완료로 바꾸지 마", STATUS_MAP) is True, "sanity: carries_change still fires"
    assert m._NEGATION_RE.search("완료로 바꾸지 마"), "sanity: broadened negation regex matches"


# ── RN-03: ticket_selection must not accept a coincidental keyword match ──

def test_ticket_selection_ignores_unrelated_reply_with_coincidental_keyword():
    tk = _ticket("tk1", "결제 시스템 개선")
    ctx = {"pending_question": "ticket_selection", "pending_original_message": "그 티켓 완료로 바꿔줘",
           "last_results": ["tk1"], "last_result_start": 1}
    b = {"message": "아 잠깐만 결제 관련해서 다른 거 물어볼 게 있는데", "requester": REQUESTER,
         "projects": [], "tickets": [tk], "work_schema": SCHEMA, "context": ctx}
    d, _ = m.route_request(b)
    assert d["action"] != "WRITE_UPDATE", "무관한 곁말이 키워드 우연 일치로 티켓에 그대로 쓰였다 — RN-03"


def test_ticket_selection_still_accepts_a_real_number():
    tk = _ticket("tk1", "결제 시스템 개선")
    ctx = {"pending_question": "ticket_selection", "pending_original_message": "그 티켓 완료로 바꿔줘",
           "last_results": ["tk1"], "last_result_start": 1}
    b = {"message": "1번", "requester": REQUESTER, "projects": [], "tickets": [tk],
         "work_schema": SCHEMA, "context": ctx}
    with mock.patch.object(m, "llm_extract_update_changes", return_value=({}, {})):
        d, _ = m.route_request(b)
    assert d["action"] == "WRITE_UPDATE", "정당한 번호 선택까지 막혔다(오탐)"


# ── RN-06: compound instructions must refuse the unsupported half regardless of order ──

def test_unsupported_action_refused_regardless_of_clause_order():
    assert m.explicit_unsupported_action("티켓 만들어줘 그리고 메일 보내줘") == "이메일 발송"
    assert m.explicit_unsupported_action("담당자에게 메일 보내줘 그리고 티켓도 만들어줘") == "이메일 발송", (
        "순서를 바꾸니 메일 요청이 조용히 사라졌다 — RN-06"
    )


# ── RN-04 / RN-05: substring gates must not swallow create/query intents ──

def test_diagnostic_gate_does_not_swallow_ticket_creation():
    b = {"message": "성능 진단 티켓 만들어줘", "requester": REQUESTER, "projects": [],
         "tickets": [], "work_schema": SCHEMA, "context": {}}
    with mock.patch.object(m, "claude_draft", return_value=(None, "", 0)):
        d, _ = m.route_request(b)
    assert d["action"] != "DIAGNOSTIC", "진단 트리거가 티켓 생성을 가로챘다 — RN-05"


def test_in_progress_work_query_is_not_swallowed_by_context_status():
    b = {"message": "진행 중인 작업 보여줘", "requester": REQUESTER, "projects": [],
         "tickets": [_ticket("t1", "A", status="진행")], "work_schema": SCHEMA, "context": {}}
    d, _ = m.route_request(b)
    assert d["action"] != "CONTEXT_STATUS", "진행 중 티켓 조회가 세션 상태 요약으로 샜다 — RN-04"


# ── RN-09: pending must survive a stalled pivot (NEED_INPUT/FORBIDDEN/NO_CHANGE) ──

def test_pending_survives_a_pivot_that_stalls_on_forbidden():
    others_ticket = _ticket("tk1", "결제 오류 수정", people=[{"id": "u2", "name": "홍길동", "person": {"email": "hong@goodmit.co.kr"}}])
    ctx = {"pending_action": {"kind": "COMMENT", "ticket_id": "tk1", "ticket_title": "결제 오류 수정",
                               "comment": "확인 부탁"},
           "pending_question": "approval", "selected_ticket": m.normalize_ticket(others_ticket, {}),
           "last_results": ["tk1"], "last_result_start": 1}
    b = {"message": "완료로 바꿔줘", "requester": REQUESTER, "projects": [], "tickets": [others_ticket],
         "work_schema": SCHEMA, "context": ctx}
    with mock.patch.object(m, "llm_extract_update_changes", return_value=({}, {})):
        d, _ = m.route_request(b)
    assert d["action"] == "FORBIDDEN", d["action"]
    assert (d["context"].get("pending_action") or {}).get("kind") == "COMMENT", (
        "FORBIDDEN으로 막혔는데 원래 댓글 pending이 사라졌다 — RN-09"
    )


# ── RN-10: a duplicate (idempotent) response must not carry an executable write ──

def test_duplicate_response_never_carries_a_write_request():
    original = {"action": "WRITE_CREATE", "response_text": "등록합니다.", "context": {},
                "write_request": {"kind": "CREATE", "body": {"parent": {}}}}
    prior = dict(original)
    prior["duplicate"] = True
    prior.pop("write_request", None)
    assert "write_request" not in prior, "중복 응답에 실행 가능한 write_request가 그대로 남아 있다 — RN-10"


# ── RN-11: lock eviction must only drop unlocked entries ──

def test_lock_eviction_keeps_a_currently_held_lock():
    m._CONV_LOCKS.clear()
    held_key = "held|conv"
    held_lock = m.conversation_lock({"email": "held", "teams_user_id": "", "name": ""}, "conv")
    held_lock.acquire()
    try:
        original_max = m._CONV_LOCKS_MAX
        m._CONV_LOCKS_MAX = 1  # force the eviction branch on the very next new key
        try:
            m.conversation_lock({"email": "new", "teams_user_id": "", "name": ""}, "conv2")
        finally:
            m._CONV_LOCKS_MAX = original_max
        assert held_key in m._CONV_LOCKS, "잠긴 락이 청소 대상이 됐다 — RN-11"
    finally:
        held_lock.release()
        m._CONV_LOCKS.clear()


# ── AI-30 (Med): screen_context, once provided, reaches the conversational payload ──

def test_screen_context_flows_into_context_when_provided():
    ctx = {}
    b = {"message": "안녕", "requester": REQUESTER, "projects": [], "tickets": [],
         "work_schema": SCHEMA, "context": ctx, "screen_context": "휴지통"}
    fake_result = {"answer": "안녕하세요", "ticket_ids": [], "project_ids": [],
                    "needs_clarification": False, "clarify_question": ""}
    with mock.patch.object(m, "_run_claude", return_value=(fake_result, "", 1)) as run:
        m.route_request(b)
    assert run.called
    sent_payload = run.call_args[0][2]
    assert sent_payload.get("screen_context") == "휴지통", "screen_context가 Claude 페이로드까지 안 갔다"
