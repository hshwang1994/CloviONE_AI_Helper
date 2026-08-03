"""팀 공간 > 문서 모델 (§17, §20).

Notion "문서" DB의 로컬 미러 캐시 + 동기화 상태 + 사용자별 즐겨찾기/최근 열람. 캐시가 있어
Notion이 장애여도 마지막 정상 동기화 데이터로 목록을 계속 보여줄 수 있다(§17.4 장애 격리).
본문(블록)은 캐시하지 않고 상세 조회 때 실시간으로 읽는다(용량·신선도 균형).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import (  # noqa: F401 — NAMES_SEP/join_names/split_names 재수출
    NAMES_SEP,
    Base,
    UUIDPrimaryKeyMixin,
    join_names,
    split_names,
    utcnow,
)

SYNC_IDLE = "idle"
SYNC_RUNNING = "running"
SYNC_OK = "ok"
SYNC_ERROR = "error"

# 다중값 relation 이름들을 한 컬럼에 담는 구분자(sentinel-wrapped Unit Separator)와 그 헬퍼는
# ticket_cache 도 똑같이 써야 해서 정의를 app/core/models_base.py 로 올렸다. 여기서는 그대로
# 재수출한다 — 기존 import 경로(app.team_docs.models.join_names 등)는 하나도 바뀌지 않는다.

# DocumentSyncState 는 단일 행이다 — 이 고정 id로 upsert 한다.
SYNC_STATE_ID = "documents"


class DocumentCache(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "document_cache"

    notion_page_id: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    url: Mapped[str | None] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # relation 이름들은 콤마로 합쳐 저장(표시·검색용). 필터 매칭은 콤마 분리로 처리.
    type_names: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category_names: Mapped[str] = mapped_column(Text, nullable=False, default="")
    project_names: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str | None] = mapped_column(String(64), index=True)
    priority: Mapped[str | None] = mapped_column(String(64))
    # 신규 택소노미(§17 개편) — 동기화 때 classify.py로 자동 계산. 사용자가 수동으로 고치면
    # classification_manual=True 가 되어 이후 sync가 덮어쓰지 않는다. type_names/category_names는
    # 원본(분류 입력)으로 남겨 두고, 화면은 아래 값을 보여준다. tech_tags는 NAMES_SEP-joined.
    document_type: Mapped[str | None] = mapped_column(String(32), index=True)
    work_field: Mapped[str | None] = mapped_column(String(32), index=True)
    tech_tags: Mapped[str] = mapped_column(Text, nullable=False, default="")
    classification_manual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    author_names: Mapped[str] = mapped_column(Text, nullable=False, default="")
    owner: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    doc_date: Mapped[str | None] = mapped_column(String(40))
    orig_date: Mapped[str | None] = mapped_column(String(40))
    created_time: Mapped[str | None] = mapped_column(String(40))
    last_edited: Mapped[str | None] = mapped_column(String(40))
    original_url: Mapped[str | None] = mapped_column(String(1000))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    memo: Mapped[str] = mapped_column(Text, nullable=False, default="")
    has_files: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notion_favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class DocumentSyncState(Base):
    __tablename__ = "document_sync_state"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # 항상 SYNC_STATE_ID
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=SYNC_IDLE)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime)
    doc_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )


class DocumentFavorite(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "document_favorites"

    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    notion_page_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "notion_page_id", name="uq_doc_favorite"),
    )


class DocumentRecentView(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "document_recent_views"

    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    notion_page_id: Mapped[str] = mapped_column(String(64), nullable=False)
    viewed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "notion_page_id", name="uq_doc_recent"),
    )
