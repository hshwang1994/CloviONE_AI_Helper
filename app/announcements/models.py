"""공지 배너 (0033, PLAN Phase 6).

관리자가 띄우고 **사용자가 닫으면 다시 안 뜬다.** 닫힘 상태를 localStorage 에 두지 않는
이유: 사용자가 공용 PC 두 대를 쓰면 같은 공지를 두 번 닫아야 하고, 브라우저 데이터를
지우면 몇 주 전 공지가 되살아난다. 서버에 남기면 계정을 따라다닌다.

`dismissible=False` 인 공지는 닫기 버튼이 없다(점검 예고처럼 반드시 보여야 하는 것).
그런 공지는 `ends_at` 으로 스스로 사라지게 하는 것이 원칙이다 — 닫을 수도 없고 끝나지도
않는 배너는 화면 위쪽을 영구히 먹는다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, UUIDPrimaryKeyMixin, utcnow

LEVEL_INFO = "info"
LEVEL_WARNING = "warning"
LEVEL_CRITICAL = "critical"
ALL_LEVELS = (LEVEL_INFO, LEVEL_WARNING, LEVEL_CRITICAL)

AUDIENCE_ALL = "all"
AUDIENCE_ADMIN = "admin"
ALL_AUDIENCES = (AUDIENCE_ALL, AUDIENCE_ADMIN)


class Announcement(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "announcements"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    level: Mapped[str] = mapped_column(String(16), nullable=False, default=LEVEL_INFO)
    audience: Mapped[str] = mapped_column(String(16), nullable=False, default=AUDIENCE_ALL)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    dismissible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    link_url: Mapped[str | None] = mapped_column(String(500))
    link_label: Mapped[str | None] = mapped_column(String(80))
    created_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )


class AnnouncementDismissal(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "announcement_dismissals"
    __table_args__ = (
        UniqueConstraint("announcement_id", "user_id", name="uq_announcement_dismissal"),
    )

    announcement_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    dismissed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
