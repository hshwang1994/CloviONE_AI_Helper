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

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.deps import get_db, require_csrf, require_permission
from app.knowledge import relations as relations_mod
from app.knowledge import service, tags as tags_mod, versions as versions_mod
from app.knowledge.schemas import (
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


def _document_json(document, *, tags=None) -> dict:
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
        "updated_at": document.updated_at,
    }
    if tags is not None:
        out["tags"] = [{"id": t.id, "name": t.name, "slug": t.slug} for t in tags]
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
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=service.PAGE_MAX),
    offset: int = Query(default=0, ge=0),
) -> dict:
    rows, total = service.list_documents(
        db, user, space_id=space_id, folder_id=folder_id, q=q, tag=tag,
        include_archived=include_archived, limit=limit, offset=offset,
    )
    return {
        "items": [_document_json(d) for d in rows],
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


@router.get("/documents/{document_id}")
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("DOCUMENT_READ")),
) -> dict:
    detail = service.document_detail(db, user, document_id)
    return {
        **_document_json(detail["document"], tags=detail["tags"]),
        "current": _version_json(detail["version"], body=True),
        "relations": detail["relations"],
        "backlinks": detail["backlinks"],
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
