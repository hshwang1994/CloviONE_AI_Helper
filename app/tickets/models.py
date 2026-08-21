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

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import (  # noqa: F401 — join_names/split_names 재수출(동일 규약)
    NAMES_SEP,
    Base,
    JsonText,
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

# ── 티켓 ↔ 프로젝트 연결 상태 (0060) ─────────────────────────────────────────
# 티켓 하나에는 프로젝트가 **정확히 하나** 있어야 한다. 외부 소스(Notion relation)는 0개나
# 2개 이상을 줄 수 있으므로, 해석 결과를 이 어휘로 남기고 `ok` 가 아니면 fail-closed 한다.
# 임의로 하나를 고르지 않는 이유는 `TicketCache.project_link` 주석 참조.
PROJECT_LINK_OK = "ok"                  # 정확히 1개, Portal 프로젝트로 해석됨
PROJECT_LINK_MISSING = "missing"        # relation 0개 — 정합성 오류
PROJECT_LINK_AMBIGUOUS = "ambiguous"    # relation 2개 이상 — 정합성 오류
PROJECT_LINK_UNRESOLVED = "unresolved"  # 1개인데 Portal 에 짝이 없음(동기화 전이거나 삭제됨)

PROJECT_LINK_STATES: tuple[str, ...] = (
    PROJECT_LINK_OK, PROJECT_LINK_MISSING, PROJECT_LINK_AMBIGUOUS, PROJECT_LINK_UNRESOLVED,
)
# ACL 계산에 쓸 수 있는 상태. 이 집합 밖은 소속을 모르는 것이고, 모르면 닫는다.
PROJECT_LINK_USABLE: frozenset[str] = frozenset({PROJECT_LINK_OK})


class TicketCache(OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin, Base):
    """Notion "작업" DB 한 행의 로컬 미러(장차 자체 티켓 표)."""

    __tablename__ = "ticket_cache"

    # nullable 인 이유: source='native' 로 만든 티켓은 Notion 페이지가 없다. unique 는 유지 —
    # 같은 Notion 페이지가 두 행이 되면 목록에 중복이 뜬다(SQLite는 NULL을 서로 다르게 본다).
    notion_page_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    # "이번 회차 Notion 응답에서 안 보였다" (0043). **지우지 않고 표시만 한다.**
    #
    # 티켓 한 건이 응답에서 깜빡이면(페이지네이션·필터·일시 권한) 예전에는 그 행을 지웠고,
    # 붙어 있던 댓글·첨부가 CASCADE 로 함께 사라졌다 — 그 셋은 **Notion 에 없어서 재동기화로
    # 돌아오지 않는다.** 재현: tests/regression/test_comment_survives_resync.py
    #
    # 표시만 하면 목록에서는 즉시 빠지지만(사용자에겐 삭제와 같아 보인다) 사용자 데이터는
    # 살아 있고, 다음 회차에 돌아오면 아무 일도 없었던 것이 된다. 유예를 넘겨도 안 돌아오면
    # 그때 진짜로 지운다(app/core/retention.py) — 그 시점의 CASCADE 는 의도된 정리다.
    notion_missing_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    # 상위 작업의 Notion page id (0044). **계층을 앱에서 새로 만들지 않는다** — Notion 작업 DB
    # 에 상위/하위 self-relation 이 이미 있고, 계층이 두 벌이 되면 둘이 갈라진 뒤 갈라진 쪽을
    # 아무도 못 고친다.
    #
    # 이 값이 없으면 프로젝트 진행률은 부모와 자식을 구별할 수 없어 Notion 과 똑같이 **이중
    # 계산**한다(부모 1건 + 자식 3건이면 같은 일을 4번 센다). 리프만 세려면 이 한 컬럼이 필요하다.
    # FK 를 걸지 않는 이유: 부모가 아직 동기화되지 않았거나 다른 필터로 빠져 있을 수 있고,
    # 그때 FK 가 있으면 자식 upsert 가 통째로 실패해 동기화가 멈춘다.
    parent_page_id: Mapped[str | None] = mapped_column(String(64), index=True)
    # ── 소속: 이 티켓은 **프로젝트 것**이다 (0060) ────────────────────────────
    #
    # 예전에는 여기 `scope_dept_id`(담당자의 부서로 유도할 예정) 컬럼이 있었다. 그 문은
    # 끝내 안 열렸고(실측 non-null 0건, 읽는 코드 0건) 이제 안 연다 — 담당자 축은 사람이
    # 부서를 옮기면 과거 티켓의 소속이 따라 움직이고, 담당자가 둘이면 소속도 둘이 된다.
    #
    # `project_ids`(아래)는 **외부 소스의 원본**(Notion relation id 다중값)이고,
    # `project_uid` 는 그것을 Portal 프로젝트 **하나**로 해석한 결과다. 권한 계산은 언제나
    # 이 해석 결과만 쓴다 — 외부 소스가 다른 시스템으로 바뀌어도 이 관계는 그대로다.
    project_uid: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=True, index=True
    )
    # 그 해석이 어떻게 끝났는가. `ok` 가 아니면 **fail-closed** 다(전역 관리자만).
    # 임의로 하나를 고르지 않는 이유: 잘못 고른 티켓은 남의 부서로 새고, 그 사고는
    # 화면이 정상으로 보이기 때문에 아무도 신고하지 않는다.
    project_link: Mapped[str] = mapped_column(
        String(16), nullable=False, default=PROJECT_LINK_UNRESOLVED,
        server_default=PROJECT_LINK_UNRESOLVED, index=True,
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
    # 시작일·대분류는 리포트(공수 집계)에는 안 쓰지만 **포털에서 편집해야** 해서 미러링한다
    # (2026-08-04 제품화 지시 — 이 값을 고치려고 노션을 여는 상태를 없앤다).
    start_date: Mapped[str | None] = mapped_column(String(40))
    category: Mapped[str | None] = mapped_column(String(200))

    # 아래 셋은 NAMES_SEP 로 감싼 다중값. project_ids 는 원본 relation id, project_names 는
    # 동기화 때 해석해 둔 표시용 이름(읽을 때 Notion을 다시 안 부르려고 함께 저장한다).
    project_ids: Mapped[str] = mapped_column(Text, nullable=False, default="")
    project_names: Mapped[str] = mapped_column(Text, nullable=False, default="")
    assignee_notion_ids: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # 본문 정본(마크다운). 우리 화면에서 한 번이라도 저장하면 채워지고, 그 뒤로는 이 값이 정본이다
    # (동기화는 이 컬럼을 건드리지 않는다 — sync.py::_upsert 에 없다).
    body_markdown: Mapped[str | None] = mapped_column(Text)
    # 본문을 Notion 까지 밀어 넣는 데 성공한 시각과, 실패했다면 그 이유.
    # **저장 순서가 이 두 컬럼의 존재 이유다**: body_markdown 을 먼저 커밋하고 그다음 Notion 을
    # 부르기 때문에, Notion 이 죽어도 사용자가 친 글은 남는다. 다만 그때 '저장됐다'고만 하면
    # 거짓말이 되므로 어긋난 상태를 여기 적어 두고 상세 화면이 배너로 보여준다(재시도 가능).
    body_synced_at: Mapped[datetime | None] = mapped_column(DateTime)
    body_sync_error: Mapped[str | None] = mapped_column(Text)
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
    # 마지막 동기화가 **실제로 지운** 건수(드리프트 지표). 바닥에 걸려 삭제를 거부했으면 0 이고
    # status 가 SYNC_ERROR + error 에 이유가 남는다 — core/sync_prune.py 참조.
    pruned_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )


