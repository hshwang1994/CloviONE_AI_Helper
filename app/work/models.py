"""Work Domain 표 (S6). 식별자·채번·관계·활동·상태·스프린트.

## 이 파일이 지키는 것 하나

**「무엇으로 불리는가」와 「몇 번인가」가 서로 다른 표에 있다.** Key 는
`project_key_registry` 가 소유하고(영구·재사용 금지), 번호는
`project_ticket_counters` 가 소유하며(프로젝트별 마지막 발급 번호), 둘을 합친
표시 이름은 **트리거가 파생한다**(D-195). 앱이 `canonical_key` 를 직접 쓰지
않으므로 셋이 어긋날 자리가 없다.

## 왜 SEQUENCE 가 아닌가

PostgreSQL `SEQUENCE` 는 롤백해도 번호를 되돌리지 않는다 — 티켓 생성이 실패할
때마다 번호에 구멍이 생기고, 그 구멍은 사람이 "142번 어디 갔어?" 라고 물었을 때
설명할 수 없다. `INSERT … ON CONFLICT DO UPDATE … RETURNING` 은 행 잠금이라
같은 트랜잭션에서 롤백되면 **번호도 함께 돌아온다**(D-196).

대가는 프로젝트별 직렬화다. 같은 프로젝트에 동시에 티켓을 만들면 뒤엣것이 앞엣것의
커밋을 기다린다. 그것이 「번호가 연속이다」의 값이고, 티켓 생성은 초당 수천 건이
아니다.
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
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import (
    Base,
    JsonText,
    OrgScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    utcnow,
)

# ── Migration Exception 사유 (U11 · D-197) ───────────────────────────────────
EXC_AMBIGUOUS = "ambiguous"          # 소스 relation 이 2개 이상
EXC_MISSING = "missing"              # 소스 relation 이 0개
EXC_UNRESOLVED = "unresolved"        # relation 은 1개인데 Portal 에 짝이 없다
EXC_SOURCE_MISSING = "source_missing"  # 소스 응답에서 사라진 채로 남아 있다
EXC_REASONS: tuple[str, ...] = (
    EXC_AMBIGUOUS, EXC_MISSING, EXC_UNRESOLVED, EXC_SOURCE_MISSING,
)

# ── Relation 종류 ────────────────────────────────────────────────────────────
#
# `subtask_of` 와 `blocks` 는 방향이 있고, `relates_to` 는 없다. 방향 없는 관계를
# 두 행으로 저장하면 한쪽만 지워지는 날이 오므로 **한 행으로 저장하고 순서를 제약이
# 고정한다**(`from < to`).
REL_SUBTASK_OF = "subtask_of"
REL_BLOCKS = "blocks"
REL_RELATES_TO = "relates_to"
REL_KINDS: tuple[str, ...] = (REL_SUBTASK_OF, REL_BLOCKS, REL_RELATES_TO)

# ── Activity 종류 ────────────────────────────────────────────────────────────
ACT_CREATED = "created"
ACT_STATUS = "status"
ACT_ASSIGNEE = "assignee"
ACT_SPRINT = "sprint"
ACT_RANK = "rank"
ACT_RELATION = "relation"
ACT_FIELD = "field"
ACT_KINDS: tuple[str, ...] = (
    ACT_CREATED, ACT_STATUS, ACT_ASSIGNEE, ACT_SPRINT, ACT_RANK, ACT_RELATION, ACT_FIELD,
)

# ── Sprint 상태 ──────────────────────────────────────────────────────────────
SPRINT_PLANNED = "planned"
SPRINT_ACTIVE = "active"
SPRINT_CLOSED = "closed"
SPRINT_STATES: tuple[str, ...] = (SPRINT_PLANNED, SPRINT_ACTIVE, SPRINT_CLOSED)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    """`col IN ('a','b')` — CHECK 제약을 상수 튜플에서 만든다.

    손으로 다시 적으면 상수를 늘린 날 제약만 옛 목록에 남는다. 그러면 새 값이 조용히
    거절되고, 거절 메시지는 제약 이름뿐이라 아무도 원인을 못 찾는다.
    """
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


class ProjectTicketCounter(Base):
    """프로젝트별 **지금까지 발급된 마지막 번호** (D-196).

    「다음 번호」가 아니다. 두 뜻이 섞이면 Migration 시드(`MAX(seq)`)와 런타임 채번이
    한 칸 어긋나 첫 신규 티켓이 마지막 기존 티켓과 같은 번호를 받는다.
    """

    __tablename__ = "project_ticket_counters"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    last_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint("last_seq >= 0", name="ck_ptc_last_seq_nonneg"),
    )


class MigrationException(UUIDPrimaryKeyMixin, Base):
    """소속 Project 를 **정할 수 없어서** 번호를 안 준 티켓과 그 사유 (U11 · D-197).

    이 표가 있는 이유는 「임의 배정 금지」를 코드가 아니라 **데이터로** 증명하기
    위해서다. 잘못 배정한 티켓은 남의 부서로 새고, 화면이 정상으로 보이기 때문에
    아무도 신고하지 않는다. 사유가 남아 있으면 사람이 하나씩 결정할 수 있다.

    미해결 예외는 티켓당 하나다 — 같은 사유가 회차마다 쌓이면 「몇 건 남았나」에
    답할 수 없다. 해결(`resolved_at`)한 행은 이력으로 남긴다.
    """

    __tablename__ = "migration_exceptions"

    ticket_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    # 판정 근거 원문(외부 relation id 목록 등). 사람이 결정하려면 「무엇을 보고 그렇게
    # 판단했는지」가 있어야 한다 — 사유 문자열만으로는 다시 조사해야 한다.
    source_evidence: Mapped[str] = mapped_column(JsonText, nullable=False, default="{}")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    resolved_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        CheckConstraint(_in_list("reason", EXC_REASONS), name="ck_mex_reason"),
        Index(
            "uq_mex_open_ticket", "ticket_id", unique=True,
            postgresql_where=text("resolved_at IS NULL"),
        ),
    )


class TicketRelation(UUIDPrimaryKeyMixin, Base):
    """티켓 사이의 관계. **계층의 정본이 여기 하나다.**

    미러의 `tickets.parent_page_id` 는 이 표의 **입력**이지 두 번째 정본이 아니다 —
    동기화가 그 값을 읽어 `subtask_of` 행을 만들고, 읽는 쪽은 전부 이 표만 본다
    (`app/work/relations.py`). 두 벌이 되면 갈라진 뒤에 갈라진 쪽을 아무도 못 고친다.
    """

    __tablename__ = "ticket_relations"

    from_ticket_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    to_ticket_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        CheckConstraint(_in_list("kind", REL_KINDS), name="ck_trel_kind"),
        CheckConstraint("from_ticket_id <> to_ticket_id", name="ck_trel_not_self"),
        # 방향 없는 관계는 한 행이다. 순서를 제약이 고정하지 않으면 같은 관계가 두 행이
        # 되고, 지울 때 한쪽만 지워진다.
        CheckConstraint(
            "kind <> 'relates_to' OR from_ticket_id < to_ticket_id",
            name="ck_trel_symmetric_ordered",
        ),
        Index("uq_trel_edge", "from_ticket_id", "to_ticket_id", "kind", unique=True),
        # 하위 작업의 부모는 하나다 — 둘이면 진행률 집계가 같은 일을 두 번 센다.
        Index(
            "uq_trel_single_parent", "from_ticket_id", unique=True,
            postgresql_where=text("kind = 'subtask_of'"),
        ),
    )


class TicketActivity(Base):
    """티켓에 무슨 일이 있었는가. 감사 로그와 **다른 표인 이유**가 있다.

    감사 로그(`audit_logs`)는 「누가 시스템에 무엇을 했는가」이고 운영·보안이 본다.
    이 표는 「이 티켓이 어떻게 흘러왔는가」이고 **일하는 사람이 상세 화면에서 본다.**
    한 표로 합치면 티켓 타임라인을 그리려고 전체 감사 로그를 훑게 되고, 반대로
    감사 보존 정책이 티켓 타임라인을 지운다.

    `seq` 를 1급 컬럼으로 드는 이유는 `ticket_comments.seq` 와 같다 — PG 에는 rowid 가
    없어서 `ORDER BY created_at` 만으로는 같은 순간의 두 사건 순서가 매번 달라진다.
    """

    __tablename__ = "ticket_activities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ticket_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # NULL 은 시스템이 한 일이다(동기화·마이그레이션). 사람이 한 일과 구별되지 않으면
    # "내가 안 바꿨는데 내 이름이 있다" 가 생긴다.
    actor_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    field: Mapped[str | None] = mapped_column(String(40))
    from_value: Mapped[str | None] = mapped_column(Text)
    to_value: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, index=True
    )
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False)

    __table_args__ = (
        CheckConstraint(_in_list("kind", ACT_KINDS), name="ck_tact_kind"),
        Index("ix_ticket_activities_timeline", "ticket_id", "seq"),
    )


class TicketWatcher(Base):
    """이 티켓의 변화를 알림으로 받겠다고 한 사람.

    담당자와 다른 축이다 — 담당자는 일을 하는 사람이고, 관찰자는 결과를 알아야 하는
    사람이다(요청한 영업, 검수할 PM). 한 컬럼에 섞으면 관찰자에게 일이 배정된다.
    """

    __tablename__ = "ticket_watchers"

    ticket_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tickets.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class TicketStatus(Base):
    """표시 Status → 내부 Category (§5.2).

    **어휘의 정본은 코드(`app/work/workflow.py`)이고 이 표는 그 결과다.** S5 가
    권한 표에서 쓴 모양 그대로다 — 마이그레이션이 값을 심고 시험이 둘을 맞물린다.
    표가 따로 있어야 하는 이유는 조인이다: 칸반이 「진행 중인 것」을 물을 때 파이썬
    사전을 SQL 에 실어 보낼 수는 없다.

    `sort_order` 는 칸반 열 순서다. 화면마다 다시 정하면 두 화면이 다른 순서를 보인다.
    """

    __tablename__ = "ticket_statuses"

    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 새 티켓의 기본 상태. 정확히 하나여야 한다 — 부분 유니크가 막는다.
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index(
            "uq_ticket_statuses_default", "is_default", unique=True,
            postgresql_where=text("is_default"),
        ),
    )


class Sprint(OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin, Base):
    """스프린트 한 회차. **지금까지 이 제품에 정의된 적이 없던 것이다.**

    실측(INVENTORY 07): `notion_sprint_database_id` 를 읽는 코드가 없고, 화면의
    「이번 주」는 마감일 범위 집계였다. 즉 스프린트라는 말은 쓰였는데 실체가 없었다 —
    그래서 「지난 스프린트에 무엇을 넣었나」에 아무도 답할 수 없었다.

    `project_id` 가 NULL 이면 팀 전체 스프린트다. 한 프로젝트에 동시에 두 개의
    `active` 회차를 둘 수 없다 — 「이번 스프린트」에 답이 둘이면 번다운이 두 개가 된다.
    """

    __tablename__ = "sprints"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    # 달력일이다. `tickets.due_date`·`projects.starts_on` 과 **같은 타입**이고
    # (S7 · P-14a), 바깥 문자열과의 경계는 `app/core/dates.py` 한 곳이다 —
    # 한 화면에서 두 규약을 섞으면 비교가 조용히 어긋난다.
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default=SPRINT_PLANNED)
    goal: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(_in_list("state", SPRINT_STATES), name="ck_sprints_state"),
        CheckConstraint("starts_on < ends_on", name="ck_sprints_window"),
        Index("uq_sprints_name", "org_id", "project_id", "name", unique=True),
        Index(
            "uq_sprints_active", "org_id", text("coalesce(project_id, '')"), unique=True,
            postgresql_where=text("state = 'active'"),
        ),
        Index("ix_sprints_window", "org_id", "starts_on", "ends_on"),
    )


# `backlog_rank` 는 `tickets` 에 붙는다(app/tickets/models.py). 여기서는 그 컬럼이
# 어떤 수인지만 고정한다 — 정밀도를 지정하지 않은 `numeric` 이라 중점 삽입이 자리수를
# 잃지 않는다. 자리수가 무한히 늘지 않도록 `app/work/rank.py` 가 재조정한다.
BACKLOG_RANK_TYPE = Numeric()
BACKLOG_RANK_STEP = Decimal(1024)
