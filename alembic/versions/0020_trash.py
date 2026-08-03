"""휴지통(trash) — 티켓·문서 삭제를 노션에서 바로 지우지 않고 보관기간 동안 잡아둔다.

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-29

티켓/문서 '삭제'는 이 표에 기록만 하고(노션 페이지는 그대로), 목록에서는 숨긴다. 관리자 설정
`trash_retention_days`(기본 7일)가 지나면 백그라운드 작업이 노션 페이지를 보관처리(archive)하고
이 행을 지운다. 복원은 이 행을 지워 원래 목록으로 되돌린다(노션은 손대지 않았으므로 그대로 복귀).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trash_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("item_type", sa.String(16), nullable=False),  # ticket | document
        sa.Column("notion_page_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(400), nullable=False, server_default=""),
        sa.Column("url", sa.String(1000), nullable=True),
        sa.Column("deleted_by_user_id", sa.String(36), nullable=False),
        sa.Column("deleted_by_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("deleted_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("item_type", "notion_page_id", name="uq_trash_item"),
    )
    op.create_index("ix_trash_items_item_type", "trash_items", ["item_type"])
    op.create_index("ix_trash_items_deleted_at", "trash_items", ["deleted_at"])
    op.create_index("ix_trash_items_notion_page_id", "trash_items", ["notion_page_id"])


def downgrade() -> None:
    op.drop_index("ix_trash_items_notion_page_id", table_name="trash_items")
    op.drop_index("ix_trash_items_deleted_at", table_name="trash_items")
    op.drop_index("ix_trash_items_item_type", table_name="trash_items")
    op.drop_table("trash_items")
