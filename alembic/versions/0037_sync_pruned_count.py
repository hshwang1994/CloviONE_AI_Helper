"""동기화 상태에 prune 삭제 건수(드리프트 지표).

지금까지 prune 이 몇 건을 지웠는지 **세지도 남기지도 않았다**. 그래서 캐시가 2000 → 0 이 되어도
상태에는 `{status: "ok", item_count: 0}` 만 남아, 운영자가 "동기화는 정상인데 티켓이 없다"를
구분할 근거가 없었다. 삭제 건수를 남기면 그 한 줄이 드리프트 탐지의 시작점이 된다.

`core.sync_prune` 의 바닥이 삭제를 거부한 경우 이 값은 0 이고 status 가 SYNC_ERROR 가 된다 —
"0건 지웠다"와 "지우려다 막았다"는 error 문구로 구분된다.

Revision ID: 0037
Revises: 0036
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("ticket_sync_state", "document_sync_state"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(
                sa.Column(
                    "pruned_count",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                )
            )


def downgrade() -> None:
    for table in ("document_sync_state", "ticket_sync_state"):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("pruned_count")
