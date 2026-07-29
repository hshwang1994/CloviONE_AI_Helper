"""Runner unit tests (#34 phase 1: free-form Notion Q&A).

Run: RUNNER_TOKEN=test python -m pytest runner/claude-work-assistant/test_assistant.py
The CLI (subprocess.run) is mocked — no real Claude call.
"""
import base64
import importlib.util
import json
import os
import sqlite3
import unittest.mock as mock
from pathlib import Path

os.environ.setdefault("RUNNER_TOKEN", "test")

_spec = importlib.util.spec_from_file_location(
    "assistant", str(Path(__file__).with_name("assistant.py"))
)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)


def _fake_cli(structured):
    # claude CLI 2.1.x: structured output arrives in "result" as a JSON string.
    class C:
        returncode = 0
        stdout = json.dumps({"type": "result", "subtype": "success",
                             "result": json.dumps(structured, ensure_ascii=False)})
        stderr = ""
    return C()


def test_run_claude_parses_both_output_formats():
    payload_ok = {"answer": "1개", "ticket_ids": ["t1"], "project_ids": [],
                  "needs_clarification": False, "clarify_question": ""}
    # New format: result as JSON string
    with mock.patch.object(m.subprocess, "run", return_value=_fake_cli(payload_ok)):
        res, err, _ = m._run_claude(m.QUERY_SCHEMA, "p", {}, "i")
    assert res == payload_ok and err == ""

    # Legacy format: structured_output dict
    class Legacy:
        returncode = 0
        stdout = json.dumps({"structured_output": payload_ok})
        stderr = ""
    with mock.patch.object(m.subprocess, "run", return_value=Legacy()):
        res, err, _ = m._run_claude(m.QUERY_SCHEMA, "p", {}, "i")
    assert res == payload_ok

    # Failure: non-zero rc → retried once, then a human-friendly error (no raw stderr)
    class Fail:
        returncode = 1
        stdout = ""
        stderr = "boom"
    with mock.patch.object(m.subprocess, "run", return_value=Fail()) as run,          mock.patch.object(m.time, "sleep"):
        res, err, _ = m._run_claude(m.QUERY_SCHEMA, "p", {}, "i")
    assert run.call_count == 2, "transient CLI failure must be retried once"
    assert res is None and "다시 시도" in err and "boom" not in err


def test_run_claude_transient_failure_recovers_on_retry():
    payload_ok = {"answer": "ok", "ticket_ids": [], "project_ids": [],
                  "needs_clarification": False, "clarify_question": ""}
    class Fail:
        returncode = 1
        stdout = ""
        stderr = "transient"
    with mock.patch.object(m.subprocess, "run", side_effect=[Fail(), _fake_cli(payload_ok)]) as run,          mock.patch.object(m.time, "sleep"):
        res, err, _ = m._run_claude(m.QUERY_SCHEMA, "p", {}, "i")
    assert run.call_count == 2
    assert res == payload_ok and err == ""


TICKETS = [
    {"id": "t1", "ticket_id": "GIT-1", "title": "VPC 설계", "status": "계획", "priority": "중간",
     "difficulty": "", "due_date": "2026-05-22", "start_date": "", "assignees": [{"id": "u1", "name": "문의진"}],
     "project_ids": ["p1"], "project_names": ["포스코DX"]},
    {"id": "t2", "ticket_id": "GIT-2", "title": "포털 배포", "status": "진행", "priority": "높음",
     "difficulty": "", "due_date": "2026-06-01", "start_date": "", "assignees": [{"id": "u1", "name": "문의진"}],
     "project_ids": ["p1"], "project_names": ["포스코DX"]},
]
PROJECTS = [{"id": "p1", "name": "포스코DX", "status": "진행", "primary": [{"id": "u1", "name": "문의진"}], "secondary": []}]


def test_freeform_heuristic():
    assert m.is_freeform_query("내 티켓 요약해줘")
    assert m.is_freeform_query("가장 급한 티켓 뭐야")
    assert not m.is_freeform_query("내 티켓 보여줘")  # structured → rule engine


def test_claude_query_answer_and_cards():
    structured = {"answer": "가장 급한 건 GIT-2 입니다.", "ticket_ids": ["t2", "t1"],
                  "project_ids": ["p1"], "needs_clarification": False, "clarify_question": ""}
    with mock.patch.object(m.subprocess, "run", return_value=_fake_cli(structured)):
        data = m.claude_query("가장 급한 티켓", {}, {"email": "a@x", "name": "문의진"},
                              {"id": "u1"}, PROJECTS, TICKETS, {})
    assert data["action"] == "QUERY"
    assert [t["ticket_id"] for t in data["tickets"]] == ["GIT-2", "GIT-1"]  # ranked order preserved
    assert [p["name"] for p in data["projects"]] == ["포스코DX"]


def test_freeform_query_beats_update_false_positive():
    # Regression: '우선순위 기준으로 요약해줘' made is_update_intent fire (→ NEED_INPUT),
    # shadowing the query. Free-form must route to claude_query first.
    msg = "진행중인 티켓들을 우선순위 기준으로 한두 문장으로 요약해줘"
    # 이 문장에서 update 휴리스틱이 오발화하던 것은 '기준으로'를 그룹 축으로 알아보게 되면서
    # 원인 자체가 사라졌다. 자유 대화가 먼저 잡아야 한다는 요구는 그대로다.
    raw = {"id": "t1", "url": "", "properties": {
        "제목": {"type": "title", "title": [{"plain_text": "A"}]},
        "진행상태": {"type": "select", "select": {"name": "진행"}},
        "티켓 담당자": {"type": "people", "people": []}}}
    structured = {"answer": "진행 티켓 요약입니다.", "ticket_ids": ["t1"], "project_ids": [],
                  "needs_clarification": False, "clarify_question": ""}
    with mock.patch.object(m.subprocess, "run", return_value=_fake_cli(structured)) as run:
        data, _ = m.process_request({"message": msg, "requester": {"email": "x@y", "name": "황형섭"},
                                     "projects": [], "tickets": [raw], "work_schema": {}, "context": {}})
    assert run.called, "claude CLI should have been invoked (routed to claude_query)"
    assert data["action"] == "QUERY", data["action"]


def test_claude_query_clarification():
    structured = {"answer": "", "ticket_ids": [], "project_ids": [],
                  "needs_clarification": True, "clarify_question": "어느 프로젝트인가요?"}
    with mock.patch.object(m.subprocess, "run", return_value=_fake_cli(structured)):
        data = m.claude_query("그거", {}, {}, None, PROJECTS, TICKETS, {})
    assert data["action"] == "NEED_INPUT"
    assert "어느 프로젝트" in data["response_text"]


def test_claude_query_falls_back_to_rule_engine_on_cli_failure():
    class Fail:
        returncode = 1
        stdout = ""
        stderr = "boom"
    with mock.patch.object(m.subprocess, "run", return_value=Fail()):
        data = m.claude_query("내 티켓 요약", {}, {"email": "a@x", "name": "문의진"},
                              {"id": "u1"}, PROJECTS, TICKETS, {})
    # Falls back to query_tickets → still returns a structured response (not a crash).
    assert isinstance(data, dict) and data.get("action")


# --- #34 phase 2: 생성(create) LLM 에이전트화 -------------------------------
def _draft_cli(ready=True, fields=None, draft=None, questions=None, conflicts=None):
    structured = {
        "ready": ready,
        "review_summary": "작업 지시를 확인했습니다.",
        "questions": questions or [],
        "conflicts": conflicts or [],
        "agreements": [],
        "draft": draft or {"title": "로그인 버그 수정", "type": "버그", "background": "배경 설명",
                           "requirements": ["요구사항 1"], "acceptance_criteria": ["완료 조건 1"], "notes": []},
        "fields": fields or {"priority": "", "difficulty": 0, "estimate_wd": 2, "due_date": "",
                             "assignee_names": [], "unassigned": False},
    }
    return _fake_cli(structured)


def test_coerce_create_fields():
    assert m._coerce_priority("보통") == "중간"
    assert m._coerce_priority("상") == "높음"
    assert m._coerce_priority("하") == "낮음"
    assert m._coerce_priority("") == ""
    assert m._coerce_difficulty("보통") == 3
    assert m._coerce_difficulty(4) == 4
    assert m._coerce_difficulty(9) == 0       # out of range → unknown
    assert m._coerce_difficulty(True) == 0    # bool is not a level
    assert m._coerce_difficulty("2단계") == 2
    assert m._coerce_iso_date("2026-08-01") == "2026-08-01"
    assert m._coerce_iso_date("내일") == ""
    assert m._coerce_iso_date("2026-13-40") == ""   # not a real date
    assert m.create_missing_fields("", "", 0, [], False) == ["마감일", "우선순위", "난이도", "티켓 담당자"]
    assert m.create_missing_fields("2026-08-01", "높음", 3, [{"id": "u1"}], False) == []
    assert m.create_missing_fields("2026-08-01", "높음", 3, [], True) == []  # 미할당


def test_coerce_estimate_wd():
    # LLM 추정치는 가장 가까운 스케일 값으로 스냅한다.
    assert m.coerce_estimate_wd(3, 4) == 3.0
    assert m.coerce_estimate_wd(2, 3) == 2.0
    assert m.coerce_estimate_wd(6, 4) == 5.0        # 6 → 가장 가까운 스케일 5
    assert m.coerce_estimate_wd(10, 4) == 8.0       # 상한 초과 → 8
    assert m.coerce_estimate_wd(0.6, 4) == 0.5
    # 값이 없거나 이상하면 난이도로 폴백 — 항상 양수(무조건 채움).
    assert m.coerce_estimate_wd(0, 5) == 5.0
    assert m.coerce_estimate_wd(None, 2) == 1.0
    assert m.coerce_estimate_wd("", 6) == 8.0
    assert m.coerce_estimate_wd(0, 0) == 2.0        # 값·난이도 모두 없음 → 기본 2인일
    assert m.coerce_estimate_wd(True, 3) == 2.0     # bool은 값으로 안 침 → 난이도 3 → 2


def test_coerce_difficulty_longest_word_wins():
    # '어려움'(4)이 '매우어려움/아주어려움'(5)의 부분문자열이라 삽입순 루프가 먼저 걸려
    # 난이도 5가 4로 새어나갔다. 가장 긴 낱말이 이기도록 고쳤다.
    assert m._coerce_difficulty("매우어려움") == 5
    assert m._coerce_difficulty("아주어려움") == 5
    assert m._coerce_difficulty("매우쉬움") == 1
    assert m._coerce_difficulty("아주쉬움") == 1
    # 비회귀: 나머지는 그대로.
    assert m._coerce_difficulty("어려움") == 4
    assert m._coerce_difficulty("쉬움") == 2
    assert m._coerce_difficulty("보통") == 3
    assert m._coerce_difficulty("최상") == 6
    # 난이도 앵커를 거친 전체 경로도 5가 나온다(예전엔 4).
    assert m.extract_difficulty("난이도 매우어려움") == 5
    assert m.extract_difficulty("난이도 아주어려움") == 5
    assert m.extract_difficulty("난이도 어려움") == 4


def test_extract_priority_standalone_gate():
    # 조회·기본 경로는 '긴급' 단독을 우선순위로 인정한다(조회 필터에 필요).
    assert m.extract_priority("긴급 티켓 보여줘") == "높음"
    assert m.extract_priority("긴급") == "높음"
    # 쓰기·생성 경로(allow_standalone=False)는 부사·주제어로 쓰인 '긴급'을 우선순위로 읽지 않는다.
    assert m.extract_priority("긴급하게 이 티켓 마감일 내일로 바꿔줘", allow_standalone=False) == ""
    assert m.extract_priority("긴급 상황 대응 티켓 담당자 나로 바꿔줘", allow_standalone=False) == ""
    # 진짜 우선순위 지정은 standalone을 꺼도 여전히 잡힌다(앵커·지시자리·전체값 경로).
    assert m.extract_priority("우선순위 긴급으로 바꿔줘", allow_standalone=False) == "높음"
    assert m.extract_priority("긴급으로 바꿔줘", allow_standalone=False) == "높음"
    assert m.extract_priority("긴급", allow_standalone=False) == "높음"  # 전체가 값 하나


def test_is_arbitrary_delegation():
    # 티켓 필드를 봇에게 위임하는 표현만 True.
    assert m._is_arbitrary_delegation("아무렇게나 등록해줘") is True
    assert m._is_arbitrary_delegation("나머지는 알아서 해줘") is True
    assert m._is_arbitrary_delegation("적당히 만들어줘") is True
    assert m._is_arbitrary_delegation("알아서") is True
    # 요구사항 내용에 섞인 '알아서/적당히'는 위임이 아니다(예전엔 여기서 필드를 발명했다).
    assert m._is_arbitrary_delegation("결제 실패 시 재시도를 알아서 하도록 만들어줘") is False
    assert m._is_arbitrary_delegation("로그를 적당히 남기게 해줘") is False
    assert m._is_arbitrary_delegation("담당자가 알아서 처리하는 로직 티켓") is False


def test_property_value_number_is_defensive():
    num = {"type": "number"}
    assert m.property_value(num, 3) == {"number": 3.0}
    assert m.property_value(num, "2.5") == {"number": 2.5}
    assert m.property_value(num, None) == {"number": None}
    assert m.property_value(num, "") == {"number": None}
    # 비수치 값은 예외를 던지지 않고 None으로 흘린다(형제 분기와 동일 계약).
    assert m.property_value(num, "높음") is None
    assert m.property_value(num, ["a"]) is None


def test_build_create_body_includes_estimate_wd():
    schema = {"properties": {
        "제목": {"type": "title"}, "진행상태": {"type": "status"}, "마감일": {"type": "date"},
        "우선순위": {"type": "select"}, "난이도": {"type": "select"}, "예상 WD": {"type": "number"},
        "프로젝트": {"type": "relation"}, "티켓 담당자": {"type": "people"},
    }}
    context = {"selected_project": {"id": "p1"}, "status": "계획", "due_date": "2026-08-01",
               "priority": "높음", "difficulty": 4, "estimate_wd": 3.0, "assignee_ids": [],
               "original_request": "로그인 버그", "creator": {"name": "황형섭", "email": "a@goodmit.co.kr"},
               "agreements": []}
    draft = {"title": "로그인 버그 수정", "type": "버그", "background": "b",
             "requirements": ["r"], "acceptance_criteria": ["c"], "notes": []}
    body, err = m.build_create_body(schema, draft, context)
    assert err == ""
    assert body["properties"]["예상 WD"] == {"number": 3.0}


def test_build_create_body_maps_planning_status_to_actual_option():
    # 작업 DB의 계획 상태 옵션이 '예정'으로 개명돼 있으면, 생성도 수정처럼 실제 옵션명을 써야
    # 400(is not a valid option)을 피한다. 예전엔 리터럴 '계획'을 박아 거절됐다.
    schema = {"properties": {
        "제목": {"type": "title"},
        "진행상태": {"type": "status", "status": {"options": [
            {"name": "예정"}, {"name": "진행"}, {"name": "완료"}]}},
        "마감일": {"type": "date"}, "우선순위": {"type": "select"}, "난이도": {"type": "select"},
        "예상 WD": {"type": "number"}, "프로젝트": {"type": "relation"}, "티켓 담당자": {"type": "people"},
    }}
    context = {"selected_project": {"id": "p1"}, "status": "계획", "due_date": "2026-08-01",
               "priority": "높음", "difficulty": 4, "estimate_wd": 3.0, "assignee_ids": [],
               "original_request": "x", "creator": {"name": "황형섭"}, "agreements": []}
    draft = {"title": "t", "type": "버그", "background": "b",
             "requirements": ["r"], "acceptance_criteria": ["c"], "notes": []}
    body, err = m.build_create_body(schema, draft, context)
    assert err == ""
    assert body["properties"]["진행상태"] == {"status": {"name": "예정"}}


CREATE_PROJECTS = [{"id": "p1", "name": "포스코DX", "status": "진행", "primary": [], "secondary": [], "url": ""}]


def test_extract_difficulty_qualitative():
    # Rule parses qualitative difficulty anchored to 난이도, tolerant of any particle.
    assert m.extract_difficulty("난이도 보통으로 바꿔줘") == 3
    assert m.extract_difficulty("난이도를 어려움으로") == 4
    assert m.extract_difficulty("난이도도 보통으로 바꿔줘") == 3   # particle 도
    assert m.extract_difficulty("난이도만 어려움으로 해줘") == 4   # particle 만
    assert m.extract_difficulty("난이도 5") == 5
    # An unrelated "2단계"/digit must NOT be misread as difficulty (must be anchored).
    assert m.extract_difficulty("2단계 작업이야") == 0
    assert m.extract_difficulty("이번 스프린트 2단계 작업인데 난이도는 어려움으로 바꿔줘") == 4
    # Anchored: an unrelated priority word must NOT be read as difficulty.
    assert m.extract_difficulty("우선순위 보통으로 바꿔줘") == 0
    # '중간' is intentionally left to the LLM fallback (priority/difficulty ambiguous).
    assert m.extract_difficulty("난이도 중간") == 0


def test_priority_not_confused_by_difficulty_phrase():
    # "난이도 보통" must NOT leak into priority (보통 is also a priority alias) — for
    # any particle. Regression for the CRITICAL review finding (~도/~만 leaked before).
    assert m.extract_priority("난이도 보통으로 바꿔줘") == ""
    assert m.extract_priority("난이도도 낮음으로 해줘") == ""
    assert m.extract_priority("난이도만 보통으로 해줘") == ""
    assert m.extract_priority("완료로 바꾸고 난이도도 낮음으로 해줘") == ""
    assert m.extract_difficulty("난이도 보통으로 바꿔줘") == 3
    # A genuine priority mention still resolves, even alongside a difficulty phrase.
    assert m.extract_priority("우선순위 높음으로 바꿔줘") == "높음"
    assert m.extract_priority("난이도 보통, 우선순위 높음") == "높음"


def test_create_fills_difficulty_from_llm_fields():
    # Regression: the rule can't parse '중간' for difficulty, so the LLM fields.difficulty
    # must fill the gap and reach CREATE_PREVIEW instead of asking for 난이도 forever.
    assert m.extract_difficulty("난이도 중간") == 0  # rule engine still can't parse this one
    msg = ("포스코DX에 로그인 버그 수정 티켓 만들어줘. "
           "마감 2026-08-01, 우선순위 높음, 난이도 중간, 담당자 미할당.")
    fields = {"priority": "높음", "difficulty": 3, "due_date": "2026-08-01",
              "assignee_names": [], "unassigned": True}
    requester = {"email": "a@goodmit.co.kr", "name": "황형섭", "teams_user_id": "t1"}
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=True, fields=fields)) as run:
        data, _ = m.create_ticket(msg, {}, requester, None, [], CREATE_PROJECTS, {})
    assert run.called, "claude CLI should have been invoked for drafting/extraction"
    assert data["action"] == "CREATE_PREVIEW", data["action"]
    assert data["context"]["difficulty"] == 3
    assert "난이도: 3" in data["response_text"]


def test_create_always_sets_estimate_wd():
    requester = {"email": "a@goodmit.co.kr", "name": "황형섭", "teams_user_id": "t1"}
    # LLM이 예상 WD를 주면 그 값(스케일 스냅)이 컨텍스트와 미리보기에 들어간다.
    msg = "포스코DX에 로그인 버그 티켓 만들어줘. 마감 2026-08-01, 우선순위 높음, 난이도 4, 담당자 미할당."
    fields = {"priority": "높음", "difficulty": 4, "estimate_wd": 3, "due_date": "2026-08-01",
              "assignee_names": [], "unassigned": True}
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=True, fields=fields)):
        data, _ = m.create_ticket(msg, {}, requester, None, [], CREATE_PROJECTS, {})
    assert data["action"] == "CREATE_PREVIEW", data["action"]
    assert data["context"]["estimate_wd"] == 3.0
    assert "예상 WD: 3인일" in data["response_text"]  # :g 포맷 — 정수 공수는 소수점 없이
    # LLM이 예상 WD를 빠뜨려도(0) 난이도로 폴백해 무조건 채운다. 난이도는 대화에 없어 LLM 필드(5)를 쓴다.
    msg2 = "포스코DX에 로그인 버그 티켓 만들어줘. 마감 2026-08-01, 우선순위 높음, 담당자 미할당."
    fields2 = {"priority": "높음", "difficulty": 5, "estimate_wd": 0, "due_date": "2026-08-01",
               "assignee_names": [], "unassigned": True}
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=True, fields=fields2)):
        data2, _ = m.create_ticket(msg2, {}, requester, None, [], CREATE_PROJECTS, {})
    assert data2["action"] == "CREATE_PREVIEW", data2["action"]
    assert data2["context"]["difficulty"] == 5
    assert data2["context"]["estimate_wd"] == 5.0    # 난이도 5 → 5인일 폴백


def test_arbitrary_delegation_does_not_overwrite_stated_values():
    requester = {"email": "a@goodmit.co.kr", "name": "황형섭", "teams_user_id": "t1"}
    # '난이도 중간'은 규칙이 못 뽑지만(중간은 난이도 어휘에서 제외) LLM이 3으로 채운다.
    # '나머지는 알아서'가 있어도 이 3을 1로 덮으면 안 된다(기본값은 병합 뒤 빈 값에만).
    msg = "포스코DX에 로그인 버그 티켓 만들어줘. 난이도 중간이고 나머지는 알아서 해줘. 마감 2026-08-01, 담당자 미할당."
    fields = {"priority": "", "difficulty": 3, "estimate_wd": 2, "due_date": "2026-08-01",
              "assignee_names": [], "unassigned": True}
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=True, fields=fields)):
        data, _ = m.create_ticket(msg, {}, requester, None, [], CREATE_PROJECTS, {})
    assert data["action"] == "CREATE_PREVIEW", data["action"]
    assert data["context"]["difficulty"] == 3          # LLM 값이 살아남음(1로 덮이지 않음)
    assert data["context"]["priority"] == "낮음"        # 안 준 값만 위임 기본값으로 채움


def test_create_does_not_treat_past_time_expression_as_due():
    requester = {"email": "a@goodmit.co.kr", "name": "황형섭", "teams_user_id": "t1"}
    # '지난주에 발생한'은 발생 시점이지 마감이 아니다. 마감 앵커도 없다. 과거 날짜를 마감일로
    # 둔갑시키지 말고, 마감일이 비었으니 되물어야 한다.
    msg = "포스코DX에 지난주에 발생한 로그인 버그 티켓 만들어줘. 우선순위 높음, 난이도 4, 담당자 미할당."
    fields = {"priority": "높음", "difficulty": 4, "estimate_wd": 2, "due_date": "",
              "assignee_names": [], "unassigned": True}
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=True, fields=fields)):
        data, _ = m.create_ticket(msg, {}, requester, None, [], CREATE_PROJECTS, {})
    assert data["action"] == "NEED_INPUT", data["action"]
    assert "마감일" in data["response_text"]
    assert data["context"].get("due_date") in ("", None)   # 과거 날짜가 마감일로 들어가지 않음


def test_ready_false_but_fields_complete_promotes_to_preview():
    # #11 게이트 방어: 규칙이 필수값을 다 확정했고 충돌도 없고 초안 제목도 있는데 LLM이
    # (확정 필드를 무시하고) ready=false로 필수 항목을 되물으면, 이미 답한 걸 다시 묻지 말고
    # 미리보기로 승격한다. 긴 대화에서 답한 턴이 대화창 밖으로 밀린 상황의 백스톱.
    requester = {"email": "a@goodmit.co.kr", "name": "황형섭", "teams_user_id": "t1"}
    msg = "포스코DX에 로그인 버그 티켓 만들어줘. 마감 2026-08-05, 우선순위 높음, 난이도 3, 담당자 미할당."
    q = [{"question": "담당자가 누구인가요?", "reason": "필수 필드", "options": []}]
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=False, questions=q)):
        data, _ = m.create_ticket(msg, {}, requester, None, [], CREATE_PROJECTS, {})
    assert data["action"] == "CREATE_PREVIEW", data["action"]
    assert data["context"]["priority"] == "높음"
    assert data["context"]["difficulty"] == 3


def test_ready_false_with_conflict_still_asks_and_renders():
    # 충돌이 있으면 필수값이 다 있어도 미리보기로 승격하지 않고 되묻는다. conflicts를 화면에
    # 렌더해 사용자가 왜 막혔는지(A/B 맥락) 볼 수 있어야 한다.
    requester = {"email": "a@goodmit.co.kr", "name": "황형섭", "teams_user_id": "t1"}
    msg = "포스코DX에 로그인 버그 티켓 만들어줘. 마감 2026-08-05, 우선순위 높음, 난이도 3, 담당자 미할당."
    conflicts = ["앞서 마감을 금요일이라 하셨는데 지금은 다음 주라고 하셨습니다."]
    with mock.patch.object(m.subprocess, "run",
                           return_value=_draft_cli(ready=False, conflicts=conflicts)):
        data, _ = m.create_ticket(msg, {}, requester, None, [], CREATE_PROJECTS, {})
    assert data["action"] == "NEED_INPUT", data["action"]
    assert "[충돌]" in data["response_text"]
    assert "금요일" in data["response_text"]


def test_create_llm_not_ready_asks_natural_question():
    msg = "포스코DX에 티켓 만들어줘. 담당자 미할당."
    questions = [{"question": "마감일이 언제인가요?", "reason": "필수값입니다.", "options": ["내일", "다음 주 금요일"]}]
    fields = {"priority": "", "difficulty": 0, "due_date": "", "assignee_names": [], "unassigned": True}
    requester = {"email": "a@goodmit.co.kr", "name": "황형섭", "teams_user_id": "t1"}
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=False, fields=fields, questions=questions)):
        data, _ = m.create_ticket(msg, {}, requester, None, [], CREATE_PROJECTS, {})
    assert data["action"] == "NEED_INPUT", data["action"]
    assert "마감일이 언제인가요?" in data["response_text"]


def test_create_not_ready_text_is_scannable():
    # 사용자 신고: "구분도 없고 줄바꿈도 없어서 뭘 원하는지 모르겠음." 되묻는 글은
    # (1) 요약과 질문 사이가 빈 줄로 갈리고, (2) 질문에 번호가 붙고, (3) 선택지는
    # 그 질문에 들여쓰기로 딸리고, (4) '확인 이유'는 적지 않는다 — 질문을 뒤집어
    # 말한 것뿐이라 사용자에게 쓸모가 없다.
    msg = "포스코DX에 티켓을 생성하자"
    questions = [
        {"question": "티켓으로 만들 작업 내용이 무엇인가요?", "reason": "메시지에 작업 내용이 없음", "options": []},
        {"question": "이 티켓의 담당자는 누구인가요?", "reason": "필수 필드인 담당자 정보가 대화에 없음",
         "options": ["나(요청자 본인)", "미할당"]},
    ]
    fields = {"priority": "", "difficulty": 0, "due_date": "", "assignee_names": [], "unassigned": False}
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=False, fields=fields, questions=questions)):
        data, _ = m.create_ticket(msg, {}, CREATE_REQUESTER, CREATE_CURRENT_USER,
                                  CREATE_DIRECTORY, CREATE_PROJECTS, {})
    assert data["action"] == "NEED_INPUT", data["action"]
    body = data["response_text"]
    lines = body.split("\n")
    assert lines[0] == "작업 지시를 확인했습니다."          # 요약 한 줄
    assert lines[1] == ""                                   # 요약과 질문을 가르는 빈 줄
    assert lines[2] == "1. 티켓으로 만들 작업 내용이 무엇인가요?"
    assert lines[3] == "2. 이 티켓의 담당자는 누구인가요?"
    assert lines[4] == "   선택지: 나(요청자 본인) / 미할당"   # 질문에 딸린 줄(들여쓰기)
    assert "확인 이유" not in body
    assert "필수 필드인 담당자 정보가 대화에 없음" not in body
    # reason은 화면에서만 뺀다 — 모델이 질문마다 근거를 대게 하는 값이라 스키마엔 남는다.
    assert "reason" in m.DRAFT_SCHEMA["properties"]["questions"]["items"]["required"]


def test_create_preview_headers_are_bracketed():
    # 미리보기의 '배경/요구사항/완료 조건'은 맨 글자였다 — 화면이 제목인지 본문인지
    # 알 수 없어 배경 문장과 같은 크기로 그렸다. 이 파일이 이미 쓰는 대괄호 관례로 맞춘다.
    msg = "포스코DX에 로그인 버그 수정 티켓 만들어줘. 담당자 미할당. 마감 2026-08-01, 우선순위 높음, 난이도 3."
    fields = {"priority": "높음", "difficulty": 3, "due_date": "2026-08-01",
              "assignee_names": [], "unassigned": True}
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=True, fields=fields)):
        data, _ = m.create_ticket(msg, {}, CREATE_REQUESTER, CREATE_CURRENT_USER,
                                  CREATE_DIRECTORY, CREATE_PROJECTS, {})
    assert data["action"] == "CREATE_PREVIEW", data["action"]
    lines = data["response_text"].split("\n")
    for head in ("[배경]", "[요구사항]", "[완료 조건]"):
        assert head in lines, f"{head} 없음: {lines}"
        # 머리글 앞은 빈 줄이어야 화면이 문단을 가른다.
        assert lines[lines.index(head) - 1] == ""


def test_create_ready_but_field_missing_still_gated():
    # LLM says ready but genuinely couldn't supply a required field → we still ask,
    # so a malformed draft never silently becomes a ticket with a blank due date.
    msg = "포스코DX에 로그인 버그 수정 티켓 만들어줘. 담당자 미할당."
    fields = {"priority": "높음", "difficulty": 3, "due_date": "", "assignee_names": [], "unassigned": True}
    requester = {"email": "a@goodmit.co.kr", "name": "황형섭", "teams_user_id": "t1"}
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=True, fields=fields)):
        data, _ = m.create_ticket(msg, {}, requester, None, [], CREATE_PROJECTS, {})
    assert data["action"] == "NEED_INPUT", data["action"]
    assert "마감일" in data["response_text"]


CREATE_DIRECTORY = [
    {"id": "u1", "name": "황형섭", "email": "a@goodmit.co.kr"},
    {"id": "u2", "name": "홍길동", "email": "hong@goodmit.co.kr"},
]
CREATE_CURRENT_USER = {"id": "u1", "name": "황형섭", "email": "a@goodmit.co.kr"}
CREATE_REQUESTER = {"email": "a@goodmit.co.kr", "name": "황형섭", "teams_user_id": "t1"}


def test_create_persists_assignee_across_turns():
    # HIGH regression: an assignee resolved on turn 1 must survive a turn-2 reply that
    # only supplies the remaining fields — never silently reassigned to the requester.
    turn1 = "포스코DX에 홍길동 담당으로 로그인 버그 수정 티켓 만들어줘."
    empty = {"priority": "", "difficulty": 0, "due_date": "", "assignee_names": [], "unassigned": False}
    q = [{"question": "마감일·우선순위·난이도를 알려주세요.", "reason": "필수값", "options": []}]
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=False, fields=empty, questions=q)):
        data1, _ = m.create_ticket(turn1, {}, CREATE_REQUESTER, CREATE_CURRENT_USER,
                                   CREATE_DIRECTORY, CREATE_PROJECTS, {})
    assert data1["action"] == "NEED_INPUT", data1["action"]
    ctx1 = data1["context"]
    assert [p.get("id") for p in ctx1.get("assignee_people", [])] == ["u2"]  # 홍길동 persisted

    turn2 = "마감 2026-08-01, 우선순위 높음, 난이도 3."
    fields2 = {"priority": "높음", "difficulty": 3, "due_date": "2026-08-01", "assignee_names": [], "unassigned": False}
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=True, fields=fields2)):
        data2, _ = m.create_ticket(turn2, ctx1, CREATE_REQUESTER, CREATE_CURRENT_USER,
                                   CREATE_DIRECTORY, CREATE_PROJECTS, {})
    assert data2["action"] == "CREATE_PREVIEW", data2["action"]
    assert data2["context"]["assignee_names"] == ["홍길동"], data2["context"]["assignee_names"]
    assert "홍길동" in data2["response_text"]


def test_coerce_priority_never_invents():
    # HIGH regression: an explanatory phrase must NOT be coerced into a real priority.
    for phrase in ["상관없어요", "중요하지 않음", "잘 모르겠음", "아무거나"]:
        assert m._coerce_priority(phrase) == "", phrase
    assert m._coerce_priority("높음") == "높음"
    assert m._coerce_priority("상") == "높음"
    assert m._coerce_priority("중") == "중간"
    assert m._coerce_priority("하") == "낮음"


