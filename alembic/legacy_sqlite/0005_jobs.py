"""jobs table (spec §21.6)

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-14

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(36)),
        sa.Column("conversation_id", sa.String(36)),
        sa.Column("message_id", sa.String(64)),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("idempotency_key", sa.String(200)),
        sa.Column("available_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime()),
        sa.Column("finished_at", sa.DateTime()),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_jobs_job_type", "jobs", ["job_type"])
    op.create_index("ix_jobs_user_id", "jobs", ["user_id"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_available_at", "jobs", ["available_at"])
    op.create_index("uq_jobs_idempotency_key", "jobs", ["idempotency_key"], unique=True)
    op.create_index("ix_jobs_claim", "jobs", ["status", "available_at", "created_at"])


def downgrade() -> None:
    op.drop_table("jobs")
