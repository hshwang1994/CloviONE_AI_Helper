"""공지 조회·닫기 (0033, PLAN Phase 6)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.announcements.models import (
    ALL_AUDIENCES,
    ALL_LEVELS,
    AUDIENCE_ADMIN,
    AUDIENCE_ALL,
    Announcement,
    AnnouncementDismissal,
)
from app.core.errors import ValidationAppError


def validate(level: str, audience: str) -> None:
    if level not in ALL_LEVELS:
        raise ValidationAppError(f"level 은 {', '.join(ALL_LEVELS)} 중 하나여야 합니다.")
    if audience not in ALL_AUDIENCES:
        raise ValidationAppError(f"audience 는 {', '.join(ALL_AUDIENCES)} 중 하나여야 합니다.")


def in_window(row: Announcement, now: datetime) -> bool:
    if row.starts_at is not None and now < row.starts_at:
        return False
    if row.ends_at is not None and now >= row.ends_at:
        return False
    return True


def view(row: Announcement) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "body": row.body,
        "level": row.level,
        "audience": row.audience,
        "starts_at": row.starts_at.isoformat() if row.starts_at else None,
        "ends_at": row.ends_at.isoformat() if row.ends_at else None,
        "active": row.active,
        "dismissible": row.dismissible,
        "link_url": row.link_url,
        "link_label": row.link_label,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def active_for_user(
    db: Session, *, user_id: str, is_admin_console: bool, now: datetime
) -> list[dict]:
    """이 사용자에게 지금 보여야 하는 공지.

    닫은 공지는 빼고, 창(starts_at~ends_at) 밖도 뺀다. **닫기 판정을 SQL 로 안 하고
    파이썬에서 하는 이유**: 공지는 많아야 수십 건이라 NOT EXISTS 서브쿼리의 이득이 없고,
    닫힘 id 집합 한 번 읽는 편이 읽기 쉽다.
    """
    audiences = (AUDIENCE_ALL, AUDIENCE_ADMIN) if is_admin_console else (AUDIENCE_ALL,)
    rows = (
        db.execute(
            select(Announcement)
            .where(Announcement.active.is_(True), Announcement.audience.in_(audiences))
            .order_by(Announcement.created_at.desc())
        )
        .scalars()
        .all()
    )
    if not rows:
        return []
    dismissed = set(
        db.execute(
            select(AnnouncementDismissal.announcement_id).where(
                AnnouncementDismissal.user_id == user_id
            )
        )
        .scalars()
        .all()
    )
    return [
        view(row)
        for row in rows
        if in_window(row, now) and row.id not in dismissed
    ]


def dismiss(db: Session, *, announcement_id: str, user_id: str, now: datetime) -> bool:
    """닫기. 이미 닫았으면 False(멱등) — 더블클릭·재시도로 행이 쌓이지 않는다."""
    existing = db.execute(
        select(AnnouncementDismissal).where(
            AnnouncementDismissal.announcement_id == announcement_id,
            AnnouncementDismissal.user_id == user_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return False
    db.add(
        AnnouncementDismissal(
            announcement_id=announcement_id, user_id=user_id, dismissed_at=now
        )
    )
    db.flush()
    return True
