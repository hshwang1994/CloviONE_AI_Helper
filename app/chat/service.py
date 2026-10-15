"""Chat service: conversations, messages, and job enqueueing (spec §13, §22).

The requester identity in every job payload is built here from the SERVER
session user — nothing client-supplied is ever trusted (spec §11.2).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timedelta

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session, aliased

from app.conversations.models import (
    PROC_DONE,
    PROC_FAILED,
    PROC_PENDING,
    PROC_PROCESSING,
    ROLE_ASSISTANT_MSG,
    ROLE_USER_MSG,
    Conversation,
    Message,
)
from app.core.config import Settings
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.core.search_text import like_folded, pattern_for
from app.jobs import repository as jobs_repo
from app.jobs.models import JOB_TYPE_CHAT_MESSAGE, Job
from app.users.models import User

logger = logging.getLogger("app.chat.service")

_CLIENT_MESSAGE_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
DEFAULT_TITLE = "새 대화"
#: 자동 제목의 글자 상한. 목록 행이 두 줄까지 보이는 길이다.
AUTO_TITLE_MAX_CHARS = 40
#: 「빈 대화 보관」이 건드리지 않는 나이 — 화면은 대화를 만든 직후에 첫 메시지를 보낸다(그 사이의 대화는 빈 대화가 아니다).
EMPTY_MIN_AGE = timedelta(minutes=2)
# AI-18: 예전엔 100개로 고정 상한이었고 그 이상은 화면에서 영영 볼 방법이 없었다(스크롤도,
# "더 보기"도 없음). 기본값은 그대로 100 — 대화가 100개 이하인 절대다수 사용자는 지금과
# 똑같이 한 번에 다 받는다. 그 이상 필요할 때만 화면이 이 값을 키워 같은 목록을 처음부터
# 다시 요청한다(오프셋을 이어붙이지 않는 이유는 router의 get_conversations 주석 참고).
DEFAULT_CONVERSATION_LIST_LIMIT = 100
MAX_CONVERSATION_LIST_LIMIT = 1000
#: 답을 기다리는 사람 메시지가 이 시간 안에 상태가 바뀌었으면 같은 대화의 새 전송 · 다시 시도를 막는다. 화면이 응답을
#: 「지연」으로 보는 기준(`chat-helpers.js::STALL_MS`)과 같은 10분이라, 잡을 잃은 메시지가 대화를 영영 잠그지 않는다.
PENDING_REPLY_WINDOW = timedelta(minutes=10)


class ReplyPendingError(ConflictError):
    """같은 대화에 아직 답을 기다리는 질문이 있다. 화면만 막던 때에는 탭 둘에서 보낸 질문의 잡 둘이 함께 돌아 답이 섞였다."""

    code = "reply_pending"
    default_message = "앞 질문의 답을 만드는 중입니다. 답이 온 뒤에 보내 주세요."


def chat_job_key(conversation_id: str, client_message_id: str) -> str:
    """답 잡의 멱등 키. 메시지 id 는 대화 안에서만 유일하므로 대화 id 를 함께 싣는다.

    예전 키(`chatmsg:{메시지 id}`)는 전역이라 다른 대화에서 같은 id 를 쓰면 `enqueue` 가 남의 잡을 돌려주고 새 메시지는
    잡 없이 대기에 갇혔다."""
    return f"chatmsg:{conversation_id}:{client_message_id}"


#: 질문 끝의 요청 어미 — 제목에는 무엇을 묻는가만 남긴다(「나에게 할당된 티켓 보여줘」 → 「나에게 할당된 티켓」).
_REQUEST_ENDING = re.compile(
    r"\s*(?:좀\s*)?(?:보여\s*줘요?|보여\s*주세요|보여\s*줄래|알려\s*줘요?|알려\s*주세요|알려\s*줄래|찾아\s*줘요?|"
    r"찾아\s*주세요|찾아\s*줄래|해\s*줘요?|해\s*주세요|해\s*줄래)?\s*[?？!！.。~]*\s*$"
)


def clean_title(content: str) -> str:
    """첫 질문에서 만든 제목 — 제어 문자 · 줄바꿈을 걷고, 끝의 요청 어미와 물음표를 떼고, 낱말 경계에서 40자로 줄인다.

    AI-55: 잘렸을 때만 말줄임표를 붙인다(같은 문장으로 시작하는 대화가 목록에서 똑같아 보이지 않게). 다듬고 나서
    아무것도 안 남으면(「?」 만 보낸 질문) 기본 제목이다."""
    text = "".join(" " if unicodedata.category(ch)[0] in ("C", "Z") else ch for ch in (content or ""))
    text = " ".join(text.split())
    trimmed = _REQUEST_ENDING.sub("", text).strip()
    text = trimmed or text.strip(" ?？!！.。~")
    if not text:
        return DEFAULT_TITLE
    if len(text) <= AUTO_TITLE_MAX_CHARS:
        return text
    head = text[: AUTO_TITLE_MAX_CHARS - 1]
    cut = head.rfind(" ")
    if cut >= AUTO_TITLE_MAX_CHARS // 2:
        head = head[:cut]
    return head.rstrip() + "…"


def create_conversation(db: Session, user: User, *, title: str | None = None) -> Conversation:
    conversation = Conversation(
        user_id=user.id, title=(title or DEFAULT_TITLE).strip()[:200] or DEFAULT_TITLE
    )
    db.add(conversation)
    db.flush()
    return conversation


#: 목록 보기 — 지금 쓰는 대화 · 보관함 · 둘 다(옛 `include_archived=true`).
VIEW_ACTIVE, VIEW_ARCHIVED, VIEW_ALL = "active", "archived", "all"


def _has_messages():
    """이 대화에 지우지 않은 메시지가 있는가(상관 서브쿼리)."""
    return select(Message.id).where(Message.conversation_id == Conversation.id, Message.deleted_at.is_(None)).exists()


def list_conversations(
    db: Session,
    user: User,
    *,
    view: str = VIEW_ACTIVE,
    q: str | None = None,
    limit: int = DEFAULT_CONVERSATION_LIST_LIMIT,
) -> tuple[list[Conversation], int]:
    stmt = select(Conversation).where(Conversation.user_id == user.id)
    if view == VIEW_ACTIVE:
        stmt = stmt.where(Conversation.archived.is_(False))
    elif view == VIEW_ARCHIVED:
        stmt = stmt.where(Conversation.archived.is_(True))
    pattern = pattern_for(q)
    if pattern is not None:
        # AI-38: 제목 부분일치만으로는 "내가 만든 티켓 보여줘" 같은 흔한 제목 아래 묻힌
        # 대화를 못 찾는다. 본문(메시지) 부분일치도 함께 본다. 대조는 공용 접기 규칙이다 —
        # 양쪽 공백·대소문자·표기를 맞추고 `%`·`_` 는 글자로 본다.
        #
        # 메시지 서브쿼리도 **내 대화로 좁힌다.** 결과의 소유권은 위 user_id 필터가 이미
        # 보장하지만, 좁히지 않으면 검색 한 번이 전 사용자의 메시지를 전부 접어 본다 —
        # 비용이 내 대화가 아니라 제품 전체 메시지 수에 비례한다.
        # 바깥 질의도 `conversations` 를 읽는다. 별칭을 안 쓰면 SQLAlchemy 가 안쪽을 바깥
        # 행에 상관시켜 버릴 수 있어서, 「내 대화」 판정이 따로 서도록 별칭으로 분리한다.
        mine = aliased(Conversation)
        own_messages = (
            select(Message.conversation_id)
            .join(mine, mine.id == Message.conversation_id)
            .where(mine.user_id == user.id, Message.deleted_at.is_(None), like_folded(Message.content, pattern))
        )
        stmt = stmt.where(
            or_(
                like_folded(Conversation.title, pattern),
                Conversation.id.in_(own_messages),
            )
        )
    # AI-18: total은 limit과 무관하게 "이 필터에 맞는 전체 개수" — 화면이 이걸로 상한
    # 너머에 더 있는지 판단해 "더 보기"를 보여줄지 정한다.
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    # 마지막으로 말을 나눈 순서다(0050). 이름 바꾸기 · 보관은 순서를 바꾸지 않는다. 같은 시각이면 만든 순서 · id 로 정한다.
    activity = func.coalesce(Conversation.last_message_at, Conversation.created_at)
    rows = (
        db.execute(stmt.order_by(activity.desc(), Conversation.created_at.desc(), Conversation.id.desc()).limit(limit))
        .scalars()
        .all()
    )
    return rows, total


def message_counts(db: Session, conversation_ids) -> dict[str, int]:
    """대화마다 지우지 않은 메시지 수 — 목록 한 쪽치를 한 질의로."""
    ids = list(conversation_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(Message.conversation_id, func.count())
        .where(Message.conversation_id.in_(ids), Message.deleted_at.is_(None))
        .group_by(Message.conversation_id)
    ).all()
    return {conversation_id: int(count) for conversation_id, count in rows}


def _empty_conversations(user: User, *, keep_id: str | None, now: datetime):
    stmt = select(Conversation).where(
        Conversation.user_id == user.id,
        Conversation.archived.is_(False),
        Conversation.created_at <= now - EMPTY_MIN_AGE,
        ~_has_messages(),
    )
    if keep_id:
        stmt = stmt.where(Conversation.id != keep_id)
    return stmt


def count_empty_conversations(db: Session, user: User, *, keep_id: str | None, now: datetime) -> int:
    """「빈 대화 N개 보관」의 N — 화면이 받아 온 쪽이 아니라 내 대화 전체에서 센다."""
    stmt = _empty_conversations(user, keep_id=keep_id, now=now)
    return db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()


def archive_empty_conversations(db: Session, user: User, *, keep_id: str | None, now: datetime) -> list[str]:
    """메시지가 하나도 없는 내 대화를 보관한다. 제목은 보지 않는다 — 제목이 「새 대화」여도 메시지가 있으면 빈 대화가 아니다.

    예전에는 화면이 받아 온 쪽에서 제목만 보고 PATCH 를 여러 번 보냈다. 지금 연 대화와 만든 지 2분이 안 된 대화(첫 메시지를
    보내는 중일 수 있다)는 건드리지 않는다. 지우지 않고 보관하므로 보관함에서 다시 꺼낼 수 있다."""
    rows = db.execute(_empty_conversations(user, keep_id=keep_id, now=now)).scalars().all()
    for conversation in rows:
        conversation.archived = True
    if rows:
        db.flush()
    return [conversation.id for conversation in rows]


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


def delete_conversation(db: Session, conversation: Conversation, *, now: datetime) -> None:
    """Hard-delete a conversation and its messages (owner-checked by caller).

    예전에는 러너에도 삭제를 알려 그쪽 미러(`conversation_state`)를 지웠다(AI-16).
    S11 이 러너를 걷어내면서 지울 미러가 없어졌다 — 대화 내용은 이제 이 DB 밖으로
    나간 적이 없으므로 여기서 지우면 끝이다.

    아직 대기 중인 답 잡은 취소한다. 남겨 두면 걷힌 페이로드로 돌다 실패해 지운 사람에게 「요청 처리에 실패했습니다」
    알림이 갔고, AI 사용 한도의 대기 몫도 그대로 잡고 있었다. 이미 도는 잡은 처리기가 마지막에 대화가 없음을 보고
    조용히 끝난다(`app/jobs/handlers/chat_message.py`).
    """
    from app.jobs.models import STATUS_CANCELLED, STATUS_QUEUED, Job

    db.execute(
        update(Job)
        .where(Job.conversation_id == conversation.id, Job.job_type == JOB_TYPE_CHAT_MESSAGE,
               Job.status == STATUS_QUEUED)
        .values(status=STATUS_CANCELLED, finished_at=now, started_at=None, updated_at=now)
        .execution_options(synchronize_session=False)
    )
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


#: 글 없이 이미지만 보낸 메시지의 본문. 워커는 이 글을 질문으로 보내지 않는다(`app/jobs/handlers/chat_message.py`).
IMAGE_ONLY_CONTENT = "(이미지 첨부)"


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
    screen_context: dict | None = None,
):
    """Save the user message and enqueue the answer job. Returns (message, job).

    ``screen_context`` 는 서랍이 보낸 화면 대상 ``{kind, ref, label}`` 이다(D-538). 사용자 메시지의 구조에 남겨 재시도 ·
    다시 만들기에도 같은 대상으로 묻고, 잡 payload 에도 싣는다. 대상을 믿지는 않는다 - 워커가 대화 주인의 권한으로 다시
    읽은 것만 모델에 간다(`app/ai/assistant/history.py`).
    """
    from app.chat.attachments import attachment_names, validate_attachments

    images = validate_attachments(attachments)
    content = (content or "").strip()
    if not content and images:
        content = IMAGE_ONLY_CONTENT
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
        # Duplicate submit (double-click / refresh) — return the original. 키를 바꾸기 전에 만든 잡은 옛 키로 찾는다.
        job = (jobs_repo.get_by_idempotency_key(db, chat_job_key(conversation.id, client_message_id))
               or jobs_repo.get_by_idempotency_key(db, f"chatmsg:{client_message_id}"))
        return existing, job

    ensure_no_pending_reply(db, conversation, now=now)

    message = Message(
        conversation_id=conversation.id,
        message_id=client_message_id,
        role=ROLE_USER_MSG,
        content=content,
        # Names only — image bytes are never stored on the platform (§13 확장).
        structured_payload_json=_user_structured(attachment_names(images) if images else None, screen_context),
        processing_status=PROC_PENDING,
    )
    db.add(message)

    # Auto-title from the first message (spec §13.1). 이미지만 보낸 질문은 제목이 될 글이 없어 기본 제목으로 둔다.
    if conversation.title == DEFAULT_TITLE and content != IMAGE_ONLY_CONTENT:
        conversation.title = clean_title(content)
    conversation.updated_at = now
    conversation.last_message_at = now
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
        idempotency_key=chat_job_key(conversation.id, client_message_id),
    )
    return message, job


def ensure_no_pending_reply(db: Session, conversation: Conversation, *, now: datetime) -> None:
    """대화당 기다리는 답은 하나다. 대화 행을 잠그고, 상태가 `PENDING_REPLY_WINDOW` 안에 바뀐 대기 · 처리 중 사람 메시지가
    있으면 `ReplyPendingError` 다. 잠금은 같은 대화로 동시에 들어온 두 요청이 둘 다 「없음」을 보고 지나가지 않게 한다."""
    db.execute(select(Conversation.id).where(Conversation.id == conversation.id).with_for_update())
    waiting = db.execute(
        select(Message.id).where(
            Message.conversation_id == conversation.id,
            Message.role == ROLE_USER_MSG,
            Message.deleted_at.is_(None),
            Message.processing_status.in_((PROC_PENDING, PROC_PROCESSING)),
            Message.updated_at >= now - PENDING_REPLY_WINDOW,
        ).limit(1)
    ).first()
    if waiting is not None:
        raise ReplyPendingError()


def _user_structured(attachment_names: list | None, screen_context: dict | None) -> str | None:
    import json as _json

    body = {}
    if attachment_names:
        body["attachments"] = attachment_names
    if screen_context:
        body["screen_context"] = screen_context
    return _json.dumps(body, ensure_ascii=False) if body else None


def _stored_screen_context(message: Message) -> dict | None:
    """사용자 메시지에 남긴 화면 대상. 재시도 · 다시 만들기가 같은 대상으로 묻는다."""
    import json as _json

    raw = message.structured_payload_json
    try:
        body = _json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        return None
    value = body.get("screen_context") if isinstance(body, dict) else None
    return value if isinstance(value, dict) else None


def _build_job_payload(
    user: User,
    conversation: Conversation,
    message: Message,
    *,
    attachments: list[dict] | None = None,
    screen_context: dict | None = None,
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

    attachments = _recover_attachments_for_retry(db, conversation.id, message.message_id)
    return jobs_repo.enqueue(
        db,
        job_type=JOB_TYPE_CHAT_MESSAGE,
        payload=_build_job_payload(user, conversation, message, attachments=attachments,
                                   screen_context=_stored_screen_context(message)),
        now=now,
        user_id=user.id,
        conversation_id=conversation.id,
        message_id=message.message_id,
        idempotency_key=f"{chat_job_key(conversation.id, message.message_id)}:{tag}:{now.strftime('%Y%m%d%H%M%S%f')}",
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
    ensure_no_pending_reply(db, conversation, now=now)

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


def _recover_attachments_for_retry(db: Session, conversation_id: str, message_id: str) -> list[dict] | None:
    """그 대화의 그 메시지 잡에서만 첨부를 되찾는다. 메시지 id 는 대화 안에서만 유일해, id 하나로 찾으면 같은 id 를 쓴
    다른 대화의 이미지를 집을 수 있었다."""
    import json as _json

    from app.jobs.handlers.chat_message import strip_attachment_bytes
    from app.jobs.models import Job

    rows = (
        db.execute(
            select(Job)
            .where(Job.conversation_id == conversation_id, Job.message_id == message_id,
                   Job.job_type == JOB_TYPE_CHAT_MESSAGE)
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


def conversation_view(conversation: Conversation, *, message_count: int | None = None) -> dict:
    view = {
        "id": conversation.id,
        "title": conversation.title,
        "archived": conversation.archived,
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
        # 목록의 정렬과 행 시각 — 메시지가 아직 없으면 만든 시각이다(정렬과 같은 값).
        "last_message_at": (conversation.last_message_at or conversation.created_at).isoformat(),
    }
    if message_count is not None:
        view["message_count"] = message_count
    return view


def result_page(db: Session, user: User, message_db_id: str, rid: str, *, offset: int, sort: str | None, env) -> dict:
    """답 아래 결과 블록의 한 쪽(「10건 더 보기」 · 정렬 바꾸기) — 모델을 부르지 않는다(`app/ai/assistant/paging.py`).

    메시지 → 대화 주인을 먼저 본다. 지운 답 · 사람 메시지 · 없는 메시지는 404 다. 쓸 수 있는 도구는 **지금** 권한과 기능
    플래그로 다시 거른다(블록을 만든 때가 아니다)."""
    from app.ai.assistant import catalog, paging
    from app.authz.service import has_permission

    message = db.get(Message, message_db_id)
    if message is None or message.deleted_at is not None:
        raise NotFoundError("메시지를 찾을 수 없습니다.")
    get_owned_conversation(db, user, message.conversation_id)
    if message.role != ROLE_ASSISTANT_MSG:
        raise NotFoundError("그 목록을 찾을 수 없습니다.")
    allowed = {tool.name: tool for tool in catalog.available_tools(
        can=lambda key: has_permission(db, user, key), flag=env.flag)}
    return paging.next_page(db, user, message, rid, offset=offset, sort=sort, env=env, allowed=allowed)
