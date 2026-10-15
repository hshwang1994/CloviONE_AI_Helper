"""chat_message job handler — AI 도우미 한 차례 (D-535 · D-537 · D-538).

## 무엇이 바뀌었나

예전(S11)에는 이 핸들러가 문서 조각만 찾아 그 결과가 0건이면 모델을 부르지 않고 「근거를 찾지 못했다」를 답으로 저장했다.
연결이 「정상」이어도 자연어 질문은 낱말 AND 검색에서 거의 0건이라 채팅이 답을 못 했다. 이제 한 차례는 **도구를 쓰는
대화**다: 일반 질문은 모델이 바로 답하고, 업무 질문은 대화 주인의 권한으로 도는 읽기 도구(티켓 · 프로젝트 · 결재 · 문서 ·
사람)로 실제 데이터를 읽어 답한다(`app/ai/assistant/`). 「찾지 못했다」는 도구가 0건을 돌려준 정상 답이고, 「AI 를 쓸 수
없다」는 요청 자체가 409 다(채팅 라우터) - 두 상태가 섞이지 않는다.

## 순서

  1. 대화 주인이 아직 활성이고 `AI_USE` 를 가졌는가 - 아니면 안내 답을 남기고 끝낸다(제공자를 부르지 않는다)
  2. 사용자 메시지를 「처리 중」으로 **커밋한다** - 화면이 보고, 제공자 호출 내내 메시지 행을 잠그지 않는다
     (`app/jobs/worker.py` 의 「느린 바깥 호출 앞에서 커밋한다」 규율)
  3. 한 차례를 돌린다(`turn.run` → `AiRuntime.converse`). 도구 사이마다 진행 문구를 적고 커밋한다
  4. 도우미 메시지(글 + 구조)를 남기고 사용자 메시지를 완료 · 실패로 바꾼다

한도는 런타임의 사용 기록 한 행이 센다(D-537) - 성공한 차례만 한 칸이다. 여기서 따로 적지 않는다.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.gateway import contract
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

#: 이미지를 읽는 어댑터가 없다. 조용히 무시하면 사용자는 그림을 보고 답한 줄 안다.
ATTACHMENT_NOTICE = "첨부한 이미지는 읽지 못했습니다. 필요한 내용은 글로 적어 주세요."

#: 글 없이 이미지만 보냈다.
EMPTY_QUESTION_TEXT = "질문을 글로 적어 주세요."

#: 넣은 뒤 실행 전에 AI 를 쓸 수 없게 된 사람(비활성, 보관, AI 사용 권한 회수).
NO_PERMISSION_TEXT = "AI 도우미를 쓸 수 있는 권한이 없어 답하지 않았습니다. 관리자에게 문의하세요."

#: 차례가 막혔을 때 찾은 자료가 있으면 덧붙이는 문장.
SOURCES_KEPT = "찾은 자료는 아래에 그대로 두었으니 직접 열어 확인해 주세요."


def _requester(db: Session, conversation: Conversation) -> User:
    """권한 판정의 주체. **대화 주인이지 잡을 넣은 프로세스가 아니다.**

    도구가 이 사람의 권한으로 읽는다. 여기서 사람을 못 찾으면 답을 만들 수 없다 — 권한 없이 부르는 갈래를 두지 않는다.
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


def _can_use(db: Session, owner: User) -> bool:
    """대화 주인이 지금도 AI 도우미를 쓸 수 있는가 - 넣은 뒤 실행 전에 권한을 잃었을 수 있다(D-538)."""
    from app.authz import permissions as perms
    from app.authz.service import has_permission

    if not owner.active or owner.archived_at is not None:
        return False
    return has_permission(db, owner, perms.AI_USE)


def _session_factory(db: Session, ctx: WorkerContext):
    """도구의 READ ONLY 세션을 여는 공장. 워커는 `extras["session_factory"]` 를 두고, 없으면 같은 연결로 만든다."""
    factory = (ctx.extras or {}).get("session_factory")
    if factory is not None:
        return factory
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(bind=db.get_bind(), expire_on_commit=False)


def _texts(reply, *, had_attachments: bool) -> tuple[str, bool]:
    """(화면에 실을 글, 실패인가). 막힌 차례도 찾은 자료가 있으면 출처로 남긴다."""
    outcome = reply.outcome
    if outcome.ok:
        text = reply.text
    elif outcome.error_code == "empty_question":
        return (ATTACHMENT_NOTICE if had_attachments else EMPTY_QUESTION_TEXT), False
    else:
        notice = outcome.notice or contract.FALLBACK_NOTICE
        text = f"{notice} {SOURCES_KEPT}" if reply.structured.get("sources") else notice
    if had_attachments:
        text = f"{text}\n\n{ATTACHMENT_NOTICE}"
    return text, not outcome.ok


