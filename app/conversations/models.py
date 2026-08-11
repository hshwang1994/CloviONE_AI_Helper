"""Conversation and message models (spec §21.4, §21.5)."""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, TimestampMixin, UUIDPrimaryKeyMixin

ROLE_USER_MSG = "user"
ROLE_ASSISTANT_MSG = "assistant"

PROC_PENDING = "pending"
PROC_PROCESSING = "processing"
PROC_DONE = "done"
PROC_FAILED = "failed"


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="새 대화")
    # Conversation ID on the n8n/assistant side — keeps follow-up context
    # (spec §13.2) without exposing backend identifiers to the browser.
    backend_conversation_id: Mapped[str | None] = mapped_column(String(128))
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Message(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "messages"

    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id"), nullable=False, index=True
    )
    # Client-generated idempotency key (spec §13.4 중복 생성 방지). UB-23: 예전엔 전역
    # unique=True였다 — 소유자 필터 없는 존재 확인(app/chat/service.py::post_user_message)과
    # 합쳐져 "이 문자열이 어딘가에 이미 존재하는가"를 아무 사용자나 물어볼 수 있는 오라클이
    # 됐다. 멱등성 키는 원래 "이 대화 안에서"만 의미가 있었다 — __table_args__의 복합
    # UNIQUE(migration 0054)로 좁힌다.
    message_id: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_payload_json: Mapped[str | None] = mapped_column(Text)
    processing_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=PROC_DONE
    )
    error_code: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "message_id", name="uq_messages_conversation_message_id"
        ),
    )
