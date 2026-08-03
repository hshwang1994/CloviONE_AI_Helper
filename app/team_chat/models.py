"""팀 채팅 모델 — 놀이(games)와 같은 폴링/이벤트-시퀀스 구조. 순수 내부(외부 호출 없음).

app/chat 는 AI 도우미 대화(러너/잡 기반)이고, 이 모듈은 사람 사이의 실시간 채팅이다(전혀 다름).
방마다 append-only 메시지 로그 + 정수 커서(event_seq)를 두고, GET .../messages?since=<seq> 폴링으로
따라온다(WebSocket 없이, 불변 §1 sync 유지). 1:1 방은 dm_key(정렬된 두 uid)로 유일하게 만든다.
홈 위젯용 '전체 채팅' 방 하나는 마이그레이션에서 시드하며 멤버십 없이 누구나 읽고 쓴다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow

ROOM_GROUP = "group"
ROOM_DIRECT = "direct"
ROLE_OWNER = "owner"
ROLE_MEMBER = "member"
MSG_TEXT = "text"
MSG_SYSTEM = "system"

# 홈 위젯이 붙는 팀 전체 방(마이그레이션에서 고정 id로 시드). 멤버십 행 없이 누구나 접근.
GLOBAL_ROOM_ID = "00000000-0000-0000-0000-0000cha70001"


class ChatRoom(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "chat_rooms"

    kind: Mapped[str] = mapped_column(String(16), nullable=False, default=ROOM_GROUP, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    created_by_user_id: Mapped[str | None] = mapped_column(String(36))
    is_global: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 1:1 유일성: 정렬된 두 user_id 를 콜론으로 이은 키. 그룹 방은 NULL(SQLite는 NULL 중복 허용).
    dm_key: Mapped[str | None] = mapped_column(String(80), unique=True)
    event_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)


class ChatRoomMember(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "chat_room_members"

    room_id: Mapped[str] = mapped_column(String(36), ForeignKey("chat_rooms.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default=ROLE_MEMBER)
    last_read_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    joined_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint("room_id", "user_id", name="uq_chat_member"),
    )


class ChatMessage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "chat_messages"

    room_id: Mapped[str] = mapped_column(String(36), ForeignKey("chat_rooms.id"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    sender_user_id: Mapped[str | None] = mapped_column(String(36))  # system 메시지는 NULL
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default=MSG_TEXT)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    client_message_id: Mapped[str | None] = mapped_column(String(64))  # 낙관적 전송 중복 제거
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint("room_id", "seq", name="uq_chat_message_seq"),
    )
