"""users.archived_at — 계정 '보관'(삭제 대신 감추기)

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-16

계정을 정말 삭제하면 감사 로그가 가리키는 행위자(user_id)가 사라져 "누가 했는지"가
빈칸이 된다. 그래서 행은 남기고 목록·검색·로그인에서만 빼는 archived_at을 둔다.
NULL = 살아 있는 계정, 값 = 그 시각에 보관됨.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("archived_at", sa.DateTime(), nullable=True))
    # 기본 목록은 archived_at IS NULL로 거른다 — 전 사용자 조회마다 타는 조건이다.
    op.create_index("ix_users_archived_at", "users", ["archived_at"])


def downgrade() -> None:
    op.drop_index("ix_users_archived_at", table_name="users")
    op.drop_column("users", "archived_at")
