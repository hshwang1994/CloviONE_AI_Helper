"""chat_message job handler — calls the n8n work-assistant webhook (spec §22).

Transient failures (timeout, 5xx, connection) are retried by the queue;
4xx and malformed payloads are permanent. When the job finally fails,
``on_failure`` marks the user message failed so the UI can offer retry.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.conversations.models import (
    PROC_DONE,
    PROC_FAILED,
    PROC_PROCESSING,
    ROLE_ASSISTANT_MSG,
    Conversation,
    Message,
)
from app.core.allowlist import URLNotAllowedError
from app.core.http_client import is_timeout_error, is_transport_error
from app.jobs.exceptions import PermanentJobError
from app.jobs.models import Job
from app.jobs.worker import WorkerContext, parse_payload
from app.workflows.models import Workflow

logger = logging.getLogger("app.handlers.chat")

# Name of the seeded Workflow registry row for this handler (must match
# app/workflows/service.py:seed_known_workflows). The admin console's
# Workflows screen lets an admin edit webhook_url and enable/disable this row —
# if this handler ignored it and always called settings.n8n_work_assistant_url
# directly, every control on that screen for this row would be a dead
# affordance (edits/disables with zero effect on real chat behavior).
CHAT_WORKFLOW_NAME = "ClovirONE AI 업무 도우미"


class ChatWorkflowMisconfiguredError(PermanentJobError):
    """워크플로 설정이 잘못돼 요청이 의미 있게 전달될 수 없는 상태.

    재시도해도 같은 결과라 영구 실패로 다룬다 — 사용자에게는 관리자가 무엇을 고쳐야 하는지
    그대로 보여준다(원인을 모른 채 '실패'만 보는 것보다 낫다).
    """


class ChatWorkflowDisabledError(PermanentJobError):
    pass


def _resolve_chat_endpoint(db: Session, settings) -> tuple[str, str]:
    """Resolve the webhook URL/method for chat, honoring the Workflow registry
    row when it has been seeded. Falls back to the static settings URL only
    when the row doesn't exist yet (fresh install before seeding, or tests
    that don't seed the registry) — never when it exists but is disabled."""
    workflow = db.execute(
        select(Workflow).where(Workflow.name == CHAT_WORKFLOW_NAME)
    ).scalar_one_or_none()
    if workflow is None:
        return settings.n8n_work_assistant_url, "POST"
    if not workflow.enabled:
        raise ChatWorkflowDisabledError(
            "채팅 워크플로가 비활성화되어 있습니다. 관리자 콘솔의 Workflow 레지스트리에서 "
            f"'{CHAT_WORKFLOW_NAME}'를 활성화해 주세요."
        )
    # 이 워크플로는 본문(요청자·메시지·대화 id)이 있어야 동작한다. 그런데 관리자 콘솔은
    # http_method로 GET도 고를 수 있고, GET이면 아래에서 json 본문이 통째로 버려졌다 —
    # 러너는 빈 요청을 받고, 그럼에도 2xx를 돌려주면 작업은 '성공'으로 끝나고 사용자는
    # 엉뚱한 답을 받는다. 조용한 실패라 아무도 원인을 못 찾는다. 여기서 크게 실패시킨다.
    method = (workflow.http_method or "").upper()
    if method != "POST":
        raise ChatWorkflowMisconfiguredError(
            f"채팅 워크플로 '{CHAT_WORKFLOW_NAME}'의 HTTP 메서드가 {method or '(없음)'}입니다. "
            "이 워크플로는 요청 본문이 필요하므로 POST여야 합니다. 관리자 콘솔 > 업무 자동화 흐름에서 "
            "메서드를 POST로 바꿔 주세요."
        )
    return workflow.webhook_url, method


# Keys the assistant/n8n side may use for the display text, in priority order.
# `response_text` is the runner/n8n canonical answer field (must come first — else
# every reply fell back to the generic default and the real answer stayed hidden
# in the structured payload).
_TEXT_KEYS = ("response_text", "reply", "text", "message", "output", "answer", "result")


