"""integrations and config_versions tables (spec §21.7, §21.18)

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-14

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integrations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("provider_type", sa.String(32), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("health_url", sa.String(500)),
        sa.Column("auth_type", sa.String(32), nullable=False, server_default="none"),
        sa.Column("secret_ref", sa.String(128)),
        sa.Column("capabilities_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "last_health_status", sa.String(16), nullable=False, server_default="unknown"
        ),
        sa.Column("last_health_at", sa.DateTime()),
        sa.Column("config_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_integrations_name", "integrations", ["name"], unique=True)

    op.create_table(
        "config_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("object_type", sa.String(64), nullable=False),
        sa.Column("object_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(36)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_config_versions_object_type", "config_versions", ["object_type"])
    op.create_index("ix_config_versions_object_id", "config_versions", ["object_id"])
    op.create_index(
        "uq_config_versions_object_version",
        "config_versions",
        ["object_type", "object_id", "version"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("config_versions")
    op.drop_table("integrations")
