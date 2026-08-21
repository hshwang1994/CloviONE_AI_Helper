"""schedules and schedule_runs (spec §21.13, §21.14)

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-14

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "schedules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("schedule_type", sa.String(16), nullable=False, server_default="cron"),
        sa.Column("cron_expression", sa.String(120)),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Seoul"),
        sa.Column("owner_user_id", sa.String(36)),
        sa.Column("target_type", sa.String(16), nullable=False),
        sa.Column("target_ref", sa.String(64), nullable=False),
        sa.Column("payload_template_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("prompt_id", sa.String(36)),
        sa.Column("runner_id", sa.String(36)),
        sa.Column("approval_policy_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("retry_policy_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("misfire_policy", sa.String(16), nullable=False, server_default="skip"),
        sa.Column("concurrency_policy", sa.String(16), nullable=False, server_default="skip"),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default=sa.text("180")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("start_at", sa.DateTime()),
        sa.Column("end_at", sa.DateTime()),
        sa.Column("next_run_at", sa.DateTime()),
        sa.Column("last_run_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("uq_schedules_name", "schedules", ["name"], unique=True)
    op.create_index("ix_schedules_next_run_at", "schedules", ["next_run_at"])

    op.create_table(
        "schedule_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("schedule_id", sa.String(36), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("request_payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("response_summary", sa.Text()),
        sa.Column("started_at", sa.DateTime()),
        sa.Column("finished_at", sa.DateTime()),
        sa.Column("error_message", sa.Text()),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_schedule_runs_schedule_id", "schedule_runs", ["schedule_id"])
    op.create_index(
        "uq_schedule_runs_idempotency_key",
        "schedule_runs",
        ["idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("schedule_runs")
    op.drop_table("schedules")
