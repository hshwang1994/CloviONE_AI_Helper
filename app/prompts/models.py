"""Prompt versions (spec §21.10). One row per version — published content is
never overwritten (spec §17.1)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, UUIDPrimaryKeyMixin, utcnow

STATUS_DRAFT = "draft"
STATUS_TEST = "test"
STATUS_REVIEW = "review"
STATUS_PUBLISHED = "published"
STATUS_ARCHIVED = "archived"

# Lifecycle (spec §17.1). Rollback = republish an old version as a NEW version.
VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    STATUS_DRAFT: frozenset({STATUS_TEST, STATUS_ARCHIVED}),
    STATUS_TEST: frozenset({STATUS_REVIEW, STATUS_DRAFT, STATUS_ARCHIVED}),
    STATUS_REVIEW: frozenset({STATUS_PUBLISHED, STATUS_DRAFT, STATUS_ARCHIVED}),
    STATUS_PUBLISHED: frozenset({STATUS_ARCHIVED}),
    STATUS_ARCHIVED: frozenset(),
}


class Prompt(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "prompts"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_prompts_name_version"),)

    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    purpose: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_DRAFT)
    runner_id: Mapped[str | None] = mapped_column(String(36))
    created_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)


class Policy(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "policies"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_policies_name_version"),)

    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_DRAFT)
    created_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
