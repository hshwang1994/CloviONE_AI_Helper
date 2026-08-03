"""휴지통 비즈니스 규칙 — 소프트 삭제 기록, 복원, 영구 삭제(노션 보관처리), 만료 정리.

'삭제'는 노션을 바로 지우지 않고 TrashItem 을 만든다. 복원은 그 행을 지운다(노션 무손상 → 원래
목록으로 복귀). 영구 삭제(만료 자동/수동)는 노션 페이지를 보관처리(archive)한 뒤 행을 지운다.
노션 archive 는 되돌릴 수 있어(노션 휴지통 30일) 실수에도 복구 여지가 있다. 권한: 운영자 이상 또는
그 항목을 버린 본인만 복원/영구삭제할 수 있다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

# 운영자 이상은 누가 버린 항목이든 복원/영구삭제할 수 있다(감사·정리 권한).
# 역할 이름을 여기 문자열로 다시 적지 않는다 — authz 한 곳이 정본이다.
from app.core.authz import MODERATOR_ROLES
from app.core.errors import ConflictError, ForbiddenError
from app.trash import repository
from app.trash.models import TRASH_DOCUMENT, TRASH_TICKET, TRASH_TYPES, TrashItem
from app.users.models import User


def _target_uid(db: Session, item_type: str, notion_page_id: str) -> str | None:
    """Notion page id → 미러 행의 자체 UUID(0025). 미러에 없으면 None.

    티켓은 ticket_cache, 문서는 document_cache 를 본다. None 이 정상 상태다 — 방금 만든
    티켓을 동기화 전에 버릴 수 있다. 그래서 FK 로 걸지 않고, 휴지통의 실제 동작(중복 방지·
    목록 필터·복원)은 계속 notion_page_id 가 담당한다.
    """
    from app.team_docs.models import DocumentCache
    from app.tickets.models import TicketCache

    model = TicketCache if item_type == TRASH_TICKET else DocumentCache
    return db.execute(
        select(model.id).where(model.notion_page_id == notion_page_id)
    ).scalar_one_or_none()


def move_to_trash(
    db: Session, *, item_type: str, notion_page_id: str, title: str, url: str | None,
    user: User, now: datetime,
) -> TrashItem:
    """항목을 휴지통으로 옮긴다(노션은 손대지 않는다). 이미 들어가 있으면 충돌."""
    if item_type not in TRASH_TYPES:
        raise ConflictError("지원하지 않는 삭제 대상입니다.")
    if repository.get_by_page(db, item_type, notion_page_id) is not None:
        raise ConflictError("이미 휴지통에 있습니다.")
    item = TrashItem(
        item_type=item_type, notion_page_id=notion_page_id,
        # 자체 id 도 함께 남긴다(0025). 미러에 아직 없으면 NULL — 중복 방지와 목록 필터는
        # 계속 notion_page_id 가 담당하므로 NULL 이어도 휴지통 동작은 그대로다.
        target_uid=_target_uid(db, item_type, notion_page_id),
        title=(title or "")[:400], url=(url or None),
        deleted_by_user_id=user.id, deleted_by_name=(user.display_name or "")[:200],
        deleted_at=now,
    )
    db.add(item)
    db.flush()
    return item


def ensure_can_manage(user: User, item: TrashItem) -> None:
    """복원/영구삭제 권한 — 운영자 이상이거나 그 항목을 버린 본인."""
    if user.role in MODERATOR_ROLES or item.deleted_by_user_id == user.id:
        return
    raise ForbiddenError("이 항목을 복원하거나 지울 권한이 없습니다.")


def restore(db: Session, item: TrashItem, user: User) -> None:
    """복원 — 휴지통 행만 지우면 노션 원본이 그대로라 원래 목록으로 되돌아온다."""
    ensure_can_manage(user, item)
    db.delete(item)
    db.flush()


def purge_item(db: Session, item: TrashItem, *, outbound, settings) -> None:
    """영구 삭제 — 노션 페이지를 보관처리(archive)한 뒤 휴지통 행을 지운다."""
    _archive_notion(item, outbound=outbound, settings=settings)
    db.delete(item)
    db.flush()


def purge_by_user(db: Session, item: TrashItem, user: User, *, outbound, settings) -> None:
    ensure_can_manage(user, item)
    purge_item(db, item, outbound=outbound, settings=settings)


def restore_bulk(db: Session, ids: list[str], user: User) -> dict:
    """여러 항목을 한 번에 복원. 건별 권한 검사, 실패(권한 없음·없음)는 건너뛰고 계속(부분 성공)."""
    from app.core.errors import AppError

    restored: list[dict] = []
    failed: list[dict] = []
    for tid in ids:
        item = repository.get(db, tid)
        if item is None:
            failed.append({"id": tid, "error": "이미 처리된 항목입니다."})
            continue
        title, itype, pid = item.title, item.item_type, item.notion_page_id
        try:
            restore(db, item, user)
            restored.append({"id": tid, "title": title, "item_type": itype, "notion_page_id": pid})
        except AppError as exc:
            failed.append({"id": tid, "error": exc.message})
    return {"restored": restored, "failed": failed}


def purge_bulk(db: Session, ids: list[str], user: User, *, outbound, settings) -> dict:
    """여러 항목을 한 번에 영구삭제(노션 보관처리 + 행 삭제). 건별 권한·노션 오류 격리(부분 성공)."""
    from app.core.errors import AppError

    purged: list[dict] = []
    failed: list[dict] = []
    for tid in ids:
        item = repository.get(db, tid)
        if item is None:
            failed.append({"id": tid, "error": "이미 처리된 항목입니다."})
            continue
        title, itype, pid = item.title, item.item_type, item.notion_page_id
        try:
            ensure_can_manage(user, item)
            purge_item(db, item, outbound=outbound, settings=settings)
            purged.append({"id": tid, "title": title, "item_type": itype, "notion_page_id": pid})
        except AppError as exc:
            failed.append({"id": tid, "error": exc.message})
        except Exception:  # noqa: BLE001 — 노션 호출 실패 격리(행은 남겨 재시도 가능)
            failed.append({"id": tid, "error": "노션 보관처리에 실패했습니다. 잠시 후 다시 시도하세요."})
    return {"purged": purged, "failed": failed}


def purge_expired(db: Session, *, now: datetime, retention_days: int, outbound, settings) -> dict:
    """보관기간이 지난 항목을 노션에서 보관처리하고 휴지통에서 지운다(백그라운드 정리 작업).

    한 항목의 노션 호출이 실패해도 다른 항목 처리는 계속한다(장애 격리) — 실패 건은 다음 주기에 재시도.
    """
    cutoff = now - timedelta(days=max(1, int(retention_days)))
    purged, failed = 0, 0
    for item in repository.list_items(db):
        if item.deleted_at >= cutoff:
            continue
        try:
            _archive_notion(item, outbound=outbound, settings=settings)
        except Exception:  # noqa: BLE001 — 개별 실패 격리, 행은 남겨 다음 주기 재시도
            failed += 1
            continue
        db.delete(item)
        purged += 1
    if purged or failed:
        db.flush()
    return {"purged": purged, "failed": failed}


def _archive_notion(item: TrashItem, *, outbound, settings) -> None:
    """항목 종류에 맞는 저장소로 원본 페이지를 보관처리한다.

    저장소 seam 을 지나는 이유: 소스가 바뀌면 '보관처리'의 뜻도 바뀌는데 여기서 Notion 모듈을
    직접 부르면 그때 고칠 곳이 하나 더 숨는다(경계 정적검사가 이걸 막는다). 지연 import 로
    순환 참조를 피한다.

    db 를 넘기지 않는 이유: 이 지점은 '외부 원본을 보관처리한다'만 한다. 캐시 행 정리는 바로
    다음 미러 동기화가 알아서 한다(보관처리된 페이지는 소스 조회 결과에서 빠진다)."""
    from app.core.source_registry import build_document_repository, build_ticket_repository

    if item.item_type == TRASH_TICKET:
        build_ticket_repository(settings, outbound).archive(None, page_id=item.notion_page_id)
    elif item.item_type == TRASH_DOCUMENT:
        build_document_repository(settings, outbound).archive(None, page_id=item.notion_page_id)
