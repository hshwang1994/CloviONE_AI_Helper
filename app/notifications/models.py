"""In-app notifications (spec §13.5, §21.16)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, UUIDPrimaryKeyMixin, utcnow

# "누구를 위한 알림인가" (0051). 관리자 콘솔 전용 운영 알림(백업 실패, 러너 장애 등)과
# 그 사람 개인 알림(티켓 배정, 문서 생성, 채팅 멘션 등)이 같은 type 자유 텍스트 컬럼 하나에
# 섞여 있어 벨/목록 화면이 둘을 구분할 방법이 없었다 — 관리자이자 사용자인 사람의 알림
# 목록에 "내 일"과 "관리자로서 처리할 일"이 뒤섞여 나왔다. 값은 이 둘뿐이다(닫힌 집합이라
# 자유 텍스트로 두지 않는다 — 오타가 나면 그 알림은 어느 탭에도 안 잡힌다).
AUDIENCE_USER = "user"
AUDIENCE_ADMIN = "admin"
AUDIENCES: frozenset[str] = frozenset({AUDIENCE_USER, AUDIENCE_ADMIN})


class Notification(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        # `user_id` 단일 인덱스는 이미 있지만 안읽음 개수 질의는
        # `user_id = ? AND read_at IS NULL` 이고 **모든 화면에서 60초마다** 폴링된다.
        # 복합이라야 뜻이 있다.
        Index("ix_notifications_user_unread", "user_id", "read_at"),
    )

    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    # NOT NULL + 서버 기본값 — 0048(board_posts.kind)과 같은 이유다: nullable로 두면
    # `audience = 'user'` 조건이 NULL 행을 못 골라 이 컬럼이 생기기 전 알림들이 어느 탭에도
    # 안 잡힌다. 기본값은 'user' — 관리자 전용 발송(notify_admins)만 명시적으로 'admin'을
    # 채운다(app/notifications/service.py), 나머지 발송 경로는 전부 개인 알림이다.
    audience: Mapped[str] = mapped_column(
        String(16), nullable=False, default=AUDIENCE_USER, server_default=AUDIENCE_USER,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime)
    related_object_type: Mapped[str | None] = mapped_column(String(64))
    related_object_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )
