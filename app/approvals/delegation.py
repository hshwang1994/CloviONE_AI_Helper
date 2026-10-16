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

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy import text as sa_text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session

from app.approvals.models import (
    APPROVAL_PENDING,
    DEFAULT_SLA_HOURS,
    Approval,
    ApprovalDelegation,
)
from app.core.authz import CONSOLE_WRITE_ROLES, ROLE_AUDITOR
from app.core.db import is_serialization_conflict
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.users.models import User

# 한 번의 위임이 가질 수 있는 최대 길이. 무기한 위임은 위임이 아니라 승격이다.
MAX_DELEGATION_DAYS = 90

# 저장은 naive UTC 이고(저장소 전역 규약) 사람이 읽는 시각은 Asia/Seoul 이다(§불변 9).
# 서버가 **완성된 문장**을 만드는 자리(알림 본문·겹침 409·권한 없음 403)에서는 그 변환을
# 화면에 미룰 수 없다 — 미뤄 두었더니 대리인이 자기 권한 기간을 하루 어긋나게 알았고,
# 겹침 409 는 실제와 9시간 다른 창을 알려 줘 관리자가 그 값을 믿고 다시 시도해도 또 409 였다.
_KST = ZoneInfo("Asia/Seoul")


def _kst(value: datetime) -> datetime:
    """저장된 naive UTC 시각 → 사람이 읽는 KST(app/quotas/service.py 와 같은 관용)."""
    return value.replace(tzinfo=timezone.utc).astimezone(_KST)


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
            # 「스스로 끝났다」와 「관리자가 거뒀다」는 다른 사건이라 다른 문장을 준다. 회수된
            # 위임에 `ends_at` 을 말하면 아직 오지 않은 시각을 「끝난 시각」으로 알려 주게 된다.
            if expired.revoked_at is not None:
                raise ForbiddenError(
                    f"관리자가 {_kst(expired.revoked_at):%m월 %d일 %H시}에 위임을 거두었습니다. "
                    "계속 승인하려면 위임을 다시 받아야 합니다."
                )
            raise ForbiddenError(
                f"위임 기간이 {_kst(expired.ends_at):%m월 %d일 %H시}에 끝났습니다. "
                "계속 승인하려면 위임을 다시 받아야 합니다."
            )
        raise ForbiddenError("승인 권한이 없습니다. 위임을 받으면 대신 승인할 수 있습니다.")
    return on_behalf_of


def _most_recent_expired_delegation(
    db: Session, user_id: str, now: datetime
) -> ApprovalDelegation | None:
    """이 사람에게 **끝난** 위임이 있었나 (실제로 가장 최근에 끝난 것).

    회수(`revoked_at`)된 것도 포함한다 — 당사자 입장에서는 '더 이상 못 한다' 로 같고,
    회수 사실을 숨길 이유가 없다.

    정렬 키가 「실제로 끝난 시각」(`coalesce(revoked_at, ends_at)`)인 이유: `ends_at` 으로
    정렬하면 **아직 오지 않은 종료 시각을 가진 회수된 위임**이 언제나 1등이 된다. 그래서
    방금 거둔 위임을 두고 몇 달 뒤 날짜를 「끝난 시각」이라고 말하는 문구가 나갔다.
    """
    ended_at = func.coalesce(
        ApprovalDelegation.revoked_at, ApprovalDelegation.ends_at
    )
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
            .order_by(ended_at.desc(), ApprovalDelegation.id.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


def validate_window(starts_at: datetime, ends_at: datetime, now: datetime) -> None:
    if ends_at <= starts_at:
        raise ValidationAppError("종료 시각은 시작 시각보다 뒤여야 합니다.")
    if (ends_at - starts_at) > timedelta(days=MAX_DELEGATION_DAYS):
        raise ValidationAppError(f"위임 기간은 최대 {MAX_DELEGATION_DAYS}일입니다.")
    # 이미 끝난 창으로 만든 위임은 만들어지는 순간 「종료」다 — 아무에게도 권한을 주지 않으면서
    # 대리인에게는 「승인할 수 있습니다」 통보가 나가고 관리자는 성공 토스트를 본다. 연도 오타
    # 하나가 「위임했는데 왜 결재가 안 되나」로 조용히 끝나던 자리라 여기서 막는다.
    if ends_at <= now:
        raise ValidationAppError(
            "이미 지난 기간으로는 위임할 수 없습니다. 종료 시각을 지금보다 뒤로 정해야 합니다."
        )


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
    validate_window(starts_at, ends_at, now)
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
    # 감사자는 이 저장소가 「읽기 전용 가지」로 정의한 역할이라 쓰기 역할 묶음에 절대 들어가지
    # 않는다(app/core/authz.py). 위임은 결재 **권한**을 빌려주는 것이므로, 감사자를 대리인으로
    # 두면 자기가 감사할 결정을 스스로 내리게 되고 권한 매트릭스가 화면에서 말하는 것과 실제가
    # 달라진다 — 위임이 그 경계를 도는 유일한 문이 되면 안 된다.
    if delegate.role == ROLE_AUDITOR:
        raise ValidationAppError(
            "감사자에게는 승인 권한을 위임할 수 없습니다. 감사자는 읽기 전용 역할입니다."
        )
    _lock_delegator(db, delegator.id)
    overlapping = _overlapping_live_delegation(
        db, delegator.id, delegate.id, starts_at=starts_at, ends_at=ends_at, now=now
    )
    if overlapping is not None:
        raise ConflictError(
            f"{delegate.display_name}님에게는 이미 "
            f"{_kst(overlapping.starts_at):%m월 %d일 %H시}부터 "
            f"{_kst(overlapping.ends_at):%m월 %d일 %H시}까지 "
            "위임한 기간이 있습니다. 겹치지 않는 기간으로 다시 정해야 합니다."
        )
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
            f"{_kst(starts_at):%m월 %d일}부터 {_kst(ends_at):%m월 %d일}까지 승인할 수 있습니다."
        ),
        related=("approval_delegation", row.id),
        now=now,
    )
    return row


