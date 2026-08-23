"""휴지통 비즈니스 규칙 — 소프트 삭제 기록, 복원, 영구 삭제(노션 보관처리), 만료 정리.

'삭제'는 노션을 바로 지우지 않고 TrashItem 을 만든다. 복원은 그 행을 지운다(노션 무손상 → 원래
목록으로 복귀). 영구 삭제(만료 자동/수동)는 노션 페이지를 보관처리(archive)한 뒤 행을 지운다.
노션 archive 는 되돌릴 수 있어(노션 휴지통 30일) 실수에도 복구 여지가 있다. 권한: 운영자 이상 또는
그 항목을 버린 본인만 복원/영구삭제할 수 있다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

# 운영자 이상은 누가 버린 항목이든 복원/영구삭제할 수 있다(감사·정리 권한).
# 역할 이름을 여기 문자열로 다시 적지 않는다 — authz 한 곳이 정본이다.
from app.core.authz import MODERATOR_ROLES
from app.core.db import is_insert_race
from app.core.errors import NotFoundError, ConflictError, ForbiddenError
from app.core.scope import visibility_scope
from app.trash import repository
from app.trash.models import TRASH_DOCUMENT, TRASH_TICKET, TRASH_TYPES, TrashItem
from app.users.models import User

logger = logging.getLogger("app.trash")


@dataclass(frozen=True)
class _PurgeTarget:
    """만료 항목의 **값 사본**. ORM 객체가 아니라 이걸 들고 HTTP 구간을 지난다 (S7).

    세션을 커밋한 뒤에도 안전하게 읽을 수 있어야 하고, 여기서 실수로 `db` 를 만지는 코드가
    생기지 않게 하려는 목적도 있다 — 그 한 줄이 다시 락을 잡는 순간 이 수정이 무효가 된다.
    """

    id: str
    item_type: str
    notion_page_id: str | None


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
    # uq_trash_item UNIQUE(item_type, notion_page_id) — 더블클릭이나 같은 항목의 동시
    # 삭제가 위 조회 사이를 비집고 들어오면 둘 다 "아직 없음"을 보고 삽입을 시도할 수
    # 있다(app/prompts/service.py::transition과 같은 관용). 위와 같은 409 문구로 알린다.
    try:
        with db.begin_nested():
            db.add(item)
            db.flush()
    except (IntegrityError, OperationalError) as exc:
        if not is_insert_race(exc):
            raise
        raise ConflictError("이미 휴지통에 있습니다.") from None
    return item


def ensure_can_manage(db: Session, user: User, item: TrashItem) -> None:
    """복원/영구삭제 권한 — **범위 안**이고, 운영자 이상이거나 그 항목을 버린 본인 (3순위 IDOR).

    범위를 먼저 본다. 목록(`list_visible`)에서 가린 항목이 **id 하나로 영구삭제**되면 가린
    의미가 없고, 여기서 새는 결과는 **되돌릴 수 없는 삭제**다. 네 경로(단건 복원·단건
    영구삭제·일괄 복원·일괄 영구삭제)가 전부 이 함수를 지나므로 **여기 한 곳**에 둔다 —
    경로마다 손으로 적으면 새 경로에서 빠뜨리고, 일괄 경로가 정확히 그렇게 열려 있었다.

    범위 밖은 **404**: 403 은 그 항목이 존재한다는 사실을 알려 준다. 일괄 경로는 이 예외를
    건별로 모아 '부분 성공' 으로 보고하므로 남의 항목은 그냥 '없는 항목'으로 보인다.
    """
    if not repository.visible_to(db, item, visibility_scope(db, user)):
        raise NotFoundError("휴지통 항목을 찾을 수 없습니다.")
    if user.role in MODERATOR_ROLES or item.deleted_by_user_id == user.id:
        return
    raise ForbiddenError("이 항목을 복원하거나 지울 권한이 없습니다.")


def restore(db: Session, item: TrashItem, user: User) -> None:
    """복원 — 휴지통 행만 지우면 노션 원본이 그대로라 원래 목록으로 되돌아온다."""
    ensure_can_manage(db, user, item)
    db.delete(item)
    db.flush()


def purge_item(db: Session, item: TrashItem, *, outbound, settings) -> None:
    """영구 삭제 — 노션 페이지를 보관처리(archive)한 뒤 휴지통 행을 지운다."""
    _archive_source(db, item, outbound=outbound, settings=settings)
    db.delete(item)
    db.flush()


def purge_by_user(db: Session, item: TrashItem, user: User, *, outbound, settings) -> None:
    ensure_can_manage(db, user, item)
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
            ensure_can_manage(db, user, item)
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

    ## 쓰기 락을 쥔 채 HTTP 를 하지 않는다 (S7)

    예전에는 한 트랜잭션 안에서 `db.delete()` 와 Notion 왕복을 번갈아 했다. SQLite 는 첫
    쓰기 문장에서 **DB 전체 쓰기 락**을 잡고 커밋까지 놓지 않는다(WAL 이어도 쓰기는 하나다).
    만료 항목 20개 × 느린 Notion = **그동안 웹의 모든 쓰기가 `database is locked` 500** 이다.
    한 시간에 한 번, 몇 분간, 게다가 이 정리는 아무 상태도 안 남겨서 **원인을 찾을 단서가 없다**.

    그래서 순서를 바꾼다:

      ① 만료 대상을 **읽기만** 해서 평범한 값으로 뽑아낸다 → 커밋(트랜잭션을 닫는다)
      ② 락이 **없는** 상태에서 Notion 왕복을 전부 한다 (여기가 느린 구간이다)
      ③ 성공한 것만 **한 문장으로** 지운다 → 락을 쥐는 시간이 밀리초가 된다

    ②에서 죽으면 행이 남아 다음 주기에 재시도한다 — 원래 설계된 실패 처리 그대로다.
    """
    cutoff = now - timedelta(days=max(1, int(retention_days)))

    # ① 읽기 전용 스냅샷. ORM 객체를 들고 다니지 않는다 — 아래에서 세션을 커밋하면
    #    identity map 은 살아 있어도 그 사이 다른 곳이 같은 행을 건드릴 수 있다.
    expired = [
        _PurgeTarget(item.id, item.item_type, item.notion_page_id)
        for item in repository.list_items(db)
        if item.deleted_at < cutoff
    ]
    if not expired:
        return {"purged": 0, "failed": 0}
    # 여기까지의 읽기 트랜잭션을 닫는다. 앞선 정리(대화·알림·잡)가 이미 쓰기를 했다면
    # 그 락도 여기서 놓인다 — 아래 HTTP 구간이 정확히 그 락을 오래 쥐던 구간이었다.
    db.commit()

    # ② 락 없이 외부 호출. 느려도 웹은 멀쩡하다.
    archived: list[str] = []
    # 🔴 예전에는 실패를 숫자로만 셌다 (H5). 그러면 **왜** 실패하는지 아무 데도 안 남아,
    # 원본이 이미 지워졌거나 토큰 권한이 빠진 항목이 매 주기 조용히 실패하면서 휴지통에
    # 영원히 남는다. 화면에는 "N건 실패" 만 뜨고 그 N 이 줄지 않는 이유를 아무도 모른다.
    failures: list[dict] = []
    for target in expired:
        try:
            _archive_source(db, target, outbound=outbound, settings=settings)
        except Exception as exc:  # noqa: BLE001 — 개별 실패 격리, 행은 남겨 다음 주기 재시도
            reason = type(exc).__name__
            logger.warning(
                "휴지통 영구삭제 실패 (다음 주기에 재시도): id=%s type=%s reason=%s",
                target.id, target.item_type, reason,
            )
            # 오류 **메시지**는 싣지 않는다 — 소스가 준 문자열이라 무엇이 들었는지 보장할 수
            # 없고, 이 값은 운영 화면까지 그대로 나간다. 종류만으로도 원인은 갈린다.
            failures.append({"id": target.id, "type": target.item_type, "reason": reason})
            continue
        archived.append(target.id)

    # ③ 성공분만 한 문장으로. 락을 쥐는 시간이 HTTP 시간과 무관해진다.
    if archived:
        db.execute(delete(TrashItem).where(TrashItem.id.in_(archived)))
        db.flush()
    return {
        "purged": len(archived),
        "failed": len(failures),
        # 상한을 둔다. 소스가 통째로 죽은 날에는 만료 항목 전부가 여기 실리는데, 목록이
        # 길다고 알 수 있는 것이 늘지는 않는다(같은 이유가 반복될 뿐이다).
        "failures": failures[:20],
        "failure_reasons": sorted({f["reason"] for f in failures}),
    }


