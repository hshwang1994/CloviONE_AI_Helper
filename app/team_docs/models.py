"""팀 공간 > 문서 모델 (§17, §20).

Notion "문서" DB의 로컬 미러 캐시 + 동기화 상태 + 사용자별 즐겨찾기/최근 열람. 캐시가 있어
Notion이 장애여도 마지막 정상 동기화 데이터로 목록을 계속 보여줄 수 있다(§17.4 장애 격리).
본문(블록)은 캐시하지 않고 상세 조회 때 실시간으로 읽는다(용량·신선도 균형).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, UUIDPrimaryKeyMixin, utcnow

SYNC_IDLE = "idle"
SYNC_RUNNING = "running"
SYNC_OK = "ok"
SYNC_ERROR = "error"

# 다중값 relation 이름들을 한 컬럼에 담는 구분자. Unit Separator(0x1f)는 Notion 제목에
# 사실상 안 나타나므로 (1) 이름에 콤마가 들어가도 안전하고 (2) 필터를 '정확한 토큰'으로
# 매칭할 수 있다(콤마 substring 매칭의 오탐 '보고'⊂'보고서' 방지). 저장은 양끝에도 구분자를
# 붙여(sentinel-wrapped) contains 매칭이 토큰 경계를 정확히 잡게 한다.
NAMES_SEP = "\x1f"


def join_names(names) -> str:
    vals = [n.strip() for n in (names or []) if n and str(n).strip()]
    if not vals:
        return ""
    return NAMES_SEP + NAMES_SEP.join(vals) + NAMES_SEP


def split_names(joined: str) -> list[str]:
    return [p for p in (joined or "").split(NAMES_SEP) if p.strip()]

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
