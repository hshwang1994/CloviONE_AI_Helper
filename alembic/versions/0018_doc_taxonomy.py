"""문서 분류 개편 (§17) — document_cache 에 신규 택소노미 컬럼 추가

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-28

document_type(문서 종류)·work_field(업무 분야)·tech_tags(기술 태그)·classification_manual 를
캐시에 추가한다. 값은 배포 후 다음 동기화(즉시 tick)가 app/team_docs/classify.py로 자동
채운다 — 데이터 백필 불필요, 멱등. downgrade는 컬럼만 드롭한다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("document_cache") as batch:
        batch.add_column(sa.Column("document_type", sa.String(32), nullable=True))
        batch.add_column(sa.Column("work_field", sa.String(32), nullable=True))
        batch.add_column(sa.Column("tech_tags", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("classification_manual", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.create_index("ix_document_cache_document_type", "document_cache", ["document_type"])
    op.create_index("ix_document_cache_work_field", "document_cache", ["work_field"])


def downgrade() -> None:
    op.drop_index("ix_document_cache_work_field", table_name="document_cache")
    op.drop_index("ix_document_cache_document_type", table_name="document_cache")
    with op.batch_alter_table("document_cache") as batch:
        batch.drop_column("classification_manual")
        batch.drop_column("tech_tags")
        batch.drop_column("work_field")
        batch.drop_column("document_type")