class TicketComment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """티켓 댓글 (PLAN Phase 3 §E).

    **`ticket_cache.id`(자체 UUID)에 건다 — Notion page id 가 아니다.** 0023 으로 티켓 캐시를
    만든 이유 중 하나가 정확히 이것이다: 내부 참조가 외부 시스템의 식별자에 묶여 있으면
    소스를 바꾸는 순간 댓글이 전부 고아가 된다. 응답의 `id` 가 여전히 page_id 인 것과는 별개
    문제다(그건 딥링크·감사 호환 때문이고, 여기는 우리 DB 안의 관계다).

    ON DELETE CASCADE 인 이유: Notion 에서 티켓이 사라지면 sync._prune 이 캐시 행을 지운다.
    FK 가 걸린 댓글이 남아 있으면 그 DELETE 가 실패하고,
    sync 는 예외를 통째로 삼키므로 **동기화 전체가 조용히 멈춘다**. 도달할 수 없는 댓글을
    남기려다 티켓 미러를 멈추는 건 나쁜 거래다.

    PG 로 옮기면서 이 이유는 **더 강해졌다**: SQLite 는 `PRAGMA foreign_keys` 로 FK 강제를
    끌 수 있었지만 PG 에는 그 스위치가 없다. 걸어 둔 FK 는 반드시 지켜진다.

    삭제는 soft-delete(deleted_at) 다. 목록 API 는 삭제된 댓글도 본문 없는 툼스톤으로 계속
    돌려준다 — 이미 목록을 받아 둔 클라이언트가 '조용히 사라짐'이 아니라 '삭제됨'을 볼 수 있어야
    한다(행이 그냥 없어지면 클라이언트는 자기 목록이 낡았는지조차 모른다).
    """

    __tablename__ = "ticket_comments"

    ticket_uid: Mapped[str] = mapped_column(
        String(36), ForeignKey("ticket_cache.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    author_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)

    # 삽입 순서를 **1급 컬럼으로** 들고 있는다 (실행목록 5).
    #
    # 예전에는 SQLite 의 숨은 `rowid` 로 동점을 깼다. PG 에는 그런 것이 없고, 없다는 사실이
    # 조용히 드러나지 않는다: `ORDER BY created_at` 만 남기면 같은 순간에 달린 두 댓글의
    # 순서가 **매번 달라진다**. 시계가 멈춘 테스트에서는 늘 동점이라 목록이 절반의 확률로
    # 뒤집히고, 운영에서는 답글이 원글보다 먼저 보인다.
    #
    # `GENERATED ALWAYS AS IDENTITY` 라 앱이 값을 못 넣는다.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False)


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
    projects_json: Mapped[str] = mapped_column(JsonText, nullable=False, default="[]")
    synced_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )


class TicketAttachment(UUIDPrimaryKeyMixin, Base):
    """티켓에 붙인 이미지·PDF 의 메타 (실제 바이트는 data_dir/uploads/ticket/).

    **`ticket_cache.id`(자체 UUID)에 건다 — Notion page id 가 아니다.** 댓글(TicketComment)과
    같은 이유다: 내부 참조가 외부 시스템 식별자에 묶여 있으면 소스를 바꾸는 순간 첨부가 전부
    고아가 된다. CASCADE 도 같은 이유 — 캐시 행이 sync._prune 으로 사라질 때 FK 가 남아 있으면
    그 DELETE 가 실패하고 동기화 전체가 조용히 멈춘다.

    파일 자체는 남는다(CASCADE 는 DB 행만 지운다). 도달할 수 없는 바이트가 디스크에 남는 것은
    게시판 첨부와 같은 성질의 문제이고, 지우는 쪽이 위험하다 — 티켓이 잠깐 안 보였다가 다시
    보이는 동기화 사고에서 사용자가 올린 원본이 사라지는 편이 훨씬 나쁘다.

    소프트 삭제를 쓰지 않는다. 댓글과 달리 첨부는 '누가 무엇을 말했는가'의 기록이 아니라
    파일이라, 툼스톤이 사용자에게 알려 주는 것이 없다(빈 회색 칸 하나).
    """

    __tablename__ = "ticket_attachments"

    ticket_uid: Mapped[str] = mapped_column(
        String(36), ForeignKey("ticket_cache.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    uploaded_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)   # 원본 표시명
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False)  # 디스크 저장명
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
