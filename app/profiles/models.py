"""사용자 본인 설정과 저장된 뷰 (계획서 Phase 6 — 사용자 백로그).

두 표 모두 **본인 것만** 읽고 쓴다. 라우터는 세션 사용자 id 로만 조회하므로 스코프 필터가
따로 필요 없고, 다른 사람의 행을 가리키는 경로 자체가 없다(IDOR 표면 0).

컬럼의 의미와 설계 근거는 `alembic/versions/0032_user_preferences_saved_views.py`
docstring 에 있다 — 여기서는 반복하지 않는다.
"""

from __future__ import annotations

import re

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# 아바타의 출처 둘. 「사진을 지웠다」와 「기본 그림을 골랐다」는 다른 사실이라 한 컬럼에
# 섞지 않는다 — 섞으면 사진을 지운 순간 골라 둔 그림도 함께 잊는다.
AVATAR_SOURCE_DEFAULT = "default"
AVATAR_SOURCE_UPLOADED = "uploaded"
AVATAR_SOURCES: tuple[str, ...] = (AVATAR_SOURCE_DEFAULT, AVATAR_SOURCE_UPLOADED)

# 기본 아바타는 **DiceBear 로 화면이 그린다**(`frontend/src/ui/DefaultAvatar.jsx`) —
# 서버는 「이 사람이 무엇을 골랐는가」만 안다. 값이 비어 있으면 사용자 id 를 씨앗으로
# 화면이 안정적으로 배정하므로, 여기 저장되는 것은 **사람이 직접 고른 값뿐**이다.
#
# 값의 모양은 `<style>:<variant>` 다. 스타일만 저장하면 「같은 스타일 안에서 다른 얼굴」을
# 고를 수 없어 후보가 다섯 개로 줄어든다 — 변형이 씨앗을 흔들어 스타일 하나에 후보를
# 1,000 개 만든다.
#
# 서버가 스타일 목록을 소유하는 이유: 모르는 값이 저장되면 그 사람은 어느 그림도 못 받는다.
# 화면이 스타일을 더할 때 이 목록도 함께 는다
# (`frontend/src/ui/default-avatar-keys-match-backend.test.js` 가 두 목록을 맞물린다).
#
# 다섯 다 **CC0 1.0** 이다. 상업적 사용이 되는 라이선스는 더 있지만 그쪽은 표시 의무가
# 따라오고, 그 의무는 다음 회차에 조용히 잊힌다.
AVATAR_DEFAULT_STYLES: tuple[str, ...] = (
    "lorelei", "notionists", "openPeeps", "pixelArt", "thumbs",
)
AVATAR_VARIANT_MAX = 999
_AVATAR_KEY_RE = re.compile(r"^([A-Za-z]+):(\d{1,3})$")


def is_known_avatar_key(value: str) -> bool:
    """`<style>:<variant>` 이고 스타일이 어휘 안인가.

    변형의 상한을 함께 보는 이유: 값을 안 보면 `pixelArt:999999` 같은 것이 컬럼 길이를
    넘거나, 넘지 않으면 화면이 못 그리는 값으로 조용히 저장된다.
    """
    m = _AVATAR_KEY_RE.match(value or "")
    if m is None:
        return False
    return m.group(1) in AVATAR_DEFAULT_STYLES and int(m.group(2)) <= AVATAR_VARIANT_MAX


class UserPreference(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """사용자당 한 행. 행이 없으면 전부 기본값이다(백필하지 않는다)."""

    __tablename__ = "user_preferences"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    # ── 아바타 ────────────────────────────────────────────────────────────────
    #
    # 사진과 기본 아바타는 **다른 축**이다. 사진을 지워도 이 사람이 고른 기본 그림은
    # 남아야 하고, 기본 그림을 골라 뒀다고 사진이 사라지면 안 된다.
    #
    #   avatar_source        `default` 면 그림, `uploaded` 면 사진. 무엇을 보여 줄지 정한다
    #   avatar_default_key   고른 기본 그림. 비어 있으면 사용자 id 로 안정 배정한다
    #   avatar_stored_name   서버가 지은 저장 이름. 업로드 파일명을 경로로 쓰지 않는다
    #
    # 자르기 값 셋은 **원본을 자른 자리**다. 표시용 썸네일은 서버가 이 값으로 만들고,
    # 원본은 그대로 남는다 — 다시 자를 때 원본이 없으면 이미 자른 그림을 또 자르게 되고
    # 그때마다 화질이 떨어진다.
    avatar_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="default", server_default="default"
    )
    avatar_default_key: Mapped[str | None] = mapped_column(String(32))
    avatar_stored_name: Mapped[str | None] = mapped_column(String(64))
    avatar_media_type: Mapped[str | None] = mapped_column(String(64))
    # 표시용 썸네일. 원본과 **다른 파일**이다 — 원본을 매번 줄여 보내면 20px 목록 한 줄에
    # 몇 MB 가 실린다.
    avatar_thumb_name: Mapped[str | None] = mapped_column(String(64))
    # 원본의 어느 사각형을 잘랐는가. 원본 짧은 변을 1.0 으로 본 비율이라 원본 해상도가
    # 달라져도 뜻이 안 변한다.
    avatar_crop_x: Mapped[float | None] = mapped_column(Float)
    avatar_crop_y: Mapped[float | None] = mapped_column(Float)
    avatar_crop_zoom: Mapped[float | None] = mapped_column(Float)
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
