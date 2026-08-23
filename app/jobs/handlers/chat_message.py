"""chat_message job handler — **답을 제품 안에서 만든다** (S11 · D-202).

## 무엇이 바뀌었나

예전에는 이 핸들러가 n8n 웹훅(`127.0.0.1:5678`)을 부르고, n8n 이 Notion 작업 DB **전량**을
읽어 러너(`127.0.0.1:8789`)에 넘겼다. 러너는 그 목록을 그대로 모델 프롬프트에 실었고,
**요청자는 대명사 해석에만 쓰이고 필터로는 쓰이지 않았다.** 즉 화면에서 볼 수 없는 문서가
답변의 근거가 될 수 있었다.

이제는 `app/ai/retrieval` 이 답을 만든다. 그 경로는 `effective_visibility_clause` 가 만든
후보 집합 **안에서만** 검색하므로, 사용자가 볼 수 없는 문서는 Context 에 들어갈 자리가
없다(D-256). 권한 판정이 `LIMIT` 앞에 있다는 뜻이고, 그것이 옛 경로를 걷어낸 이유다 —
「기능이 겹친다」가 아니라 **「하나는 권한을 안 본다」**다.

## 생성으로 가는 문은 하나다

`app/ai/retrieval/answer.py::answer()` 를 부른다. AI 작업공간(`/ai`)이 부르는 것과 같은
함수이고, 그래서 두 화면의 답이 같은 권한·같은 프롬프트 경계·같은 인용 규약을 지난다.
여기서 `Gateway.generate()` 를 직접 부르지 않는다 — 부르는 순간 방어가 한쪽에만 걸리는
두 번째 경로가 생긴다.

## 실패는 세 종류이고 셋을 구별한다

- **답했다**: 인용과 함께 저장하고 쿼터를 센다.
- **근거가 없다**: 그것도 답이다. 실패로 표시하지 않는다 — 다시 눌러도 같은 결과다.
- **생성이 막혔다**(모델 없음·시간 초과·다른 작업 중): 인용은 그대로 내보내고 왜인지
  말한다. 사용자 메시지는 실패로 남겨 「다시 시도」를 살린다.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.gateway import contract
from app.ai.retrieval import answer as answer_mod
from app.conversations.models import (
    PROC_DONE,
    PROC_FAILED,
    PROC_PROCESSING,
    ROLE_ASSISTANT_MSG,
    Conversation,
    Message,
)
from app.jobs.exceptions import PermanentJobError
from app.jobs.models import Job
from app.jobs.worker import WorkerContext, parse_payload
from app.users.models import User

logger = logging.getLogger("app.handlers.chat")

#: 근거를 한 건도 못 찾았을 때. 「실패」가 아니라 **답**이다 — 다시 눌러도 같은 결과이므로
#: 재시도를 권하지 않는다.
NO_EVIDENCE_TEXT = (
    "질문에 답할 근거를 사내 문서에서 찾지 못했습니다. "
    "다른 낱말로 다시 물어보시거나, 찾는 내용이 담긴 문서를 먼저 등록해 주세요."
)

#: 이미지를 읽는 어댑터가 없다. 조용히 무시하면 사용자는 그림을 보고 답한 줄 안다.
ATTACHMENT_NOTICE = "첨부한 이미지는 읽지 못했습니다. 필요한 내용은 글로 적어 주세요."


def _requester(db: Session, conversation: Conversation) -> User:
    """권한 판정의 주체. **대화 주인이지 잡을 넣은 프로세스가 아니다.**

    `answer()` 가 이 사람의 가시성으로 후보 집합을 만든다. 여기서 사람을 못 찾으면
    답을 만들 수 없다 — 필터 없이 부르는 갈래를 두지 않는다.
    """
    user = db.get(User, conversation.user_id)
    if user is None:
        raise PermanentJobError("대화 주인을 찾을 수 없어 권한을 판정할 수 없습니다.")
    return user


def _gateway(ctx: WorkerContext):
    """프로세스에 하나뿐인 Gateway (`app/worker_main.py`).

    잡마다 만들면 그때마다 새 Adapter 가 생기고, 임베딩 Adapter 는 첫 호출에 ONNX
    세션을 만든다 — S1 실측 2.3초다. `app/ai/router.py::_gateway` 와 같은 폴백을 둔다.
    """
    gateway = (ctx.extras or {}).get("ai_gateway")
    if gateway is None:
        from app.ai.gateway.registry import build_gateway

        gateway = build_gateway(ctx.settings, outbound=ctx.outbound_client)
        if ctx.extras is not None:
            ctx.extras["ai_gateway"] = gateway
    return gateway


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


def _load_message(db: Session, job: Job, payload: dict) -> Message:
    # UB-23: message_id는 대화 단위로만 유일하다(migration 0054) — conversation_id로
    # 좁힌다(on_failure와 같은 이유).
    message = db.execute(
        select(Message).where(
            Message.conversation_id == job.conversation_id,
            Message.message_id == payload.get("message_id", ""),
        )
    ).scalar_one_or_none()
    if message is None:
        raise PermanentJobError("대상 메시지가 존재하지 않습니다.")
    return message


def _has_attachments(payload: dict) -> bool:
    attachments = payload.get("attachments")
    return isinstance(attachments, list) and any(
        isinstance(a, dict) and not a.get("stripped") for a in attachments
    )


def _reply(ans: answer_mod.Answer, *, had_attachments: bool) -> tuple[str, dict, bool]:
    """(화면에 실을 글, 저장할 구조, 답을 냈는가).

    인용은 **어느 갈래에서도** 함께 나간다. 생성이 막혀도 근거 문서로는 갈 수 있어야
    한다(S10 Exit) — 그 성질을 채팅에서도 그대로 지킨다.
    """
    stored = ans.as_dict()
    if had_attachments:
        stored = {**stored, "attachments_ignored": True}

    if ans.ok:
        text = ans.text
        if had_attachments:
            text = f"{text}\n\n{ATTACHMENT_NOTICE}"
        return text, stored, True

    if ans.retrieval.empty:
        # 근거가 0 이면 모델을 아예 안 불렀다(answer.py). 빈 Context 로 부르면 모델은
        # 무언가를 지어내고 그 문장에는 인용이 하나도 안 붙는다.
        text = NO_EVIDENCE_TEXT
        if had_attachments:
            text = f"{text}\n\n{ATTACHMENT_NOTICE}"
        return text, {**stored, "no_evidence": True}, False

    # 근거는 찾았는데 문장을 못 만들었다. 왜인지 말한다 — 「안 됩니다」만 남기면 운영자가
    # 고칠 수 있는 상태(모델 파일을 안 넣었다)와 못 고치는 상태를 구별하지 못한다.
    notice = ans.notice or contract.FALLBACK_NOTICE
    text = (
        f"{notice} 찾은 근거 {len(ans.retrieval.citations)}건은 아래에 그대로 두었으니 "
        "문서를 직접 열어 확인해 주세요."
    )
    return text, {**stored, "error_notice": True}, False


def handle_chat_message(db: Session, job: Job, ctx: WorkerContext) -> None:
    payload = parse_payload(job)
    requester = payload.get("requester") or {}
    if not requester.get("email"):
        raise PermanentJobError("requester가 없는 payload: 위조 또는 손상")

    message = _load_message(db, job, payload)
    message.processing_status = PROC_PROCESSING

    conversation = db.get(Conversation, message.conversation_id)
    if conversation is None:
        raise PermanentJobError("대상 대화가 존재하지 않습니다.")
    user = _requester(db, conversation)

    db.flush()

    ans = answer_mod.answer(
        db, user, raw_query=payload.get("content"), gateway=_gateway(ctx)
    )
    text, stored, answered = _reply(ans, had_attachments=_has_attachments(payload))

    # '-fail-{job.id}' ID는 on_failure의 안내 메시지와 같은 규약이다 — retry_message가 그
    # 패턴으로 옛 안내를 지운다(재시도가 성공해도 '답을 못 받았다' 안내가 새 답변 옆에 그대로
    # 남는 걸 막는다).
    #
    # answered일 때도 **job.id**를 쓴다(attempt_count가 아니다) — TEST SERVER 실사용
    # (재생성 버튼) 실측으로 발견: attempt_count는 "이 잡 자신의" 재시도 횟수일 뿐이라,
    # regenerate_message/retry_message가 만드는 **새 Job**은 매번 attempt_count=1부터
    # 다시 센다. job.id(UUID)는 매 Job마다 전역적으로 유일해 그 충돌이 구조적으로 불가능하다.
    #
    # 「근거가 없다」는 답이므로 `-fail-` 을 안 붙인다. 그 접미사는 retry_message 가
    # 지우는 대상이고, 지워도 되는 것은 안내뿐이다.
    failed_suffix = not answered and not stored.get("no_evidence")
    assistant = Message(
        conversation_id=conversation.id,
        message_id=(
            f"a-{message.message_id}-fail-{job.id}"
            if failed_suffix
            else f"a-{message.message_id}-{job.id}"
        ),
        role=ROLE_ASSISTANT_MSG,
        content=text,
        structured_payload_json=json.dumps(stored, ensure_ascii=False),
        processing_status=PROC_DONE,
    )
    db.add(assistant)

    # 「근거가 없다」로 끝난 메시지는 실패가 아니다 — 같은 질문을 다시 넣어도 같은 답이고,
    # 「다시 시도」를 켜 두면 사용자를 헛수고시킨다. 생성이 막힌 경우만 실패로 남긴다.
    if failed_suffix:
        message.processing_status = PROC_FAILED
        message.error_code = f"assistant_{ans.status}"
    else:
        message.processing_status = PROC_DONE
        message.error_code = None
    conversation.updated_at = ctx.clock.now()

    # 쿼터는 **모델이 실제로 답한 경우만** 센다. 검색은 서버 CPU 이지 구독 호출이 아니고
    # (S10), 우리 쪽 실패를 사용자에게 청구하지 않는다.
    if answered:
        from app.quotas.service import KIND_CHAT_MESSAGE, record_call

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
    # UB-23: message_id는 이제 대화 단위로만 유일하다(migration 0054) — job 자신이 이미
    # conversation_id를 들고 있으니(enqueue 시점에 저장) 조회도 같은 범위로 좁힌다.
    message = db.execute(
        select(Message).where(
            Message.conversation_id == job.conversation_id,
            Message.message_id == payload.get("message_id", ""),
        )
    ).scalar_one_or_none()
    if message is None:
        strip_attachment_bytes(job, payload)
        db.flush()
        return
    message.processing_status = PROC_FAILED
    message.error_code = "assistant_error"
    db.add(Message(
        conversation_id=message.conversation_id,
        # job.id in the id: a retried-then-failed message would collide on a fixed
        # suffix (unique constraint) and roll back the whole failure transaction,
        # freezing the message at '처리 중' forever.
        message_id=f"a-{message.message_id}-fail-{job.id}",
        role=ROLE_ASSISTANT_MSG,
        content=(
            "답변을 만드는 중에 문제가 생겨 요청을 끝내지 못했습니다. '다시 시도' 버튼을 "
            "누르면 같은 내용으로 다시 처리합니다. 계속 실패하면 관리자에게 알려주세요."
        ),
        structured_payload_json=json.dumps({"error_notice": True}, ensure_ascii=False),
        processing_status=PROC_DONE,
    ))
    strip_attachment_bytes(job, payload)  # terminal path — no bytes at rest
    db.flush()
    logger.warning("chat message %s marked failed: %s", message.message_id, error)


handle_chat_message.on_failure = on_failure
