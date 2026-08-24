"""문서 캐시 데이터 접근 (읽기 전용 쿼리 — 규칙은 service)."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.team_docs.models import (
    NAMES_SEP,
    DocumentCache,
)


def _token_filter(column, value: str):
    """콤마 substring이 아니라 '정확한 토큰'으로 매칭한다. 저장은 sentinel-wrapped(양끝에도
    NAMES_SEP)이므로 NAMES_SEP+값+NAMES_SEP 를 contains 하면 토큰 경계가 정확히 잡힌다.
    autoescape=True 로 값의 %/_ (LIKE 메타문자)를 이스케이프한다."""
    return column.contains(NAMES_SEP + value + NAMES_SEP, autoescape=True)


def get_by_page_id(db: Session, page_id: str) -> DocumentCache | None:
    return db.execute(
        select(DocumentCache).where(DocumentCache.notion_page_id == page_id)
    ).scalar_one_or_none()


def list_documents(
    db: Session,
    *,
    search: str | None,
    doc_type_f: str | None,
    work_field_f: str | None,
    project_f: str | None,
    tech_f: str | None,
    sort: str,
    offset: int,
    limit: int,
    exclude_page_ids: set[str] | None = None,
) -> tuple[list[DocumentCache], int]:
    stmt = select(DocumentCache).where(DocumentCache.archived.is_(False))
    if exclude_page_ids:
        stmt = stmt.where(DocumentCache.notion_page_id.notin_(exclude_page_ids))
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                DocumentCache.title.ilike(like),
                DocumentCache.memo.ilike(like),
                DocumentCache.owner.ilike(like),
                DocumentCache.author_names.ilike(like),
            )
        )
    if doc_type_f:
        stmt = stmt.where(DocumentCache.document_type == doc_type_f)
    if work_field_f:
        stmt = stmt.where(DocumentCache.work_field == work_field_f)
    if project_f:
        stmt = stmt.where(_token_filter(DocumentCache.project_names, project_f))
    if tech_f:
        stmt = stmt.where(_token_filter(DocumentCache.tech_tags, tech_f))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    if sort == "title":
        order = [DocumentCache.title.asc()]
    else:  # recent = 최근 수정순. `last_edited` 는 `timestamp` 다 (S7 · P-14a)
        order = [DocumentCache.last_edited.desc().nulls_last(), DocumentCache.title.asc()]
    rows = db.execute(stmt.order_by(*order).offset(offset).limit(limit)).scalars().all()
    return list(rows), int(total)


def all_active(db: Session) -> list[DocumentCache]:
    return list(
        db.execute(
            select(DocumentCache).where(DocumentCache.archived.is_(False))
        ).scalars().all()
    )


# 즐겨찾기·최근 열람은 여기 없다 (S14 · C2). 두 축은 정본 문서(`documents`)에 붙었고
# `app/knowledge/favorites.py` · `app/knowledge/recent_views.py` 가 답한다.


