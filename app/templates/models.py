"""Automation templates (spec §21.12, §17.3)."""

from __future__ import annotations

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, JsonText, TimestampMixin, UUIDPrimaryKeyMixin

TARGET_WORKFLOW = "workflow"
TARGET_RUNNER = "runner"


class AutomationTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "automation_templates"

    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    input_schema_json: Mapped[str] = mapped_column(JsonText, nullable=False, default="{}")
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_id: Mapped[str | None] = mapped_column(String(36))
    policy_id: Mapped[str | None] = mapped_column(String(36))
    approval_policy_json: Mapped[str] = mapped_column(JsonText, nullable=False, default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str | None] = mapped_column(String(36))