def test_create_consumes_llm_assignee_names():
    # Rule matcher misses the assignee, but the LLM extracts it → resolve exact match.
    msg = "포스코DX 로그인 버그 티켓 등록해줘. 마감 2026-08-01 우선순위 높음 난이도 3."
    fields = {"priority": "높음", "difficulty": 3, "due_date": "2026-08-01",
              "assignee_names": ["hong@goodmit.co.kr"], "unassigned": False}
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=True, fields=fields)):
        data, _ = m.create_ticket(msg, {}, CREATE_REQUESTER, CREATE_CURRENT_USER,
                                  CREATE_DIRECTORY, CREATE_PROJECTS, {})
    assert data["action"] == "CREATE_PREVIEW", data["action"]
    assert data["context"]["assignee_names"] == ["홍길동"], data["context"]["assignee_names"]


# --- #34 phase 2: update(수정) LLM 폴백 (규칙이 못 찾으면 LLM 추출 → 확인 미리보기) ---
UPDATE_SCHEMA = {"properties": {
    "제목": {"type": "title"}, "진행상태": {"type": "status"}, "우선순위": {"type": "select"},
    "난이도": {"type": "select"}, "마감일": {"type": "date"}, "시작일": {"type": "date"},
    "티켓 담당자": {"type": "people"},
}}
UPDATE_TICKET = {
    "id": "tk1", "title": "로그인 버그", "status": "진행", "priority": "중간", "difficulty": "",
    "due_date": "2026-08-01", "start_date": "", "ticket_id": "GIT-9",
    "assignees": [CREATE_CURRENT_USER], "project_id": "p1", "project_ids": ["p1"],
    "project_names": ["포스코DX"], "url": "",
}


def test_update_llm_extracts_and_previews():
    # Rules find no change in "좀 더 쉽게 해줘"; the LLM infers a difficulty change,
    # which must go through a CONFIRMATION preview — never a silent direct write.
    msg = "로그인 버그 티켓 좀 더 쉽게 해줘"
    extract = {"has_change": True, "status": "", "priority": "", "difficulty": 2,
               "due_date": "", "clear_due": False}
    status_map = {"진행": "진행", "완료": "완료", "계획": "계획"}
    with mock.patch.object(m.subprocess, "run", return_value=_fake_cli(extract)) as run:
        data = m.update_ticket(msg, {}, CREATE_REQUESTER, CREATE_CURRENT_USER,
                               CREATE_DIRECTORY, [UPDATE_TICKET], UPDATE_SCHEMA, status_map)
    assert run.called, "LLM extractor should have been called"
    assert data["action"] == "UPDATE_PREVIEW", data["action"]
    assert "write_request" not in data           # confirmation, not a direct write
    pending = data["context"]["pending_action"]
    assert pending["changes"].get("difficulty") == 2
    assert pending.get("needs_confirmation") is True


def test_update_compound_message_fills_missing_field():
    # Rules parse the status change; 난이도 is mentioned but unparsed ("낮춰줘") → the
    # LLM must FILL it (not silently drop it), and the whole update goes to confirmation.
    msg = "로그인 버그 완료로 바꾸고 난이도도 낮춰줘"
    extract = {"has_change": True, "status": "", "priority": "", "difficulty": 2,
               "due_date": "", "clear_due": False}
    status_map = {"완료": "완료", "진행": "진행", "계획": "계획"}
    with mock.patch.object(m.subprocess, "run", return_value=_fake_cli(extract)) as run:
        data = m.update_ticket(msg, {}, CREATE_REQUESTER, CREATE_CURRENT_USER,
                               CREATE_DIRECTORY, [UPDATE_TICKET], UPDATE_SCHEMA, status_map)
    assert run.called, "LLM should fill the unparsed 난이도 mention"
    assert data["action"] == "UPDATE_PREVIEW", data["action"]
    changes = data["context"]["pending_action"]["changes"]
    assert changes.get("status") == "완료"       # rule-parsed field kept
    assert changes.get("difficulty") == 2        # LLM-filled gap


def test_update_llm_no_change_still_asks():
    msg = "로그인 버그 티켓 어떻게 생각해?"
    extract = {"has_change": False, "status": "", "priority": "", "difficulty": 0,
               "due_date": "", "clear_due": False}
    with mock.patch.object(m.subprocess, "run", return_value=_fake_cli(extract)):
        data = m.update_ticket(msg, {}, CREATE_REQUESTER, CREATE_CURRENT_USER,
                               CREATE_DIRECTORY, [UPDATE_TICKET], UPDATE_SCHEMA, {"진행": "진행"})
    assert data["action"] == "NEED_INPUT", data["action"]
    assert "어떤 값을 변경할지" in data["response_text"]


# --- #34 phase 2: 이미지 (비전 인제스트 · 라우팅 · 하드닝) ---------------------
PNG_1PX = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
           "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def _vision_cli():
    return _fake_cli({"summary": "로그인 500 에러 화면", "ocr_text": "TypeError: x is null",
                      "notable": ["콘솔에 TypeError"], "suggested_title": "로그인 500 오류"})


def test_ingest_image_saves_analyzes_and_notes(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "IMAGE_DIR", str(tmp_path))
    atts = [{"filename": "err.png", "media_type": "image/png", "data": PNG_1PX}]
    with mock.patch.object(m.subprocess, "run", return_value=_vision_cli()) as run:
        ctx, ai_ms = m.ingest_image_attachments(atts, {}, "conv-1", "이 에러 봐줘", "m1")
    assert run.called
    notes = ctx["image_notes"]
    assert len(notes) == 1
    assert notes[0]["summary"] == "로그인 500 에러 화면"
    assert notes[0]["ocr_text"] == "TypeError: x is null"
    # File persisted under the conversation dir with a GENERATED name (never user's).
    files = list((tmp_path / "conv-1").iterdir())
    assert len(files) == 1 and files[0].suffix == ".png" and "err" not in files[0].name


def test_ingest_rejects_fake_and_degrades_on_cli_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "IMAGE_DIR", str(tmp_path))
    import base64 as _b64
    fake = [{"filename": "x.png", "media_type": "image/png",
             "data": _b64.b64encode(b"<svg onload=alert(1)>").decode()}]
    with mock.patch.object(m.subprocess, "run") as run:
        ctx, ai_ms = m.ingest_image_attachments(fake, {"a": 1}, "c", "msg", "m2")
    assert not run.called            # nothing saved → no vision call
    assert ctx == {"a": 1} and ai_ms == 0

    class Fail:
        returncode = 1
        stdout = ""
        stderr = "boom"
    good = [{"filename": "e.png", "media_type": "image/png", "data": PNG_1PX}]
    with mock.patch.object(m.subprocess, "run", return_value=Fail()):
        ctx2, _ = m.ingest_image_attachments(good, {}, "c2", "msg", "m3")
    assert "분석에 실패" in ctx2["image_notes"][0]["summary"]  # graceful note, no crash


def test_image_message_routes_to_conversational_query(tmp_path, monkeypatch):
    # Image + plain remark ("이거 봐줘") → vision then claude_query (conversational).
    monkeypatch.setattr(m, "IMAGE_DIR", str(tmp_path))
    query_cli = _fake_cli({"answer": "로그인 500 에러 화면이네요. TypeError가 원인으로 보입니다.",
                           "ticket_ids": [], "project_ids": [],
                           "needs_clarification": False, "clarify_question": ""})
    with mock.patch.object(m.subprocess, "run", side_effect=[_vision_cli(), query_cli]) as run:
        data, ai_ms = m.process_request({
            "message": "이 스크린샷 봐줘", "message_id": "mi1", "conversation_id": "cv1",
            "requester": {"email": "a@goodmit.co.kr", "name": "황형섭"},
            "projects": [], "tickets": [], "work_schema": {}, "context": {},
            "attachments": [{"filename": "e.png", "media_type": "image/png", "data": PNG_1PX}],
        })
    assert run.call_count == 2, "vision + query 두 번의 CLI 호출"
    assert data["action"] == "QUERY"
    assert "TypeError" in data["response_text"]
    # Notes persist in context for follow-up turns; history accumulated for flow.
    assert data["context"]["image_notes"][0]["ocr_text"] == "TypeError: x is null"
    assert data["context"]["conversation_history"][-1]["role"] == "assistant"


def test_update_unresolvable_target_never_calls_llm():
    # Hardening: no ticket can be resolved → NEED_INPUT without any CLI spend.
    with mock.patch.object(m.subprocess, "run") as run:
        data = m.update_ticket("존재하지않는것 좀 바꿔줘", {}, CREATE_REQUESTER,
                               CREATE_CURRENT_USER, CREATE_DIRECTORY, [UPDATE_TICKET],
                               UPDATE_SCHEMA, {"진행": "진행"})
    assert not run.called
    assert data["action"] == "NEED_INPUT"


def test_confirm_revalidates_ownership():
    # Between preview and "변경해줘" the ticket was reassigned → confirm must refuse.
    pending_ctx = {"pending_action": {"kind": "UPDATE", "ticket_id": "tk1",
                                      "changes": {"difficulty": 2}, "needs_confirmation": True}}
    reassigned = {**UPDATE_TICKET, "assignees": [{"id": "u9", "name": "다른사람"}]}
    out = m.handle_confirmation(pending_ctx, UPDATE_SCHEMA, [reassigned],
                                CREATE_CURRENT_USER, CREATE_REQUESTER)
    assert out["action"] == "FORBIDDEN"
    assert "pending_action" not in out["context"]
    # Ticket vanished entirely → clear pending and ask to re-query.
    out2 = m.handle_confirmation(pending_ctx, UPDATE_SCHEMA, [],
                                 CREATE_CURRENT_USER, CREATE_REQUESTER)
    assert out2["action"] == "NEED_INPUT"
    # Still owned → write proceeds with the SAME changes.
    out3 = m.handle_confirmation(pending_ctx, UPDATE_SCHEMA, [UPDATE_TICKET],
                                 CREATE_CURRENT_USER, CREATE_REQUESTER)
    assert out3["action"] == "WRITE_UPDATE"
    assert out3["write_request"]["page_id"] == "tk1"


# --- 적대 리뷰 후속 회귀 (vision timeout · update 라우팅 · project_ids · dedup) ---
def test_vision_timeout_degrades_gracefully(tmp_path, monkeypatch):
    # subprocess.TimeoutExpired must NOT 504 the whole message — failure note instead.
    monkeypatch.setattr(m, "IMAGE_DIR", str(tmp_path))
    def boom(*a, **kw):
        raise m.subprocess.TimeoutExpired(cmd="claude", timeout=60)
    with mock.patch.object(m.subprocess, "run", side_effect=boom):
        ctx, ai_ms = m.ingest_image_attachments(
            [{"filename": "e.png", "media_type": "image/png", "data": PNG_1PX}],
            {}, "cv-t", "봐줘", "mt1")
    assert "분석에 실패" in ctx["image_notes"][0]["summary"]


def test_vision_not_rerun_for_same_message_id(tmp_path, monkeypatch):
    # Worker retry re-sends the same message_id → reuse the persisted note.
    monkeypatch.setattr(m, "IMAGE_DIR", str(tmp_path))
    prior = {"image_notes": [{"message_id": "dup1", "summary": "이미 분석됨",
                              "ocr_text": "", "notable": [], "suggested_title": "", "files": "e.png",
                              "analyzed_at": "2026-07-15T13:00:00+09:00"}]}
    with mock.patch.object(m.subprocess, "run") as run:
        ctx, ai_ms = m.ingest_image_attachments(
            [{"filename": "e.png", "media_type": "image/png", "data": PNG_1PX}],
            prior, "cv-d", "다시", "dup1")
    assert not run.called and ai_ms == 0
    assert ctx is prior


def test_image_with_explicit_update_still_reaches_write_flow(tmp_path, monkeypatch):
    # "…으로 바꿔줘" + image must go to update_ticket (direct write), not claude_query.
    monkeypatch.setattr(m, "IMAGE_DIR", str(tmp_path))
    raw_ticket = {"id": "tk1", "url": "", "properties": {
        "제목": {"type": "title", "title": [{"plain_text": "로그인 버그"}]},
        "진행상태": {"type": "status", "status": {"name": "진행"}},
        "티켓 담당자": {"type": "people", "people": [{"id": "u1", "name": "황형섭",
            "person": {"email": "a@goodmit.co.kr"}}]}}}
    schema = {"properties": {"진행상태": {"type": "status", "status": {"options": [
        {"name": "계획"}, {"name": "진행"}, {"name": "완료"}]}}}}
    with mock.patch.object(m.subprocess, "run", return_value=_vision_cli()) as run:
        data, _ = m.process_request({
            "message": "로그인 버그 완료로 바꿔줘", "message_id": "mu1", "conversation_id": "cvu",
            "requester": {"email": "a@goodmit.co.kr", "name": "황형섭"},
            "projects": [], "tickets": [raw_ticket], "work_schema": schema, "context": {},
            "attachments": [{"filename": "e.png", "media_type": "image/png", "data": PNG_1PX}],
        })
    assert run.call_count == 1, "vision만 1회 — update는 규칙 직접 쓰기"
    assert data["action"] == "WRITE_UPDATE", data["action"]
    assert data["context"]["image_notes"], "이미지 노트는 컨텍스트에 남아야 함"


def test_bulk_candidates_respect_selected_project():
    # Regression: filter used nonexistent 'project_id' key → always emptied candidates.
    t_in = {**UPDATE_TICKET, "id": "in1", "title": "A작업", "status": "계획"}
    t_out = {**UPDATE_TICKET, "id": "out1", "title": "B작업", "status": "계획", "project_ids": ["p9"]}
    ctx = {"selected_project": {"id": "p1", "name": "포스코DX"}}
    with mock.patch.object(m.subprocess, "run") as run:
        data = m.update_ticket("계획 티켓을 진행으로 바꿔줘", ctx, CREATE_REQUESTER,
                               CREATE_CURRENT_USER, CREATE_DIRECTORY, [t_in, t_out],
                               UPDATE_SCHEMA, {"계획": "계획", "진행": "진행"})
    assert not run.called
    # Single owned in-project candidate → direct write to it (not 특정못함).
    assert data["action"] == "WRITE_UPDATE", data["action"]
    assert data["write_request"]["page_id"] == "in1"


# --- 버그사냥 루프 확정건 회귀 -------------------------------------------------
def test_double_approval_does_not_dispatch_twice():
    # HIGH: '응' 두 번(동기화 도착 전) → 두 번째는 처리중 안내, write_request 재발행 금지.
    ctx = {"pending_action": {"kind": "CREATE"}, "pending_question": "approval",
           "ticket_draft": {"title": "T", "background": "b", "requirements": [],
                            "acceptance_criteria": [], "notes": [], "due_date": "2026-08-01"},
           "selected_project": {"id": "p1", "name": "포스코DX"},
           "due_date": "2026-08-01", "priority": "높음", "difficulty": 3,
           "assignee_ids": [], "creator": {"name": "황형섭", "email": "a@goodmit.co.kr"},
           "status": "계획"}
    schema = {"properties": {"제목": {"type": "title"}, "진행상태": {"type": "status"},
              "마감일": {"type": "date"}, "우선순위": {"type": "select"},
              "난이도": {"type": "select"}, "프로젝트": {"type": "relation"}}}
    first = m.handle_confirmation(ctx, schema, [], CREATE_CURRENT_USER, CREATE_REQUESTER)
    assert first["action"] == "WRITE_CREATE" and "write_request" in first
    assert first["context"]["pending_action"].get("dispatched_at")
    second = m.handle_confirmation(first["context"], schema, [], CREATE_CURRENT_USER, CREATE_REQUESTER)
    assert second["action"] == "PENDING_ACTION_STATUS"
    assert "write_request" not in second


def test_ticket_selection_number_reply_keeps_original_change():
    # MEDIUM: 다중 후보 → '2번' 응답이 원래 변경값(진행)을 그대로 적용해야 한다.
    t1 = {**UPDATE_TICKET, "id": "s1", "title": "A작업", "status": "계획"}
    t2 = {**UPDATE_TICKET, "id": "s2", "title": "B작업", "status": "계획"}
    smap = {"계획": "계획", "진행": "진행"}
    with mock.patch.object(m.subprocess, "run") as run:
        ask = m.update_ticket("계획 티켓을 진행으로 바꿔줘", {}, CREATE_REQUESTER,
                              CREATE_CURRENT_USER, CREATE_DIRECTORY, [t1, t2], UPDATE_SCHEMA, smap)
    assert ask["action"] == "NEED_INPUT"
    ctx = ask["context"]
    assert ctx.get("pending_original_message")
    with mock.patch.object(m.subprocess, "run") as run:
        done = m.update_ticket("2번", ctx, CREATE_REQUESTER, CREATE_CURRENT_USER,
                               CREATE_DIRECTORY, [t1, t2], UPDATE_SCHEMA, smap)
    assert not run.called, "번호 응답은 LLM 없이 원문 병합으로 해결"
    assert done["action"] == "WRITE_UPDATE", done["action"]
    assert done["write_request"]["page_id"] == "s2"
    assert done["changes"].get("status") == "진행"


def test_create_does_not_fold_query_pending_original():
    # round2 확정(교차 모달 누출): create_ticket가 mode 무관하게 pending_original_message를
    # 접어, 조회(QUERY)가 남긴 문장의 우선순위가 생성 미리보기로 샜다. CREATE가 남긴 원본만 접어야.
    query_ctx = {  # 조회 프로젝트 모호 턴이 남긴 상태(mode:QUERY)
        "mode": "QUERY", "pending_question": "project_selection",
        "project_candidates": [{"id": "q1", "name": "결제시스템개편"}, {"id": "q2", "name": "결제시스템고도화"}],
        "pending_original_message": "결제시스템에서 우선순위 높은 티켓 보여줘",
    }
    fields = {"priority": "", "difficulty": 0, "due_date": "", "assignee_names": [], "unassigned": True}
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=True, fields=fields)):
        data, _ = m.create_ticket("프로젝트 없이 회의록 정리 티켓 만들어줘 마감 아무렇게나 미할당",
                                  query_ctx, CREATE_REQUESTER, CREATE_CURRENT_USER,
                                  CREATE_DIRECTORY, CREATE_PROJECTS, {})
    assert data["action"] == "CREATE_PREVIEW", data["action"]
    # 조회의 '우선순위 높은'이 생성으로 새면 안 된다 — '아무렇게나' 기본값(낮음)이어야.
    assert "우선순위: 낮음" in data["response_text"], data["response_text"]
    assert "우선순위: 높음" not in data["response_text"]


def _two_owned_planning(prio_a="중간", prio_b="낮음"):
    a = {**UPDATE_TICKET, "id": "s1", "title": "A작업", "status": "계획", "priority": prio_a}
    b = {**UPDATE_TICKET, "id": "s2", "title": "B작업", "status": "계획", "priority": prio_b}
    return a, b


def test_update_no_change_then_correction_is_applied():
    # round2 확정(HIGH, create 결함의 형제): 다중 후보 선택 뒤 NO_CHANGE가 ticket_selection과
    # pending_original을 남겨, 이어지는 정정이 재주입된 원본에 조용히 덮이고 NO_CHANGE 무한 루프.
    a, b = _two_owned_planning(prio_a="높음")  # A는 이미 높음
    smap = {"계획": "계획", "진행": "진행"}
    with mock.patch.object(m, "llm_extract_update_changes", return_value=({}, {})):
        ask = m.update_ticket("계획 티켓 우선순위 높음으로 바꿔줘", {}, CREATE_REQUESTER,
                              CREATE_CURRENT_USER, CREATE_DIRECTORY, [a, b], UPDATE_SCHEMA, smap)
        assert ask["action"] == "NEED_INPUT", ask["action"]
        nc = m.update_ticket("1번", ask["context"], CREATE_REQUESTER, CREATE_CURRENT_USER,
                             CREATE_DIRECTORY, [a, b], UPDATE_SCHEMA, smap)
        assert nc["action"] == "NO_CHANGE", nc["action"]  # A가 이미 높음
        # 정정: A를 낮음으로. 재주입된 '높음'에 덮이지 않고 실제로 낮음이 적용돼야 한다.
        done = m.update_ticket("1번 낮음으로 바꿔줘", nc["context"], CREATE_REQUESTER,
                               CREATE_CURRENT_USER, CREATE_DIRECTORY, [a, b], UPDATE_SCHEMA, smap)
    assert done["action"] == "WRITE_UPDATE", done["action"]
    assert done["write_request"]["page_id"] == "s1"
    assert done["changes"].get("priority") == "낮음", done["changes"]


def test_ticket_selection_number_with_value_applies():
    # 다중 후보에서 번호와 값을 함께 말하면('1번 높음으로 바꿔줘') 그 티켓에 정확히 반영된다.
    # (값없음 되물음 뒤 값만 답하는 분리 흐름은 지원하지 않는다 — 별도 잠금 상태가 회귀를
    #  반복해서 만들어 제거했다. 사용자는 번호+값을 함께 말한다.)
    a, b = _two_owned_planning(prio_a="중간")
    smap = {"계획": "계획", "진행": "진행"}
    with mock.patch.object(m, "llm_extract_update_changes", return_value=({}, {})):
        ask = m.update_ticket("계획 티켓 우선순위 바꿔줘", {}, CREATE_REQUESTER,
                              CREATE_CURRENT_USER, CREATE_DIRECTORY, [a, b], UPDATE_SCHEMA, smap)
        assert ask["action"] == "NEED_INPUT", ask["action"]
        done = m.update_ticket("1번 높음으로 바꿔줘", ask["context"], CREATE_REQUESTER, CREATE_CURRENT_USER,
                               CREATE_DIRECTORY, [a, b], UPDATE_SCHEMA, smap)
    assert done["action"] == "WRITE_UPDATE", done["action"]
    assert done["write_request"]["page_id"] == "s1"
    assert done["changes"].get("priority") == "높음", done["changes"]


def test_approval_message_does_not_swallow_revisions_or_deferrals():
    # round3 확정(HIGH): norm("ㅇㅇ")==""이라 startswith("")가 항상 참이 되어, 동작어만 든
    # 수정/연기 문장이 전부 승인으로 오인됐다(수정 유실·성급한 쓰기).
    assert m.is_approval_message("우선순위 높음으로 변경해줘", {"kind": "CREATE"}) is False
    assert m.is_approval_message("그건 나중에 반영할게", {"kind": "UPDATE"}) is False
    assert m.is_approval_message("난이도 3으로 변경해줘", {"kind": "UPDATE"}) is False
    # 진짜 승인은 그대로 인정한다.
    assert m.is_approval_message("응 등록해줘", {"kind": "CREATE"}) is True
    assert m.is_approval_message("네 진행해줘", {}) is True
    assert m.is_approval_message("등록해줘", {"kind": "CREATE"}) is True


def test_status_value_취소_reaches_update_in_locked_state():
    # round3 확정(MED): update_target_locked 탈출 토큰에 '취소'가 있어, 진행상태를 '취소'로
    # 바꾸는 값 답변이 조회로 새 상태 변경이 유실됐다. '취소로 바꿔줘'는 update로 가야 한다.
    ctx = {"pending_question": "update_target_locked", "selected_ticket": {"id": "x"}}
    assert m.is_update_intent("취소로 바꿔줘", ctx, {"취소": "취소"}) is True
    assert m.is_update_intent("완료로 바꿔줘", ctx, {"완료": "완료"}) is True
    # 순수 조회는 여전히 빠져나간다.
    assert m.is_update_intent("내 티켓 목록 보여줘", ctx, {}) is False


def test_title_field_value_in_one_message_writes_correct_field():
    # 제목+필드+값을 한 문장으로 말하면 그 필드에 정확히 쓴다('로그인 버그 시작일 X로 바꿔줘'
    # → start_date, 마감일 아님). 필드어가 문장에 있으므로 date_field가 시작일을 고른다.
    t = {**UPDATE_TICKET, "id": "sd1", "title": "로그인 버그", "status": "진행",
         "start_date": "", "due_date": "2026-08-01"}
    smap = {"진행": "진행", "완료": "완료", "계획": "계획"}
    with mock.patch.object(m, "llm_extract_update_changes", return_value=({}, {})):
        done = m.update_ticket("로그인 버그 시작일 2026-09-15로 바꿔줘", {}, CREATE_REQUESTER,
                               CREATE_CURRENT_USER, CREATE_DIRECTORY, [t], UPDATE_SCHEMA, smap)
    assert done["action"] == "WRITE_UPDATE", done["action"]
    assert done["write_request"]["page_id"] == "sd1"
    assert done["changes"].get("start_date") == "2026-09-15", done["changes"]
    assert "due_date" not in done["changes"], done["changes"]


_RT_U1 = {"id": "u1", "name": "황형섭", "person": {"email": "a@goodmit.co.kr"}}
_RT_U2 = {"id": "u2", "name": "홍길동", "person": {"email": "hong@goodmit.co.kr"}}
_RT_SCHEMA = {"properties": {
    "제목": {"type": "title"},
    "진행상태": {"type": "status", "status": {"options": [{"name": "계획"}, {"name": "진행"}, {"name": "완료"}]}},
    "우선순위": {"type": "select", "select": {"options": [{"name": "낮음"}, {"name": "중간"}, {"name": "높음"}]}},
    "마감일": {"type": "date"}, "티켓 담당자": {"type": "people"}}}


def _raw_ticket(tid, title, status="진행", prio="중간", people=(_RT_U1,)):
    return {"id": tid, "url": "", "properties": {
        "제목": {"type": "title", "title": [{"plain_text": title}]},
        "진행상태": {"type": "status", "status": {"name": status}},
        "우선순위": {"type": "select", "select": {"name": prio}},
        "티켓 담당자": {"type": "people", "people": list(people)}}}


def test_comment_on_others_ticket_can_be_confirmed():
    # round3 확정(HIGH): route_request pending 블록에 COMMENT 분기가 없어 확인 답변이
    # comment_ticket으로 되돌아가 '어떤 내용을 남길까요?'만 반복하고 댓글이 영영 안 달렸다.
    other = [_raw_ticket("c1", "결제 오류", people=[_RT_U2])]  # 남의 티켓
    b1 = {"message": '1번 티켓에 "확인 부탁"이라고 댓글 남겨줘', "requester": CREATE_REQUESTER,
          "projects": [], "tickets": other, "work_schema": _RT_SCHEMA,
          "context": {"last_results": ["c1"], "last_result_start": 1}}
    d1, _ = m.route_request(b1)
    assert d1["action"] == "COMMENT_PREVIEW", d1["action"]
    d2, _ = m.route_request({**b1, "message": "댓글 남겨줘", "context": d1["context"]})
    assert d2["action"] == "WRITE_COMMENT", d2["action"]
    assert d2["write_request"]["kind"] == "COMMENT"


def test_update_preview_refinement_with_number_applies():
    # UPDATE 미리보기 중 번호로 티켓을 짚어 값을 재정의하면('1번 높음으로 바꿔줘') 그 대상에
    # 반영된다(직전 목록 last_results로 번호 해석). 값만으로는 대상을 알 수 없어 지원하지 않는다.
    tk1 = _raw_ticket("tk1", "결제 오류 수정")
    upctx = {"pending_action": {"kind": "UPDATE", "ticket_id": "tk1", "ticket_title": "결제 오류 수정",
                                "changes": {"difficulty": 3}, "needs_confirmation": True, "direct": False},
             "pending_question": "approval", "selected_ticket": m.normalize_ticket(tk1, {}),
             "last_results": ["tk1"], "last_result_start": 1}
    b = {"message": "1번 높음으로 바꿔줘", "requester": CREATE_REQUESTER, "projects": [],
         "tickets": [tk1], "work_schema": _RT_SCHEMA, "context": upctx}
    with mock.patch.object(m, "llm_extract_update_changes", return_value=({}, {})):
        d, _ = m.route_request(b)
    assert d["action"] == "WRITE_UPDATE", d["action"]
    assert d["write_request"]["page_id"] == "tk1"
    assert d["changes"].get("priority") == "높음", d["changes"]


def test_project_selection_escape_clears_state_and_no_hijack():
    # round3 확정(HIGH): project_selection 되묻기를 조회로 이탈하면 상태가 안 지워져,
    # 다음 번호 응답이 stale 프로젝트 재선택으로 납치되고 사용자의 업데이트가 유실됐다.
    psctx = {"pending_question": "project_selection",
             "project_candidates": [{"id": "p1", "name": "결제개편"}, {"id": "p2", "name": "결제고도화"}],
             "pending_original_message": "결제 티켓 보여줘", "mode": "QUERY"}
    tks = [_raw_ticket("t1", "A작업"), _raw_ticket("t2", "B작업")]
    b1 = {"message": "그냥 전체 티켓 보여줘", "requester": CREATE_REQUESTER, "projects": [],
          "tickets": tks, "work_schema": _RT_SCHEMA, "context": psctx}
    d1, _ = m.route_request(b1)
    # 이탈 턴은 project_selection 상태를 비워야 한다.
    assert d1["context"].get("pending_question") != "project_selection", d1["context"].get("pending_question")
    # 다음 번호 응답은 프로젝트 재선택이 아니라 티켓 업데이트로 가야 한다(무반영 유실 방지).
    with mock.patch.object(m, "llm_extract_update_changes", return_value=({}, {})):
        d2, _ = m.route_request({**b1, "message": "1번 완료로 바꿔줘", "context": d1["context"]})
    assert d2["action"] == "WRITE_UPDATE", d2["action"]
    assert d2["write_request"]["page_id"] == "t1"


def test_create_pivot_to_update_drops_abandoned_draft():
    # round3 확정(MED): 생성 미리보기에서 무관한 업데이트로 피벗하면 CREATE 초안이 안 지워져,
    # 나중의 정당한 '응'이 그 엉뚱한 초안을 등록했다. 피벗 시 초안을 접어야 한다.
    cctx = {"pending_action": {"kind": "CREATE"}, "pending_question": "approval",
            "ticket_draft": {"title": "결제 모듈 리팩터링"}, "selected_project": {"id": "p1", "name": "포스코DX"},
            "last_results": ["tkp"], "mode": "CREATE"}
    tkp = [_raw_ticket("tkp", "완료된작업", status="완료")]
    b = {"message": "1번 완료로 해줘", "requester": CREATE_REQUESTER, "projects": [],
         "tickets": tkp, "work_schema": _RT_SCHEMA, "context": cctx}
    with mock.patch.object(m, "llm_extract_update_changes", return_value=({}, {})):
        d, _ = m.route_request(b)
    # 피벗 뒤 컨텍스트에 버려진 CREATE 초안이 남으면 안 된다.
    assert (d["context"].get("pending_action") or {}).get("kind") != "CREATE", d["context"].get("pending_action")


def test_update_target_locked_chitchat_does_not_write():
    # round4 확정(HIGH): update_target_locked에서 값도 조회도 아닌 잡담이 규칙 추출을 거쳐
    # 미리보기 없이 direct write 됐다('고마워 오늘도'의 '오늘'→마감일). 잡담은 쓰기가 아니라 대화다.
    tk1 = _raw_ticket("tk1", "로그인 버그")
    lock = {"pending_question": "update_target_locked", "selected_ticket": m.normalize_ticket(tk1, {})}
    b = {"message": "고마워 오늘도 수고했어", "requester": CREATE_REQUESTER, "projects": [],
         "tickets": [tk1], "work_schema": _RT_SCHEMA, "context": lock}
    with mock.patch.object(m, "claude_query", return_value={"action": "QUERY", "response_text": "천만에요", "context": lock}):
        d, _ = m.route_request(b)
    assert d["action"] != "WRITE_UPDATE", d["action"]
    assert "write_request" not in d


def test_update_target_locked_stale_target_not_written():
    # round4 확정(MED): 잠긴 대상이 이번 스냅샷에 없으면(삭제/이동) stale dict에 direct write가
    # 나가 not-found 가드를 우회했다. 살아 있는 대상만 복원하고, 없으면 안전하게 되묻는다.
    tk1 = _raw_ticket("tk1", "로그인 버그")
    stale = m.normalize_ticket(_raw_ticket("gone", "사라진 티켓"), {})
    lock = {"pending_question": "update_target_locked", "selected_ticket": stale}
    b = {"message": "높음으로 바꿔줘", "requester": CREATE_REQUESTER, "projects": [],
         "tickets": [tk1], "work_schema": _RT_SCHEMA, "context": lock}
    with mock.patch.object(m, "llm_extract_update_changes", return_value=({}, {})):
        d, _ = m.route_request(b)
    assert d["action"] != "WRITE_UPDATE", d["action"]
    assert "write_request" not in d


