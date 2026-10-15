"""문서 분류 — 조직이 스스로 만드는 어휘.

## 이름이 둘이다 — 그리고 그것이 의도다

화면에 보이는 낱말은 **분류**다(문서 개편 2번). 모듈·표·필드 이름은 `category` 로 남는다 —
주소(`?category_id=`)와 서버 계약과 저장된 행이 그 이름을 이미 쓰고 있어서, 축 이름을
통일하자고 스키마까지 건드리면 이번 변경의 범위가 열 배가 된다.

🔴 그래서 **이 파일의 오류 문장은 화면 문구다.** `lib/api.js` 가 봉투의 `error.message` 를
그대로 Error 로 만들고 화면이 그것을 띄운다 — 이름을 비우거나 중복 이름을 넣는 가장 흔한
실패 경로가 전부 여기다. 여기에 「카테고리」를 적으면 「분류」 탭에서 그 낱말이 튀어나온다.


## 태그와 무엇이 다른가

태그는 문서 하나에 여럿이 붙는 자유 분류이고, 카테고리는 **문서 하나에 하나**인 큰 갈래다.
어느 조직은 「회의록·기획·개발」로 쓰고 어느 조직은 「고객사별」로 쓴다 — 어휘를 제품이
정하지 않고 관리 화면이 만들게 두는 이유다(0026 이 이관 `doc_type` 값에서 첫 어휘를
시드했다).

정규화 규칙은 태그와 **한 벌**이다(`app.knowledge.tags.slugify`). 규칙을 두 벌 두면
한쪽만 고치는 날 「회의록」과 「회의록 」이 카테고리에서만 서로 다른 것이 된다.
"""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.knowledge.models import Document, DocumentCategory
from app.knowledge.tags import slugify

__all__ = [
    "CATEGORY_NAME_MAX",
    "list_for_org", "usage_counts", "get_or_404",
    "create", "rename", "remove", "of_documents",
]

#: 카테고리 이름의 상한. 컬럼과 같은 값이다 — 태그의 `TAG_NAME_MAX` 와 같은 근거.
CATEGORY_NAME_MAX = 80

#: 새 카테고리가 받는 순서 간격. 사이에 끼워 넣을 자리를 남긴다(폴더 `sort_order` 와 같은 발상).
_SORT_STEP = 1024


def _org_clause(org_id: str | None):
    return (
        DocumentCategory.org_id.is_(None)
        if org_id is None
        else DocumentCategory.org_id == org_id
    )


def _clean_name(name: str) -> tuple[str, str]:
    clean = (name or "").strip()
    if not clean:
        raise ValidationAppError("분류 이름을 입력해 주세요.")
    if len(clean) > CATEGORY_NAME_MAX:
        raise ValidationAppError(f"분류 이름은 {CATEGORY_NAME_MAX}자 이하여야 합니다.")
    slug = slugify(clean)
    if not slug:
        raise ValidationAppError("분류 이름을 입력해 주세요.")
    return clean, slug


def list_for_org(db: Session, org_id: str | None) -> list[DocumentCategory]:
    """사람이 정한 순서(`sort_order`)로, 같은 순서 안에서는 slug 로 — 전순서다."""
    return list(
        db.execute(
            select(DocumentCategory)
            .where(_org_clause(org_id))
            .order_by(DocumentCategory.sort_order, DocumentCategory.slug)
        ).scalars().all()
    )


def usage_counts(db: Session, category_ids: list[str], *, document_ids=None) -> dict[str, int]:
    """{category_id: 그 분류의 문서 수}.

    `document_ids` 를 주면 **그 집합 안에서만** 센다 — 태그의 `usage_counts` 와 같은 이유다:
    수 하나도 남의 공간에 무엇이 있는지 말해 준다.
    """
    if not category_ids:
        return {}
    stmt = (
        select(Document.category_id, func.count())
        .where(Document.category_id.in_(tuple(category_ids)))
        .group_by(Document.category_id)
    )
    if document_ids is not None:
        if not document_ids:
            return {}
        stmt = stmt.where(Document.id.in_(tuple(document_ids)))
    return {category_id: int(n) for category_id, n in db.execute(stmt).all()}


