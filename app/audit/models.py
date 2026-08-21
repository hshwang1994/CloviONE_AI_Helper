"""Audit log model (spec §21.19)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, JsonText, UUIDPrimaryKeyMixin, utcnow


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_object_id", "object_id"),
    )

    user_id: Mapped[str | None] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    object_id: Mapped[str | None] = mapped_column(String(64))
    before_json: Mapped[str | None] = mapped_column(JsonText)
    after_json: Mapped[str | None] = mapped_column(JsonText)
    result: Mapped[str] = mapped_column(String(16), nullable=False, default="success")
    client_ip: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )
