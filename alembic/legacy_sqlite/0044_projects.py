"""프로젝트 subsystem: 앱 DB 가 정본 (0044)

첫 줄에 em 대시를 쓰지 않는다. alembic 이 이 줄을 리비전 메시지로 **stdout 에 찍고**,
Windows 콘솔(cp949)로 파이프될 때 그 한 글자가 디코딩을 깨뜨린다. 마이그레이션 로그를
못 읽으면 배포 중 무엇이 돌았는지 확인할 방법이 사라진다.

Revision ID: 0044
Revises: 0043
Create Date: 2026-08-06

## 왜 앱 DB 가 정본인가

사용자 결정이다: Notion 에는 최소한만 두고 나머지는 앱 DB 가 갖는다. 그래서 `projects` 는
`ticket_cache` 같은 '미러'가 아니라 **처음부터 자체 표**다. `notion_page_id` 는 nullable 보조
외부키일 뿐이고, NULL 이면 Notion 에 짝이 없는 **포털 전용 프로젝트**다. 이 방향을 뒤집으면
(Notion 이 정본) 포털에서 만든 프로젝트가 다음 동기화에서 조용히 사라진다.

## 왜 진행률 컬럼을 두면서도 Notion 의 진행률을 안 받는가

`progress_pct` 는 **앱이 다시 계산한 값의 캐시**다(`app/projects/progress.py`). Notion 의
`티켓 진행률` rollup 은 `percent_per_group / groupName="Complete"` 인데, 작업 DB 의 status
그룹이 `complete = [완료, 취소]` 라서 **취소한 티켓이 완료로 집계된다**(10건 중 3건 취소면
진행률이 그냥 +30% 다). 그 값을 여기 받아 적으면 틀린 숫자가 앱의 정본이 된다.

`progress_pct` 는 nullable 이고 기본이 NULL 이다. **NULL 과 0.0 은 다른 말이다** — NULL 은
"아직 계산한 적이 없다", 0.0 은 "셌는데 0% 다". 기본값을 0 으로 두면 계산이 한 번도 안 돈
프로젝트가 화면에서 '전혀 진행 안 됨'으로 보인다. `health_score` 도 같은 이유로 nullable 이다.

## 날짜를 String 으로 두는 이유

`starts_on` / `ends_on` / `due_on` / `week_of` 는 ISO 'YYYY-MM-DD' **문자열**이다.
`ticket_cache.due_date` 가 이미 그 규약이고(원본이 문자열이며 문자열 비교로 정렬·범위가
맞다), 한 화면에서 두 규약을 섞으면 비교가 조용히 어긋난다.

## `ticket_cache.parent_page_id` — 계층을 새로 만들지 않는다

Notion 작업 DB 에는 상위/하위 self-relation 이 **이미 있다**. WBS 트리를 앱에서 새로 만들면
두 개의 계층이 생기고 둘이 갈라진다. 상위 작업 page id 를 그대로 미러링해 재료로 쓴다.
진행률이 '리프만 세기'를 하려면 이 컬럼이 없이는 부모와 자식을 구별할 수 없다 — 없으면
Notion 과 똑같이 **이중 계산**한다.

⚠️ 0043 이 방금 넣은 `notion_missing_at`(소프트 프룬)은 건드리지 않는다. 여기서는 컬럼
하나를 **더할 뿐**이다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None

_TICKETS = "ticket_cache"
_PARENT_COL = "parent_page_id"
_PARENT_IDX = "ix_ticket_cache_parent_page_id"


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    tables = _table_names()

    if "projects" not in tables:
        op.create_table(
            "projects",
            sa.Column("id", sa.String(36), primary_key=True),
            # 표시 이름. 코드(PRJ-001 같은 약칭)는 조직마다 규칙이 다르고 없을 수도 있어
            # nullable 이다. 없는 코드를 빈 문자열로 채우면 유니크가 두 번째 프로젝트를 막는다.
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("code", sa.String(64), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="active"),
            sa.Column("dept_id", sa.String(36), sa.ForeignKey("departments.id"), nullable=True),
            sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True),
            sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("starts_on", sa.String(40), nullable=True),
            sa.Column("ends_on", sa.String(40), nullable=True),
            sa.Column("goal", sa.Text(), nullable=True),
            sa.Column("biz_type", sa.String(200), nullable=True),
            sa.Column("product", sa.String(200), nullable=True),
            # NULL = 아직 계산 안 함. 0.0 = 계산했는데 0% (모듈 docstring).
            sa.Column("progress_pct", sa.Float(), nullable=True),
            sa.Column("health_score", sa.Integer(), nullable=True),
            sa.Column("archived_at", sa.DateTime(), nullable=True),
            # NULL 이면 포털 전용 프로젝트. unique 는 유지 — 같은 Notion 페이지가 두 행이 되면
            # 목록에 중복이 뜬다(SQLite 는 NULL 을 서로 다르게 보므로 포털 전용은 여러 개 가능).
            sa.Column("notion_page_id", sa.String(64), nullable=True, unique=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        # dept_id 는 **범위 판정이 매 요청 거는 축**이다(app/core/scope.py). 인덱스가 없으면
        # 부서 관리자의 목록이 통째로 풀스캔이 된다.
        op.create_index("ix_projects_dept_id", "projects", ["dept_id"])
        op.create_index("ix_projects_org_id", "projects", ["org_id"])
        op.create_index("ix_projects_owner_user_id", "projects", ["owner_user_id"])
        op.create_index("ix_projects_archived_at", "projects", ["archived_at"])
        op.create_index("ix_projects_notion_page_id", "projects", ["notion_page_id"])
        # 코드는 조직 안에서만 유일하다. 전역 유니크로 두면 조직 B 가 조직 A 와 같은 약칭을
        # 못 쓰게 되는데, 그건 조직 축을 도입한 이유(0038)와 정면으로 어긋난다.
        op.create_index("uq_projects_org_code", "projects", ["org_id", "code"], unique=True)

    if "project_members" not in tables:
        op.create_table(
            "project_members",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "project_id", sa.String(36),
                sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("role", sa.String(16), nullable=False, server_default="member"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_project_members_project_id", "project_members", ["project_id"])
        op.create_index("ix_project_members_user_id", "project_members", ["user_id"])
        # 같은 사람이 한 프로젝트에 두 역할로 들어가면 "이 사람의 역할" 에 답이 둘이 된다.
        op.create_index(
            "uq_project_members", "project_members", ["project_id", "user_id"], unique=True
        )

    if "project_milestones" not in tables:
        op.create_table(
            "project_milestones",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "project_id", sa.String(36),
                sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("due_on", sa.String(40), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="planned"),
            # 이름이 `order` 가 아닌 이유: `ORDER` 는 SQL 예약어라 raw SQL 에서 따옴표를
            # 한 번 빠뜨리면 구문 오류가 아니라 **다른 뜻**으로 파싱될 수 있다. 이 저장소는
            # 실제로 raw text() 질의를 쓴다(app/jobs/repository.py::claim_next). 뜻은 같다.
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index(
            "ix_project_milestones_project_id", "project_milestones", ["project_id"]
        )

    if "project_health_snapshots" not in tables:
        op.create_table(
            "project_health_snapshots",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "project_id", sa.String(36),
                sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
            ),
            # 그 주의 월요일(ISO 'YYYY-MM-DD'). 주를 (연도, 주차) 정수 쌍으로 두면 연말에
            # ISO 주차와 달력 연도가 어긋나 12월 마지막 주가 다음 해로 튄다.
            sa.Column("week_of", sa.String(10), nullable=False),
            sa.Column("score", sa.Integer(), nullable=False),
            # 점수만 남기면 6주 뒤에 "왜 그때 47점이었나" 에 아무도 답할 수 없다.
            sa.Column("reasons_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index(
            "ix_project_health_snapshots_project_id",
            "project_health_snapshots", ["project_id"],
        )
        # 한 주에 한 행. 재계산이 행을 쌓으면 '주간 이력'이 아니라 '실행 로그'가 된다.
        op.create_index(
            "uq_project_health_snapshots_week",
            "project_health_snapshots", ["project_id", "week_of"], unique=True,
        )

    if "project_weekly_reports" not in tables:
        op.create_table(
            "project_weekly_reports",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "project_id", sa.String(36),
                sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column("week_of", sa.String(10), nullable=False),
            sa.Column("summary_md", sa.Text(), nullable=False, server_default=""),
            # rule = 규칙으로 만든 요약, llm = 모델이 쓴 요약. 화면이 둘을 구별해 말할 수
            # 있어야 한다. 구별을 안 남기면 나중에 "이 문장 누가 썼나" 에 답할 수 없다.
            sa.Column("source", sa.String(8), nullable=False, server_default="rule"),
            sa.Column("generated_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index(
            "ix_project_weekly_reports_project_id", "project_weekly_reports", ["project_id"]
        )
        op.create_index(
            "uq_project_weekly_reports_week",
            "project_weekly_reports", ["project_id", "week_of"], unique=True,
        )

    # ── ticket_cache 미러 컬럼 하나 (0043 의 notion_missing_at 은 건드리지 않는다) ──
    if _TICKETS in tables:
        if _PARENT_COL not in _columns(_TICKETS):
            op.add_column(_TICKETS, sa.Column(_PARENT_COL, sa.String(64), nullable=True))
        # 진행률이 '리프만 세기' 를 하려면 프로젝트 티켓 전체에서 부모 집합을 뽑아야 한다.
        if _PARENT_IDX not in _indexes(_TICKETS):
            op.create_index(_PARENT_IDX, _TICKETS, [_PARENT_COL])


def downgrade() -> None:
    tables = _table_names()

    if _TICKETS in tables:
        if _PARENT_IDX in _indexes(_TICKETS):
            op.drop_index(_PARENT_IDX, table_name=_TICKETS)
        if _PARENT_COL in _columns(_TICKETS):
            op.drop_column(_TICKETS, _PARENT_COL)

    # 자식(FK CASCADE)부터 지운다 — 부모를 먼저 지우면 FK 가 걸린 채로 남는다.
    for table in (
        "project_weekly_reports",
        "project_health_snapshots",
        "project_milestones",
        "project_members",
        "projects",
    ):
        if table in tables:
            op.drop_table(table)
