"""Document generation records (spec §19). Tracks preview/publish lifecycle
and enforces duplicate-document prevention via a UNIQUE idempotency key."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, UUIDPrimaryKeyMixin, utcnow

MODE_PREVIEW_ONLY = "preview_only"
MODE_PREVIEW_THEN_APPROVE = "preview_then_approve"
MODE_AUTO_PUBLISH = "auto_publish"

STATUS_PENDING = "pending"
STATUS_PREVIEW_READY = "preview_ready"
STATUS_QUALITY_FAILED = "quality_failed"
STATUS_AWAITING_APPROVAL = "awaiting_approval"
STATUS_PUBLISHED = "published"
STATUS_FAILED = "failed"


class DocumentGeneration(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "document_generations"

    template_id: Mapped[str | None] = mapped_column(String(36))
    workflow_id: Mapped[str] = mapped_column(String(36), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(300), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=STATUS_PENDING)
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    preview_json: Mapped[str | None] = mapped_column(Text)
    quality_problems_json: Mapped[str | None] = mapped_column(Text)
    published_ref: Mapped[str | None] = mapped_column(String(500))
    error_message: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