def _archive_source(
    db: Session, item: "_PurgeTarget | TrashItem", *, outbound, settings
) -> None:
    """항목 종류에 맞는 저장소로 원본을 보관처리한다.

    저장소 seam 을 지나는 이유: 소스가 바뀌면 '보관처리'의 뜻도 바뀌는데 여기서 구현 모듈을
    직접 부르면 그때 고칠 곳이 하나 더 숨는다(경계 정적검사가 이걸 막는다). 지연 import 로
    순환 참조를 피한다.

    **`db` 를 넘긴다 (S14).** 예전에는 안 넘겼고, 그때는 그것이 옳았다 — 이 지점이 하는 일은
    저쪽 페이지를 보관처리하는 것뿐이었고 우리 캐시 행은 **다음 미러 동기화가** 정리했다.
    자체 DB 가 정본이 되면서 그 「다음 동기화」가 없어졌으므로, 보관처리 자체가 로컬 쓰기다.

    안 넘긴 채로 두면 조용히 틀린다: 휴지통 행은 지워지는데 원본 행은 살아남고, 목록은
    휴지통 행으로 그것을 숨기고 있었으므로 **영구 삭제한 티켓이 목록에 다시 나타난다.**
    """
    from app.core.source_registry import build_document_repository, build_ticket_repository

    if item.item_type == TRASH_TICKET:
        build_ticket_repository(settings, outbound).archive(db, page_id=item.notion_page_id)
    elif item.item_type == TRASH_DOCUMENT:
        build_document_repository(settings, outbound).archive(db, page_id=item.notion_page_id)
