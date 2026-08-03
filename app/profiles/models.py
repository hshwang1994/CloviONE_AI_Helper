"""사용자 본인 설정과 저장된 뷰 (계획서 Phase 6 — 사용자 백로그).

두 표 모두 **본인 것만** 읽고 쓴다. 라우터는 세션 사용자 id 로만 조회하므로 스코프 필터가
따로 필요 없고, 다른 사람의 행을 가리키는 경로 자체가 없다(IDOR 표면 0).

컬럼의 의미와 설계 근거는 `alembic/versions/0032_user_preferences_saved_views.py`
docstring 에 있다 — 여기서는 반복하지 않는다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserPreference(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """사용자당 한 행. 행이 없으면 전부 기본값이다(백필하지 않는다)."""

    __tablename__ = "user_preferences"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    # ── 아바타 ────────────────────────────────────────────────────────────────
    avatar_stored_name: Mapped[str | None] = mapped_column(String(64))
    avatar_media_type: Mapped[str | None] = mapped_column(String(64))
    avatar_updated_at: Mapped[datetime | None] = mapped_column(DateTime)

    # ── 알림 설정 ─────────────────────────────────────────────────────────────
    # 콤마 구분 알림 유형 키. 파싱·직렬화는 app/profiles/prefs.py 한 곳에서만 한다.
    muted_types: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )

    # ── 방해금지 ──────────────────────────────────────────────────────────────
    dnd_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    dnd_until: Mapped[datetime | None] = mapped_column(DateTime)
    quiet_hours_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    quiet_start: Mapped[str] = mapped_column(
        String(5), nullable=False, default="22:00", server_default="22:00"
    )
    quiet_end: Mapped[str] = mapped_column(
        String(5), nullable=False, default="08:00", server_default="08:00"
    )

    # ── 첫 로그인 투어 ────────────────────────────────────────────────────────
    tour_seen_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    tour_skipped: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    tour_completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class SavedView(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """한 화면의 필터 조합에 이름을 붙인 것. `query` 는 URL 쿼리 문자열이다."""

    __tablename__ = "saved_views"
    __table_args__ = (
        UniqueConstraint("user_id", "screen_key", "name", name="uq_saved_views_user_screen_name"),
    )

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    screen_key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
