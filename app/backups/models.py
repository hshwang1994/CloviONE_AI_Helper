"""Backup records (spec §21.20)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, UUIDPrimaryKeyMixin, utcnow

STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_VERIFIED = "verified"
STATUS_FAILED = "failed"


class Backup(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "backups"

    backup_type: Mapped[str] = mapped_column(String(32), nullable=False, default="sqlite")
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_RUNNING)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    checksum: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_message: Mapped[str | None] = mapped_column(Text)
