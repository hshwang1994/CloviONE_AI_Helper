"""지식 공간 · 폴더 · 문서 — 화면이 부르는 입구 (S7).

## 이 파일이 지는 책임은 하나다: **범위**

권한 게이트(`SPACE_READ`·`SPACE_WRITE`·`DOCUMENT_*`)는 라우터가 건다. 그것은 「무엇을
할 수 있는가」에 답하고, 여기는 「**어느 것에** 할 수 있는가」에 답한다(D-194). 게이트만
걸고 범위를 안 걸면 권한 있는 사람이 남의 부서 공간을 연다.

범위 밖은 **404** 다. 403 은 「그것이 있다」를 말해 주고, 목록에 안 나오는 공간의 존재를
상세가 알려 주면 목록을 좁힌 의미가 없다.

## 판정은 한 함수다

`effective_visibility_clause` 가 목록의 SQL 을 만들고 `is_visible` 이 상세의 행을
판정한다 — **같은 규칙 목록의 두 표현**이다(D-231). 여기서 조건을 손으로 다시 적으면
목록과 상세가 갈라지고, 갈라진 상태는 「목록에는 없는데 링크로는 열린다」로만 드러난다.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.authz.visibility import (
    RESOURCE_KNOWLEDGE_DOC,
    RESOURCE_SPACE,
    context_for_user,
    effective_visibility_clause,
    is_visible,
)
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.core.models_base import utcnow
from app.core.ownership import OWNER_PROJECT
from app.knowledge import (
    blocks,
    categories,
    comments as doc_comments,
    favorites as doc_favorites,
    folders,
    mentions,
    recent_views,
    relations,
    tags,
    templates as doc_templates,
    versions,
)
from app.knowledge.models import (
    SOURCE_TYPES,
    SOURCE_USER,
    VSRC_AI,
    VSRC_USER,
    Document,
    Folder,
    KnowledgeSpace,
)
from app.users.models import User

__all__ = [
    "list_spaces",
    "get_scoped_space_or_404",
    "create_space",
    "update_space",
    "space_tree",
    "create_folder",
    "update_folder",
    "delete_folder",
    "list_documents",
    "get_scoped_document_or_404",
    "create_document",
    "save_document",
    "move_document",
    "delete_document",
    "restore_document",
    "purge_document",
    "purge_expired_documents",
    "can_manage_trashed",
    "list_page_extras",
    "workspace_summary",
    "author_options",
    "titles_of",
    "visible_document_ids",
    "recent_documents",
    "document_detail",
    "restore_document_version",
    "get_scoped_document_by_legacy_page_id",
    "toggle_favorite",
    "record_view",
    "list_comments",
    "add_comment",
    "edit_comment",
    "delete_comment",
]

# 목록 한 페이지의 최대 건수. 상한이 없으면 한 요청이 공간 전체를 실어 나른다.
PAGE_MAX = 200

# 프로젝트 축의 「없음」 센티널 — 「어느 프로젝트에도 속하지 않은(공통) 문서만」.
# 값이 UUID 와 충돌할 수 없고, 화면의 주소 축(?project=none)과 무변환으로 왕복한다.
# P-61 이 계획한 `department_id=none` 과 같은 관례다.
PROJECT_FILTER_NONE = "none"


# ── 공간 ─────────────────────────────────────────────────────────────────────


def _space_scope(db: Session, user: User):
    ctx = context_for_user(db, user)
    return ctx, effective_visibility_clause(ctx, RESOURCE_SPACE)


def list_spaces(db: Session, user: User, *, include_archived: bool = False) -> list[KnowledgeSpace]:
    _, clause = _space_scope(db, user)
    stmt = select(KnowledgeSpace)
    if clause is not None:
        stmt = stmt.where(clause)
    if not include_archived:
        stmt = stmt.where(KnowledgeSpace.archived.is_(False))
    return list(db.execute(stmt.order_by(KnowledgeSpace.name)).scalars().all())


def get_scoped_space_or_404(db: Session, user: User, space_id: str) -> KnowledgeSpace:
    """범위 밖이면 **404**. 상세가 존재를 알려 주면 목록을 좁힌 의미가 없다."""
    space = db.get(KnowledgeSpace, space_id)
    if space is None:
        raise NotFoundError("공간을 찾지 못했습니다.")
    ctx = context_for_user(db, user)
    if not is_visible(db, ctx, RESOURCE_SPACE, space):
        raise NotFoundError("공간을 찾지 못했습니다.")
    return space


def create_space(
    db: Session,
    user: User,
    *,
    name: str,
    slug: str,
    description: str = "",
    owner_kind: str,
    owner_dept_id: str | None = None,
    owner_project_id: str | None = None,
    confidential: bool = False,
) -> KnowledgeSpace:
    clean_name = (name or "").strip()
    clean_slug = (slug or "").strip().lower()
    if not clean_name:
        raise ValidationAppError("공간 이름을 입력해 주세요.")
    if not clean_slug:
        raise ValidationAppError("공간 주소를 입력해 주세요.")

    org_id = getattr(user, "org_id", None)
    exists = db.execute(
        select(KnowledgeSpace.id).where(
            KnowledgeSpace.slug == clean_slug,
            KnowledgeSpace.org_id.is_(None) if org_id is None else KnowledgeSpace.org_id == org_id,
        )
    ).scalars().first()
    if exists:
        raise ConflictError("같은 주소의 공간이 이미 있습니다.")

    space = KnowledgeSpace(
        org_id=org_id,
        name=clean_name,
        slug=clean_slug,
        description=(description or "").strip(),
        owner_kind=owner_kind,
        owner_dept_id=owner_dept_id,
        owner_project_id=owner_project_id,
        confidential=bool(confidential),
        created_by=user.id,
    )
    db.add(space)
    db.flush()
    return space


def resolve_or_create_project_space(db: Session, user: User, project_id: str) -> KnowledgeSpace:
    """그 프로젝트의 지식 공간을 찾거나 만든다 (§14.2).

    사용자가 이해해야 하는 것은 "어느 프로젝트"뿐이다(§14.4) — "공간"이라는 개념을
    몰라도 새 문서를 그 프로젝트 아래 만들 수 있어야 한다. 프로젝트마다 미리 만들지
    않는다: 문서가 하나라도 그 프로젝트를 고르는 순간에만 만든다(그러지 않으면 문서가
    하나도 없는 프로젝트 공간이 탐색기에 줄줄이 선다).

    권한 재검증은 **프로젝트 자체의 범위 게이트**로 한다(`SPACE_ADMIN` 이 아니다) —
    이 경로를 타는 사용자는 문서를 만들 뿐 공간을 관리하는 것이 아니다. 그 프로젝트를
    볼 수 없으면 여기서 404 를 낸다.

    `app/projects/service.py::get_scoped_project_or_404` 를 부르지 않는다 — 그쪽은
    `Principal` 을 받는데, 그것을 새로 만들면(`app/work/service.py` 가 같은 이유로
    자기 게이트를 하나 더 둔 이유) 이 모듈이 이미 쓰는 `context_for_user` 경로와 갈라진
    판정 경로가 생긴다. 판정 자체는 양쪽 다 `effective_visibility_clause` 하나다(D-194).
    """
    from app.authz.visibility import RESOURCE_PROJECT
    from app.projects.models import Project

    ctx = context_for_user(db, user)
    stmt = select(Project).where(Project.id == project_id)
    clause = effective_visibility_clause(ctx, RESOURCE_PROJECT)
    if clause is not None:
        stmt = stmt.where(clause)
    project = db.execute(stmt).scalar_one_or_none()
    if project is None:
        raise NotFoundError("프로젝트를 찾을 수 없습니다.")
    existing = db.execute(
        select(KnowledgeSpace).where(
            KnowledgeSpace.owner_kind == OWNER_PROJECT,
            KnowledgeSpace.owner_project_id == project.id,
        )
    ).scalars().first()
    if existing is not None:
        return existing
    return create_space(
        db, user,
        name=project.name, slug=(project.code or project.id[:8]).lower(),
        owner_kind=OWNER_PROJECT, owner_project_id=project.id,
    )


def update_space(
    db: Session, user: User, space_id: str, *, expected_version: int | None = None, **fields
) -> KnowledgeSpace:
    space = get_scoped_space_or_404(db, user, space_id)
    _check_lock(space, expected_version)

    for key in ("name", "description", "owner_kind", "owner_dept_id",
                "owner_project_id", "confidential", "archived"):
        if key in fields and fields[key] is not None:
            value = fields[key]
            setattr(space, key, value.strip() if isinstance(value, str) else value)
    space.version += 1
    db.flush()
    return space


def _check_lock(row, expected_version: int | None) -> None:
    """낙관적 잠금 (D-240). 세 자원이 **같은 이름의 같은 규약**이라 검사도 하나다."""
    if expected_version is not None and row.version != expected_version:
        raise ConflictError("다른 사람이 먼저 저장했습니다. 새로 고친 뒤 다시 시도해 주세요.")


# ── 폴더 ─────────────────────────────────────────────────────────────────────


def space_tree(db: Session, user: User, space_id: str) -> dict:
    space = get_scoped_space_or_404(db, user, space_id)
    return {
        "space": {"id": space.id, "name": space.name, "slug": space.slug},
        "folders": folders.tree(db, space.id),
    }


def get_scoped_folder_or_404(db: Session, user: User, folder_id: str) -> Folder:
    folder = db.get(Folder, folder_id)
    if folder is None:
        raise NotFoundError("폴더를 찾지 못했습니다.")
    # 폴더는 권한 축이 아니다 — 공간을 통과시키는 것이 곧 폴더를 통과시키는 것이다(§5.3).
    get_scoped_space_or_404(db, user, folder.space_id)
    return folder


def create_folder(
    db: Session, user: User, *, space_id: str, name: str,
    parent_id: str | None = None, before_id: str | None = None, after_id: str | None = None,
) -> Folder:
    space = get_scoped_space_or_404(db, user, space_id)
    return folders.create(
        db, space_id=space.id, name=name, parent_id=parent_id,
        before_id=before_id, after_id=after_id,
    )


def update_folder(
    db: Session, user: User, folder_id: str, *,
    name: str | None = None, parent_id: str | None = None, reparent: bool = False,
    before_id: str | None = None, after_id: str | None = None,
) -> Folder:
    """이름 · 부모 · 자리를 한 번에 고친다.

    `reparent` 를 따로 받는 이유: `parent_id=None` 은 「뿌리로 옮긴다」이고 「부모를 안
    건드린다」가 아니다. 둘을 한 값으로 표현하면 뿌리로 옮기는 요청이 조용히 무시된다.
    """
    folder = get_scoped_folder_or_404(db, user, folder_id)
    if name is not None:
        folders.rename(db, folder, name)
    if reparent:
        folders.move(db, folder, parent_id=parent_id, before_id=before_id, after_id=after_id)
    elif before_id is not None or after_id is not None:
        folders.reorder(db, folder, before_id=before_id, after_id=after_id)
    return folder


def delete_folder(db: Session, user: User, folder_id: str) -> int:
    """폴더와 그 **하위 폴더**를 지운다. 문서는 안 지운다 — 공간 뿌리로 올라온다.

    문서까지 함께 지우면 폴더 하나를 잘못 지운 날 그 아래 글이 전부 사라지고, 글은
    재계산으로 안 돌아온다. 몇 건이 올라왔는지는 돌려준다 — 화면이 「문서 12건이
    공간 뿌리로 이동했습니다」라고 말할 수 있어야 사용자가 놀라지 않는다.
    """
    folder = get_scoped_folder_or_404(db, user, folder_id)
    subtree = folders.subtree_ids(db, folder)
    moved = db.execute(
        select(func.count()).select_from(Document).where(Document.folder_id.in_(subtree))
    ).scalar_one()
    db.delete(folder)
    db.flush()
    # 하위 폴더는 DB CASCADE 로, 문서의 `folder_id` 는 DB SET NULL 로 바뀌었다 — 둘 다
    # ORM 이 모르는 변화다. 세션이 `expire_on_commit=False` 라 다시 읽게 하지 않으면
    # 같은 요청 안의 이어지는 조회가 지워진 폴더를 계속 든다.
    db.expire_all()
    return int(moved)


# ── 문서 ─────────────────────────────────────────────────────────────────────


def _document_scope(db: Session, user: User):
    ctx = context_for_user(db, user)
    return ctx, effective_visibility_clause(ctx, RESOURCE_KNOWLEDGE_DOC)


#: 목록의 정렬 축. 이름 → SQL 표현으로 **여기 한 곳**에서 푼다.
#:
#: 화면이 컬럼 이름을 문자열로 보내고 서버가 그대로 `order_by` 에 넣으면 그것은 SQL 에
#: 임의의 이름을 실어 보내는 길이다(같은 이유로 `app/work/rank.py` 가 허용 목록을 둔다).
#: 모르는 값은 기본값으로 떨어진다 — 거절하면 옛 주소를 들고 온 사람의 목록이 통째로 깨진다.
SORTS: tuple[str, ...] = ("recent", "created", "title", "archived")


def _order_by(sort: str | None):
    """정렬은 **전순서**여야 한다 — 뒤에 `id` 를 붙이는 이유가 그것이다(아래 주석)."""
    if sort == "created":
        return (Document.created_at.desc(), Document.id.asc())
    if sort == "title":
        return (Document.title.asc(), Document.id.asc())
    if sort == "archived":
        # 휴지통이 쓰는 축. 0021 이전에 보관된 문서는 이 값이 NULL 이라 뒤로 보낸다 —
        # 앞에 세우면 「가장 최근에 버린 것」 자리에 시각을 모르는 행이 선다.
        return (Document.archived_at.desc().nullslast(), Document.id.asc())
    return (Document.updated_at.desc(), Document.id.asc())


def list_documents(
    db: Session, user: User, *, space_id: str | None = None, project_id: str | None = None,
    folder_id: str | None = None,
    q: str | None = None, tags: list[str] | None = None, category_id: str | None = None,
    favorites: bool = False,
    include_archived: bool = False, archived_only: bool = False,
    created_by: str | None = None, drafts: bool = False, sort: str | None = None,
    limit: int = 50, offset: int = 0,
) -> tuple[list[Document], int]:
    """문서 목록. **권한 조건이 상한 앞에 걸린다**(Z6 · D-202).

    `folder_id` 는 그 폴더 **아래 전부**를 뜻한다. 직계 자식만 보여 주면 사용자는
    「분명 여기 넣었는데 없다」를 자주 만난다 — 폴더를 한 겹 더 만든 사실을 잊기 때문이다.

    `project_id` 는 그 프로젝트가 소유한 공간의 문서로 좁힌다(§11.4). 권한은 이미 걸린
    `clause` 가 맡는다 — 볼 수 없는 프로젝트를 넘기면 조건을 만족하는 공간이 없어 결과가
    0건이 될 뿐이다(별도 게이트를 다시 걸지 않는다, 다른 필터들과 같은 방식).

    `tags` 는 **다중이고 AND** 다 — 고른 태그를 전부 가진 문서로 좁힌다(고르개가 늘수록
    범위가 넓어지면 "좁히는 필터"라는 사용자의 기대와 어긋난다).

    `drafts` 는 「아직 한 번도 고치지 않은 문서」다. 이 제품에 **초안 상태 같은 것은
    없고**(문서에 상태 칸이 없다) 만들지도 않는다 — 대신 이미 있는 사실 하나를 읽는다:
    `version` 은 만들 때 1 이고 저장할 때마다 오른다. 그래서 `version <= 1` 은 「만들어
    놓고 아직 손대지 않았다」와 정확히 같은 말이다.
    """
    ctx, clause = _document_scope(db, user)

    stmt = select(Document)
    if clause is not None:
        stmt = stmt.where(clause)
    if space_id:
        space = get_scoped_space_or_404(db, user, space_id)
        stmt = stmt.where(Document.space_id == space.id)
    if project_id == PROJECT_FILTER_NONE:
        # 「어느 프로젝트에도 속하지 않은 문서」 — 프로젝트 소유가 아닌 공간 전부다.
        # `!= OWNER_PROJECT` 인 이유는 분할 완전성이다: 각 프로젝트 + 공통 = 전체가
        # 되어야 어느 필터로도 못 찾는 문서가 안 생긴다(P-61 의 `department_id` 센티널과
        # 같은 관례). 가시성 절은 위에서 이미 걸렸다 — 이 필터는 좁히기만 한다.
        stmt = stmt.where(
            Document.space_id.in_(
                select(KnowledgeSpace.id).where(KnowledgeSpace.owner_kind != OWNER_PROJECT)
            )
        )
    elif project_id:
        stmt = stmt.where(
            Document.space_id.in_(
                select(KnowledgeSpace.id).where(
                    KnowledgeSpace.owner_kind == OWNER_PROJECT,
                    KnowledgeSpace.owner_project_id == project_id,
                )
            )
        )
    if folder_id:
        folder = get_scoped_folder_or_404(db, user, folder_id)
        stmt = stmt.where(Document.folder_id.in_(folders.subtree_ids(db, folder)))
    if archived_only:
        # 휴지통이 쓰는 갈래다. `include_archived` 는 「보관된 것도 함께」이고 이쪽은
        # 「보관된 것만」이라 다른 질문이다 — 한 깃발로 둘을 표현하면 휴지통이 살아 있는
        # 문서를 함께 보여 준다.
        stmt = stmt.where(Document.archived.is_(True))
    elif not include_archived:
        stmt = stmt.where(Document.archived.is_(False))
    if created_by:
        stmt = stmt.where(Document.created_by == created_by)
    if category_id:
        # 권한은 이미 걸린 clause 가 맡는다 — 남의 조직 카테고리 id 를 넘기면 그 분류의
        # 보이는 문서가 없어 0건이 될 뿐이다(`project_id` 필터와 같은 방식).
        stmt = stmt.where(Document.category_id == category_id)
    if drafts:
        stmt = stmt.where(Document.version <= 1)
    if q and q.strip():
        needle = f"%{q.strip()}%"
        # 제목**과 본문**을 본다 (지시 22.4). 본문은 현재 판의 파생 텍스트에서 찾는다 —
        # Block JSON 을 뒤지면 서식 속성까지 걸려서 「없는 말」이 찾아진다.
        from app.knowledge.models import DocumentVersion

        stmt = stmt.where(
            Document.title.ilike(needle)
            | Document.current_version_id.in_(
                select(DocumentVersion.id).where(DocumentVersion.body_text.ilike(needle))
            )
        )
    clean_tags = [t.strip() for t in (tags or []) if t and t.strip()]
    if clean_tags:
        from app.knowledge import tags as tags_mod
        from app.knowledge.models import DocumentTag, Tag

        wanted_slugs = tuple(sorted({tags_mod.slugify(t) for t in clean_tags}))
        # AND: 고른 태그 수만큼 EXISTS 를 겹친다. 문서 하나가 그 태그 전부를 가져야 하므로
        # 단순 `IN` + `GROUP BY HAVING COUNT` 대신 태그마다 독립된 존재 조건을 건다 —
        # 읽는 사람이 "왜 3개"인지 SQL 만 보고 알 수 있다(고른 태그 수와 조건 수가 같다).
        for slug in wanted_slugs:
            stmt = stmt.where(
                Document.id.in_(
                    select(DocumentTag.document_id)
                    .join(Tag, Tag.id == DocumentTag.tag_id)
                    .where(Tag.slug == slug)
                )
            )
    if favorites:
        # 즐겨찾기는 **내용 필터**다(무엇을 볼지). 권한 조건과 나란히 걸리므로, 남이 담아 둔
        # 문서가 이 목록에 새어 들어올 수 없다.
        from app.knowledge.models import DocumentFavorite

        stmt = stmt.where(
            Document.id.in_(
                select(DocumentFavorite.document_id)
                .where(DocumentFavorite.user_id == user.id)
            )
        )

    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()

    rows = list(
        db.execute(
            # 정렬은 **전순서**여야 한다 (Z9 · 티켓 목록이 이미 같은 규칙을 쓴다,
            # `app/tickets/query.py::ORDER`). `updated_at` 하나로만 정렬하면 같은 시각의
            # 행들 사이 순서를 DB 가 매번 마음대로 정하고, 그 순간 OFFSET 페이지네이션이
            # **1쪽에 나온 문서를 2쪽에 또 내거나 아예 빠뜨린다** — 사용자에게는 "문서가
            # 사라졌다" 로 보이고 새로고침하면 돌아와서 재현조차 안 된다. 이관은 문서
            # 여럿을 한 회차에 적재하므로 같은 시각이 실제로 생긴다.
            stmt.order_by(*_order_by(sort))
            .limit(max(1, min(limit, PAGE_MAX)))
            .offset(max(0, offset))
        ).scalars().all()
    )
    return rows, int(total)


def get_scoped_document_or_404(db: Session, user: User, document_id: str) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise NotFoundError("문서를 찾지 못했습니다.")
    ctx = context_for_user(db, user)
    if not is_visible(db, ctx, RESOURCE_KNOWLEDGE_DOC, document):
        raise NotFoundError("문서를 찾지 못했습니다.")
    return document


def create_document(
    db: Session, user: User, *, space_id: str | None = None, project_id: str | None = None,
    title: str,
    folder_id: str | None = None, body: dict | None = None,
    doc_type: str | None = None, source_type: str = SOURCE_USER,
    tag_names: list[str] | None = None, category_id: str | None = None,
    confidential: bool = False,
    template: str | None = None,
) -> Document:
    """`space_id` 나 `project_id` 중 하나를 받는다 — 화면은 보통 후자만 안다(§14.4).

    `project_id` 를 주면 그 프로젝트의 공간을 찾거나 만든다
    (`resolve_or_create_project_space`). 화면이 "공간" 개념을 몰라도 프로젝트 문서를
    만들 수 있는 것이 이 매개변수가 존재하는 이유다.
    """
    if project_id:
        space = resolve_or_create_project_space(db, user, project_id)
    elif space_id:
        space = get_scoped_space_or_404(db, user, space_id)
    else:
        raise ValidationAppError("어느 프로젝트(또는 공간)의 문서인지 골라 주세요.")
    if source_type not in SOURCE_TYPES:
        raise ValidationAppError(f"모르는 문서 출처입니다: {source_type}")
    if folder_id:
        folder = get_scoped_folder_or_404(db, user, folder_id)
        if folder.space_id != space.id:
            raise ValidationAppError("다른 공간의 폴더에는 넣을 수 없습니다.")

    clean_title = (title or "").strip()
    if not clean_title:
        raise ValidationAppError("문서 제목을 입력해 주세요.")

    # 카테고리는 문서의 조직(=공간의 조직) 것이어야 한다. 남의 조직 id 는 404 다.
    if category_id:
        categories.get_or_404(db, space.org_id, category_id)

    # 틀은 **본문이 없을 때만** 채운다. 본문을 들고 온 경로(제안을 문서로 옮기는 자리)가
    # 틀 때문에 그 내용을 잃으면, 사용자는 자기가 쓴 글이 사라진 것으로 본다.
    if body is None:
        body = doc_templates.body_for(template)

    document = Document(
        space_id=space.id,
        folder_id=folder_id,
        title=clean_title,
        doc_type=(doc_type or "").strip() or None,
        category_id=category_id or None,
        source_type=source_type,
        confidential=bool(confidential),
        created_by=user.id,
    )
    db.add(document)
    db.flush()

    version = versions.snapshot(
        db, document, body if body is not None else blocks.empty_doc(),
        author_id=user.id,
        change_reason="문서를 만들었습니다.",
        source=VSRC_AI if source_type == "AI" else VSRC_USER,
        ai_used=source_type == "AI",
    )
    if version is not None:
        mentions.sync(db, document, version.body)
    if tag_names:
        tags.set_for_document(db, document, tag_names)
    db.flush()
    return document


#: `save_document` 의 「안 보냈다」 표식. `None` 은 「분류를 해제한다」라 다른 값이 필요하다.
UNSET = object()


def save_document(
    db: Session, user: User, document_id: str, *,
    body: dict | None = None, title: str | None = None,
    change_reason: str | None = None, ai_used: bool = False,
    tag_names: list[str] | None = None,
    category_id=UNSET,
    expected_version: int | None = None,
) -> dict:
    """제목 · 본문 · 태그 · 카테고리를 **한 트랜잭션**에 저장한다.

    본문이 안 바뀌었으면 판을 안 만든다(`versions.snapshot` 이 `None` 을 낸다) — 그래도
    제목이나 태그는 저장된다. 「저장했는데 아무 일도 안 일어났다」가 되면 안 되기 때문이다.

    `category_id` 는 기본값이 `UNSET` 이다 — `None` 은 「미분류로 되돌린다」는 실제 값이라,
    카테고리를 모르는 호출자가 분류를 지우지 않으려면 「안 보냈다」가 따로 있어야 한다.
    """
    document = get_scoped_document_or_404(db, user, document_id)
    _check_lock(document, expected_version)

    changed = False
    if title is not None:
        clean = title.strip()
        if not clean:
            raise ValidationAppError("문서 제목을 입력해 주세요.")
        if clean != document.title:
            document.title = clean
            changed = True

    version = None
    if body is not None:
        version = versions.snapshot(
            db, document, body,
            author_id=user.id, change_reason=change_reason, ai_used=bool(ai_used),
            source=VSRC_USER,
        )
        if version is not None:
            mentions.sync(db, document, version.body)
            changed = True

    if tag_names is not None:
        tags.set_for_document(db, document, tag_names)
        changed = True

    if category_id is not UNSET:
        next_id = category_id or None
        if next_id:
            categories.get_or_404(db, tags.document_org_id(db, document), next_id)
        if next_id != document.category_id:
            document.category_id = next_id
            changed = True

    if changed:
        document.version += 1
        document.updated_at = utcnow()
    db.flush()
    return {
        "document": document,
        "version": version,
        "created_version": version is not None,
    }


def move_document(
    db: Session, user: User, document_id: str, *, folder_id: str | None = None,
    project_id: str | None = None, expected_version: int | None = None,
) -> tuple[Document, bool]:
    """정리(폴더)와 소속(프로젝트)을 한 호출로 옮긴다 (§14.4 이동 대화상자).

    `folder_id` 만 오면 폴더 이동 — **같은 공간 안에서만** 옮긴다. `project_id` 가 오면
    소속(공간) 이동이다: 그 프로젝트의 공간을 찾거나 만들고(`resolve_or_create_project_space`),
    권한 경계가 바뀌므로 옛 폴더 참조는 버린다(다른 공간의 폴더를 가리키게 둘 수 없다 —
    0023 마이그레이션이 프로젝트 재배치에서 하는 것과 같은 처리). 이 함수를 부르는
    라우터는 소속이 실제로 바뀐 경우에만 감사 로그를 남긴다 — **폴더 정리는 권한을 안
    바꾸지만 소속 이동은 바꾼다**(§5.3), 그 차이가 로그에도 드러나야 한다.

    두 번째 반환값은 "소속(공간)이 실제로 바뀌었는가" — 라우터가 감사 로그 여부를
    그것으로 정한다.
    """
    document = get_scoped_document_or_404(db, user, document_id)
    _check_lock(document, expected_version)

    space_changed = False
    if project_id:
        new_space = resolve_or_create_project_space(db, user, project_id)
        if new_space.id != document.space_id:
            document.space_id = new_space.id
            document.folder_id = None
            space_changed = True
        elif folder_id:
            folder = get_scoped_folder_or_404(db, user, folder_id)
            if folder.space_id != document.space_id:
                raise ValidationAppError("다른 공간의 폴더로는 옮길 수 없습니다.")
            document.folder_id = folder_id
    elif folder_id:
        folder = get_scoped_folder_or_404(db, user, folder_id)
        if folder.space_id != document.space_id:
            raise ValidationAppError("다른 공간의 폴더로는 옮길 수 없습니다.")
        document.folder_id = folder_id
    else:
        document.folder_id = None

    document.version += 1
    db.flush()
    return document, space_changed


def delete_document(db: Session, user: User, document_id: str, *, now=None) -> Document:
    """보관 처리다 — 행을 지우지 않는다.

    지우면 이력·멘션·관계가 CASCADE 로 함께 사라지고, 셋 다 재계산으로 안 돌아온다.
    「지웠다」와 「보이지 않는다」는 사용자에게 같은 일이지만 복구 가능성이 다르다.

    **누가 언제 버렸는지를 함께 적는다** (0021). 그 둘이 없으면 휴지통이 「삭제한 사람」도
    「삭제 예정」도 말할 수 없고, 되살릴 권한을 누구에게 줄지도 판정할 수 없다.
    """
    document = get_scoped_document_or_404(db, user, document_id)
    document.archived = True
    document.archived_at = now or utcnow()
    document.archived_by = user.id
    document.version += 1
    db.flush()
    return document


def restore_document(db: Session, user: User, document_id: str) -> Document:
    """휴지통에서 되살린다 — `archived` 를 내린다 (지시 22.7).

    ## 무엇을 확인하는가

    * **공간**은 확인할 필요가 없다. 공간이 사라졌으면 문서도 CASCADE 로 함께 사라져
      여기까지 못 온다.
    * **폴더**도 마찬가지다. 폴더를 지우면 문서의 `folder_id` 는 그때 이미 NULL 이 됐고
      (SET NULL), 그 문서는 공간 첫 화면으로 올라온다.
    * **권한**은 지금 이 사람의 것으로 다시 본다 — `get_scoped_document_or_404` 가 그
      문이다. 버릴 때 보이던 문서가 지금은 안 보일 수 있고, 그때는 404 다.
    * **판 · 관계 · 첨부**는 애초에 안 사라졌다. 보관은 행을 지우는 것이 아니었다.
    * **색인**은 다시 건다. 보관 중에는 검색과 AI 후보에서 빠져 있었으므로
      (`app/search/indexer.py` · `app/ai/retrieval/service.py`), 되살린 문서가 다시
      찾아지려면 신호가 필요하다.

    두 번 눌러도 같은 결과다 — 이미 살아 있으면 아무 일도 안 한다. 실패로 만들면 목록을
    열어 둔 사이에 누가 먼저 되살린 경우가 오류로 보인다.
    """
    from app.ai.index import service as index_service

    document = get_scoped_document_or_404(db, user, document_id)
    if not document.archived:
        return document
    document.archived = False
    document.archived_at = None
    document.archived_by = None
    document.version += 1
    index_service.enqueue(db, document.id)
    db.flush()
    return document


def purge_document(db: Session, user: User, document_id: str) -> dict:
    """영구 삭제 — **행을 지운다. 되돌릴 수 없다.**

    보관과 다른 동작이다. 보관은 `archived` 를 세우는 것이라 되살릴 수 있고, 이것은
    `documents` 행을 지워 판·태그·관계·멘션·댓글·즐겨찾기·색인 조각이 CASCADE 로 함께
    사라진다. 그래서 **휴지통에 있는 문서만** 지날 수 있다: 살아 있는 문서를 이 문으로
    지우는 경로를 열어 두면 「삭제」 버튼 하나가 실수로 영구 삭제가 된다.

    첨부의 **파일 자체는 안 지운다**. 지우는 것은 문서와 파일을 잇는 줄(`document_attachments`)
    뿐이고, 바이너리는 저장소 정책의 별도 Sweep 이 맡는다(지시 22.3).
    """
    document = get_scoped_document_or_404(db, user, document_id)
    if not document.archived:
        raise ValidationAppError("휴지통에 있는 문서만 영구 삭제할 수 있습니다.")
    info = {"id": document.id, "title": document.title}
    db.delete(document)
    db.flush()
    return info


def purge_expired_documents(
    db: Session, *, now, retention_days: int, enabled: bool = True, limit: int = 200
) -> dict:
    """보관 기간이 지난 문서를 **영구 삭제한다** (지시 22.9 개정 · D-352).

    ## 기준은 `archived_at` 하나다

    `created_at` 도 `updated_at` 도 아니다. 3년 전에 쓴 문서를 어제 버렸다면 남은 시간은
    이레이고, 어제 고친 문서를 3주 전에 버렸다면 이미 지났다. 그 둘을 뒤집는 값으로 판정하면
    사람이 예상한 것과 정확히 반대로 사라진다.

    되살린 문서는 `archived_at` 이 NULL 로 돌아가므로(`restore_document`) **그 순간 대상에서
    빠진다.** 조건에 `archived` 와 `archived_at IS NOT NULL` 을 함께 거는 이유다.

    ## 끌 수 있다

    `enabled` 가 거짓이면 아무것도 안 지운다. 자동으로 지우는 일을 원하지 않는 설치가 그것을
    고르는 방법이 있어야 하고, 그 선택은 설정 한 곳(`document_trash_autopurge`)에서 온다.

    ## 한 번에 다 지우지 않는다

    `limit` 이 있는 이유는 락이다. 정리는 배경 작업이고, 그 작업이 문서 수백 건의 CASCADE
    를 한 트랜잭션에 묶으면 그동안 문서 쓰기가 전부 기다린다. 남은 것은 다음 주기에 지운다 —
    하루에 여러 번 도는 작업이라 밀리지 않는다.

    ## 파일은 안 지운다

    첨부의 연결(`document_attachments`)은 CASCADE 로 사라지지만 `files` 행과 그 뒤의
    바이너리는 그대로 둔다. 같은 파일이 다른 문서에도 붙어 있을 수 있고(같은 체크섬은 한
    행을 나눠 쓴다), 무엇보다 **추측해서 지우면 안 되는 것**이 파일이다. 도달할 수 없는
    바이트의 정리는 저장소 정책의 별도 Sweep 이 맡는다.
    """
    from datetime import timedelta

    if not enabled:
        return {"purged": 0, "skipped": "자동 영구 삭제가 꺼져 있습니다."}
    days = max(1, int(retention_days or 1))
    cutoff = now - timedelta(days=days)

    rows = list(db.execute(
        select(Document)
        .where(
            Document.archived.is_(True),
            Document.archived_at.is_not(None),
            Document.archived_at <= cutoff,
        )
        .order_by(Document.archived_at)
        .limit(max(1, limit))
    ).scalars().all())
    titles = [d.title for d in rows[:20]]
    for document in rows:
        # 판·태그·멘션·관계·댓글·즐겨찾기·최근 열람·색인 조각·첨부 연결이 전부 이 한 줄에
        # 딸려 사라진다(전부 `ON DELETE CASCADE`). 표를 여기서 하나씩 지우지 않는 이유가
        # 그것이다 — 손으로 적으면 새 표가 생긴 날 그 표만 고아로 남는다.
        db.delete(document)
    db.flush()
    return {"purged": len(rows), "retention_days": days, "titles": titles}


def can_manage_trashed(user: User, document: Document) -> bool:
    """되살리기·영구 삭제를 할 수 있는 사람 — **공용 휴지통과 같은 규칙**이다.

    `app/trash/service.py::ensure_can_manage` 가 「운영자군이거나 버린 본인」으로 정해
    뒀다. 문서라고 다른 기준을 쓰면 같은 화면의 두 줄이 다른 규칙으로 움직인다.

    범위(어느 문서가 보이는가)는 여기서 안 본다 — 그것은 이미
    `get_scoped_document_or_404` 가 답했고, 두 곳에서 답하면 한쪽만 고쳐지는 날이 온다.
    """
    from app.core.authz import MODERATOR_ROLES

    return user.role in MODERATOR_ROLES or document.archived_by == user.id


def document_detail(db: Session, user: User, document_id: str) -> dict:
    """상세 한 벌 — 본문 · 태그 · 관계 · 역링크.

    관계와 역링크는 **가시성으로 좁힌 뒤** 낸다. 안 좁히면 「관련 문서 3건」이라고
    말해 놓고 열면 404 가 되고, 그 숫자 자체가 남의 공간에 무엇이 있는지 알려 준다.
    """
    document = get_scoped_document_or_404(db, user, document_id)
    version = versions.current(db, document)

    related = relations.of_document(db, document.id)
    visible_ids = _visible_document_ids(db, user, [r["document_id"] for r in related])
    related = [r for r in related if r["document_id"] in visible_ids]

    back = mentions.backlinks(
        db, target_kind="document", target_id=document.id,
        document_ids=list(_all_visible_document_ids(db, user)),
    )

    return {
        "document": document,
        "version": version,
        "tags": tags.of_document(db, document.id),
        "relations": related,
        "backlinks": [{"document_id": m.document_id, "block_id": m.block_id} for m in back],
        # 이 문서가 가리키는 티켓 (지시 22.8). **티켓 축으로 좁혀서** 낸다 — 문서가 보인다고
        # 그 문서가 언급한 티켓이 보이는 것은 아니다(회의 화면에서 같은 것을 놓칠 뻔했다).
        "ticket_mentions": _visible_ticket_mentions(db, user, document.id),
    }


def _visible_ticket_mentions(db: Session, user: User, document_id: str) -> list[dict]:
    """{ticket_id, key, title} — 내가 볼 수 있는 티켓만.

    판정은 업무 도메인이 이미 가진 것을 그대로 쓴다(`work.service._visible_tickets_stmt`,
    D-194). 여기서 규칙을 다시 적으면 문서 화면만 옛 규칙으로 남는다.
    """
    from app.tickets.models import Ticket
    from app.work import service as work_service
    from app.work.resolve import display_key

    ids = [m.target_id for m in mentions.of_document(db, document_id, target_kind="ticket")]
    if not ids:
        return []
    rows = db.execute(
        work_service._visible_tickets_stmt(db, user).where(Ticket.id.in_(tuple(dict.fromkeys(ids))))
    ).scalars().all()
    return [{"ticket_id": t.id, "key": display_key(t), "title": t.title} for t in rows]


def _visible_document_ids(db: Session, user: User, ids: list[str]) -> set[str]:
    if not ids:
        return set()
    _, clause = _document_scope(db, user)
    stmt = select(Document.id).where(Document.id.in_(tuple(sorted(set(ids)))))
    if clause is not None:
        stmt = stmt.where(clause)
    return {str(v) for v in db.execute(stmt).scalars().all()}


def visible_document_ids(db: Session, user: User) -> list[str]:
    """내가 볼 수 있는 문서 id 전부. 태그 사용 수를 셀 때 쓴다.

    보관된 문서도 **포함한다** — 휴지통에 있는 문서에 붙은 태그도 그 태그를 지우면 함께
    끊긴다. 「지우면 무엇이 끊기는가」를 적게 말하면 안 된다.
    """
    _, clause = _document_scope(db, user)
    stmt = select(Document.id)
    if clause is not None:
        stmt = stmt.where(clause)
    return [str(v) for v in db.execute(stmt).scalars().all()]


def _all_visible_document_ids(db: Session, user: User) -> set[str]:
    _, clause = _document_scope(db, user)
    stmt = select(Document.id)
    if clause is not None:
        stmt = stmt.where(clause)
    return {str(v) for v in db.execute(stmt).scalars().all()}


def restore_document_version(
    db: Session, user: User, document_id: str, version_no: int,
    *, expected_version: int | None = None,
) -> dict:
    document = get_scoped_document_or_404(db, user, document_id)
    version = versions.restore(
        db, document, version_no, author_id=user.id, expected_version=expected_version
    )
    mentions.sync(db, document, version.body)
    db.flush()
    return {"document": document, "version": version}


# ── 목록 한 쪽에 붙는 것들 (지시 22.4) ──────────────────────────────────────
#
# 목록 화면이 문서마다 물어야 하는 것이 다섯이다: 누가 썼는가 · 무슨 내용인가 · 어느
# 폴더인가 · 첨부와 댓글이 있는가. 문서마다 묻게 두면 한 화면이 문서 수의 다섯 배만큼
# 질의를 낸다. 그래서 **쪽 단위로 한 번에** 모은다 — 판·회의 화면이 사람 조각을 한 번에
# 만드는 것과 같은 관용이다(`app/work/service.py::_people`).


#: 목록에 싣는 본문 미리보기의 길이. 줄이면 무슨 문서인지 못 알아보고, 늘리면 목록이
#: 본문 읽는 자리가 된다.
EXCERPT_CHARS = 160


def _excerpt(text: str | None) -> str:
    """본문 앞머리 한 줄. 줄바꿈은 공백으로 편다 — 목록 한 줄에 들어가야 한다."""
    clean = " ".join((text or "").split())
    if len(clean) <= EXCERPT_CHARS:
        return clean
    return clean[:EXCERPT_CHARS].rstrip() + "…"


def _folder_paths(db: Session, space_ids: list[str]) -> dict[str, dict]:
    """{folder_id: {name, path}} — 「어느 폴더인가」를 조상까지 적는다.

    `1-1. CloviONE` 만 보여 주면 같은 이름의 폴더가 두 공간에 있을 때 구별이 안 된다.
    공간의 폴더는 몇 개뿐이라 그 공간 것을 통째로 읽고 파이썬에서 잇는다 — 폴더마다
    조상을 재귀 질의로 물으면 목록 한 쪽이 트리 깊이만큼 느려진다.
    """
    if not space_ids:
        return {}
    rows = list(db.execute(
        select(Folder).where(Folder.space_id.in_(tuple(sorted(set(space_ids)))))
    ).scalars().all())
    by_id = {f.id: f for f in rows}
    out: dict[str, dict] = {}
    for folder in rows:
        names = []
        seen = set()
        cursor = folder
        # 순환은 생길 수 없지만(`folders.move` 가 막는다) 방어는 둔다 — 여기서 도는
        # 무한 루프는 목록 응답 하나가 통째로 멈추는 결과다.
        while cursor is not None and cursor.id not in seen:
            seen.add(cursor.id)
            names.append(cursor.name)
            cursor = by_id.get(cursor.parent_id) if cursor.parent_id else None
        out[folder.id] = {"name": folder.name, "path": " > ".join(reversed(names))}
    return out


def list_page_extras(db: Session, user: User, documents: list[Document]) -> dict:
    """목록 한 쪽이 그리는 데 필요한 것 전부 — **질의 수는 문서 수와 무관하다.**"""
    from app.core.people import identities_for
    from app.knowledge.models import (
        DocumentAttachment,
        DocumentComment,
        DocumentRelation,
        DocumentVersion,
    )
    from app.users.models import User as UserModel

    ids = [d.id for d in documents]
    if not ids:
        return {
            "people": {}, "excerpts": {}, "counts": {}, "folders": {}, "spaces": {},
            "projects": {},
        }

    version_ids = [d.current_version_id for d in documents if d.current_version_id]
    excerpts: dict[str, str] = {}
    if version_ids:
        rows = db.execute(
            select(DocumentVersion.document_id, DocumentVersion.body_text)
            .where(DocumentVersion.id.in_(tuple(sorted(set(version_ids)))))
        ).all()
        excerpts = {doc_id: _excerpt(text) for doc_id, text in rows}

    author_ids = {d.created_by for d in documents if d.created_by}
    author_ids |= {d.archived_by for d in documents if d.archived_by}
    authors: dict[str, object] = {}
    if author_ids:
        for row in db.execute(
            select(UserModel).where(UserModel.id.in_(tuple(sorted(author_ids))))
        ).scalars().all():
            authors[row.id] = row
    people = identities_for(db, authors) if authors else {}

    def _counts(model, column) -> dict[str, int]:
        rows = db.execute(
            select(column, func.count())
            .where(column.in_(tuple(ids)))
            .group_by(column)
        ).all()
        return {key: int(n) for key, n in rows}

    counts = {
        "attachments": _counts(DocumentAttachment, DocumentAttachment.document_id),
        "comments": _counts(DocumentComment, DocumentComment.document_id),
        # 관계는 **양방향**이다. 「관련 문서 2건」이라고 적어 놓고 상세에서 3건이 나오면
        # 목록이 틀린 것처럼 보인다 — 상세(`relations.of_document`)도 양쪽을 센다.
        "relations": _counts(DocumentRelation, DocumentRelation.from_document_id),
    }
    inverse = _counts(DocumentRelation, DocumentRelation.to_document_id)
    for doc_id, n in inverse.items():
        counts["relations"][doc_id] = counts["relations"].get(doc_id, 0) + n

    space_ids = [d.space_id for d in documents]
    space_rows = list(db.execute(
        select(KnowledgeSpace).where(KnowledgeSpace.id.in_(tuple(sorted(set(space_ids)))))
    ).scalars().all())
    spaces = {row.id: row.name for row in space_rows}

    # 프로젝트 소유 공간만 프로젝트를 낸다 — 공통(조직) 공간의 문서는 `project: null`.
    from app.projects.models import Project

    project_space_ids = [
        row.id for row in space_rows
        if row.owner_kind == OWNER_PROJECT and row.owner_project_id
    ]
    projects: dict[str, dict] = {}
    if project_space_ids:
        project_by_id = {
            p.id: p for p in db.execute(
                select(Project).where(Project.id.in_(
                    tuple(sorted({r.owner_project_id for r in space_rows if r.id in project_space_ids}))
                ))
            ).scalars().all()
        }
        for row in space_rows:
            if row.id not in project_space_ids:
                continue
            project = project_by_id.get(row.owner_project_id)
            if project is not None:
                projects[row.id] = {"id": project.id, "code": project.code, "name": project.name}

    return {
        "people": people,
        "excerpts": excerpts,
        "counts": counts,
        "folders": _folder_paths(db, space_ids),
        "spaces": spaces,
        "projects": projects,
    }


def author_options(db: Session, user: User) -> list[dict]:
    """「작성자」로 좁힐 후보 — **내가 볼 수 있는 문서의 작성자만.**

    후보를 사용자 표에서 통째로 뽑으면 문서를 한 건도 안 쓴 사람이 목록에 서고, 무엇보다
    **남의 부서 문서만 쓴 사람의 이름이 이 화면에 나온다.** 후보 목록도 데이터다.

    한 쪽치가 아니라 **보이는 전체**에서 뽑는다 — 지금 쪽에 없는 사람으로 좁힐 수 있어야
    필터가 뜻을 갖는다.
    """
    from app.core.people import name_map

    _, clause = _document_scope(db, user)
    stmt = select(Document.created_by).where(
        Document.archived.is_(False), Document.created_by.is_not(None)
    ).distinct()
    if clause is not None:
        stmt = stmt.where(clause)
    ids = [str(v) for v in db.execute(stmt).scalars().all() if v]
    names = name_map(db, ids)
    rows = [
        {"value": uid, "label": (names.get(uid) or {}).get("display_name") or "이름 없음"}
        for uid in ids
    ]
    return sorted(rows, key=lambda r: r["label"])


def titles_of(db: Session, user: User, document_ids: list[str]) -> dict[str, str]:
    """{문서 id: 제목} — **볼 수 있는 것만.**

    관계와 역링크는 이미 가시성으로 좁혀서 온다(`document_detail`). 여기서 한 번 더 좁히는
    이유는 이 함수가 그 사실을 모르기 때문이다 — 다음에 다른 곳에서 부르는 날, 안 좁히면
    남의 공간 문서 제목이 그 화면으로 나간다.
    """
    ids = [i for i in dict.fromkeys(document_ids or []) if i]
    if not ids:
        return {}
    _, clause = _document_scope(db, user)
    stmt = select(Document.id, Document.title).where(Document.id.in_(tuple(ids)))
    if clause is not None:
        stmt = stmt.where(clause)
    return {doc_id: title for doc_id, title in db.execute(stmt).all()}


def workspace_summary(db: Session, user: User, *, now) -> dict:
    """작업공간 위에 서는 수 넷 (지시 22.4).

    **누르면 좁혀지는 수만 낸다.** 장식용 숫자는 화면을 채우지만 아무 행동으로도 이어지지
    않고, 이어지지 않는 수는 다음 회차에 아무도 안 본다. 그래서 각 수는 아래 목록의 조건
    하나와 **같은 판정**을 쓴다 — 「최근 수정 12」를 눌렀는데 아홉 줄이 나오면 화면이 자기
    말을 못 지킨 것이다.
    """
    from datetime import timedelta

    from app.knowledge.models import DocumentFavorite

    _, clause = _document_scope(db, user)

    def _count(*conditions) -> int:
        stmt = select(func.count()).select_from(Document).where(Document.archived.is_(False))
        if clause is not None:
            stmt = stmt.where(clause)
        for condition in conditions:
            stmt = stmt.where(condition)
        return int(db.execute(stmt).scalar_one())

    return {
        "total": _count(),
        # 「오늘」이 아니라 「최근 24시간」이다. 달력일로 자르면 자정 직후에 이 수가 0 이
        # 되는데, 그때 사람이 보고 싶은 것은 어젯밤에 고친 문서다.
        "recent": _count(Document.updated_at >= now - timedelta(hours=24)),
        "favorites": _count(
            Document.id.in_(
                select(DocumentFavorite.document_id).where(DocumentFavorite.user_id == user.id)
            )
        ),
        "drafts": _count(Document.created_by == user.id, Document.version <= 1),
    }


def recent_documents(db: Session, user: User, *, limit: int = 8) -> list[Document]:
    """내가 최근에 연 문서. **지금 볼 수 있는 것만** 낸다.

    옛 기록은 그대로 남아 있어도 그 사이 공간 권한이 바뀌었을 수 있다 — 기록을 근거로
    보여 주면 목록에서 가린 문서를 「최근 열람」이 열어 준다.
    """
    from app.knowledge.models import DocumentRecentView

    _, clause = _document_scope(db, user)
    stmt = (
        select(Document)
        .join(DocumentRecentView, DocumentRecentView.document_id == Document.id)
        .where(
            DocumentRecentView.user_id == user.id,
            Document.archived.is_(False),
        )
    )
    if clause is not None:
        stmt = stmt.where(clause)
    return list(db.execute(
        stmt.order_by(DocumentRecentView.viewed_at.desc()).limit(max(1, min(limit, 50)))
    ).scalars().all())


# ── 옛 주소를 지금 문서로 (S14 · C2) ─────────────────────────────────────────


def get_scoped_document_by_legacy_page_id(db: Session, user: User, legacy_page_id: str) -> Document:
    """옛 문서 화면의 주소(`/team-docs/<page id>`)가 가리키던 문서.

    알림 딥링크 · 감사 로그 · 사람들이 걸어 둔 북마크에 옛 page id 가 박혀 있다. 그 주소가
    죽으면 「문서가 사라졌다」로 보이므로, 다리(`documents.legacy_page_id`)로 지금 문서를
    찾아 준다.

    **못 찾는 것과 못 보는 것을 구별하지 않는다.** 둘 다 404 다 — 범위 밖에 403 을 주면
    남의 부서 문서의 존재를 옛 id 하나로 확인할 수 있게 된다.
    """
    key = (legacy_page_id or "").strip()
    if not key:
        raise NotFoundError("옛 주소에서 문서를 찾지 못했습니다.")
    document = db.execute(
        select(Document).where(Document.legacy_page_id == key)
    ).scalar_one_or_none()
    if document is None:
        raise NotFoundError("옛 주소에서 문서를 찾지 못했습니다.")
    ctx = context_for_user(db, user)
    if not is_visible(db, ctx, RESOURCE_KNOWLEDGE_DOC, document):
        raise NotFoundError("옛 주소에서 문서를 찾지 못했습니다.")
    return document


# ── 즐겨찾기 · 최근 열람 ─────────────────────────────────────────────────────
#
# 둘 다 **범위 판정을 먼저 지난다**. 목록에 안 나오는 문서를 id 하나로 담거나 열람 기록에
# 남길 수 있으면, 그 기록이 나중에 「내가 본 문서」 목록을 통해 그 문서의 존재를 알려 준다.


def toggle_favorite(db: Session, user: User, document_id: str, *, on: bool, now) -> bool:
    document = get_scoped_document_or_404(db, user, document_id)
    return doc_favorites.toggle(
        db, user_id=user.id, document_id=document.id, on=on, now=now
    )


def favorite_ids(db: Session, user: User, document_ids: list[str] | None = None) -> set[str]:
    return doc_favorites.ids_for(db, user.id, document_ids)


def record_view(db: Session, user: User, document_id: str, *, now) -> None:
    """문서 상세를 열었다는 기록. 부수효과라 실패해도 조회를 막지 않는다."""
    recent_views.record(db, user_id=user.id, document_id=document_id, now=now)


# ── 댓글 ─────────────────────────────────────────────────────────────────────
#
# 네 함수가 전부 `get_scoped_document_or_404` 한 곳을 지난다. 응답이 늘 **목록 전체**라
# 쓰기 경로의 범위 판정이 곧 조회 판정이기도 하다 — 판정 없이 삭제를 한 번 던지면 그
# 문서의 댓글 전체가 응답으로 돌아온다. 티켓 댓글에서 정확히 이 자리가 뚫려 있었다.


def list_comments(db: Session, user: User, document_id: str) -> dict:
    document = get_scoped_document_or_404(db, user, document_id)
    return doc_comments.list_comments(db, document_id=document.id, me=user)


def add_comment(db: Session, user: User, document_id: str, *, body: str, now) -> dict:
    document = get_scoped_document_or_404(db, user, document_id)
    created = doc_comments.create_comment(
        db, document_id=document.id, author=user, body=body, now=now
    )
    _notify_comment(db, document=document, author=user, now=now)
    return {
        "comment_id": created.id,
        **doc_comments.list_comments(db, document_id=document.id, me=user),
    }


def edit_comment(db: Session, user: User, comment_id: str, *, body: str, now) -> dict:
    # 범위 판정이 권한 판정보다 **먼저**다. 순서가 뒤집히면 범위 밖 댓글에 403 이 나가고,
    # 403 은 「그 id 는 존재한다」를 알려 준다.
    comment = doc_comments.get_or_404(db, comment_id)
    get_scoped_document_or_404(db, user, comment.document_id)
    doc_comments.ensure_can_edit(comment, user)
    doc_comments.update_comment(db, comment, body=body, now=now)
    return doc_comments.list_comments(db, document_id=comment.document_id, me=user)


def delete_comment(db: Session, user: User, comment_id: str, *, now) -> dict:
    # 범위 밖은 404 — 모더레이션 권한(운영자군)은 **자기 범위 안에서만** 있다.
    comment = doc_comments.get_or_404(db, comment_id)
    get_scoped_document_or_404(db, user, comment.document_id)
    doc_comments.ensure_can_delete(comment, user)
    doc_comments.soft_delete_comment(db, comment, now=now)
    return doc_comments.list_comments(db, document_id=comment.document_id, me=user)


def _notify_comment(db: Session, *, document: Document, author: User, now) -> None:
    """내 문서에 댓글이 달리면 알린다 (티켓 댓글과 같은 규약).

    받는 사람은 문서를 만든 사람이고, 자기 글에 자기가 단 댓글은 알리지 않는다 — 그러면
    배지가 늘 켜져 있다. 만든 사람을 모르는 문서(이관해 온 문서 중 작성자를 앱 계정으로
    해석하지 못한 것)는 조용히 넘어간다. 알림 하나 때문에 댓글 저장을 실패시키지 않는다.
    """
    target = document.created_by
    if not target or target == author.id:
        return
    try:
        from app.notifications.service import notify_user

        notify_user(
            db, target, type_="document_comment",
            title=f"문서에 새 댓글: {author.display_name}",
            body=(document.title or "")[:200],
            related=("document", document.id), now=now,
        )
    except Exception:  # noqa: BLE001 — 알림이 댓글 저장을 막으면 안 된다
        import logging

        logging.getLogger(__name__).exception(
            "문서 댓글 알림에 실패했습니다 (document_id=%s)", document.id
        )
