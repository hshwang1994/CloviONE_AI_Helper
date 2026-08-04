"""티켓 캐시에 시작일·대분류 컬럼.

리포트(공수 집계)는 이 둘을 쓰지 않지만, **포털만으로 업무를 끝내려면** 화면에서 편집할 수
있어야 하고 그러려면 미러에도 있어야 한다(2026-08-04 제품화 지시). 실제 노션 데이터에서
시작일은 22%, 대분류는 4% 의 티켓이 값을 갖고 있다 — 안 쓰는 필드가 아니다.

Revision ID: 0036
Revises: 0035
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ticket_cache") as batch:
        batch.add_column(sa.Column("start_date", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("category", sa.String(length=200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ticket_cache") as batch:
        batch.drop_column("category")
        batch.drop_column("start_date")
