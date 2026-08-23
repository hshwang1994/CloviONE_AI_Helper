"""프로젝트 subsystem 모델 (0044). **앱 DB 가 정본이다.**

`ticket_cache` 와 정반대의 성격이라는 점을 먼저 적어 둔다. 티켓 캐시는 Notion 작업 DB 의
미러이고 동기화가 값을 덮어쓴다. 여기 `Project` 는 미러가 아니라 **자체 표**다 — 사용자
결정에 따라 Notion 에는 최소한만 두고 나머지는 앱이 갖는다. `notion_page_id` 는 nullable
보조 외부키일 뿐이고 NULL 이면 Notion 에 짝이 없는 **포털 전용 프로젝트**다.

이 방향이 중요한 이유: 미러로 다루면 포털에서 만든 프로젝트가 다음 동기화의 prune 대상이
되어 조용히 사라진다. 정본이므로 동기화는 이 표를 **지우지 않는다**(동기화 자체는 다음
단계이고 여기서는 만들지 않는다).

## 진행률과 헬스는 캐시된 계산 결과다

`progress_pct` 는 Notion 의 `티켓 진행률` rollup 을 받아 적은 값이 **아니다**. 그 rollup 은
`percent_per_group / groupName="Complete"` 인데 작업 DB 의 status 그룹이
`complete = [완료, 취소]` 라서 **취소한 티켓을 완료로 센다**. 앱이 다시 계산한다
(`app/projects/progress.py`) — 그 함수가 계산 근거까지 함께 돌려주는 이유도 같다.

`progress_pct` 와 `health_score` 는 nullable 이고 기본이 NULL 이다. **NULL 과 0 은 다른
말이다**: NULL 은 "아직 계산한 적이 없다", 0 은 "셌는데 0 이다". 기본값을 0 으로 두면 계산이
한 번도 안 돈 프로젝트가 화면에서 '전혀 진행 안 됨'으로 보이고, 그 거짓말은 신고되지 않는다
(그럴듯하기 때문이다).

## 날짜는 `date` 다 (S7 · P-14a)

`starts_on` / `ends_on` / `due_on` / `week_of` 는 **달력일**이고 컬럼 타입이 `date` 다.
예전에는 'YYYY-MM-DD' 문자열이었다 — ISO 는 사전순이 날짜순과 같아서 비교가 그냥
됐기 때문이다. 그런데 문자열은 **틀린 값을 막지 못한다**: `'2026-02-31'` 도 `'TBD'` 도
들어갔고, 그 값 하나가 기간 필터와 번다운을 조용히 왜곡했다. 이제 DB 가 막는다.
바깥 문자열과의 경계는 `app/core/dates.py` 한 곳이다.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
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

# 동기화 상태 어휘. `app/tickets/models.py` 와 **같은 문자열**을 일부러 다시 쓴다 - 운영자가
# 두 화면에서 같은 단어를 봐야 하기 때문이다. import 로 끌어오지 않는 이유는 반대 방향이다:
# 프로젝트가 티켓 모듈에 의존하면 티켓 쪽 상수 하나를 고칠 때 프로젝트 화면이 함께 움직인다.
SYNC_IDLE = "idle"
SYNC_OK = "ok"
SYNC_ERROR = "error"

# 동기화 싱글턴의 고정 id (문서·티켓 sync 싱글턴과 같은 관례).
PROJECT_SYNC_STATE_ID = "projects"

# 프로젝트 상태. 티켓의 상태 어휘(진행/완료/취소)와 **일부러 다른 축**이다 — 프로젝트가
# '완료' 인지와 그 안의 작업이 몇 % 끝났는지는 다른 질문이고, 하나로 뭉치면 진행률 100% 인데
# 아직 안 닫힌 프로젝트를 표현할 수 없다.
PROJECT_ACTIVE = "active"
PROJECT_PLANNED = "planned"
PROJECT_ON_HOLD = "on_hold"
PROJECT_DONE = "done"
PROJECT_STATUSES: tuple[str, ...] = (
    PROJECT_PLANNED, PROJECT_ACTIVE, PROJECT_ON_HOLD, PROJECT_DONE,
)

# 멤버 역할. 앱 전체의 RBAC 역할(`app/users/models.py`)과 **다른 축**이다: 저쪽은 "이 사람이
# 포털에서 무엇을 할 수 있는가", 이쪽은 "이 프로젝트에서 어떤 자리인가". 한 컬럼에 섞으면
# '운영자인데 이 프로젝트에서는 참관만' 을 표현할 수 없다.
MEMBER_OWNER = "owner"
MEMBER_MEMBER = "member"
MEMBER_VIEWER = "viewer"
MEMBER_ROLES: tuple[str, ...] = (MEMBER_OWNER, MEMBER_MEMBER, MEMBER_VIEWER)

MILESTONE_PLANNED = "planned"
MILESTONE_DONE = "done"
MILESTONE_MISSED = "missed"
MILESTONE_STATUSES: tuple[str, ...] = (
    MILESTONE_PLANNED, MILESTONE_DONE, MILESTONE_MISSED,
)

# 주간 리포트를 누가 썼는가. 구별을 안 남기면 몇 주 뒤에 "이 문장 규칙이 만든 건가 모델이
# 쓴 건가" 에 답할 수 없고, 그러면 둘 다 못 믿게 된다.
REPORT_SOURCE_RULE = "rule"
REPORT_SOURCE_LLM = "llm"
REPORT_SOURCES: tuple[str, ...] = (REPORT_SOURCE_RULE, REPORT_SOURCE_LLM)


class Project(OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin, Base):
    """프로젝트 한 건. **범위 판정의 축은 `dept_id` 와 `org_id` 두 개다.**

    `app/core/scope.py::scope_filter` 가 이 두 컬럼을 그대로 받는다. 컬럼 이름을 바꾸면
    범위가 조용히 `MATCH_NOTHING` 이 되는 것이 아니라 **조건이 안 걸린 채로 지나간다** —
    호출부가 컬럼 객체를 넘기므로 이름을 바꾸면 import 가 깨져서 알게 되지만, 컬럼을
    nullable 로 비워 두는 것은 아무도 못 알아챈다(부서 없는 프로젝트는 부서 범위에서
    통째로 사라진다). 그래서 부서를 비워 두는 것이 정상인 자리인지 화면이 물어야 한다.
    """

    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Project Code. **서버가 짓고 사람은 못 고친다** (D-282). 규칙과 생성은
    # `app/work/codes.py` 가 정본이고, 이 컬럼은 그 결과를 담는 자리다.
    #
    # 전역 유일이다(`uq_projects_code`) — 조직 안에서만 유일하던 앞 정책은 폐기했다.
    # 티켓 이름 `<CODE>-<SEQ>` 는 조직을 안 지고 다니므로, 조직마다 같은 코드를 허용하면
    # 같은 문자열이 두 티켓을 가리킨다.
    #
    # 아직 nullable 인 이유는 하나뿐이다: 이관이 표를 먼저 복사하고 코드를 뒤에 붙인다
    # (D-281 의 순서). 그 사이 잠깐 비어 있고, 그 뒤로는 비는 경로가 없다.
    code: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=PROJECT_ACTIVE)

    dept_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("org_units.id"), index=True
    )
    owner_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), index=True
    )

    starts_on: Mapped[date | None] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)
    goal: Mapped[str | None] = mapped_column(Text)
    biz_type: Mapped[str | None] = mapped_column(String(200))
    product: Mapped[str | None] = mapped_column(String(200))

    # 앱이 다시 계산한 값의 캐시. NULL = 아직 계산 안 함(클래스 docstring).
    progress_pct: Mapped[float | None] = mapped_column(Float)
    health_score: Mapped[int | None] = mapped_column(Integer)

    # 소프트 삭제. 하드 삭제를 안 쓰는 이유는 CASCADE 다 — 주간 이력과 리포트가 함께
    # 사라지는데 그 둘은 재계산으로 돌아오지 않는다(그때의 판단 기록이기 때문이다).
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)

    # 낙관적 잠금 (S6). 저장할 때마다 1 씩 늘고, 편집을 시작할 때 받은 값과 다르면 409 다.
    #
    # 예전에는 `notion_version` — **Notion 에 실려 나가는 필드 집합의 해시**였다. 그 지문은
    # 두 가지를 못 잡았다: (1) 소스에 안 보내는 값(담당자·마일스톤·헬스)이 바뀐 것과
    # (2) 소스가 바뀌면 지문 계산의 입력 목록도 함께 바뀐다는 것. 정수는 그 둘과 무관하다.
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    # NULL 이면 포털 전용 프로젝트. unique 는 유지한다(같은 페이지가 두 행이면 목록 중복).
    notion_page_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)

    # ── Notion 미러 값 (0045). **정본이 아니라 '저쪽은 이렇게 말한다' 이다.** ──────────
    #
    # Notion 이 계산한 진행률(0..100). `progress_pct` 옆에 나란히 두는 것이 목적이다.
    # 저 값은 취소한 티켓을 완료로 세고(status 그룹 complete = [완료, 취소]) 하위 작업을
    # 부모와 이중 계산하므로 정본으로 쓸 수 없다(app/projects/progress.py 에 실측 근거).
    # 그렇다고 감추면 사용자는 Notion 화면과 포털 숫자가 다른 이유를 알 방법이 없다.
    notion_progress_pct: Mapped[float | None] = mapped_column(Float)
    # Notion 진행 상태 원문(백로그/계획 중/진행 중/차질/완료/취소). `status` 와 **다른 축**이라
    # 따로 담는다: '차질' 은 앱 어휘에 없고 'on_hold' 는 Notion 어휘에 없어서 1:1 로 겹치지
    # 않는다. 억지로 맞추면 '차질'(가장 봐야 할 상태)이 '진행 중' 으로 뭉개져 사라진다.
    notion_status: Mapped[str | None] = mapped_column(String(64))
    # 담당자(정)의 Notion person id 목록(NAMES_SEP 다중값). 앱 사용자로 해석되는 사람은
    # `owner_user_id` 에도 들어가지만, 해석되지 않는 사람(포털 미가입·매핑 미검증)이 있어도
    # 값을 잃지 않으려고 원문을 함께 둔다(ticket_cache.assignee_notion_ids 와 같은 규약).
    notion_owner_ids: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # "이번 회차 Notion 응답에서 안 보였다" 표시. **지우지 않는다** - 지우면 CASCADE 로
    # 마일스톤·주간 리포트·헬스 이력·참여자가 함께 사라지는데 넷 다 Notion 에 없다.
    #
    # ⚠️ 티켓(0043)과 **다른 점**: 표시된 프로젝트를 목록에서 감추지 않는다. 티켓은 미러라
    # 감추는 것이 맞지만, 프로젝트 행은 앱 정본이라 Notion 이 한 회차 깜빡였다고 포털의
    # 마일스톤·주간 리포트가 화면에서 통째로 사라지면 안 된다. 이 값은 배지용 사실이다.
    notion_missing_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    notion_last_edited: Mapped[datetime | None] = mapped_column(DateTime)
    # **노션 값을 이 행에 반영한 시각**이지 "언제 확인했나" 가 아니다. 확인만 하고 값이
    # 같았던 회차는 행을 아예 안 건드린다 - 건드리면 `updated_at` 의 onupdate 가 딸려 붙어
    # 회차마다 전 프로젝트의 갱신 시각이 덮이고, 목록 정렬(updated_at DESC)이 무너진다
    # (app/projects/sync.py::_upsert 에 전말을 적어 뒀다).
    # 미러 전체의 신선도는 `project_sync_state.last_success_at` 이 답한다.
    notion_synced_at: Mapped[datetime | None] = mapped_column(DateTime)
    # push(앱 → Notion) 가 실패했을 때 그 이유. 로컬 저장은 롤백하지 않는다 - 롤백하면
    # 사용자가 방금 고친 이름·기간이 Notion 장애 때문에 사라진다(ticket_cache.body_sync_error
    # 가 같은 판단을 기록한다). 대신 어긋난 상태를 여기 남겨 화면이 배너로 말하게 한다.
    notion_sync_error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        # 코드는 **전역에서** 하나다. 부분 유니크인 이유는 위 컬럼 주석의 그 잠깐 —
        # 표 복사와 코드 부여 사이에 여러 행이 NULL 이다. NULL 은 서로 다른 값이므로
        # 그 상태를 이 인덱스가 막지 않는다.
        Index(
            "uq_projects_code", "code", unique=True,
            postgresql_where=text("code IS NOT NULL"),
        ),
        # 앱이 만든 모양을 DB 가 다시 잰다. 두 벌이라서가 아니라, 이관·수동 SQL·되감기
        # 처럼 **앱을 안 거치는 쓰기**가 실제로 있기 때문이다. 정본은
        # `app/work/codes.py::CODE_ALPHABET` 이고 이 정규식은 그 사본이다 —
        # `tests/unit/test_project_codes.py` 가 둘이 같은지 확인한다.
        CheckConstraint(
            r"code IS NULL OR code ~ '^[ABCDEFGHJKMNPQRSTUVWXYZ]{6}$'",
            name="ck_projects_code_shape",
        ),
    )


class ProjectSyncState(Base):
    """Notion 프로젝트 미러 동기화 싱글턴. `TicketSyncState` 와 같은 모양이다.

    같은 모양으로 두는 이유는 운영 화면이다: 두 미러의 상태를 한 표로 보여 줄 때 컬럼 이름이
    다르면 화면이 두 벌의 번역을 갖게 되고, 그 번역이 갈라지는 순간 한쪽이 조용히 안 보인다.
    """

    __tablename__ = "project_sync_state"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # 항상 PROJECT_SYNC_STATE_ID
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=SYNC_IDLE)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime)
    project_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 상한에 걸려 일부만 받아온 회차. True 면 prune 을 건너뛰었다는 뜻이다.
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 실제로 **표시한** 건수. 소프트 프룬이라 '지운 건수' 가 아니다.
    pruned_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )


class ProjectMember(TimestampMixin, UUIDPrimaryKeyMixin, Base):
    """프로젝트 참여자. `Project.owner_user_id` 와 **역할이 겹치지 않는다**.

    소유자 컬럼은 "이 프로젝트의 책임자 한 명"(목록에 한 줄로 보여야 한다), 이 표는
    "참여자 전원"이다. 소유자를 이 표에서만 찾게 하면 목록 한 화면이 프로젝트 수만큼
    질의를 더 하게 되고, 반대로 참여자를 컬럼 하나로 두면 다중값이 다시 문자열이 된다.
    """

    __tablename__ = "project_members"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False, default=MEMBER_MEMBER)

    __table_args__ = (
        # 같은 사람이 두 역할로 들어가면 "이 사람의 역할" 에 답이 둘이 된다.
        Index("uq_project_members", "project_id", "user_id", unique=True),
    )


class ProjectMilestone(TimestampMixin, UUIDPrimaryKeyMixin, Base):
    """중간 목표. 진행률과 **별개로** 본다.

    진행률은 작업 공수의 비율이고 마일스톤은 약속한 날짜다. 둘이 어긋나는 것(진행률 80% 인데
    다음 주 마일스톤을 못 맞춤)이 정확히 화면이 알려야 하는 상태라, 하나를 다른 하나로
    유도하지 않는다.
    """

    __tablename__ = "project_milestones"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    due_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=MILESTONE_PLANNED)
    # `order` 가 아닌 이유: SQL 예약어라 raw text() 질의에서 따옴표를 빠뜨리면 조용히 깨진다
    # (이 저장소는 실제로 raw 질의를 쓴다 — app/jobs/repository.py::claim_next). 뜻은 같다.
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ProjectHealthSnapshot(UUIDPrimaryKeyMixin, Base):
    """주간 헬스 이력 한 줄.

    **왜 이력을 따로 쌓는가**: `Project.health_score` 는 '지금' 하나뿐이라 덮어쓰면 지난주
    값이 사라진다. "지난달부터 계속 나빠지고 있다" 는 한 점으로는 말할 수 없는 문장이고,
    그것이 이 표가 답하려는 질문이다.

    `reasons_json` 을 함께 남기는 이유도 같다 — 점수만 남기면 6주 뒤에 "왜 그때 47점이었나"
    에 아무도 답하지 못한다. 그러면 점수 자체를 아무도 안 믿게 된다.
    """

    __tablename__ = "project_health_snapshots"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # 그 주의 월요일. (연도, 주차) 정수 쌍으로 두면 연말에 ISO 주차와 달력 연도가
    # 어긋나 12월 마지막 주가 다음 해로 튄다.
    week_of: Mapped[date] = mapped_column(Date, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    reasons_json: Mapped[str] = mapped_column(JsonText, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        # 한 주에 한 행. 재계산이 행을 쌓으면 '주간 이력' 이 아니라 '실행 로그' 가 된다.
        Index("uq_project_health_snapshots_week", "project_id", "week_of", unique=True),
    )


class ProjectWeeklyReport(TimestampMixin, UUIDPrimaryKeyMixin, Base):
    """주간 리포트 본문. 헬스 스냅샷과 **한 주 단위로 짝**이지만 표를 나눈다.

    스냅샷은 숫자와 근거(기계가 읽는다), 리포트는 사람이 읽는 문장이다. 한 표에 두면
    리포트를 다시 쓸 때마다 점수 이력이 함께 흔들린다.
    """

    __tablename__ = "project_weekly_reports"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    week_of: Mapped[date] = mapped_column(Date, nullable=False)
    summary_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(String(8), nullable=False, default=REPORT_SOURCE_RULE)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        Index("uq_project_weekly_reports_week", "project_id", "week_of", unique=True),
    )
