"""Server-side session records (spec §21.3).

Only the SHA-256 hash of the opaque session token is stored.
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
