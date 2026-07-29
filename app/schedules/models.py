"""Schedule and schedule-run models (spec §21.13, §21.14)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow

TYPE_CRON = "cron"
TYPE_ONCE = "once"

MISFIRE_SKIP = "skip"
MISFIRE_RUN_ONCE = "run_once"
# spec §18.4: Run All Missed는 기본 금지 — 구현하지 않음.

CONCURRENCY_SKIP = "skip"
CONCURRENCY_ALLOW = "allow"

RUN_QUEUED = "queued"
RUN_RUNNING = "running"
RUN_SUCCEEDED = "succeeded"
RUN_FAILED = "failed"
RUN_SKIPPED = "skipped"

TARGET_WORKFLOW = "workflow"
TARGET_SYSTEM = "system"


class Schedule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "schedules"

    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    schedule_type: Mapped[str] = mapped_column(String(16), nullable=False, default=TYPE_CRON)
    cron_expression: Mapped[str | None] = mapped_column(String(120))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Seoul")
    owner_user_id: Mapped[str | None] = mapped_column(String(36))
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_template_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    prompt_id: Mapped[str | None] = mapped_column(String(36))
    runner_id: Mapped[str | None] = mapped_column(String(36))
    approval_policy_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    retry_policy_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    misfire_policy: Mapped[str] = mapped_column(
        String(16), nullable=False, default=MISFIRE_SKIP
    )
    concurrency_policy: Mapped[str] = mapped_column(
        String(16), nullable=False, default=CONCURRENCY_SKIP
    )
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=180)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    start_at: Mapped[datetime | None] = mapped_column(DateTime)
    end_at: Mapped[datetime | None] = mapped_column(DateTime)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)


class ScheduleRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "schedule_runs"

    schedule_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=RUN_QUEUED)
    request_payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    response_summary: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
