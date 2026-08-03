"""팀 채팅 데이터 접근 (쿼리 전용)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.team_chat.models import (
    ChatMessage,
    ChatMessageImage,
    ChatReadCursor,
    ChatRoom,
    ChatRoomMember,
)
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


def get_message_by_seq(db: Session, room_id: str, seq: int) -> ChatMessage | None:
    """방 안의 seq 하나를 집는다(삭제된 것도 포함).

    삭제된 행까지 돌려주는 이유: 삭제 요청이 두 번 오면(느린 네트워크의 재시도) '이미 삭제됨'과
    '그런 메시지 없음'을 구분해서 답해야 한다. 없는 것으로 답하면 404 가 뜨고 사용자는
    자기 메시지가 사라졌는지 실패했는지 알 수 없다.
    """
    return db.execute(
        select(ChatMessage).where(ChatMessage.room_id == room_id, ChatMessage.seq == seq)
    ).scalar_one_or_none()


def find_by_client_id(db: Session, room_id: str, client_message_id: str) -> ChatMessage | None:
    return db.execute(
        select(ChatMessage).where(
            ChatMessage.room_id == room_id, ChatMessage.client_message_id == client_message_id
        )
    ).scalar_one_or_none()


def get_message(db: Session, message_id: str) -> ChatMessage | None:
    return db.execute(
        select(ChatMessage).where(
            ChatMessage.id == message_id, ChatMessage.deleted_at.is_(None)
        )
    ).scalar_one_or_none()


def get_image(db: Session, message_id: str, image_id: str) -> ChatMessageImage | None:
    """이미지는 항상 자기 메시지와 짝지어 조회한다 — image_id만으로 찾으면 다른 방의
    이미지를 자기 방 메시지 id에 붙여 부르는 경로가 열린다."""
    return db.execute(
        select(ChatMessageImage).where(
            ChatMessageImage.id == image_id, ChatMessageImage.message_id == message_id
        )
    ).scalar_one_or_none()


def images_for_messages(db: Session, message_ids: list[str]) -> dict[str, list[ChatMessageImage]]:
    """메시지 목록 한 번에 이미지 붙이기(N+1 회피). 이미지 없는 방은 쿼리 자체를 건너뛴다."""
    if not message_ids:
        return {}
    rows = (
        db.execute(
            select(ChatMessageImage)
            .where(ChatMessageImage.message_id.in_(list(message_ids)))
            .order_by(ChatMessageImage.created_at)
        )
        .scalars()
        .all()
    )
    out: dict[str, list[ChatMessageImage]] = {}
    for row in rows:
        out.setdefault(row.message_id, []).append(row)
    return out


def get_cursor(db: Session, room_id: str, user_id: str) -> ChatReadCursor | None:
    return db.execute(
        select(ChatReadCursor).where(
            ChatReadCursor.room_id == room_id, ChatReadCursor.user_id == user_id
        )
    ).scalar_one_or_none()


def cursors_for_user(db: Session, user_id: str) -> dict[str, ChatReadCursor]:
    """room_id → 커서. 목록 화면이 방마다 한 번씩 묻지 않게 한 번에 읽는다."""
    rows = (
        db.execute(select(ChatReadCursor).where(ChatReadCursor.user_id == user_id))
        .scalars()
        .all()
    )
    return {row.room_id: row for row in rows}


def cursors_for_room(db: Session, room_id: str) -> dict[str, ChatReadCursor]:
    """user_id → 커서(방 하나). 멤버 행이 없는 참여자의 읽음 위치를 한 번에 읽는다."""
    rows = (
        db.execute(select(ChatReadCursor).where(ChatReadCursor.room_id == room_id))
        .scalars()
        .all()
    )
    return {row.user_id: row for row in rows}


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
