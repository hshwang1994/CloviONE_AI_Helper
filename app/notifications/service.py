"""In-app notification provider (spec §7.3 initial implementation, §13.5).

Future Email/Teams providers implement the same notify() shape and get
fanned out alongside (spec §13.5 마지막 문단).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.notifications.models import Notification
from app.users.models import ROLE_ADMIN, ROLE_SYSTEM_ADMIN, User


def notify_user(
    db: Session,
    user_id: str,
    *,
    type_: str,
    title: str,
    body: str | None = None,
    related: tuple[str, str] | None = None,
    now: datetime,
) -> Notification:
    row = Notification(
        user_id=user_id,
        type=type_,
        title=title[:200],
        body=body,
        related_object_type=related[0] if related else None,
        related_object_id=related[1] if related else None,
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
            db, admin.id, type_=type_, title=title, body=body, related=related, now=now
        )
    return len(admins)


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
    유지보수 공지처럼 일반 사용자도 알아야 하는 이벤트에 쓴다(spec §13.5)."""
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


def unread_count(db: Session, user_id: str) -> int:
    from sqlalchemy import func

    return db.execute(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
    ).scalar_one()
