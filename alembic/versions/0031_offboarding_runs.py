"""offboarding_runs + offboarding_ticket_moves (PLAN Phase 6 — 온/오프보딩)

Revision ID: 0031
Revises: 0030
Create Date: 2026-08-03

계획서가 관리자 백로그의 **최우선**으로 지목한 항목(퇴사자 보유 티켓 재배정)을 되돌릴 수 있게
만드는 표 둘이다.

**왜 감사 로그로 부족한가.** `audit_log` 는 before/after 가 JSON 텍스트다. 되돌리기가 그것을
다시 파싱해 실행하면 **감사 로그의 형식이 곧 실행 계약**이 되어, 로그 포맷을 손대는 순간
되돌리기가 조용히 깨진다. 되돌리기에 필요한 값(옮기기 직전의 담당자 구성, 계정에 실제로 적용한
변경)만 1급 컬럼으로 따로 남긴다. 감사 로그는 그대로 함께 남는다 — 목적이 다르다.

**`offboarding_ticket_moves.ticket_uid` 에 FK 를 걸지 않는다.** `ticket_cache` 행은 동기화
prune 이 지운다. CASCADE 면 이력이 증발하고, RESTRICT 면 prune 이 실패해 티켓 미러 전체가
멈춘다(0028 의 `ticket_comments` docstring 이 같은 함정을 기록한다). 여기 남는 값은 '그때 그
티켓이 무엇이었는가'라는 기록이므로 참조 무결성보다 보존이 우선이다.

타임스탬프는 전부 nullable 이거나 애플리케이션이 채운다 — `STRFTIME` 을 쓰지 않는다
(CLAUDE.md §8: SQLite `STRFTIME('%f')` 가 과거 부서 화면을 죽인 함정).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "offboarding_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("successor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="completed"),
        # 계정에 **실제로 적용한** 변경만 참이다. 원래 비활성이던 계정을 되돌리기가 활성으로
        # 만들어 버리면 없던 권한을 주는 셈이 된다.
        sa.Column("deactivated", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("ticket_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("ticket_moved", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("ticket_failed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("undone_at", sa.DateTime(), nullable=True),
        sa.Column("undone_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("undo_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_offboarding_runs_user_id", "offboarding_runs", ["user_id"])
    op.create_index("ix_offboarding_runs_actor_user_id", "offboarding_runs", ["actor_user_id"])
    op.create_index("ix_offboarding_runs_org_id", "offboarding_runs", ["org_id"])
    op.create_index("ix_offboarding_runs_undone_at", "offboarding_runs", ["undone_at"])

    op.create_table(
        "offboarding_ticket_moves",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id", sa.String(36),
            sa.ForeignKey("offboarding_runs.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("ticket_page_id", sa.String(64), nullable=False),
        # FK 없음 — 모듈 docstring 참조.
        sa.Column("ticket_uid", sa.String(36), nullable=True),
        sa.Column("ticket_number", sa.Integer(), nullable=True),
        sa.Column("ticket_title", sa.String(500), nullable=False, server_default=""),
        # NAMES_SEP(0x1f) 로 감싼 앱 user_id 목록 — ticket_cache 의 다중값과 같은 규약.
        sa.Column("before_user_ids", sa.Text(), nullable=False, server_default=""),
        sa.Column("after_user_ids", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="moved"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("reverted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_offboarding_ticket_moves_run_id", "offboarding_ticket_moves", ["run_id"]
    )
    op.create_index(
        "ix_offboarding_ticket_moves_page_id", "offboarding_ticket_moves", ["ticket_page_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_offboarding_ticket_moves_page_id", table_name="offboarding_ticket_moves")
    op.drop_index("ix_offboarding_ticket_moves_run_id", table_name="offboarding_ticket_moves")
    op.drop_table("offboarding_ticket_moves")

    op.drop_index("ix_offboarding_runs_undone_at", table_name="offboarding_runs")
    op.drop_index("ix_offboarding_runs_org_id", table_name="offboarding_runs")
    op.drop_index("ix_offboarding_runs_actor_user_id", table_name="offboarding_runs")
    op.drop_index("ix_offboarding_runs_user_id", table_name="offboarding_runs")
    op.drop_table("offboarding_runs")
