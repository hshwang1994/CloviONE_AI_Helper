"""n8n Workflow Registry model (spec §21.9)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, JsonText, TimestampMixin, UUIDPrimaryKeyMixin

MODE_READ = "read"
MODE_WRITE = "write"


class Workflow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workflows"

    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    purpose: Mapped[str | None] = mapped_column(Text)
    webhook_url: Mapped[str] = mapped_column(String(500), nullable=False)
    http_method: Mapped[str] = mapped_column(String(8), nullable=False, default="POST")
    payload_schema_json: Mapped[str | None] = mapped_column(JsonText)
    response_schema_json: Mapped[str | None] = mapped_column(JsonText)
    operation_mode: Mapped[str] = mapped_column(String(8), nullable=False, default=MODE_READ)
    approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    owner: Mapped[str | None] = mapped_column(String(120))
    tags_json: Mapped[str] = mapped_column(JsonText, nullable=False, default="[]")
    last_test_status: Mapped[str | None] = mapped_column(String(16))
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime)
    config_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
