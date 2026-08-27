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

#: Native 문서 항목의 id 앞머리. 휴지통 항목 id 와 문서 id 를 **한 목록에서** 구별한다.
#:
#: 왜 `trash_items` 에 행을 만들지 않는가: 그 표의 유일키가 `notion_page_id` 이고 Native
#: 문서에는 그런 id 가 없다. 만들어 넣으면 없는 개념을 지어내는 것이고, 지시 22.7 이
#: 「Legacy `trash_items`/Notion page id 구조를 Native 복원의 정본으로 쓰지 말라」고 적었다.
#: 정본은 `documents.archived` 하나이고, 이 화면은 두 출처를 **합쳐서 보여 줄 뿐**이다.
DOC_PREFIX = "doc:"


def _document_id(trash_id: str) -> str | None:
    """휴지통 항목 id 가 Native 문서를 가리키면 그 문서 id, 아니면 None."""
    return trash_id[len(DOC_PREFIX):] if trash_id.startswith(DOC_PREFIX) else None


def _document_view(document, extras, *, retention_days: int | None, me: User) -> dict:
    """Native 문서 한 건을 휴지통 줄로. 열 이름은 옛 항목과 **같다**.

    같지 않으면 화면이 종류마다 다른 표를 그리게 되고, 그 순간 「티켓과 문서를 한 목록에서
    본다」는 지시가 이름만 남는다.
    """
    from app.knowledge import service as knowledge_service

    deleted_at = document.archived_at
    # 자동 삭제가 꺼져 있으면 `retention_days` 가 None 이고, 그때는 삭제 예정도 없다.
    purge_after = (
        deleted_at + timedelta(days=retention_days)
        if (deleted_at and retention_days is not None) else None
    )
    people = extras.get("people") or {}
    archiver = people.get(document.archived_by) or {}
    folder = (extras.get("folders") or {}).get(document.folder_id) if document.folder_id else None
    space = (extras.get("spaces") or {}).get(document.space_id, "")
    return {
        "id": DOC_PREFIX + document.id,
        "item_type": "document",
        "type_label": "문서",
        # 옛 미러 문서와 지금 문서는 **되살리는 방법이 다르다.** 화면이 그것을 알아야
        # 같은 버튼이 두 종류의 요청을 낼 수 있다.
        "source": "knowledge",
        "title": document.title,
        "notion_page_id": None,
        "space": space,
        "folder": folder["path"] if folder else "",
        "deleted_by": archiver.get("display_name") or "",
        # 0021 이전에 보관된 문서는 시각을 모른다. 그때는 **비워 둔다** — `updated_at` 을
        # 대신 적으면 「이때 버렸다」는 거짓말이 되고, 삭제 예정일도 함께 틀린다.
        "deleted_at": deleted_at.isoformat() if deleted_at else None,
        "purge_after": purge_after.isoformat() if purge_after else None,
        "can_manage": knowledge_service.can_manage_trashed(me, document),
    }


def _retention_days(request: Request) -> int:
    try:
        return max(1, int(request.app.state.settings_cache.current_value("trash_retention_days") or 7))
    except (TypeError, ValueError):
        return 7


def _document_policy(request: Request) -> tuple[bool, int]:
    """문서 휴지통의 자동 영구 삭제 정책 — **켜졌는가와 며칠인가** (D-352).

    티켓 쪽 기간과 따로 읽는다. 두 정책이 하는 일이 다르기 때문이다: 옛 항목의 정리는
    원본을 보관처리하는 것이고, 문서는 이미 보관된 상태라 다음 단계가 **행을 지우는 것**이다.

    꺼져 있으면 화면이 「삭제 예정」을 말하면 안 된다 — 안 지워지는데 날짜를 적으면 거짓말이다.
    """
    cache = request.app.state.settings_cache
    try:
        days = max(1, int(cache.current_value("document_trash_retention_days") or 7))
    except (TypeError, ValueError):
        days = 7
    enabled = cache.current_value("document_trash_autopurge")
    return (True if enabled is None else bool(enabled)), days


