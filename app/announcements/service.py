"""공지 조회·닫기 (0033, PLAN Phase 6)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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
from app.core.safe_url import is_safe_external_url, normalize_external_url


def validate(level: str, audience: str, link_url: str | None = None) -> None:
    """공지 입력 검증.

    `link_url` 은 예전에 길이만 봤다. 그 배너는 audience=all 이면 전 사용자에게 뜨고,
    `javascript:` 페이로드를 넣으면 누른 사람의 세션에서 실행된다 — 관리자 → 시스템 관리자
    권한 상승 경로다. 화면 쪽 `safeExternal()` 은 이중 방어일 뿐이고 **경계는 여기다**
    (API 를 직접 부르면 화면 검사는 지나가지도 않는다). app/core/safe_url.py 참조.

    CORE-11: 빈 문자열(`""`)은 "링크 없음"으로 본다 — `normalize_external_url`로 먼저
    정규화한 뒤 그 결과가 있을 때만 스킴을 검사한다. 예전엔 `link_url is not None`만
    보고 빈 문자열까지 `is_safe_external_url("")`(거짓)에 넣어 폼을 비웠을 뿐인 요청이
    422로 거부됐다.
    """
    if level not in ALL_LEVELS:
        raise ValidationAppError(f"level 은 {', '.join(ALL_LEVELS)} 중 하나여야 합니다.")
    if audience not in ALL_AUDIENCES:
        raise ValidationAppError(f"audience 는 {', '.join(ALL_AUDIENCES)} 중 하나여야 합니다.")
    normalized = normalize_external_url(link_url)
    if normalized is not None and not is_safe_external_url(normalized):
        raise ValidationAppError("링크는 http:// 또는 https:// 로 시작해야 합니다.")


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
    """닫기. 이미 닫았으면 False(멱등) — 더블클릭·재시도로 행이 쌓이지 않는다.

    UB-07: 위 SELECT 와 아래 INSERT 사이엔 잠금이 없다 — 탭 두 개(또는 더블클릭)가 거의
    동시에 오면 둘 다 "없음"을 보고 둘 다 insert 를 시도하고, `uq_announcement_dismissal`
    (announcement_id, user_id) UNIQUE 제약에 걸린 쪽이 잡히지 않은 `IntegrityError`로
    500이 됐다 — docstring 이 약속한 "멱등"과 반대로 두 번째 클릭이 사용자에게 오류로
    보였다. 그 예외를 "이미 남이 방금 닫았다"는 신호로 해석해 같은 멱등 결과(False)로
    되돌린다. `db.rollback()`이 필요하다 — flush 실패로 세션이 pending-rollback 상태가
    되면 이 요청의 나머지(get_db 의 요청-끝 commit 포함)가 `PendingRollbackError`로 깨진다.
    """
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
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return False
    return True
