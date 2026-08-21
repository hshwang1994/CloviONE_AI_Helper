"""Conversation and message models (spec §21.4, §21.5)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, JsonText, TimestampMixin, UUIDPrimaryKeyMixin

ROLE_USER_MSG = "user"
ROLE_ASSISTANT_MSG = "assistant"

PROC_PENDING = "pending"
PROC_PROCESSING = "processing"
PROC_DONE = "done"
PROC_FAILED = "failed"


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_updated_at", "updated_at"),
    )

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
    #
    # **폭이 128 인 이유는 계약이다** (D-214). SQLite 는 `VARCHAR(n)` 의 n 을 무시했지만
    # PG 는 강제한다 — 그리고 이 컬럼에 들어가는 값 중 하나는 선언된 64 를 넘는다.
    # `app/jobs/handlers/chat_message.py` 가 만드는 실패 표식이 가장 길다:
    #
    #     "a-" (2) + client_message_id (≤64) + "-fail-" (6) + job.id (uuid4 36) = 108
    #
    # `client_message_id` 의 상한 64 는 `app/chat/router.py` 의 `max_length=64` 와
    # `app/chat/service.py` 의 정규식이 잡는다. **운영에서 관측된 최대는 80 이지만 그건
    # 우연이다** — 지금 클라이언트가 36자 UUID 를 보내기 때문이고, 계약은 64자를 허용한다.
    # 관측값에 맞춰 넓히면 더 긴(그러나 유효한) id 가 오는 날 다시 깨진다.
    #
    # 이 컬럼은 `uq_messages_conversation_message_id` 의 일부라 **절단은 선택지가 아니다** —
    # 자르면 서로 다른 두 메시지가 같은 키가 된다.
    message_id: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_payload_json: Mapped[str | None] = mapped_column(JsonText)
    processing_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=PROC_DONE
    )
    error_code: Mapped[str | None] = mapped_column(String(64))
    # AI-36/AI-68: soft-delete — 사용자가 자기 대화에서 메시지를 지우거나(delete_message),
    # 재생성이 이전 답변을 대체할 때(regenerate_message) 쓴다. list_messages가
    # deleted_at IS NULL로 거른다. useChat.js의 폴링은 매번 대화 전체를 다시 받아 오므로
    # (team_chat과 달리 커서 기반 증분 동기화가 아니다) 이 필드만으로 다음 폴링에 곧바로
    # 반영된다 — team_chat/models.py::ChatMessage.deleted_at처럼 seq를 올리는 툼스톤이
    # 필요 없다(그 모듈은 `after=` 커서 폴링이라 다르다).
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    # AI-68: 어시스턴트 메시지에만 의미가 있다("up"/"down"/None) — set_message_feedback이
    # role을 검증한다.
    feedback: Mapped[str | None] = mapped_column(String(16))

    # 삽입 순서를 **1급 컬럼으로** 들고 있는다 (실행목록 5).
    #
    # 예전에는 SQLite 의 숨은 `rowid` 로 정렬했다. PG 에는 그런 것이 없다 — 그리고 없다는
    # 사실이 조용히 드러나지 않는다: `ORDER BY created_at` 만 남기면 동점일 때 순서가
    # **매번 달라진다**(PG 는 동점 순서를 보장하지 않는다). 시계가 멈춘 테스트에서는 늘
    # 동점이라 목록이 뒤집히고, 운영에서도 같은 순간에 달린 두 줄이 뒤바뀐다.
    #
    # `GENERATED ALWAYS AS IDENTITY` 라 앱이 값을 못 넣는다. 넣을 수 있으면 언젠가 넣게
    # 되고, 그 순간 이 컬럼은 "삽입 순서" 가 아니게 된다.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "message_id", name="uq_messages_conversation_message_id"
        ),
    )
