"""관측성 모델 — 사용 이벤트 + 미러 동기화 상태 (0026, PLAN Phase 4).

두 표의 성격이 다르다:
  * `UsageEvent` 는 **추가만 하는 로그**다. 저빈도 지점에서만 쓴다(모듈 `service.py` 의
    금지 규칙 참조).
  * `SyncStatus` 는 컴포넌트당 **한 행짜리 현재 상태**다. 워커가 upsert 하고 화면이 읽는다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, OrgScopedMixin, UUIDPrimaryKeyMixin, utcnow

# 상태 어휘는 document_sync_state / ticket_sync_state 와 **같은 말**을 쓴다 —
# 운영자가 화면 세 개에서 같은 단어를 봐야 한다.
SYNC_IDLE = "idle"
SYNC_RUNNING = "running"
SYNC_OK = "ok"
SYNC_ERROR = "error"

# 컴포넌트 이름. 새 미러가 생기면 여기에 이름을 먼저 적는다.
COMPONENT_TICKETS = "tickets"
COMPONENT_DOCUMENTS = "documents"


class UsageEvent(OrgScopedMixin, UUIDPrimaryKeyMixin, Base):
    """사람이 의도해서 한 드문 행동 하나."""

    __tablename__ = "usage_events"

    # 계정이 보관·삭제돼도 집계는 남아야 하므로 FK 를 걸지 않는다(감사 로그와 같은 판단).
    user_id: Mapped[str | None] = mapped_column(String(36), index=True)
    event: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    object_type: Mapped[str | None] = mapped_column(String(48))
    object_id: Mapped[str | None] = mapped_column(String(64))
    # **개인정보·비밀은 넣지 않는다.** 기록 함수가 값을 검사하지 않으므로 부르는 쪽 책임이다.
    meta_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, index=True
    )


class SyncStatus(Base):
    """미러 동기화 컴포넌트 하나의 현재 상태(화면에 그대로 보여줄 공통 모양)."""

    __tablename__ = "sync_status"

    component: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=SYNC_IDLE)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 소스가 페이지 상한에서 잘렸는가. 잘린 채로 prune 을 돌리면 나머지가 전부 삭제된다
    # (계획 C4) — 그 사실을 화면에도 드러낸다.
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[str | None] = mapped_column(Text)
    detail_json: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