def test_create_project_ambiguity_no_project_continues_create():
    # round4 확정(HIGH): CREATE 모드 프로젝트 되묻기에서 '프로젝트 없음'을 조회 이탈로 오해해
    # 생성 초안을 통째로 폐기하고 조회 목록을 냈다. '프로젝트 없음'은 생성 계속이어야 한다.
    ctx = {"pending_question": "project_selection",
           "project_candidates": [{"id": "p1", "name": "결제개편"}, {"id": "p2", "name": "결제고도화"}],
           "pending_original_message": "결제 티켓 만들어줘 마감 내일 우선순위 높음 난이도 3",
           "mode": "CREATE", "creator": {"name": "황형섭", "email": "a@goodmit.co.kr"}}
    fields = {"priority": "높음", "difficulty": 3, "due_date": "2026-08-01", "assignee_names": [], "unassigned": True}
    b = {"message": "프로젝트 없음", "requester": CREATE_REQUESTER, "projects": [],
         "tickets": [], "work_schema": _RT_SCHEMA, "context": ctx}
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=True, fields=fields)):
        d, _ = m.route_request(b)
    # 생성 흐름으로 이어져야(조회 목록이 아니라).
    assert d["action"] in ("CREATE_PREVIEW", "NEED_INPUT"), d["action"]
    assert d["action"] != "TICKET_LIST"


def test_comment_preview_pivot_to_update_reaches_write():
    # round4 확정(MED): COMMENT 미리보기 대기 중 무관한 수정으로 피벗하면 대화로 새 유실됐다.
    # CREATE·UPDATE 분기처럼 피벗이 update로 도달해야 한다.
    own = _raw_ticket("o1", "내 작업")
    other = m.normalize_ticket(_raw_ticket("c1", "남의거", people=[_RT_U2]), {})
    prev = {"pending_action": {"kind": "COMMENT", "direct": False, "ticket_id": "c1", "comment": "확인"},
            "pending_question": "approval", "selected_ticket": other,
            "last_results": ["o1"], "last_result_start": 1}
    b = {"message": "1번 완료로 바꿔줘", "requester": CREATE_REQUESTER, "projects": [],
         "tickets": [own], "work_schema": _RT_SCHEMA, "context": prev}
    with mock.patch.object(m, "llm_extract_update_changes", return_value=({}, {})):
        d, _ = m.route_request(b)
    assert d["action"] == "WRITE_UPDATE", d["action"]
    assert d["write_request"]["page_id"] == "o1"


def test_direct_comment_retry_does_not_redispatch():
    # round4 확정(MED): 이미 발송한 direct 댓글에 '재시도'/'응'을 다시 handle_confirmation으로
    # 태우면 dispatched_at 가드가 없어 같은 댓글이 중복 발행됐다. 미리보기(direct=False)에서만 확인한다.
    own = _raw_ticket("o1", "내 작업")
    dctx = {"pending_action": {"kind": "COMMENT", "direct": True, "ticket_id": "o1", "comment": "확인"},
            "pending_question": "write_in_progress", "selected_ticket": m.normalize_ticket(own, {})}
    b = {"message": "재시도", "requester": CREATE_REQUESTER, "projects": [],
         "tickets": [own], "work_schema": _RT_SCHEMA, "context": dctx}
    with mock.patch.object(m, "claude_query", return_value={"action": "QUERY", "response_text": "x", "context": dctx}):
        d, _ = m.route_request(b)
    assert d["action"] != "WRITE_COMMENT", d["action"]
    assert "write_request" not in d


def test_yes_prefixed_approval_confirms_update_preview():
    # round6 확정(HIGH): UPDATE 미리보기에서 값 없는 자연 승인('응 변경해줘','네 반영해줘')이
    # 확정으로 인식되지 않고 pending을 유실하던 회귀. 이제 확정(WRITE_UPDATE)돼야 한다.
    tk1 = _raw_ticket("tk1", "결제 오류 수정", status="진행")

    def _upctx():
        return {"pending_action": {"kind": "UPDATE", "ticket_id": "tk1", "ticket_title": "결제 오류 수정",
                                   "changes": {"status": "완료"}, "needs_confirmation": True, "direct": False},
                "pending_question": "approval", "selected_ticket": m.normalize_ticket(tk1, {}),
                "last_results": ["tk1"], "last_result_start": 1}
    for msg in ["응 변경해줘", "네 반영해줘", "변경해줘", "좋아 변경해줘"]:
        b = {"message": msg, "requester": CREATE_REQUESTER, "projects": [], "tickets": [tk1],
             "work_schema": _RT_SCHEMA, "context": _upctx()}
        with mock.patch.object(m, "llm_extract_update_changes", return_value=({}, {})):
            d, _ = m.route_request(b)
        assert d["action"] == "WRITE_UPDATE", f"{msg}: {d['action']}"
        assert d["write_request"]["page_id"] == "tk1", msg


def test_carries_change_distinguishes_value_from_bare_approval():
    smap = {"완료": "완료", "진행": "진행"}
    assert m.carries_change("높음으로 변경해줘", smap) is True      # 우선순위 값
    assert m.carries_change("완료로 바꿔줘", smap) is True          # 상태 값
    assert m.carries_change("난이도 3으로 변경해줘", smap) is True  # 난이도 값
    assert m.carries_change("담당자를 홍길동으로 변경해줘", smap) is True   # 담당자 재지정(round7)
    assert m.carries_change("마감일 없애고 진행해줘", smap) is True         # 마감 삭제(round7)
    assert m.carries_change("응 변경해줘", smap) is False           # 값 없는 순수 승인
    assert m.carries_change("네 반영해줘", smap) is False
    assert m.carries_change("그대로 변경해줘", smap) is False       # 미리보기대로 승인


def test_update_preview_assignee_instruction_does_not_force_stale_confirm():
    # round7 확정(HIGH): '응 담당자를 홍길동으로 변경해줘'는 담당자 재지정 지시라, 낡은 pending
    # (status→완료)을 강제 확정하면 안 된다. carries_change가 담당자 지시를 잡아 피벗한다(안전 되물음).
    tk1 = _raw_ticket("tk1", "결제 오류 수정", status="진행")
    upctx = {"pending_action": {"kind": "UPDATE", "ticket_id": "tk1", "ticket_title": "결제 오류 수정",
                                "changes": {"status": "완료"}, "needs_confirmation": True, "direct": False},
             "pending_question": "approval", "selected_ticket": m.normalize_ticket(tk1, {}),
             "last_results": ["tk1"], "last_result_start": 1}
    b = {"message": "응 담당자를 홍길동으로 변경해줘", "requester": CREATE_REQUESTER, "projects": [],
         "tickets": [tk1], "work_schema": _RT_SCHEMA, "context": upctx}
    with mock.patch.object(m, "llm_extract_update_changes", return_value=({}, {})):
        d, _ = m.route_request(b)
    assert d["action"] != "WRITE_UPDATE", d["action"]   # 낡은 status→완료를 강제로 쓰면 안 된다
    assert "write_request" not in d


def test_glued_and_variant_approvals_confirm_update():
    # round15 확정(HIGH 회귀): round14의 '첫 낱말 정확일치'가 무공백 '응변경해줘'·변형 '좋아요/네네/
    # 그래그래'를 승인 미인식→pending 유실시켰다. strong yes 접두 매칭으로 복원한다.
    tk1 = _raw_ticket("tk1", "결제 오류 수정", status="진행")

    def _upctx():
        return {"pending_action": {"kind": "UPDATE", "ticket_id": "tk1", "ticket_title": "결제 오류 수정",
                                   "changes": {"status": "완료"}, "needs_confirmation": True, "direct": False},
                "pending_question": "approval", "selected_ticket": m.normalize_ticket(tk1, {}),
                "last_results": ["tk1"], "last_result_start": 1}
    for msg in ["응변경해줘", "응반영해줘", "응적용해줘", "좋아요 반영해줘", "네네 반영해줘", "그래그래 변경해줘"]:
        b = {"message": msg, "requester": CREATE_REQUESTER, "projects": [], "tickets": [tk1],
             "work_schema": _RT_SCHEMA, "context": _upctx()}
        with mock.patch.object(m, "llm_extract_update_changes", return_value=({}, {})):
            d, _ = m.route_request(b)
        assert d["action"] == "WRITE_UPDATE", f"{msg}: {d['action']}"
        assert d["write_request"]["page_id"] == "tk1", msg


def test_value_with_approval_only_verb_does_not_confirm_stale():
    # round15 확정(HIGH 기존): '응 높음으로 진행해줘'는 값(높음)을 실은 재정의인데 승인전용동사(진행)라
    # 피벗 게이트를 놓쳐 낡은 pending을 그대로 확정했다. carries_change만으로 피벗해 낡은 값을 쓰지
    # 않는다(대상 재특정 안 되면 안전한 되물음).
    tk1 = _raw_ticket("tk1", "결제 오류 수정", status="진행", prio="중간")
    upctx = {"pending_action": {"kind": "UPDATE", "ticket_id": "tk1", "ticket_title": "결제 오류 수정",
                                "changes": {"priority": "중간"}, "needs_confirmation": True, "direct": False},
             "pending_question": "approval", "selected_ticket": m.normalize_ticket(tk1, {}),
             "last_results": ["tk1"], "last_result_start": 1}
    for msg in ["응 높음으로 진행해줘", "응 완료로 진행해줘", "응 낮음으로 등록해줘"]:
        b = {"message": msg, "requester": CREATE_REQUESTER, "projects": [], "tickets": [tk1],
             "work_schema": _RT_SCHEMA, "context": dict(upctx)}
        with mock.patch.object(m, "llm_extract_update_changes", return_value=({}, {})):
            d, _ = m.route_request(b)
        # 낡은 우선순위 '중간'을 조용히 확정하면 안 된다.
        stale = (d.get("action") == "WRITE_UPDATE"
                 and d.get("write_request", {}).get("body", {}).get("properties", {})
                     .get("우선순위", {}).get("select", {}).get("name") == "중간")
        assert not stale, f"{msg}: silently confirmed stale 중간"


def test_yes_completed_confirms_update_preview():
    # round15 확정(MED 기존): '응 완료해줘'가 '완료' 조회어로 오인돼 티켓 목록을 냈다. action_words에
    # '완료'를 넣어 상태→완료 미리보기를 확정한다.
    tk1 = _raw_ticket("tk1", "결제 오류 수정", status="진행")
    upctx = {"pending_action": {"kind": "UPDATE", "ticket_id": "tk1", "ticket_title": "결제 오류 수정",
                                "changes": {"status": "완료"}, "needs_confirmation": True, "direct": False},
             "pending_question": "approval", "selected_ticket": m.normalize_ticket(tk1, {}),
             "last_results": ["tk1"], "last_result_start": 1}
    b = {"message": "응 완료해줘", "requester": CREATE_REQUESTER, "projects": [], "tickets": [tk1],
         "work_schema": _RT_SCHEMA, "context": upctx}
    with mock.patch.object(m, "llm_extract_update_changes", return_value=({}, {})):
        d, _ = m.route_request(b)
    assert d["action"] == "WRITE_UPDATE", d["action"]
    assert d["write_request"]["page_id"] == "tk1"


def test_date_clear_emits_null_not_empty_start():
    # round8 확정(HIGH, 기존): 마감일 삭제가 {'date':{'start':''}}를 보내 Notion 400. null이어야.
    assert m.property_value({"type": "date"}, "") == {"date": None}
    assert m.property_value({"type": "date"}, "2026-09-15") == {"date": {"start": "2026-09-15"}}


def test_deferral_is_not_approval():
    # round8 확정(MED): '응/그대로 나중에 반영할게'(연기)가 승인으로 오인돼 성급히 쓰이던 문제.
    assert m.is_approval_message("응 나중에 반영할게", {"kind": "CREATE"}) is False
    assert m.is_approval_message("그대로 나중에 반영할게", {"kind": "CREATE"}) is False
    assert m.is_approval_message("이따가 반영해줘", {"kind": "UPDATE"}) is False


def test_geudaero_body_edit_redrafts_not_confirms():
    # round8 확정(HIGH): CREATE 미리보기에서 '그대로 본문만 바꿔줘'가 승인으로 오라우팅돼 원본
    # 초안을 그대로 등록하던 회귀. '그대로'를 접두가 아니라 정확 조합만 승인으로 인정해 고쳤다.
    ctx = {"pending_action": {"kind": "CREATE"}, "pending_question": "approval",
           "ticket_draft": {"title": "T", "background": "b", "requirements": ["r"],
                            "acceptance_criteria": ["a"], "notes": [], "due_date": "2026-08-01"},
           "selected_project": {"id": "p1", "name": "포스코DX"}, "due_date": "2026-08-01",
           "priority": "높음", "difficulty": 3, "assignee_ids": [], "create_unassigned": True,
           "creator": {"name": "황형섭", "email": "a@goodmit.co.kr"}, "status": "계획"}
    fields = {"priority": "높음", "difficulty": 3, "due_date": "2026-08-01", "assignee_names": [], "unassigned": True}
    b = {"message": "그대로 본문만 바꿔줘", "requester": CREATE_REQUESTER, "projects": CREATE_PROJECTS,
         "tickets": [], "work_schema": _RT_SCHEMA, "context": ctx}
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=True, fields=fields)):
        d, _ = m.route_request(b)
    assert d["action"] == "CREATE_PREVIEW", d["action"]   # 재작성(수정 반영), WRITE_CREATE 아님


def test_status_value_with_approval_verb_does_not_confirm_stale():
    # round8 확정(HIGH): UPDATE 미리보기에서 '응 진행으로 반영해줘'가 새 값(진행)을 버리고 낡은
    # pending(완료)을 확정하던 회귀. 상태값+로를 carries_change가 잡아 피벗(안전 되물음)한다.
    tk1 = _raw_ticket("tk1", "결제 오류 수정", status="진행")
    upctx = {"pending_action": {"kind": "UPDATE", "ticket_id": "tk1", "ticket_title": "결제 오류 수정",
                                "changes": {"status": "완료"}, "needs_confirmation": True, "direct": False},
             "pending_question": "approval", "selected_ticket": m.normalize_ticket(tk1, {}),
             "last_results": ["tk1"], "last_result_start": 1}
    b = {"message": "응 진행으로 반영해줘", "requester": CREATE_REQUESTER, "projects": [],
         "tickets": [tk1], "work_schema": _RT_SCHEMA, "context": upctx}
    with mock.patch.object(m, "llm_extract_update_changes", return_value=({}, {})):
        d, _ = m.route_request(b)
    # 낡은 status→완료를 강제로 쓰면 안 된다.
    assert not (d["action"] == "WRITE_UPDATE" and d.get("changes", {}).get("status") == "완료"), d


_FULL_CREATE_SCHEMA = {"properties": {
    "제목": {"type": "title"}, "진행상태": {"type": "status"}, "우선순위": {"type": "select"},
    "난이도": {"type": "select"}, "마감일": {"type": "date"}, "시작일": {"type": "date"},
    "프로젝트": {"type": "relation"}, "티켓 담당자": {"type": "people"}}}
_TWO_PROJECTS = [{"id": "p1", "name": "포스코DX", "primary": [], "secondary": []},
                 {"id": "p2", "name": "클로비원", "primary": [], "secondary": []}]


def _create_preview_ctx():
    return {"pending_action": {"kind": "CREATE"}, "pending_question": "approval",
            "ticket_draft": {"title": "T", "background": "b", "requirements": ["r"],
                             "acceptance_criteria": ["a"], "notes": [], "due_date": "2026-08-01"},
            "selected_project": {"id": "p1", "name": "포스코DX"}, "due_date": "2026-08-01",
            "priority": "높음", "difficulty": 3, "assignee_ids": [], "create_unassigned": True,
            "creator": {"name": "황형섭", "email": "a@goodmit.co.kr"}, "status": "계획", "mode": "CREATE"}


def test_create_content_word_approval_confirms_not_loops():
    # round12 확정(HIGH 회귀): '응 이 내용으로 등록해줘'는 순수 승인인데 초안 필드어 '내용'만으로
    # 재작성으로 오인돼 무한 미리보기 루프. 필드어+편집동사(_DRAFT_EDIT_RE)만 수정으로 본다.
    fields = {"priority": "높음", "difficulty": 3, "due_date": "2026-08-01", "assignee_names": [], "unassigned": True}
    b = {"message": "응 이 내용으로 등록해줘", "requester": CREATE_REQUESTER, "projects": _TWO_PROJECTS,
         "tickets": [], "work_schema": _FULL_CREATE_SCHEMA, "context": _create_preview_ctx()}
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=True, fields=fields)):
        d, _ = m.route_request(b)
    assert d["action"] == "WRITE_CREATE", d["action"]   # 확정(재작성 루프 아님)


def test_create_project_change_redrafts():
    # round12 확정: '프로젝트를 클로비원으로 바꿔줘'(초안 프로젝트 수정)가 update 피벗으로 새
    # 초안이 폐기되던 회귀, 그리고 '응 클로비원으로 등록해줘'가 낡은 프로젝트로 쓰이던 기존 결함.
    # 지금과 다른 프로젝트 지목은 재작성으로 본다.
    fields = {"priority": "높음", "difficulty": 3, "due_date": "2026-08-01", "assignee_names": [], "unassigned": True}
    for msg in ["프로젝트를 클로비원으로 바꿔줘", "응 클로비원으로 등록해줘"]:
        b = {"message": msg, "requester": CREATE_REQUESTER, "projects": _TWO_PROJECTS,
             "tickets": [], "work_schema": _FULL_CREATE_SCHEMA, "context": _create_preview_ctx()}
        with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=True, fields=fields)):
            d, _ = m.route_request(b)
        assert d["action"] == "CREATE_PREVIEW", f"{msg}: {d['action']}"   # 재작성, 폐기/낡은 프로젝트 확정 아님


def test_create_content_word_edit_verb_redrafts_r14():
    # round14 확정(HIGH 회귀): round13이 '내용'을 _DRAFT_EDIT_RE 필드어에서 빼면서 '응 내용 수정해서
    # 등록해줘'가 초안을 그대로 등록. 편집동사를 함께 요구하므로 '내용'을 필드어에 되살려도 순수 승인
    # '응 이 내용으로 등록해줘'는 확정 유지된다.
    fields = {"priority": "높음", "difficulty": 3, "due_date": "2026-08-01", "assignee_names": [], "unassigned": True}
    for msg in ["응 내용 수정해서 등록해줘", "응 내용 추가해서 등록해줘", "응 담당자 변경해서 등록해줘"]:
        b = {"message": msg, "requester": CREATE_REQUESTER, "projects": _TWO_PROJECTS,
             "tickets": [], "work_schema": _FULL_CREATE_SCHEMA, "context": _create_preview_ctx()}
        with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=True, fields=fields)):
            d, _ = m.route_request(b)
        assert d["action"] == "CREATE_PREVIEW", f"{msg}: {d['action']}"


def test_create_assignee_removal_redrafts():
    # round14 확정: '응 담당자 없이 등록해줘'가 기존(자기배정) 담당자로 조용히 등록. 담당자 제거
    # 지시도 재작성으로 봐 초안 재생성 때 미할당을 반영한다.
    ctx = _create_preview_ctx()
    ctx["assignee_ids"] = ["cu"]
    ctx["create_unassigned"] = False
    fields = {"priority": "높음", "difficulty": 3, "due_date": "2026-08-01", "assignee_names": [], "unassigned": True}
    for msg in ["응 담당자 없이 등록해줘", "응 담당자 제거하고 등록해줘"]:
        b = {"message": msg, "requester": CREATE_REQUESTER, "projects": _TWO_PROJECTS,
             "tickets": [], "work_schema": _FULL_CREATE_SCHEMA, "context": dict(ctx)}
        with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=True, fields=fields)):
            d, _ = m.route_request(b)
        # 재작성(안전) — 최소한 낡은 담당자 그대로 조용히 등록(WRITE_CREATE)만은 아니어야 한다.
        assert d["action"] != "WRITE_CREATE", f"{msg}: {d['action']}"


def test_approval_message_yes_prefix_not_greedy():
    # round14 확정(MED, 승인 없는 쓰기): 단음절 '예'/'네'가 '예산'/'네트워크'의 접두라서 무관한
    # 문장이 승인으로 오인됐다. yes 접두는 띄어쓴 첫 낱말이 정확히 yes 단어일 때만 인정한다.
    pend = {"kind": "UPDATE"}
    for msg in ["예산 변경해줘", "네트워크 반영해줘", "예약 처리해줘", "예상 등록해줘", "예정대로 진행해줘"]:
        assert m.is_approval_message(msg, pend) is False, msg
    for msg in ["응 등록해줘", "네 변경해줘", "예 반영해줘", "응 변경해줘"]:
        assert m.is_approval_message(msg, pend) is True, msg


def test_approval_message_query_is_not_approval():
    # round14 확정(MED, 승인 없는 쓰기): '응 진행중인 티켓 보여줘'가 동작어 부분일치('진행')로
    # 승인 오인돼 대기 쓰기가 발행됐다. 질문·조회어가 있으면 승인이 아니다.
    pend = {"kind": "CREATE"}
    for msg in ["응 진행중인 티켓 보여줘", "응 생성된 티켓 목록 보여줘", "네 등록된 티켓들 보여줘",
                "응 변경사항 알려줘", "응 진행 현황 보여줘"]:
        assert m.is_approval_message(msg, pend) is False, msg


def test_create_field_change_verb_redrafts():
    # round13 확정(HIGH 회귀): '응 본문 변경해줘'가 _DRAFT_EDIT_RE 편집동사에 '변경'이 없어
    # 재작성 대신 초안을 그대로 등록(본문 변경 지시 유실). 편집동사 목록에 '변경' 등을 넣는다.
    fields = {"priority": "높음", "difficulty": 3, "due_date": "2026-08-01", "assignee_names": [], "unassigned": True}
    for msg in ["응 본문 변경해줘", "응 배경 변경해줘", "응 요구사항 조정해줘"]:
        b = {"message": msg, "requester": CREATE_REQUESTER, "projects": _TWO_PROJECTS,
             "tickets": [], "work_schema": _FULL_CREATE_SCHEMA, "context": _create_preview_ctx()}
        with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=True, fields=fields)):
            d, _ = m.route_request(b)
        assert d["action"] == "CREATE_PREVIEW", f"{msg}: {d['action']}"


def test_create_assignee_mention_redrafts():
    # round13 확정(HIGH 회귀): '응 담당자 홍길동으로 등록해줘'가 담당자 없이 조용히 등록됐다.
    # 담당자 지정('담당자 X으로/에게', '맡겨')은 재작성으로 봐 초안 재생성 때 이름을 담게 한다.
    fields = {"priority": "높음", "difficulty": 3, "due_date": "2026-08-01", "assignee_names": [], "unassigned": True}
    for msg in ["응 담당자 홍길동으로 등록해줘", "응 홍길동에게 맡겨서 등록해줘"]:
        b = {"message": msg, "requester": CREATE_REQUESTER, "projects": _TWO_PROJECTS,
             "tickets": [], "work_schema": _FULL_CREATE_SCHEMA, "context": _create_preview_ctx()}
        with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=True, fields=fields)):
            d, _ = m.route_request(b)
        assert d["action"] == "CREATE_PREVIEW", f"{msg}: {d['action']}"


def test_create_pure_approval_still_confirms_after_r13():
    # 위 확대가 순수 승인을 재작성으로 오인하지 않아야 한다(회귀 방지).
    fields = {"priority": "높음", "difficulty": 3, "due_date": "2026-08-01", "assignee_names": [], "unassigned": True}
    for msg in ["응 등록해줘", "응 변경해줘", "응 이 내용으로 등록해줘"]:
        b = {"message": msg, "requester": CREATE_REQUESTER, "projects": _TWO_PROJECTS,
             "tickets": [], "work_schema": _FULL_CREATE_SCHEMA, "context": _create_preview_ctx()}
        with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=True, fields=fields)):
            d, _ = m.route_request(b)
        assert d["action"] == "WRITE_CREATE", f"{msg}: {d['action']}"


def test_failed_direct_comment_retry_redispatches():
    # round13 확정(HIGH): direct 댓글 재발행 가드가 실패한 direct 댓글의 '재시도'까지 막아
    # 문서화된 복구 경로가 영구히 깨졌다. UPDATE와 같게 in-flight일 때만 막는다.
    oth = _raw_ticket("o1", "내 작업", status="진행",
                      people=[{"id": "u9", "name": "남", "person": {"email": "n@goodmit.co.kr"}}])
    ctx = {"pending_action": {"kind": "COMMENT", "ticket_id": "o1", "ticket_title": "내 작업",
                              "comment": "확인", "direct": True},
           "pending_question": "write_retry", "selected_ticket": m.normalize_ticket(oth, {}),
           "last_results": ["o1"], "last_action": {"success": False, "ticket_title": "내 작업"}}
    b = {"message": "재시도", "requester": CREATE_REQUESTER, "projects": [], "tickets": [oth],
         "work_schema": _RT_SCHEMA, "context": ctx}
    d, _ = m.route_request(b)
    assert d["action"] == "WRITE_COMMENT", d["action"]


def test_inflight_direct_comment_retry_does_not_redispatch():
    # in-flight(write_in_progress)인 direct 댓글은 여전히 재발행하지 않는다(이중 발행 방지 유지).
    oth = _raw_ticket("o1", "내 작업", status="진행",
                      people=[{"id": "u9", "name": "남", "person": {"email": "n@goodmit.co.kr"}}])
    ctx = {"pending_action": {"kind": "COMMENT", "ticket_id": "o1", "ticket_title": "내 작업",
                              "comment": "확인", "direct": True},
           "pending_question": "write_in_progress", "selected_ticket": m.normalize_ticket(oth, {}),
           "last_results": ["o1"]}
    b = {"message": "재시도", "requester": CREATE_REQUESTER, "projects": [], "tickets": [oth],
         "work_schema": _RT_SCHEMA, "context": ctx}
    with mock.patch.object(m, "claude_query", return_value={"action": "QUERY", "response_text": "x", "context": ctx}):
        d, _ = m.route_request(b)
    assert d["action"] != "WRITE_COMMENT", d["action"]
    assert "write_request" not in d


def test_failed_direct_update_retry_redispatches():
    # round12 확정(HIGH 회귀): direct 재발행 가드가 실패한 direct 쓰기의 '재시도'까지 막아
    # 재전송이 막다른 길이 됐다. in-flight(write_in_progress)만 막고 실패(write_retry)는 재시도한다.
    tk1 = _raw_ticket("tk1", "결제 오류 수정", status="진행")
    ctx = {"pending_action": {"kind": "UPDATE", "ticket_id": "tk1", "ticket_title": "결제 오류 수정",
                              "changes": {"priority": "높음"}, "direct": True},
           "pending_question": "write_retry", "selected_ticket": m.normalize_ticket(tk1, {}),
           "last_results": ["tk1"], "last_action": {"success": False, "ticket_title": "결제 오류 수정"}}
    b = {"message": "재시도", "requester": CREATE_REQUESTER, "projects": [], "tickets": [tk1],
         "work_schema": _RT_SCHEMA, "context": ctx}
    d, _ = m.route_request(b)
    assert d["action"] == "WRITE_UPDATE", d["action"]
    assert d["write_request"]["page_id"] == "tk1"


def test_hedge_word_value_change_pivots_not_confirms_stale():
    # round11 확정(HIGH 회귀): round10이 값+로 간격을 '(상태)?'로만 좁혀 '중간 정도로'·'높음 쪽으로'
    # 같은 헤지 표현을 놓쳐 낡은 pending을 확정. 작은 간격 허용(관용구 접미만 배제)으로 고침.
    smap = {"계획": "계획", "진행": "진행", "완료": "완료"}
    assert m.carries_change("응 중간 정도로 변경해줘", smap) is True
    assert m.carries_change("응 높음 쪽으로 변경해줘", smap) is True
    assert m.carries_change("응 계획대로 반영해줘", smap) is False   # 관용구는 여전히 승인
    tk1 = _raw_ticket("tk1", "결제 오류 수정", status="진행")
    b = {"message": "응 중간 정도로 변경해줘", "requester": CREATE_REQUESTER, "projects": [], "tickets": [tk1],
         "work_schema": _RT_SCHEMA, "context": _update_preview_ctx(tk1)}
    with mock.patch.object(m, "llm_extract_update_changes", return_value=({}, {})):
        d, _ = m.route_request(b)
    assert not (d["action"] == "WRITE_UPDATE" and d.get("changes", {}).get("status") == "완료"), d


def test_yes_prefixed_body_revision_redrafts_not_confirms():
    # round11 확정(HIGH): '응 배경 좀 더 자세히 써서 등록해줘'(승인접두+본문수정)가 낡은 초안을
    # 그대로 등록하던 문제. 초안 내용 필드(_DRAFT_CONTENT_RE) 언급을 재작성 조건으로 잡는다.
    ctx = {"pending_action": {"kind": "CREATE"}, "pending_question": "approval",
           "ticket_draft": {"title": "T", "background": "b", "requirements": ["r"],
                            "acceptance_criteria": ["a"], "notes": [], "due_date": "2026-08-01"},
           "selected_project": {"id": "p1", "name": "포스코DX"}, "due_date": "2026-08-01",
           "priority": "높음", "difficulty": 3, "assignee_ids": [], "create_unassigned": True,
           "creator": {"name": "황형섭", "email": "a@goodmit.co.kr"}, "status": "계획"}
    fields = {"priority": "높음", "difficulty": 3, "due_date": "2026-08-01", "assignee_names": [], "unassigned": True}
    for msg in ["응 배경 좀 더 자세히 써서 등록해줘", "응 요구사항 하나 추가해서 등록해줘"]:
        b = {"message": msg, "requester": CREATE_REQUESTER, "projects": CREATE_PROJECTS,
             "tickets": [], "work_schema": _RT_SCHEMA, "context": ctx}
        with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=True, fields=fields)):
            d, _ = m.route_request(b)
        assert d["action"] == "CREATE_PREVIEW", f"{msg}: {d['action']}"   # 재작성, 낡은 초안 확정 아님
        assert "write_request" not in d, msg
    # 순수 승인('응 등록해줘')은 재작성 조건에서 빠져 확정 경로로 간다(내용 필드어 없음).
    assert m.is_exact_approval("응 등록해줘", {"kind": "CREATE"}) is True


def test_direct_update_retry_does_not_redispatch():
    # round11 확정(MED): 이미 발송한 direct 변경에 '응'을 다시 handle_confirmation으로 태우면
    # dispatched_at 가드가 없어 같은 변경이 중복 발행됐다. direct는 확인 재발행을 막는다.
    tk1 = _raw_ticket("tk1", "결제 오류 수정", status="진행")
    dctx = {"pending_action": {"kind": "UPDATE", "ticket_id": "tk1", "changes": {"priority": "높음"}, "direct": True},
            "pending_question": "write_in_progress", "selected_ticket": m.normalize_ticket(tk1, {}),
            "last_results": ["tk1"]}
    b = {"message": "응", "requester": CREATE_REQUESTER, "projects": [], "tickets": [tk1],
         "work_schema": _RT_SCHEMA, "context": dctx}
    with mock.patch.object(m, "claude_query", return_value={"action": "QUERY", "response_text": "x", "context": dctx}):
        d, _ = m.route_request(b)
    assert d["action"] != "WRITE_UPDATE", d["action"]
    assert "write_request" not in d


def test_daero_idiom_is_approval_not_value_change():
    # round10 확정(HIGH 회귀): '계획대로 반영해줘'(as-planned)가 값+로 정규식의 임의 간격에
    # '계획+로'로 오인돼 pending을 잃었다. '-대로' 관용구는 승인이지 값 재지정이 아니다.
    smap = {"계획": "계획", "진행": "진행", "완료": "완료"}
    assert m.carries_change("응 계획대로 반영해줘", smap) is False
    assert m.carries_change("예정대로 처리해줘", smap) is False
    # 진짜 값 재지정은 여전히 잡는다.
    assert m.carries_change("응 진행으로 반영해줘", smap) is True
    assert m.carries_change("응 진행 상태로 반영해줘", smap) is True
    tk1 = _raw_ticket("tk1", "결제 오류 수정", status="진행")
    b = {"message": "응 계획대로 반영해줘", "requester": CREATE_REQUESTER, "projects": [], "tickets": [tk1],
         "work_schema": _RT_SCHEMA, "context": _update_preview_ctx(tk1)}
    with mock.patch.object(m, "llm_extract_update_changes", return_value=({}, {})):
        d, _ = m.route_request(b)
    assert d["action"] == "WRITE_UPDATE", d["action"]        # 승인 확정(피벗으로 pending 잃지 않음)
    assert d["write_request"]["page_id"] == "tk1"


