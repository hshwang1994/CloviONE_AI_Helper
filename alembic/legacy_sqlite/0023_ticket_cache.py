"""ticket_cache / ticket_sync_state / ticket_meta_cache — 티켓 로컬 미러 (§7.3, PLAN §A)

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-03

이 단계는 **쓰기 전용**이다: 워커가 캐시를 채우기 시작하지만 읽기 경로는 아직 Notion 실시간
그대로다. 그래서 앱 동작·응답 형태가 100% 그대로여야 하고 API 골든 회귀가 바이트 단위로 통과한다.
읽기 전환은 다음 단계(저장소 seam) 몫이다.

싱글턴 두 행(ticket_sync_state / ticket_meta_cache)은 document_sync_state 와 같은 관례로 여기서
시드한다. 타임스탬프는 반드시 파이썬 datetime 으로 만들어 파라미터로 바인딩한다(SQLite
STRFTIME '%f' 금지 — 초를 두 번 써 넣어 나중에 ORM isoformat 파싱이 깨진다, CLAUDE.md §8).
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

_SYNC_STATE_ID = "tickets"
_META_CACHE_ID = "tickets"


def upgrade() -> None:
    op.create_table(
        "ticket_cache",
        # 자체 UUID PK. 내부 참조(댓글·휴지통·알림)는 앞으로 이 id를 쓴다 — notion_page_id는
        # 소스가 Notion일 때만 채워지는 보조 외부키다(§7.1.A).
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("notion_page_id", sa.String(64), nullable=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("scope_dept_id", sa.String(36), sa.ForeignKey("departments.id"), nullable=True),
        sa.Column("notion_ticket_number", sa.Integer(), nullable=True),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("title", sa.String(500), nullable=False, server_default=""),
        sa.Column("status", sa.String(64), nullable=True),
        sa.Column("priority", sa.String(64), nullable=True),
        sa.Column("difficulty", sa.String(64), nullable=True),
        sa.Column("est_wd", sa.Float(), nullable=True),
        sa.Column("act_wd", sa.Float(), nullable=True),
        sa.Column("due_date", sa.String(40), nullable=True),
        # NAMES_SEP(0x1f) sentinel-wrapped 다중값 — document_cache 와 같은 규약.
        sa.Column("project_ids", sa.Text(), nullable=False, server_default=""),
        sa.Column("project_names", sa.Text(), nullable=False, server_default=""),
        sa.Column("assignee_notion_ids", sa.Text(), nullable=False, server_default=""),
        sa.Column("body_markdown", sa.Text(), nullable=True),
        sa.Column("source", sa.String(16), nullable=False, server_default="notion"),
        sa.Column("notion_created_time", sa.String(40), nullable=True),
        sa.Column("notion_last_edited", sa.String(40), nullable=True),
        sa.Column("synced_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    # 같은 Notion 페이지가 두 행이 되면 목록에 중복이 뜬다. SQLite는 UNIQUE에서 NULL을 서로
    # 다르게 취급하므로 native 티켓(page_id 없음)은 이 제약에 걸리지 않는다.
    op.create_index(
        "ix_ticket_cache_notion_page_id", "ticket_cache", ["notion_page_id"], unique=True
    )
    op.create_index("ix_ticket_cache_org_id", "ticket_cache", ["org_id"])
    op.create_index("ix_ticket_cache_scope_dept_id", "ticket_cache", ["scope_dept_id"])
    op.create_index("ix_ticket_cache_status", "ticket_cache", ["status"])
    op.create_index("ix_ticket_cache_due_date", "ticket_cache", ["due_date"])

    op.create_table(
        "ticket_sync_state",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="idle"),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("ticket_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("truncated", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "ticket_meta_cache",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("statuses", sa.Text(), nullable=False, server_default=""),
        sa.Column("priorities", sa.Text(), nullable=False, server_default=""),
        sa.Column("difficulties", sa.Text(), nullable=False, server_default=""),
        sa.Column("projects_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("synced_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO ticket_sync_state"
            " (id, status, ticket_count, truncated, updated_at)"
            " VALUES (:id, 'idle', 0, 0, :now)"
        ).bindparams(id=_SYNC_STATE_ID, now=now)
    )
    bind.execute(
        sa.text(
            "INSERT INTO ticket_meta_cache"
            " (id, statuses, priorities, difficulties, projects_json, updated_at)"
            " VALUES (:id, '', '', '', '[]', :now)"
        ).bindparams(id=_META_CACHE_ID, now=now)
    )


def downgrade() -> None:
    op.drop_table("ticket_meta_cache")
    op.drop_table("ticket_sync_state")
    op.drop_index("ix_ticket_cache_due_date", table_name="ticket_cache")
    op.drop_index("ix_ticket_cache_status", table_name="ticket_cache")
    op.drop_index("ix_ticket_cache_scope_dept_id", table_name="ticket_cache")
    op.drop_index("ix_ticket_cache_org_id", table_name="ticket_cache")
    op.drop_index("ix_ticket_cache_notion_page_id", table_name="ticket_cache")
    op.drop_table("ticket_cache")
