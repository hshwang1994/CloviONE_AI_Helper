"""approvals and notifications (spec §21.15, §21.16)

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-14

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "approvals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("request_type", sa.String(64), nullable=False),
        sa.Column("object_type", sa.String(64), nullable=False),
        sa.Column("object_id", sa.String(64), nullable=False),
        sa.Column("requested_by", sa.String(36), nullable=False),
        sa.Column("approver_id", sa.String(36)),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("request_payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("decision_comment", sa.Text()),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime()),
        sa.Column("expires_at", sa.DateTime()),
    )
    op.create_index("ix_approvals_request_type", "approvals", ["request_type"])
    op.create_index("ix_approvals_status", "approvals", ["status"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column("read_at", sa.DateTime()),
        sa.Column("related_object_type", sa.String(64)),
        sa.Column("related_object_id", sa.String(64)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("approvals")
