"""티켓 생성 채팅 경로의 **계약 고정** (WORK_PLAN_INDEX §7 "Phase 3 러너 티켓 라우팅" = [부분]).

계획 문서는 이 경로를 "배포됨, 단 **실제 채팅 end-to-end(진짜 티켓 생성) 미검증**"으로 남겨
뒀다. 곧 티켓 **조회** 경로가 로컬 캐시로 옮겨간다. 그러면 "정말 티켓이 만들어졌나"를 플랫폼
쪽에서 확인할 방법이 더 모호해진다 — 플랫폼에는 티켓 테이블이 없고(app/tickets 는 Notion 을
직접 읽는다), 생성된 티켓의 유일한 플랫폼 기록은 **어시스턴트 메시지의 structured_payload**
뿐이기 때문이다. 옮기기 전에 지금의 계약을 못 박아 둔다.

이 파일이 못 박는 것
  1. 사용자가 "티켓 만들어줘"라고 했을 때 나가는 아웃바운드 요청의 정확한 모양 —
     엔드포인트/메서드/헤더/본문 키와 **각 키의 출처**.
  2. 러너/n8n 응답을 어떻게 읽고 무엇을 저장하는가 — 특히 action=CREATED(티켓 생성됨) 분기.
  3. 실패 갈래(4xx / 5xx / 2xx-이상한 본문 / 타임아웃 / 연결 실패 / allowlist 차단)에서 잡이
     어떤 상태로 끝나고 오류가 어디에 남는가. 조용히 삼켜지는 것이 없어야 한다.
  4. 재전송(브라우저 중복 제출 / 워커 재시도 / 사용자 '다시 시도')이 티켓을 두 번 만드는가.

이 파일이 **증명하지 못하는 것**(정직하게)
  여기의 n8n·러너·Notion 은 전부 가짜(httpx MockTransport)다. "진짜 Notion 페이지가 생겼다"는
  이 파일로 절대 증명되지 않는다. 파일 맨 아래 '사람이 직접 해야 하는 확인' 목록 참고.

응답 본문은 실제 워크플로(docs/n8n/ClovirONE_AI_Work_Assistant_v7.json)의 코드 노드
'조회 및 질문 응답'(초안 턴)과 'Notion 변경 결과'(생성 성공 턴)가 만들어 내는 모양을 그대로
옮긴 것이다. 워크플로가 바뀌어 계약이 깨지면 여기서 잡힌다.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import literal_column, select

from app.jobs.handlers.chat_message import CHAT_WORKFLOW_NAME, handle_chat_message
from app.jobs.models import Job
from app.jobs.worker import Worker, WorkerContext

pytestmark = pytest.mark.integration

N8N_URL = "http://127.0.0.1:5678/webhook/clovirone-work-assistant"

USER_EMAIL = "ticketer@goodmit.co.kr"
USER_NAME = "티켓 요청자"

# 사용자가 실제로 치는 두 턴: 초안 요청 → 승인. 러너의 생성은 항상 2턴이다
# (CREATE_PREVIEW → 승인 → WRITE_CREATE → CREATED).
DRAFT_TEXT = "결제 모듈 리팩터링 티켓 만들어줘. 마감 8월 10일, 우선순위 높음."
APPROVE_TEXT = "등록해줘"

DRAFT_MSG_ID = "tkt0draft0123456789abcdef012345"
APPROVE_MSG_ID = "tkt0approve0123456789abcdef0123"

NOTION_PAGE_ID = "22b1e0f0-1111-4222-8333-444455556666"
NOTION_URL = "https://www.notion.so/22b1e0f0111142228333444455556666"
TICKET_TITLE = "결제 모듈 리팩터링"


# --- 실제 n8n 이 돌려주는 두 응답 모양 -----------------------------------------


def preview_response(conversation_id: str, *, message_id: str = DRAFT_MSG_ID) -> dict:
    """초안 턴: 노드 '조회 및 질문 응답'의 허용목록 envelope + 러너의 CREATE_PREVIEW.

    핵심: 초안(ticket_draft)과 승인 대기 상태(pending_action/pending_question)는 **전부
    n8n/러너 쪽 context 에만** 산다. 플랫폼은 다음 턴에 context 를 되돌려 보내지 않는다
    (아래 test_platform_never_sends_context_back 참고).
    """
    return {
        "action": "CREATE_PREVIEW",
        "response_text": (
            "다음 내용으로 티켓을 만들까요?\n"
            f"제목: {TICKET_TITLE}\n마감일: 2026-08-10\n우선순위: 높음\n담당자: 티켓 요청자"
        ),
        "context": {
            "pending_action": {"kind": "CREATE", "title": TICKET_TITLE},
            "pending_question": "approval",
            "ticket_draft": {"title": TICKET_TITLE, "due_date": "2026-08-10", "priority": "높음"},
            "_context_revision": 1,
        },
        "questions": [],
        "tickets": [],
        "projects": [],
        "ticket": None,
        "ticket_draft": {"title": TICKET_TITLE, "due_date": "2026-08-10", "priority": "높음"},
        "choices": [
            {"label": "이대로 등록", "send": "등록해줘"},
            {"label": "등록 안 함", "send": "아니"},
        ],
        "message_id": message_id,
        "request_id": "req-1770000000000-aaaaaa",
        # n8n '요청 전처리'는 body.conversation_id 를 그대로 되돌려준다(에코).
        "conversation_id": conversation_id,
        "timing": {"total_ms": 812, "assistant_ms": 640, "ai_ms": 610, "ai_used": True, "local": False},
    }


def created_response(
    conversation_id: str, *, message_id: str = APPROVE_MSG_ID, duplicate: bool = False
) -> dict:
    """생성 성공 턴: 노드 'Notion 변경 결과'의 CREATE 분기가 만드는 모양 그대로.

    duplicate=True 는 n8n 이 재전송을 걸러 **저장해 둔 응답을 다시 돌려준** 경우
    (노드 '요청 전처리'의 processedMessages 적중). 새 티켓은 만들어지지 않는다.
    """
    ticket = {
        "id": NOTION_PAGE_ID,
        "title": TICKET_TITLE,
        "url": NOTION_URL,
        "status": "계획",
        "due_date": "2026-08-10",
        "priority": "높음",
        "difficulty": "",
    }
    body = {
        "action": "CREATED",
        "response_text": f"Notion 티켓이 생성됐습니다.\n제목: {TICKET_TITLE}\n링크: {NOTION_URL}",
        "context": {
            "selected_ticket": ticket,
            "last_results": [NOTION_PAGE_ID],
            "last_result_start": 1,
            "last_action": {
                "kind": "CREATE",
                "success": True,
                "ticket_id": NOTION_PAGE_ID,
                "ticket_title": TICKET_TITLE,
                "url": NOTION_URL,
                "at": "2026-07-14T09:00:00.000Z",
            },
            "_context_revision": 2,
            "_context_updated_at": "2026-07-14T09:00:00.000Z",
        },
        "ticket": ticket,
        "choices": [],
        "message_id": message_id,
        "request_id": "req-1770000000001-bbbbbb",
        "conversation_id": conversation_id,
        "timing": {"total_ms": 2140, "assistant_ms": 900, "ai_ms": 850, "ai_used": True, "local": False},
    }
    if duplicate:
        body = {**body, "duplicate": True}
    return body


# --- harness ------------------------------------------------------------------


@pytest.fixture()
def chat_worker(app, settings, fake_clock):
    ctx = WorkerContext(
        settings=settings, clock=fake_clock, outbound_client=app.state.outbound_client
    )
    return Worker(
        app.state.session_factory,
        fake_clock,
        {"chat_message": handle_chat_message},
        ctx,
        poll_interval=0.01,
    )


@pytest.fixture()
def ticket_chat(client, login_as, make_user):
    """로그인 → 대화 생성 → "티켓 만들어줘" 전송. 사용자가 실제로 하는 그대로."""
    make_user(USER_EMAIL, display_name=USER_NAME)
    csrf = login_as("user", email=USER_EMAIL)
    conversation = client.post(
        "/api/conversations", json={}, headers={"X-CSRF-Token": csrf}
    ).json()["conversation"]

    def send(content: str, client_message_id: str, **extra):
        return client.post(
            f"/api/conversations/{conversation['id']}/messages",
            json={"content": content, "client_message_id": client_message_id, **extra},
            headers={"X-CSRF-Token": csrf},
        )

    first = send(
        DRAFT_TEXT,
        DRAFT_MSG_ID,
        # 클라이언트가 요청자를 위조해 보내도 무시돼야 한다(§11.2). 아래에서 확인한다.
        requester={"email": "attacker@evil.example", "name": "공격자"},
    )
    assert first.status_code == 202, first.text
    return {
        "conversation_id": conversation["id"],
        "csrf": csrf,
        "send": send,
        "message_db_id": first.json()["message"]["id"],
        "job_id": first.json()["job_id"],
    }


def sent_body(fake_http, index: int = -1) -> dict:
    return json.loads(fake_http.requests[index].content)


def messages(client, conversation_id: str) -> list[dict]:
    return client.get(f"/api/conversations/{conversation_id}/messages").json()["items"]


def jobs_for(db, message_id: str) -> list[Job]:
    db.expire_all()
    return list(
        db.execute(
            select(Job).where(Job.message_id == message_id).order_by(literal_column("rowid"))
        )
        .scalars()
        .all()
    )


def only_job(db, message_id: str = DRAFT_MSG_ID) -> Job:
    rows = jobs_for(db, message_id)
    assert len(rows) == 1, f"expected exactly one job for {message_id}, got {len(rows)}"
    return rows[0]


# =============================================================================
# 1. 아웃바운드 요청 계약 — 어디로, 어떻게, 무엇을 보내는가
# =============================================================================


def test_create_ticket_outbound_request_is_pinned(
    app, settings, db, chat_worker, fake_http, ticket_chat
):
    """티켓 생성 요청 1건의 URL/메서드/헤더/본문 전체 모양."""
    fake_http.on(N8N_URL, json_body=preview_response(ticket_chat["conversation_id"]))
    assert chat_worker.run_once() is True

    assert len(fake_http.requests) == 1, "채팅 1건은 아웃바운드 1건 — 그 이상도 이하도 아니다"
    request = fake_http.requests[0]

    # --- 엔드포인트 / 메서드 -------------------------------------------------
    assert request.method == "POST"
    assert str(request.url) == N8N_URL == settings.n8n_work_assistant_url
    # 정적 설정값과 Workflow 레지스트리 시드값이 어긋나면, 레지스트리를 시드한 설치에서만
    # 채팅이 조용히 다른 URL 로 간다. 두 출처가 같은 값임을 못 박는다.
    from app.workflows.models import Workflow
    from app.workflows.service import seed_known_workflows

    seed_known_workflows(db, allowlists=app.state.allowlists)
    db.commit()
    row = db.execute(
        select(Workflow).where(Workflow.name == CHAT_WORKFLOW_NAME)
    ).scalar_one()
    assert (row.webhook_url, row.http_method) == (settings.n8n_work_assistant_url, "POST")

    # --- 헤더 ---------------------------------------------------------------
    assert request.headers["content-type"].startswith("application/json")
    # 이 웹훅은 **무인증**이다. 보호 장치는 SSRF allowlist(127.0.0.1:5678 뿐)와 루프백뿐 —
    # 자격증명 헤더가 붙기 시작하면 그 사실이 바뀐 것이므로 여기서 잡힌다.
    assert "authorization" not in request.headers
    assert "x-api-key" not in request.headers

    # --- 본문: 키 전체 목록 (첨부가 없으면 attachments 키 자체가 없다) -------
    body = sent_body(fake_http)
    assert sorted(body) == [
        "conversation_id",
        "idempotency_key",
        "message",
        "message_id",
        "requester",
    ]

    # --- 각 키의 출처 -------------------------------------------------------
    assert body["message"] == DRAFT_TEXT  # 사용자가 친 그대로, 가공 없음
    assert body["message_id"] == DRAFT_MSG_ID  # 브라우저가 만든 client_message_id
    assert body["conversation_id"] == ticket_chat["conversation_id"]  # 첫 턴 = 플랫폼 대화 UUID
    assert body["idempotency_key"] == f"chatmsg:{DRAFT_MSG_ID}"
    assert sorted(body["requester"]) == ["email", "name", "user_id"]

    # 플랫폼은 context 를 보내지 않는다 — 초안/승인 대기 상태는 전적으로 n8n·러너 쪽에 산다.
    # (그래서 러너 상태가 유실되면 승인 턴이 아무 티켓도 만들지 않는데, 플랫폼은 그것을
    #  알 방법이 없다. 이 파일이 증명하지 못하는 부분이다.)
    assert "context" not in body
    assert "request_id" not in body  # request_id 는 n8n '요청 전처리'가 스스로 만든다


def test_requester_identity_comes_from_the_session_never_from_the_client(
    db, chat_worker, fake_http, ticket_chat
):
    """요청자는 **서버 세션 사용자**에서만 만들어진다(§11.2).

    fixture 는 위조 requester 를 함께 POST 했다. 그 값이 러너까지 흘러가면 러너는 남의
    Notion 사람으로 티켓을 만든다.
    """
    from app.users.service import get_user_by_email

    fake_http.on(N8N_URL, json_body=preview_response(ticket_chat["conversation_id"]))
    assert chat_worker.run_once() is True

    db.expire_all()
    user = get_user_by_email(db, USER_EMAIL)
    assert sent_body(fake_http)["requester"] == {
        "user_id": user.id,
        "email": USER_EMAIL,
        "name": USER_NAME,
    }
    assert b"attacker@evil.example" not in fake_http.requests[0].content


def test_second_turn_carries_the_backend_conversation_id(
    chat_worker, fake_http, ticket_chat, fake_clock
):
    """승인 턴은 초안 턴과 **같은 대화 키**로 나가야 한다 — 이것이 끊기면 러너는 승인
    메시지("등록해줘")를 붙일 초안을 못 찾고 티켓은 만들어지지 않는다.

    우선순위: 러너가 돌려준 backend_conversation_id > 플랫폼 대화 UUID. 여기서는 러너가
    자기 식별자를 돌려주는 경우로 확인한다(현재 n8n 은 받은 값을 그대로 에코하므로 실전
    값은 플랫폼 UUID 와 같다 — 계약은 "러너가 돌려준 값이 이긴다"이다).
    """
    backend_id = "n8n-ctx-9f3a"
    first = preview_response(ticket_chat["conversation_id"])
    fake_http.on(N8N_URL, json_body={**first, "conversation_id": backend_id})
    assert chat_worker.run_once() is True

    fake_clock.advance(5)
    assert ticket_chat["send"](APPROVE_TEXT, APPROVE_MSG_ID).status_code == 202
    fake_http.on(N8N_URL, json_body=created_response(backend_id))
    assert chat_worker.run_once() is True

    assert len(fake_http.requests) == 2
    assert sent_body(fake_http, 0)["conversation_id"] == ticket_chat["conversation_id"]
    assert sent_body(fake_http, 1)["conversation_id"] == backend_id
    assert sent_body(fake_http, 1)["message"] == APPROVE_TEXT
    assert sent_body(fake_http, 1)["idempotency_key"] == f"chatmsg:{APPROVE_MSG_ID}"


def test_method_comes_from_the_registry_and_get_drops_the_message(
    app, db, chat_worker, fake_http, ticket_chat
):
    """메서드는 Workflow 레지스트리 행에서 온다. 그리고 **GET 이면 본문이 통째로 사라진다.**

    현재 동작을 기록만 한다(고치는 것은 이 작업 범위 밖). 관리자 콘솔의 Workflow 화면은
    http_method 에 GET 을 허용한다(app/workflows/schemas.py). 핸들러는
    `json=request_body if http_method == "POST" else None` 이라, GET 으로 바꾸는 순간
    러너는 message/requester 를 아예 못 받는데 사용자 화면에는 아무 오류도 안 뜬다.
    """
    from app.workflows.models import Workflow
    from app.workflows.service import seed_known_workflows

    seed_known_workflows(db, allowlists=app.state.allowlists)
    db.commit()
    row = db.execute(
        select(Workflow).where(Workflow.name == CHAT_WORKFLOW_NAME)
    ).scalar_one()
    row.http_method = "GET"
    db.commit()

    fake_http.on(N8N_URL, json_body=preview_response(ticket_chat["conversation_id"]))
    assert chat_worker.run_once() is True

    request = fake_http.requests[-1]
    assert request.method == "GET"
    assert request.content == b""  # 사용자의 메시지가 통째로 유실된다 (미보호 — 기록만 함)
    # 그런데도 잡은 성공으로 끝나고 사용자에게는 정상 답변이 보인다.
    assert only_job(db).status == "succeeded"


def test_offlist_webhook_url_is_blocked_before_any_outbound_call(
    app, db, chat_worker, fake_http, ticket_chat, fake_clock
):
    """SSRF allowlist 는 호출 시점의 보안 경계다 — 관리자가 레지스트리 URL 을 외부로
    바꿔도 요청 자체가 나가지 않는다."""
    from app.workflows.models import Workflow
    from app.workflows.service import seed_known_workflows

    seed_known_workflows(db, allowlists=app.state.allowlists)
    db.commit()
    row = db.execute(
        select(Workflow).where(Workflow.name == CHAT_WORKFLOW_NAME)
    ).scalar_one()
    row.webhook_url = "http://evil.example/webhook/steal"
    db.commit()

    fake_http.on("http://evil.example", json_body={"response_text": "탈취"})
    assert chat_worker.run_once() is True

    assert fake_http.requests == [], "allowlist 밖 URL 로는 단 한 번도 나가면 안 된다"
    job = only_job(db)
    assert "허용 목록" in (job.last_error or "")
    # 참고(미보호, 기록만 함): URLNotAllowedError 는 PermanentJobError 가 아니라서 잡은
    # 재시도 큐로 돌아간다. 관리자가 URL 을 고치기 전에는 절대 성공할 수 없는데도
    # max_attempts 만큼 다시 시도한다.
    assert job.status == "queued"
    for _ in range(2):
        fake_clock.advance(60)
        assert chat_worker.run_once() is True
    assert only_job(db).status == "failed"
    assert fake_http.requests == []


# =============================================================================
# 2. 응답 파싱 — 무엇을 읽고 무엇을 저장하는가 (CREATED 분기)
# =============================================================================


def test_created_response_becomes_reply_ticket_card_and_backend_context(
    client, db, chat_worker, fake_http, fake_clock, ticket_chat
):
    """티켓 생성 성공 턴이 플랫폼에 남기는 것 전부.

    플랫폼에는 티켓 테이블이 없다. 생성된 Notion 페이지의 **유일한** 플랫폼 기록은 이
    어시스턴트 메시지의 structured_payload 다. (티켓 조회가 로컬 캐시로 옮겨가면, 그때
    캐시에도 써야 하는지 여기서 다시 판단해야 한다.)
    """
    # 1턴: 초안
    fake_http.on(N8N_URL, json_body=preview_response(ticket_chat["conversation_id"]))
    assert chat_worker.run_once() is True

    # 2턴: 승인 → 생성
    fake_clock.advance(5)
    assert ticket_chat["send"](APPROVE_TEXT, APPROVE_MSG_ID).status_code == 202
    body = created_response(ticket_chat["conversation_id"])
    fake_http.on(N8N_URL, json_body=body)
    fake_clock.advance(37)  # 결정론적 시계 — 아래 updated_at 을 이 값으로 못 박는다
    assert chat_worker.run_once() is True

    items = messages(client, ticket_chat["conversation_id"])
    assert [m["role"] for m in items] == ["user", "assistant", "user", "assistant"]
    approve_user, created = items[2], items[3]

    # 사용자에게 보이는 답 = response_text 그대로 (다른 키보다 우선, strip 됨)
    assert created["content"] == body["response_text"]
    assert NOTION_URL in created["content"]
    # 화면의 티켓 카드는 structured.ticket 에서 나온다(frontend/src/screens/Chat.jsx).
    assert created["structured"]["ticket"]["url"] == NOTION_URL
    assert created["structured"]["ticket"]["id"] == NOTION_PAGE_ID
    assert created["structured"]["action"] == "CREATED"
    # 응답 전체가 손실 없이 그대로 저장된다 — context/last_action 까지.
    assert created["structured"] == body
    assert created["message_id"] == f"a-{APPROVE_MSG_ID}-1"  # a-<사용자메시지>-<시도횟수>
    assert created["processing_status"] == "done"

    # 사용자 메시지는 done 으로 닫히고 오류 코드는 지워진다.
    assert (approve_user["processing_status"], approve_user["error_code"]) == ("done", None)

    job = only_job(db, APPROVE_MSG_ID)
    assert (job.status, job.attempt_count, job.last_error) == ("succeeded", 1, None)
    assert job.finished_at == fake_clock.now()

    from app.conversations.models import Conversation

    db.expire_all()
    conversation = db.get(Conversation, ticket_chat["conversation_id"])
    assert conversation.backend_conversation_id == ticket_chat["conversation_id"]
    assert conversation.updated_at == fake_clock.now()  # 시계는 FakeClock 하나뿐


def test_response_text_wins_over_other_text_keys_and_is_stripped(
    client, chat_worker, fake_http, ticket_chat
):
    """_TEXT_KEYS 우선순위 고정: response_text 가 1순위다.

    한때 reply/text 가 앞서서 러너의 진짜 답이 structured 안에 숨고 화면에는 기본 문구만
    떴다(app/jobs/handlers/chat_message.py 주석). 그 회귀를 여기서 잡는다.
    """
    fake_http.on(
        N8N_URL,
        json_body={
            "response_text": "  Notion 티켓이 생성됐습니다.  ",
            "reply": "이 값이 보이면 우선순위가 뒤집힌 것이다",
            "text": "이것도 아니다",
            "message": "이것도 아니다",
        },
    )
    assert chat_worker.run_once() is True
    assert messages(client, ticket_chat["conversation_id"])[1]["content"] == (
        "Notion 티켓이 생성됐습니다."
    )


def test_empty_2xx_payload_succeeds_with_a_generic_reply(
    client, db, chat_worker, fake_http, ticket_chat
):
    """빈 2xx 도 **성공**으로 끝난다 — 플랫폼은 티켓이 생겼는지 알 방법이 없다.

    이것이 이 경로의 근본 한계다. 플랫폼은 HTTP 상태코드만 본다. n8n 이 200 을 주면서
    Notion 쓰기에 실패했거나, 아무것도 안 했거나, 워크플로가 중간에 끊겨도 사용자에게는
    "요청이 처리되었습니다."가 뜨고 잡은 succeeded 로 닫힌다. 진짜 확인은 사람이
    Notion 을 봐야 한다(파일 하단 체크리스트).
    """
    fake_http.on(N8N_URL, json_body={})
    assert chat_worker.run_once() is True

    assistant = messages(client, ticket_chat["conversation_id"])[1]
    assert assistant["content"] == "요청이 처리되었습니다."
    assert assistant["structured"] == {}
    assert only_job(db).status == "succeeded"


def test_non_object_2xx_payload_is_stringified_into_the_reply(
    client, db, chat_worker, fake_http, ticket_chat
):
    """dict 가 아닌 2xx 본문(배열 등)은 파이썬 repr 로 뭉개져 답변이 된다.

    현재 동작 기록. 러너가 배열을 돌려주면 response_text 는 추출되지 않고 사용자는
    "[{'response_text': ...}]" 를 그대로 본다. 조용히 버려지지는 않는다(그건 지킨다).
    """
    fake_http.on(N8N_URL, json_body=[{"response_text": "티켓 생성됨"}])
    assert chat_worker.run_once() is True

    assistant = messages(client, ticket_chat["conversation_id"])[1]
    assert assistant["content"] == "[{'response_text': '티켓 생성됨'}]"
    assert assistant["structured"] == {"reply": "[{'response_text': '티켓 생성됨'}]"}
    assert only_job(db).status == "succeeded"


# =============================================================================
# 3. 실패 갈래 — 잡 상태와 남는 오류
# =============================================================================


def test_runner_5xx_requeues_with_recorded_error_and_no_reply(
    client, db, chat_worker, fake_http, ticket_chat
):
    fake_http.on(N8N_URL, status=502, json_body={"error": "bad gateway"})
    assert chat_worker.run_once() is True

    job = only_job(db)
    assert job.status == "queued"  # 일시 오류 → 백오프 후 재시도
    assert job.attempt_count == 1
    assert job.last_error == "RuntimeError: n8n 서버 오류 HTTP 502"
    assert job.available_at > job.created_at  # 백오프가 실제로 걸렸다
    assert job.finished_at is None

    items = messages(client, ticket_chat["conversation_id"])
    assert len(items) == 1  # 어시스턴트 답은 아직 없다
    assert items[0]["processing_status"] == "processing"


def test_runner_4xx_fails_permanently_and_records_the_status_code(
    client, db, chat_worker, fake_http, ticket_chat
):
    fake_http.on(N8N_URL, status=422, json_body={"error": "unprocessable"})
    assert chat_worker.run_once() is True

    job = only_job(db)
    assert job.status == "failed"
    assert job.attempt_count == 1  # 재시도하지 않는다
    assert job.last_error == "n8n 요청 거부 HTTP 422"
    assert job.finished_at is not None

    items = messages(client, ticket_chat["conversation_id"])
    assert items[0]["processing_status"] == "failed"
    assert items[0]["error_code"] == "assistant_rejected"
    assert items[1]["structured"] == {"error_notice": True}
    assert "동일하게 실패" in items[1]["content"]  # "그냥 재시도하세요"라고 하지 않는다


def test_timeout_requeues_then_fails_with_timeout_bucket(
    client, db, chat_worker, fake_http, fake_clock, ticket_chat
):
    fake_http.on_timeout(N8N_URL)
    assert chat_worker.run_once() is True
    assert only_job(db).last_error == "RuntimeError: n8n 응답 시간 초과"
    assert only_job(db).status == "queued"

    for _ in range(2):
        fake_clock.advance(60)
        assert chat_worker.run_once() is True

    job = only_job(db)
    assert (job.status, job.attempt_count) == ("failed", 3)
    assert job.last_error == "RuntimeError: n8n 응답 시간 초과"
    assert len(fake_http.requests) == 3  # 시도마다 실제로 다시 보냈다

    items = messages(client, ticket_chat["conversation_id"])
    assert items[0]["error_code"] == "assistant_timeout"
    assert "다시 시도" in items[1]["content"]


def test_connection_error_requeues_with_its_own_message(db, chat_worker, fake_http, ticket_chat):
    fake_http.on_connect_error(N8N_URL)
    assert chat_worker.run_once() is True

    job = only_job(db)
    assert job.status == "queued"
    assert job.last_error == "RuntimeError: n8n 연결 실패"


def test_malformed_json_2xx_is_transient_and_recorded(db, chat_worker, fake_http, ticket_chat):
    fake_http.on_invalid_json(N8N_URL)
    assert chat_worker.run_once() is True

    job = only_job(db)
    assert job.status == "queued"
    assert job.last_error == "RuntimeError: n8n 응답이 올바른 JSON이 아닙니다"


# =============================================================================
# 4. 재전송 / 중복 — 티켓이 두 번 만들어지는가
# =============================================================================


def test_double_submit_of_the_same_client_message_id_posts_once(
    client, db, chat_worker, fake_http, ticket_chat
):
    """브라우저 더블클릭/새로고침 재전송: 잡도 아웃바운드도 정확히 1건.

    보호 지점은 플랫폼이다 — Message.message_id UNIQUE + Job.idempotency_key
    ("chatmsg:<client_message_id>"). 두 번째 POST 는 원본 메시지/잡을 그대로 돌려준다.
    """
    second = ticket_chat["send"](DRAFT_TEXT, DRAFT_MSG_ID)
    assert second.status_code == 202
    assert second.json()["job_id"] == ticket_chat["job_id"]
    assert second.json()["message"]["id"] == ticket_chat["message_db_id"]

    fake_http.on(N8N_URL, json_body=created_response(ticket_chat["conversation_id"]))
    assert chat_worker.run_once() is True
    assert chat_worker.run_once() is False  # 두 번째 잡은 애초에 없다

    assert len(fake_http.requests) == 1
    assert len(jobs_for(db, DRAFT_MSG_ID)) == 1
    assert len(messages(client, ticket_chat["conversation_id"])) == 2  # 사용자 1 + 답 1


def test_worker_retry_after_timeout_reposts_an_identical_body(
    client, db, chat_worker, fake_http, fake_clock, ticket_chat
):
    """타임아웃 후 워커 재시도는 **완전히 동일한 본문**을 다시 보낸다.

    미보호(기록만 함): n8n 이 Notion 쓰기를 끝낸 뒤 응답만 유실되면, 플랫폼은 그 사실을
    알 수 없고 재전송을 막지도 않는다. 중복 방지는 전적으로 원격(n8n)에 위임돼 있다 —
    docs/n8n/…v7.json '요청 전처리'가 `identity|conversation_id|message_id` 를 열쇠로
    processedMessages 를 뒤진다. 주의: n8n 은 플랫폼이 보내는 **idempotency_key 필드를
    읽지 않는다**(그 파일 전체에 그 이름이 없다). 그래도 계약상 두 요청의 message_id 와
    idempotency_key 가 동일해야 원격이 재전송임을 알아볼 수 있으므로 여기서 못 박는다.
    """
    fake_http.on_timeout(N8N_URL)
    assert chat_worker.run_once() is True  # 시도 1: 쓰기는 됐을 수도, 안 됐을 수도 있다

    fake_clock.advance(60)
    # n8n 은 이미 티켓을 만들어 두고 저장된 응답을 duplicate 로 돌려준다.
    fake_http.on(
        N8N_URL, json_body=created_response(ticket_chat["conversation_id"], message_id=DRAFT_MSG_ID, duplicate=True)
    )
    assert chat_worker.run_once() is True

    assert len(fake_http.requests) == 2, "플랫폼은 재전송을 스스로 막지 않는다"
    first, second = sent_body(fake_http, 0), sent_body(fake_http, 1)
    assert first == second  # 완전히 동일 — 원격이 구분할 근거는 message_id 뿐
    assert second["message_id"] == DRAFT_MSG_ID
    assert second["idempotency_key"] == f"chatmsg:{DRAFT_MSG_ID}"

    # 사용자에게는 티켓 생성 답이 **한 번만** 보인다(시도 1 은 답을 남기지 않았다).
    items = messages(client, ticket_chat["conversation_id"])
    assert [m["role"] for m in items] == ["user", "assistant"]
    assert items[1]["structured"]["duplicate"] is True
    assert items[1]["structured"]["ticket"]["id"] == NOTION_PAGE_ID
    assert items[1]["message_id"] == f"a-{DRAFT_MSG_ID}-2"  # 시도 2 가 답을 만들었다
    assert only_job(db).status == "succeeded"


def test_user_retry_after_failure_reuses_the_same_remote_idempotency_key(
    client, db, chat_worker, fake_http, fake_clock, ticket_chat
):
    """사용자 '다시 시도'는 **잡 키만** 새로 만들고, 원격에 보내는 키는 그대로다.

    잡 레벨 idempotency_key 는 "chatmsg:<mid>:retry:<타임스탬프>"로 새로 발급되지만
    (app/chat/service.py:retry_message), 본문의 idempotency_key/message_id 는 메시지에서
    파생되므로 첫 요청과 동일하다. 즉 n8n 관점에서 사용자 재시도와 워커 재시도는 구분되지
    않는다. n8n 이 이미 티켓을 만들어 뒀다면 재시도는 저장된 응답을 되돌려줄 뿐 두 번째
    티켓을 만들지 않는다(위 테스트). 반대로 정말 아무것도 안 만들었다면 그때 만든다.
    현재 동작 기록 — 고치지 않는다.
    """
    fake_http.on(N8N_URL, status=400, json_body={"error": "bad request"})
    assert chat_worker.run_once() is True
    assert messages(client, ticket_chat["conversation_id"])[0]["processing_status"] == "failed"

    fake_clock.advance(30)
    fake_http.on(N8N_URL, json_body=created_response(ticket_chat["conversation_id"], message_id=DRAFT_MSG_ID))
    retried = client.post(
        f"/api/messages/{ticket_chat['message_db_id']}/retry",
        json={},
        headers={"X-CSRF-Token": ticket_chat["csrf"]},
    )
    assert retried.status_code == 200
    assert chat_worker.run_once() is True

    rows = jobs_for(db, DRAFT_MSG_ID)
    assert len(rows) == 2
    assert rows[0].idempotency_key == f"chatmsg:{DRAFT_MSG_ID}"
    assert rows[1].idempotency_key.startswith(f"chatmsg:{DRAFT_MSG_ID}:retry:")
    assert rows[0].idempotency_key != rows[1].idempotency_key
    assert [j.status for j in rows] == ["failed", "succeeded"]

    # 그런데 원격이 보는 값은 두 번 다 같다.
    assert len(fake_http.requests) == 2
    assert sent_body(fake_http, 0)["idempotency_key"] == sent_body(fake_http, 1)["idempotency_key"]
    assert sent_body(fake_http, 0)["message_id"] == sent_body(fake_http, 1)["message_id"]

    items = messages(client, ticket_chat["conversation_id"])
    assert items[0]["processing_status"] == "done"
    assert items[-1]["structured"]["ticket"]["url"] == NOTION_URL
    # 실패 안내 말풍선은 재시도 성공과 함께 사라진다(사실과 반대되는 상태를 남기지 않는다).
    assert not [m for m in items if (m["structured"] or {}).get("error_notice")]


# =============================================================================
# 사람이 직접 해야 하는 확인 — 이 파일로는 절대 증명되지 않는 것
# =============================================================================
#
# 위 테스트는 **플랫폼이 보내는 요청과 받은 응답을 다루는 방식**만 고정한다. 아래는 가짜
# 트랜스포트로는 원리상 증명할 수 없고, 살아 있는 서버 + 진짜 n8n + 진짜 Notion 자격증명이
# 있어야만 확인된다. WORK_PLAN_INDEX §7 의 "[부분] … 실제 채팅 end-to-end 미검증"은 아래를
# 사람이 수행하기 전까지 그대로 [부분]이다.
#
#   1. n8n 워크플로가 켜져 있고 웹훅 경로가 살아 있는가:
#      운영 서버에서 `curl -sS -X POST http://127.0.0.1:5678/webhook/clovirone-work-assistant
#      -H 'Content-Type: application/json' -d '{"message":"도움말","message_id":"probe-1",
#      "conversation_id":"probe","requester":{"email":"<본인>","name":"<본인>"}}'`
#      → 200 과 response_text 가 오는지.
#   2. 진짜 브라우저에서 로그인 → 새 대화 → "…티켓 만들어줘" → 초안(CREATE_PREVIEW)이
#      뜨는지. 뜨지 않으면 러너/LLM 단계에서 끊긴 것이다.
#   3. "등록해줘"로 승인 → 답변에 'Notion 티켓이 생성됐습니다' + 링크가 오는지.
#   4. **그 링크를 열어 Notion 작업 DB 에 페이지가 실제로 생겼는지 눈으로 확인** —
#      제목/담당자/마감일/우선순위가 요청한 값과 같은지. (플랫폼은 이것을 확인하지 않는다.
#      200 만 오면 성공으로 닫는다 — test_empty_2xx_payload_succeeds_with_a_generic_reply.)
#   5. 같은 대화에서 이어서 "방금 만든 티켓 상태 진행으로 바꿔줘" → 러너가 방금 그 티켓을
#      기억하는지(대화 컨텍스트가 실제로 이어지는지).
#   6. 중복 방지 실측: 같은 승인 메시지를 강제로 두 번 보내(예: 승인 직후 서버 재시작으로
#      잡 재시도 유발) Notion 에 티켓이 **1개만** 생겼는지 확인. 이 방어는 플랫폼이 아니라
#      n8n staticData(processedMessages)에 있고, n8n 재시작 시 사라질 수 있다.
#   7. 서버 로그(app.worker / app.handlers.chat)와 jobs 테이블에서 그 job 이 succeeded 로
#      끝났는지, last_error 가 비어 있는지 대조.
