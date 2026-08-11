"""Chat service: conversations, messages, and job enqueueing (spec §13, §22).

The requester identity in every job payload is built here from the SERVER
session user — nothing client-supplied is ever trusted (spec §11.2).
"""

from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.conversations.models import (
    PROC_FAILED,
    PROC_PENDING,
    ROLE_USER_MSG,
    Conversation,
    Message,
)
from app.core.config import Settings
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.jobs import repository as jobs_repo
from app.jobs.models import JOB_TYPE_CHAT_MESSAGE
from app.users.models import User

_CLIENT_MESSAGE_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
DEFAULT_TITLE = "새 대화"
AUTO_TITLE_MAX_CHARS = 60


def auto_title(content: str) -> str:
    """AI-55: 첫 메시지를 그대로 60자에서 잘랐더니 잘렸다는 표시가 없어, 같은 문장으로
    시작하는 대화 여러 개가 목록에서 글자 하나 안 틀리고 똑같아 보였다(사용자가 구분할
    유일한 단서가 없어졌다). 잘렸을 때만 말줄임표를 붙인다 — 안 잘렸으면 그대로 둔다."""
    text = content.strip()
    if len(text) <= AUTO_TITLE_MAX_CHARS:
        return text
    return text[: AUTO_TITLE_MAX_CHARS - 1].rstrip() + "…"


def create_conversation(db: Session, user: User, *, title: str | None = None) -> Conversation:
    conversation = Conversation(
        user_id=user.id, title=(title or DEFAULT_TITLE).strip()[:200] or DEFAULT_TITLE
    )
    db.add(conversation)
    db.flush()
    return conversation


def list_conversations(
    db: Session, user: User, *, include_archived: bool = False, q: str | None = None
):
    stmt = select(Conversation).where(Conversation.user_id == user.id)
    if not include_archived:
        stmt = stmt.where(Conversation.archived.is_(False))
    if q and q.strip():
        # AI-38: 제목 부분일치만으로는 "내가 만든 티켓 보여줘" 같은 흔한 제목 아래 묻힌
        # 대화를 못 찾는다. 본문(사용자 메시지) 부분일치도 함께 본다 — 대화 소유권은 위
        # user_id 필터가 이미 보장하므로 서브쿼리에 따로 걸지 않는다.
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Conversation.title.ilike(like),
                Conversation.id.in_(
                    select(Message.conversation_id).where(Message.content.ilike(like))
                ),
            )
        )
    return (
        db.execute(stmt.order_by(Conversation.updated_at.desc()).limit(100))
        .scalars()
        .all()
    )


def get_owned_conversation(db: Session, user: User, conversation_id: str) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise NotFoundError("대화를 찾을 수 없습니다.")
    # Ownership is enforced server-side — never by UI hiding (spec §25.5).
    if conversation.user_id != user.id:
        raise ForbiddenError("본인 대화만 접근할 수 있습니다.")
    return conversation


def rename_conversation(db: Session, conversation: Conversation, title: str) -> Conversation:
    conversation.title = (title or "").strip()[:200] or DEFAULT_TITLE
    db.flush()
    return conversation


def set_conversation_archived(
    db: Session, conversation: Conversation, archived: bool
) -> Conversation:
    conversation.archived = bool(archived)
    db.flush()
    return conversation


def purge_conversation_job_payloads(db: Session, conversation_ids) -> int:
    """Redact queued/finished job payloads belonging to deleted conversations.

    삭제(사용자 요청이든 보존기간 만료든)는 사용자에게 '원문이 없어졌다'는 뜻이다.
    Job payload에 채팅 원문·첨부 바이트·요청자 정보가 남아 있으면 삭제가 아니라
    이동일 뿐이다. 큐 행 자체는 운영 지표(상태/재시도/오류)라 남기고, 사람이 쓴
    내용만 지운다. Returns 손댄 Job 수.
    """
    import json as _json

    from app.jobs.models import Job

    ids = list(conversation_ids)
    if not ids:
        return 0
    rows = (
        db.execute(select(Job).where(Job.conversation_id.in_(ids))).scalars().all()
    )
    for job in rows:
        # 참조값(어느 대화/메시지의 작업이었나)만 남긴 stub — 내용은 남기지 않는다.
        job.payload_json = _json.dumps(
            {
                "conversation_id": job.conversation_id,
                "message_id": job.message_id,
                "purged": True,
            },
            ensure_ascii=False,
        )
    if rows:
        db.flush()
    return len(rows)


