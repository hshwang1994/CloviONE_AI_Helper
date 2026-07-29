"""n8n v7 워크플로가 러너에게 넘기는 컨텍스트의 계약.

n8n JSON에는 테스트가 없다. 그래서 '노드가 무엇을 지우는가'를 이 파일에서 못 박는다 —
워크플로가 바뀌어 계약이 깨지면 여기서 잡힌다.

이 파일은 test_assistant.py와 분리돼 있다(다른 세션이 그 파일을 동시에 고칠 수 있다).
"""

import importlib.util
import json
import os
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_V7 = _ROOT / "docs" / "n8n" / "ClovirONE_AI_Work_Assistant_v7.json"

os.environ.setdefault("RUNNER_TOKEN", "test-token")
_spec = importlib.util.spec_from_file_location(
    "assistant_contract", Path(__file__).resolve().parent / "assistant.py"
)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)


def _node(name):
    wf = json.loads(_V7.read_text(encoding="utf-8"))
    for n in wf["nodes"]:
        if n["name"] == name:
            return n
    raise AssertionError(f"노드 '{name}'을 찾지 못했다 — 워크플로 구조가 바뀌었다")


def test_create_success_closes_the_draft_completely():
    """CREATE가 성공하면 그 초안에 딸린 것이 전부 함께 닫혀야 한다.

    한때 pending_action/pending_question만 지우고 draft_images·ticket_draft·image_notes를
    남겼다. 그래서 다음 티켓이 지난 초안의 스크린샷을 물려받아, 월요일 로그인 오류 화면이
    수요일 결제 리팩터링 티켓에 붙었다. 러너는 초안을 만들 때 draft_images에 '이 초안이 보고
    쓴 화면'을 적으므로, 소진된 초안의 값이 남아 있으면 다음 초안이 그대로 이어받는다.
    """
    js = _node("Notion 변경 결과")["parameters"]["jsCode"]
    for key in ("pending_action", "pending_question", "draft_images", "ticket_draft", "image_notes"):
        assert f"delete context.{key};" in js, (
            f"CREATE 성공 분기가 context.{key}를 남긴다 — 다음 티켓이 물려받는다"
        )


def test_only_create_wipes_the_draft_state():
    """초안에 딸린 것(draft_images·ticket_draft·image_notes)은 **CREATE 성공에만** 지운다.

    이 세 삭제문이 write_kind 분기 밖에 있어서 COMMENT·UPDATE 성공에도 실행됐다. 그래서
    사용자가 초안을 승인하기 전에 다른 티켓에 댓글을 달거나 상태를 바꾸면, 승인 대기 중이던
    초안의 ticket_draft가 통째로 사라지고 image_notes(이미지 Q&A가 이어서 참조하는 값)도
    함께 날아갔다. 초안을 소진한 것은 CREATE뿐이므로 CREATE에서만 닫아야 한다.
    """
    js = _node("Notion 변경 결과")["parameters"]["jsCode"]
    create_idx = js.index("write_kind === 'CREATE'")
    else_idx = js.index("} else {", create_idx)   # UPDATE 분기 시작
    create_branch = js[create_idx:else_idx]
    for key in ("draft_images", "ticket_draft", "image_notes"):
        assert f"delete context.{key};" in create_branch, (
            f"context.{key} 삭제가 CREATE 분기 안에 없다 — 분기 밖이면 UPDATE·COMMENT도 지운다"
        )
    # 분기 밖(성공 진입 직후, 첫 write_kind 분기 이전)에는 초안 삭제가 없어야 한다.
    comment_idx = js.index("write_kind === 'COMMENT'")
    preamble = js[js.index("const success ="):comment_idx]
    for key in ("draft_images", "ticket_draft", "image_notes"):
        assert f"delete context.{key};" not in preamble, (
            f"context.{key} 삭제가 아직 분기 밖에 있다 — COMMENT·UPDATE 성공도 지운다"
        )
    # pending_action·pending_question은 어떤 쓰기든 완료되면 닫는다 — 이건 분기 밖이 맞다.
    for key in ("pending_action", "pending_question"):
        assert f"delete context.{key};" in preamble, (
            f"context.{key}는 모든 성공에서 닫혀야 한다(분기 밖)"
        )


def test_cache_store_and_hit_agree():
    """'캐시 기록'의 저장 조건과 '캐시 확인'의 적중 조건이 어긋나면 안 된다.

    저장은 OR(projects 또는 tickets가 있으면)로 쓰는데 적중은 AND(둘 다 있어야)로 읽었다.
    그래서 한쪽만 있는 워크스페이스는 캐시에 써 놓고도 영영 못 읽어, 매 요청이 Notion
    전체를 다시 조회했다. 두 조건이 같은 술어를 봐야 한다.
    """
    store = _node("캐시 기록")["parameters"]["jsCode"]
    check = _node("캐시 확인")["parameters"]["jsCode"]
    # 적중은 둘 다 있어야(AND) 한다 — 부분 캐시를 완전한 데이터인 척 쓰지 않는다.
    assert "projects.length > 0 &&" in check and "tickets.length > 0 &&" in check
    # 저장도 같은 술어여야 한다: 완전한 데이터일 때만 캐시한다(실패한 조회의 빈 배열 방지).
    assert "projects.length > 0 && tickets.length > 0" in store, (
        "저장 조건이 적중 조건과 어긋난다 — 한쪽만 있으면 저장돼도 영영 미적중이다"
    )
    assert "projects.length > 0 ||" not in store, "저장이 아직 OR 조건이다"


