"""0048 — 로컬 릴레이의 바깥 전달 추적 (계획 M7, D-551 · D-555).

## 무엇을 더하는가

`mail_deliveries` 에 로컬 릴레이로 넘긴 메일의 바깥 결과 칸을 더한다. 외부 SMTP 로 보낸 행과 옛 행은 모두 비어 있다(그 메일은 「메일
서버가 접수함」까지가 제품이 아는 전부다).

- `relay_queue_id` — 릴레이가 준 큐 id(`250 … queued as X`). 추적이 이 id 로 큐와 로그를 읽는다.
- `relay_delivery` — 넘길 때의 전달 방식(smarthost · direct). 나중에 방식을 바꿔도 옛 행의 낱말이 틀리지 않게 행에 남긴다.
- `remote_status` — queued · deferred · delivered · bounced · expired · unknown.
- `remote_stage` · `remote_detail` — 막힌 단계(dns · connect · tls · rejected · temporary · expired)와 받는 쪽이 말한 문장(300자).
- `remote_checked_at` — 마지막으로 본 시각.

아직 끝나지 않은 행(queued · deferred)만 담는 부분 색인을 둔다 - 추적이 1분마다 그 행만 읽는다.

## 되돌리기

색인과 칸을 지운다. 로컬 릴레이로 보낸 메일의 바깥 결과를 잃는다(메일 자체는 이미 나갔다).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0048_mail_relay_tracking"
down_revision = "0047_notify_email"
branch_labels = None
depends_on = None

PENDING_INDEX = "ix_mail_deliveries_remote_pending"


def upgrade() -> None:
    op.add_column("mail_deliveries", sa.Column("relay_queue_id", sa.String(32), nullable=True))
    op.add_column("mail_deliveries", sa.Column("relay_delivery", sa.String(16), nullable=True))
    op.add_column("mail_deliveries", sa.Column("remote_status", sa.String(16), nullable=True))
    op.add_column("mail_deliveries", sa.Column("remote_stage", sa.String(16), nullable=True))
    op.add_column("mail_deliveries", sa.Column("remote_detail", sa.Text(), nullable=True))
    op.add_column("mail_deliveries", sa.Column("remote_checked_at", sa.DateTime(), nullable=True))
    op.create_index(
        PENDING_INDEX, "mail_deliveries", ["remote_status", "sent_at"],
        postgresql_where=sa.text("remote_status IN ('queued', 'deferred')"),
    )


def downgrade() -> None:
    op.drop_index(PENDING_INDEX, table_name="mail_deliveries")
    for column in ("remote_checked_at", "remote_detail", "remote_stage", "remote_status", "relay_delivery",
                   "relay_queue_id"):
        op.drop_column("mail_deliveries", column)
