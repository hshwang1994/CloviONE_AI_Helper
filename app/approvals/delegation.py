"""승인 위임 + SLA (0033, PLAN Phase 6).

## 위임이 실제로 무엇을 바꾸는가

이 저장소의 승인은 특정 결재자에게 배정되지 않는다 — `CONSOLE_WRITE_ROLES`(admin·
system_admin) 이면 누구나 결재한다. 그래서 '위임'을 "내 큐를 남에게 넘긴다"로 만들 수는
없다(넘길 큐가 없다). 대신 **권한을 빌려주는 것**으로 정의한다:

    관리자 A 가 부재하는 동안, 평소에는 결재할 수 없는 B(예: 운영자)가 결재할 수 있다.

이렇게 하면 위임이 실제로 새로운 능력을 만들고(= 켜고 끄는 의미가 있고), 그 결재는
`approvals.decided_on_behalf_of` 에 A 로 남아 감사가 성립한다. "이미 할 수 있는 사람에게
또 허락해 주는" 장식용 스위치가 되지 않는다.

## SLA

`due_at` = 요청 시각 + `DEFAULT_SLA_HOURS`. 기한을 넘긴 대기 건은 목록에서 `overdue: true`
로 표시되고, 워커가 **한 번만** 관리자에게 알린다(`sla_notified_at`). 반복 알림을 보내면
승인 큐가 밀린 날 알림이 수십 개 쌓여 아무도 안 본다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.approvals.models import (
    APPROVAL_PENDING,
    DEFAULT_SLA_HOURS,
    Approval,
    ApprovalDelegation,
)
from app.core.authz import CONSOLE_WRITE_ROLES
from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.users.models import User

# 한 번의 위임이 가질 수 있는 최대 길이. 무기한 위임은 위임이 아니라 승격이다.
MAX_DELEGATION_DAYS = 90


def due_at_for(requested_at: datetime, hours: int = DEFAULT_SLA_HOURS) -> datetime:
    return requested_at + timedelta(hours=hours)


def is_overdue(row: Approval, now: datetime) -> bool:
    return (
        row.status == APPROVAL_PENDING
        and row.due_at is not None
        and row.due_at <= now
    )


def active_delegations_for(db: Session, delegate_user_id: str, now: datetime) -> list[ApprovalDelegation]:
    """지금 이 사람이 '대신 결재할 수 있는' 위임들."""
    return list(
        db.execute(
            select(ApprovalDelegation).where(
                ApprovalDelegation.delegate_user_id == delegate_user_id,
                ApprovalDelegation.revoked_at.is_(None),
                ApprovalDelegation.starts_at <= now,
                ApprovalDelegation.ends_at > now,
            )
        )
        .scalars()
        .all()
    )


def resolve_authority(db: Session, actor: User, now: datetime) -> tuple[bool, str | None]:
    """(결재할 수 있는가, 누구를 대신하는가).

    역할로 이미 결재할 수 있으면 위임을 보지 않는다 — 대신하는 사람이 없으므로 두 번째
    값은 None 이다. 그렇지 않으면 활성 위임 중 **가장 먼저 끝나는 것**을 쓴다(가장 좁은
    권한부터 소진하는 편이 '언제까지 열려 있는가'를 예측 가능하게 한다).
    """
    if actor.role in CONSOLE_WRITE_ROLES:
        return True, None
    rows = active_delegations_for(db, actor.id, now)
    if not rows:
        return False, None
    rows.sort(key=lambda r: r.ends_at)
    return True, rows[0].delegator_user_id


def require_decider(db: Session, actor: User, now: datetime) -> str | None:
    """결재 권한 확인. 통과하면 '대신하는 사람 id'(없으면 None)를 돌려준다."""
    allowed, on_behalf_of = resolve_authority(db, actor, now)
    if not allowed:
        # 위임이 **있었는데 끝난** 경우와 애초에 없던 경우는 다른 사건이다 (X7).
        # 둘을 같은 문구로 뭉개면, 어제까지 결재하던 사람이 오늘 "권한이 없습니다" 를 보고
        # 시스템이 고장났다고 신고한다 — 실제로는 위임 기간이 끝난 것뿐이다.
        expired = _most_recent_expired_delegation(db, actor.id, now)
        if expired is not None:
            raise ForbiddenError(
                f"위임 기간이 {expired.ends_at:%m월 %d일 %H시}에 끝났습니다. "
                "계속 결재하려면 위임을 다시 받아야 합니다."
            )
        raise ForbiddenError("승인 권한이 없습니다. 위임을 받으면 대리 결재할 수 있습니다.")
    return on_behalf_of


def _most_recent_expired_delegation(
    db: Session, user_id: str, now: datetime
) -> ApprovalDelegation | None:
    """이 사람에게 **끝난** 위임이 있었나 (가장 최근 것).

    회수(`revoked_at`)된 것도 포함한다 — 당사자 입장에서는 '더 이상 못 한다' 로 같고,
    회수 사실을 숨길 이유가 없다.
    """
    return (
        db.execute(
            select(ApprovalDelegation)
            .where(
                ApprovalDelegation.delegate_user_id == user_id,
                or_(
                    ApprovalDelegation.ends_at <= now,
                    ApprovalDelegation.revoked_at.is_not(None),
                ),
            )
            .order_by(ApprovalDelegation.ends_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


def validate_window(starts_at: datetime, ends_at: datetime) -> None:
    if ends_at <= starts_at:
        raise ValidationAppError("종료 시각은 시작 시각보다 뒤여야 합니다.")
    if (ends_at - starts_at) > timedelta(days=MAX_DELEGATION_DAYS):
        raise ValidationAppError(f"위임 기간은 최대 {MAX_DELEGATION_DAYS}일입니다.")


def create(
    db: Session,
    *,
    delegator: User,
    delegate: User,
    starts_at: datetime,
    ends_at: datetime,
    reason: str | None,
    created_by: str,
    now: datetime,
    visible: frozenset[str] | None,
) -> ApprovalDelegation:
    validate_window(starts_at, ends_at)
    if visible is not None and not {delegator.id, delegate.id} <= visible:
        # 범위 밖 계정은 **없는 것과 똑같다** — 「그 사람은 있지만 당신 부서가 아닙니다」로
        # 답하면 남의 부서 명부를 id 로 열거할 수 있다(위 `get_scoped_or_404` 와 같은 이유).
        raise NotFoundError("사용자를 찾을 수 없습니다.")
    if delegator.id == delegate.id:
        raise ValidationAppError("자기 자신에게 위임할 수 없습니다.")
    # 위임하는 쪽이 애초에 결재 권한이 없으면 빌려줄 것이 없다.
    if delegator.role not in CONSOLE_WRITE_ROLES:
        raise ValidationAppError("승인 권한이 있는 계정만 위임할 수 있습니다.")
    if not delegate.active or delegate.archived_at is not None:
        raise ValidationAppError("비활성 또는 보관된 계정에는 위임할 수 없습니다.")
    row = ApprovalDelegation(
        delegator_user_id=delegator.id,
        delegate_user_id=delegate.id,
        reason=(reason or "").strip()[:500] or None,
        starts_at=starts_at,
        ends_at=ends_at,
        created_by=created_by,
        created_at=now,
    )
    db.add(row)
    db.flush()
    # 위임받은 **사실 자체**를 당사자에게 알린다 (X7). 예전에는 아무 통보가 없어서, 결재하라고
    # 권한을 준 사람이 자기에게 권한이 생긴 줄도 몰랐다. 그 상태로 승인 큐가 밀린다.
    from app.notifications.service import notify_user

    notify_user(
        db, delegate.id,
        type_="approval_delegated",
        title="승인 권한을 위임받았습니다",
        body=(
            f"{delegator.display_name}님을 대신해 "
            f"{starts_at:%m월 %d일}부터 {ends_at:%m월 %d일}까지 승인할 수 있습니다."
        ),
        related=("approval_delegation", row.id),
        now=now,
    )
    return row


def revoke(db: Session, row: ApprovalDelegation, *, now: datetime) -> ApprovalDelegation:
    if row.revoked_at is None:
        row.revoked_at = now
        db.flush()
    return row


def scope_clause(visible: frozenset[str] | None):
    """이 위임이 관리 범위 안인가. 전역(``visible is None``)이면 ``None`` = 조건 없음.

    **양쪽 다** 범위 안이어야 한다. 위임은 「A 의 권한을 B 가 쓴다」라 한쪽만 봐도 되는
    관계가 아니다 — 위임자만 보면 내 부서 사람의 권한이 남의 부서로 새는 것을 못 막고,
    대리자만 보면 남의 부서 권한이 내 부서 사람에게 들어오는 것을 못 막는다.

    ``None`` 을 돌려주는 이유는 `app/core/scope.py::scope_filter` 와 같다 — 부르는 쪽이
    `if clause is None` 을 쓸 수밖에 없어 '범위를 고려했다'가 코드에 남는다.
    """
    if visible is None:
        return None
    ids = tuple(sorted(visible))
    return ApprovalDelegation.delegator_user_id.in_(ids) & (
        ApprovalDelegation.delegate_user_id.in_(ids)
    )


def apply_scope(stmt, visible: frozenset[str] | None):
    clause = scope_clause(visible)
    return stmt if clause is None else stmt.where(clause)


def get_scoped_or_404(
    db: Session, row_id: str, visible: frozenset[str] | None
) -> ApprovalDelegation:
    """단건 — 범위 밖은 **없는 것과 똑같이 404** 다 (P-12a).

    403 은 "그 위임은 존재한다"를 알려 준다. id 를 찍어 보며 403/404 를 세면 다른 부서에
    누가 누구에게 결재를 맡겼는지를 열거할 수 있다 — 인사 정보다. 같은 파일의 승인 큐가
    이미 그 규칙을 쓰고 있었고 이쪽만 빠져 있었다.

    조건을 **조회 자체에** 붙인다(`app/approvals/service.py::get_scoped_approval_or_404`
    와 같은 관용): 먼저 꺼내 놓고 나중에 판정하면 판정을 빠뜨린 새 경로가 조용히 열린다.
    """
    row = db.execute(
        apply_scope(select(ApprovalDelegation).where(ApprovalDelegation.id == row_id), visible)
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("위임을 찾을 수 없습니다.")
    return row


def state(row: ApprovalDelegation, now: datetime) -> str:
    if row.revoked_at is not None:
        return "revoked"
    if now < row.starts_at:
        return "scheduled"
    if now >= row.ends_at:
        return "ended"
    return "active"


def view(
    row: ApprovalDelegation, now: datetime, names: dict[str, dict[str, str]] | None = None
) -> dict:
    names = names or {}
    delegator = names.get(row.delegator_user_id, {})
    delegate = names.get(row.delegate_user_id, {})
    return {
        "id": row.id,
        "delegator_user_id": row.delegator_user_id,
        "delegator_name": delegator.get("display_name"),
        "delegator_email": delegator.get("email"),
        "delegate_user_id": row.delegate_user_id,
        "delegate_name": delegate.get("display_name"),
        "delegate_email": delegate.get("email"),
        "reason": row.reason,
        "starts_at": row.starts_at.isoformat(),
        "ends_at": row.ends_at.isoformat(),
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        "state": state(row, now),
        "created_at": row.created_at.isoformat(),
    }


def notify_overdue(db: Session, *, now: datetime) -> int:
    """기한을 넘긴 대기 승인에 대해 관리자에게 **한 번만** 알린다. 알린 건수를 돌려준다."""
    from app.notifications.service import notify_approvers

    rows = (
        db.execute(
            select(Approval).where(
                Approval.status == APPROVAL_PENDING,
                Approval.due_at.is_not(None),
                Approval.due_at <= now,
                Approval.sla_notified_at.is_(None),
                # 이미 죽은(만료된) 요청까지 다시 깨우지 않는다.
                or_(Approval.expires_at.is_(None), Approval.expires_at > now),
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        row.sla_notified_at = now
        notify_approvers(
            db,
            type_="approval_overdue",
            title=f"승인 기한 초과: {row.request_type}",
            body="기한이 지난 승인 요청이 아직 처리되지 않았습니다.",
            related=("approval", row.id),
            now=now,
        )
    db.flush()
    return len(rows)