def delete_conversation(db: Session, conversation: Conversation) -> None:
    """Hard-delete a conversation and its messages (owner-checked by caller)."""
    purge_conversation_job_payloads(db, [conversation.id])
    db.execute(delete(Message).where(Message.conversation_id == conversation.id))
    db.delete(conversation)
    db.flush()


def list_messages(db: Session, conversation: Conversation, *, after: str | None = None):
    # Order by SQLite rowid = true insertion order. Timestamp ordering is not
    # reliable here: Windows/most OS clocks tick coarser than message inserts,
    # so created_at ties are common. (Revisit if the DB moves to Postgres —
    # repository layer isolates this.)
    from sqlalchemy import literal_column

    stmt = select(Message).where(Message.conversation_id == conversation.id)
    rows = list(db.execute(stmt.order_by(literal_column("rowid"))).scalars().all())
    if after:
        index = next((i for i, m in enumerate(rows) if m.id == after), None)
        if index is None:
            # Unknown/stale cursor: return nothing new rather than resending the
            # whole conversation (which would duplicate every message client-side).
            return []
        rows = rows[index + 1 :]
    return rows


def post_user_message(
    db: Session,
    user: User,
    conversation: Conversation,
    *,
    content: str,
    client_message_id: str,
    settings: Settings,
    now: datetime,
    attachments: list | None = None,
    screen_context: str | None = None,
):
    """Save the user message and enqueue the n8n job. Returns (message, job)."""
    import json as _json

    from app.chat.attachments import attachment_names, validate_attachments

    images = validate_attachments(attachments)
    content = (content or "").strip()
    if not content and images:
        content = "(이미지 첨부)"
    if not content:
        raise ValidationAppError("메시지를 입력하세요.")
    if len(content) > settings.max_message_length:
        raise ValidationAppError(
            f"메시지는 최대 {settings.max_message_length}자까지 입력할 수 있습니다."
        )
    if not _CLIENT_MESSAGE_ID.match(client_message_id or ""):
        raise ValidationAppError("client_message_id 형식이 올바르지 않습니다.")

    # UB-23: 소유자(대화) 필터 없이 message_id만 봤었다 — 전역에서 "이 문자열이 이미
    # 존재하는가"를 201/409로 알려 주는 존재-확인 오라클이었다(다른 사용자의 대화에 속한
    # 메시지라도). 유일성 자체가 이제 (conversation_id, message_id) 복합키다(migration
    # 0054) — 조회도 같은 범위로 좁힌다. 다른 대화에서 이미 쓰인 id와 겹쳐도 이 대화
    # 안에서는 새 메시지일 뿐이라 "다른 대화에서 사용됨" 분기 자체가 더 이상 없다.
    existing = db.execute(
        select(Message).where(
            Message.conversation_id == conversation.id, Message.message_id == client_message_id
        )
    ).scalar_one_or_none()
    if existing is not None:
        # Duplicate submit (double-click / refresh) — return the original.
        job = jobs_repo.get_by_idempotency_key(db, f"chatmsg:{client_message_id}")
        return existing, job

    message = Message(
        conversation_id=conversation.id,
        message_id=client_message_id,
        role=ROLE_USER_MSG,
        content=content,
        # Names only — image bytes are never stored on the platform (§13 확장).
        structured_payload_json=(
            _json.dumps({"attachments": attachment_names(images)}, ensure_ascii=False)
            if images
            else None
        ),
        processing_status=PROC_PENDING,
    )
    db.add(message)

    # Auto-title from the first message (spec §13.1).
    if conversation.title == DEFAULT_TITLE:
        conversation.title = auto_title(content)
    conversation.updated_at = now
    db.flush()

    job = jobs_repo.enqueue(
        db,
        job_type=JOB_TYPE_CHAT_MESSAGE,
        payload=_build_job_payload(
            user, conversation, message, attachments=images, screen_context=screen_context
        ),
        now=now,
        user_id=user.id,
        conversation_id=conversation.id,
        message_id=client_message_id,
        idempotency_key=f"chatmsg:{client_message_id}",
    )
    return message, job


