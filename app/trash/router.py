"""휴지통 API — 목록 조회 / 복원 / 영구 삭제.

목록은 로그인 사용자 누구나 본다(팀 공용 휴지통). 복원·영구삭제는 운영자 이상 또는 그 항목을
버린 본인만(service.ensure_can_manage). 티켓/문서를 '삭제'해 넣는 동작은 각 모듈(tickets/team_docs)
라우터에 있고, 여기서는 넣은 뒤의 관리를 맡는다.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.authz import MODERATOR_ROLES
from app.core.deps import get_current_user, get_db, require_csrf
from app.core.etag import etag_json_response
from app.core.errors import NotFoundError
from app.trash import repository, service
from app.trash.schemas import TrashBulkIds
from app.users.models import User
from app.settings.gate import block_if_maintenance

router = APIRouter(
    prefix="/api/trash",
    tags=["trash"],
    dependencies=[Depends(block_if_maintenance)],
)

_TYPE_LABELS = {"ticket": "티켓", "document": "문서"}


def _retention_days(request: Request) -> int:
    try:
        return max(1, int(request.app.state.settings_cache.current_value("trash_retention_days") or 7))
    except (TypeError, ValueError):
        return 7


def _item_view(item, *, retention_days: int, me: User) -> dict:
    purge_after = item.deleted_at + timedelta(days=retention_days)
    can_manage = me.role in MODERATOR_ROLES or item.deleted_by_user_id == me.id
    return {
        "id": item.id,
        "item_type": item.item_type,
        "type_label": _TYPE_LABELS.get(item.item_type, item.item_type),
        "title": item.title,
        "url": item.url,
        # FN-14 — 프런트의 문서 상세 캐시 키가 notion_page_id다([team-doc, id], TeamDoc.jsx).
        # 이게 없으면 복원·영구삭제 뒤 그 캐시를 무효화할 방법이 없어 상세를 다시 열면 옛
        # 내용이 잠깐 보인다. 이미 이 행(TicketCache 아님, TrashItem)에 not-null로 있다 — 조인 없음.
        "notion_page_id": item.notion_page_id,
        "deleted_by": item.deleted_by_name,
        "deleted_at": item.deleted_at.isoformat(),
        "purge_after": purge_after.isoformat(),
        "can_manage": can_manage,
    }


@router.get("")
def list_trash(
    request: Request, db: Session = Depends(get_db), me: User = Depends(get_current_user),
    # UA-10 확증 — 예전에는 이 값이 아예 없어 응답이 무제한이었고 total도 안 실려서
    # "더 보기" 자체가 불가능했다(?limit=1을 줘도 조용히 무시됐다).
    limit: int = Query(default=repository.DEFAULT_TRASH_LIST_LIMIT, ge=1, le=repository.MAX_TRASH_LIST_LIMIT),
):
    days = _retention_days(request)
    # 범위를 건다 — 예전에는 조건이 하나도 없어 남의 팀이 지운 것까지 보였다.
    from app.core.scope import build_scope

    items, total = repository.list_visible(db, build_scope(db, me), limit=limit)
    # 휴지통은 15초마다 폴링되는데 실제로는 며칠에 한 번 바뀐다 — 전형적인 304 대상이다.
    return etag_json_response(request, {
        "items": [_item_view(i, retention_days=days, me=me) for i in items],
        "retention_days": days,
        "total": total,
    })


def _get_or_404(db: Session, trash_id: str):
    item = repository.get(db, trash_id)
    if item is None:
        raise NotFoundError("휴지통 항목을 찾을 수 없습니다.")
    return item


@router.post("/restore-bulk", dependencies=[Depends(require_csrf)])
def restore_bulk(request: Request, payload: TrashBulkIds, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """여러 항목을 한 번에 복원(운영자 이상 또는 버린 본인). 부분 성공.
    (리터럴 경로라 아래 /{trash_id}/... 보다 먼저 선언 — trash_id 로 잡히지 않게.)"""
    result = service.restore_bulk(db, payload.ids, me)
    for it in result["restored"]:
        record_audit_from_request(request, db, action="trash.restore",
                                  object_type=f"notion_{it['item_type']}", object_id=it["notion_page_id"],
                                  after={"title": it["title"]})
    return {"ok": True, **result}


@router.post("/purge-bulk", dependencies=[Depends(require_csrf)])
def purge_bulk(request: Request, payload: TrashBulkIds, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """여러 항목을 한 번에 영구삭제(노션 보관처리 + 제거). 부분 성공."""
    result = service.purge_bulk(
        db, payload.ids, me,
        outbound=request.app.state.outbound_client, settings=request.app.state.settings,
    )
    for it in result["purged"]:
        record_audit_from_request(request, db, action="trash.purge",
                                  object_type=f"notion_{it['item_type']}", object_id=it["notion_page_id"],
                                  before={"title": it["title"]})
    return {"ok": True, **result}


@router.post("/{trash_id}/restore", dependencies=[Depends(require_csrf)])
def restore(request: Request, trash_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    item = _get_or_404(db, trash_id)
    itype, pid, title = item.item_type, item.notion_page_id, item.title
    service.restore(db, item, me)
    record_audit_from_request(
        request, db, action="trash.restore", object_type=f"notion_{itype}",
        object_id=pid, after={"title": title},
    )
    return {"ok": True}


@router.post("/{trash_id}/purge", dependencies=[Depends(require_csrf)])
def purge(request: Request, trash_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """영구 삭제 — 노션 페이지를 보관처리하고 휴지통에서 제거(운영자 이상 또는 버린 본인)."""
    item = _get_or_404(db, trash_id)
    itype, pid, title = item.item_type, item.notion_page_id, item.title
    service.purge_by_user(
        db, item, me,
        outbound=request.app.state.outbound_client, settings=request.app.state.settings,
    )
    record_audit_from_request(
        request, db, action="trash.purge", object_type=f"notion_{itype}",
        object_id=pid, before={"title": title},
    )
    return {"ok": True}
