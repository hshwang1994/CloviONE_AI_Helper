"""문서 캐시 데이터 접근 (읽기 전용 쿼리 — 규칙은 service)."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.team_docs.models import (
    NAMES_SEP,
    DocumentCache,
    DocumentFavorite,
    DocumentRecentView,
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
    favorite_page_ids: set[str] | None,
    favorites_only: bool,
    sort: str,
    offset: int,
    limit: int,
) -> tuple[list[DocumentCache], int]:
    stmt = select(DocumentCache).where(DocumentCache.archived.is_(False))
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
    if favorites_only:
        ids = favorite_page_ids or set()
        # 빈 집합이면 아무것도 매치 안 되게(불가능 조건) 만든다.
        stmt = stmt.where(DocumentCache.notion_page_id.in_(ids or {"__none__"}))

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    if sort == "title":
        order = [DocumentCache.title.asc()]
    else:  # recent = 최근 수정순(원본 last_edited 문자열 ISO라 정렬 가능)
        order = [DocumentCache.last_edited.desc().nulls_last(), DocumentCache.title.asc()]
    rows = db.execute(stmt.order_by(*order).offset(offset).limit(limit)).scalars().all()
    return list(rows), int(total)


def all_active(db: Session) -> list[DocumentCache]:
    return list(
        db.execute(
            select(DocumentCache).where(DocumentCache.archived.is_(False))
        ).scalars().all()
    )


def favorite_page_ids(db: Session, user_id: str) -> set[str]:
    rows = db.execute(
        select(DocumentFavorite.notion_page_id).where(DocumentFavorite.user_id == user_id)
    ).scalars().all()
    return set(rows)


def find_favorite(db: Session, user_id: str, page_id: str) -> DocumentFavorite | None:
    return db.execute(
        select(DocumentFavorite).where(
            DocumentFavorite.user_id == user_id,
            DocumentFavorite.notion_page_id == page_id,
        )
    ).scalar_one_or_none()


def find_recent(db: Session, user_id: str, page_id: str) -> DocumentRecentView | None:
    return db.execute(
        select(DocumentRecentView).where(
            DocumentRecentView.user_id == user_id,
            DocumentRecentView.notion_page_id == page_id,
        )
    ).scalar_one_or_none()


def recent_views(db: Session, user_id: str, *, limit: int) -> list[DocumentRecentView]:
    return list(
        db.execute(
            select(DocumentRecentView)
            .where(DocumentRecentView.user_id == user_id)
            .order_by(DocumentRecentView.viewed_at.desc())
            .limit(limit)
        ).scalars().all()
    )
