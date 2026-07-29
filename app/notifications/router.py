"""User notification API (spec §13.5, §23.2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user, require_csrf
from app.core.errors import NotFoundError
from app.core.pagination import PageParams
from app.notifications.models import Notification
from app.notifications.service import mark_all_read, mark_read, unread_count
from app.users.models import User

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _view(row: Notification) -> dict:
    return {
        "id": row.id,
        "type": row.type,
        "title": row.title,
        "body": row.body,
        "read_at": row.read_at.isoformat() if row.read_at else None,
        "related_object_type": row.related_object_type,
        "related_object_id": row.related_object_id,
        "created_at": row.created_at.isoformat(),
    }


@router.get("")
def list_notifications(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: PageParams = Depends(),
    unread_only: bool = Query(default=False),
    read: str | None = Query(
        default=None,
        description="읽음 상태 필터: 'read'(읽음만)·'unread'(안 읽음만)·'all'(전체). "
        "unread_only=true는 하위 호환으로 'unread'와 같다.",
    ),
    type: str | None = Query(default=None, max_length=48),
):
    stmt = select(Notification).where(Notification.user_id == user.id)
    # unread_only(bool)는 기존 클라이언트 호환용, read(문자열)는 읽음까지 좁힐 수 있는
    # 확장이다 — 둘 중 하나라도 '안 읽음'을 요구하면 안 읽음만, read='read'면 읽음만
    # 보여 준다(round30 감사 E: 관리자 인박스는 이미 읽은 것도 되짚어야 한다).
    if unread_only or read == "unread":
        stmt = stmt.where(Notification.read_at.is_(None))
    elif read == "read":
        stmt = stmt.where(Notification.read_at.is_not(None))
    if type:
        stmt = stmt.where(Notification.type == type)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(Notification.created_at.desc(), Notification.id.desc())
            .offset(page.offset)
            .limit(page.page_size)
        )
        .scalars()
        .all()
    )
    return {
        "items": [_view(r) for r in rows],
        "total": total,
        "unread": unread_count(db, user.id),
        "page": page.page,
        "page_size": page.page_size,
    }


@router.get("/unread-count")
def get_unread_count(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    return {"unread": unread_count(db, user.id)}


@router.post("/read-all", dependencies=[Depends(require_csrf)])
def read_all_notifications(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    count = mark_all_read(db, user.id, now=request.app.state.clock.now())
    return {"ok": True, "read_count": count}


@router.post("/{notification_id}/read", dependencies=[Depends(require_csrf)])
def read_notification(
    request: Request,
    notification_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not mark_read(db, user.id, notification_id, now=request.app.state.clock.now()):
        raise NotFoundError("알림을 찾을 수 없습니다.")
    return {"ok": True}


@router.delete("/{notification_id}", dependencies=[Depends(require_csrf)])
def delete_notification(
    notification_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # '모두 읽음'은 읽음 표시만 할 뿐 행을 지우지 않아 알림이 무한정 쌓였다 — 본인 소유
    # 알림을 삭제(dismiss)할 경로를 연다(round30 감사 E). user_id로 소유권을 확인해
    # 남의 알림을 지울 수 없게 한다(IDOR 방지).
    row = db.execute(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user.id
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("알림을 찾을 수 없습니다.")
    db.delete(row)
    db.flush()
    return {"ok": True}