def _extract_text(data: dict) -> tuple[str, bool]:
    """(표시 텍스트, 실제로 답이 있었는지)를 돌려준다.

    예전에는 답이 하나도 없어도 "요청이 처리되었습니다."를 돌려줬다. 러너가 빈 2xx({})를
    주는 경우 — 워크플로가 중간에 끊겼거나 조건 분기에서 아무것도 안 만든 경우 — 사용자에게는
    성공처럼 보이고 작업도 succeeded로 끝나서, 티켓이 실제로 만들어졌는지 아무도 알 수 없었다.
    이제 '답이 없었다'는 사실을 호출측이 알 수 있게 함께 돌려준다.
    """
    for key in _TEXT_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip(), True
    return ("요청은 전달됐지만 도우미가 답을 돌려주지 않았습니다. "
            "잠시 후 다시 시도하거나, 계속되면 관리자에게 알려 주세요."), False


def strip_attachment_bytes(job: Job, payload: dict) -> None:
    """Purge image bytes from the stored job payload, keeping name stubs only.

    Must run on EVERY terminal path (success, safe-refusal, final failure) — the
    platform never keeps image bytes at rest (사용자 결정: 서버 미보관, §13 확장).
    Transient retries are unaffected: the queue re-reads the untouched payload
    until the job reaches a terminal state.
    """
    attachments = payload.get("attachments")
    if not isinstance(attachments, list) or not attachments:
        return
    if all(isinstance(a, dict) and a.get("stripped") for a in attachments):
        return
    stripped = {
        **payload,
        "attachments": [
            {
                "filename": a.get("filename", ""),
                "media_type": a.get("media_type", ""),
                "stripped": True,
            }
            for a in attachments
            if isinstance(a, dict)
        ],
    }
    job.payload_json = json.dumps(stripped, ensure_ascii=False)


def _load_message(db: Session, payload: dict) -> Message:
    message = db.execute(
        select(Message).where(Message.message_id == payload.get("message_id", ""))
    ).scalar_one_or_none()
    if message is None:
        raise PermanentJobError("대상 메시지가 존재하지 않습니다.")
    return message


