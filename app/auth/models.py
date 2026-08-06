"""Server-side session records (spec §21.3) + 비밀번호 재설정 토큰 (9-9 P4).

Only the SHA-256 hash of the opaque session token is stored. 재설정 토큰도 **같은 규약**을
따른다 - 원문은 메일로만 나가고 DB 에는 해시만 남는다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, UUIDPrimaryKeyMixin, utcnow


class UserSession(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    client_ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    # ── 읽기 전용 임퍼소네이션(0033) ──────────────────────────────────────────
    # 관리자가 남의 화면을 '보는 중'이면 여기 두 칸이 채워진다. 대상의 세션을 새로 만들지
    # 않는 이유는 app/impersonation/service.py 모듈 docstring 참조 — 행위자는 끝까지
    # 관리자여야 감사가 성립한다. 둘 다 NULL 이면 평소 세션이다.
    impersonated_user_id: Mapped[str | None] = mapped_column(String(36))
    impersonation_id: Mapped[str | None] = mapped_column(String(36))

    @property
    def impersonating(self) -> bool:
        return self.impersonated_user_id is not None


# 재설정 토큰의 용도. 규칙(1회용, 만료, 해시 저장)은 같고 메일 문구만 다르다.
RESET_PURPOSE_RESET = "reset"
RESET_PURPOSE_INVITE = "invite"


class PasswordResetToken(UUIDPrimaryKeyMixin, Base):
    """사용자가 스스로 비밀번호를 되찾을 때 쓰는 1회용 토큰 (9-9 P4).

    **세 가지가 전부 필요하다.** 하나라도 빠지면 메일함을 한 번 본 사람이 계정을 갖는다:

      * ``token_hash``  - 원문 미저장. DB 를 읽을 수 있는 사람이 곧 전 계정 접근이 되면 안 된다.
      * ``used_at``     - 1회용. 행을 지우지 않고 표시만 하는 이유는 "이미 쓴 토큰" 과
        "처음 보는 토큰" 을 구별해 재사용 시도를 셀 수 있게 하기 위해서다.
      * ``expires_at``  - 만료. 메일은 영원히 남는다.
    """

    __tablename__ = "password_reset_tokens"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    created_ip: Mapped[str | None] = mapped_column(String(64))
