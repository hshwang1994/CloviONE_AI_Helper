"""app_settings and document_generations (spec §21.17, §19)

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-14

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("value_type", sa.String(16), nullable=False),
        sa.Column("validation_schema_json", sa.Text()),
        sa.Column("secret_reference", sa.String(128)),
        sa.Column("restart_required", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_by", sa.String(36)),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "document_generations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("template_id", sa.String(36)),
        sa.Column("workflow_id", sa.String(36), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(300), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("preview_json", sa.Text()),
        sa.Column("quality_problems_json", sa.Text()),
        sa.Column("published_ref", sa.String(500)),
        sa.Column("error_message", sa.Text()),
        sa.Column("requested_by", sa.String(36)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "uq_document_generations_idempotency_key",
        "document_generations",
        ["idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("document_generations")
    op.drop_table("app_settings")
