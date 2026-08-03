"""티켓 로컬 미러 캐시 모델 (§7.1.A, NEXT_SESSION_PLAN §A).

문서(team_docs)와 같은 구조다: 워커가 주기적으로 Notion "작업" DB를 통째로 읽어 여기에
미러링하고, 화면은 로컬만 읽는다. 그래서 (1) 목록이 Notion 왕복 없이 즉시 뜨고 (2) Notion이
죽어도 마지막 정상 동기화 데이터로 계속 보인다(§17.4 장애 격리).

문서 캐시와 다른 점 두 가지:
  * `ticket_cache` 는 '얇은 읽기 캐시'가 아니라 **나중에 자체 소스가 될 수 있는 완전한 표**다
    (§7.1.A). 그래서 자체 UUID PK 를 갖고 notion_page_id 는 nullable 보조 외부키이며,
    본문 정본(body_markdown)과 source 컬럼을 처음부터 갖는다.
  * 다중값(프로젝트 id/이름, 담당자 Notion id)은 문서 캐시와 **같은** sentinel-wrapped
    구분자 규약(app.core.models_base.NAMES_SEP)으로 저장한다. 새 규약을 만들지 않는다.

담당자는 원본 Notion user id 로 저장하고 앱 user 로의 해석은 읽는 시점에 한다 — 매핑이
바뀌어도 캐시를 다시 채울 필요가 없고, 응답에는 raw Notion id 를 절대 싣지 않는다(§12.3).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import (  # noqa: F401 — join_names/split_names 재수출(동일 규약)
    NAMES_SEP,
    Base,
    OrgScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    join_names,
    split_names,
    utcnow,
)

# 동기화 상태값 — DocumentSyncState 와 같은 어휘를 쓴다(운영자가 두 화면에서 같은 말을 본다).
SYNC_IDLE = "idle"
SYNC_RUNNING = "running"
SYNC_OK = "ok"
SYNC_ERROR = "error"

# 아래 두 테이블은 각각 단일 행이다 — 이 고정 id로 upsert 한다(문서 sync 싱글턴과 같은 관례).
SYNC_STATE_ID = "tickets"
META_CACHE_ID = "tickets"

# source 컬럼 값. 지금은 항상 'notion'. 'native'(자체 DB가 정본)는 문만 열어 둔 상태다.
SOURCE_NOTION = "notion"
SOURCE_NATIVE = "native"


class TicketCache(OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin, Base):
    """Notion "작업" DB 한 행의 로컬 미러(장차 자체 티켓 표)."""

    __tablename__ = "ticket_cache"

    # nullable 인 이유: source='native' 로 만든 티켓은 Notion 페이지가 없다. unique 는 유지 —
    # 같은 Notion 페이지가 두 행이 되면 목록에 중복이 뜬다(SQLite는 NULL을 서로 다르게 본다).
    notion_page_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    # 담당자의 부서로 유도할 예정인 스코프 컬럼. 지금은 항상 NULL이고 읽는 코드가 없다(문만 연다).
    scope_dept_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("departments.id"), nullable=True, index=True
    )

    # Notion 'ID' 속성(auto_increment). 화면이 "GIT-" + 번호로 보여주므로 반드시 미러링한다.
    notion_ticket_number: Mapped[int | None] = mapped_column(Integer)
    url: Mapped[str | None] = mapped_column(String(500))

    title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    status: Mapped[str | None] = mapped_column(String(64), index=True)
    priority: Mapped[str | None] = mapped_column(String(64))
    difficulty: Mapped[str | None] = mapped_column(String(64))
    est_wd: Mapped[float | None] = mapped_column(Float)
    act_wd: Mapped[float | None] = mapped_column(Float)
    # ISO 'YYYY-MM-DD' 문자열 그대로 저장한다(원본이 문자열이고 문자열 비교로 정렬·범위가 맞다).
    due_date: Mapped[str | None] = mapped_column(String(40), index=True)

    # 아래 셋은 NAMES_SEP 로 감싼 다중값. project_ids 는 원본 relation id, project_names 는
    # 동기화 때 해석해 둔 표시용 이름(읽을 때 Notion을 다시 안 부르려고 함께 저장한다).
    project_ids: Mapped[str] = mapped_column(Text, nullable=False, default="")
    project_names: Mapped[str] = mapped_column(Text, nullable=False, default="")
    assignee_notion_ids: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # 본문 정본(마크다운). 지금은 상세 조회 때 Notion 블록을 실시간으로 읽으므로 대개 NULL이다.
    body_markdown: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default=SOURCE_NOTION)

    notion_created_time: Mapped[str | None] = mapped_column(String(40))
    notion_last_edited: Mapped[str | None] = mapped_column(String(40))
    synced_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class TicketSyncState(Base):
    """동기화 싱글턴. DocumentSyncState 와 같은 모양 + truncated(상한 도달) 신호."""

    __tablename__ = "ticket_sync_state"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # 항상 SYNC_STATE_ID
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=SYNC_IDLE)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime)
    # DocumentSyncState.doc_count 와 같은 자리(티켓이라 이름만 다르다).
    ticket_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 상한에 걸려 일부만 받아온 상태. True 면 prune(삭제 감지)을 건너뛰었다는 뜻이라 운영자가
    # 상한을 올려야 한다는 신호가 된다.
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )


class TicketMetaCache(Base):
    """편집·생성 폼용 스키마 파생값(상태/우선순위/난이도 옵션 + 프로젝트 목록) 싱글턴.

    티켓만 캐시하고 이건 그대로 두면 폼 드롭다운(/meta, /projects)이 100% 실시간이라
    '새 티켓' 화면이 계속 느리다 — 티켓 목록보다 오히려 Notion 왕복이 많다(스키마 + relation 조회).
    """

    __tablename__ = "ticket_meta_cache"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # 항상 META_CACHE_ID
    statuses: Mapped[str] = mapped_column(Text, nullable=False, default="")
    priorities: Mapped[str] = mapped_column(Text, nullable=False, default="")
    difficulties: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # [{"id": ..., "name": ...}] JSON. id/이름 쌍이라 NAMES_SEP 한 줄로는 못 담는다.
    projects_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    synced_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
