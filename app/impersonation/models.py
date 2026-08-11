"""읽기 전용 임퍼소네이션 기록 (0033, PLAN Phase 6).

**이 표는 감사 산출물이다.** "누가 · 누구로 · 언제부터 언제까지 · 왜 봤는가"가 여기 남고,
같은 사실이 `audit_logs` 에도 한 줄씩 들어간다. 두 곳에 남기는 이유가 있다:
감사 로그는 시간순 흐름을 보는 곳이라 한 세션의 시작과 끝이 수천 줄 떨어져 있을 수 있다.
반면 관리자가 실제로 답해야 하는 질문은 "지금 누가 남의 화면을 보고 있는가"와 "지난달에
누가 누구를 봤는가"이고, 그건 **구간 하나가 한 행**이어야 한번에 답이 나온다.

계정이 보관·삭제돼도 기록은 남아야 하므로 FK 를 걸지 않는다(감사 로그와 같은 판단).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, UUIDPrimaryKeyMixin, utcnow

# 종료 사유. 왜 끝났는지가 남아야 "관리자가 스스로 끝냈다"와 "대상 계정이 잠겨서 강제로
# 끊겼다"가 구분된다.
END_MANUAL = "manual"
END_LOGOUT = "logout"
END_TARGET_UNAVAILABLE = "target_unavailable"
END_EXPIRED = "expired"


class ImpersonationSession(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "impersonation_sessions"

    actor_user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    target_user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500))
    client_ip: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, index=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    ended_reason: Mapped[str | None] = mapped_column(String(32))
    # 얼마나 돌아다녔는가. 숫자 자체보다 "0인데 30분 열려 있었다" 같은 이상을 보기 위한 값이다.
    read_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 막힌 쓰기 시도 횟수. 0이 아니면 그 관리자는 임퍼소네이션 중에 쓰기를 시도했다는 뜻이고,
    # 그건 감사가 알아야 할 사실이다(실수든 아니든).
    blocked_write_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    @property
    def active(self) -> bool:
        return self.ended_at is None