# 겹침 검사와 삽입 사이가 열려 있으면(커밋은 요청 끝에 한 번뿐이다) 동시에 들어온 두 요청이
# 각자 「겹치는 것 없음」을 보고 둘 다 넣는다 — 실측으로 4발 전부 201 이었다. 그러면 관리자가
# 목록에서 한 장을 거두고 「권한을 회수했다」고 믿는 순간 쌍둥이 한 장이 그대로 결재 권한을
# 준다. 회수가 거짓말을 하지 않게 하는 것이 겹침 금지의 목적이므로, 그 목적이 경합 한 번에
# 무너지면 안 된다.
_DELEGATOR_LOCK_TIMEOUT_MS = 5000


def _lock_delegator(db: Session, delegator_id: str) -> None:
    """이 위임자의 계정 행을 잠근다 — 같은 위임자에 대한 생성은 한 번에 하나만 지난다.

    겹침 규칙은 (위임자, 대리자) 짝에 걸리므로 **위임자 행**을 문으로 삼으면 충분하다.
    아직 없는 행은 잠글 수 없어(팬텀) 위임 표 자체를 잠글 수는 없다 — 부모 행을 잠그는 것이
    이 상황의 정석이다.

    **이것은 응용 계층의 문이다.** 진짜 승자 판정은 DB 가 해야 한다 —
    `EXCLUDE USING gist (delegator_user_id WITH =, delegate_user_id WITH =,
    tsrange(starts_at, ends_at) WITH &&) WHERE (revoked_at IS NULL)` 배제 제약이 그 답이고,
    그것은 마이그레이션이 필요해 이 수정의 범위 밖이다(승인 생성 경로가 부분 유일 인덱스로
    이미 그 형태를 쓴다). 제약이 생기면 이 잠금은 그대로 두어도 되고 걷어도 된다.
    """
    db.execute(sa_text(f"SET LOCAL lock_timeout = '{_DELEGATOR_LOCK_TIMEOUT_MS}ms'"))
    try:
        db.execute(
            select(User.id).where(User.id == delegator_id).with_for_update()
        ).scalar_one_or_none()
    except (OperationalError, DBAPIError) as exc:
        # `55P03 lock_not_available` — 다른 생성이 아직 커밋 전이다. 문구가 아니라 SQLSTATE 로
        # 가른다(`app/approvals/service.py::lock_for_decision` 과 같은 이유): PG 는 오류 문구를
        # 서버 로캘로 쓰므로 영어 "lock" 대조는 한국어 로캘에서 통째로 뒤집힌다.
        if not is_serialization_conflict(exc):
            raise
        raise ConflictError(
            "같은 사람의 위임이 동시에 추가되고 있습니다. 잠시 뒤 다시 시도해 주세요."
        ) from exc


