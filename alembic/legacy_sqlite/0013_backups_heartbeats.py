"""backups and heartbeats (spec §21.20, §14.1)

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-14

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backups",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("backup_type", sa.String(32), nullable=False, server_default="sqlite"),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.Column("checksum", sa.String(64)),
        sa.Column("created_by", sa.String(36)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("verified_at", sa.DateTime()),
        sa.Column("error_message", sa.Text()),
    )

    op.create_table(
        "heartbeats",
        sa.Column("component", sa.String(32), primary_key=True),
        sa.Column("last_beat_at", sa.DateTime(), nullable=False),
        sa.Column("detail", sa.Text()),
    )


def downgrade() -> None:
    op.drop_table("heartbeats")
    op.drop_table("backups")
