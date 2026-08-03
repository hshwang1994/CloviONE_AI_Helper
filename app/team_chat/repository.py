"""팀 채팅 데이터 접근 (쿼리 전용)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.team_chat.models import ChatMessage, ChatRoom, ChatRoomMember
from app.users.models import User


def get_room(db: Session, room_id: str) -> ChatRoom | None:
    return db.execute(
        select(ChatRoom).where(ChatRoom.id == room_id, ChatRoom.deleted_at.is_(None))
    ).scalar_one_or_none()


def get_global_room(db: Session) -> ChatRoom | None:
    return db.execute(
        select(ChatRoom).where(ChatRoom.is_global.is_(True), ChatRoom.deleted_at.is_(None))
    ).scalar_one_or_none()


def get_direct_by_key(db: Session, dm_key: str) -> ChatRoom | None:
    return db.execute(
        select(ChatRoom).where(ChatRoom.dm_key == dm_key, ChatRoom.deleted_at.is_(None))
    ).scalar_one_or_none()


def get_member(db: Session, room_id: str, user_id: str) -> ChatRoomMember | None:
    return db.execute(
        select(ChatRoomMember).where(ChatRoomMember.room_id == room_id, ChatRoomMember.user_id == user_id)
    ).scalar_one_or_none()


def members(db: Session, room_id: str) -> list[ChatRoomMember]:
    return list(
        db.execute(select(ChatRoomMember).where(ChatRoomMember.room_id == room_id)).scalars().all()
    )


def rooms_for_user(db: Session, user_id: str) -> list[ChatRoom]:
    """사용자가 속한(삭제 안 된) 방들 — 그룹·1:1. 전체 채팅 방은 서비스가 따로 붙인다."""
    return list(
        db.execute(
            select(ChatRoom)
            .join(ChatRoomMember, ChatRoomMember.room_id == ChatRoom.id)
            .where(ChatRoomMember.user_id == user_id, ChatRoom.deleted_at.is_(None))
            .order_by(ChatRoom.updated_at.desc())
        ).scalars().all()
    )


def messages_since(db: Session, room_id: str, since: int, *, limit: int = 200) -> list[ChatMessage]:
    """seq > since 인 메시지(삭제 제외)를 seq 오름차순으로. since=0 이면 처음부터(최근 limit개)."""
    rows = list(
        db.execute(
            select(ChatMessage)
            .where(ChatMessage.room_id == room_id, ChatMessage.seq > since, ChatMessage.deleted_at.is_(None))
            .order_by(ChatMessage.seq.desc())
            .limit(limit)
        ).scalars().all()
    )
    rows.reverse()  # 최근 limit개를 시간순(오름차순)으로
    return rows


def last_message(db: Session, room_id: str) -> ChatMessage | None:
    return db.execute(
        select(ChatMessage)
        .where(ChatMessage.room_id == room_id, ChatMessage.deleted_at.is_(None))
        .order_by(ChatMessage.seq.desc())
        .limit(1)
    ).scalar_one_or_none()


def find_by_client_id(db: Session, room_id: str, client_message_id: str) -> ChatMessage | None:
    return db.execute(
        select(ChatMessage).where(
            ChatMessage.room_id == room_id, ChatMessage.client_message_id == client_message_id
        )
    ).scalar_one_or_none()


def users_by_ids(db: Session, ids: list[str]) -> dict[str, User]:
    if not ids:
        return {}
    rows = db.execute(select(User).where(User.id.in_(list(ids)))).scalars().all()
    return {u.id: u for u in rows}


def directory(db: Session, exclude_user_id: str) -> list[User]:
    """1:1 상대 고르기용 — 활성·비보관 사용자(본인 제외). 이름/부서/직책만 노출(라우터에서)."""
    return list(
        db.execute(
            select(User)
            .where(User.active.is_(True), User.archived_at.is_(None), User.id != exclude_user_id)
            .order_by(User.display_name)
        ).scalars().all()
    )
