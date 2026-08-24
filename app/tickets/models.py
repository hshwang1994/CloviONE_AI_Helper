"""티켓 표 (§7.1.A → S6). **표 이름은 `tickets` 다.**

0023 이 이 표를 `ticket_cache` 라는 이름으로 만들었고, 그때는 그 이름이 정직했다 —
워커가 Notion "작업" DB 를 통째로 읽어 여기 미러링하고 화면은 로컬만 읽었다. 그래서
(1) 목록이 Notion 왕복 없이 즉시 뜨고 (2) Notion 이 죽어도 마지막 정상 동기화
데이터로 계속 보인다(§17.4 장애 격리).

S6 이 티켓 번호·표시 이름·상태·순서를 이 표에 붙이면서 그 이름이 틀린 말이 됐다.
캐시는 지워도 되는 것이고, 이 표는 지우면 티켓 번호가 사라진다 — `tickets` 로 옮겼다
(D-234 가 `departments` → `org_units` 에 쓴 것과 같은 이전이고, **컬럼 이름은 그대로**).
`TicketCache` 는 같은 클래스의 별칭으로 남아 기존 호출부가 그대로 동작한다.

처음부터 이 표가 '얇은 읽기 캐시' 가 아니었던 자리 둘:
  * 자체 UUID PK 를 갖고 `notion_page_id` 는 nullable 보조 외부키이며, 본문 정본
    (`body_markdown`)과 `source` 컬럼을 처음부터 갖는다.
  * 다중값(프로젝트 id/이름, 담당자 Notion id)은 문서 캐시와 **같은** sentinel-wrapped
    구분자 규약(app.core.models_base.NAMES_SEP)으로 저장한다. 새 규약을 만들지 않는다.

담당자는 원본 Notion user id 로 저장하고 앱 user 로의 해석은 읽는 시점에 한다 — 매핑이
바뀌어도 캐시를 다시 채울 필요가 없고, 응답에는 raw Notion id 를 절대 싣지 않는다(§12.3).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
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


class Ticket(OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin, Base):
    """티켓 한 건. **표 이름이 `tickets` 다** (S6).

    0023 이 이 표를 만들 때 이름이 `ticket_cache` 였고 그 이름은 정직했다 — 그때는
    Notion 미러였다. S6 이 식별자·채번·상태·순서를 여기 붙이면서 그 이름이 틀린 말이
    됐다: 캐시는 지워도 되는 것이고 이 표는 지우면 티켓 번호가 사라진다.

    D-234(`departments` → `org_units`)와 같은 이전이다. **컬럼 이름은 그대로 둔다** —
    `project_uid` 는 API 응답에 그대로 나가는 이름이고(`ticket_view`), 바꾸면 사용자와
    프런트가 보는 말이 함께 바뀐다. `TicketCache` 는 이 클래스의 별칭으로 남는다.

    ## 두 층의 이름 (D-282)

    | 층 | 컬럼 | 성격 |
    |---|---|---|
    | Internal | `id` (uuid) | 영구 불변. 내부 참조는 전부 이것이다 |
    | Canonical | `canonical_key` (`ABCDEF-37`) | **트리거가 파생한다.** 앱이 직접 쓰지 않는다 |

    세 번째 층(`legacy_key` · `GIT-142`)이 있었고 **없앴다**. 옛 코드를 이관하지 않기로
    했으므로(D-283) 그 층에 들어올 값이 없다. Project Code 가 안 바뀌므로 canonical 이
    별칭으로 밀려나는 일도 없다 — 그래서 `ticket_key_aliases` 도 함께 사라졌다.

    `canonical_key` 를 Generated Column 으로 만들 수 없는 이유는 그대로다 — PostgreSQL
    Generated Column 은 다른 표(`projects.code`)를 참조할 수 없다.
    """

    __tablename__ = "tickets"

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
    # 달력일이다 (S7 · P-14a). 예전에는 소스가 준 ISO 문자열을 그대로 담았는데,
    # 문자열은 `'2026-02-31'` 도 `'TBD'` 도 받았고 그 값 하나가 기간 필터와 번다운을
    # 조용히 왜곡했다. 소스 문자열과의 경계는 `app/core/dates.py` 한 곳이다 (D-248).
    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    # 시작일·대분류는 리포트(공수 집계)에는 안 쓰지만 **포털에서 편집해야** 해서 미러링한다
    # (2026-08-04 제품화 지시 — 이 값을 고치려고 노션을 여는 상태를 없앤다).
    start_date: Mapped[date | None] = mapped_column(Date)
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

    notion_created_time: Mapped[datetime | None] = mapped_column(DateTime)
    notion_last_edited: Mapped[datetime | None] = mapped_column(DateTime)
    synced_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    # ── 두 층의 이름 (S6 · D-282) ───────────────────────────────────────────
    #
    # `seq` 는 프로젝트 안의 번호이고 `project_ticket_counters` 가 발급한다(D-196).
    # `canonical_key` 는 **앱이 쓰지 않는다** — BEFORE INSERT/UPDATE 트리거가
    # `projects.code || '-' || seq` 로 파생시킨다. 앱이 쓰면 둘이 어긋날 수 있고,
    # 어긋난 티켓은 검색으로도 링크로도 못 찾는다.
    #
    # 이 이름이 **영원히 같은 티켓을 가리키는** 근거는 Project Code 가 안 바뀌고
    # 재사용되지 않는다는 것 하나다(D-282). 그 근거가 무너지면 여기에 유니크 제약을
    # 걸어도 못 잡는다 — 같은 문자열이 서로 다른 시각에 서로 다른 티켓을 뜻하게 된다.
    seq: Mapped[int | None] = mapped_column(Integer)
    canonical_key: Mapped[str | None] = mapped_column(String(64))

    # ── 낙관적 잠금 (S6) ────────────────────────────────────────────────────
    #
    # 저장할 때마다 1 씩 는다. 편집을 시작할 때 받은 값과 다르면 409 다.
    # 프로젝트가 쓰던 `notion_version`(Notion 페이로드 해시)을 대신한다 — 해시는
    # **외부 소스에 실려 나가는 필드 집합**을 지문으로 삼아서, 소스에 안 보내는 값
    # (담당자·스프린트·순서)이 바뀌어도 충돌을 못 잡았다.
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    # ── 스프린트와 백로그 순서 (S6) ─────────────────────────────────────────
    #
    # `backlog_rank` 는 `priority` 와 **다른 축**이다. 우선순위는 "얼마나 급한가"고
    # 순서는 "다음에 무엇을 하는가"다 — 높음 3건의 선후는 우선순위가 답하지 못한다.
    #
    # 정밀도를 지정하지 않은 `numeric` 이라 두 값 사이에 언제나 중점이 있다. 전체
    # 재번호 없이 삽입할 수 있고, 자리수는 `app/work/rank.py` 가 재조정한다.
    sprint_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sprints.id", ondelete="SET NULL"), index=True
    )
    backlog_rank: Mapped[Decimal | None] = mapped_column(Numeric())

    __table_args__ = (
        CheckConstraint("seq IS NULL OR seq > 0", name="ck_tickets_seq_positive"),
        # **번호와 표시 이름은 함께 있거나 함께 없다.** 그리고 번호가 있으면 소속
        # 프로젝트가 있다.
        #
        # 초안(§5.2)은 `project_id` 까지 셋을 한 묶음으로 묶었다 — 「배정됐거나 전부
        # NULL 이거나」. 그 제약은 지금도 못 건다: 이관은 표를 먼저 복사하고 코드를
        # 뒤에 붙이므로(D-281 의 순서) 그 사이 티켓 1,124행이 프로젝트에는 연결돼
        # 있는데 번호는 없는 상태로 존재한다.
        #
        # 그래서 실제로 지켜야 하는 불변식만 남긴다: **번호는 코드를 가진 프로젝트
        # 안에서만 발급된다.** 그 절반은 여기가, 나머지 절반(프로젝트에 코드가
        # 있는가)은 트리거가 막는다.
        CheckConstraint(
            "(seq IS NULL AND canonical_key IS NULL) OR "
            "(seq IS NOT NULL AND canonical_key IS NOT NULL AND project_uid IS NOT NULL)",
            name="ck_tickets_key_assigned",
        ),
        CheckConstraint("version > 0", name="ck_tickets_version_positive"),
        Index(
            "uq_tickets_project_seq", "project_uid", "seq", unique=True,
            postgresql_where=text("project_uid IS NOT NULL AND seq IS NOT NULL"),
        ),
        Index(
            "uq_tickets_canonical", "canonical_key", unique=True,
            postgresql_where=text("canonical_key IS NOT NULL"),
        ),
        # 백로그 화면은 프로젝트별로 순서대로 읽는다.
        Index("ix_tickets_backlog", "project_uid", "backlog_rank"),
    )


# 옛 이름. 0023~S5 의 호출부 57곳이 이 이름을 쓴다 — 같은 클래스의 별칭이라
# `isinstance` 도 질의도 그대로 동작한다 (D-234 가 `Department` 에 쓴 것과 같은 수법).
TicketCache = Ticket


def api_page_id(row: Ticket) -> str:
    """행 → **API 가 부르는 `page_id`**. `tickets/service.py::ticket_row_for` 의 역함수다.

    두 축이다(S14): 이관해 온 티켓은 `notion_page_id` 로 열리고(옛 링크가 계속 살아야
    한다), 자체 DB 에서 만든 티켓은 그 칸이 `NULL` 이라 행의 uuid 로 열린다.

    🔴 이 변환을 호출부마다 손으로 쓰면 **어디선가 `notion_page_id` 만 읽는다.** 그 자리는
    자체 티켓에서 `None` 을 받고, `None` 은 오류가 아니라 「그런 티켓 없음」으로 읽힌다 —
    판에서 카드가 안 열리고, 버린 티켓이 판에 남고, 상태 변경이 404 가 되고, 알림이 아무
    데도 안 간다. 넷 다 조용하다. 그래서 변환은 이 함수 하나다.

    `Ticket.id` 는 NOT NULL 이므로 돌려주는 값은 항상 문자열이다.
    """
    return row.notion_page_id or row.id


def api_page_id_expr():
    """`api_page_id` 의 SQL 판. 질의 안에서 같은 두 축을 쓰려면 이것을 쓴다.

    파이썬 쪽과 값이 갈라지면 「목록에는 있는데 검색에는 없다」 같은 모양이 되고, 그 차이는
    두 구현을 나란히 놓고 읽기 전에는 안 보인다.
    """
    return func.coalesce(Ticket.notion_page_id, Ticket.id)


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
    # 마지막 동기화가 **실제로 지운** 건수(드리프트 지표)였다. 미러 동기화가 사라진 뒤로
    # (S14 · D-284) 이 칸에 쓰는 코드가 없다 — 표를 내리는 것은 별도 migration 몫이라
    # 컬럼만 남아 있고, 값은 항상 0 이다.
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
        String(36), ForeignKey("tickets.id", ondelete="CASCADE"),
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
        String(36), ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # 비어 있을 수 있다: **이관이 가져온 파일에는 올린 사람이 없다** (D12 · 0014).
    # 티켓 본문에 박혀 있던 이미지를 옮길 때 누가 붙였는지를 원본이 파일 단위로 알려
    # 주지 않는다. 아무나 골라 적으면 「이 사람이 올렸다」가 거짓 기록으로 남고, 그
    # 거짓은 화면에 정상으로 보여서 아무도 신고하지 않는다. `NULL` 은 「올린 사람이
    # 없다」를 그대로 말한다 — `DocumentAttachment.created_by` 가 같은 뜻의 같은 모양이다.
    uploaded_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)   # 원본 표시명
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False)  # 디스크 저장명
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