def _item_view(item, *, retention_days: int, me: User) -> dict:
    purge_after = item.deleted_at + timedelta(days=retention_days)
    can_manage = me.role in MODERATOR_ROLES or item.deleted_by_user_id == me.id
    return {
        "id": item.id,
        "item_type": item.item_type,
        "type_label": _TYPE_LABELS.get(item.item_type, item.item_type),
        # 옛 미러(티켓·`document_cache`)에서 온 항목이라는 표시. Native 문서와 되살리는
        # 경로가 다르다.
        "source": "legacy",
        "title": item.title,
        # 옛 항목은 공간/폴더를 모른다 — 그 개념이 없는 표에서 왔다. 빈 값으로 두고
        # 화면이 자리를 비운다(없는 값을 「-」로 지어내지 않는다).
        "space": "",
        "folder": "",
        # `url` 은 여기 없다. 옛 Notion 주소라 목록의 제목을 그 링크로 만들면 사용자가
        # 지운 것을 확인하려다 낡은 사본을 열게 된다(행에는 이관 흔적으로 남는다).
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
    # 종류로 좁히는 것은 **서버가 한다**. 화면에서만 거르면 상한 너머의 그 종류가 안 보이면서
    # 화면은 「이게 전부」라고 말한다 — 문서 화면의 「휴지통」이 이 조건을 걸고 연다.
    kind: str | None = Query(default=None, max_length=16),
):
    days = _retention_days(request)
    doc_autopurge, doc_days = _document_policy(request)
    # 범위를 건다 — 예전에는 조건이 하나도 없어 남의 팀이 지운 것까지 보였다.
    from app.core.scope import visibility_scope
    from app.knowledge import service as knowledge_service

    want_documents = kind != "ticket"

    # 옛 미러 표에는 티켓과 문서가 함께 있다. 「문서만」을 골라도 그쪽 문서는 남아야 한다 —
    # 옛 문서를 되살릴 길이 거기 하나뿐이다.
    items, total = repository.list_visible(
        db, visibility_scope(db, me), limit=limit,
        item_type=kind if kind in ("ticket", "document") else None,
    )
    rows = [_item_view(i, retention_days=days, me=me) for i in items]

    # 🔴 **Native 문서는 이 표에 없다.** 문서 삭제는 `documents.archived` 를 세우는
    # 것이고(그래야 판·멘션·관계가 안 사라진다), 그 사실이 여기 안 실리면 문서를 지운
    # 사람은 되살릴 자리를 찾지 못한다 — 지시 22.7 이 지목한 그 상태다.
    #
    # 가시성은 문서 쪽 문(`list_documents`)이 건다 — 휴지통이 자기 규칙을 갖는 순간
    # 목록에서 가린 문서가 휴지통에서 보인다.
    docs, doc_total = (
        knowledge_service.list_documents(
            db, me, archived_only=True, sort="archived", limit=limit,
        )
        if want_documents else ([], 0)
    )
    extras = knowledge_service.list_page_extras(db, me, docs)
    rows += [
        _document_view(d, extras, retention_days=doc_days if doc_autopurge else None, me=me)
        for d in docs
    ]
    # 종류가 섞이므로 **삭제일 최신순**으로 다시 세운다. 시각을 모르는 옛 행은 뒤로 간다.
    rows.sort(key=lambda r: (r["deleted_at"] or ""), reverse=True)

    # 휴지통은 15초마다 폴링되는데 실제로는 며칠에 한 번 바뀐다 — 전형적인 304 대상이다.
    return etag_json_response(request, {
        "items": rows,
        "retention_days": days,
        # 문서 정책은 따로 싣는다 — 화면이 「문서는 이레 뒤 자동으로 지워집니다」와
        # 「문서는 자동으로 지워지지 않습니다」를 구별해서 말할 수 있어야 한다.
        "document_autopurge": doc_autopurge,
        "document_retention_days": doc_days,
        "total": total + doc_total,
    })


def _get_or_404(db: Session, trash_id: str):
    item = repository.get(db, trash_id)
    if item is None:
        raise NotFoundError("휴지통 항목을 찾을 수 없습니다.")
    return item


def _split_ids(ids: list[str]) -> tuple[list[str], list[str]]:
    """휴지통 항목 id 와 Native 문서 id 를 가른다. 한 요청에 둘이 섞여 온다."""
    legacy: list[str] = []
    docs: list[str] = []
    for raw in ids:
        document_id = _document_id(raw)
        (docs if document_id else legacy).append(document_id or raw)
    return legacy, docs


def _bulk_documents(request: Request, db: Session, me: User, ids: list[str], result: dict,
                    *, key: str, act) -> None:
    """문서 몫을 건별로 처리해 **같은 결과 사전에** 실어 준다.

    실패를 건별로 격리하는 것은 옛 경로와 같은 규칙이다 — 한 건이 권한에 막혔다고 나머지
    아홉 건이 함께 실패하면, 사용자는 어느 것이 처리됐는지 알 수 없어 전부 다시 누른다.
    """
    from app.core.errors import AppError

    for document_id in ids:
        try:
            act(request, db, me, document_id)
            result[key].append({"id": DOC_PREFIX + document_id, "item_type": "document"})
        except AppError as exc:
            result["failed"].append({"id": DOC_PREFIX + document_id, "error": exc.message})


