"""users and sessions tables (spec §21.1, §21.3)

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-14

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("department", sa.String(120)),
        sa.Column("title", sa.String(120)),
        sa.Column("role", sa.String(32), nullable=False, server_default="user"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "failed_login_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("locked_until", sa.DateTime()),
        sa.Column("created_by", sa.String(36)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_login_at", sa.DateTime()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime()),
        sa.Column("client_ip", sa.String(64)),
        sa.Column("user_agent", sa.String(255)),
    )
    op.create_index("ix_sessions_token_hash", "sessions", ["token_hash"], unique=True)
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])


def downgrade() -> None:
    op.drop_table("sessions")
    op.drop_table("users")
