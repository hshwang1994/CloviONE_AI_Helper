"""User notification API (spec §13.5, §23.2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user, require_csrf
from app.core.etag import etag_json_response
from app.core.errors import NotFoundError
from app.core.pagination import PageParams
from app.notifications.destinations import destination_for
from app.notifications.models import Notification
from app.notifications.service import (
    mark_all_read,
    mark_read,
    unread_count,
    unread_count_excluding,
)
from app.users.models import User

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _view(row: Notification, muted: frozenset[str] = frozenset()) -> dict:
    return {
        "id": row.id,
        "type": row.type,
        "title": row.title,
        "body": row.body,
        "read_at": row.read_at.isoformat() if row.read_at else None,
        "related_object_type": row.related_object_type,
        "related_object_id": row.related_object_id,
        # 딥링크 목적지(해시 라우터 경로 또는 null). 매핑은 destinations.RELATED_DESTINATIONS
        # 한 표에만 있다 — 프런트는 if 체인을 늘리지 않고 이 값을 그대로 쓴다.
        "related_route": destination_for(row.related_object_type, row.related_object_id),
        "created_at": row.created_at.isoformat(),
        # 사용자가 이 유형을 뮤트했는가. **목록에서 빼지 않고 표시만 한다** — 뮤트가
        # 삼키는 기능이 되면 사용자는 껐다는 사실조차 잊은 채 일을 놓친다.
        "muted": row.type in muted,
    }


def _badge_state(request: Request, db: Session, user) -> dict:
    """배지에 실제로 띄울 숫자 + 왜 조용한지.

    `unread` 는 예전과 똑같은 '안 읽음 총계'다(계약 유지). 새로 붙은 `badge` 가 화면이
    그리는 숫자이며, 방해금지 중이거나 뮤트된 유형만 남았을 때 0 이 된다.
    """
    from app.profiles import service as profile_service

    now = request.app.state.clock.now()
    pref = profile_service.get_preference(db, user.id)
    state = profile_service.quiet_state(
        pref, now=now, timezone_name=request.app.state.settings.timezone
    )
    profile_service.clear_expired_dnd(db, pref, state, now=now)

    from app.profiles.prefs import parse_muted

    muted = parse_muted(pref.muted_types if pref else "")
    total = unread_count(db, user.id)
    badge = 0 if state.quiet else unread_count_excluding(db, user.id, muted)
    return {
        "unread": total,
        "badge": badge,
        "quiet": state.quiet,
        "quiet_reason": state.reason,
        "quiet_until": state.until.isoformat() if state.until else None,
        "muted_types": muted,
    }


@router.get("")
def list_notifications(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: PageParams = Depends(),
    unread_only: bool = Query(default=False),
    read: str | None = Query(
        default=None,
        description="읽음 상태 필터: 'read'(읽음만), 'unread'(안 읽음만), 'all'(전체). "
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
    from app.profiles import service as profile_service
    from app.profiles.prefs import parse_muted

    pref = profile_service.get_preference(db, user.id)
    muted = frozenset(parse_muted(pref.muted_types if pref else ""))
    return {
        "items": [_view(r, muted) for r in rows],
        "total": total,
        "unread": unread_count(db, user.id),
        "page": page.page,
        "page_size": page.page_size,
    }


@router.get("/unread-count")
def get_unread_count(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """알림 배지 숫자. **모든 화면에서 60초마다 폴링**되므로 ETag/304 를 건다.

    목록(`GET /api/notifications`)에는 걸지 않는다 — 페이지네이션·읽음/유형 필터가 있어
    같은 URL 이 파라미터마다 다른 응답을 내고, 실제로 늘 도는 것은 배지 쪽이다.

    방해금지가 걸리거나 풀리면 본문이 달라지므로 ETag 도 함께 바뀐다 — 조용해진 순간
    다음 폴링에서 304 가 아니라 200 이 나가고 배지가 실제로 꺼진다.
    """
    return etag_json_response(request, _badge_state(request, db, user))


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