def test_create_value_only_inline_correction_redrafts_not_confirms():
    # round10 확정(MED): CREATE 미리보기에서 값만 정정한 '응 높음으로 등록해줘'가
    # is_revision_intent(필드'이름'만 봄) 미인식으로 낡은 초안을 그대로 Notion에 등록하던 문제.
    # carries_change가 값을 잡아 재작성(미리보기)로 흘려 잘못된 확정을 막는다. (값 자체의 반영은
    # 사용자가 필드명을 붙이면 정확해진다 — 여기 핵심은 낡은 초안을 확정하지 않는 것.)
    ctx = {"pending_action": {"kind": "CREATE"}, "pending_question": "approval",
           "ticket_draft": {"title": "T", "background": "b", "requirements": ["r"],
                            "acceptance_criteria": ["a"], "notes": [], "due_date": "2026-08-01"},
           "selected_project": {"id": "p1", "name": "포스코DX"}, "due_date": "2026-08-01",
           "priority": "낮음", "difficulty": 3, "assignee_ids": [], "create_unassigned": True,
           "creator": {"name": "황형섭", "email": "a@goodmit.co.kr"}, "status": "계획"}
    fields = {"priority": "높음", "difficulty": 3, "due_date": "2026-08-01", "assignee_names": [], "unassigned": True}
    b = {"message": "응 높음으로 등록해줘", "requester": CREATE_REQUESTER, "projects": CREATE_PROJECTS,
         "tickets": [], "work_schema": _RT_SCHEMA, "context": ctx}
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=True, fields=fields)):
        d, _ = m.route_request(b)
    assert d["action"] == "CREATE_PREVIEW", d["action"]      # 재작성(확인 미리보기), 낡은 초안 확정 아님
    assert "write_request" not in d


def test_update_assignee_apply_verb_does_not_confirm_stale():
    # round10 확정(MED): '응 담당자를 X로 반영해줘'가 담당자 값을 못 잡아 낡은 pending(완료)을
    # 확정하던 문제. 필드어+반영/적용/처리를 carries_change가 잡아 피벗(안전 되물음)한다.
    tk1 = _raw_ticket("tk1", "결제 오류 수정", status="진행")
    b = {"message": "응 담당자를 홍길동으로 반영해줘", "requester": CREATE_REQUESTER, "projects": [],
         "tickets": [tk1], "work_schema": _RT_SCHEMA, "context": _update_preview_ctx(tk1)}
    with mock.patch.object(m, "llm_extract_update_changes", return_value=({}, {})):
        d, _ = m.route_request(b)
    assert not (d["action"] == "WRITE_UPDATE" and d.get("changes", {}).get("status") == "완료"), d


def _update_preview_ctx(tk1):
    return {"pending_action": {"kind": "UPDATE", "ticket_id": "tk1", "ticket_title": "결제 오류 수정",
                               "changes": {"status": "완료"}, "needs_confirmation": True, "direct": False},
            "pending_question": "approval", "selected_ticket": m.normalize_ticket(tk1, {}),
            "last_results": ["tk1"], "last_result_start": 1}


def test_value_with_approval_verb_variants_do_not_confirm_stale():
    # round9 확정(HIGH): '응 진행 상태로 반영해줘'·'응 높음으로 반영해줘'가 낡은 pending(완료)을
    # 확정하던 문제. 값+로를 carries_change가 잡아 피벗(안전 되물음)한다.
    tk1 = _raw_ticket("tk1", "결제 오류 수정", status="진행")
    for msg in ["응 진행 상태로 반영해줘", "네 진행 상태로 반영해줘", "응 높음으로 반영해줘", "응 중간으로 적용해줘"]:
        b = {"message": msg, "requester": CREATE_REQUESTER, "projects": [], "tickets": [tk1],
             "work_schema": _RT_SCHEMA, "context": _update_preview_ctx(tk1)}
        with mock.patch.object(m, "llm_extract_update_changes", return_value=({}, {})):
            d, _ = m.route_request(b)
        stale = d.get("action") == "WRITE_UPDATE" and d.get("changes", {}).get("status") == "완료"
        assert not stale, f"{msg}: {d.get('action')} {d.get('changes')}"


def test_temporal_adverb_approval_confirms_not_pivots():
    # round9 확정(MED): '응 오늘 반영해줘'(지금 반영하자)는 마감일 값이 아니라 승인이다.
    # carries_change가 '오늘 반영'을 날짜 값으로 오인해 피벗으로 pending을 잃었다. 이제 확정된다.
    tk1 = _raw_ticket("tk1", "결제 오류 수정", status="진행")
    b = {"message": "응 오늘 반영해줘", "requester": CREATE_REQUESTER, "projects": [], "tickets": [tk1],
         "work_schema": _RT_SCHEMA, "context": _update_preview_ctx(tk1)}
    with mock.patch.object(m, "llm_extract_update_changes", return_value=({}, {})):
        d, _ = m.route_request(b)
    assert d["action"] == "WRITE_UPDATE", d["action"]    # 승인 확정(피벗 아님)
    assert d["write_request"]["page_id"] == "tk1"
    # carries_change 단위: '오늘 반영해줘'는 날짜 값이 아니라 타이밍이라 변경으로 보지 않는다.
    assert m.carries_change("오늘 반영해줘", {"완료": "완료"}) is False


def test_update_preview_geudaero_approval_confirms():
    # round7 확정(MED): '그대로 변경해줘'(미리보기대로 반영)는 자연 승인이라 확정돼야 한다.
    tk1 = _raw_ticket("tk1", "결제 오류 수정", status="진행")
    upctx = {"pending_action": {"kind": "UPDATE", "ticket_id": "tk1", "ticket_title": "결제 오류 수정",
                                "changes": {"status": "완료"}, "needs_confirmation": True, "direct": False},
             "pending_question": "approval", "selected_ticket": m.normalize_ticket(tk1, {}),
             "last_results": ["tk1"], "last_result_start": 1}
    b = {"message": "그대로 변경해줘", "requester": CREATE_REQUESTER, "projects": [],
         "tickets": [tk1], "work_schema": _RT_SCHEMA, "context": upctx}
    with mock.patch.object(m, "llm_extract_update_changes", return_value=({}, {})):
        d, _ = m.route_request(b)
    assert d["action"] == "WRITE_UPDATE", d["action"]
    assert d["write_request"]["page_id"] == "tk1"


def test_is_exact_approval_distinguishes_from_revision():
    # round5 확정(HIGH) 대응: 딱 승인만 exact로 인정하고, 수정이 섞인 승인 접두는 exact 아님.
    assert m.is_exact_approval("등록해줘", {"kind": "CREATE"}) is True
    assert m.is_exact_approval("변경해줘", {"kind": "UPDATE"}) is True
    assert m.is_exact_approval("응 난이도 3으로 변경해줘", {"kind": "CREATE"}) is False
    assert m.is_exact_approval("높음으로 변경해줘", {"kind": "UPDATE"}) is False


def test_yes_prefixed_revision_redrafts_not_approves():
    # round5 확정(HIGH): '응 난이도 3으로 변경해줘'는 승인 접두가 붙었어도 구체적 수정이라,
    # 수정 전 초안을 그대로 등록하지 않고 재작성(미리보기)해야 한다.
    ctx = {"pending_action": {"kind": "CREATE"}, "pending_question": "approval",
           "ticket_draft": {"title": "T", "background": "b", "requirements": ["r"],
                            "acceptance_criteria": ["a"], "notes": [], "due_date": "2026-08-01"},
           "selected_project": {"id": "p1", "name": "포스코DX"}, "due_date": "2026-08-01",
           "priority": "높음", "difficulty": 5, "assignee_ids": [], "create_unassigned": True,
           "creator": {"name": "황형섭", "email": "a@goodmit.co.kr"}, "status": "계획"}
    fields = {"priority": "높음", "difficulty": 3, "due_date": "2026-08-01", "assignee_names": [], "unassigned": True}
    b = {"message": "응 난이도 3으로 변경해줘", "requester": CREATE_REQUESTER, "projects": CREATE_PROJECTS,
         "tickets": [], "work_schema": _RT_SCHEMA, "context": ctx}
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=True, fields=fields)):
        d, _ = m.route_request(b)
    assert d["action"] == "CREATE_PREVIEW", d["action"]     # 재작성 미리보기(WRITE_CREATE 아님)
    assert "난이도: 3" in d["response_text"], d["response_text"]


def test_ticket_selection_resets_page_start():
    # round5 확정(MED): 직전 조회 2페이지(last_result_start=11) 뒤 벌크 변경으로 다중 후보가
    # 1번부터 표시되는데 last_result_start가 11로 남아 화면의 '2번'이 범위 밖으로 거부되던 문제.
    a, b = _two_owned_planning()
    smap = {"계획": "계획", "진행": "진행"}
    ctx = {"last_result_start": 11, "last_results": ["x1", "x2"]}
    with mock.patch.object(m, "llm_extract_update_changes", return_value=({}, {})):
        ask = m.update_ticket("계획 티켓을 진행으로 바꿔줘", ctx, CREATE_REQUESTER,
                              CREATE_CURRENT_USER, CREATE_DIRECTORY, [a, b], UPDATE_SCHEMA, smap)
        assert ask["action"] == "NEED_INPUT", ask["action"]
        assert ask["context"].get("last_result_start") == 1, ask["context"].get("last_result_start")
        # '2번'이 화면의 2번(B작업, s2)으로 해석돼 진행으로 반영돼야 한다.
        done = m.update_ticket("2번", ask["context"], CREATE_REQUESTER, CREATE_CURRENT_USER,
                               CREATE_DIRECTORY, [a, b], UPDATE_SCHEMA, smap)
    assert done["action"] == "WRITE_UPDATE", done["action"]
    assert done["write_request"]["page_id"] == "s2"


def test_smalltalk_routes_to_conversation_not_unsupported():
    # 사용자 피드백: 잡담/예상 밖 입력이 거부되지 않고 대화로 흘러야 한다.
    assert m.explicit_unsupported_action("오늘 날씨 어때?") == ""
    answer = {"answer": "저는 실시간 날씨는 볼 수 없지만, 오늘 마감 티켓은 알려드릴 수 있어요.",
              "ticket_ids": [], "project_ids": [], "needs_clarification": False, "clarify_question": ""}
    with mock.patch.object(m.subprocess, "run", return_value=_fake_cli(answer)) as run:
        data, _ = m.process_request({"message": "오늘 날씨 어때?", "message_id": "st1",
                                     "conversation_id": "cv-st", "requester": {"email": "a@goodmit.co.kr", "name": "황형섭"},
                                     "projects": [], "tickets": [], "work_schema": {}, "context": {}})
    assert run.called
    assert data["action"] == "QUERY"
    assert "날씨" in data["response_text"]


# --- IMPROVEMENT_BACKLOG P0 회귀 ---------------------------------------------
def test_claude_query_records_followup_anchor():
    # P0: 대화형 답변의 참조 티켓이 후속 "두 번째 티켓" 참조의 앵커가 되어야 한다.
    structured = {"answer": "급한 건 GIT-2와 GIT-1입니다.", "ticket_ids": ["t2", "t1"],
                  "project_ids": [], "needs_clarification": False, "clarify_question": ""}
    with mock.patch.object(m.subprocess, "run", return_value=_fake_cli(structured)):
        data = m.claude_query("가장 급한 티켓 알려줘", {}, {"email": "a@x", "name": "문의진"},
                              {"id": "u1"}, PROJECTS, TICKETS, {})
    ctx = data["context"]
    assert ctx["last_results"] == ["t2", "t1"]
    assert ctx["last_result_start"] == 1
    # 이어서 "두 번째 티켓 상세" → t1이 잡혀야 한다.
    cands, src = m.resolve_ticket_reference("두 번째 티켓 상세", ctx, TICKETS)
    assert [t["id"] for t in cands] == ["t1"]


def test_more_after_freeform_continues_conversation():
    # P0: freeform 직후 "더 보여줘"가 전체 티켓 덤프가 아니라 대화로 이어져야 한다.
    ctx = {"last_query": {"kind": "freeform", "message": "긴급한 티켓 알려줘"},
           "conversation_history": [{"role": "user", "content": "긴급한 티켓 알려줘"},
                                    {"role": "assistant", "content": "GIT-2가 가장 급합니다."}]}
    structured = {"answer": "이어서 GIT-1도 마감이 임박했습니다.", "ticket_ids": ["t1"],
                  "project_ids": [], "needs_clarification": False, "clarify_question": ""}
    with mock.patch.object(m.subprocess, "run", return_value=_fake_cli(structured)) as run:
        data = m.query_tickets("더 보여줘", ctx, {"email": "a@x", "name": "문의진"},
                               {"id": "u1"}, PROJECTS, TICKETS, {})
    assert run.called, "freeform 이어가기는 LLM으로 재라우팅"
    assert data["action"] == "QUERY"
    assert "GIT-1" in data["response_text"]


def test_page2_bare_number_never_guesses():
    # P0: 2페이지에서 "2번"은 모호 — 절대 추측해 직접 쓰기하지 않는다.
    ctx = {"last_results": ["t1", "t2"], "last_result_start": 11}
    cands, src = m.resolve_ticket_reference("2번 완료로 바꿔줘", ctx, TICKETS)
    assert cands == [] and src == "ambiguous_number"
    with mock.patch.object(m.subprocess, "run") as run:
        data = m.update_ticket("2번 완료로 바꿔줘", ctx, CREATE_REQUESTER, CREATE_CURRENT_USER,
                               CREATE_DIRECTORY, [UPDATE_TICKET], UPDATE_SCHEMA, {"완료": "완료"})
    assert data["action"] == "NEED_INPUT"
    assert "11번부터" in data["response_text"]
    # 전역 번호(12번)는 여전히 정상 해석된다.
    cands2, _ = m.resolve_ticket_reference("12번", ctx, TICKETS)
    assert [t["id"] for t in cands2] == ["t2"]


def test_slim_ticket_includes_url():
    t = {**TICKETS[0], "url": "https://www.notion.so/abc"}
    assert m._slim_ticket_for_query(t)["url"] == "https://www.notion.so/abc"


def test_start_date_change_goes_to_start_field():
    # P0: "시작일을 …로" 가 마감일로 오기록되던 결함 — start_date 채널로 가야 한다.
    msg = "로그인 버그 시작일을 2026-08-01로 바꿔줘"
    with mock.patch.object(m.subprocess, "run") as run:
        data = m.update_ticket(msg, {}, CREATE_REQUESTER, CREATE_CURRENT_USER,
                               CREATE_DIRECTORY, [UPDATE_TICKET], UPDATE_SCHEMA, {"진행": "진행"})
    assert not run.called
    assert data["action"] == "WRITE_UPDATE", data["action"]
    assert data["changes"].get("start_date") == "2026-08-01"
    assert "due_date" not in data["changes"], "마감일이 건드려지면 안 된다"


def test_title_change_supported_and_safe():
    # P0: 제목 변경 지원 + 새 제목 속 상태어("완료")가 상태 변경으로 오발사되지 않아야 한다.
    msg = "로그인 버그 티켓 제목을 '배포 완료 안내'로 바꿔줘"
    with mock.patch.object(m.subprocess, "run") as run:
        data = m.update_ticket(msg, {}, CREATE_REQUESTER, CREATE_CURRENT_USER,
                               CREATE_DIRECTORY, [UPDATE_TICKET], UPDATE_SCHEMA,
                               {"진행": "진행", "완료": "완료"})
    assert not run.called
    assert data["action"] == "WRITE_UPDATE", data["action"]
    assert data["changes"].get("title") == "배포 완료 안내"
    assert "status" not in data["changes"], "제목 속 '완료'가 상태를 바꾸면 안 된다"


def test_my_created_scope_and_honest_refusal():
    # P0: "내가 만든 티켓" = created_by 필터. "내가 요청한" = 정직한 한계 안내(전체 덤프 금지).
    mine = {**TICKETS[0], "created_by": "u1"}
    other = {**TICKETS[1], "created_by": "u9"}
    data = m.query_tickets("내가 만든 티켓 보여줘", {}, {"email": "a@x", "name": "문의진"},
                           {"id": "u1"}, PROJECTS, [mine, other], {})
    assert "내가 만든 티켓" in data["response_text"]
    assert data["context"]["last_results"] == [mine["id"]]

    data2 = m.query_tickets("내가 요청한 티켓 보여줘", {}, {"email": "a@x", "name": "문의진"},
                            {"id": "u1"}, PROJECTS, [mine, other], {})
    assert data2["action"] == "NEED_INPUT"
    assert "요청자" in data2["response_text"]


# --- P1 웨이브 A 회귀 ---------------------------------------------------------
def test_grouped_summary_renders_deterministic_counts():
    # P1-17: "상태별로 정리해줘" → 규칙 엔진이 집계를 결정론적으로 렌더.
    ts = [
        {**TICKETS[0], "id": "g1", "status": "진행"},
        {**TICKETS[0], "id": "g2", "status": "진행", "title": "두번째"},
        {**TICKETS[0], "id": "g3", "status": "계획", "title": "세번째"},
    ]
    data = m.query_tickets("티켓 상태별로 정리해줘", {}, {"email": "a@x", "name": "문의진"},
                           {"id": "u1"}, PROJECTS, ts, {})
    assert data["action"] == "TICKET_SUMMARY", data["action"]
    assert "진행: 2건" in data["response_text"]
    assert "계획: 1건" in data["response_text"]


def test_relative_dates_last_week_and_yesterday():
    # P1-18: 지난주/어제/지난달이 전체 덤프가 아니라 실제 기간 필터가 된다.
    from datetime import date
    r = m.parse_date_range("지난주 마감 티켓", date(2026, 7, 15))  # 수요일
    assert r == {"mode": "BETWEEN", "start": "2026-07-06", "end": "2026-07-12", "label": "지난주"}
    r2 = m.parse_date_range("어제 마감이었던 것", date(2026, 7, 15))
    assert r2["start"] == r2["end"] == "2026-07-14"
    r3 = m.parse_date_range("지난달 티켓", date(2026, 7, 15))
    assert r3["start"] == "2026-06-01" and r3["end"] == "2026-06-30"


def test_routing_boundary_structured_query_stays_rule_engine():
    # P1-19: '알려줘' 어미 하나로 LLM에 뺏기지 않는다 — 정형 질의는 규칙 엔진 고정.
    assert not m.is_freeform_query("내 티켓 알려줘")
    assert not m.is_freeform_query("진행중인 티켓 몇 개인지 알려줘")
    assert m.is_freeform_query("내 티켓 요약해줘")  # 진짜 추론 마커는 유지


def test_delete_refused_honestly():
    # P1-13: 삭제는 침묵 무시가 아니라 대안까지 안내.
    data, _ = m.process_request({"message": "그 티켓 삭제해줘", "message_id": "d1",
                                 "conversation_id": "cv-d", "requester": {"email": "a@x", "name": "황형섭"},
                                 "projects": [], "tickets": [], "work_schema": {}, "context": {}})
    assert data["action"] == "UNSUPPORTED"
    assert "취소" in data["response_text"] and "Notion" in data["response_text"]


def test_groupby_beats_freeform_marker():
    # "상태별로 정리해줘"의 '정리'가 LLM으로 새지 않고 규칙 그룹화로 간다.
    assert not m.is_freeform_query("내 티켓 상태별로 정리해줘")
    assert m.is_freeform_query("내 티켓 정리해줘")  # 그룹 축 없으면 기존대로 LLM


def test_start_date_period_query_filters_on_start():
    # P1-16: "이번 주에 시작하는" 은 시작일 축으로 필터링된다(마감일 오해석 금지).
    ts = [
        {**TICKETS[0], "id": "sd1", "start_date": "2026-07-16", "due_date": "2026-09-01"},
        {**TICKETS[0], "id": "sd2", "title": "다음달 시작", "start_date": "2026-08-10", "due_date": "2026-07-16"},
    ]
    from datetime import date as _d
    import unittest.mock as _m
    with _m.patch.object(m, "now_kst") as nk:
        class FakeNow:
            @staticmethod
            def date(): return _d(2026, 7, 15)
            @staticmethod
            def isoformat(): return "2026-07-15T09:00:00+09:00"
        nk.return_value = FakeNow()
        data = m.query_tickets("이번 주에 시작하는 티켓 보여줘", {}, {"email": "a@x", "name": "문의진"},
                               {"id": "u1"}, PROJECTS, ts, {})
    assert data["context"]["last_results"] == ["sd1"], data["response_text"][:120]
    assert "시작일" in data["response_text"]


def test_create_mode_lets_queries_escape():
    # P1-10: 생성 필드 수집 중에도 조회는 빠져나가고, 초안 상태는 유지된다.
    ctx = {"mode": "CREATE", "pending_question": "ticket_requirements",
           "due_date": "2026-08-01", "creator": {"name": "황형섭"}}
    assert not m.is_create_intent("내 티켓 보여줘", ctx)
    assert not m.is_create_intent("진행중인 티켓 몇 개야?", ctx)
    assert m.is_create_intent("우선순위 낮음, 난이도 1", ctx)   # 필드 입력은 계속 수집
    assert m.is_create_intent("다른 티켓도 만들어줘", ctx)


def test_freeform_residue_does_not_pollute_condition_edit():
    # P1-9: LLM 답변 뒤 "완료된 것 빼줘"가 전체 티켓으로 리셋되지 않는다.
    ctx = {"last_query": {"kind": "freeform", "message": "긴급한 티켓 알려줘"},
           "last_results": ["t1"]}
    data = m.query_tickets("완료된 건 빼고 내 티켓 보여줘", ctx, {"email": "a@x", "name": "문의진"},
                           {"id": "u1"}, PROJECTS, TICKETS, {})
    assert data["action"] == "TICKET_LIST"
    assert "내" in data["response_text"] or "직접 할당" in data["response_text"]


def test_my_projects_include_open_counts():
    # P1-24: 프로젝트 목록에 진행 중 티켓 수가 포함된다.
    data = m.query_tickets("내 담당 프로젝트 보여줘", {}, {"email": "a@x", "name": "문의진"},
                           {"id": "u1"}, PROJECTS, TICKETS, {})
    assert data["action"] == "PROJECT_LIST"
    assert "미완료 티켓" in data["response_text"]  # active = 완료·취소 제외 (라벨 정직화)
    assert data["projects"][0]["open_tickets"] == 2


# --- 배치 검수(15.5) 확정건 회귀 -----------------------------------------------
def test_title_regex_no_overcapture():
    # HIGH: "제목은 그대로 두고 마감일을…"이 제목 변경으로 오탐되지 않는다.
    assert m.extract_title_change("제목은 그대로 두고 마감일을 다음 주로 변경해줘") == ""
    assert m.extract_title_change("제목에 오타 있는 티켓 상태를 완료로 바꿔줘") == ""
    assert m.extract_title_change("제목을 '결제 오류 수정'으로 바꿔줘") == "결제 오류 수정"


def test_create_escape_not_stolen_by_bare_nouns():
    # MED: 필드 답변("발주 현황 조회 화면")이 생성 흐름에서 뺏기지 않는다.
    ctx = {"mode": "CREATE", "pending_question": "ticket_requirements"}
    assert m.is_create_intent("발주 현황 조회 화면", ctx)
    assert m.is_create_intent("관리자 목록 화면 개선", ctx)
    assert not m.is_create_intent("내 티켓 보여줘", ctx)


def test_start_channel_yields_to_explicit_deadline():
    from datetime import date as _d
    f = m.parse_date_range("이번 주 마감 티켓 중 착수 전인 것", _d(2026, 7, 15))
    # 마감이 명시되면 시작일로 뒤집지 않는다 — query_tickets 레벨 가드라 여기선 필드 부재 확인
    ts = [{**TICKETS[0], "id": "gd1", "start_date": "2026-09-01", "due_date": "2026-07-17"}]
    data = m.query_tickets("이번 주 마감 티켓 중 착수 전인 것 보여줘", {},
                           {"email": "a@x", "name": "문의진"}, {"id": "u1"}, PROJECTS, ts, {})
    assert "시작일" not in (data.get("response_text") or "")[:30]


def test_reasoning_groupby_goes_to_llm():
    # MED: "프로젝트별 진행률"은 건수 나열이 아니라 LLM 추론으로 간다.
    assert m.is_freeform_query("프로젝트별 진행률 알려줘")
    assert m.is_freeform_query("담당자별로 누가 제일 바쁜지 분석해줘")
    assert not m.is_freeform_query("프로젝트별로 정리해줘")


def test_delete_guidance_clears_stale_selection():
    ctx = {"selected_ticket": {"id": "stale", "title": "엉뚱한 티켓"}}
    data, _ = m.process_request({"message": "결제 모듈 개선 티켓 삭제해줘", "message_id": "dg1",
                                 "conversation_id": "cv-dg", "requester": {"email": "a@x", "name": "황"},
                                 "projects": [], "tickets": [], "work_schema": {}, "context": ctx})
    assert data["action"] == "UNSUPPORTED"
    assert data["context"].get("selected_ticket") is None
    assert "그 티켓" not in data["response_text"]


def test_my_created_disclosure_notice():
    mine = {**TICKETS[0], "created_by": "u1"}
    data = m.query_tickets("내가 만든 티켓 보여줘", {}, {"email": "a@x", "name": "문의진"},
                           {"id": "u1"}, PROJECTS, [mine], {})
    assert "봇" in data["response_text"]


def test_p2_sort_axes_and_page_size():
    assert m.extract_sort("최신순으로 보여줘") == "CREATED_DESC"
    assert m.extract_sort("난이도 높은 순") == "DIFFICULTY_DESC"
    assert m.extract_limit("20개씩 보여줘") == 20
    assert m.extract_limit("5건만") == 5
    assert m.extract_limit("보여줘") == 0
    ts = [{**TICKETS[0], "id": f"p{i}", "title": f"T{i}"} for i in range(15)]
    data = m.query_tickets("전체 티켓 12개씩 보여줘", {}, {"email": "a@x", "name": "문의진"},
                           {"id": "u1"}, PROJECTS, ts, {})
    assert len(data["context"]["last_results"]) == 10 or len(data["tickets"]) == 12


def test_p2_count_leaves_no_phantom_numbers():
    data = m.query_tickets("전체 티켓 몇 개야?", {}, {"email": "a@x", "name": "문의진"},
                           {"id": "u1"}, PROJECTS, TICKETS, {})
    assert data["action"] == "TICKET_COUNT"
    assert data["context"]["last_results"] == []


def test_choices_ride_selection_and_preview_responses():
    # P2-32: 선택/확인 응답에 원탭 버튼 데이터(choices)가 실린다.
    projs = [{"id": "pa", "name": "P. SK하이닉스 [용인]", "status": "진행", "primary": [], "secondary": [], "url": ""},
             {"id": "pb", "name": "M. SK하이닉스 [ITAP]", "status": "진행", "primary": [], "secondary": [], "url": ""}]
    with mock.patch.object(m.subprocess, "run"):
        data, _ = m.create_ticket("SK하이닉스에 테스트용 티켓 만들어줘 아무렇게나. 마감 내일, 우선순위 낮음, 난이도 1, 미할당",
                                  {}, CREATE_REQUESTER, CREATE_CURRENT_USER, [], projs, {})
    assert data["action"] == "NEED_INPUT"
    assert data["choices"][0]["send"] == "1번"
    assert "SK하이닉스" in data["choices"][0]["label"]

    fields = {"priority": "높음", "difficulty": 3, "due_date": "2026-08-01",
              "assignee_names": [], "unassigned": True}
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=True, fields=fields)):
        prev, _ = m.create_ticket("포스코DX에 로그인 버그 티켓 만들어줘. 마감 2026-08-01, 우선순위 높음, 난이도 3, 미할당",
                                  {}, CREATE_REQUESTER, CREATE_CURRENT_USER, [], CREATE_PROJECTS, {})
    assert prev["action"] == "CREATE_PREVIEW"
    sends = [c["send"] for c in prev["choices"]]
    assert "등록해줘" in sends and "아니" in sends


def test_comment_flow_targets_and_body():
    # P2-27: 따옴표 댓글이 대상 티켓에 COMMENT write_request로 나간다.
    ctx = {"last_results": ["tk1"], "last_result_start": 1}
    data = m.comment_ticket('1번 티켓에 "내일 배포 예정입니다"라고 댓글 남겨줘', ctx, [UPDATE_TICKET],
                            CREATE_REQUESTER, CREATE_CURRENT_USER)
    assert data["action"] == "WRITE_COMMENT"
    wr = data["write_request"]
    assert wr["kind"] == "COMMENT" and wr["page_id"] == "tk1"
    assert wr["body"]["parent"]["page_id"] == "tk1"
    assert "내일 배포 예정입니다" in wr["body"]["rich_text"][0]["plain_text"]

    # 내용 없으면 정중히 되묻기 / 대상 모호하면 되묻기
    ask = m.comment_ticket("댓글 남겨줘", {}, [UPDATE_TICKET], CREATE_REQUESTER, CREATE_CURRENT_USER)
    assert ask["action"] == "NEED_INPUT"
    assert m.is_comment_intent('여기에 "메모"라고 댓글 달아줘')
    assert not m.is_comment_intent("댓글 기능이 있나요?")


def test_create_intent_yields_to_trailing_read_verb():
    # 문장 뒤쪽 동사가 요청의 정체다. 앞에 놓인 '생성/등록'은 설명 대상의 일부다.
    assert not m.is_create_intent("티켓 생성 기능 검증 검색해줘", {})
    assert not m.is_create_intent("티켓 등록 화면 버그 현황 알려줘", {})
    assert not m.is_create_intent("티켓 생성 관련 티켓 보여줘", {})
    # 반대로 만드는 동사가 뒤에 오면 생성이다.
    assert m.is_create_intent("티켓 만들어줘", {})
    assert m.is_create_intent("티켓 생성해줘", {})
    assert m.is_create_intent("티켓 생성", {})
    assert m.is_create_intent("로그인 개선 티켓 추가해줘", {})
    assert m.is_create_intent("티켓 목록에서 찾아서 새 티켓 만들어줘", {})


def test_summarize_plus_create_prioritizes_create():
    # 지시서 §19.2: 요약/정리 + 생성이 함께면 뒤에 읽기 동사(보여/알려)가 와도 최종 액션은
    # '생성'이다. 예전엔 create_verb_leads가 뒤 동사를 우선해 요약(claude_query)으로 샜다.
    assert m.is_create_intent("회의록 정리해서 티켓 만들어서 보여줘", {})
    assert m.is_create_intent("이번주 완료 작업 요약해서 티켓으로 등록하고 알려줘", {})
    assert m.is_create_intent("정리해서 티켓 만들어줘", {})
    assert m.is_create_intent("지금까지 대화 요약해서 이슈로 등록해줘", {})
    # 요약/정리만 있고 생성 동사가 없으면 순수 요약이다 — 생성 아님.
    assert not m.is_create_intent("진행중인 티켓 요약해줘", {})
    assert not m.is_create_intent("이번주 작업 정리해서 보여줘", {})


def test_create_mode_escapes_on_explicit_search():
    # 생성 흐름 중에도 명시적 검색 문장은 조회로 빠져나간다.
    ctx = {"mode": "CREATE", "pending_question": "title"}
    assert not m.is_create_intent("내 티켓 검색해줘", ctx)
    assert not m.is_create_intent("지난주 티켓 찾아줘", ctx)
    # 필드 답변에 들어간 단순 명사는 흐름을 깨지 않는다.
    assert m.is_create_intent("관리자 목록 화면 개선", ctx)


def test_llm_clarify_answer_routes_back_to_create():
    # 결함(runner 갈래가 실행으로 확인): create_ticket의 ready==false(LLM 되물음)
    # NEED_INPUT 경로가 반환 컨텍스트에 mode:"CREATE"를 넣지 않아, 그 되물음에 대한
    # 답변 턴이 route_request에서 다시 create_ticket으로 라우팅되지 않고 조회로 샜다.
    # 대조: 필수값 되묻기(_ask_missing) 경로는 mode:"CREATE"를 설정해 정상이다.
    q = [{"question": "마감일·우선순위·난이도를 알려주세요.", "reason": "필수값", "options": []}]
    empty = {"priority": "", "difficulty": 0, "due_date": "", "assignee_names": [], "unassigned": False}
    body1 = {"message": "포스코DX에 로그인 버그 수정 티켓 만들어줘",
             "requester": CREATE_REQUESTER, "projects": CREATE_PROJECTS,
             "tickets": [], "work_schema": {}, "context": {}}
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=False, fields=empty, questions=q)):
        data1, _ = m.route_request(body1)
    assert data1["action"] == "NEED_INPUT", data1["action"]
    ctx1 = data1["context"]
    # 되물음 컨텍스트는 CREATE 모드를 유지해야 답변 턴이 초안으로 돌아온다(_ask_missing과 동일).
    assert ctx1.get("mode") == "CREATE", ctx1.get("mode")

    # 답변 턴: 생성 동사가 없는 순수 필드 답변이 create_ticket으로 다시 라우팅돼
    # 초안(CREATE_PREVIEW)이 나와야 한다. 버그 상태에서는 '마감' 등이 조회로 샜다.
    full = {"priority": "높음", "difficulty": 3, "due_date": "2026-08-01",
            "assignee_names": [], "unassigned": True}
    body2 = {"message": "마감 2026-08-01, 우선순위 높음, 난이도 3, 미할당",
             "requester": CREATE_REQUESTER, "projects": CREATE_PROJECTS,
             "tickets": [], "work_schema": {}, "context": ctx1}
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=True, fields=full)):
        data2, _ = m.route_request(body2)
    assert data2["action"] == "CREATE_PREVIEW", data2["action"]


