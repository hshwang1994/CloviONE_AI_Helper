"""휴지통 모델 — 삭제 대기 중인 티켓/문서 한 건.

'삭제'는 노션 페이지를 바로 지우지 않고 이 행으로 옮긴다(원본은 그대로). 보관기간이 지나면
백그라운드 작업이 노션 페이지를 보관처리(archive)하고 이 행을 지운다. 복원은 이 행만 지우면
원래 목록으로 되돌아온다(노션을 손대지 않았으므로). 티켓은 로컬 DB가 없어 notion_page_id 로
목록에서 걸러내고, 문서는 캐시(document_cache)에서 같은 방식으로 걸러낸다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, UUIDPrimaryKeyMixin

TRASH_TICKET = "ticket"
TRASH_DOCUMENT = "document"
TRASH_TYPES = frozenset({TRASH_TICKET, TRASH_DOCUMENT})


class TrashItem(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "trash_items"

    item_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    notion_page_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(400), nullable=False, default="")
    url: Mapped[str | None] = mapped_column(String(1000))
    deleted_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    deleted_by_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    deleted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("item_type", "notion_page_id", name="uq_trash_item"),
    )