@router.post("/restore-bulk", dependencies=[Depends(require_csrf)])
def restore_bulk(request: Request, payload: TrashBulkIds, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """여러 항목을 한 번에 복원(운영자 이상 또는 버린 본인). 부분 성공.
    (리터럴 경로라 아래 /{trash_id}/... 보다 먼저 선언 — trash_id 로 잡히지 않게.)"""
    legacy, docs = _split_ids(payload.ids)
    result = service.restore_bulk(db, legacy, me)
    _bulk_documents(request, db, me, docs, result, key="restored", act=_restore_document)
    for it in result["restored"]:
        # 문서 몫은 `_restore_document` 가 이미 자기 기록을 남겼다(`notion_page_id` 가 없다).
        if it.get("notion_page_id") is None:
            continue
        record_audit_from_request(request, db, action="trash.restore",
                                  object_type=f"notion_{it['item_type']}", object_id=it["notion_page_id"],
                                  after={"title": it["title"]})
    return {"ok": True, **result}


@router.post("/purge-bulk", dependencies=[Depends(require_csrf)])
def purge_bulk(request: Request, payload: TrashBulkIds, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """여러 항목을 한 번에 영구삭제(원본 보관처리 + 제거). 부분 성공."""
    legacy, docs = _split_ids(payload.ids)
    result = service.purge_bulk(
        db, legacy, me,
        outbound=request.app.state.outbound_client, settings=request.app.state.settings,
    )
    _bulk_documents(request, db, me, docs, result, key="purged", act=_purge_document)
    for it in result["purged"]:
        if it.get("notion_page_id") is None:
            continue
        record_audit_from_request(request, db, action="trash.purge",
                                  object_type=f"notion_{it['item_type']}", object_id=it["notion_page_id"],
                                  before={"title": it["title"]})
    return {"ok": True, **result}


def _restore_document(request: Request, db: Session, me: User, document_id: str) -> dict:
    """Native 문서 되살리기 — **판정도 쓰기도 문서 도메인이 한다.**

    여기서 `archived = False` 를 직접 적지 않는 이유는 하나다: 되살리기는 색인을 다시
    거는 일까지 포함하고(보관 중에는 검색·AI 후보에서 빠져 있다), 그 절차가 두 곳에
    적히면 한쪽만 고쳐진다.
    """
    from app.core.errors import ForbiddenError
    from app.knowledge import service as knowledge_service

    document = knowledge_service.get_scoped_document_or_404(db, me, document_id)
    if not knowledge_service.can_manage_trashed(me, document):
        raise ForbiddenError("이 문서를 되살릴 권한이 없습니다.")
    title = document.title
    knowledge_service.restore_document(db, me, document_id)
    record_audit_from_request(
        request, db, action="trash.restore", object_type="document",
        object_id=document_id, after={"title": title},
    )
    return {"ok": True}


def _purge_document(request: Request, db: Session, me: User, document_id: str) -> dict:
    """Native 문서 영구 삭제 — 행을 지운다. 되돌릴 수 없다."""
    from app.core.errors import ForbiddenError
    from app.knowledge import service as knowledge_service

    document = knowledge_service.get_scoped_document_or_404(db, me, document_id)
    if not knowledge_service.can_manage_trashed(me, document):
        raise ForbiddenError("이 문서를 영구 삭제할 권한이 없습니다.")
    info = knowledge_service.purge_document(db, me, document_id)
    record_audit_from_request(
        request, db, action="trash.purge", object_type="document",
        object_id=document_id, before={"title": info["title"]},
    )
    return {"ok": True}


@router.post("/{trash_id}/restore", dependencies=[Depends(require_csrf)])
def restore(request: Request, trash_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    document_id = _document_id(trash_id)
    if document_id:
        return _restore_document(request, db, me, document_id)
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
    """영구 삭제 — 원본을 보관처리하고 휴지통에서 제거(운영자 이상 또는 버린 본인).

    Native 문서는 **뜻이 다르다.** 그쪽은 이미 보관된 상태로 여기 와 있으므로 「보관처리」가
    할 일이 없고, 영구 삭제는 행을 지우는 일이다(지시 22.7 의 「권한이 허용된 영구 삭제」).
    """
    document_id = _document_id(trash_id)
    if document_id:
        return _purge_document(request, db, me, document_id)
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
