"""runners and workflows tables (spec §21.8, §21.9)

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-14

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runners",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("integration_id", sa.String(36)),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("provider_type", sa.String(32), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("health_url", sa.String(500)),
        sa.Column("version", sa.String(64)),
        sa.Column("capabilities_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("auth_type", sa.String(32), nullable=False, server_default="none"),
        sa.Column("secret_ref", sa.String(128)),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default=sa.text("60")),
        sa.Column("concurrency_limit", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("retry_policy_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("maintenance_state", sa.String(16), nullable=False, server_default="normal"),
        sa.Column("last_health_status", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("last_health_at", sa.DateTime()),
        sa.Column("config_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("owner", sa.String(120)),
        sa.Column("tags_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("circuit_open_until", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_runners_name", "runners", ["name"], unique=True)

    op.create_table(
        "workflows",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("purpose", sa.Text()),
        sa.Column("webhook_url", sa.String(500), nullable=False),
        sa.Column("http_method", sa.String(8), nullable=False, server_default="POST"),
        sa.Column("payload_schema_json", sa.Text()),
        sa.Column("response_schema_json", sa.Text()),
        sa.Column("operation_mode", sa.String(8), nullable=False, server_default="read"),
        sa.Column("approval_required", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("owner", sa.String(120)),
        sa.Column("tags_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("last_test_status", sa.String(16)),
        sa.Column("last_test_at", sa.DateTime()),
        sa.Column("config_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_workflows_name", "workflows", ["name"], unique=True)


def downgrade() -> None:
    op.drop_table("workflows")
    op.drop_table("runners")
