"""팀 공간 > 문서 API (§17).

조회는 인증만, 상태변경(동기화·즐겨찾기)은 CSRF. 목록·상세 메타는 로컬 캐시에서 읽어
Notion 장애와 무관하게 응답한다(§17.4). 본문 블록만 상세 조회 때 실시간으로 읽고, 실패하면
메타는 보여주되 본문 자리에 '불러올 수 없음'을 표시한다(티켓 등 다른 기능엔 무영향).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.deps import get_current_user, get_db, require_csrf
from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.core.feature_flags import load_feature_flags
from app.core.pagination import PageParams
from app.team_docs import notion_docs, repository, service
from app.team_docs.models import split_names
from app.team_docs.schemas import DocumentCreate
from app.team_docs.sync import get_or_create_state, sync_documents
from app.tickets.schemas import BulkPageIds  # 티켓·문서 공용 일괄 삭제 스키마
from app.users.models import User


def require_team_docs_enabled(request: Request) -> None:
    flags = load_feature_flags(request.app.state.settings.config_dir)
    if not flags.get("team_docs_enabled", True):
        raise NotFoundError("문서 기능이 비활성화되어 있습니다.")


router = APIRouter(
    prefix="/api/team-docs",
    tags=["team-docs"],
    dependencies=[Depends(require_team_docs_enabled)],
)


def _doc_view(row, *, is_favorite: bool) -> dict:
    return {
        "id": row.notion_page_id,
        "title": row.title,
        "document_type": row.document_type,
        "work_field": row.work_field,
        "tech_tags": split_names(row.tech_tags),
        "projects": split_names(row.project_names),
        "status": row.status,
        "priority": row.priority,
        "owner": row.owner,
        "author_names": split_names(row.author_names),
        "doc_date": row.doc_date,
        "last_edited": row.last_edited,
        "url": row.url,
        "original_url": row.original_url,
        "source_url": row.source_url,
        "has_files": row.has_files,
        "is_favorite": is_favorite,
        "synced_at": row.synced_at.isoformat() if row.synced_at else None,
    }


def _sync_view(state) -> dict:
    return {
        "status": state.status,
        "last_run_at": state.last_run_at.isoformat() if state.last_run_at else None,
        "last_success_at": state.last_success_at.isoformat() if state.last_success_at else None,
        "doc_count": state.doc_count,
        "error": state.error,
    }


@router.get("")
def list_documents(
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
    page: PageParams = Depends(),
    q: str | None = Query(default=None, max_length=200),
    doc_type: str | None = Query(default=None, max_length=32),
    work_field: str | None = Query(default=None, max_length=32),
    project: str | None = Query(default=None, max_length=120),
    tech: str | None = Query(default=None, max_length=40),
    favorites: bool = Query(default=False),
    sort: str = Query(default="recent"),
):
    from app.trash import repository as trash_repo
    from app.trash.models import TRASH_DOCUMENT

    favs = repository.favorite_page_ids(db, me.id)
    rows, total = repository.list_documents(
        db,
        search=q,
        doc_type_f=doc_type,
        work_field_f=work_field,
        project_f=project,
        tech_f=tech,
        favorite_page_ids=favs,
        favorites_only=favorites,
        sort=sort if sort in {"recent", "title"} else "recent",
        offset=page.offset,
        limit=page.page_size,
        exclude_page_ids=trash_repo.trashed_page_ids(db, TRASH_DOCUMENT),  # 휴지통 문서는 숨김
    )
    state = get_or_create_state(db)
    return {
        "items": [_doc_view(r, is_favorite=r.notion_page_id in favs) for r in rows],
        "total": total,
        "page": page.page,
        "page_size": page.page_size,
        "sync": _sync_view(state),
        "can_sync": service.can_trigger_sync(me),
    }


@router.post("", dependencies=[Depends(require_csrf)])
def create_document(
    request: Request,
    payload: DocumentCreate,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """Notion "문서" DB에 새 문서를 생성한다(제목·유형/카테고리/프로젝트·상태·소유자·메모·본문).
    주의: 이 DB가 원본에서 재생성되는 복사본이면 생성분이 덮일 수 있다(운영 데이터소스 구성에 의존)."""
    outbound = request.app.state.outbound_client
    settings = request.app.state.settings
    now = request.app.state.clock.now()

    from app.tickets.service import my_notion_id

    schema = notion_docs.fetch_documents_schema(outbound, settings)
    # 프로젝트만 Notion 관계로 기록. 문서 종류·업무 분야·기술 태그는 앱측(신규 택소노미)이다.
    project_names = [payload.project] if payload.project else []
    project_ids = notion_docs.resolve_names_to_ids(outbound, settings, schema, notion_docs.PROP_PROJECT, project_names)
    # 작성자 자동 채움: 로그인 사용자의 Notion 매핑이 있으면 Notion 작성자(person)로도 기록하고,
    # 앱 캐시엔 항상 만든 사람 이름을 넣어 목록에 작성자가 바로 뜨게 한다.
    author_id = my_notion_id(db, me)
    props = notion_docs.build_create_properties(
        title=payload.title, status=payload.status, priority=payload.priority,
        owner=payload.owner, memo=payload.memo,
        type_ids=[], category_ids=[], project_ids=project_ids, author_id=author_id,
    )
    children = notion_docs.body_children(payload.body)
    page = notion_docs.create_document(outbound, settings, properties=props, children=children)

    row = service.cache_created_document(
        db, page=page, title=payload.title,
        document_type=payload.document_type, work_field=payload.work_field,
        tech_tags=payload.tech_tags, project_names=project_names,
        status=payload.status, priority=payload.priority, owner=payload.owner,
        memo=payload.memo, author_name=me.display_name, now=now,
    )
    record_audit_from_request(
        request, db, action="team_docs.create", object_type="notion_document",
        object_id=row.notion_page_id, after={"title": payload.title},
    )
    return {"document": _doc_view(row, is_favorite=False)}


@router.get("/filters")
def get_filters(
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    favs = repository.favorite_page_ids(db, me.id)
    recent = service.recent_documents(db, me.id, limit=8)
    return {
        **service.filter_options(db),
        "recent": [_doc_view(r, is_favorite=r.notion_page_id in favs) for r in recent],
    }


@router.get("/projects")
def all_projects(
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """생성 폼용 전체 프로젝트 목록(Notion 기준). Notion 장애 시 캐시 기반 프로젝트로 폴백한다
    (이 엔드포인트만 영향받고 목록/상세는 캐시로 계속 동작 — §17.4 격리)."""
    try:
        names = notion_docs.list_all_project_names(
            request.app.state.outbound_client, request.app.state.settings
        )
    except AppError:
        names = service.filter_options(db)["projects"]
    if not names:
        names = service.filter_options(db)["projects"]
    return {"projects": names}


@router.post("/trash-bulk", dependencies=[Depends(require_csrf)])
def trash_documents_bulk(
    request: Request,
    payload: BulkPageIds,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """문서 여러 건을 한 번에 휴지통으로(목록 다중선택). 건별 권한 검사, 부분 성공.
    (리터럴 경로라 아래 GET /{page_id} 보다 먼저 선언.)"""
    result = service.trash_documents_bulk(db, user=me, page_ids=payload.page_ids, now=request.app.state.clock.now())
    for it in result["trashed"]:
        record_audit_from_request(request, db, action="team_docs.trash", object_type="notion_document",
                                  object_id=it["id"], before={"title": it.get("title")})
    return {"ok": True, **result}


@router.get("/{page_id}")
def get_document(
    request: Request,
    page_id: str,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    row = repository.get_by_page_id(db, page_id)
    if row is None:
        raise NotFoundError("문서를 찾을 수 없습니다. 동기화가 필요할 수 있습니다.")
    is_fav = repository.find_favorite(db, me.id, page_id) is not None
    # 본문 블록은 실시간 — Notion 장애면 메타만 보여주고 본문은 null(§17.4 격리).
    blocks = None
    blocks_error = None
    try:
        blocks = notion_docs.fetch_page_blocks(
            request.app.state.outbound_client,
            request.app.state.settings,
            page_id,
        )
    except AppError as exc:
        blocks_error = exc.message
    except Exception:
        blocks_error = "본문을 불러오지 못했습니다."
    # 최근 열람 기록(본인).
    service.record_view(db, user_id=me.id, page_id=page_id, now=request.app.state.clock.now())
    return {
        "document": _doc_view(row, is_favorite=is_fav),
        "blocks": blocks,
        "blocks_error": blocks_error,
    }


@router.post("/{page_id}/trash", dependencies=[Depends(require_csrf)])
def trash_document(
    request: Request,
    page_id: str,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """문서를 휴지통으로 보낸다(노션 원본은 보관기간 뒤 보관처리). 작성자/운영자만 + 감사."""
    result = service.trash_document(db, user=me, page_id=page_id, now=request.app.state.clock.now())
    record_audit_from_request(
        request, db, action="team_docs.trash", object_type="notion_document",
        object_id=page_id, before={"title": result["title"]},
    )
    return {"ok": True}


@router.post("/{page_id}/favorite", dependencies=[Depends(require_csrf)])
def toggle_favorite(
    request: Request,
    page_id: str,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
    on: bool = Query(default=True),
):
    if repository.get_by_page_id(db, page_id) is None:
        raise NotFoundError("문서를 찾을 수 없습니다.")
    is_fav = service.toggle_favorite(
        db, user_id=me.id, page_id=page_id, on=on, now=request.app.state.clock.now()
    )
    return {"ok": True, "is_favorite": is_fav}


@router.post("/sync", dependencies=[Depends(require_csrf)])
def trigger_sync(
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    if not service.can_trigger_sync(me):
        raise ForbiddenError("문서 동기화는 운영자만 실행할 수 있습니다.")
    state = sync_documents(
        db,
        outbound=request.app.state.outbound_client,
        settings=request.app.state.settings,
        now=request.app.state.clock.now(),
    )
    record_audit_from_request(
        request,
        db,
        action="team_docs.sync",
        object_type="document_sync",
        object_id="documents",
        after={"status": state.status, "doc_count": state.doc_count},
    )
    return {"sync": _sync_view(state)}
