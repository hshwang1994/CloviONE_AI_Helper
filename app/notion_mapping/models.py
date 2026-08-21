"""Notion user mapping (spec §12, §21.2)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, JsonText, UUIDPrimaryKeyMixin

STATUS_UNMAPPED = "unmapped"
STATUS_VERIFIED = "verified"
STATUS_CONFLICT = "conflict"

SOURCE_WORKFLOW = "workflow"
SOURCE_MANUAL = "manual"


class UserNotionMapping(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "user_notion_mappings"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), unique=True, nullable=False, index=True
    )
    notion_user_id: Mapped[str | None] = mapped_column(String(64))
    notion_email: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_UNMAPPED)
    source: Mapped[str | None] = mapped_column(String(16))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_message: Mapped[str | None] = mapped_column(Text)
    # Candidate matches captured on conflict so an admin can resolve it.
    candidates_json: Mapped[str | None] = mapped_column(JsonText)
