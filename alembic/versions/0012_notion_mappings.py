"""user_notion_mappings (spec §21.2)

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-14

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_notion_mappings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("notion_user_id", sa.String(64)),
        sa.Column("notion_email", sa.String(255)),
        sa.Column("status", sa.String(16), nullable=False, server_default="unmapped"),
        sa.Column("source", sa.String(16)),
        sa.Column("last_verified_at", sa.DateTime()),
        sa.Column("error_message", sa.Text()),
        sa.Column("candidates_json", sa.Text()),
    )
    op.create_index(
        "uq_user_notion_mappings_user_id", "user_notion_mappings", ["user_id"], unique=True
    )


def downgrade() -> None:
    op.drop_table("user_notion_mappings")
