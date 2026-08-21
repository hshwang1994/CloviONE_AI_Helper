"""Integration Registry model (spec §21.7)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, JsonText, TimestampMixin, UUIDPrimaryKeyMixin

HEALTH_UP = "up"
HEALTH_DOWN = "down"
HEALTH_UNKNOWN = "unknown"


class Integration(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "integrations"

    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    health_url: Mapped[str | None] = mapped_column(String(500))
    auth_type: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    secret_ref: Mapped[str | None] = mapped_column(String(128))
    capabilities_json: Mapped[str] = mapped_column(JsonText, nullable=False, default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_health_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=HEALTH_UNKNOWN
    )
    last_health_at: Mapped[datetime | None] = mapped_column(DateTime)
    config_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