def _overlapping_live_delegation(
    db: Session,
    delegator_id: str,
    delegate_id: str,
    *,
    starts_at: datetime,
    ends_at: datetime,
    now: datetime,
) -> ApprovalDelegation | None:
    """같은 위임자→대리자 짝에 이미 살아 있고 창이 겹치는 위임 (가장 이른 것).

    ## 왜 겹침을 막는가

    같은 짝의 위임이 두 장 겹쳐 있으면 회수가 거짓말을 한다 — 관리자가 한 장을 거둬도
    다른 한 장이 그대로 권한을 준다. 화면은 「회수됨」을 보여 주는데 그 사람은 계속
    결재한다. 위임은 감사 근거(`decided_on_behalf_of`)라, 같은 권한이 두 근거로 남는 것도
    되짚을 때 혼란만 만든다.

    ## 무엇을 «살아 있다» 로 보는가

    회수되지 않았고(`revoked_at IS NULL`) 아직 끝나지 않은 것(`ends_at > now`)이다.
    예약된(아직 시작 전) 위임도 포함한다 — 곧 살아날 창이므로 겹치면 같은 문제가 된다.
    끝난 위임과 회수된 위임은 비운 자리라 다시 채울 수 있다.

    창은 반열림 `[starts_at, ends_at)` 이다 — 한 창이 끝나는 시각에 다음 창이 시작하는
    것은 겹침이 아니다(`state()` 가 `now >= ends_at` 을 «끝남» 으로 보는 것과 같은 경계).
    """
    return (
        db.execute(
            select(ApprovalDelegation)
            .where(
                ApprovalDelegation.delegator_user_id == delegator_id,
                ApprovalDelegation.delegate_user_id == delegate_id,
                ApprovalDelegation.revoked_at.is_(None),
                ApprovalDelegation.ends_at > now,
                ApprovalDelegation.starts_at < ends_at,
                ApprovalDelegation.ends_at > starts_at,
            )
            .order_by(ApprovalDelegation.starts_at.asc())
            .limit(1)
        )
        .scalars()
        .first()
    )


def revoke(db: Session, row: ApprovalDelegation, *, now: datetime) -> ApprovalDelegation:
    """거둘 수 있는 위임은 **진행 중이거나 예약된 것**뿐이다 — 화면 액션의 조건과 같다.

    예전에는 `revoked_at` 이 비어 있기만 하면 지금 시각을 찍었다. 그래서 스스로 끝난 위임에
    회수 API 를 한 번 부르면 기록의 뜻이 「저절로 닫혔다」에서 「관리자가 거뒀다」로 바뀌고,
    목록의 종료 열도 원래 종료 시각 대신 오늘로 바뀐다(`state()` 가 `revoked_at` 을 먼저 본다).
    위임은 감사 근거라 그 두 사실을 뒤바꾸면 안 된다.
    """
    current = state(row, now)
    if current == "revoked":
        raise ConflictError("이미 거둔 위임입니다.")
    if current == "ended":
        raise ConflictError("이미 끝난 위임입니다. 진행 중이거나 예약된 위임만 거둘 수 있습니다.")
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
    """기한을 넘긴 대기 승인에 대해 **그 건을 결재할 수 있는 사람에게만** 한 번 알린다.

    수신자는 요청 알림과 같은 규칙이다(`service.deciders_for`) — 결재함에 뜨지도 않는 줄을
    「기한이 지났다」고 재촉받는 사람이 없어야 한다. 제목의 요청 유형도 요청·결정 알림과
    같은 한국어 라벨을 쓴다(APPR-02): 벨에 `user.role_change` 같은 내부 코드를 띄우지 않는다.
    """
    from app.approvals.service import _request_type_ko, notify_deciders

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
        notify_deciders(
            db,
            row,
            type_="approval_overdue",
            title=f"승인 기한 초과: {_request_type_ko(row.request_type)}",
            body="기한이 지난 승인 요청이 아직 처리되지 않았습니다.",
            now=now,
        )
    db.flush()
    return len(rows)