def handle_chat_message(db: Session, job: Job, ctx: WorkerContext) -> None:
    payload = parse_payload(job)
    requester = payload.get("requester") or {}
    if not requester.get("email"):
        raise PermanentJobError("requester가 없는 payload: 위조 또는 손상")

    message = _load_message(db, payload)
    message.processing_status = PROC_PROCESSING
    db.flush()
    db.commit()

    # First-person requests ("내 티켓" 등) are forwarded even for unmapped users —
    # the runner matches the requester by name/email against the live Notion people
    # directory and answers with its own guidance only when it truly cannot identify
    # them. Admin-verified mapping remains an accuracy booster, not a gate.
    # (The old platform-side refusal blocked users the runner could resolve fine.)

    settings = ctx.settings
    request_body = {
        "requester": requester,
        "message": payload["content"],
        # Fall back to the platform conversation UUID on the first message — a None
        # here made n8n coalesce EVERY conversation into one shared bucket
        # ('powershell-local'), bleeding runner context/image notes across
        # conversations and co-locating all users' images in one directory.
        "conversation_id": payload.get("backend_conversation_id")
        or payload.get("conversation_id"),
        "message_id": payload["message_id"],
        # §32.8 스타일 멱등성: the POST carries no idempotency key of its own, so if
        # n8n completes a WRITE (e.g. creates a ticket) but the HTTP response is lost
        # and the job requeues, the retry re-POSTs and n8n performs the write twice.
        # message_id is stable across every retry of the same message (same payload),
        # so n8n can dedupe on it. Mirrors document_generate's idempotency_key.
        #
        # **job.idempotency_key 를 쓰면 안 된다.** 그러면 사용자 재시도마다 값이 달라지는데,
        # 재시도는 오직 '실패한' 메시지에만 열려 있다(chat/service.py:retry_message 가
        # 그 외에는 409). 즉 재시도가 가능한 경우란 "n8n 이 티켓을 만들었는데 응답만
        # 유실됐을 수 있는" 상황이고, 여기서 키가 달라지면 원격은 새 요청으로 보고
        # **두 번째 티켓을 만든다**. 값이 같아야 저장된 응답이 돌아와 티켓이 한 장으로
        # 남는다. tests/integration/test_chat_ticket_routing_contract.py 가 못 박는다.
        "idempotency_key": f"chatmsg:{payload['message_id']}",
    }
    # AI-30(Med): "현재 문맥: X"가 실제로는 아무 데도 전달되지 않던 것을 고치는 자리 —
    # 플랫폼→러너까지는 이제 실려 간다. n8n 워크플로가 이 필드를 러너 호출(POST
    # /v1/assistant/message)로 그대로 넘겨야 마지막 구간이 완성된다(이 저장소가 소유하지
    # 않는 n8n 워크플로 정의 쪽 변경 — docs/RUNNER_HANDOFF.md의 기존 미해결 항목과 같은 종류).
    screen_context = payload.get("screen_context")
    if screen_context:
        request_body = {**request_body, "screen_context": screen_context}
    attachments = payload.get("attachments")
    if isinstance(attachments, list) and attachments:
        request_body = {**request_body, "attachments": attachments}

    webhook_url, http_method = _resolve_chat_endpoint(db, settings)

    try:
        response = ctx.outbound_client.request(
            http_method,
            webhook_url,
            allowlist="workflows",
            json=request_body,   # _resolve_chat_endpoint가 POST를 보장한다
            timeout=float(settings.n8n_timeout_seconds),
        )
    except URLNotAllowedError as exc:
        # allowlist 거부는 설정이 바뀌기 전에는 몇 번을 다시 던져도 같은 결과다. 예전에는
        # 일반 예외로 새어 나가 큐가 3회까지 재시도했다 — 요청이 실제로 나가지는 않으니
        # 위험하진 않지만, 사용자는 그만큼 오래 기다린 뒤에야 실패를 본다.
        raise PermanentJobError(
            f"워크플로 주소가 허용 목록에 없습니다: {exc}. "
            "관리자 콘솔 > 업무 자동화 흐름에서 주소를 확인하거나, 허용 목록에 추가해 주세요."
        ) from exc
    except Exception as exc:
        if is_timeout_error(exc):
            raise RuntimeError("n8n 응답 시간 초과") from exc
        if is_transport_error(exc):
            raise RuntimeError("n8n 연결 실패") from exc
        raise

    if response.status_code >= 500:
        raise RuntimeError(f"n8n 서버 오류 HTTP {response.status_code}")
    if response.status_code >= 400:
        raise PermanentJobError(f"n8n 요청 거부 HTTP {response.status_code}")

    try:
        data = response.json()
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError("n8n 응답이 올바른 JSON이 아닙니다") from exc
    if not isinstance(data, dict):
        data = {"reply": str(data)}

    conversation = db.get(Conversation, message.conversation_id)
    backend_id = data.get("conversation_id")
    if isinstance(backend_id, str) and backend_id:
        conversation.backend_conversation_id = backend_id

    text, answered = _extract_text(data)
    # 답이 없는 2xx는 성공으로 뭉개지 않는다 — structured에 표시해 두면 화면이 다르게 그릴 수
    # 있고, 나중에 '왜 티켓이 안 생겼나'를 로그에서 구분해 셀 수 있다.
    stored = data if answered else {**data, "empty_response": True}
    assistant = Message(
        conversation_id=conversation.id,
        message_id=f"a-{message.message_id}-{job.attempt_count}",
        role=ROLE_ASSISTANT_MSG,
        content=text,
        structured_payload_json=json.dumps(stored, ensure_ascii=False),
        processing_status=PROC_DONE,
    )
    db.add(assistant)
    message.processing_status = PROC_DONE
    message.error_code = None
    conversation.updated_at = ctx.clock.now()

    # 쿼터는 **성공한 호출만** 센다(assistant 쪽과 같은 규약). 큐에 넣을 때 세면 러너가
    # 죽은 날 사용자가 답을 못 받고 상한만 잃고, 재시도 세 번이 한 답변에 세 번 세어진다 —
    # 우리 실패를 사용자에게 청구하는 셈이다.
    from app.quotas.service import KIND_CHAT_MESSAGE, record_call

    from app.users.models import User

    owner = db.get(User, conversation.user_id)
    record_call(
        db, user_id=conversation.user_id,
        # 조직은 사람에게서 읽는다 — `conversations` 에는 org 컬럼이 없다(0024 가 제외).
        # 멀티테넌트에서 사용량 집계가 조직 없이 쌓이면 나중에 되살릴 수가 없다.
        org_id=getattr(owner, "org_id", None),
        kind=KIND_CHAT_MESSAGE, now=ctx.clock.now(),
    )

    strip_attachment_bytes(job, payload)  # terminal path — no bytes at rest
    db.flush()


