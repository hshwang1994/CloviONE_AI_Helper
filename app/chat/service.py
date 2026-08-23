"""Chat service: conversations, messages, and job enqueueing (spec §13, §22).

The requester identity in every job payload is built here from the SERVER
session user — nothing client-supplied is ever trusted (spec §11.2).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.conversations.models import (
    PROC_DONE,
    PROC_FAILED,
    PROC_PENDING,
    ROLE_ASSISTANT_MSG,
    ROLE_USER_MSG,
    Conversation,
    Message,
)
from app.core.config import Settings
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.jobs import repository as jobs_repo
from app.jobs.models import JOB_TYPE_CHAT_MESSAGE, Job
from app.users.models import User

logger = logging.getLogger("app.chat.service")

_CLIENT_MESSAGE_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
DEFAULT_TITLE = "새 대화"
AUTO_TITLE_MAX_CHARS = 60
# AI-18: 예전엔 100개로 고정 상한이었고 그 이상은 화면에서 영영 볼 방법이 없었다(스크롤도,
# "더 보기"도 없음). 기본값은 그대로 100 — 대화가 100개 이하인 절대다수 사용자는 지금과
# 똑같이 한 번에 다 받는다. 그 이상 필요할 때만 화면이 이 값을 키워 같은 목록을 처음부터
# 다시 요청한다(오프셋을 이어붙이지 않는 이유는 router의 get_conversations 주석 참고).
DEFAULT_CONVERSATION_LIST_LIMIT = 100
MAX_CONVERSATION_LIST_LIMIT = 1000


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
    db: Session,
    user: User,
    *,
    include_archived: bool = False,
    q: str | None = None,
    limit: int = DEFAULT_CONVERSATION_LIST_LIMIT,
) -> tuple[list[Conversation], int]:
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
    # AI-18: total은 limit과 무관하게 "이 필터에 맞는 전체 개수" — 화면이 이걸로 상한
    # 너머에 더 있는지 판단해 "더 보기"를 보여줄지 정한다.
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = (
        db.execute(stmt.order_by(Conversation.updated_at.desc()).limit(limit))
        .scalars()
        .all()
    )
    return rows, total


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
    """Hard-delete a conversation and its messages (owner-checked by caller).

    예전에는 러너에도 삭제를 알려 그쪽 미러(`conversation_state`)를 지웠다(AI-16).
    S11 이 러너를 걷어내면서 지울 미러가 없어졌다 — 대화 내용은 이제 이 DB 밖으로
    나간 적이 없으므로 여기서 지우면 끝이다.
    """
    purge_conversation_job_payloads(db, [conversation.id])
    db.execute(delete(Message).where(Message.conversation_id == conversation.id))
    db.delete(conversation)
    db.flush()


def list_messages(db: Session, conversation: Conversation, *, after: str | None = None):
    # `Message.seq`(GENERATED ALWAYS AS IDENTITY) 로 정렬한다 = 진짜 삽입 순서.
    # `created_at` 으로는 못 한다: 대부분의 OS 시계는 메시지 삽입보다 굵게 tick 해서
    # 동점이 흔하다. 예전에는 SQLite 의 숨은 `rowid` 를 썼고, PG 에는 그것이 없다.
    # AI-36: soft-deleted messages (user delete, or replaced by regenerate) never
    # come back. useChat.js refetches the whole list every poll (no `after=` cursor
    # client-side), so this filter alone is enough for the next poll to drop them —
    # unlike team_chat's ChatMessage.deleted_at, no seq-bumping tombstone is needed.
    stmt = select(Message).where(
        Message.conversation_id == conversation.id, Message.deleted_at.is_(None)
    )
    rows = list(db.execute(stmt.order_by(Message.seq)).scalars().all())
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
    """Save the user message and enqueue the answer job. Returns (message, job)."""
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


def _reenqueue(
    db: Session, user: User, conversation: Conversation, message: Message,
    *, tag: str, now: datetime,
) -> Job:
    """retry/regenerate가 공유하는 꼬리 — 메시지를 PENDING으로 되돌리고 새 잡을 큐에
    넣는다. 첨부는 원래 잡에서 회수한다(성공 종료 시에만 바이트가 지워지므로, 아직 안
    지워진 최신 payload에 남아 있다). 멱등키의 `tag`(retry/regen)만 호출부마다 다르다."""
    message.processing_status = PROC_PENDING
    message.error_code = None
    db.flush()

    attachments = _recover_attachments_for_retry(db, message.message_id)
    return jobs_repo.enqueue(
        db,
        job_type=JOB_TYPE_CHAT_MESSAGE,
        payload=_build_job_payload(user, conversation, message, attachments=attachments),
        now=now,
        user_id=user.id,
        conversation_id=conversation.id,
        message_id=message.message_id,
        idempotency_key=f"chatmsg:{message.message_id}:{tag}:{now.strftime('%Y%m%d%H%M%S%f')}",
    )


def retry_message(
    db: Session, user: User, message_db_id: str, *, settings: Settings, now: datetime
):
    message = db.get(Message, message_db_id)
    if message is None:
        raise NotFoundError("메시지를 찾을 수 없습니다.")
    conversation = get_owned_conversation(db, user, message.conversation_id)
    if message.role != ROLE_USER_MSG or message.processing_status != PROC_FAILED:
        raise ConflictError("실패한 요청만 다시 시도할 수 있습니다.")

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

    job = _reenqueue(db, user, conversation, message, tag="retry", now=now)
    return message, job


def _is_last_turn(db: Session, conversation: Conversation, message: Message) -> bool:
    """이 사용자 메시지 뒤에 자기 자신의 답변 말고 다른 메시지가 없는가 — 재생성은 대화가
    이미 그 뒤로 이어졌으면 막는다(중간 턴을 바꾸면 그 뒤 맥락과 어긋난다, 분기(branch)는
    이 항목의 범위 밖이라 AI-36 묶음에서 함께 다음 설계 사이클로 미뤘다)."""
    rows = list_messages(db, conversation)
    idx = next((i for i, m in enumerate(rows) if m.id == message.id), None)
    if idx is None:
        return False
    prefix = f"a-{message.message_id}-"
    return all(m.message_id.startswith(prefix) for m in rows[idx + 1 :])


def regenerate_message(
    db: Session, user: User, message_db_id: str, *, settings: Settings, now: datetime
):
    """AI-36: 성공한 답변을 다시 만든다 — 이전 답변(들)은 지우고(soft-delete) 같은 요청을
    새 잡으로 다시 큐에 넣는다. `retry_message`와 재사용 경로(`_reenqueue`)는 같지만
    전제조건이 다르다: 실패가 아니라 **완료된, 그리고 대화의 마지막 턴인** 요청만 대상이다
    (분기 없이 재생성하면서 그 사이 새 메시지가 왔으면 어느 시점 기준인지 모호해진다)."""
    message = db.get(Message, message_db_id)
    if message is None:
        raise NotFoundError("메시지를 찾을 수 없습니다.")
    conversation = get_owned_conversation(db, user, message.conversation_id)
    if message.role != ROLE_USER_MSG or message.processing_status != PROC_DONE:
        raise ConflictError("답변이 완료된 요청만 다시 생성할 수 있습니다.")
    if not _is_last_turn(db, conversation, message):
        raise ConflictError("이후 대화가 이어진 요청은 다시 생성할 수 없습니다.")

    prefix = f"a-{message.message_id}-"
    for reply in db.execute(
        select(Message).where(
            Message.conversation_id == conversation.id,
            Message.message_id.like(f"{prefix}%"),
            Message.deleted_at.is_(None),
        )
    ).scalars().all():
        reply.deleted_at = now
    db.flush()

    job = _reenqueue(db, user, conversation, message, tag="regen", now=now)
    return message, job


def delete_message(db: Session, user: User, message_db_id: str, *, now: datetime) -> Message:
    """AI-36: 내 대화 안의 메시지 하나를 지운다(soft-delete, 멱등) — 소유권은 대화 단위로
    이미 검증되므로(`get_owned_conversation`) role과 무관하게(내 메시지든 어시스턴트
    답변이든) 지울 수 있다. 짝이 되는 메시지를 자동으로 함께 지우지는 않는다 — 턴 전체
    삭제가 필요하면 사용자가 둘 다 누른다(간단하고 예측 가능한 쪽을 골랐다)."""
    message = db.get(Message, message_db_id)
    if message is None:
        raise NotFoundError("메시지를 찾을 수 없습니다.")
    get_owned_conversation(db, user, message.conversation_id)
    if message.deleted_at is None:
        message.deleted_at = now
        db.flush()
    return message


VALID_FEEDBACK = frozenset({"up", "down"})


def set_message_feedback(
    db: Session, user: User, message_db_id: str, feedback: str | None
) -> Message:
    """AI-68: 어시스턴트 답변에 👍/👎. `feedback=None`은 취소(토글 off)."""
    if feedback is not None and feedback not in VALID_FEEDBACK:
        raise ValidationAppError("feedback은 'up'/'down'/null만 허용합니다.")
    message = db.get(Message, message_db_id)
    if message is None:
        raise NotFoundError("메시지를 찾을 수 없습니다.")
    get_owned_conversation(db, user, message.conversation_id)
    if message.role != ROLE_ASSISTANT_MSG:
        raise ConflictError("도우미 답변에만 피드백을 남길 수 있습니다.")
    message.feedback = feedback
    db.flush()
    return message


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
        "feedback": message.feedback,
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