def test_llm_clarify_answer_still_lets_cancel_and_query_escape():
    # 과잉수정 방지: 되물음 중 mode:"CREATE"라도 '취소'와 명시적 조회는 여전히 빠져나간다.
    # (mode:CREATE를 넣으면 그 뒤 아무 말이나 생성으로 빨려 들어갈 수 있는 반복 결함 방지 —
    #  is_create_intent의 read_only escape와 route_request의 CANCEL 가드가 이를 막는다.)
    q = [{"question": "마감일을 알려주세요.", "reason": "필수값", "options": []}]
    empty = {"priority": "", "difficulty": 0, "due_date": "", "assignee_names": [], "unassigned": False}
    body1 = {"message": "포스코DX에 로그인 버그 수정 티켓 만들어줘",
             "requester": CREATE_REQUESTER, "projects": CREATE_PROJECTS,
             "tickets": [], "work_schema": {}, "context": {}}
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=False, fields=empty, questions=q)):
        data1, _ = m.route_request(body1)
    ctx1 = data1["context"]
    assert ctx1.get("mode") == "CREATE"

    # '취소'는 진행 문맥을 비우고 빠져나간다.
    cancel_body = {"message": "취소", "requester": CREATE_REQUESTER, "projects": CREATE_PROJECTS,
                   "tickets": [], "work_schema": {}, "context": ctx1}
    cdata, _ = m.route_request(cancel_body)
    assert cdata["action"] == "CANCELLED", cdata["action"]

    # 명시적 조회는 생성이 아니라 조회로 라우팅된다(초안 상태는 그대로 두고 빠져나간다).
    assert not m.is_create_intent("내 티켓 보여줘", ctx1)
    assert not m.is_create_intent("진행중인 티켓 몇 개야?", ctx1)


def test_project_selection_still_folds_original_once():
    # 과잉수정 방지 가드: 선택 턴('1번')은 원본 요청을 여전히 한 번 접어 넣어야 한다
    # ('1번'만으로는 티켓 내용이 없다). 동시에 그 원본은 소비 후 컨텍스트에서 사라져야
    # 다음 턴이 재주입하지 못한다 — 이 둘을 함께 못 박는다.
    HIGH = "높음"
    ctx = {
        "mode": "CREATE",
        "pending_question": "project_selection",
        "project_candidates": [{"id": "p1", "name": "포스코DX"}, {"id": "p2", "name": "포스코ICT"}],
        "pending_original_message": f"우선순위 {HIGH}으로 로그인 버그 티켓 만들어줘 마감 2026-08-01 난이도 3 미할당",
        "creator": {"name": "황형섭", "email": "a@goodmit.co.kr", "teams_user_id": "t1"},
    }
    body = {"message": "1번", "requester": CREATE_REQUESTER,
            "projects": [{"id": "p1", "name": "포스코DX", "primary": [], "secondary": []},
                         {"id": "p2", "name": "포스코ICT", "primary": [], "secondary": []}],
            "tickets": [], "work_schema": {}, "context": ctx}
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=True)):
        data, _ = m.route_request(body)
    assert data["action"] == "CREATE_PREVIEW", data["action"]
    # 원본의 우선순위가 이 턴에서 한 번은 반영돼야 한다.
    assert f"우선순위: {HIGH}" in data["response_text"], data["response_text"]
    # 핵심 수정(round1 검수 확정): 원본은 한 번 쓰고 지운다. 안 지우면 다음 정정/수정 턴이
    # {**previous}로 그것을 물고 와 사용자의 정정을 조용히 덮는다.
    assert "pending_original_message" not in data["context"], "원본이 소비 후 남아 재주입된다"


_AMBIG_PROJECTS = [{"id": "p1", "name": "포스코DX", "primary": [], "secondary": []},
                   {"id": "p2", "name": "포스코ICT", "primary": [], "secondary": []}]


def _project_selection_ctx(original):
    # 프로젝트 모호 턴이 만들어 내는 실제 중간 상태(create_ticket line 4083 참조).
    return {
        "mode": "CREATE",
        "pending_question": "project_selection",
        "project_candidates": [{"id": "p1", "name": "포스코DX"}, {"id": "p2", "name": "포스코ICT"}],
        "pending_original_message": original,
        "creator": {"name": "황형섭", "email": "a@goodmit.co.kr", "teams_user_id": "t1"},
    }


def test_correction_after_selection_not_overridden_by_stale_original():
    # round1 검수 확정 결함(실제 다중 턴 흐름): 프로젝트 선택 왕복 뒤의 되물음 답변 턴에서
    # 재주입된 원본이 왼쪽 앵커 추출기(extract_priority)에 먼저 잡혀 사용자의 정정을 유실시킨다.
    # mode:CREATE 라우팅 수정이 이 경로를 도달 가능하게 만들며 노출됐다. 수정 전에는 선택
    # 턴이 원본을 안 지워 답변 턴 컨텍스트가 계속 물고 왔다.
    HIGH, LOW = "높음", "낮음"
    q = [{"question": "마감/우선순위/난이도?", "reason": "필수", "options": []}]
    empty = {"priority": "", "difficulty": 0, "due_date": "", "assignee_names": [], "unassigned": False}
    # 선택 턴: '1번' → 되물음(ready=false). 이 턴이 원본을 소비하고 지운다.
    sel_body = {"message": "1번", "requester": CREATE_REQUESTER, "projects": _AMBIG_PROJECTS,
                "tickets": [], "work_schema": {},
                "context": _project_selection_ctx(f"우선순위 {HIGH}으로 로그인 버그 티켓 만들어줘")}
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=False, fields=empty, questions=q)):
        sel_data, _ = m.route_request(sel_body)
    assert sel_data["action"] == "NEED_INPUT", sel_data["action"]
    assert "pending_original_message" not in sel_data["context"], "선택 턴이 원본을 소비 후 지워야 한다"

    # 답변 턴: 순수 필드 정정. 재주입될 원본이 없어야 '낮음'이 살아남는다.
    full = {"priority": LOW, "difficulty": 3, "due_date": "2026-08-01", "assignee_names": [], "unassigned": True}
    ans_body = {"message": f"우선순위 {LOW}으로 바꾸고 마감 2026-08-01, 난이도 3, 미할당",
                "requester": CREATE_REQUESTER, "projects": _AMBIG_PROJECTS,
                "tickets": [], "work_schema": {}, "context": sel_data["context"]}
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=True, fields=full)):
        ans_data, _ = m.route_request(ans_body)
    assert ans_data["action"] == "CREATE_PREVIEW", ans_data["action"]
    body_text = ans_data["response_text"]
    assert f"우선순위: {LOW}" in body_text, body_text       # 정정이 반영돼야 한다
    assert f"우선순위: {HIGH}" not in body_text             # 낡은 원본이 재적용되면 안 된다


def test_revision_turn_not_overridden_by_stale_original():
    # 같은 오염의 미리보기→수정(revision) 경로 변형(실제 흐름): 선택 턴이 곧바로 미리보기를
    # 내고, 이어지는 수정 턴의 정정이 이겨야 한다. 수정 전에는 미리보기 컨텍스트가 원본을
    # 물고 있어 수정 턴이 그것을 재주입했다.
    HIGH, LOW = "높음", "낮음"
    ready_fields = {"priority": HIGH, "difficulty": 3, "due_date": "2026-08-01",
                    "assignee_names": [], "unassigned": True}
    # 선택 턴: '1번' → 바로 미리보기(ready=true). 원본('높음')이 이 턴엔 반영되고, 소비 후 지워진다.
    sel_body = {"message": "1번", "requester": CREATE_REQUESTER, "projects": _AMBIG_PROJECTS,
                "tickets": [], "work_schema": {},
                "context": _project_selection_ctx(
                    f"우선순위 {HIGH}으로 로그인 버그 티켓 만들어줘 마감 2026-08-01 난이도 3 미할당")}
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=True, fields=ready_fields)):
        sel_data, _ = m.route_request(sel_body)
    assert sel_data["action"] == "CREATE_PREVIEW", sel_data["action"]
    assert f"우선순위: {HIGH}" in sel_data["response_text"]        # 이 턴엔 원본이 반영된다
    assert "pending_original_message" not in sel_data["context"]  # 소비 후 지워졌다

    # 수정 턴: '우선순위 낮음으로 바꿔줘'. 재주입될 원본이 없어야 '낮음'이 이긴다.
    rev_body = {"message": f"우선순위 {LOW}으로 바꿔줘", "requester": CREATE_REQUESTER,
                "projects": _AMBIG_PROJECTS, "tickets": [], "work_schema": {}, "context": sel_data["context"]}
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=True, fields={**ready_fields, "priority": LOW})):
        rev_data, _ = m.route_request(rev_body)
    assert rev_data["action"] == "CREATE_PREVIEW", rev_data["action"]
    body_text = rev_data["response_text"]
    assert f"우선순위: {LOW}" in body_text, body_text
    assert f"우선순위: {HIGH}" not in body_text


PROJECT_CORPUS = [
    {"name": "M. 현대모비스 [OKE KVM 윈도우 기능 개선] (검증)"},
    {"name": "P. NH손해보험 ClovirSM"},
    {"name": "P. SK하이닉스 [용인 클러스터 대비]"},
    {"name": "P. 인천국제공항공사 [클라우드 인프라 고도화]"},
    {"name": "M. KISA, 한국인터넷진흥원"},
    {"name": "P. 포스코DX [P-Cloud 2.0 포털 구축]"},
]


def _best_project(message):
    scored = sorted(((m.project_score(p, message), p["name"]) for p in PROJECT_CORPUS), reverse=True)
    return scored[0][1] if scored[0][0] else None


def test_project_reference_needs_a_name_not_a_coincidence():
    # 프로젝트 이름에 흔한 낱말이 들어 있다는 이유로 조건이 붙으면 0건이 나온다.
    assert _best_project("티켓 생성 기능 검증 검색해줘") is None
    assert _best_project("기능 개선 티켓 보여줘") is None
    assert _best_project("검증 상태인 티켓 보여줘") is None
    assert _best_project("배포 관련 티켓 보여줘") is None
    assert _best_project("이번주 마감인 작업 알려줘") is None
    assert _best_project("프로젝트 목록 보여줘") is None


def test_project_reference_matches_real_names():
    assert _best_project("NH손해보험 티켓 보여줘") == "P. NH손해보험 ClovirSM"
    assert _best_project("SK하이닉스 진행중인 티켓 몇개야") == "P. SK하이닉스 [용인 클러스터 대비]"
    assert _best_project("현대모비스 티켓 보여줘") == "M. 현대모비스 [OKE KVM 윈도우 기능 개선] (검증)"
    assert _best_project("포스코DX 마감 임박한 거") == "P. 포스코DX [P-Cloud 2.0 포털 구축]"
    assert _best_project("ClovirSM 관련 작업") == "P. NH손해보험 ClovirSM"
    assert _best_project("한국인터넷진흥원 현황") == "M. KISA, 한국인터넷진흥원"
    # 짧은 코드명도 프로젝트 이름의 한 낱말이면 지목으로 인정한다.
    assert _best_project("KISA 티켓 보여줘") == "M. KISA, 한국인터넷진흥원"


def test_project_entity_question_is_about_projects():
    assert m.asks_about_projects(m.norm("프로젝트 목록 보여줘"))
    assert m.asks_about_projects(m.norm("내 프로젝트 보여줘"))
    # 티켓을 프로젝트로 묶어 달라는 요청은 프로젝트 목록이 아니다.
    assert not m.asks_about_projects(m.norm("프로젝트별로 티켓 정리해줘"))
    assert not m.asks_about_projects(m.norm("프로젝트 티켓 보여줘"))
    assert m.mentions_own(m.norm("내 프로젝트 보여줘"))
    assert not m.mentions_own(m.norm("프로젝트 목록 보여줘"))
    assert not m.mentions_own(m.norm("사내 프로젝트 목록"))


def test_person_label_never_shows_a_raw_identifier():
    assert m.person_label({"id": "239d872b-594c-8163", "name": "", "email": ""}) == "이름 미확인 담당자"
    assert m.person_label({"id": "x", "name": "정현수", "email": "a@b.c"}) == "정현수"
    assert m.person_label({"id": "x", "name": "", "email": "a@b.c"}) == "a@b.c"


def test_backfill_gives_a_nameless_person_the_known_name():
    directory = [{"id": "u1", "name": "정현수", "email": "hs@x.com"}]
    tickets = [{"assignees": [{"id": "u1", "name": "", "email": ""}]}]
    projects = [{"primary": [{"id": "u1", "name": "", "email": ""}], "secondary": []}]
    m.backfill_people(directory, projects, tickets)
    assert tickets[0]["assignees"][0]["name"] == "정현수"
    assert projects[0]["primary"][0]["name"] == "정현수"


def test_create_accepts_a_ticket_with_no_project():
    # 작업 DB에는 프로젝트 없는 티켓이 실제로 존재한다. 사용자가 없다고 답하면 받아들인다.
    assert m.declines_project(m.norm("프로젝트는 없음"))
    assert m.declines_project(m.norm("프로젝트 없이 만들어줘"))
    assert m.declines_project(m.norm("프로젝트 미지정"))
    assert not m.declines_project(m.norm("NH손해보험 프로젝트에 만들어줘"))


def test_create_body_leaves_the_relation_empty_without_a_project():
    schema = {"properties": {
        "제목": {"type": "title"},
        "진행 상태": {"type": "status"},
        "마감일": {"type": "date"},
        "우선순위": {"type": "select"},
        "난이도": {"type": "number"},
        "프로젝트": {"type": "relation"},
        "티켓 담당자": {"type": "people"},
    }}
    ctx = {"selected_project": dict(m.NO_PROJECT), "status": "계획", "due_date": "2026-07-31",
           "priority": "낮음", "difficulty": 1, "assignee_ids": [], "original_request": "x"}
    body, err = m.build_create_body(schema, {"title": "제목", "background": "b", "requirements": [], "acceptance_criteria": []}, ctx)
    assert not err
    assert body["properties"]["프로젝트"] == {"relation": []}


# --- 3.15.0 검수 확정 결함 회귀 ------------------------------------------------
# 아래 문장들은 모두 라이브에서 실제로 틀린 답을 냈던 원문이다.

STATUS_MAP_FULL = {
    "계획": "계획", "계획중": "계획", "예정": "계획", "대기": "계획",
    "진행": "진행", "진행중": "진행", "작업중": "진행",
    "완료": "완료", "끝난": "완료", "종료": "완료",
    "검증": "검증", "검토": "검증",
    "이슈": "이슈", "문제": "이슈",
    "취소": "취소",
}


def _statuses(message):
    return m.resolve_status_intent(message, STATUS_MAP_FULL)["selected"]


def test_status_alias_needs_an_anchor_not_a_coincidence():
    # 일상 명사와 티켓 제목 속 상태 낱말이 상태 필터로 둔갑하면 0건이 나오거나
    # 엉뚱한 목록이 나온다(라이브에서 이 결함으로 엉뚱한 티켓에 댓글이 달렸다).
    assert _statuses("결제 문제 관련 티켓 보여줘") == []
    assert _statuses("프로젝트 진행 상황 알려줘") == []
    assert _statuses("[자동 검증] 챗봇 쓰기 경로 점검 티켓 보여줘") == []
    assert _statuses("대기 시간이 긴 화면 알려줘") == []
    assert _statuses("검토 의견 정리해줘") == []


def test_status_alias_still_read_where_a_condition_is_stated():
    assert _statuses("진행중인 티켓 보여줘") == ["진행"]
    assert _statuses("계획인 것만") == ["계획"]
    assert _statuses("상태가 완료인 티켓") == ["완료"]
    assert _statuses("검증 상태인 티켓 보여줘") == ["검증"]
    assert _statuses("이슈 티켓 보여줘") == ["이슈"]
    assert _statuses("진행만") == ["진행"]
    assert _statuses("계획된 작업 보여줘") == ["계획"]
    assert _statuses("진행중") == ["진행"]  # 상태만 말한 짧은 후속


def test_ticket_title_never_becomes_a_status_change():
    # 제목이 '배포 완료 안내'인 티켓의 마감일만 바꾸랬는데 진행상태가 완료로 뒤집혔다.
    ticket = {**UPDATE_TICKET, "id": "bd1", "title": "배포 완료 안내", "status": "진행"}
    smap = {"진행": "진행", "완료": "완료", "계획": "계획"}
    with mock.patch.object(m.subprocess, "run") as run:
        data = m.update_ticket("배포 완료 안내 티켓 마감일을 내일로 바꿔줘", {}, CREATE_REQUESTER,
                               CREATE_CURRENT_USER, CREATE_DIRECTORY, [ticket], UPDATE_SCHEMA, smap)
    assert not run.called
    assert data["action"] == "WRITE_UPDATE", data["action"]
    changes = data["changes"]
    assert "status" not in changes, f"사용자가 말하지 않은 상태 변경: {changes}"
    assert changes.get("due_date")


def test_status_change_only_from_the_instructing_position():
    smap = {"진행": "진행", "진행중": "진행", "완료": "완료", "계획": "계획"}
    assert m.detect_target_status("배포 완료 안내 티켓 마감일을 내일로 바꿔줘", smap) == ""
    assert m.detect_target_status("완료 보고서 티켓 담당자를 나한테 할당해줘", smap) == ""
    # 지시 위치의 상태는 그대로 읽는다.
    assert m.detect_target_status("진행으로 바꿔줘", smap) == "진행"
    assert m.detect_target_status("완료 상태로 변경해줘", smap) == "완료"
    assert m.detect_target_status("진행중으로 바꿔줘", smap) == "진행"
    assert m.detect_target_status("다 완료했어", smap) == "완료"


def test_priority_needs_its_own_anchor_and_difficulty_is_a_grade():
    # '난이도 높은 티켓 보여줘'가 우선순위 필터가 되어 정반대 데이터를 돌려줬다.
    assert m.extract_priority("난이도 높은 티켓 보여줘") == ""
    assert m.extract_difficulty_filter("난이도 높은 티켓 보여줘") == {"value": 4, "op": "이상"}
    assert m.extract_difficulty_filter("난이도 낮은 티켓 보여줘") == {"value": 2, "op": "이하"}
    assert m.extract_difficulty_filter("난이도 쉬운 것만") == {"value": 2, "op": "이하"}
    # 정렬 요청은 필터가 아니다 — 필터로 둔갑하면 나머지 데이터가 숨는다.
    assert m.extract_priority("우선순위 높은 순으로 보여줘") == ""
    assert m.extract_sort("우선순위 높은 순으로 보여줘") == "PRIORITY"
    assert m.extract_difficulty_filter("난이도 높은 순으로 보여줘") is None
    # 진짜 우선순위 조건은 계속 읽는다.
    assert m.extract_priority("우선순위 높은 티켓 보여줘") == "높음"
    assert m.extract_priority("우선순위 높음으로 바꿔줘") == "높음"


def test_priority_answer_without_the_word_priority_is_still_a_priority():
    # '우선순위' 앵커를 강제한 탓에 봇이 '우선순위를 알려주세요'라고 묻고도 사용자의
    # 답('높음')을 하나도 못 읽어 같은 질문을 무한히 되묻던 결함.
    for answer, expected in [("높음", "높음"), ("낮음", "낮음"), ("중간", "중간"),
                             ("보통", "중간"), ("긴급", "높음"), ("high", "높음")]:
        assert m.extract_priority(answer) == expected, answer
        # 되묻기 목록에서 빠져야 대화가 다음 질문으로 넘어간다.
        assert "우선순위" not in m.create_missing_fields(
            "2026-07-20", m.extract_priority(answer), 3, [{"id": "u1"}], False
        ), answer
    # 앵커 없는 자연스러운 조회도 우선순위 조건이다.
    assert m.extract_priority("긴급 티켓 보여줘") == "높음"
    assert m.extract_priority("높음으로 바꿔줘") == "높음"
    # 그래도 난이도 구절은 우선순위가 아니다(원래 결함이 되살아나지 않는지 함께 고정).
    assert m.extract_priority("난이도 높은 티켓 보여줘") == ""
    assert m.extract_priority("난이도 낮은 순으로 보여줘") == ""


def test_comment_question_is_answered_not_written():
    # 댓글 분기를 자유대화 앞으로 옮기면서 본문 없는 '댓글 어떻게 달아?'까지
    # 쓰기 흐름으로 끌고 가 대화 응답 대신 티켓을 되묻던 회귀.
    assert m.is_comment_intent("댓글 어떻게 달아?")
    assert m.is_freeform_query("댓글 어떻게 달아?")
    assert m.extract_comment_text("댓글 어떻게 달아?") == ""
    with mock.patch.object(m, "claude_query", return_value={"action": "FREEFORM"}) as llm:
        data, _ = m.route_request({"message": "댓글 어떻게 달아?", "message_id": "cq1",
                                   "conversation_id": "cv-cq", "requester": {"email": "a@x", "name": "황형섭"},
                                   "projects": [], "tickets": [], "work_schema": {}})
    assert llm.called, "본문 없는 댓글 질문은 대화로 답해야 한다"
    assert data["action"] == "FREEFORM"


def test_week_is_monday_to_sunday_everywhere():
    from datetime import date
    # 토·일 마감이 빠지지 않는다. 금요일 이후에도 start>end가 되지 않는다.
    for today, label in [(date(2026, 7, 15), "수"), (date(2026, 7, 18), "토"), (date(2026, 7, 19), "일")]:
        this_week = m.parse_date_range("이번주 마감 티켓", today)
        assert this_week["start"] == "2026-07-13", (label, this_week)
        assert this_week["end"] == "2026-07-19", (label, this_week)
        assert this_week["start"] <= this_week["end"]
        next_week = m.parse_date_range("다음주 마감 티켓", today)
        assert (next_week["start"], next_week["end"]) == ("2026-07-20", "2026-07-26"), label
        last_week = m.parse_date_range("지난주 마감 티켓", today)
        assert (last_week["start"], last_week["end"]) == ("2026-07-06", "2026-07-12"), label


def test_impossible_date_asks_back_instead_of_dropping_the_filter():
    from datetime import date
    assert m.parse_date_range("2월 30일까지 티켓 보여줘", date(2026, 7, 15)) == {
        "mode": "INVALID", "label": "2월 30일"}
    assert m.parse_date_range("2026-02-30 마감", date(2026, 7, 15))["mode"] == "INVALID"
    data = m.query_tickets("2월 30일 마감 티켓 보여줘", {}, {"email": "a@x", "name": "문의진"},
                           {"id": "u1"}, PROJECTS, TICKETS, {})
    assert data["action"] == "NEED_INPUT", data["action"]
    assert "없는 날짜" in data["response_text"]


def test_creating_work_is_not_only_about_the_word_ticket():
    assert m.is_create_intent("작업 만들어줘", {})
    assert m.is_create_intent("업무 하나 추가해줘", {})
    assert m.is_create_intent("할일 등록해줘", {})
    assert m.is_create_intent("일감 생성해줘", {})
    # 뒤에 오는 조회 동사가 이긴다는 기존 규칙은 유지된다.
    assert not m.is_create_intent("작업 생성 관련 티켓 보여줘", {})


def test_natural_change_verbs_reach_the_write_flow():
    smap = {"진행": "진행", "완료": "완료"}
    assert m.is_update_intent("마감일 내일로 미뤄줘", {}, smap)
    assert m.is_update_intent("마감일 내일로 당겨줘", {}, smap)
    assert m.is_update_intent("마감일을 다음주로 늦춰줘", {}, smap)
    assert m.is_update_intent("마감일 하루만 앞당겨줘", {}, smap)
    # 조회는 여전히 조회다.
    assert not m.is_update_intent("마감 임박한 티켓 보여줘", {}, smap)


def test_comment_wins_over_conversation():
    # 댓글 본문에 '정리/요약/왜'가 들어가면 댓글이 조용히 안 달리고 대화 응답만 나갔다.
    msg = '1번 티켓에 "진행 상황 정리해서 공유함"이라고 댓글 남겨줘'
    assert m.is_freeform_query(msg), "본문 때문에 자유대화 마커가 켜지는 상황을 재현"
    assert m.is_comment_intent(msg)
    raw = {"id": "t1", "url": "", "properties": {
        "제목": {"type": "title", "title": [{"plain_text": "로그인 버그"}]},
        "진행상태": {"type": "select", "select": {"name": "진행"}},
        "티켓 담당자": {"type": "people", "people": []}}}
    with mock.patch.object(m.subprocess, "run") as run:
        data, _ = m.process_request({"message": msg, "message_id": "cm1", "conversation_id": "cv-cm",
                                     "requester": {"email": "a@x", "name": "황형섭"},
                                     "projects": [], "tickets": [raw], "work_schema": {},
                                     "context": {"last_results": ["t1"], "last_result_start": 1}})
    assert not run.called, "댓글은 LLM 대화로 새면 안 된다"
    # 이 티켓은 담당자가 비어 있어 '내 티켓'이 아니다. 그래서 바로 쓰지 않고 대상을 보여주며
    # 확인을 받는다. 요점은 댓글 요청이 자유대화로 새지 않는다는 것이다.
    assert data["action"] == "COMMENT_PREVIEW", data["action"]
    assert data["context"]["pending_action"]["kind"] == "COMMENT"


def test_group_axis_is_not_a_person_name():
    # '담당자별로 보여줘'가 '별로'라는 담당자를 찾다가 NEED_INPUT을 냈다.
    assert m._explicit_assignee_token("담당자별로 보여줘") == ""
    assert m._explicit_assignee_token("담당자 기준으로 보여줘") == ""
    assert m.extract_group_by("담당자별로 보여줘") == "assignee"
    data = m.query_tickets("담당자별로 티켓 정리해줘", {}, {"email": "a@x", "name": "문의진"},
                           {"id": "u1"}, PROJECTS, TICKETS, {})
    assert data["action"] == "TICKET_SUMMARY", data["action"]
    # 사람 이름은 계속 읽는다.
    assert m._explicit_assignee_token("문의진 담당 티켓") == "문의진"


def test_nameless_assignee_is_not_counted_as_unassigned():
    # 이름이 빈 사람을 '미할당'에 합산하면 '미할당 티켓 보여줘'와 건수가 어긋난다.
    nameless = {**TICKETS[0], "id": "n1", "assignees": [{"id": "u9", "name": "", "email": ""}]}
    unassigned = {**TICKETS[0], "id": "n2", "title": "주인 없음", "assignees": []}
    data = m.query_tickets("담당자별로 티켓 정리해줘", {}, {"email": "a@x", "name": "문의진"},
                           {"id": "u1"}, PROJECTS, [nameless, unassigned], {})
    assert "■ 미할당: 1건" in data["response_text"], data["response_text"]
    assert "■ 이름 미확인 담당자: 1건" in data["response_text"], data["response_text"]


def test_project_role_shows_every_owner_and_never_hides_one():
    two = {"primary": [{"id": "a", "name": "김철수"}, {"id": "b", "name": "이영희"}], "secondary": []}
    assert m.project_role(two, None, {"name": "x", "email": "y"}) == "담당자 정 김철수, 이영희"
    nameless = {"primary": [{"id": "a", "name": "", "email": ""}], "secondary": []}
    assert m.project_role(nameless, None, {"name": "x", "email": "y"}) == "담당자 정 이름 미확인 담당자"
    empty = {"primary": [], "secondary": []}
    assert m.project_role(empty, None, {"name": "x", "email": "y"}) == "담당자 미지정"


# --- 3.15.0: 완료 조회·문맥 유지 회귀 ------------------------------------------
DONE_SMAP = {"계획": "계획", "진행": "진행", "완료": "완료", "취소": "취소"}
DONE_PROJECTS = [
    {"id": "p1", "name": "포스코DX", "status": "진행", "primary": [{"id": "u1", "name": "문의진"}], "secondary": []},
    {"id": "p2", "name": "NH손해보험", "status": "진행", "primary": [{"id": "u2", "name": "남기훈"}], "secondary": []},
]


def _t(tid, status, due, pid="p1", pname="포스코DX", who="문의진", uid="u1"):
    return {"id": tid, "ticket_id": "G" + tid, "title": "T" + tid, "status": status,
            "priority": "중간", "difficulty": "", "due_date": due, "start_date": "",
            "assignees": [{"id": uid, "name": who}], "project_ids": [pid], "project_names": [pname]}


DONE_TICKETS = [
    _t("a", "완료", "2026-07-15"), _t("b", "완료", "2026-07-08"),
    _t("c", "진행", "2026-07-15"), _t("d", "계획", "2026-07-16"),
]
DONE_REQUESTER = {"email": "a@x", "name": "문의진"}
DONE_USER = {"id": "u1", "name": "문의진"}


class _FakeNow:
    @staticmethod
    def date():
        from datetime import date
        return date(2026, 7, 15)

    @staticmethod
    def isoformat():
        return "2026-07-15T09:00:00+09:00"


def _query(message, ctx=None, tickets=None):
    with mock.patch.object(m, "now_kst", return_value=_FakeNow()):
        return m.query_tickets(message, ctx or {}, DONE_REQUESTER, DONE_USER,
                               DONE_PROJECTS, tickets or DONE_TICKETS, DONE_SMAP)


def test_dated_completed_query_is_not_self_contradictory():
    # 라벨은 '(완료, 오늘)'인데 statuses=['완료'] + exclude_completed=True로 항상 0건이었다.
    data = _query("오늘 완료된 티켓만 보여줘")
    assert data["action"] == "TICKET_LIST", data["action"]
    assert data["total"] == 1, data["response_text"]
    assert data["context"]["last_query"]["exclude_completed"] is False
    assert [t["id"] for t in data["tickets"]] == ["a"]

    last = _query("지난주에 완료한 티켓 보여줘")
    assert last["total"] == 1, last["response_text"]
    assert [t["id"] for t in last["tickets"]] == ["b"]

    # 완료를 말하지 않으면 기존 기본값(완료 제외)은 그대로다.
    default = _query("오늘 마감인 티켓 보여줘")
    assert default["context"]["last_query"]["exclude_completed"] is True
    assert [t["id"] for t in default["tickets"]] == ["c"]


def test_a_persons_name_never_switches_off_completed_tickets():
    # '남' 한 글자 원문 검사가 '남기훈'·'강남'·'하남'에 걸려 완료 조회가 0건이 됐다.
    tickets = DONE_TICKETS + [_t("e", "완료", "2026-07-15", pid="p2", pname="NH손해보험",
                                 who="남기훈", uid="u2")]
    data = _query("남기훈 담당 완료 티켓 보여줘", tickets=tickets)
    assert data["action"] == "TICKET_LIST", data["action"]
    assert data["context"]["last_query"]["exclude_completed"] is False
    assert [t["id"] for t in data["tickets"]] == ["e"], data["response_text"]
    # '남은'은 resolve_status_intent가 계속 완료 제외로 읽는다.
    remaining = _query("남은 티켓 보여줘")
    assert remaining["context"]["last_query"]["exclude_completed"] is True


def _list_query_context(**over):
    base = {"kind": "list", "scope": "MY_TICKETS", "statuses": [], "excluded_statuses": [],
            "exclude_completed": True, "due_filter": None, "priority": "", "difficulty_filter": None,
            "assignee_filter": None, "keyword": "", "sort": "DUE_ASC", "group_by": "",
            "offset": 0, "limit": 10}
    return {"last_query": {**base, **over}}


def test_followup_include_completed_survives_a_deadline_filter():
    # 같은 '완료 포함' 요청인데 마감 조건이 붙으면 무시돼 결과가 달라졌다.
    ctx = _list_query_context()
    plain = _query("완료 포함해서 보여줘", ctx)
    assert plain["context"]["last_query"]["exclude_completed"] is False
    assert plain["total"] == 4, plain["response_text"]

    dated = _query("오늘 마감인 것 완료 포함해서 보여줘", ctx)
    assert dated["context"]["last_query"]["exclude_completed"] is False, dated["response_text"]
    assert sorted(t["id"] for t in dated["tickets"]) == ["a", "c"], dated["response_text"]


