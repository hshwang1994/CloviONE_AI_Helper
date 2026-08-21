"""Approval requests (spec §20, §21.15)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, JsonText, UUIDPrimaryKeyMixin, utcnow

APPROVAL_PENDING = "pending"
APPROVAL_APPROVED = "approved"
APPROVAL_REJECTED = "rejected"
APPROVAL_EXPIRED = "expired"
APPROVAL_CANCELLED = "cancelled"

DEFAULT_EXPIRY_HOURS = 72

# SLA 기본 기한(시간). `DEFAULT_EXPIRY_HOURS`(72)보다 짧다 — 만료는 '요청이 죽는 시각'이고
# 기한은 '사람이 답해야 하는 시각'이라 같을 수 없다. 둘이 같으면 기한 초과 표시가 만료와
# 동시에 뜨고, 그때는 이미 늦었다는 뜻이라 아무 쓸모가 없다.
DEFAULT_SLA_HOURS = 24


class Approval(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "approvals"

    # 같은 (request_type, object_id) 에 payload 가 다른 pending 요청은 **의도적으로**
    # 여러 개 있을 수 있다(예: 다른 역할로의 재요청 — create_approval 의 주석 참고).
    # 그래서 유일성은 (request_type, object_id) 만이 아니라 request_payload_json 까지
    # 묶어야 한다 — 그래야 '완전히 같은 내용의 pending 요청이 두 번 만들어지는' 동시
    # 요청(더블클릭, 폼 재제출)만 막고 의도된 재요청은 그대로 허용한다.
    __table_args__ = (
        Index(
            "ux_approvals_pending_dedup",
            "request_type",
            "object_id",
            "request_payload_json",
            unique=True,
            # `sqlite_where=` 였다. PG 에서 그 키워드는 **조용히 무시되고**, 남는 것은
            # 전체 유니크다 — 그러면 의도된 재요청(다른 역할로 다시 올리기)까지 "이미
            # 있습니다"로 막힌다. 원인은 마이그레이션 파일 안에 있고 증상은 화면에 있다.
            postgresql_where=text("status = 'pending'"),
        ),
    )

    request_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(36), nullable=False)
    approver_id: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=APPROVAL_PENDING, index=True
    )
    request_payload_json: Mapped[str] = mapped_column(JsonText, nullable=False, default="{}")
    decision_comment: Mapped[str | None] = mapped_column(Text)
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    # ── SLA (0033) ────────────────────────────────────────────────────────────
    # `expires_at` 과 다르다: 만료는 **요청이 죽는 시각**, `due_at` 은 **사람이 답해야 하는
    # 기한**이다. 기한을 넘겨도 요청은 살아 있고 결재할 수 있다 — 다만 화면에 '기한 초과'로
    # 표시되고 관리자에게 한 번 알림이 간다. 한 컬럼으로 합치면 "72시간 뒤 죽는다"와
    # "24시간 안에 답해라"를 동시에 말할 수 없다.
    due_at: Mapped[datetime | None] = mapped_column(DateTime)
    sla_notified_at: Mapped[datetime | None] = mapped_column(DateTime)
    # 위임으로 결재했다면 누구를 대신한 것인가(ApprovalDelegation).
    decided_on_behalf_of: Mapped[str | None] = mapped_column(String(36))


class ApprovalDelegation(UUIDPrimaryKeyMixin, Base):
    """부재 시 대리 승인자 (0033, PLAN Phase 6).

    **이 표는 권한을 빌려준다.** `delegate_user_id` 는 위임 창(starts_at~ends_at) 동안
    `CONSOLE_WRITE_ROLES` 가 아니어도 승인/거절을 할 수 있다. 그 결재는 `approvals` 행에
    `decided_on_behalf_of=delegator_user_id` 로 남아, 나중에 "누가 무슨 권한으로 이걸
    승인했나"를 되짚을 수 있다.

    창을 스위치가 아니라 **시각 두 개**로 잡는 이유: on/off 로 만들면 휴가에서 돌아와 끄는
    것을 잊는 순간 빌려준 권한이 영구히 남는다. 시작·종료를 미리 못 박으면 저절로 닫힌다.
    """

    __tablename__ = "approval_delegations"

    delegator_user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    delegate_user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(String(500))
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
