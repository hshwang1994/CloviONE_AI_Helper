"""In-app notification provider (spec §7.3 initial implementation, §13.5).

Future Email/Teams providers implement the same notify() shape and get
fanned out alongside (spec §13.5 마지막 문단).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.notifications.models import AUDIENCE_ADMIN, AUDIENCE_USER, Notification
from app.users.models import ROLE_ADMIN, ROLE_SYSTEM_ADMIN, User

# 유형 자체가 명백히 관리자 전용인 이벤트 (0051). notify_admins가 이미 이 유형들만 보내
# audience="admin"을 넘기지만, 그건 "이 함수를 거쳐 갔다"는 사실에 기대는 것이다. 나중에
# 실수로 notify_user를 직접 호출해 같은 유형을 보내도(또는 새 호출부가 생겨도) 사용자
# 알림 벨에 새지 않도록 유형 자체로 한 번 더 못박는다. job_failed는 여기 넣지 않는다 —
# app/jobs/worker.py가 job.user_id 한 명(신청자 본인)에게만 보내는 개인 알림이지 관리자
# 팬아웃이 아니다.
_ADMIN_ONLY_TYPES = frozenset({"backup_failed", "runner_unavailable"})


def _resolve_audience(type_: str, audience: str) -> str:
    return AUDIENCE_ADMIN if type_ in _ADMIN_ONLY_TYPES else audience


def notify_user(
    db: Session,
    user_id: str,
    *,
    type_: str,
    title: str,
    body: str | None = None,
    related: tuple[str, str] | None = None,
    now: datetime,
    audience: str = AUDIENCE_USER,
) -> Notification:
    row = Notification(
        user_id=user_id,
        type=type_,
        title=title[:200],
        body=body,
        related_object_type=related[0] if related else None,
        related_object_id=related[1] if related else None,
        audience=_resolve_audience(type_, audience),
        created_at=now,
    )
    db.add(row)
    db.flush()
    return row


def notify_admins(
    db: Session,
    *,
    type_: str,
    title: str,
    body: str | None = None,
    related: tuple[str, str] | None = None,
    now: datetime,
) -> int:
    admins = (
        db.execute(
            select(User).where(
                User.role.in_([ROLE_ADMIN, ROLE_SYSTEM_ADMIN]), User.active.is_(True)
            )
        )
        .scalars()
        .all()
    )
    for admin in admins:
        notify_user(
            db, admin.id, type_=type_, title=title, body=body, related=related, now=now,
            # 관리자 전용 발송 — 개인 알림과 섞이면 안 된다(0051).
            audience=AUDIENCE_ADMIN,
        )
    return len(admins)


def approver_user_ids(db: Session, *, now: datetime) -> list[str]:
    """**지금 결재할 수 있는 사람 전원** = 관리자 ∪ 활성 위임을 받은 사람 (X7).

    "누가 결재할 수 있는가" 의 정의는 `delegation.resolve_authority` 한 곳에 있다.
    여기서 그 규칙을 다시 쓰지 않고 **활성 위임 표를 그대로 읽는다** — 두 벌이 되면
    한쪽만 고쳐지고, 그때 증상은 "어떤 사람만 알림을 못 받는다" 라 찾기가 매우 어렵다.

    **목록을 함수로 뽑아 둔 이유**(9-9 P4): 승인 요청을 메일로도 알리게 되면서 수신자
    목록이 필요한 곳이 둘이 됐다. 각자 조회를 쓰면 `notify_admins` 만 부르던 예전 결함
    (피위임자는 admin 이 아니라 영원히 못 받는다)이 메일 쪽에서 그대로 되살아난다.

    반환 순서는 관리자 먼저, 그다음 피위임자다(중복 없음).
    """
    from app.approvals.models import ApprovalDelegation

    admin_ids = list(
        db.execute(
            select(User.id).where(
                User.role.in_([ROLE_ADMIN, ROLE_SYSTEM_ADMIN]), User.active.is_(True)
            )
        ).scalars().all()
    )
    delegate_ids = set(
        db.execute(
            select(ApprovalDelegation.delegate_user_id).where(
                ApprovalDelegation.revoked_at.is_(None),
                ApprovalDelegation.starts_at <= now,
                ApprovalDelegation.ends_at > now,
            )
        ).scalars().all()
    )
    if not delegate_ids:
        return admin_ids
    # 이미 관리자인 사람은 두 번 받지 않는다(위임은 역할과 무관하게 걸 수 있다).
    extra = list(
        db.execute(
            select(User.id).where(
                User.id.in_(delegate_ids - set(admin_ids)), User.active.is_(True)
            )
        ).scalars().all()
    )
    return admin_ids + extra


def notify_approvers(
    db: Session,
    *,
    type_: str,
    title: str,
    body: str | None = None,
    related: tuple[str, str] | None = None,
    now: datetime,
) -> int:
    """결재할 수 있는 사람 전원에게 화면 알림. 대상 정의는 `approver_user_ids` 한 곳이다.

    audience는 기본값('user')을 그대로 쓴다(0051) — 결재는 관리자만이 아니라 활성 위임을
    받은 일반 사용자도 하고, `app/profiles/prefs.py` 도 "내가 승인해야 할 건" 이라고
    개인 할 일로 설명한다. notify_admins처럼 "관리자 전용 팬아웃"이 아니라 "이 사람에게
    할당된 개인 업무"에 더 가깝다.
    """
    recipients = approver_user_ids(db, now=now)
    for uid in recipients:
        notify_user(
            db, uid, type_=type_, title=title, body=body, related=related, now=now
        )
    return len(recipients)


def notify_active_users(
    db: Session,
    *,
    type_: str,
    title: str,
    body: str | None = None,
    related: tuple[str, str] | None = None,
    now: datetime,
) -> int:
    """notify_admins와 같은 팬아웃이지만 역할 제한 없이 활성 사용자 전체 대상이다 —
    유지보수 공지처럼 일반 사용자도 알아야 하는 이벤트에 쓴다(spec §13.5).

    audience는 기본값('user')을 그대로 쓴다(0051) — 이름과 달리 "관리자용"이 아니라
    "역할 제한 없는 전체 공지"라 사용자 콘솔에서 보여야 할 개인 알림에 가깝다.
    """
    users = db.execute(select(User).where(User.active.is_(True))).scalars().all()
    for user in users:
        notify_user(
            db, user.id, type_=type_, title=title, body=body, related=related, now=now
        )
    return len(users)


def mark_read(db: Session, user_id: str, notification_id: str, *, now: datetime) -> bool:
    """Idempotent: marking an already-read notification is a success (not 404).
    Returns False only when the notification does not belong to the user or
    does not exist."""
    row = db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,  # 소유권 — 남의 알림 읽음 처리 불가
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    if row.read_at is None:
        row.read_at = now
        db.flush()
    return True


def mark_all_read(db: Session, user_id: str, *, now: datetime) -> int:
    """현재 사용자의 안 읽은 알림을 한 번에 읽음 처리한다(소유권 범위 안에서만).
    반환값은 읽음 처리된 건수."""
    result = db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        .values(read_at=now)
    )
    db.flush()
    return int(result.rowcount or 0)


def unread_by_type(
    db: Session, user_id: str, *, exclude: list[str] | None = None, audience: str | None = None
) -> dict[str, int]:
    """{알림 유형: 안 읽음 수}. 사이드바 항목별 배지가 이 값을 쓴다 (사용자 지적 S2).

    예전에는 합계(`unread`)만 돌려줬다. 그러면 화면은 "안 읽은 것이 12건" 까지만 알 수 있고
    **어느 메뉴에 생긴 일인지**는 모른다 — 사용자가 요구한 "왼쪽 사이드에 신규 표시" 를
    할 수가 없었다. 종류별로 세어 돌려주면 화면이 메뉴에 나눠 붙인다.

    `exclude` 는 뮤트한 유형이다. `unread_count_excluding` 과 같은 원칙으로 **빼는 것은
    '지금 눈길을 끌 것인가' 하나뿐**이고, 알림 자체는 목록에 그대로 남는다.

    `audience` 는 선택 필터다(0051). None(기본값)이면 예전과 똑같이 전체를 센다 — 기존
    호출부(방해금지 배지)의 계약을 건드리지 않는다.
    """
    from sqlalchemy import func

    stmt = (
        select(Notification.type, func.count())
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        .group_by(Notification.type)
    )
    if exclude:
        stmt = stmt.where(Notification.type.notin_(exclude))
    if audience:
        stmt = stmt.where(Notification.audience == audience)
    return {t: int(n) for t, n in db.execute(stmt).all()}


def mark_types_read(db: Session, user_id: str, types: list[str], *, now: datetime) -> int:
    """그 유형들의 안 읽은 알림을 읽음 처리한다. 반환값은 처리 건수.

    사용자 지적 S2 의 뒷절반: "확인하면 자동으로 없애는 형태로". 화면을 열었다는 것은
    그 종류의 알림을 확인했다는 뜻이므로, 그 화면이 진입 시 자기 유형을 읽음 처리한다.
    **폴링이 아니라 화면 진입 이벤트**다 — 폴링으로 지우면 열지도 않은 알림이 사라진다.

    유형 목록이 비면 아무 일도 하지 않는다(빈 목록을 '전부'로 해석하면 화면 하나를 여는
    것이 모든 알림을 지우는 사고가 된다).
    """
    if not types:
        return 0
    result = db.execute(
        update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
            Notification.type.in_(types),
        )
        .values(read_at=now)
    )
    db.flush()
    return int(result.rowcount or 0)


def unread_count(db: Session, user_id: str, *, audience: str | None = None) -> int:
    """전체(또는 audience로 좁힌) 안 읽음 총계.

    `audience` 는 선택 필터다(0051) — None(기본값)이면 예전과 똑같은 총계를 돌려준다,
    벨 배지 등 기존 계약을 지키는 호출부는 인자를 안 넘기면 그만이다.
    """
    from sqlalchemy import func

    stmt = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
    )
    if audience:
        stmt = stmt.where(Notification.audience == audience)
    return db.execute(stmt).scalar_one()


def unread_count_excluding(
    db: Session, user_id: str, types: list[str], *, audience: str | None = None
) -> int:
    """배지에 세는 안 읽음 — 사용자가 뮤트한 유형만 뺀다.

    **알림 자체를 지우거나 안 만드는 것이 아니다.** 뮤트한 유형도 `unread_count` 에는
    그대로 잡히고 목록에도 그대로 나온다. 여기서 빠지는 것은 '지금 눈길을 끌 것인가'
    하나뿐이다 — 방해금지와 같은 원칙이다(app/profiles/prefs.py 모듈 docstring).

    `audience` 는 선택 필터다(0051), `unread_count`와 같은 기본값 규칙을 따른다.
    """
    if not types:
        return unread_count(db, user_id, audience=audience)
    from sqlalchemy import func

    stmt = (
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
            Notification.type.notin_(types),
        )
    )
    if audience:
        stmt = stmt.where(Notification.audience == audience)
    return db.execute(stmt).scalar_one()