def test_followup_deadline_keeps_an_inherited_completed_filter():
    # 직전에 확정한 statuses=['완료']가 마감 조건 때문에 0건이 되면 안 된다.
    ctx = _list_query_context(statuses=["완료"], exclude_completed=False)
    data = _query("오늘 마감인 것만 보여줘", ctx)
    assert data["context"]["last_query"]["exclude_completed"] is False, data["response_text"]
    assert [t["id"] for t in data["tickets"]] == ["a"], data["response_text"]


def test_demonstrative_followup_keeps_the_confirmed_project():
    # '그 프로젝트'가 무시되면 담당하지도 않는 전사 티켓이 통째로 노출됐다.
    tickets = DONE_TICKETS + [_t("e", "진행", "2026-07-15", pid="p2", pname="NH손해보험",
                                 who="남기훈", uid="u2")]
    ctx = {**_list_query_context(scope="PROJECT_TICKETS", project_id="p1", project_name="포스코DX"),
           "selected_project": DONE_PROJECTS[0]}
    assert m.is_query_followup("그 프로젝트 티켓 보여줘", ctx)
    data = _query("그 프로젝트 티켓 보여줘", ctx, tickets=tickets)
    assert data["action"] == "TICKET_LIST", data["action"]
    assert data["context"]["last_query"]["project_id"] == "p1"
    assert all("NH손해보험" not in (t.get("project_names") or []) for t in data["tickets"])
    assert data["total"] == 2, data["response_text"]
    # 새 프로젝트 이름을 말하면 문맥이 아니라 그 이름이 이긴다.
    fresh = _query("NH손해보험 티켓 보여줘", ctx, tickets=tickets)
    assert fresh["context"]["last_query"]["project_id"] == "p2", fresh["response_text"]


def test_image_note_records_the_files_this_message_stored(tmp_path, monkeypatch):
    # 첨부 단계가 대화 폴더를 훑어 가장 오래된 사진을 붙이던 결함의 반대편.
    # 이번 메시지가 저장한 파일 이름을 노트에 남겨야 그 사진만 붙일 수 있다.
    monkeypatch.setattr(m, "IMAGE_DIR", str(tmp_path))
    png = base64.b64encode(
        bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 32
    ).decode()
    monkeypatch.setattr(m, "analyze_images", lambda saved, message: ({"summary": "s", "ocr_text": "", "notable": [], "suggested_title": ""}, "", 1))
    ctx, _ = m.ingest_image_attachments(
        [{"media_type": "image/png", "data": png, "filename": "a.png"}], {}, "conv-1", "화면 오류", "msg-1"
    )
    note = ctx["image_notes"][-1]
    assert note["message_id"] == "msg-1"
    assert len(note["stored_files"]) == 1
    assert note["stored_files"][0].endswith(".png")


def test_named_subject_that_matches_nothing_is_admitted_not_papered_over():
    # 이름을 댔는데 못 찾으면 못 찾았다고 해야 한다. 전체 목록을 내놓으면 사용자는
    # 그 목록이 자기가 말한 이름의 티켓인 줄 안다.
    data = m.query_tickets("화성 탐사 프로젝트 티켓 보여줘", {}, {"email": "a@x", "name": "문의진"},
                           {"id": "u1"}, PROJECTS, TICKETS, {})
    assert data["total"] == 0
    assert "찾지 못했습니다" in data["response_text"]
    assert "프로젝트" in data["response_text"]
    assert data["choices"]


def test_named_subject_finds_the_ticket_by_title():
    # 따옴표 없이 제목을 말해도 그 제목으로 찾는다.
    target = {**TICKETS[0], "id": "tt1", "title": "[자동 검증] 챗봇 쓰기 경로 점검"}
    data = m.query_tickets("[자동 검증] 챗봇 쓰기 경로 점검 티켓 보여줘", {}, {"email": "a@x", "name": "문의진"},
                           {"id": "u1"}, PROJECTS, [target] + TICKETS, {})
    assert data["total"] == 1
    assert data["tickets"][0]["id"] == "tt1"


def test_plain_list_requests_are_not_treated_as_a_name():
    # 이름을 대지 않은 평범한 요청은 그대로 목록이어야 한다.
    for message in ["티켓 보여줘", "전체 티켓 보여줘", "내 티켓 보여줘", "티켓 12개씩 보여줘", "최신순으로 보여줘"]:
        data = m.query_tickets(message, {}, {"email": "a@x", "name": "문의진"}, {"id": "u1"}, PROJECTS, TICKETS, {})
        assert "찾지 못했습니다" not in data["response_text"], message


def test_the_bot_quotes_what_the_person_typed_not_the_normalised_form():
    # 대조용 정규화 문자열('화성탐사')을 되돌려주면 기계처럼 읽힌다.
    assert m.spoken_phrase("화성 탐사 프로젝트 티켓 보여줘", "화성탐사") == "화성 탐사"
    assert m.spoken_phrase("[자동 검증] 챗봇 점검 티켓 보여줘", "자동검증챗봇점검") == "[자동 검증] 챗봇 점검"
    # 조사는 받침에 맞춘다.
    assert m.with_particle("화성 탐사", "이라는", "라는") == "라는"
    assert m.with_particle("이슈판", "이라는", "라는") == "이라는"
    assert m.with_particle("ClovirSM", "이라는", "라는") == "이라는"


def test_not_found_message_reads_like_a_person_wrote_it():
    data = m.query_tickets("화성 탐사 프로젝트 티켓 보여줘", {}, {"email": "a@x", "name": "문의진"},
                           {"id": "u1"}, PROJECTS, TICKETS, {})
    assert "'화성 탐사'라는 이름의 프로젝트를 찾지 못했습니다." in data["response_text"]


def test_month_is_the_whole_month_everywhere():
    from datetime import date

    # 주를 월~일로 통일한 것과 같은 이유다. '이번 달'만 오늘부터 세면 이번 달에 이미 지난
    # 마감이 조용히 빠지고, '지난달'/'다음 달'과 정의가 어긋난다.
    today = date(2026, 7, 16)
    this_month = m.parse_date_range("이번달 마감인 티켓", today)
    assert this_month["start"] == "2026-07-01" and this_month["end"] == "2026-07-31"
    last_month = m.parse_date_range("지난달 마감", today)
    assert last_month["start"] == "2026-06-01" and last_month["end"] == "2026-06-30"
    next_month = m.parse_date_range("다음달 마감", today)
    assert next_month["start"] == "2026-08-01" and next_month["end"] == "2026-08-31"


def _status_map_from_aliases():
    return {m.norm(a): actual for actual, aliases in m.STATUS_ALIASES.items() for a in [actual, *aliases]}


def test_spoken_status_forms_are_understood():
    # 재검수 회귀: 앵커를 요구하면서 가장 흔한 구어체 '~인 것/거 보여줘'를 새로 막았다.
    sm = _status_map_from_aliases()
    assert m.resolve_status_intent("진행중인 것 보여줘", sm)["selected"] == ["진행"]
    assert m.resolve_status_intent("진행중인 거 보여줘", sm)["selected"] == ["진행"]
    # 일상 명사는 여전히 상태가 아니다.
    assert m.resolve_status_intent("결제 문제 관련 티켓 보여줘", sm)["selected"] == []
    assert m.resolve_status_intent("프로젝트 진행 상황 알려줘", sm)["selected"] == []


def test_every_listed_status_survives():
    # 재검수 회귀: 나열하면 마지막 하나만 남아 앞의 상태가 조용히 사라졌다.
    sm = _status_map_from_aliases()
    assert m.resolve_status_intent("계획과 진행 상태 티켓", sm)["selected"] == ["계획", "진행"]
    assert m.resolve_status_intent("진행중이거나 검증중인 티켓 보여줘", sm)["selected"] == ["진행", "검증"]
    assert m.resolve_status_intent("검증이랑 이슈 티켓", sm)["selected"] == ["검증", "이슈"]


def test_difficulty_reads_both_word_orders():
    # 재검수: '난이도 높은'만 고치고 '높은 난이도'를 두면 어순만 뒤집어 같은 결함이 재현된다.
    for message in ["난이도 높은 티켓 보여줘", "높은 난이도 티켓 보여줘", "어려운 난이도 티켓"]:
        assert m.extract_priority(message) == "", message
        assert m.extract_difficulty_filter(message) == {"value": 4, "op": "이상"}, message
    assert m.extract_difficulty_filter("낮은 난이도 작업 보여줘") == {"value": 2, "op": "이하"}


def test_priority_word_in_a_title_is_not_a_priority_filter():
    # 재검수: 앵커 없는 폴백이 '중간 점검'을 우선순위 중간 조회로 만들었다.
    assert m.extract_priority("중간 점검 티켓 보여줘") == ""
    assert m.extract_priority("높은 확률로 지연될 티켓") == ""
    # 봇이 우선순위를 물었을 때의 한 낱말 답변과 그 자체로 우선순위인 낱말은 계속 인정한다.
    assert m.extract_priority("높음") == "높음"
    assert m.extract_priority("긴급 티켓 보여줘") == "높음"
    assert m.extract_priority("우선순위 높은 티켓") == "높음"


def test_group_axis_suffixes_are_defined_once():
    # 재검수: 축 어미를 두 곳에 나눠 적어, 이름 해석은 걷어내는데 집계는 인식하지 못했다.
    assert m.extract_group_by("담당자 기준으로 묶어줘") == "assignee"
    assert m.extract_group_by("담당자별로 보여줘") == "assignee"
    assert m.extract_group_by("프로젝트별로 정리해줘") == "project"


def test_an_unknown_condition_is_not_declared_a_missing_name():
    # 재검수 치명적 회귀: 못 알아들은 조건을 이름으로 단정해 있는 데이터를 없다고 답했다.
    mine = {**TICKETS[0], "id": "mine1", "title": "내 작업", "assignees": [{"id": "u1", "name": "문의진", "email": "a@x"}]}
    for message in ["내가 담당하는 티켓 보여줘", "마감 임박한 티켓 알려줘", "진행중인 것 보여줘"]:
        data = m.query_tickets(message, {}, {"email": "a@x", "name": "문의진"}, {"id": "u1"}, PROJECTS, [mine] + TICKETS, {})
        assert "찾지 못했습니다" not in data["response_text"], message
        assert data["total"] > 0, message
    # 프로젝트를 이름으로 지목했는데 없는 경우는 여전히 단정한다.
    data = m.query_tickets("화성 탐사 프로젝트 티켓 보여줘", {}, {"email": "a@x", "name": "문의진"},
                           {"id": "u1"}, PROJECTS, TICKETS, {})
    assert "찾지 못했습니다" in data["response_text"] and data["total"] == 0


def test_asking_for_my_own_work_is_not_a_fixed_phrase_list():
    # 나열식으로 관리하면 나열에 없는 표현이 전부 전체 목록으로 새어나간다.
    # 띄어쓰기가 살아 있는 원문으로 본다 — 정규화하면 '사내 티켓'과 '내 티켓'을 가를 수 없다.
    for message in ["내 티켓 보여줘", "내가 담당하는 티켓 보여줘", "나한테 할당된 작업",
                    "제가 맡은 업무 보여줘", "내가 해야 할 일 보여줘", "내 미완료 작업 몇 건이야?"]:
        assert m.asks_for_own_work(message), message
    # '내일'과 '제일'은 1인칭이 아니다. 내 프로젝트를 묻는 것도 내 티켓 조회가 아니다.
    for message in ["내일 마감인 티켓 보여줘", "내일까지 끝내야 하는 작업", "제일 급한 티켓",
                    "내 프로젝트 보여줘", "전체 티켓 보여줘", "문의진 담당 티켓",
                    "내 동료가 만든 티켓"]:
        assert not m.asks_for_own_work(message), message


def test_my_work_phrases_do_not_swallow_lookalikes():
    # '사내'의 '내'와 '내일'의 '내'는 1인칭이 아니다.
    assert m.asks_for_own_work("완료된 건 빼고 내 티켓 보여줘")
    assert m.asks_for_own_work("내티켓보여줘")
    assert not m.asks_for_own_work("사내 티켓 관리 개선")
    assert not m.asks_for_own_work("안내 문서 작업")


def test_commenting_on_someone_elses_ticket_asks_first():
    # 남의 티켓에 댓글을 다는 것은 정상 업무다. 다만 대상 해석이 틀렸을 때 사용자가
    # 알아챌 수 있어야 한다. 실제로 제목 검색이 상태 조건으로 둔갑해 엉뚱한 고객 티켓에
    # 검증용 댓글이 달린 적이 있다.
    other = {**UPDATE_TICKET, "id": "tk9", "title": "남의 티켓",
             "assignees": [{"id": "u9", "name": "서윤경", "email": "seoyk@x.com"}]}
    ctx = {"last_results": ["tk9"], "last_result_start": 1}
    data = m.comment_ticket('1번 티켓에 "확인 부탁드립니다"라고 댓글 남겨줘', ctx, [other],
                            {"email": "a@x", "name": "문의진"}, {"id": "u1"})
    assert data["action"] == "COMMENT_PREVIEW"
    assert "서윤경" in data["response_text"]
    assert not data.get("write_request")
    assert data["context"]["pending_action"]["kind"] == "COMMENT"

    # 확인하면 그때 실제로 쓴다.
    confirmed = m.handle_confirmation(data["context"], {}, [other], {"id": "u1"}, {"email": "a@x", "name": "문의진"})
    assert confirmed["action"] == "WRITE_COMMENT"
    wr = confirmed["write_request"]
    assert wr["kind"] == "COMMENT" and wr["page_id"] == "tk9"
    assert "확인 부탁드립니다" in wr["body"]["rich_text"][0]["plain_text"]


def test_commenting_on_my_own_ticket_is_direct():
    mine = {**UPDATE_TICKET, "id": "tk1", "assignees": [{"id": "u1", "name": "문의진", "email": "a@x"}]}
    ctx = {"last_results": ["tk1"], "last_result_start": 1}
    data = m.comment_ticket('1번 티켓에 "내일 배포 예정"이라고 댓글 남겨줘', ctx, [mine],
                            {"email": "a@x", "name": "문의진"}, {"id": "u1"})
    assert data["action"] == "WRITE_COMMENT"
    assert data["write_request"]["page_id"] == "tk1"


def test_same_name_different_company_email_is_a_different_person():
    # 이름만 같고 이메일이 다르면 다른 사람이다. 이어붙이면 동명이인의 티켓을 본인 것처럼
    # 보고 바꿀 수 있다.
    directory = [
        {"id": "u-other", "name": "김민수", "email": "minsu.kim@goodmit.co.kr"},
        {"id": "u-noemail", "name": "박서준", "email": ""},
    ]
    hit, quality, _ = m.match_person(directory, "minsu@goodmit.co.kr", "김민수")
    assert hit is None and quality == "not_found"
    # 이메일을 모르는 항목은 이름으로 이어도 된다. 그것이 가진 유일한 단서다.
    hit, quality, _ = m.match_person(directory, "park@goodmit.co.kr", "박서준")
    assert hit is not None and hit["id"] == "u-noemail"
    # 이메일이 같으면 당연히 그 사람이다.
    hit, quality, _ = m.match_person(directory, "minsu.kim@goodmit.co.kr", "김민수")
    assert hit is not None and hit["id"] == "u-other" and quality == "email"


def test_delete_guard_only_blocks_deleting_the_ticket_itself():
    # '담당자 제거해줘'는 티켓의 한 칸을 비우는 평범한 변경이다. 삭제 가드가 가로채
    # '삭제는 지원하지 않는다'는 엉뚱한 안내를 하면 사용자는 할 수 있는 일을 못 하게 된다.
    def guarded(message):
        data, _ = m.process_request({
            "message": message, "requester": {"email": "a@x", "name": "문의진"},
            "projects": [], "tickets": [], "work_schema": {}, "context": {},
        })
        return data["action"] == "UNSUPPORTED" and "삭제는 아직" in data["response_text"]

    assert guarded("이 티켓 삭제해줘")
    assert guarded("티켓 지워줘")
    assert not guarded("티켓 담당자 제거해줘")
    assert not guarded("마감일 지워줘")


def test_retry_after_a_failed_write_works_for_every_kind():
    # 쓰기가 실패하면 봇이 "'재시도'라고 말씀해주세요"라고 안내한다. 그런데 CREATE에는
    # 재시도 처리가 없어서 안내대로 해도 '이미 처리 중'만 돌아오는 교착이 있었다.
    schema = {"properties": {"제목": {"type": "title"}, "진행 상태": {"type": "status"},
                             "마감일": {"type": "date"}, "우선순위": {"type": "select"},
                             "난이도": {"type": "number"}, "프로젝트": {"type": "relation"},
                             "티켓 담당자": {"type": "people"}}}
    ctx = {"pending_action": {"kind": "CREATE", "dispatched_at": "2026-07-16T02:00:00+09:00"},
           "pending_question": "write_in_progress",
           "ticket_draft": {"title": "T", "background": "b", "requirements": [], "acceptance_criteria": []},
           "selected_project": {"id": "p1", "name": "P"}, "status": "계획", "due_date": "2026-07-31",
           "priority": "낮음", "difficulty": 1, "assignee_ids": ["u1"], "original_request": "x"}
    data, _ = m.route_request({
        "message": "재시도", "requester": {"email": "a@x", "name": "문의진"},
        "projects": [], "tickets": [], "work_schema": schema, "context": ctx,
    })
    assert data["action"] == "WRITE_CREATE", data["action"]
    assert data["write_request"]["kind"] == "CREATE"


def test_quarters_are_a_period_people_actually_use():
    from datetime import date

    # 모르는 기간 표현은 조용히 사라져, 사용자가 말한 조건과 무관한 답이 나간다.
    today = date(2026, 7, 16)  # 3분기
    this_q = m.parse_date_range("이번 분기에 끝내야 하는 일", today)
    assert this_q["start"] == "2026-07-01" and this_q["end"] == "2026-09-30"
    assert m.parse_date_range("지난 분기 마감", today)["start"] == "2026-04-01"
    assert m.parse_date_range("다음 분기 마감", today)["end"] == "2026-12-31"
    assert m.parse_date_range("1분기 마감 티켓", today)["start"] == "2026-01-01"
    assert m.parse_date_range("4분기 마감 티켓", today)["end"] == "2026-12-31"


def test_no_project_bucket_can_be_opened():
    # 집계가 '프로젝트 없음 티켓 보여줘'라고 안내해 놓고 정작 그 명령을 실행하지 못했다.
    loose = {**TICKETS[0], "id": "np1", "title": "프로젝트 없는 일", "project_ids": [], "project_names": []}
    data = m.query_tickets("프로젝트 없음 티켓 보여줘", {}, {"email": "a@x", "name": "문의진"},
                           {"id": "u1"}, PROJECTS, [loose] + TICKETS, {})
    assert data["total"] == 1
    assert data["tickets"][0]["id"] == "np1"
    assert "프로젝트 없는 티켓" in data["response_text"]


def test_asking_politely_is_not_asking_for_a_change():
    # '해줘'는 변경동사가 아니라 부탁하는 말이다. 이것을 변경 근거로 삼으면 담당자를 언급한
    # 모든 정중한 요청이 변경 지시가 된다. '담당자 기준으로 정리해줘'가 실제로 그랬다.
    sm = _status_map_from_aliases()
    for message in ["담당자 기준으로 정리해줘", "담당자별로 정리해줘", "담당자 기준으로 묶어줘",
                    "마감 임박한 티켓 알려줘", "우선순위 높은 티켓 보여줘"]:
        assert not m.is_update_intent(message, {}, sm), message
    # 진짜 변경 지시는 그대로 쓰기로 간다.
    for message in ["담당자 문의진으로 바꿔줘", "담당자 추가해줘", "마감일 내일로 미뤄줘",
                    "우선순위 높음으로 변경해줘", "마감일 지워줘", "담당자 빼줘"]:
        assert m.is_update_intent(message, {}, sm), message


# ── 검수 #35: 문장 아무 데나 있는 낱말이 아니라 문장 끝 동사가 의도를 정한다 ──────────

def test_an_unheard_condition_is_not_declared_a_missing_project():
    # [CRITICAL] '프로젝트'라는 낱말이 문장에 있다 ≠ 사용자가 프로젝트를 이름으로 지목했다.
    # '프로젝트 전체에서'는 범위를 말한 것인데 이것을 이름 지목으로 읽어, 조사까지 끌어안은
    # 추측('에서배포실패')을 확신으로 승격시키고 실제로 있는 티켓을 없다고 답했다.
    target = {**TICKETS[0], "id": "dep1", "title": "배포 실패 원인 분석"}
    data = m.query_tickets("프로젝트 전체에서 배포 실패 티켓 보여줘", {}, {"email": "a@x", "name": "문의진"},
                           {"id": "u1"}, PROJECTS, [target] + TICKETS, {})
    assert "찾지 못했습니다" not in data["response_text"], data["response_text"]
    assert "프로젝트를 찾지" not in data["response_text"], "없는 프로젝트 이름을 지어내면 안 된다"
    assert data["total"] > 0, "있는 티켓을 없다고 답했다"
    assert any(t["id"] == "dep1" for t in data["tickets"])
    # 범위 표현은 이름이 아니다. 진짜 이름 지목만 확신이다.
    assert not m.points_at_project_by_name("프로젝트 전체에서 배포 실패 티켓 보여줘", PROJECTS, "에서배포실패")
    assert not m.points_at_project_by_name("프로젝트 전체 보여줘", PROJECTS, "전체")
    assert m.points_at_project_by_name("화성 탐사 프로젝트 티켓 보여줘", PROJECTS, "화성탐사")
    assert m.points_at_project_by_name('"화성 탐사" 티켓 보여줘', PROJECTS, "화성탐사")
    assert m.points_at_project_by_name("포스코DX 티켓 보여줘", PROJECTS, "포스코dx")


def test_an_explicit_change_order_is_not_small_talk():
    # [HIGH] '정도'·'제일' 같은 부사가 문장에 있다는 게 "이건 잡담이다"를 뜻하지 않는다.
    # 쓰기 지시가 자유대화로 새면 Notion엔 아무것도 반영 안 되고 pending_action도 안 남아
    # '재시도'조차 못 한다 — 사용자는 반영된 줄 안다.
    sm = _status_map_from_aliases()
    for msg in ["마감일 다음 주 금요일 정도로 미뤄줘", "난이도 3 정도로 바꿔줘", "제일 급한 티켓 완료로 바꿔줘"]:
        assert m.is_freeform_query(msg), f"자유대화 표지가 켜지는 상황을 재현: {msg}"
        assert m.is_update_intent(msg, {}, sm), msg
        with mock.patch.object(m, "update_ticket", return_value={"action": "WRITE_UPDATE"}) as up, \
             mock.patch.object(m, "claude_query", return_value={"action": "FREEFORM"}):
            data, _ = m.route_request({"message": msg, "requester": {"email": "a@x", "name": "문의진"},
                                       "projects": PROJECTS, "tickets": TICKETS, "work_schema": {}})
        assert up.called, f"명시적 쓰기 지시가 자유대화로 샜다: {msg}"
        assert data["action"] == "WRITE_UPDATE", msg
    # 진짜 자유대화는 그대로 대화다.
    for msg in ["내 티켓 요약해줘", "가장 급한 티켓 뭐야", "프로젝트별 진행률 알려줘"]:
        assert not m.is_update_intent(msg, {}, sm), msg


def test_a_question_about_comments_is_not_an_order_to_write_one():
    # [HIGH] 조회 질문이 댓글 쓰기 흐름으로 납치됐다. 문장 끝 동사가 '보여줘'/'몇 개야'라는
    # 사실을 아무도 안 봤다. create_verb_leads와 같은 원칙으로 본다.
    for msg in ["댓글 남긴 티켓 보여줘", "댓글 달아야 하는 티켓 몇 개야", "댓글 남긴 티켓 목록"]:
        assert not m.is_comment_intent(msg), msg
        assert m.is_query_intent(msg, {}), msg
    # 댓글 쓰기 지시는 그대로 쓰기다 — 본문 안에 조회 낱말이 있어도 끝 동사가 '남겨줘'다.
    for msg in ["댓글 남겨줘", '1번 티켓에 "확인했습니다" 댓글 남겨줘', "댓글 어떻게 달아?",
                '여기에 "메모"라고 댓글 달아줘', '1번 티켓에 "목록 정리해서 공유함" 댓글 남겨줘']:
        assert m.is_comment_intent(msg), msg
    assert not m.is_comment_intent("댓글 기능이 있나요?")
    # 조회로 흘려보내면 query_tickets 안의 '내가 댓글' 안내가 비로소 살아난다.
    data = m.query_tickets("내가 댓글 남긴 티켓 보여줘", {}, {"email": "a@x", "name": "문의진"},
                           {"id": "u1"}, PROJECTS, TICKETS, {})
    assert data["action"] == "NEED_INPUT", data["action"]
    assert "요청자나 참여자" in data["response_text"]


def test_that_ticket_is_not_my_ticket():
    # [HIGH·회귀] 지시관형사 '저'(that)를 1인칭 '저'(I)로 읽어 남의 티켓을 조용히 숨겼다.
    # 같은 파일 _CONTEXT_REF_RE는 '저'를 지시관형사로 등록해 두어, 두 판정이 같은 문장에서
    # 동시에 True가 됐다.
    for msg in ["저 프로젝트 티켓 보여줘", "저 티켓 담당자 누구야", "저 이슈 상태 알려줘"]:
        assert not m.asks_for_own_work(msg), msg
        assert m._CONTEXT_REF_RE.search(m.norm(msg)), f"지시관형사로만 읽혀야 한다: {msg}"
    # 1인칭 '저'는 조사가 붙거나 단독으로 쓰인다.
    for msg in ["저는 티켓 보여줘", "저한테 할당된 티켓 보여줘", "저의 업무 보여줘", "저에게 할당된 작업"]:
        assert m.asks_for_own_work(msg), msg
    # 주석대로 두 어절까지만 꾸미는 말로 본다. 맨명사가 연달아 오면 주인이 바뀐다.
    for msg in ["제 동료 김민수 티켓 보여줘", "제 옆자리 박대리 업무 보여줘", "내 동료가 만든 티켓"]:
        assert not m.asks_for_own_work(msg), msg
    # 기존 1인칭 표현은 하나도 잃지 않는다.
    for msg in ["내 티켓 보여줘", "내가 담당하는 티켓 보여줘", "나한테 할당된 작업",
                "제가 맡은 업무 보여줘", "제가 맡은 급한 업무 보여줘", "내가 해야 할 일 보여줘",
                "내 미완료 작업 몇 건이야?", "완료된 건 빼고 내 티켓 보여줘", "내티켓보여줘"]:
        assert m.asks_for_own_work(msg), msg


def test_that_ticket_scope_keeps_other_peoples_tickets():
    # 본인 것만 걸러낸 목록을 프로젝트 전체인 것처럼 내밀면 사용자는 알아챌 수 없다.
    others = {**TICKETS[0], "id": "o1", "title": "남의 일", "assignees": [{"id": "u9", "name": "박대리"}]}
    ctx = {"last_query": {"kind": "tickets"}, "selected_project": {"id": "p1", "name": "포스코DX"}}
    data = m.query_tickets("저 프로젝트 티켓 보여줘", ctx, {"email": "a@x", "name": "문의진"},
                           {"id": "u1"}, PROJECTS, [others] + TICKETS, {})
    scope = (data["context"].get("last_query") or {}).get("scope")
    assert scope != "PROJECT_MY_TICKETS", scope
    assert any(t["id"] == "o1" for t in data["tickets"]), "남의 티켓이 조용히 사라졌다"


def test_redoing_a_field_is_a_revision_not_a_second_dispatch():
    # [HIGH·회귀] 'X 다시 해줘'는 X를 고쳐달라는 수정 요청이지 재발행 요청이 아니다.
    # 부분일치로 '다시해줘'를 잡아 중복 방지 가드를 우회하고 같은 초안을 두 번 발행했다.
    for msg in ["제목 다시 해줘", "요약 다시 해줘", "배경 다시 써줘", "마감일 다시 정해줘"]:
        assert not m.retry_requested(m.norm(msg)), msg
    for msg in ["재시도", "재시도해줘", "다시 해줘", "다시 해주세요", "다시 등록해줘",
                "다시 반영해줘", "다시 적용해줘"]:
        assert m.retry_requested(m.norm(msg)), msg

    schema = {"properties": {"제목": {"type": "title"}, "진행 상태": {"type": "status"},
                             "마감일": {"type": "date"}, "우선순위": {"type": "select"},
                             "난이도": {"type": "number"}, "프로젝트": {"type": "relation"},
                             "티켓 담당자": {"type": "people"}}}
    ctx = {"pending_action": {"kind": "CREATE", "dispatched_at": "2026-07-16T02:00:00+09:00"},
           "pending_question": "write_in_progress",
           "ticket_draft": {"title": "T", "background": "b", "requirements": [], "acceptance_criteria": []},
           "selected_project": {"id": "p1", "name": "P"}, "status": "계획", "due_date": "2026-07-31",
           "priority": "낮음", "difficulty": 1, "assignee_ids": ["u1"], "original_request": "x"}
    with mock.patch.object(m, "create_ticket", return_value=({"action": "CREATE_PREVIEW"}, 0)) as ct:
        data, _ = m.route_request({
            "message": "제목 다시 해줘", "requester": {"email": "a@x", "name": "문의진"},
            "projects": [], "tickets": [], "work_schema": schema, "context": ctx,
        })
    assert data["action"] != "WRITE_CREATE", "발행 중인 초안을 다시 발행했다 — Notion에 중복 티켓"
    assert ct.called, "'제목 다시 해줘'는 초안 수정으로 가야 한다"


def test_help_examples_come_from_the_workspace_not_from_the_code():
    """도움말 예시에 사람·프로젝트 이름을 박지 않는다.

    예전엔 '용인 프로젝트'와 '민지원'이 코드에 박혀 있었다. 그 프로젝트 이름이 바뀌면
    도움말이 거짓이 되고, 실존하는 동료의 이름이 모든 사용자의 도움말에 나왔다.
    """
    projects = [{"id": "p1", "name": "화성 탐사"}, {"id": "p2", "name": "달 기지"}]
    data, _ = m.route_request({
        "message": "도움말",
        "requester": {"email": "kim@x.co", "name": "김현우"},
        "projects": projects, "tickets": [], "work_schema": {},
    })
    assert data["action"] == "HELP"
    body = data["response_text"]

    # 이 워크스페이스의 실제 이름이 나온다
    assert "화성 탐사" in body, "도움말이 실제 프로젝트를 예시로 써야 한다"
    assert "김현우" in body, "예시는 물어본 본인 이름을 써야 한다 — 남의 이름을 노출하지 않는다"

    # 옛 하드코딩이 되살아나면 여기서 잡힌다
    for banned in ("용인", "민지원", "Jenkins"):
        assert banned not in body, f"'{banned}'이(가) 도움말에 박혀 있다 — 하드코딩 금지"


def test_help_does_not_invent_names_when_the_workspace_is_empty():
    """프로젝트도 사람도 없을 때 그럴듯한 이름을 지어내지 않는다."""
    data, _ = m.route_request({
        "message": "도움말",
        "requester": {},
        "projects": [], "tickets": [], "work_schema": {},
    })
    assert data["action"] == "HELP"
    body = data["response_text"]
    assert "프로젝트 이름" in body and "담당자 이름" in body, "빈 워크스페이스에서는 자리표시자를 쓴다"


def test_change_prompt_does_not_hardcode_a_colleagues_name():
    """변경 안내의 할당 예시도 코드에 박힌 이름을 쓰지 않는다.

    도움말을 고치면서 이 자리를 놓쳤었다 — 같은 하드코딩이 오류 안내 문구에도 있었다.
    """
    schema = {"status": ["계획", "진행", "완료"]}
    ctx = {"selected_ticket": {"id": "t1", "title": "배포", "status": "계획"}}
    tickets = [{"id": "t1", "title": "배포", "status": "계획"}]
    data, _ = m.route_request({
        "message": "이 티켓 바꿔줘",
        "requester": {"email": "park@x.co", "name": "박서준"},
        "projects": [], "tickets": tickets, "work_schema": schema, "context": ctx,
    })
    if data["action"] == "NEED_INPUT" and "할당해줘" in data["response_text"]:
        assert "민지원" not in data["response_text"], "동료 이름이 안내 문구에 박혀 있다"
        assert "박서준" in data["response_text"], "예시는 물어본 본인 이름을 써야 한다"


_PHOTO_SCHEMA = {"properties": {"제목": {"type": "title"}, "진행상태": {"type": "status"},
                 "마감일": {"type": "date"}, "우선순위": {"type": "select"},
                 "난이도": {"type": "select"}, "프로젝트": {"type": "relation"}}}


