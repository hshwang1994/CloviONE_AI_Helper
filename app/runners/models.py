"""Runner Registry model (spec §21.8) + circuit-breaker state (spec §15.6)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, JsonText, TimestampMixin, UUIDPrimaryKeyMixin

MAINT_NORMAL = "normal"
MAINT_DEGRADED = "degraded"
MAINT_MAINTENANCE = "maintenance"

CIRCUIT_FAILURE_THRESHOLD = 5
CIRCUIT_COOLDOWN_SECONDS = 300


class Runner(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "runners"

    integration_id: Mapped[str | None] = mapped_column(String(36))
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    health_url: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[str | None] = mapped_column(String(64))
    capabilities_json: Mapped[str] = mapped_column(JsonText, nullable=False, default="{}")
    auth_type: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    secret_ref: Mapped[str | None] = mapped_column(String(128))
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    concurrency_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    retry_policy_json: Mapped[str] = mapped_column(JsonText, nullable=False, default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    maintenance_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default=MAINT_NORMAL
    )
    last_health_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unknown"
    )
    last_health_at: Mapped[datetime | None] = mapped_column(DateTime)
    config_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    owner: Mapped[str | None] = mapped_column(String(120))
    tags_json: Mapped[str] = mapped_column(JsonText, nullable=False, default="[]")

    # Circuit breaker (spec §15.6)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    circuit_open_until: Mapped[datetime | None] = mapped_column(DateTime)
