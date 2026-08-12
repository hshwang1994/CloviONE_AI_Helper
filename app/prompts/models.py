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
    # WF1 단독 결함 — 자매 엔티티 Prompt에는 있는데 Policy에는 없어 "이 정책이 무엇을
    # 강제하는가"를 목록에서 말할 방법이 없었다(마이그레이션 0058).
    purpose: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_DRAFT)
    created_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