def on_failure(db: Session, job: Job, ctx: WorkerContext, error: str) -> None:
    """Called by the worker after the job has finally failed — marks the user
    message failed so the browser can restore input and offer retry.

    Retry note: image bytes are needed for a user-initiated retry, so
    ``retry_message`` copies them out of this failed job FIRST and then strips it.
    Bytes left in never-retried failed jobs are swept by the retention job."""
    try:
        payload = parse_payload(job)
    except PermanentJobError:
        return
    message = db.execute(
        select(Message).where(Message.message_id == payload.get("message_id", ""))
    ).scalar_one_or_none()
    if message is None:
        strip_attachment_bytes(job, payload)
        db.flush()
        return
    message.processing_status = PROC_FAILED
    # The '실패' badge alone tells the user nothing — say what happened and what
    # to do next, in the conversation itself (지시서 11장). This previously
    # collapsed every terminal failure (timeout, a permanent 4xx rejection from
    # n8n, an admin-disabled workflow, transient connection/server errors) into
    # the same two-way branch and the same fixed error_code, losing the
    # diagnostic distinction the worker already captured (timeout raises
    # RuntimeError("n8n 응답 시간 초과"); a permanent rejection raises
    # PermanentJobError with "n8n 요청 거부 HTTP …" or the disabled-workflow
    # message; everything else is a transient RuntimeError). Differentiate at
    # least those three buckets in both the stored error_code and the guidance
    # text so a future UI (and anyone reading the DB/audit trail directly) can
    # tell "retrying is pointless without admin action" apart from "just retry".
    err_text = error or ""
    if "시간 초과" in err_text:
        message.error_code = "assistant_timeout"
        guidance = (
            "요청 처리가 제한 시간을 넘겨 완료하지 못했습니다. 잠시 후 '다시 시도' 버튼을 "
            "누르거나 같은 내용을 한 번 더 보내 주세요. 계속 반복되면 관리자에게 알려주세요."
        )
    elif "요청 거부 HTTP" in err_text or "비활성화되어 있습니다" in err_text:
        # Permanent: n8n itself rejected the request (4xx), or an admin disabled
        # the chat workflow. Retrying the identical content will very likely
        # fail the same way — the guidance says so instead of implying retry
        # is a reliable fix.
        message.error_code = "assistant_rejected"
        guidance = (
            "요청이 업무 처리 서버에서 거부되었습니다. 같은 내용으로 다시 시도해도 대부분 "
            "동일하게 실패합니다. 요청 내용을 확인하거나 관리자에게 문의해 주세요."
        )
    else:
        message.error_code = "assistant_error"
        guidance = (
            "업무 처리 서버와의 연결에 문제가 있어 요청을 완료하지 못했습니다. '다시 시도' "
            "버튼을 누르면 같은 내용으로 다시 처리합니다. 계속 실패하면 관리자에게 알려주세요."
        )
    db.add(Message(
        conversation_id=message.conversation_id,
        # job.id in the id: a retried-then-failed message would collide on a fixed
        # suffix (unique constraint) and roll back the whole failure transaction,
        # freezing the message at '처리 중' forever.
        message_id=f"a-{message.message_id}-fail-{job.id}",
        role=ROLE_ASSISTANT_MSG,
        content=guidance,
        structured_payload_json=json.dumps({"error_notice": True}, ensure_ascii=False),
        processing_status=PROC_DONE,
    ))
    db.flush()
    logger.warning("chat message %s marked failed: %s", message.message_id, error)


handle_chat_message.on_failure = on_failure
