"""Async job queue model (spec §21.6, §22)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, JsonText, TimestampMixin, UUIDPrimaryKeyMixin

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

ALL_STATUSES = frozenset(
    {STATUS_QUEUED, STATUS_RUNNING, STATUS_SUCCEEDED, STATUS_FAILED, STATUS_CANCELLED}
)

# AI 도우미 채팅 한 건. 이름을 여기 둔 이유: 쿼터가 '아직 안 세어진 호출' 을 이 값으로
# 세는데(app/quotas/service.py::pending) 그쪽이 chat 패키지를 import 하면 순환이 된다.
# 문자열을 양쪽에 따로 적으면 한쪽만 바뀌는 날 쿼터가 조용히 0을 세기 시작한다.
JOB_TYPE_CHAT_MESSAGE = "chat_message"


class Job(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        # 워커의 claim 질의가 매초 도는 그 인덱스다 — `WHERE status='queued' AND
        # available_at <= now ORDER BY created_at, id`. 마이그레이션 0005 가 만들었지만
        # 모델에는 없었다: 스키마를 모델에서 만드는 순간 조용히 사라져 claim 이 순차
        # 스캔이 되고, 증상은 "큐가 밀린다" 로만 보인다.
        Index("ix_jobs_claim", "status", "available_at", "created_at"),
    )

    job_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36))
    message_id: Mapped[str | None] = mapped_column(String(64))
    payload_json: Mapped[str] = mapped_column(JsonText, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=STATUS_QUEUED, index=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    available_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