def _build_job_payload(
    user: User,
    conversation: Conversation,
    message: Message,
    *,
    attachments: list[dict] | None = None,
    screen_context: str | None = None,
) -> dict:
    # Requester comes ONLY from the authenticated session user (spec §11.2).
    payload = {
        "conversation_id": conversation.id,
        "backend_conversation_id": conversation.backend_conversation_id,
        "message_id": message.message_id,
        "content": message.content,
        "requester": {
            "user_id": user.id,
            "email": user.email,
            "name": user.display_name,
        },
    }
    if attachments:
        payload = {**payload, "attachments": attachments}
    if screen_context:
        payload = {**payload, "screen_context": screen_context}
    return payload


def retry_message(
    db: Session, user: User, message_db_id: str, *, settings: Settings, now: datetime
):
    message = db.get(Message, message_db_id)
    if message is None:
        raise NotFoundError("메시지를 찾을 수 없습니다.")
    conversation = get_owned_conversation(db, user, message.conversation_id)
    if message.role != ROLE_USER_MSG or message.processing_status != PROC_FAILED:
        raise ConflictError("실패한 요청만 다시 시도할 수 있습니다.")

    message.processing_status = PROC_PENDING
    message.error_code = None
    # 이전 실패 안내(error_notice)는 재시도로 무효가 된다. 지우지 않으면 재시도가 성공해도
    # '연결에 문제가 있어 완료하지 못했습니다'가 성공 답변과 함께 남아 사실과 반대되는 상태를
    # 보여준다(round16 제품 스윕에서 확정). 이 사용자 메시지에 달렸던 실패 안내를 걷어낸다.
    for notice in db.execute(
        select(Message).where(
            Message.conversation_id == conversation.id,
            Message.message_id.like(f"a-{message.message_id}-fail-%"),
        )
    ).scalars().all():
        db.delete(notice)
    db.flush()

    # Recover image attachments from the failed job so a retry doesn't silently
    # lose them (bytes are only stripped from TERMINAL-success payloads; the
    # newest non-stripped payload for this message still holds them). The donor
    # is stripped right after copying — bytes live in exactly one queued job.
    attachments = _recover_attachments_for_retry(db, message.message_id)

    # New idempotency key per retry attempt — the original is spent.
    job = jobs_repo.enqueue(
        db,
        job_type=JOB_TYPE_CHAT_MESSAGE,
        payload=_build_job_payload(user, conversation, message, attachments=attachments),
        now=now,
        user_id=user.id,
        conversation_id=conversation.id,
        message_id=message.message_id,
        idempotency_key=f"chatmsg:{message.message_id}:retry:{now.strftime('%Y%m%d%H%M%S%f')}",
    )
    return message, job


def _recover_attachments_for_retry(db: Session, message_id: str) -> list[dict] | None:
    import json as _json

    from app.jobs.handlers.chat_message import strip_attachment_bytes
    from app.jobs.models import Job

    rows = (
        db.execute(
            select(Job)
            .where(Job.message_id == message_id, Job.job_type == JOB_TYPE_CHAT_MESSAGE)
            .order_by(Job.created_at.desc())
        )
        .scalars()
        .all()
    )
    for job in rows:
        try:
            payload = _json.loads(job.payload_json)
        except (ValueError, TypeError):
            continue
        attachments = payload.get("attachments")
        if not isinstance(attachments, list) or not attachments:
            continue
        live = [
            a for a in attachments
            if isinstance(a, dict) and a.get("data") and not a.get("stripped")
        ]
        if live:
            strip_attachment_bytes(job, payload)
            db.flush()
            return live
    return None


def message_view(message: Message) -> dict:
    import json

    return {
        "id": message.id,
        "message_id": message.message_id,
        "role": message.role,
        "content": message.content,
        "structured": (
            json.loads(message.structured_payload_json)
            if message.structured_payload_json
            else None
        ),
        "processing_status": message.processing_status,
        "error_code": message.error_code,
        "created_at": message.created_at.isoformat(),
        "updated_at": message.updated_at.isoformat(),
    }


def conversation_view(conversation: Conversation) -> dict:
    return {
        "id": conversation.id,
        "title": conversation.title,
        "archived": conversation.archived,
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
    }
