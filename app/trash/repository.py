"""휴지통 데이터 접근 (쿼리 전용)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.trash.models import TrashItem


def list_items(db: Session) -> list[TrashItem]:
    """휴지통 전체를 최근 삭제 순으로. 팀 전원이 본다(동작은 권한으로 통제)."""
    return list(
        db.execute(select(TrashItem).order_by(TrashItem.deleted_at.desc())).scalars().all()
    )


def get(db: Session, trash_id: str) -> TrashItem | None:
    return db.execute(select(TrashItem).where(TrashItem.id == trash_id)).scalar_one_or_none()


def get_by_page(db: Session, item_type: str, notion_page_id: str) -> TrashItem | None:
    return db.execute(
        select(TrashItem).where(TrashItem.item_type == item_type, TrashItem.notion_page_id == notion_page_id)
    ).scalar_one_or_none()


def trashed_page_ids(db: Session, item_type: str) -> set[str]:
    """해당 종류의 휴지통에 들어간 노션 page id 집합 — 목록에서 걸러내는 데 쓴다."""
    rows = db.execute(
        select(TrashItem.notion_page_id).where(TrashItem.item_type == item_type)
    ).scalars().all()
    return set(rows)