def test_dedupe_identity_matches_the_runner():
    """n8n의 신원 조각이 러너의 requester_state_key와 같은 순서·같은 값을 봐야 한다.

    어긋나면 이름만 있는 요청자가 전부 한 칸에 몰려, 같은 대화·같은 message_id를 쓴 다른
    사람에게 남의 티켓 제목·Notion URL·대화 문맥이 그대로 돌아간다.
    """
    js = _node("요청 전처리")["parameters"]["jsCode"]
    assert "requester.email || requester.teams_user_id || nk(requester.name) || 'anonymous'" in js, (
        "신원 조각이 러너(clean_email(email) or teams_user_id or norm(name))와 어긋난다"
    )
    # 러너 쪽 정의가 바뀌면 이 테스트가 먼저 깨져야 한다.
    assert m.requester_state_key({"name": "홍 길동"}) == m.requester_state_key({"name": "홍길동"}), \
        "러너의 norm()이 공백을 지운다는 전제가 깨졌다 — n8n의 nk()도 함께 고쳐야 한다"
    assert m.requester_state_key({"email": "A@X.co", "name": "다른이름"}) == "a@x.co", \
        "러너는 이메일을 최우선으로 본다는 전제가 깨졌다"


def test_work_summary_resets_the_numbering_basis():
    """WORK_SUMMARY의 본문은 1부터 센다 — 컨텍스트의 번호 기준도 함께 1로 돌아가야 한다.

    이 분기는 본문을 `enumerate(my_tickets[:10], 1)`로 1..10으로 찍으면서 이전 페이지의
    last_result_start(예: 11)를 그대로 물려줬다. 그러면 화면이 본문 1..10 / 카드 11..20으로
    같은 말풍선 안에서 자기 모순을 일으키고, 사용자가 "3번 상세"라고 하면 엉뚱한 티켓이 나온다.
    같은 함수의 다른 분기들은 전부 "last_result_start": 1을 명시한다.
    """
    schema = {"status": ["계획", "진행", "완료"]}
    me = {"id": "u1", "name": "황형섭", "email": "a@goodmit.co.kr"}
    tickets = [
        {"id": f"t{i}", "title": f"티켓{i}", "status": "진행",
         "assignees": [me], "project_ids": []}
        for i in range(1, 4)
    ]
    # 직전 턴이 2페이지를 봤다 — 번호 기준이 11로 남아 있다.
    ctx = {"last_result_start": 11, "last_results": ["old1", "old2"]}
    data, _ = m.route_request({
        "message": "내 업무 현황 보여줘",
        "requester": {"email": "a@goodmit.co.kr", "name": "황형섭"},
        "projects": [], "tickets": tickets, "work_schema": schema, "context": ctx,
    })
    if data["action"] != "WORK_SUMMARY":
        import pytest
        pytest.skip(f"이 입력이 WORK_SUMMARY로 안 갔다: {data['action']}")
    start = data["context"].get("last_result_start")
    assert start == 1, (
        f"본문은 1부터 세는데 번호 기준이 {start}로 남았다 — 화면이 본문 1..N / 카드 {start}..로 "
        "자기 모순을 일으킨다"
    )


# --- 1인칭 표기 흔들림 (사용자 실제 보고) -----------------------------------

def test_first_person_survives_spacing_and_short_forms():
    """사람이 쓰는 1인칭 표기를 다 받아야 한다.

    사용자 실제 보고: "나 에게 할당된 티켓 리스트 보자"가
    "'나 에게 할당된'이라는 이름으로는 찾지 못해..."로 답했다. 조사를 띄어 쓴 것뿐인데
    그 말 전체가 사람 **이름**으로 추측된 것이다.

    이 판정은 원문에 정규식을 돌린다(어절 간격을 세야 하므로 norm을 못 쓴다). 그래서
    '나에게'는 잡히고 '나 에게'는 안 잡혔다. '내게/제게'는 조사 목록에 '게'가 없어 빠졌다.
    """
    for msg in [
        "나에게 할당된 티켓 리스트 보자",
        "나 에게 할당된 티켓 리스트 보자",   # 조사를 띄어 씀
        "내게 할당된 티켓 보여줘",
        "제게 할당된 티켓 보여줘",
        "나 한테 할당된 티켓 보여줘",
        "내 티켓 보여줘",
        "제가 맡은 급한 업무 보여줘",
    ]:
        assert m.asks_for_own_work(msg), f"1인칭을 못 알아봤다: {msg!r}"

    # 과잉 수정 방지 — 남의 일이 내 일이 되면 안 된다
    for msg in [
        "제 동료 김민수 티켓 보여줘",
        "사내 티켓 관리 프로젝트 보여줘",
        "저 프로젝트 티켓 보여줘",           # 지시관형사
        "내일 마감 티켓 보여줘",
    ]:
        assert not m.asks_for_own_work(msg), f"남의 일을 내 일로 읽었다: {msg!r}"
