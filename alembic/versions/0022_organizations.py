"""organizations — 테넌트 1급 엔티티 + 기본 조직 1행 시드 (§7.1.A / §7.3)

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-03

**읽는 코드가 하나도 없는 마이그레이션이다.** 기존 테이블을 건드리지 않고 새 테이블 하나만
만들고 한 행을 시드한다 — 그래서 이 단계에서 앱 동작은 100% 그대로여야 하고, API 골든 회귀가
바이트 단위로 그대로 통과해야 한다. 다음 단계(0023 ticket_cache)의 org_id FK 가 이 테이블을
필요로 해서 먼저 온다.

타임스탬프는 반드시 파이썬 datetime 으로 만들어 파라미터로 바인딩한다(SQLite STRFTIME '%f'
금지 — 초를 두 번 써 넣어 나중에 ORM isoformat 파싱이 깨진다, CLAUDE.md §8 함정).
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

# app/org/constants.py 와 같은 값이어야 한다(거기가 정본, 여기는 마이그레이션이라 import 대신
# 값을 못박는다 — 상수 모듈이 나중에 바뀌어도 이미 적용된 마이그레이션은 불변이어야 하므로).
_DEFAULT_ORG_ID = "00000000-0000-0000-0000-00000000org1"
_DEFAULT_ORG_SLUG = "default"
_DEFAULT_ORG_NAME = "ClovirONE"


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("settings_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    op.get_bind().execute(
        sa.text(
            "INSERT INTO organizations (id, slug, name, status, created_at, updated_at)"
            " VALUES (:id, :slug, :name, 'active', :now, :now)"
        ).bindparams(
            id=_DEFAULT_ORG_ID, slug=_DEFAULT_ORG_SLUG, name=_DEFAULT_ORG_NAME, now=now
        )
    )


def downgrade() -> None:
    op.drop_index("ix_organizations_slug", table_name="organizations")
    op.drop_table("organizations")