def get_or_404(db: Session, org_id: str | None, category_id: str) -> DocumentCategory:
    """이 조직의 카테고리 하나. 다른 조직 것이면 **없는 것**이다(404) — 태그와 같은 계약."""
    category = db.get(DocumentCategory, category_id)
    if category is None or category.org_id != org_id:
        raise NotFoundError("분류를 찾지 못했습니다.")
    return category


def create(db: Session, org_id: str | None, name: str) -> DocumentCategory:
    """새 카테고리. 같은 뜻이 이미 있으면 거절한다(관리 화면의 「추가」에는 그것이 정확한 답이다)."""
    clean, slug = _clean_name(name)
    found = db.execute(
        select(DocumentCategory).where(DocumentCategory.slug == slug, _org_clause(org_id))
    ).scalars().first()
    if found is not None:
        raise ConflictError(f"같은 이름의 분류가 이미 있습니다: {found.name}")
    top = db.execute(
        select(func.max(DocumentCategory.sort_order)).where(_org_clause(org_id))
    ).scalar()
    category = DocumentCategory(
        org_id=org_id, name=clean, slug=slug, sort_order=int(top or 0) + _SORT_STEP
    )
    db.add(category)
    db.flush()
    return category


def rename(db: Session, category: DocumentCategory, name: str) -> DocumentCategory:
    """이름과 slug 를 함께 고친다. 합치기(merge)는 안 한다 — 태그의 `rename` 과 같은 이유."""
    clean, slug = _clean_name(name)
    if slug != category.slug:
        clash = db.execute(
            select(DocumentCategory).where(
                DocumentCategory.slug == slug,
                _org_clause(category.org_id),
                DocumentCategory.id != category.id,
            )
        ).scalars().first()
        if clash is not None:
            raise ConflictError(f"같은 이름의 분류가 이미 있습니다: {clash.name}")
    renamed = clean != category.name
    category.name = clean
    category.slug = slug
    db.flush()
    if renamed:
        # 분류 이름은 그 문서들의 AI 첫 조각 자리 줄에 있다(D-568) — 다시 색인한다(P-138).
        from app.knowledge import versions

        versions.mark_stale_many(db, db.execute(
            select(Document.id).where(Document.category_id == category.id)
        ).scalars().all())
    return category


def remove(db: Session, category: DocumentCategory) -> int:
    """카테고리를 지운다. **문서는 안 지운다** — 미분류로 돌아온다.

    FK 는 `ON DELETE SET NULL` 이라 DB 가 알아서 풀지만, 몇 건이 미분류가 되는지는
    지우기 **전에** 세어서 돌려준다 — 화면이 「문서 3건이 미분류가 됩니다」라고 말할 수
    있어야 한다. UPDATE 를 직접 치는 이유는 수를 세는 김에 같은 트랜잭션에서 끊어
    ORM 캐시와 DB 가 어긋나지 않게 하기 위해서다.
    """
    from app.knowledge import versions

    document_ids = list(db.execute(select(Document.id).where(Document.category_id == category.id)).scalars().all())
    used = len(document_ids)
    db.execute(
        update(Document)
        .where(Document.category_id == category.id)
        .values(category_id=None)
        .execution_options(synchronize_session="fetch")
    )
    db.delete(category)
    db.flush()
    versions.mark_stale_many(db, document_ids)  # 미분류가 된 문서의 AI 첫 조각 자리 줄을 고친다(P-138)
    return int(used)


def of_documents(db: Session, document_ids: list[str]) -> dict[str, DocumentCategory]:
    """여러 문서의 카테고리를 한 질의로 — 목록이 문서 수만큼 묻지 않게 한다
    (`tags.of_documents` 와 같은 규칙)."""
    if not document_ids:
        return {}
    rows = db.execute(
        select(Document.id, DocumentCategory)
        .join(DocumentCategory, DocumentCategory.id == Document.category_id)
        .where(Document.id.in_(tuple(document_ids)))
    ).all()
    return {document_id: category for document_id, category in rows}
