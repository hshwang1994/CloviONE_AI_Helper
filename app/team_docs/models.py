"""팀 공간 > 문서 모델 (§17, §20).

Notion "문서" DB의 로컬 미러 캐시 + 동기화 상태 + 사용자별 즐겨찾기/최근 열람. 캐시가 있어
Notion이 장애여도 마지막 정상 동기화 데이터로 목록을 계속 보여줄 수 있다(§17.4 장애 격리).
본문(블록)은 캐시하지 않고 상세 조회 때 실시간으로 읽는다(용량·신선도 균형).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import (  # noqa: F401 — NAMES_SEP/join_names/split_names 재수출
    NAMES_SEP,
    Base,
    OrgScopedMixin,
    TimestampMixin,
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


class DocumentCache(OrgScopedMixin, UUIDPrimaryKeyMixin, Base):
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
    # 작성자의 **소스 id**(0040 / X2). 이름 문자열로 권한을 판정하면 개명하면 자기 문서를
    # 못 지우고 동명이인은 남의 문서를 지운다 — `display_name` 에 유일 제약이 없기 때문이다.
    # 매핑(`user_notion_mappings`)을 거쳐 앱 사용자로 해석한다.
    author_notion_ids: Mapped[str] = mapped_column(Text, nullable=False, default="")
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
    # 포털에서 저장한 본문(0046). 읽기만 할 때는 캐시하지 않는 것이 맞았지만(모듈 docstring),
    # 편집을 열면 저장 순서가 '우리 DB 먼저 → Notion push' 여야 한다. 정본을 담을 자리가
    # 없으면 Notion 이 죽은 날 사용자가 방금 친 글이 통째로 사라진다.
    #
    # **NULL 과 빈 문자열은 다르다.** NULL 은 "아직 포털에서 고친 적이 없다"(원본이 정본)이고
    # 빈 문자열은 "본문을 비웠다" 이다. 둘을 뭉개면 동기화된 문서 전부가 빈 본문으로 보이고,
    # 그 상태에서 저장하면 원본 본문이 지워진다.
    body_markdown: Mapped[str | None] = mapped_column(Text)
    # 정본은 저장됐는데 원본에 못 밀어 넣은 상태면 그 이유. 토스트는 사라지지만 이 값은
    # 남으므로 다시 열어도 화면이 "저장됨, 원본 반영 실패" 를 말할 수 있다.
    body_sync_error: Mapped[str | None] = mapped_column(Text)
    body_synced_at: Mapped[datetime | None] = mapped_column(DateTime)


class DocumentSyncState(Base):
    __tablename__ = "document_sync_state"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # 항상 SYNC_STATE_ID
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=SYNC_IDLE)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime)
    doc_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 마지막 동기화가 **실제로 지운** 건수(드리프트 지표). 바닥에 걸려 삭제를 거부했으면 0 이고
    # status 가 SYNC_ERROR + error 에 이유가 남는다 — core/sync_prune.py 참조.
    pruned_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )


class DocumentFavorite(UUIDPrimaryKeyMixin, Base):
    """사용자별 문서 즐겨찾기.

    **notion_page_id 와 document_id 를 둘 다 든다(0025).** 유일 제약과 조회는 계속
    notion_page_id 로 한다 — 소스가 Notion 인 동안 그게 안정적인 키이고, 미러가 아직
    그 페이지를 못 봤을 때도 즐겨찾기는 걸려야 하기 때문이다. document_id 는 미러 행이
    있을 때 채워지는 **보조 참조**로, 소스가 자체 DB 로 바뀔 때 이어질 다리다.
    """

    __tablename__ = "document_favorites"

    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    notion_page_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # 미러에 아직 없는 페이지면 NULL. FK 를 걸지 않는 이유는 0025 docstring 참조.
    document_id: Mapped[str | None] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "notion_page_id", name="uq_doc_favorite"),
    )


class DocumentComment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """문서 댓글 (사용자 지적 #9).

    구조는 티켓 댓글(`app/tickets/models.py::TicketComment`)을 그대로 옮겼다: 툼스톤
    soft-delete(`deleted_at`), 작성자 본인 또는 운영자군 권한, 쓰기마다 목록 전체 응답.
    **다르게 한 것은 부모를 가리키는 방법 하나뿐이고, 그건 일부러 다르다.**

    ## 왜 `document_cache.id` 에 CASCADE 를 걸지 않았는가

    티켓 댓글은 `ticket_cache.id` 에 `ondelete="CASCADE"` 로 걸려 있었고, 그 선택이
    사용자 데이터를 지웠다: 티켓이 소스 응답에서 **한 회차** 빠지면 prune 이 캐시 행을
    지우고 CASCADE 가 댓글과 첨부를 함께 지웠다(재현 기록:
    `tests/regression/test_comment_survives_resync.py`). 그래서 0043 이 소프트 프룬
    (`ticket_cache.notion_missing_at`)을 도입해 **지우는 대신 표시**하게 고쳤다.

    문서 동기화도 같은 prune 을 한다(`app/team_docs/sync.py::_prune`). 그런데 문서 쪽에는
    그 표시 컬럼이 **없어서 지금도 진짜로 지운다.** 즉 여기에 CASCADE 를 걸면 이미 한 번
    값을 치르고 배운 함정을 그대로 다시 파는 것이 된다. 반대로 RESTRICT 로 막는 것도 안
    된다 - 캐시 행 DELETE 가 실패하고 sync 는 예외를 통째로 삼키므로 **문서 미러 전체가
    조용히 멈춘다**(0028 이 CASCADE 를 고른 이유가 정확히 그 걱정이었고, 그 걱정 자체는
    지금도 맞다).

    ## 그래서 조회 키는 `notion_page_id`, FK 는 `SET NULL` 다리다 (0025 관용)

    같은 모듈의 `DocumentFavorite` / `DocumentRecentView` 가 이미 이 모양이다: 유일성과
    조회는 `notion_page_id` 가 담당하고 `document_id` 는 미러 행이 있을 때 채워지는 보조
    참조다. 그 판단이 댓글에도 그대로 맞는다.

      * 캐시 행이 prune 으로 사라져도 댓글은 **남는다**(그 순간에는 문서 자체가 포탈에서
        안 보이므로 화면에서도 함께 사라진다 - 조회는 `get_doc_in_scope` 를 지난다).
      * FK 가 `ON DELETE SET NULL` 이라 그 DELETE 는 **실패하지 않는다**. 동기화가 멈추지
        않는다.
      * 문서가 다음 회차에 돌아오면 `_upsert` 가 **새 UUID 로** 캐시 행을 만드는데, 댓글은
        page id 로 붙어 있어 그대로 다시 보인다. 티켓에서 '결정적 UUID' 로도 못 고쳤던
        상황이 여기서는 애초에 생기지 않는다.

    티켓이 page id 를 못 쓴 이유(자체 생성 티켓은 page id 가 아예 없다)는 문서에 없다.
    `document_cache.notion_page_id` 는 NOT NULL + UNIQUE 이고 문서 API 는 처음부터 page id
    로만 말한다. 소스가 자체 DB 로 바뀌는 날 이어 붙일 다리가 `document_id` 이고, 그때
    조회 키를 옮기는 것은 이 표 하나를 고치는 일이다.

    ## 문서 쪽에도 소프트 프룬이 필요한가

    필요하다. 다만 그건 **이 표의 문제가 아니다** - `classification_manual` 로 표시된 수동
    분류도 Notion 에 대응 필드가 없어 prune 한 번에 영구 소실이고(`sync._prune` 이 이미 그
    사실을 적어 놨다), 그건 댓글을 붙이기 전부터 있던 결함이다. 댓글이 그 결함에 인질로
    잡히지 않게 만드는 것이 먼저이고, 문서 소프트 프룬은 그 자체로 별도 작업이다.
    """

    __tablename__ = "document_comments"

    # 조회 키. FK 가 아니다(위 docstring) - 미러 행이 한 회차 사라져도 댓글은 남아야 한다.
    notion_page_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # 소스 전환을 위한 다리. 미러 행이 없거나 prune 으로 사라지면 NULL 이 정상 상태다.
    document_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("document_cache.id", ondelete="SET NULL"), index=True
    )
    author_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)


class DocumentRecentView(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "document_recent_views"

    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    notion_page_id: Mapped[str] = mapped_column(String(64), nullable=False)
    document_id: Mapped[str | None] = mapped_column(String(36), index=True)
    viewed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "notion_page_id", name="uq_doc_recent"),
    )