def _photo_ctx(images):
    return {
        "mode": "CREATE",
        "pending_action": {"kind": "CREATE"},
        "pending_question": "approval",
        "selected_project": {"id": "p1", "name": "화성 탐사"},
        "ticket_draft": {"title": "배포 실패", "background": "b", "requirements": [],
                         "acceptance_criteria": [], "notes": [], "due_date": "2026-08-01"},
        "creator": {"name": "황형섭", "email": "a@goodmit.co.kr"},
        "due_date": "2026-08-01", "priority": "높음", "difficulty": 3,
        "assignee_ids": [], "status": "계획",
        "draft_images": images,
    }


def test_user_is_told_when_draft_photos_expired_before_approval(tmp_path, monkeypatch):
    """사진이 보관 기한으로 사라졌으면 등록할 때 말해준다.

    n8n의 첨부 체인은 실패해도 응답 경로에 합류하지 못한다(마지막 노드에 나가는 연결이
    없고 전부 continueRegularOutput). 그래서 사용자는 사진 없이 만들어진 티켓을 받고도
    그 사실을 어디서도 알 수 없었다. 월요일에 스크린샷으로 초안을 만들고 화요일에
    승인하면 조용히 사진이 빠진다.
    """
    monkeypatch.setattr(m, "IMAGE_DIR", str(tmp_path))
    out = m.handle_confirmation(_photo_ctx(["1730000000-deadbeef.png"]), _PHOTO_SCHEMA, [],
                                CREATE_CURRENT_USER, CREATE_REQUESTER, "cv-1")
    assert out is not None and out["action"] == "WRITE_CREATE", out["action"]
    assert "사라졌" in out["response_text"], (
        "사진이 없어진 것을 말하지 않으면 사용자는 첨부가 빠진 줄 모른다: " + out["response_text"]
    )


def test_no_false_alarm_when_photos_are_still_there(tmp_path, monkeypatch):
    """사진이 멀쩡히 있으면 경고하지 않는다 — 거짓 경고는 신뢰를 깎는다."""
    monkeypatch.setattr(m, "IMAGE_DIR", str(tmp_path))
    conv_dir = tmp_path / m._safe_conv_key("cv-2")
    conv_dir.mkdir(parents=True)
    (conv_dir / "1730000000-cafe.png").write_bytes(b"x")
    out = m.handle_confirmation(_photo_ctx(["1730000000-cafe.png"]), _PHOTO_SCHEMA, [],
                                CREATE_CURRENT_USER, CREATE_REQUESTER, "cv-2")
    assert out is not None and out["action"] == "WRITE_CREATE", out["action"]
    assert "사라졌" not in out["response_text"], "멀쩡한 첨부에 거짓 경고: " + out["response_text"]


def test_no_warning_when_the_draft_had_no_photos(tmp_path, monkeypatch):
    """사진을 안 올린 평범한 티켓에는 아무 말도 덧붙이지 않는다."""
    monkeypatch.setattr(m, "IMAGE_DIR", str(tmp_path))
    out = m.handle_confirmation(_photo_ctx([]), _PHOTO_SCHEMA, [],
                                CREATE_CURRENT_USER, CREATE_REQUESTER, "cv-3")
    assert out is not None and out["action"] == "WRITE_CREATE"
    assert out["response_text"] == "Notion에 티켓을 등록합니다."


def test_reason_clause_does_not_close_the_ticket():
    """'완료했으니 ~ 바꿔줘'는 이유를 말하는 종속절이지 상태 변경 지시가 아니다.

    앵커 없는 '완료했/끝냈' 폴백이 문장 아무 데나 있는 그 말에 걸려, 사용자가 요청하지도
    않은 완료 처리를 승인 없이 Notion에 썼다. 단일 티켓 명시 변경은 미리보기가 없어
    '바로 변경'으로 즉시 발행되므로, 사용자는 막을 기회조차 없었다.
    """
    status_map = {"계획": "계획", "진행": "진행", "완료": "완료"}
    # 이유를 말하는 종속절 — 요청은 마감일/우선순위/담당자다
    for msg in [
        "리뷰 완료했으니 이 티켓 마감일 내일로 바꿔줘",
        "설계 다 끝냈으니 우선순위 높음으로 바꿔줘",
        "앞 단계 완료했고 담당자 나로 바꿔줘",
    ]:
        got = m.detect_target_status(msg, status_map)
        assert got == "", f"{msg!r} → 상태를 {got!r}로 바꾸려 한다. 사용자는 그걸 요청하지 않았다"

    # 진짜 완료 지시는 계속 동작해야 한다 — 과잉 수정으로 기능을 죽이지 않는다
    for msg, want in [
        ("이 티켓 완료로 바꿔줘", "완료"),
        ("완료 처리해줘", "완료"),
        ("진행으로 변경해줘", "진행"),
    ]:
        got = m.detect_target_status(msg, status_map)
        assert got == want, f"{msg!r} → {got!r} (기대: {want!r}) — 진짜 지시를 놓쳤다"


# --- 3.32.0 검수 확정 결함 회귀 ------------------------------------------------
# 네 결함 모두 근본 원인이 같다: 문장 아무 데나 있는 낱말을 매칭했다.
# 한국어는 문장 끝 동사가 의도를 정하고, 낱말은 앞뒤에 붙은 말이 자리를 정한다.


def test_status_alias_glued_to_another_word_is_a_topic_not_a_status():
    """'결제 문제 티켓' — '문제'는 이슈의 별칭이지만 여기선 주제이지 상태가 아니다.

    별칭 바로 뒤에 일 명사가 온다는 이유로 상태 조건으로 승격시키면, 결제 관련
    티켓을 찾는 사용자가 '상태=이슈'로 좁혀진 목록을 받는다. 0건이 나와도 오류
    표시가 없어 사용자는 그런 티켓이 없다고 믿는다.
    """
    # 앞에 다른 낱말이 붙어 복합어를 이루면 주제다
    assert _statuses("결제 문제 티켓 보여줘") == []
    assert _statuses("배포 이슈 티켓 보여줘") == []
    assert _statuses("결제 문제 작업 보여줘") == []
    assert not m.mentions_status_condition("결제 문제 티켓 보여줘")

    # 맨몸 별칭이라도 그 자체로 조건인 자리(문장 첫머리)면 상태다 — 과잉 수정 방지
    assert _statuses("이슈 티켓 보여줘") == ["이슈"]
    # 꼬리(진행'중인', 완료'된')가 붙으면 어디에 있든 상태다
    assert _statuses("그 프로젝트에서 진행중인 티켓") == ["진행"]
    assert _statuses("나한테 할당된 완료된 티켓") == ["완료"]
    assert _statuses("검증이랑 이슈 티켓") == ["검증", "이슈"]


def test_a_self_contained_question_does_not_inherit_the_previous_project():
    """'완료된 티켓 보여줘'는 스스로 조건을 다 갖춘 새 질문이다.

    직전 프로젝트 필터를 물려받으면 사용자는 전체를 물었는데 이전 프로젝트 것만
    받는다. 조용히 좁힌 목록을 전체인 양 주는 것이 이 제품의 반복 결함이다.
    """
    ctx = {**_list_query_context(scope="PROJECT_TICKETS", project_id="p1", project_name="포스코DX"),
           "selected_project": DONE_PROJECTS[0]}
    assert not m.is_query_followup("완료된 티켓 보여줘", ctx)

    tickets = DONE_TICKETS + [_t("e", "완료", "2026-07-15", pid="p2", pname="NH손해보험",
                                 who="남기훈", uid="u2")]
    data = _query("완료된 티켓 보여줘", ctx, tickets=tickets)
    assert data["action"] == "TICKET_LIST", data["action"]
    assert data["context"]["last_query"]["project_id"] == "", data["response_text"]
    assert sorted(t["id"] for t in data["tickets"]) == ["a", "b", "e"], data["response_text"]

    # 스스로 대상을 대지 않은 조각은 여전히 직전 조건을 물려받는다 — 과잉 수정 방지
    assert m.is_query_followup("완료만", ctx)
    assert m.is_query_followup("진행중인 것만", ctx)
    assert m.is_query_followup("그 프로젝트 티켓 보여줘", ctx)

    # 그리고 상속했으면 상속했다고 응답이 말해야 한다. 좁힌 목록을 '전체'인 양 주면
    # 사용자는 전사 결과를 본 줄 안다 — 제목이 물려받은 프로젝트를 이름으로 밝힌다.
    narrowed = _query("완료만", ctx, tickets=tickets)
    assert sorted(t["id"] for t in narrowed["tickets"]) == ["a", "b"], narrowed["response_text"]
    assert "포스코DX" in narrowed["response_text"], narrowed["response_text"]
    assert "전체 티켓" not in narrowed["response_text"], narrowed["response_text"]


def test_a_test_word_anywhere_never_swaps_the_users_request_for_a_canned_ticket():
    """'테스트'와 '알아서'가 문장 어디에 있다고 사용자 요청을 버리면 안 된다.

    '테스트 환경 배포 자동화'는 테스트 환경에 배포하는 실제 업무다. 이걸 코드에
    박힌 '[테스트] … 티켓 생성 기능 검증'으로 바꿔치기하면 사용자가 원하지 않은
    것을 Notion에 쓰는 것이다.
    """
    draft = {"title": "테스트 환경 배포 자동화", "type": "작업",
             "background": "스테이징 배포를 자동화한다.",
             "requirements": ["배포 스크립트를 작성한다."],
             "acceptance_criteria": ["스테이징에 자동 배포된다."], "notes": []}
    fields = {"priority": "", "difficulty": 0, "due_date": "",
              "assignee_names": [], "unassigned": True}
    with mock.patch.object(m.subprocess, "run",
                           return_value=_draft_cli(ready=True, draft=draft, fields=fields)) as run:
        data, _ = m.create_ticket(
            "포스코DX에 테스트 환경 배포 자동화 티켓 만들어줘. 마감 2026-08-01, 난이도 3, 미할당. 우선순위는 알아서 정해줘",
            {}, CREATE_REQUESTER, CREATE_CURRENT_USER, [], CREATE_PROJECTS, {})
    assert data["action"] == "CREATE_PREVIEW", data["response_text"]
    assert run.called, "사용자 요청이 초안 작성에 전달되지 않았다 — 캔 티켓으로 바꿔치기됐다"
    assert "테스트 환경 배포 자동화" in data["response_text"], data["response_text"]
    assert "티켓 생성 기능 검증" not in data["response_text"], data["response_text"]


def test_even_an_explicit_test_ticket_request_is_drafted_from_what_was_asked():
    # 캔 경로를 지웠으므로 '테스트용 티켓 아무렇게나'도 초안 작성을 거친다.
    # 사용자 요청을 버리는 경로는 남기지 않는다.
    draft = {"title": "티켓 생성 점검용 테스트 티켓", "type": "테스트", "background": "b",
             "requirements": ["r"], "acceptance_criteria": ["a"], "notes": []}
    fields = {"priority": "낮음", "difficulty": 1, "due_date": "2026-08-01",
              "assignee_names": [], "unassigned": True}
    with mock.patch.object(m.subprocess, "run",
                           return_value=_draft_cli(ready=True, draft=draft, fields=fields)) as run:
        data, _ = m.create_ticket(
            "포스코DX에 테스트용 티켓 만들어줘 아무렇게나. 마감 2026-08-01, 우선순위 낮음, 난이도 1, 미할당",
            {}, CREATE_REQUESTER, CREATE_CURRENT_USER, [], CREATE_PROJECTS, {})
    assert data["action"] == "CREATE_PREVIEW", data["response_text"]
    assert run.called
    assert not hasattr(m, "simple_ticket_draft_for_test"), "캔 티켓 경로가 남아 있다"


def test_a_name_we_could_not_match_is_dropped_out_loud_not_in_silence():
    """사용자가 댄 이름을 못 찾으면 조건을 빼고 목록을 낼 수는 있다. 다만 말해야 한다.

    조용히 버리면 사용자는 무관한 전체 목록을 자기가 물은 것의 답인 줄 안다.
    이전 라운드 수정이 "못 알아들은 조건을 '없다'고 단정하지 말라"에서
    반대편으로 넘어가 "알아들은 조건도 조용히 버린다"가 된 회귀다.
    """
    data = m.query_tickets("화성 탐사 티켓 보여줘", {}, {"email": "a@x", "name": "문의진"},
                           {"id": "u1"}, PROJECTS, TICKETS, {})
    # 있는 걸 없다고 하지 않는다 — 목록은 낸다
    assert data["total"] > 0, data["response_text"]
    # 그러나 그 이름으로 못 찾아 조건을 뺐다는 사실을 말한다
    assert "화성 탐사" in data["response_text"], data["response_text"]
    assert "빼고" in data["response_text"], data["response_text"]


# =============================================================================
# 낱말이 문장의 어느 자리에 있느냐가 의도를 정한다 (3.36.0)
#
# 아래 결함들의 근본 원인은 하나다: 문장 아무 데나 있는 낱말을 매칭했다.
# 한국어는 문장 끝 동사가 의도를 정하고, 낱말은 앞뒤에 붙은 말이 자리를 정한다.
# =============================================================================


def test_a_finished_clause_inside_a_question_stays_a_question():
    """'완료했던 티켓 목록 보여줘'는 조회다 — 이 문장 어디에도 지시가 없다.

    조회 낱말('목록', '보여')이 있으면 조회로 빠져나가는 문이 있는데, 그 문에
    '완료했/끝냈'이라는 앵커 없는 예외가 뚫려 있었다. 그래서 지난 일을 묻는 문장이
    쓰기 흐름(update_ticket)으로 끌려가, 사용자가 묻기만 한 자리에서 티켓을 고르라고
    되묻거나 상태를 바꿀 자리에 선다.

    detect_target_status는 같은 폴백을 _STATUS_ONLY_DONE_RE(문장 끝 동사)로 이미 고쳤다.
    같은 원칙을 여기에도 쓴다 — 새로 발명하지 않는다.
    """
    sm = _status_map_from_aliases()
    for msg in [
        "완료했던 티켓 목록 보여줘",
        "지난주에 완료했던 작업 현황 알려줘",
        "내가 끝냈던 티켓 몇건이야",
        "내가 끝냈던 작업 상세 보여줘",
    ]:
        assert not m.is_update_intent(msg, {}, sm), f"조회 문장이 쓰기로 갔다: {msg!r}"

    # 과잉 수정 방지 — 문장이 실제로 상태를 지시하면 여전히 쓰기다.
    assert m.is_update_intent("이 티켓 완료했어", {}, sm)
    assert m.is_update_intent("완료 처리해줘", {}, sm)
    assert m.is_update_intent("리뷰 완료했으니 마감일 내일로 바꿔줘", {}, sm)


def test_asking_whether_a_ticket_exists_does_not_start_a_creation():
    """'~티켓 있어?'는 조회다. 그런데 조회 동사 목록에 '있어/있나/있는지'가 없었다.

    그래서 주제어에 '추가/등록/생성'이 들어간 질문("회원 추가 기능 티켓 있어?")이
    조회 동사를 하나도 못 찾고 생성 흐름을 시작해, 사용자가 요청하지도 않은 티켓의
    프로젝트를 되물었다. _QUERY_VERB_RE는 이미 이 세 낱말을 조회 동사로 등록해 뒀다 —
    같은 낱말이 판정마다 다른 뜻이면 안 된다.
    """
    for msg in [
        "회원 추가 기능 티켓 있어?",
        "결제 등록 관련 티켓 있나?",
        "사용자 생성 API 작업 있는지 확인해줘",
        "티켓 만들 수 있어?",
    ]:
        assert not m.is_create_intent(msg, {}), f"조회가 생성 흐름을 시작했다: {msg!r}"

    # 과잉 수정 방지 — 뒤에 오는 생성 동사가 이기는 것은 그대로다.
    assert m.is_create_intent("로그인 버그 티켓 만들어줘", {})
    assert m.is_create_intent("그런 티켓 있는지 보고 없으면 새로 만들어줘", {})


def test_a_topic_that_ends_in_a_status_name_is_not_a_status_filter():
    """'배포 계획 티켓' — '계획'은 상태 이름이지만 여기선 주제('배포 계획')의 뒷말이다.

    복합어 보호가 이슈/문제/검증/검토 4개뿐이라 '계획·종료·대기'는 무조건 상태로 읽혔다.
    그 결과 배포 계획 티켓을 찾는 사용자가 '상태=계획'으로 좁혀진 무관한 목록을 받는다.
    0건이 나와도 조건이 걸렸다는 표시가 없어 사용자는 그런 티켓이 없다고 믿는다.
    """
    assert _statuses("배포 계획 티켓 보여줘") == []
    assert _statuses("서비스 종료 작업 보여줘") == []
    assert _statuses("승인 대기 티켓 보여줘") == []

    # 과잉 수정 방지 — 조건을 말하는 자리에서는 여전히 상태다.
    assert _statuses("계획 티켓 보여줘") == ["계획"]
    assert _statuses("계획된 작업 보여줘") == ["계획"]
    assert _statuses("상태가 대기인 티켓") == ["계획"]
    assert _statuses("종료된 티켓 보여줘") == ["완료"]
    assert _statuses("계획과 진행 상태 티켓") == ["계획", "진행"]


def test_a_noun_ending_that_looks_like_a_particle_is_not_a_word_boundary():
    """'메시지 문제'의 '지'는 조사가 아니라 '메시지'의 끝 음절이다.

    맨몸 별칭 앞이 조사면 새 어절, 낱말이면 복합어로 가르는데, 그 조사 목록에
    지/의/이/들처럼 명사 끝에 흔한 음절이 들어 있었다. 그래서 '메시지 문제 티켓',
    '이미지 이슈 티켓'이 상태=이슈 필터가 됐다 — 결제 문제 티켓을 막으려고 만든
    보호가 정작 같은 모양의 문장을 그대로 통과시킨 것이다.
    """
    assert _statuses("메시지 문제 티켓 보여줘") == []
    assert _statuses("이미지 이슈 티켓 보여줘") == []
    assert _statuses("페이지 검토 작업 보여줘") == []
    assert _statuses("회의 문제 티켓 보여줘") == []

    # 과잉 수정 방지 — 진짜 경계는 그대로 경계다.
    assert _statuses("이슈 티켓 보여줘") == ["이슈"]
    assert _statuses("검증이랑 이슈 티켓") == ["검증", "이슈"]
    assert _statuses("그 프로젝트에서 진행중인 티켓") == ["진행"]
    assert _statuses("나한테 할당된 완료된 티켓") == ["완료"]
    assert _statuses("상태가 이슈인 티켓") == ["이슈"]


def test_my_projects_is_still_mine_when_a_word_comes_first():
    """'그럼 내 프로젝트 보여줘' — 앞에 낱말이 하나 붙었다고 남의 것이 되지 않는다.

    낱말 경계를 [^0-9a-z가-힣]로 뒀는데 이 판정은 norm() 뒤(공백·기호가 전부 사라진
    문자열)에서 돈다. 그래서 그 경계는 문자열 맨 앞에서만 성립했고, 1인칭 앞에 아무
    낱말이나 오면 '내 프로젝트'가 조용히 '전체 프로젝트'가 됐다.
    """
    for msg in ["내 프로젝트 보여줘", "그럼 내 프로젝트 보여줘",
                "자 이제 우리 프로젝트 현황 알려줘", "혹시 내가 담당하는 프로젝트 뭐야",
                "오늘 제 프로젝트 목록 보여줘"]:
        assert m.mentions_own(msg), f"내 프로젝트를 남의 것으로 읽었다: {msg!r}"

    # 과잉 수정 방지 — 붙어 있는 '내'는 1인칭이 아니다.
    for msg in ["사내 프로젝트 목록", "프로젝트 목록 보여줘", "국내 프로젝트 현황",
                "결제 프로젝트 티켓 보여줘"]:
        assert not m.mentions_own(msg), f"남의 것을 내 것으로 읽었다: {msg!r}"

    # 이미 정규화된 문자열로 물어보던 호출자도 그대로 동작해야 한다.
    assert m.mentions_own(m.norm("내 프로젝트 보여줘"))
    assert not m.mentions_own(m.norm("사내 프로젝트 목록"))


# --- 초안에 붙는 사진은 이 초안이 본 사진이어야 한다 -------------------------

def _image_note(message_id, files):
    return {"files": "screen.png", "stored_files": files, "message_id": message_id,
            "analyzed_at": "2026-07-16T09:00:00+09:00", "summary": "로그인 화면 오류",
            "ocr_text": "", "notable": [], "suggested_title": ""}


_CREATE_MSG = "포스코DX에 로그인 버그 수정 티켓 만들어줘. 마감 2026-08-01, 우선순위 높음, 난이도 3, 미할당"
_READY_FIELDS = {"priority": "높음", "difficulty": 3, "due_date": "2026-08-01",
                 "assignee_names": [], "unassigned": True}


def _create_turn(message, context, message_id, ready=True, questions=None):
    """n8n이 실제로 부르는 자리(route_request)로 한 턴을 돌린다."""
    body = {
        "message": message, "requester": CREATE_REQUESTER, "context": context,
        "projects": CREATE_PROJECTS, "tickets": [], "work_schema": {},
        "conversation_id": "cv-img", "message_id": message_id,
    }
    with mock.patch.object(m.subprocess, "run",
                           return_value=_draft_cli(ready=ready, fields=_READY_FIELDS,
                                                   questions=questions)):
        data, _ = m.route_request(body)
    return data


def test_a_screenshot_from_an_earlier_topic_does_not_ride_into_a_new_ticket():
    """월요일에 다른 이야기를 하며 올린 스크린샷이 수요일 티켓에 붙으면 안 된다.

    초안은 image_notes를 뒤에서부터 훑어 사진이 있는 노트를 무조건 집었다 — 그 노트가
    몇 턴 전, 전혀 다른 화제에서 온 것이어도 상관하지 않았다. 첨부는 사용자가 승인한
    뒤 조용히 실행되므로, 무관한 사진이 붙은 것을 사용자는 Notion에서야 본다.
    """
    stale = {"image_notes": [_image_note("m-old", ["1730000000-old.png"])]}
    data = _create_turn(_CREATE_MSG, stale, "m-now")
    assert data["action"] == "CREATE_PREVIEW", data["response_text"]
    assert data["context"]["draft_images"] == [], (
        "지난 턴의 사진이 새 초안에 붙었다: " + repr(data["context"]["draft_images"])
    )


def test_the_screenshot_this_turn_brought_is_the_one_the_draft_uses():
    # 과잉 수정 방지 — 이번 메시지가 가져온 사진은 반드시 붙는다.
    fresh = {"image_notes": [_image_note("m-old", ["1730000000-old.png"]),
                             _image_note("m-now", ["1730000900-new.png"])]}
    data = _create_turn("이 화면 " + _CREATE_MSG, fresh, "m-now")
    assert data["action"] == "CREATE_PREVIEW", data["response_text"]
    assert data["context"]["draft_images"] == ["1730000900-new.png"]


def test_a_draft_keeps_its_photos_through_the_question_turns():
    """과잉 수정 방지 — 초안이 되묻고 사용자가 답하는 사이에 사진이 죽으면 안 된다.

    승인 턴('등록해줘')에는 사진이 없다는 것이 이 설계의 전제다. 초안이 집어 둔 사진은
    그 초안이 소진될 때까지 따라와야 한다.
    """
    # 되묻는 턴: 첫 진입에서 이 초안이 집은 사진이 NEED_INPUT 컨텍스트에 남아야 한다.
    # 마감일을 비워(서사대로 '마감일을 알려주세요') 진짜 질문 턴이 되게 한다 — 필수값이 다
    # 차 있으면 게이트 방어가 미리보기로 승격하기 때문(#11).
    q = [{"question": "마감일을 알려주세요.", "reason": "필수값", "options": []}]
    turn1_fields = {**_READY_FIELDS, "due_date": ""}
    with mock.patch.object(m.subprocess, "run",
                           return_value=_draft_cli(ready=False, fields=turn1_fields, questions=q)):
        turn1, _ = m.create_ticket(
            "이 화면 오류로 포스코DX에 티켓 만들어줘",
            {"image_notes": [_image_note("m-1", ["1730000000-shot.png"])]},
            CREATE_REQUESTER, CREATE_CURRENT_USER, [], CREATE_PROJECTS, {}, "m-1")
    assert turn1["action"] == "NEED_INPUT", turn1["response_text"]
    assert turn1["context"].get("draft_images") == ["1730000000-shot.png"], (
        "되묻는 턴에서 이미 사진을 잃었다: " + repr(turn1["context"].get("draft_images"))
    )

    # 답변 턴: 사진 없는(승인 직전) 후속 메시지가 와도 초안의 사진은 살아 있어야 한다.
    with mock.patch.object(m.subprocess, "run",
                           return_value=_draft_cli(ready=True, fields=_READY_FIELDS)):
        turn2, _ = m.create_ticket(
            "마감 2026-08-01, 우선순위 높음, 난이도 3, 미할당",
            turn1["context"], CREATE_REQUESTER, CREATE_CURRENT_USER, [], CREATE_PROJECTS, {}, "m-2")
    assert turn2["action"] == "CREATE_PREVIEW", turn2["response_text"]
    assert turn2["context"]["draft_images"] == ["1730000000-shot.png"], (
        "답변 턴에서 초안의 사진이 사라졌다: " + repr(turn2["context"]["draft_images"])
    )


def test_a_photo_the_user_points_at_is_still_attached():
    # 과잉 수정 방지 — 앞 턴에 보여준 사진을 사용자가 지목하면 그 사진이 이 초안의 화면이다.
    prev = {"image_notes": [_image_note("m-old", ["1730000000-shot.png"])]}
    data = _create_turn("이 스크린샷으로 " + _CREATE_MSG, prev, "m-now")
    assert data["action"] == "CREATE_PREVIEW", data["response_text"]
    assert data["context"]["draft_images"] == ["1730000000-shot.png"]


# --- 저장 실패는 저장 실패라고 말해야 한다 ----------------------------------

def _post(path, payload):
    """러너를 실제로 띄워 한 요청만 받는다 — n8n이 보는 그 층에서 확인한다."""
    import http.client
    import threading as _threading
    from http.server import HTTPServer

    srv = HTTPServer(("127.0.0.1", 0), m.Handler)
    t = _threading.Thread(target=srv.handle_request, daemon=True)
    t.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=10)
        conn.request("POST", path, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                     {"Authorization": f"Bearer {m.TOKEN}", "Content-Type": "application/json"})
        res = conn.getresponse()
        out = (res.status, json.loads(res.read().decode("utf-8")))
        conn.close()
        return out
    finally:
        t.join(timeout=5)
        srv.server_close()


_SYNC_BODY = {"requester": {"email": "a@goodmit.co.kr", "name": "황형섭"},
              "conversation_id": "cv-sync", "context": {"mode": "CREATE"}}


def test_a_failed_state_save_is_not_reported_as_ok(monkeypatch):
    """저장에 실패하면 실패라고 말해야 한다.

    n8n의 '동기화 후 응답'은 이 응답을 보고 사용자에게 '이어지는 대화가 이 변경을 모를
    수 있다'고 알린다. 그런데 러너는 저장이 터져도 200 ok:true를 돌려줬다 — 그래서 그
    경고는 러너가 아예 안 뜰 때(HTTP 오류) 말고는 절대 뜨지 않았다. 저장이 조용히
    실패하면 사용자는 승인 대기 중인 초안이 사라진 이유를 알 수 없다.
    """
    def boom(*a, **kw):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(m, "state_db", boom)
    status, payload = _post("/v1/assistant/context/sync", _SYNC_BODY)
    assert payload.get("ok") is False, f"저장 실패에 ok:true를 돌려줬다: {payload}"
    assert payload.get("error"), f"실패 이유가 없다: {payload}"


def test_a_successful_state_save_still_reports_ok(tmp_path, monkeypatch):
    # 과잉 수정 방지 — 성공은 성공이고, 리비전은 올라간다.
    monkeypatch.setattr(m, "STATE_DB_PATH", tmp_path / "state.sqlite3")
    status, payload = _post("/v1/assistant/context/sync", _SYNC_BODY)
    assert status == 200 and payload.get("ok") is True, payload
    assert payload.get("context_revision") == 1, payload


# ============================================================================
# round16 회귀 검수 확정 결함 — 승인/피벗 경계 fail-safe 재설계(러너 3.53.0)
# 원칙: 잘못된 승인/피벗은 낡은 pending을 조용히 확정·유실시키는 HIGH 오쓰기다.
# 애매하면 '쓰지 않고 답하거나 되묻는' 쪽으로 흐르게 한다. 아래는 각 확정 결함을 못 박는다.
# ============================================================================

def _r16_upctx(changes=None, status="진행", prio="중간"):
    tk1 = _raw_ticket("tk1", "결제 오류 수정", status=status, prio=prio)
    return tk1, {"pending_action": {"kind": "UPDATE", "ticket_id": "tk1", "ticket_title": "결제 오류 수정",
                                     "changes": changes or {"status": "완료"}, "needs_confirmation": True, "direct": False},
                 "pending_question": "approval", "selected_ticket": m.normalize_ticket(tk1, {}),
                 "last_results": ["tk1"], "last_result_start": 1}


def _r16_route(msg, tk, ctx, tickets=None):
    b = {"message": msg, "requester": CREATE_REQUESTER, "projects": [], "tickets": tickets or [tk],
         "work_schema": _RT_SCHEMA, "context": ctx}
    with mock.patch.object(m, "llm_extract_update_changes", return_value=({}, {})), \
         mock.patch.object(m, "claude_query", side_effect=lambda *a, **k: {"action": "QUERY", "response_text": "…", "context": a[1] if len(a) > 1 else {}}), \
         mock.patch.object(m, "answer_query", side_effect=lambda *a, **k: {"action": "TICKET_LIST", "response_text": "…", "context": a[1] if len(a) > 1 else {}}):
        return m.route_request(b)


def test_r16_f0_strong_yes_prefix_no_false_write():
    # F0(HIGH 회귀): '응답/응급/응모/웅진/그래서/그래도/좋아질/맞아도'로 시작하는 무관한 문장이
    # strong_yes 접두 매칭으로 승인 오인돼 낡은 pending을 확정했다. 첫 낱말 정확일치로 좁힌다.
    tk, ctx = _r16_upctx(changes={"status": "완료"})
    for msg in ["응답 속도 개선 티켓 등록해줘", "응급 대응이 필요해", "응모 페이지 변경 사항 정리",
                "그래서 진행 상황이 궁금해", "그래도 변경은 하지 말아줘", "좋아질 때까지 기다려줘",
                "맞아도 지금은 미뤄줘", "웅진 프로젝트 얘기였어"]:
        d, _ = _r16_route(msg, tk, dict(ctx))
        assert d["action"] != "WRITE_UPDATE", f"{msg}: 승인 오인 쓰기 {d['action']}"
        assert "write_request" not in d, msg


def test_r16_f1_completion_words_not_approval():
    # F1(HIGH 회귀): action_words '완료' 추가로 완료 질문·보류문이 승인 판정돼 낡은 pending 확정.
    tk, ctx = _r16_upctx(changes={"status": "완료"})
    for msg in ["네 완료 조건이 뭐였지", "응 완료됐는지 확인해줘", "응 아직 완료하지마"]:
        d, _ = _r16_route(msg, tk, dict(ctx))
        assert d["action"] != "WRITE_UPDATE", f"{msg}: {d['action']}"
        assert "write_request" not in d, msg


def test_r16_f2_f4_question_and_query_keep_pending_no_write():
    # F2·F4(HIGH 회귀): 값 토큰이 든 조회('완료로 변경된 티켓 보여줘')·확인 질문('…맞아?')이
    # carries_change 단독 피벗으로 pending 유실 또는 확인 없는 direct write. 물음은 답만 한다.
    tk, ctx = _r16_upctx(changes={"status": "완료"})
    for msg in ["완료로 변경된 티켓 보여줘", "우선순위 높음인 티켓 몇 개야?", "1번 완료로 변경된 거 맞아?"]:
        d, _ = _r16_route(msg, tk, dict(ctx))
        assert d["action"] != "WRITE_UPDATE", f"{msg}: {d['action']}"
        assert "write_request" not in d, msg
        assert (d["context"].get("pending_action") or {}).get("kind") == "UPDATE", f"{msg}: pending 유실"


def test_r16_f3_f11_value_redefinition_writes_new_value_not_stale():
    # F3·F11(HIGH): 미리보기 값을 재정의하는 답('응 높음으로 진행해줘')이 carries 단독 피벗으로
    # 대상 재특정 실패→pending 유실 또는 낡은 값 확정. selected_ticket으로 그 티켓에 새 값을 쓴다.
    tk, ctx = _r16_upctx(changes={"priority": "중간"}, prio="중간")
    d, _ = _r16_route("응 높음으로 진행해줘", tk, dict(ctx))
    assert d["action"] == "WRITE_UPDATE", d["action"]
    prio = d["write_request"]["body"]["properties"].get("우선순위", {}).get("select", {}).get("name")
    assert prio == "높음", f"낡은 값이 쓰였거나 유실: {prio}"