def _finish(db: Session, job: Job, ctx: WorkerContext, payload: dict, *, conversation: Conversation,
            message: Message, text: str, stored: dict, failed: bool, error_code: str | None) -> None:
    # '-fail-{job.id}' ID는 on_failure의 안내 메시지와 같은 규약이다 — retry_message가 그 패턴으로 옛 안내를 지운다.
    # 답에도 **job.id**를 쓴다(attempt_count가 아니다) — regenerate_message/retry_message가 만드는 새 Job은
    # attempt_count=1부터 다시 세서 충돌한다(TEST SERVER 재생성 실측). job.id 는 전역에서 유일하다.
    db.add(Message(
        conversation_id=conversation.id,
        message_id=f"a-{message.message_id}-fail-{job.id}" if failed else f"a-{message.message_id}-{job.id}",
        role=ROLE_ASSISTANT_MSG,
        content=text,
        structured_payload_json=json.dumps({**stored, **({"error_notice": True} if failed else {})},
                                           ensure_ascii=False),
        processing_status=PROC_DONE,
    ))
    message.processing_status = PROC_FAILED if failed else PROC_DONE
    message.error_code = error_code if failed else None
    conversation.updated_at = ctx.clock.now()
    strip_attachment_bytes(job, payload)  # terminal path — no bytes at rest
    db.flush()


def _conversation_alive(db: Session, conversation_id: str) -> bool:
    """대화가 아직 있는가 — 답을 만드는 동안 사람이 대화를 지웠을 수 있다(다른 트랜잭션의 커밋을 본다)."""
    return db.execute(select(Conversation.id).where(Conversation.id == conversation_id)).first() is not None


def handle_chat_message(db: Session, job: Job, ctx: WorkerContext) -> None:
    payload = parse_payload(job)
    if payload.get("purged"):
        # 대화를 지우며 잡의 내용을 걷었다(`app/chat/service.py::purge_conversation_job_payloads`) — 할 일이 없다.
        # 실패로 올리면 지운 사람에게 「요청 처리에 실패했습니다」 알림이 간다.
        logger.info("chat job %s: 지운 대화의 잡이라 건너뜀", job.id)
        return
    requester = payload.get("requester") or {}
    if not requester.get("email"):
        raise PermanentJobError("requester가 없는 payload: 위조 또는 손상")

    message = _load_message(db, job, payload)
    conversation = db.get(Conversation, message.conversation_id)
    if conversation is None:
        raise PermanentJobError("대상 대화가 존재하지 않습니다.")
    owner = _requester(db, conversation)
    had_attachments = _has_attachments(payload)

    if not _can_use(db, owner):
        _finish(db, job, ctx, payload, conversation=conversation, message=message, text=NO_PERMISSION_TEXT,
                stored={"kind": "assistant", "status": "no_permission"}, failed=True,
                error_code="assistant_no_permission")
        return

    from app.ai.assistant import catalog
    from app.ai.assistant import turn as turn_mod
    from app.ai.runtime import runtime_for_worker
    from app.home import service as home_service

    # 처리 중을 **커밋한다** - 화면이 보고, 제공자를 부르는 동안 이 행을 잠그지 않는다.
    message.processing_status = PROC_PROCESSING
    progress = turn_mod.progress_writer(db, message, clock=ctx.clock)
    progress("질문을 받았습니다.")

    now = ctx.clock.now()
    env = catalog.ToolEnv(
        session_factory=_session_factory(db, ctx), user_id=owner.id, settings=ctx.settings,
        outbound=ctx.outbound_client, gateway=_gateway(ctx), settings_cache=(ctx.extras or {}).get("settings_cache"),
        now=now,
    )
    reply = turn_mod.run(
        db, owner=owner, user_message=message, conversation_id=conversation.id, runtime=runtime_for_worker(ctx),
        env=env, screen_context=payload.get("screen_context"), today=home_service.local_today(ctx.settings, now),
        job_id=job.id, progress=progress,
    )
    if not _conversation_alive(db, conversation.id):
        logger.info("chat job %s: 답을 만드는 동안 대화가 지워져 조용히 끝냄", job.id)
        strip_attachment_bytes(job, payload)
        db.flush()
        return
    text, failed = _texts(reply, had_attachments=had_attachments)
    stored = dict(reply.structured)
    if had_attachments:
        stored["attachments_ignored"] = True
    _finish(db, job, ctx, payload, conversation=conversation, message=message, text=text, stored=stored,
            failed=failed, error_code=f"assistant_{reply.outcome.status}")


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
