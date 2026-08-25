"""Knowledge Domain API — 공간 · 폴더 · 문서 · 판 · 태그 · 관계 (S7).

## 권한은 역할이 아니라 권한으로 묻는다

S5 가 `SPACE_READ`·`SPACE_WRITE`·`SPACE_ADMIN` 을 미리 고정해 뒀다. **S7 은 새 이름을
짓지 않고 그것을 소비한다** — 새 역할이 생겨도 이 파일은 안 고친다.

**다만 권한만으로는 부족하다.** 「무엇을 할 수 있는가」와 「어느 것에 할 수 있는가」는
다른 질문이고, 뒤쪽은 서비스가 `effective_visibility_clause` 로 답한다(D-194).
게이트만 걸고 범위를 안 걸면 권한 있는 사람이 남의 부서 공간을 연다.

## 응답이 본문을 언제 싣는가

목록은 안 싣는다. 문서 하나의 본문이 수백 KB 가 될 수 있고(D-198 이 길이 제한을
없앴다), 그것이 50건 실리면 목록 한 화면이 메가바이트가 된다. 본문은 상세와
판 조회에서만 나간다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core import uploads
from app.core.audit import record_audit_from_request
from app.core.deps import (
    AuthContext,
    get_current_auth,
    get_db,
    require_csrf,
    require_permission,
)
from app.knowledge import attachments as attachments_mod
from app.knowledge import relations as relations_mod
from app.knowledge import service, tags as tags_mod, versions as versions_mod
from app.knowledge.schemas import (
    CommentCreate,
    CommentUpdate,
    DocumentCreate,
    DocumentMove,
    DocumentRelationCreate,
    DocumentSave,
    FolderCreate,
    FolderUpdate,
    SpaceCreate,
    SpaceUpdate,
    VersionRestore,
)
from app.settings.gate import block_if_maintenance
from app.storage import service as storage_service
from app.users.models import User

router = APIRouter(
    prefix="/api/knowledge",
    tags=["knowledge"],
    dependencies=[Depends(block_if_maintenance)],
)


# ── 직렬화 ───────────────────────────────────────────────────────────────────
#
# 한 자리에 모아 둔다. 화면마다 다른 필드 이름을 쓰면 프런트가 자원 하나에 여러 벌의
# 처리를 갖게 되고, 그중 하나가 빠진 화면에서 잠금 값(`version`)이 안 실려 나간다.


def _space_json(space) -> dict:
    return {
        "id": space.id,
        "name": space.name,
        "slug": space.slug,
        "description": space.description,
        "owner_kind": space.owner_kind,
        "owner_dept_id": space.owner_dept_id,
        "owner_project_id": space.owner_project_id,
        "confidential": space.confidential,
        "archived": space.archived,
        "version": space.version,
        "updated_at": space.updated_at,
    }


def _folder_json(folder) -> dict:
    return {
        "id": folder.id,
        "space_id": folder.space_id,
        "parent_id": folder.parent_id,
        "name": folder.name,
        "depth": folder.depth,
        "sort_order": str(folder.sort_order),
    }


def _document_json(document, *, tags=None, is_favorite: bool | None = None) -> dict:
    out = {
        "id": document.id,
        "space_id": document.space_id,
        "folder_id": document.folder_id,
        "title": document.title,
        "doc_type": document.doc_type,
        "source_type": document.source_type,
        "confidential": document.confidential,
        "archived": document.archived,
        "version": document.version,
        "current_version_id": document.current_version_id,
        "created_by": document.created_by,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
    }
    if tags is not None:
        out["tags"] = [{"id": t.id, "name": t.name, "slug": t.slug} for t in tags]
    if is_favorite is not None:
        out["is_favorite"] = is_favorite
    return out


def _version_json(version, *, body: bool = False) -> dict:
    if version is None:
        return {}
    out = {
        "id": version.id,
        "version_no": version.version_no,
        "author_id": version.author_id,
        "change_reason": version.change_reason,
        "ai_used": version.ai_used,
        "source": version.source,
        "created_at": version.created_at,
    }
    if body:
        out["body"] = version.body
        out["body_markdown"] = version.body_markdown
    return out


# ── 공간 ─────────────────────────────────────────────────────────────────────


@router.get("/spaces")
def list_spaces(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("SPACE_READ")),
    include_archived: bool = Query(default=False),
) -> dict:
    rows = service.list_spaces(db, user, include_archived=include_archived)
    return {"items": [_space_json(s) for s in rows]}


@router.post("/spaces", dependencies=[Depends(require_csrf)])
def create_space(
    payload: SpaceCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("SPACE_ADMIN")),
) -> dict:
    """공간을 만드는 것은 **권한 경계를 만드는 것**이라 `SPACE_ADMIN` 이다.

    문서를 쓰는 것(`SPACE_WRITE`)과 같은 선에 두면, 아무나 자기만 보이는 공간을
    만들어 조직의 글을 그 안으로 옮길 수 있다.
    """
    space = service.create_space(
        db, user,
        name=payload.name, slug=payload.slug, description=payload.description,
        owner_kind=payload.owner_kind,
        owner_dept_id=payload.owner_dept_id,
        owner_project_id=payload.owner_project_id,
        confidential=payload.confidential,
    )
    record_audit_from_request(
        request, db, action="knowledge.space_create", object_type="knowledge_space",
        object_id=space.id, after={"slug": space.slug, "owner_kind": space.owner_kind},
    )
    return _space_json(space)


@router.get("/spaces/{space_id}")
def get_space(
    space_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("SPACE_READ")),
) -> dict:
    return _space_json(service.get_scoped_space_or_404(db, user, space_id))


@router.patch("/spaces/{space_id}", dependencies=[Depends(require_csrf)])
def update_space(
    space_id: str,
    payload: SpaceUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("SPACE_ADMIN")),
) -> dict:
    fields = payload.model_dump(exclude_unset=True, exclude={"base_version"})
    before = _space_json(service.get_scoped_space_or_404(db, user, space_id))
    space = service.update_space(
        db, user, space_id, expected_version=payload.base_version, **fields
    )
    record_audit_from_request(
        request, db, action="knowledge.space_update", object_type="knowledge_space",
        object_id=space_id,
        before={"owner_kind": before["owner_kind"], "confidential": before["confidential"]},
        after={"owner_kind": space.owner_kind, "confidential": space.confidential},
    )
    return _space_json(space)


@router.get("/spaces/{space_id}/tree")
def space_tree(
    space_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("SPACE_READ")),
) -> dict:
    """공간 전체의 폴더 트리. **질의 한 번**이다 — 화면이 폴더마다 자식을 묻지 않는다."""
    return service.space_tree(db, user, space_id)


# ── 폴더 ─────────────────────────────────────────────────────────────────────


@router.post("/folders", dependencies=[Depends(require_csrf)])
def create_folder(
    payload: FolderCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("SPACE_WRITE")),
) -> dict:
    folder = service.create_folder(
        db, user, space_id=payload.space_id, name=payload.name,
        parent_id=payload.parent_id,
        before_id=payload.before_id, after_id=payload.after_id,
    )
    return _folder_json(folder)


@router.patch("/folders/{folder_id}", dependencies=[Depends(require_csrf)])
def update_folder(
    folder_id: str,
    payload: FolderUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("SPACE_WRITE")),
) -> dict:
    """이름 · 부모 · 자리. 옮기면 `path` 와 하위 전부를 **트리거가** 고친다 (D-244)."""
    folder = service.update_folder(
        db, user, folder_id,
        name=payload.name, parent_id=payload.parent_id, reparent=payload.reparent,
        before_id=payload.before_id, after_id=payload.after_id,
    )
    return _folder_json(folder)


@router.delete("/folders/{folder_id}", dependencies=[Depends(require_csrf)])
def delete_folder(
    folder_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("SPACE_WRITE")),
) -> dict:
    """폴더와 하위 폴더를 지운다. **문서는 공간 뿌리로 올라온다** — 몇 건인지 알려 준다."""
    moved = service.delete_folder(db, user, folder_id)
    return {"deleted": True, "documents_moved_to_root": moved}


# ── 문서 ─────────────────────────────────────────────────────────────────────


@router.get("/documents")
def list_documents(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("DOCUMENT_READ")),
    space_id: str | None = Query(default=None, max_length=36),
    folder_id: str | None = Query(default=None, max_length=36),
    q: str | None = Query(default=None, max_length=200),
    tag: str | None = Query(default=None, max_length=80),
    favorites: bool = Query(default=False),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=service.PAGE_MAX),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """한 페이지치 문서. `total` 을 함께 낸다 — 화면이 「몇 건 중 어디쯤」을 말할 수 있어야
    50번째 뒤에 문서가 더 있다는 사실이 사용자에게 보인다."""
    rows, total = service.list_documents(
        db, user, space_id=space_id, folder_id=folder_id, q=q, tag=tag,
        favorites=favorites, include_archived=include_archived, limit=limit, offset=offset,
    )
    # 즐겨찾기·태그는 **한 질의씩**으로 이 페이지치만 묻는다. 문서마다 묻게 두면 목록
    # 한 화면이 문서 수만큼의 질의가 된다.
    starred = service.favorite_ids(db, user, [d.id for d in rows])
    doc_tags = tags_mod.of_documents(db, [d.id for d in rows])
    return {
        "items": [
            _document_json(d, tags=doc_tags.get(d.id, []), is_favorite=d.id in starred)
            for d in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/documents", dependencies=[Depends(require_csrf)])
def create_document(
    payload: DocumentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("DOCUMENT_CREATE")),
) -> dict:
    document = service.create_document(
        db, user,
        space_id=payload.space_id, title=payload.title, folder_id=payload.folder_id,
        body=payload.body, doc_type=payload.doc_type, source_type=payload.source_type,
        tag_names=payload.tag_names, confidential=payload.confidential,
    )
    return _document_json(document, tags=tags_mod.of_document(db, document.id))


@router.get("/documents/by-legacy/{legacy_page_id}")
def resolve_legacy_document(
    legacy_page_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("DOCUMENT_READ")),
) -> dict:
    """옛 문서 주소(`/team-docs/<page id>`)가 가리키던 문서의 지금 id (S14 · C2).

    알림 딥링크 · 감사 로그 · 북마크에 옛 page id 가 박혀 있어서, 그 주소로 들어온 사람을
    지금 문서로 데려가려면 화면이 이것 하나를 물어봐야 한다. 제목도 함께 낸다 — 화면이
    옮겨 가면서 「무엇으로 데려가는지」를 말할 수 있어야 한다.
    """
    document = service.get_scoped_document_by_legacy_page_id(db, user, legacy_page_id)
    return {"id": document.id, "title": document.title}


@router.get("/documents/{document_id}")
def get_document(
    document_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("DOCUMENT_READ")),
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    detail = service.document_detail(db, user, document_id)
    document = detail["document"]
    # 최근 열람은 **부수효과**다. 여기서 실패해도 본문은 그대로 나간다
    # (`app/knowledge/recent_views.py`).
    #
    # 임퍼소네이션 중에는 **적지 않는다.** GET 이라 공용 쓰기 차단
    # (`core/deps.py::_guard_impersonation_write`)을 안 지나므로, 여기서 안 막으면 관리자가
    # 읽기 전용으로 열어 본 문서가 대상 사용자의 「최근 열람」에 조용히, 감사 로그도 없이
    # 남는다.
    if not auth.impersonating:
        service.record_view(db, user, document.id, now=request.app.state.clock.now())
    return {
        **_document_json(
            document, tags=detail["tags"],
            is_favorite=document.id in service.favorite_ids(db, user, [document.id]),
        ),
        "current": _version_json(detail["version"], body=True),
        "relations": detail["relations"],
        "backlinks": detail["backlinks"],
        "attachments": [
            attachments_mod.json_of(link, record)
            for link, record in attachments_mod.of_document(db, document_id)
        ],
    }


@router.put("/documents/{document_id}", dependencies=[Depends(require_csrf)])
def save_document(
    document_id: str,
    payload: DocumentSave,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("DOCUMENT_UPDATE")),
) -> dict:
    """제목 · 본문 · 태그를 한 트랜잭션에 저장한다.

    본문이 안 바뀌었으면 판을 안 만든다 — 그 사실을 `created_version` 으로 알려 준다.
    화면이 「저장됨」과 「새 판 1건」을 구별해서 말할 수 있어야 이력이 소음이 안 된다.
    """
    result = service.save_document(
        db, user, document_id,
        body=payload.body, title=payload.title,
        change_reason=payload.change_reason, ai_used=payload.ai_used,
        tag_names=payload.tag_names, expected_version=payload.base_version,
    )
    document = result["document"]
    return {
        **_document_json(document, tags=tags_mod.of_document(db, document.id)),
        "created_version": result["created_version"],
        "current": _version_json(result["version"]),
    }


@router.post("/documents/{document_id}/move", dependencies=[Depends(require_csrf)])
def move_document(
    document_id: str,
    payload: DocumentMove,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("DOCUMENT_UPDATE")),
) -> dict:
    """폴더를 옮긴다. **권한은 안 바뀐다** (§5.3) — 정리 축과 권한 축은 별개다."""
    document = service.move_document(
        db, user, document_id, folder_id=payload.folder_id,
        expected_version=payload.base_version,
    )
    return _document_json(document)


@router.delete("/documents/{document_id}", dependencies=[Depends(require_csrf)])
def delete_document(
    document_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("DOCUMENT_DELETE")),
) -> dict:
    """보관 처리다 — 행을 지우지 않는다(이력·멘션·관계가 함께 사라진다)."""
    document = service.delete_document(db, user, document_id)
    record_audit_from_request(
        request, db, action="knowledge.document_archive", object_type="document",
        object_id=document_id, after={"archived": True},
    )
    return _document_json(document)


# ── 판 ───────────────────────────────────────────────────────────────────────


@router.get("/documents/{document_id}/versions")
def list_versions(
    document_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("DOCUMENT_READ")),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    """이력 목록. **본문은 안 싣는다** — 수십 판의 본문이 한 응답에 들어가면 안 된다."""
    document = service.get_scoped_document_or_404(db, user, document_id)
    rows = versions_mod.history(db, document, limit=limit)
    current = versions_mod.current(db, document)
    return {
        "items": [_version_json(v) for v in rows],
        "current_version_no": current.version_no if current else None,
    }


@router.get("/documents/{document_id}/versions/{version_no}")
def get_version(
    document_id: str,
    version_no: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("DOCUMENT_READ")),
) -> dict:
    document = service.get_scoped_document_or_404(db, user, document_id)
    return _version_json(versions_mod.get(db, document, version_no), body=True)


@router.get("/documents/{document_id}/diff")
def diff_versions(
    document_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("DOCUMENT_READ")),
    base: int = Query(ge=1),
    target: int = Query(ge=1),
) -> dict:
    """두 판의 차이. **블록 단위**다 (D-198) — 줄바꿈만 바뀐 판이 전면 수정으로 안 보인다."""
    document = service.get_scoped_document_or_404(db, user, document_id)
    return versions_mod.compare(db, document, base_no=base, target_no=target)


@router.post(
    "/documents/{document_id}/versions/{version_no}/restore",
    dependencies=[Depends(require_csrf)],
)
def restore_version(
    document_id: str,
    version_no: int,
    payload: VersionRestore,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("DOCUMENT_UPDATE")),
) -> dict:
    """옛 판의 본문으로 **새 판을 쌓는다**. 이력은 그대로 남는다."""
    result = service.restore_document_version(
        db, user, document_id, version_no, expected_version=payload.base_version,
    )
    record_audit_from_request(
        request, db, action="knowledge.version_restore", object_type="document",
        object_id=document_id,
        after={"restored_from": version_no, "new_version_no": result["version"].version_no},
    )
    return {
        **_document_json(result["document"]),
        "current": _version_json(result["version"], body=True),
    }


# ── 관계 ─────────────────────────────────────────────────────────────────────


@router.post("/documents/{document_id}/relations", dependencies=[Depends(require_csrf)])
def add_relation(
    document_id: str,
    payload: DocumentRelationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("DOCUMENT_UPDATE")),
) -> dict:
    """**양쪽이 다 보여야 잇는다.** 한쪽만 보이면 안 보이는 문서의 존재가 새어 나간다."""
    service.get_scoped_document_or_404(db, user, document_id)
    service.get_scoped_document_or_404(db, user, payload.to_document_id)
    relations_mod.add(
        db, from_document_id=document_id, to_document_id=payload.to_document_id,
        kind=payload.kind, actor_id=user.id,
    )
    return {"relations": relations_mod.of_document(db, document_id)}


@router.delete("/documents/{document_id}/relations", dependencies=[Depends(require_csrf)])
def drop_relation(
    document_id: str,
    payload: DocumentRelationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("DOCUMENT_UPDATE")),
) -> dict:
    service.get_scoped_document_or_404(db, user, document_id)
    service.get_scoped_document_or_404(db, user, payload.to_document_id)
    removed = relations_mod.remove(
        db, from_document_id=document_id, to_document_id=payload.to_document_id,
        kind=payload.kind,
    )
    return {"removed": removed, "relations": relations_mod.of_document(db, document_id)}


# ── 태그 ─────────────────────────────────────────────────────────────────────


@router.get("/tags")
def list_tags(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("DOCUMENT_READ")),
) -> dict:
    """이 조직의 태그. 화면의 자동완성이 쓴다 — 그것이 없으면 사람이 같은 뜻의
    다른 표기를 계속 새로 만든다."""
    from sqlalchemy import select

    from app.knowledge.models import Tag

    org_id = getattr(user, "org_id", None)
    stmt = select(Tag).where(Tag.org_id.is_(None) if org_id is None else Tag.org_id == org_id)
    rows = db.execute(stmt.order_by(Tag.slug)).scalars().all()
    return {"items": [{"id": t.id, "name": t.name, "slug": t.slug} for t in rows]}


# ── 첨부 (S8) ────────────────────────────────────────────────────────────────
#
# 접근권은 **부모 문서가 정한다.** 그래서 세 라우트가 전부 먼저
# `get_scoped_document_or_404` 를 지난다 — 첨부에 판정을 따로 적으면 두 벌이 되고,
# 그중 하나가 빠진 자리에서 문서는 404 인데 첨부 URL 은 열린다.


@router.get("/documents/{document_id}/attachments")
def list_attachments(
    document_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("DOCUMENT_READ")),
) -> dict:
    service.get_scoped_document_or_404(db, user, document_id)
    return {
        "items": [
            attachments_mod.json_of(link, record)
            for link, record in attachments_mod.of_document(db, document_id)
        ]
    }


@router.post(
    "/documents/{document_id}/attachments",
    dependencies=[Depends(require_csrf), Depends(require_permission("FILE_UPLOAD"))],
)
def upload_attachment(
    document_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("DOCUMENT_UPDATE")),
    file: UploadFile = File(...),
    caption: str = Form(default=""),
) -> dict:
    """문서에 파일을 붙인다. **권한 둘과 범위 하나를 함께 본다.**

    권한이 둘인 이유: 파일을 올릴 수 있는가(`FILE_UPLOAD`)와 **이 문서를 고칠 수
    있는가**(`DOCUMENT_UPDATE`)는 다른 질문이다. 지금은 둘 다 전원에게 열려 있어서
    같은 답이 나오지만, 「올리기만 되는 역할」이 생기는 날 하나만 걸어 두면 그 역할이
    남의 문서를 고칠 수 있게 된다.

    범위는 권한이 안 답한다. `get_scoped_document_or_404` 가 답한다 — 권한만 보고
    범위를 안 보면 올릴 수 있는 사람이 남의 부서 문서에 파일을 붙인다.
    """
    document = service.get_scoped_document_or_404(db, user, document_id)
    # sync 핸들러에서는 UploadFile 의 내부 파일 객체를 직접 읽는다(불변 §1).
    # 상한보다 한 바이트 더 읽는다 — 정확히 상한인 파일과 넘는 파일을 구별해야 한다.
    content = file.file.read(uploads.MAX_UPLOAD_BYTES + 1)
    link, record = attachments_mod.attach(
        db, document,
        filename=file.filename or "file", content=content,
        created_by=user.id, caption=(caption.strip() or None),
    )
    record_audit_from_request(
        request, db, action="knowledge.attachment.add", object_type="knowledge_document",
        object_id=document.id,
        after={"file_id": record.id, "filename": record.filename, "size": record.size_bytes},
    )
    return attachments_mod.json_of(link, record)


@router.get(
    "/attachments/{attachment_id}/content",
    dependencies=[Depends(require_permission("FILE_DOWNLOAD"))],
)
def serve_attachment(
    attachment_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("DOCUMENT_READ")),
):
    """원본 바이트. **판정된 형식만 신뢰하고 실행은 못 하게 보낸다.**

    이미지와 PDF 만 탭 안에서 펼친다. 나머지는 내려받기로 준다 — `nosniff` 가 실행을
    막지만, 「받아서 여는 것」과 「탭 안에서 열리는 것」은 사용자가 느끼는 위험이 다르다.
    """
    link, record = attachments_mod.get_or_404(db, attachment_id)
    # 부모 문서를 못 보면 첨부도 없는 것이다. 403 이 아니라 404 인 이유는 403 이
    # 「그 문서에 그런 첨부가 있다」를 확인해 주기 때문이다.
    service.get_scoped_document_or_404(db, user, link.document_id)
    path = storage_service.file_path(db, record)
    inline = record.mime_type in uploads.INLINE_MEDIA_TYPES
    return FileResponse(
        str(path),
        media_type=record.mime_type,
        headers={
            "Content-Disposition": uploads.content_disposition(record.filename, inline=inline),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=300",
        },
    )


@router.delete("/attachments/{attachment_id}", dependencies=[Depends(require_csrf)])
def delete_attachment(
    attachment_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("DOCUMENT_UPDATE")),
) -> dict:
    link, record = attachments_mod.get_or_404(db, attachment_id)
    document = service.get_scoped_document_or_404(db, user, link.document_id)
    attachments_mod.detach(db, link)
    record_audit_from_request(
        request, db, action="knowledge.attachment.remove", object_type="knowledge_document",
        object_id=document.id, before={"file_id": record.id, "filename": record.filename},
    )
    return {"ok": True}


# ── 즐겨찾기 (S14 · C2) ──────────────────────────────────────────────────────


@router.post("/documents/{document_id}/favorite", dependencies=[Depends(require_csrf)])
def toggle_favorite(
    document_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("DOCUMENT_READ")),
    on: bool = Query(default=True),
) -> dict:
    """이 문서를 내 즐겨찾기에 담거나 뺀다.

    권한이 `DOCUMENT_READ` 인 이유: 담는 것은 **내 목록**을 고치는 일이지 문서를 고치는
    일이 아니다. 볼 수 있는 사람은 담을 수 있어야 하고, 담았다고 남의 화면이 달라지지
    않는다. 어느 문서에 담을 수 있는지는 서비스가 범위로 답한다.
    """
    state = service.toggle_favorite(
        db, user, document_id, on=on, now=request.app.state.clock.now()
    )
    return {"is_favorite": state}


# ── 댓글 (S14 · C2) ──────────────────────────────────────────────────────────
#
# 옛 문서 화면(`/team-docs`)에 있던 축을 정본 문서로 옮긴 것이다. 규약은 티켓 댓글과 같다:
# 삭제는 툼스톤이고, 쓰기는 늘 **목록 전체**로 답한다 — 클라이언트가 자기 목록을 기워
# 맞추면 툼스톤 규약이 두 벌이 되고 언젠가 갈라진다.


@router.get("/documents/{document_id}/comments")
def list_comments(
    document_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("DOCUMENT_READ")),
) -> dict:
    """그 문서의 댓글 전부(삭제된 것은 본문 없는 툼스톤)와 등장인물 신원."""
    return {"ok": True, **service.list_comments(db, user, document_id)}


@router.post("/documents/{document_id}/comments", dependencies=[Depends(require_csrf)])
def create_comment(
    document_id: str,
    payload: CommentCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("DOCUMENT_READ")),
) -> dict:
    """댓글 작성 — 그 문서가 보이는 사람 누구나.

    `DOCUMENT_UPDATE` 가 아닌 이유: 질문을 남기는 것과 남의 글을 고치는 것은 다른 일이다.
    쓰기 권한을 요구하면 「옆 팀 사람이 물어볼 곳」이 없어진다.
    """
    result = service.add_comment(
        db, user, document_id, body=payload.body, now=request.app.state.clock.now()
    )
    record_audit_from_request(
        request, db, action="knowledge.comment.create", object_type="document_comment",
        object_id=result["comment_id"], after={"document_id": document_id},
    )
    return {"ok": True, **result}


@router.patch("/comments/{comment_id}", dependencies=[Depends(require_csrf)])
def update_comment(
    comment_id: str,
    payload: CommentUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("DOCUMENT_READ")),
) -> dict:
    """댓글 수정 — **작성자 본인만**(운영자 우회 없음). 남의 문장을 고쳐 쓸 수는 없다."""
    result = service.edit_comment(
        db, user, comment_id, body=payload.body, now=request.app.state.clock.now()
    )
    record_audit_from_request(
        request, db, action="knowledge.comment.update", object_type="document_comment",
        object_id=comment_id,
    )
    return {"ok": True, **result}


@router.delete("/comments/{comment_id}", dependencies=[Depends(require_csrf)])
def delete_comment(
    comment_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("DOCUMENT_READ")),
) -> dict:
    """댓글 삭제 — 작성자 본인 또는 운영자군. 목록에는 툼스톤으로 남는다."""
    result = service.delete_comment(
        db, user, comment_id, now=request.app.state.clock.now()
    )
    record_audit_from_request(
        request, db, action="knowledge.comment.delete", object_type="document_comment",
        object_id=comment_id,
    )
    return {"ok": True, **result}