def test_r16_f3_echo_value_confirms():
    # F3: 미리보기 값을 되읊는 승인('응 완료로 진행해줘' ← status=완료)은 그 값으로 확정한다.
    tk, ctx = _r16_upctx(changes={"status": "완료"}, status="진행")
    d, _ = _r16_route("응 완료로 진행해줘", tk, dict(ctx))
    assert d["action"] == "WRITE_UPDATE", d["action"]
    st = d["write_request"]["body"]["properties"].get("진행상태", {}).get("status", {}).get("name")
    assert st == "완료", st


def test_r16_f6_negation_is_not_approval():
    # F6(HIGH 기존): '응 아니다 변경하지마'가 승인 동사 부분일치로 승인 오인. 부정이 섞이면 승인 아님.
    tk, ctx = _r16_upctx(changes={"status": "완료"})
    for msg in ["응 아니다 변경하지마", "네 등록하지 말아줘", "응 그건 말고 처리하지마"]:
        d, _ = _r16_route(msg, tk, dict(ctx))
        assert d["action"] != "WRITE_UPDATE", f"{msg}: {d['action']}"
        assert "write_request" not in d, msg


def test_r16_f7_different_target_no_write_to_old():
    # F7(HIGH 기존): '응 그거 말고 2번을 변경해줘'가 값이 없어 피벗을 놓치고 낡은 pending을 원래
    # 티켓(tk1)에 그대로 썼다. 배제한 티켓에 쓰지 않는다.
    tk1 = _raw_ticket("tk1", "결제 오류 수정", status="진행")
    tk2 = _raw_ticket("tk2", "포털 배포", status="진행")
    ctx = {"pending_action": {"kind": "UPDATE", "ticket_id": "tk1", "ticket_title": "결제 오류 수정",
                              "changes": {"status": "완료"}, "needs_confirmation": True, "direct": False},
           "pending_question": "approval", "selected_ticket": m.normalize_ticket(tk1, {}),
           "last_results": ["tk1", "tk2"], "last_result_start": 1}
    d, _ = _r16_route("응 그거 말고 2번을 변경해줘", tk1, ctx, tickets=[tk1, tk2])
    wrote_tk1 = d.get("action") == "WRITE_UPDATE" and d.get("write_request", {}).get("page_id") == "tk1"
    assert not wrote_tk1, f"배제한 tk1에 씀: {d.get('action')}"


def test_r16_f8_ticket_selection_read_escape_no_write():
    # F8(HIGH 기존): ticket_selection 되묻기 중 '그럼 2번 티켓 상세 알려줘'(조회)가 원본 변경과
    # 병합돼 그 티켓에 직접 쓰였다. 조회로 이탈하고 대기 변경은 버린다.
    s1 = _raw_ticket("s1", "A작업", status="계획")
    s2 = _raw_ticket("s2", "B작업", status="계획")
    ctx = {"pending_question": "ticket_selection", "pending_original_message": "계획 티켓 우선순위 높음으로 바꿔줘",
           "last_results": ["s1", "s2"], "last_result_start": 1}
    d, _ = _r16_route("그럼 2번 티켓 상세 알려줘", s1, ctx, tickets=[s1, s2])
    assert d["action"] != "WRITE_UPDATE", d["action"]
    assert "write_request" not in d


def test_r16_f5_comment_pending_value_redefinition_not_commented():
    # F5(HIGH 회귀): COMMENT 확인 대기 중 값 실은 재정의('네 완료로 바꿔줘')가 댓글로 확정되고
    # 변경 지시는 유실. 값 재정의는 댓글 승인이 아니라 상태 변경으로 피벗한다.
    other = _raw_ticket("c1", "결제 오류", people=[_RT_U2])
    ctx = {"pending_action": {"kind": "COMMENT", "direct": False, "ticket_id": "c1",
                              "ticket_title": "결제 오류", "comment": "확인 부탁드립니다"},
           "pending_question": "approval", "last_results": ["c1"], "last_result_start": 1}
    d, _ = _r16_route("네 완료로 바꿔줘", other, ctx, tickets=[other])
    assert d["action"] != "WRITE_COMMENT", f"댓글이 잘못 발행됨: {d['action']}"


def test_r16_f9_comment_body_correction_then_approve_writes_new_body():
    # F9(HIGH 기존): COMMENT_PREVIEW 대기 중 본문 정정('"…"라고 댓글 남겨줘')이 대화로 새고,
    # 이어진 승인이 옛 본문을 발행. 정정이 미리보기 본문을 갱신해야 한다.
    other = [_raw_ticket("c1", "결제 오류", people=[_RT_U2])]
    b1 = {"message": '1번 티켓에 "확인 부탁"이라고 댓글 남겨줘', "requester": CREATE_REQUESTER,
          "projects": [], "tickets": other, "work_schema": _RT_SCHEMA,
          "context": {"last_results": ["c1"], "last_result_start": 1}}
    d1, _ = m.route_request(b1)
    assert d1["action"] == "COMMENT_PREVIEW", d1["action"]
    d2, _ = m.route_request({**b1, "message": '"배포 연기 안내"라고 댓글 남겨줘', "context": d1["context"]})
    assert d2["action"] == "COMMENT_PREVIEW", d2["action"]
    d3, _ = m.route_request({**b1, "message": "댓글 남겨줘", "context": d2["context"]})
    assert d3["action"] == "WRITE_COMMENT", d3["action"]
    body = json.dumps(d3["write_request"]["body"], ensure_ascii=False)
    assert "배포 연기 안내" in body and "확인 부탁" not in body, f"옛 본문 발행: {body}"


def test_r16_f10_okay_approval_confirms():
    # F10(HIGH 기존): '오케이 반영해줘'가 update 피벗으로 유실·막다른 되물음. yes 낱말로 확정한다.
    tk, ctx = _r16_upctx(changes={"status": "완료"}, status="진행")
    d, _ = _r16_route("오케이 반영해줘", tk, dict(ctx))
    assert d["action"] == "WRITE_UPDATE", d["action"]


def test_r16_f16_create_request_during_update_pending_goes_create():
    # F16(MED 기존): UPDATE 대기 중 새 티켓 생성 요청이 검색어 오인 조회 목록으로 응답. 생성으로.
    tk, ctx = _r16_upctx(changes={"status": "완료"})
    b = {"message": "결제 알림 기능 티켓 새로 만들어줘", "requester": CREATE_REQUESTER, "projects": [],
         "tickets": [tk], "work_schema": _RT_SCHEMA, "context": dict(ctx)}
    with mock.patch.object(m.subprocess, "run", return_value=_draft_cli(ready=False, fields={}, questions=["프로젝트?"])):
        d, _ = m.route_request(b)
    assert d["action"] != "TICKET_LIST", d["action"]


def test_r16_f13_query_during_create_preview_answers_not_redraft():
    # F13(MED 기존): CREATE 미리보기 중 값 토큰이 든 조회('진행으로 되어 있는 티켓 보여줘')가
    # 재작성으로 소비돼 초안이 조회 문장 기반으로 뒤바뀜. 조회는 답만 하고 초안을 유지한다.
    for msg in ["지금 진행으로 되어 있는 티켓 보여줘", "이 티켓 마감일 언제야?", "완료로 변경된 티켓 몇 개야?"]:
        b = {"message": msg, "requester": CREATE_REQUESTER, "projects": _TWO_PROJECTS,
             "tickets": [], "work_schema": _FULL_CREATE_SCHEMA, "context": _create_preview_ctx()}
        with mock.patch.object(m, "answer_query", side_effect=lambda *a, **k: {"action": "TICKET_LIST", "context": a[1]}), \
             mock.patch.object(m, "claude_query", side_effect=lambda *a, **k: {"action": "QUERY", "context": a[1]}):
            d, _ = m.route_request(b)
        assert d["action"] not in ("CREATE_PREVIEW", "WRITE_CREATE"), f"{msg}: {d['action']}"


def test_r16_f14_different_project_query_during_create_no_hijack():
    # F14(MED 기존): CREATE 미리보기 중 다른 프로젝트 조회('클로비원 티켓 몇 개야?')가 재작성으로
    # 납치되고 초안 프로젝트가 뒤바뀜. 조회로 답하고 초안 프로젝트를 유지한다.
    b = {"message": "클로비원 티켓 몇 개야?", "requester": CREATE_REQUESTER, "projects": _TWO_PROJECTS,
         "tickets": [], "work_schema": _FULL_CREATE_SCHEMA, "context": _create_preview_ctx()}
    with mock.patch.object(m, "answer_query", side_effect=lambda *a, **k: {"action": "TICKET_COUNT", "context": a[1]}), \
         mock.patch.object(m, "claude_query", side_effect=lambda *a, **k: {"action": "QUERY", "context": a[1]}):
        d, _ = m.route_request(b)
    assert d["action"] not in ("CREATE_PREVIEW", "WRITE_CREATE"), d["action"]
    assert (d["context"].get("selected_project") or {}).get("id") == "p1", "초안 프로젝트가 바뀜"


def test_r16_f17_jamo_yes_confirms_not_help():
    # F17(MED 기존): 'ㅇㅇ'이 norm→''로 HELP '?'와 일치해 도움말. 자모 승인을 확정으로 인정한다.
    tk, ctx = _r16_upctx(changes={"status": "완료"}, status="진행")
    d, _ = _r16_route("ㅇㅇ", tk, dict(ctx))
    assert d["action"] == "WRITE_UPDATE", d["action"]
    assert m.is_help_intent("ㅇㅇ") is False
    assert m.is_help_intent("ㅇㅋ") is False


def test_r16_pure_approval_still_confirms():
    # 회귀 방지: 값 없는 순수 승인은 여전히 확정된다(fail-safe가 지나쳐 승인을 막으면 안 된다).
    tk, ctx = _r16_upctx(changes={"status": "완료"}, status="진행")
    for msg in ["응", "네", "응 변경해줘", "그대로 반영해줘", "변경해줘", "재시도"]:
        d, _ = _r16_route(msg, tk, dict(ctx))
        assert d["action"] == "WRITE_UPDATE", f"{msg}: {d['action']}"


def test_self_reference_assignee_with_josa_resolves_to_requester():
    # 라이브 확인: '담당자 나로'가 '나로'를 실존 담당자 이름으로 조회해 "'나로' 담당자를 찾지
    # 못했습니다"로 되묻던 결함. 조사(로/가/…)가 붙은 자기지시를 요청자 본인으로 해석한다.
    directory = [
        {"id": "u1", "name": "황형섭", "email": "a@goodmit.co.kr"},
        {"id": "u2", "name": "홍길동", "email": "hong@goodmit.co.kr"},
        {"id": "u3", "name": "미로", "email": "miro@goodmit.co.kr"},  # '로'로 끝나는 실존 이름
    ]
    req = {"email": "a@goodmit.co.kr", "name": "황형섭"}
    for msg in ["담당자 나로", "담당자 나로 지정", "내가 담당", "담당자 저로", "담당자 본인으로", "담당자 나로 해줘"]:
        assert m._explicit_assignee_token(msg) == "", f"{msg}: 자기지시가 이름 토큰으로 샜다"
        names = [p["name"] for p in m.extract_assignee_names(msg, directory, req)]
        assert names == ["황형섭"], f"{msg}: {names}"
    # 실존 이름은 그대로 이름으로 — 자기지시 오탐 없음.
    assert m._explicit_assignee_token("담당자 미로") == "미로"
    assert [p["name"] for p in m.extract_assignee_names("담당자 미로", directory, req)] == ["미로"]
    assert [p["name"] for p in m.extract_assignee_names("담당자 홍길동", directory, req)] == ["홍길동"]


# ---------------------------------------------------------------------------
# Capability / feasibility / meta routing (#rigidity fix).
#
# Real live failures: the assistant forced the ticket-CREATE clarify template
# ("우선순위·난이도·마감일·담당자를 알려주세요") onto messages that were NOT trying to
# create a ticket — capability questions ("이런 것도 돼?"), feasibility/dry-run
# questions ("수정하지 말고 되는지만"), bulk requests, plain modify-existing intent,
# vague/chit-chat. These must fall through to the honest conversational layer
# (claude_query) or a clarify — never the CREATE interrogation.
# ---------------------------------------------------------------------------

# The two exact turns the real user sent. Both must route to the conversational
# layer, and must NOT emit the 3-field CREATE clarify template.
_VERBATIM_CAPABILITY_TURNS = [
    "기존 티켓 이해가 안되는게 있으면 너가 수정해줘~  이런 기능도 돼?",
    "티켓 전체 말이야... 해당 프로젝트에 있는 티켓을 전체 자동으로 수정하는 (수정하지말고 기능이 되는지 안되는지만)",
]


def _is_create_template(text_out: str) -> bool:
    """The rigid CREATE clarify template asks for the required fields together."""
    return "알려주세요" in text_out and ("우선순위" in text_out or "난이도" in text_out) and "티켓 등록에 필요한" in text_out


def test_capability_question_predicate_true_cases():
    # (1) capability/meta, (2) feasibility/dry-run — all recognized as capability.
    for msg in _VERBATIM_CAPABILITY_TURNS + [
        "이런 것도 돼?", "이것도 가능해?", "가능해?", "가능한가요?",
        "기능이 되는지만 알려줘", "이런 기능도 돼?", "그런 기능 있어?",
        "할 수 있어?", "지원해?", "지원하나요?",
        "실제로 하지말고 되는지만 알려줘", "테스트로만 해볼 수 있어?",
        "되는지 안되는지만 알려줘", "댓글 기능이 있나요?",
    ]:
        assert m.is_capability_question(msg), f"capability로 인식돼야 한다: {msg!r}"


def test_capability_question_predicate_false_cases():
    # Real work requests / queries must NOT be swallowed as capability questions.
    for msg in [
        "내 티켓 보여줘", "전체 티켓 보여줘", "포스코DX 계획 티켓 몇 개야?",
        "로그인 버그 티켓 만들어줘", "우선순위 높음으로 바꿔줘", "1번 완료 처리해줘",
        "결제 알림 기능 티켓 새로 만들어줘", "회원 추가 기능 티켓 있어?",
        "고마워", "안녕", "다음 주까지 마감인 티켓",
    ]:
        assert not m.is_capability_question(msg), f"capability 오탐: {msg!r}"


def test_bulk_modify_request_predicate():
    # (3) bulk/batch: a bulk WRITE is recognized; a bulk READ is a normal query.
    for msg in ["모든 티켓 일괄 수정해줘", "전체 티켓 완료 처리해줘", "전부 자동으로 수정해줘",
                "티켓 일괄로 변경해줘"]:
        assert m.is_bulk_modify_request(msg), f"일괄 수정으로 인식돼야 한다: {msg!r}"
    for msg in ["전체 티켓 보여줘", "모든 프로젝트 목록", "1번 완료 처리해줘",
                "전체 티켓 몇 개야?"]:
        assert not m.is_bulk_modify_request(msg), f"일괄 수정 오탐: {msg!r}"


def _route(msg, context=None, tickets=None):
    structured = {"answer": "기존 티켓 수정은 됩니다. 어떤 티켓을 어떻게 바꿀지 알려주세요.",
                  "ticket_ids": [], "project_ids": [],
                  "needs_clarification": False, "clarify_question": ""}
    with mock.patch.object(m.subprocess, "run", return_value=_fake_cli(structured)) as run:
        data, _ = m.process_request({
            "message": msg,
            "requester": {"email": "a@goodmit.co.kr", "name": "황형섭"},
            "projects": [], "tickets": tickets or [], "work_schema": {},
            "context": context or {},
        })
    return data, run


def test_verbatim_capability_turns_do_not_start_creation():
    # THE bug: these two must not emit the CREATE 3-field template, and must reach the LLM.
    for msg in _VERBATIM_CAPABILITY_TURNS:
        data, run = _route(msg)
        assert run.called, f"대화 계층(claude_query)으로 라우팅돼야 한다: {msg!r}"
        assert data["action"] == "QUERY", f"{msg!r} → {data['action']}"
        assert not _is_create_template(data["response_text"]), \
            f"CREATE 3필드 템플릿이 나오면 안 된다: {msg!r}\n{data['response_text']}"
        assert "티켓을 생성할 프로젝트를 알려주세요" not in data["response_text"], \
            f"프로젝트 되묻기(생성 흐름)로 새면 안 된다: {msg!r}"


def test_bulk_modify_request_routes_to_conversation_not_write():
    # (3) A bulk write request explains the limit conversationally instead of a blind
    # single-ticket write or the CREATE template.
    data, run = _route("모든 티켓 일괄 수정해줘")
    assert run.called
    assert data["action"] == "QUERY", data["action"]
    assert not _is_create_template(data["response_text"])


def test_capability_question_mid_creation_escapes_template():
    # Once in CREATE mode the flow used to swallow EVERYTHING. A capability question must
    # escape to the conversational layer while the draft stays intact for the next turn.
    assert m.is_create_intent("우선순위 높음으로 해줘", {"mode": "CREATE"}) is True
    assert m.is_create_intent("이런 것도 돼?", {"mode": "CREATE"}) is False
    assert m.is_create_intent("일괄로도 수정 되는지만 알려줘", {"mode": "CREATE"}) is False


def test_capability_question_during_pending_create_keeps_draft():
    # A capability question asked while a CREATE preview awaits approval must NOT be read as
    # a content revision (is_revision_intent used to catch '수정/기능' and redraw the draft).
    ctx = {
        "pending_action": {"kind": "CREATE"},
        "ticket_draft": {"title": "로그인 버그"},
        "mode": "CREATE",
        "pending_question": "approval",
    }
    data, run = _route("이런 것도 돼? 일괄로도 수정 가능해?", context=ctx)
    assert run.called, "대화로 답해야 한다"
    assert data["action"] == "QUERY", data["action"]
    # Draft preserved so the user can still approve/continue.
    assert isinstance(data["context"].get("pending_action"), dict)
    assert not _is_create_template(data["response_text"])


def test_modify_existing_intent_does_not_start_creation():
    # (4) modify-existing: '수정/고쳐/바꿔' on existing tickets must never be a CREATE.
    for msg in ["이 티켓 수정해줘", "그 티켓 고쳐줘", "이거 바꿔줘", "기존 티켓 좀 고쳐줘"]:
        assert not m.is_create_intent(msg, {}), f"수정 요청이 생성으로 샜다: {msg!r}"


def test_chit_chat_and_thanks_route_to_conversation():
    # (6) chit-chat / out-of-scope greetings get a natural reply, not the CREATE template.
    for msg in ["고마워", "안녕", "수고했어", "오늘 날짜 뭐야?"]:
        data, run = _route(msg)
        assert run.called, f"잡담은 대화 계층으로: {msg!r}"
        assert data["action"] in {"QUERY", "NEED_INPUT"}, f"{msg!r} → {data['action']}"
        assert not _is_create_template(data["response_text"]), msg


def test_capability_question_does_not_shadow_confident_write():
    # A confident explicit write that happens to include a capability-sounding tail still
    # goes to the update flow — capability routing is gated behind `not wants_update`.
    sm = {"완료": "완료", "진행": "진행", "계획": "계획"}
    assert m.is_update_intent("우선순위 높음으로 바꿔줘", {}, sm)
    # Even though this phrasing is polite, the explicit value+verb keeps it an update.
    assert m.is_update_intent("마감일 내일로 바꿔줘", {}, sm)


# ===========================================================================
# LOOP2 — broaden real Korean workplace-chat coverage without false positives.
# Every category has BOTH a positive routing case AND a paired regression guard
# proving a nearby confident create/query/update still reaches its real handler.
# ===========================================================================


# --- (1) How-to / usage questions ------------------------------------------

def test_howto_question_predicate_true_and_false():
    for msg in [
        "티켓 어떻게 만들어?", "티켓 만드는 방법 있어?", "댓글 다는 방법 알려줘",
        "마감일 어떻게 바꿔?", "사용법 알려줘", "이거 어떻게 해야 해?",
        "우선순위 어떻게 변경해?",
    ]:
        assert m.is_howto_question(msg), f"how-to로 인식돼야 한다: {msg!r}"
    # Confident imperatives are NOT how-to.
    for msg in ["티켓 만들어줘", "3번 완료로 바꿔줘", "내 티켓 보여줘",
                "마감일 내일로 바꿔줘", "로그인 버그 티켓 등록해줘"]:
        assert not m.is_howto_question(msg), f"how-to 오탐: {msg!r}"


def test_howto_routes_to_conversation_not_create_or_dump():
    # POSITIVE: how-to questions get a conversational (LLM) answer, never the CREATE
    # template and never a blind ticket list.
    for msg in ["티켓 어떻게 만들어?", "티켓 만드는 방법 있어?", "댓글 다는 방법 알려줘"]:
        data, run = _route(msg)
        assert run.called, f"대화 계층으로 라우팅돼야 한다: {msg!r}"
        assert data["action"] == "QUERY", f"{msg!r} → {data['action']}"
        assert not _is_create_template(data["response_text"]), msg
        assert "티켓을 생성할 프로젝트를 알려주세요" not in data["response_text"], msg


def test_howto_does_not_hijack_confident_create():
    # REGRESSION: an unambiguous create with no how-to marker still creates.
    assert m.is_create_intent("로그인 버그 티켓 만들어줘", {}) is True
    assert m.is_howto_question("로그인 버그 티켓 만들어줘") is False


# --- (2) Comparison / decision help ----------------------------------------

def test_comparison_decision_routes_to_llm():
    # POSITIVE: decision questions reason with the LLM, not a rigid template/dump.
    for msg in ["A랑 B 중 뭐가 나아?", "우선순위 어떻게 정하지?", "뭐부터 해야 할까?"]:
        data, run = _route(msg)
        assert run.called, f"의사결정은 대화 계층으로: {msg!r}"
        assert data["action"] == "QUERY", f"{msg!r} → {data['action']}"
        assert not _is_create_template(data["response_text"]), msg


def test_comparison_does_not_hijack_confident_query():
    # REGRESSION: a confident structured query still uses the deterministic rule engine.
    data, run = _route("내 티켓 보여줘")
    assert data["action"] == "TICKET_LIST", data["action"]
    assert not run.called, "정형 조회는 규칙 엔진이 처리해야 한다(claude_query 아님)"


# --- (3) Status / summary reasoning -----------------------------------------

def test_status_summary_routes_to_llm():
    # POSITIVE (verify): status/summary reasoning reaches the conversational layer.
    for msg in ["요즘 뭐가 밀렸어?", "이번주 리스크 뭐야?", "누가 제일 바빠?"]:
        data, run = _route(msg)
        assert run.called, f"현황 추론은 대화 계층으로: {msg!r}"
        assert data["action"] == "QUERY", f"{msg!r} → {data['action']}"


def test_status_summary_does_not_hijack_count_query():
    # REGRESSION: a plain count query stays deterministic (rule engine), not LLM.
    data, run = _route("전체 티켓 몇 개야?", tickets=[
        {"id": "t1", "title": "A", "status": "진행", "assignees": [], "project_names": []}])
    assert not run.called, "개수 조회는 규칙 엔진이 정확히 세야 한다"
    assert data["action"] in {"TICKET_COUNT", "TICKET_LIST"}, data["action"]


# --- (4) Undo / cancel / mistake --------------------------------------------

def test_undo_intent_predicate_true_and_false():
    for msg in ["방금 거 취소", "아까 잘못 말했어", "그거 말고", "방금 한 말 취소해줘",
                "아까 잘못 골랐어", "그게 아니라"]:
        assert m.is_undo_intent(msg), f"undo로 인식돼야 한다: {msg!r}"
    for msg in ["3번 완료로 바꿔줘", "내 티켓 보여줘", "티켓 만들어줘", "응 변경해줘"]:
        assert not m.is_undo_intent(msg), f"undo 오탐: {msg!r}"


def test_undo_during_pending_declines_the_write():
    # POSITIVE: an undo cancels the pending write and preserves prior conversation.
    for msg in ["방금 거 취소", "그거 말고", "아까 잘못 말했어"]:
        tk, ctx = _r16_upctx(changes={"status": "완료"})
        d, _ = _r16_route(msg, tk, dict(ctx))
        assert d["action"] == "DECLINED", f"{msg!r} → {d['action']}"
        assert "pending_action" not in d["context"], f"{msg!r}: pending이 남았다"


def test_undo_does_not_hijack_redefinition_or_approval():
    # REGRESSION: '그거 말고 2번을 변경해줘' names a concrete alternative — it must pivot,
    # not decline; a pure approval must still confirm.
    tk1 = _raw_ticket("tk1", "결제 오류 수정", status="진행")
    tk2 = _raw_ticket("tk2", "포털 배포", status="진행")
    ctx = {"pending_action": {"kind": "UPDATE", "ticket_id": "tk1", "ticket_title": "결제 오류 수정",
                              "changes": {"status": "완료"}, "needs_confirmation": True, "direct": False},
           "pending_question": "approval", "selected_ticket": m.normalize_ticket(tk1, {}),
           "last_results": ["tk1", "tk2"], "last_result_start": 1}
    d, _ = _r16_route("그거 말고 2번을 변경해줘", tk1, dict(ctx), tickets=[tk1, tk2])
    assert d["action"] != "DECLINED", "구체적 대안을 담은 재정의를 무르기로 오인하면 안 된다"
    # A pure approval still confirms the pending write.
    tk, actx = _r16_upctx(changes={"status": "완료"})
    d2, _ = _r16_route("응 변경해줘", tk, dict(actx))
    assert d2["action"] == "WRITE_UPDATE", d2["action"]


def test_undo_without_pending_is_graceful_not_create():
    # REGRESSION: an undo with nothing in flight is small talk, never a new creation.
    for msg in ["방금 거 취소", "아까 잘못 말했어"]:
        data, run = _route(msg)
        assert run.called, f"대화 계층으로: {msg!r}"
        assert data["action"] == "QUERY", f"{msg!r} → {data['action']}"
        assert not _is_create_template(data["response_text"]), msg


# --- (5) Multi-intent -------------------------------------------------------

def test_multi_create_intent_predicate_true_and_false():
    for msg in ["티켓 만들고 담당자도 알려줘", "티켓 등록하고 목록도 보여줘",
                "작업 만들어서 누가 하는지도 알려줘"]:
        assert m.is_multi_create_intent(msg), f"복합 요청으로 인식돼야 한다: {msg!r}"
    # A plain single create is NOT multi-intent (ends in 만들어줘/등록해줘).
    for msg in ["티켓 만들어줘", "로그인 버그 티켓 등록해줘", "내 티켓 보여줘"]:
        assert not m.is_multi_create_intent(msg), f"복합 요청 오탐: {msg!r}"


def test_multi_intent_routes_to_conversation():
    # POSITIVE: a create joined to a second ask reaches the conversational layer instead
    # of a blind ticket dump, so it can acknowledge both and ask which to do first.
    data, run = _route("티켓 만들고 담당자도 알려줘")
    assert run.called, "복합 요청은 대화 계층으로"
    assert data["action"] == "QUERY", data["action"]
    assert not _is_create_template(data["response_text"])


def test_multi_intent_does_not_hijack_plain_create():
    # REGRESSION: an unambiguous single create still creates (not routed to chit-chat).
    data, run = _route("로그인 버그 티켓 만들어줘", tickets=[])
    assert data["action"] != "QUERY", "확실한 생성이 대화로 새면 안 된다"


# --- (7) Bare fragments / ambiguous single tokens ---------------------------

def test_bare_fragment_predicate_true_and_false():
    for msg in ["티켓", "프로젝트?", "음...", "그", "저기", "업무"]:
        assert m.is_bare_fragment(msg), f"단편으로 인식돼야 한다: {msg!r}"
    for msg in ["내 티켓 보여줘", "티켓 만들어줘", "프로젝트 목록 보여줘", "티켓 몇 개야?"]:
        assert not m.is_bare_fragment(msg), f"단편 오탐: {msg!r}"


def test_bare_fragment_routes_to_gentle_clarify():
    # POSITIVE: a lone token offers concrete options, not a blind dump or CREATE template.
    for msg in ["티켓", "프로젝트?"]:
        data, run = _route(msg)
        assert data["action"] == "NEED_INPUT", f"{msg!r} → {data['action']}"
        assert not run.called, "단편은 결정적 clarify여야 한다(LLM 호출 없음)"
        assert data.get("choices"), f"{msg!r}: 구체적 선택지가 있어야 한다"
        assert not _is_create_template(data["response_text"]), msg


def test_bare_fragment_does_not_hijack_real_query_or_active_work():
    # REGRESSION 1: a real query with the same noun still runs as a query.
    data, run = _route("내 티켓 보여줘")
    assert data["action"] == "TICKET_LIST", data["action"]
    # REGRESSION 2: a lone token while work is in flight does not clarify — the pending
    # flow keeps ownership (here a pending CREATE answers conversationally, draft intact).
    ctx = {"pending_action": {"kind": "CREATE"}, "ticket_draft": {"title": "로그인 버그"},
           "mode": "CREATE", "pending_question": "approval"}
    data2, run2 = _route("티켓", context=ctx)
    assert data2["action"] != "NEED_INPUT" or run2.called, \
        "진행 중 작업이 있으면 단편 clarify가 가로채면 안 된다"
    assert isinstance(data2["context"].get("pending_action"), dict), "초안이 유지돼야 한다"


# --- (8) English / mixed-language variants ----------------------------------

def test_english_capability_and_howto_route_to_conversation():
    # POSITIVE: EN capability/how-to reach the conversational layer, never CREATE/dump.
    for msg in ["can you do this?", "is that possible?", "how do I create a ticket?"]:
        assert m.is_capability_question(msg), f"EN capability 인식: {msg!r}"
        data, run = _route(msg)
        assert run.called, f"EN은 대화 계층으로: {msg!r}"
        assert data["action"] == "QUERY", f"{msg!r} → {data['action']}"
        assert not _is_create_template(data["response_text"]), msg


def test_english_greetings_route_to_conversation_not_template():
    # REGRESSION: EN small talk is a natural reply, not a capability misfire or template.
    for msg in ["thanks", "hello"]:
        assert not m.is_capability_question(msg), f"인사를 capability로 오인: {msg!r}"
        data, run = _route(msg)
        assert run.called, f"EN 인사는 대화로: {msg!r}"
        assert data["action"] == "QUERY", f"{msg!r} → {data['action']}"


# --- (9) 팀 놀이 AI 퀴즈 생성 (§7-9) ----------------------------------------

def _quiz_cli(questions):
    return _fake_cli({"questions": questions})


def test_generate_quiz_maps_answer_text_to_index():
    qs = [
        {"q": "1+1?", "options": ["1", "2", "3"], "answer": "2"},
        {"q": "하늘색?", "options": ["빨강", "파랑"], "answer": "파랑"},
    ]
    with mock.patch.object(m.subprocess, "run", return_value=_quiz_cli(qs)) as run:
        out, ai_ms = m.generate_quiz("상식", 2, 3)
    assert run.called
    assert out == [
        {"q": "1+1?", "options": ["1", "2", "3"], "answer": 1},
        {"q": "하늘색?", "options": ["빨강", "파랑"], "answer": 1},
    ]
    assert ai_ms >= 0


def test_generate_quiz_drops_bad_items():
    qs = [
        {"q": "정답이 보기에 없음", "options": ["a", "b"], "answer": "c"},   # drop
        {"q": "보기 부족", "options": ["only"], "answer": "only"},            # drop
        {"q": "", "options": ["a", "b"], "answer": "a"},                       # drop (빈 질문)
        {"q": "정상", "options": ["a", "b", "b"], "answer": "b"},              # 중복 보기 정리 → [a,b], answer=1
    ]
    with mock.patch.object(m.subprocess, "run", return_value=_quiz_cli(qs)):
        out, _ = m.generate_quiz("t", 5, 4)
    assert out == [{"q": "정상", "options": ["a", "b"], "answer": 1}]


def test_generate_quiz_cli_failure_returns_empty_not_raise():
    class Fail:
        returncode = 1
        stdout = ""
        stderr = "boom"
    with mock.patch.object(m.subprocess, "run", return_value=Fail()), mock.patch.object(m.time, "sleep"):
        out, _ = m.generate_quiz("t", 3, 4)
    assert out == []  # 실패는 빈 목록으로 — 예외를 던지지 않는다


def test_sanitize_quiz_ignores_non_list_and_caps():
    assert m._sanitize_quiz(None, 4) == []
    assert m._sanitize_quiz("nope", 4) == []
    big = [{"q": f"q{i}", "options": ["a", "b"], "answer": "a"} for i in range(30)]
    assert len(m._sanitize_quiz(big, 4)) == 20  # 최대 20문항
