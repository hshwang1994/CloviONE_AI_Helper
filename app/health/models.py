"""Component heartbeats — worker/scheduler write these so the dashboard can
show liveness (spec §14.1)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base


class Heartbeat(Base):
    __tablename__ = "heartbeats"

    component: Mapped[str] = mapped_column(String(32), primary_key=True)
    last_beat_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
