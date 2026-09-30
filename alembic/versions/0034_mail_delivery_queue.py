"""mail_deliveries — 재시도 상태와 멱등 열쇠, 실패 종류 (계획 3.3).

Revision ID: 0034_mail_delivery_queue
Revises: 0033_project_org_backfill

상태 열은 문자열이라(`String(16)`, 제약 없음) 새 상태(`retrying` · `cancelled` · `superseded`)는 DDL 이
필요 없다. 더하는 것은 열 넷과 인덱스 둘이다:

  * `idempotency_key` - 같은 사건이 메일을 두 번 만들지 않게 한다(유일, NULL 허용).
  * `message_id`      - 보낸 메일의 `Message-ID`.
  * `failure_kind`    - 실패의 종류(인증 · 보안 연결 · 받는 사람 거부 · 연결 · 임시 거절 …).
  * `skip_reason`     - 보내지 않은 까닭.
  * `(status, created_at)` 인덱스 - 발송 기록 목록과 보존 정리가 상태로 거른다.

## 옛 행

`failed` 로 남은 옛 행은 그대로 둔다. 그중 일부는 재시도가 남아 있었을 수 있지만, 옛 잡은 이미 끝났고
그 사실을 되살릴 근거가 없다. 대기 중인 옛 `queued` 행도 그대로다 - 워커가 옛 잡을 계속 처리한다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0034_mail_delivery_queue"
down_revision = "0033_project_org_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mail_deliveries", sa.Column("idempotency_key", sa.String(200), nullable=True))
    op.add_column("mail_deliveries", sa.Column("message_id", sa.String(300), nullable=True))
    op.add_column("mail_deliveries", sa.Column("failure_kind", sa.String(32), nullable=True))
    op.add_column("mail_deliveries", sa.Column("skip_reason", sa.String(64), nullable=True))
    op.create_unique_constraint(
        "uq_mail_deliveries_idempotency_key", "mail_deliveries", ["idempotency_key"]
    )
    op.create_index(
        "ix_mail_deliveries_status_created", "mail_deliveries", ["status", "created_at"]
    )


def downgrade() -> None:
    # 새 상태로 남은 행을 옛 어휘로 되돌린다. 옛 앱은 `retrying` 을 모른다 - 모르는 상태는 화면에
    # 이름 없이 나오고 보존 정리에서도 빠진다. 끝나지 않은 재시도는 `queued`(워커가 잡을 계속 돈다),
    # 보내지 않은 두 상태는 `failed` 로 둔다(사람에게는 둘 다 「안 온 메일」이다).
    op.execute("UPDATE mail_deliveries SET status = 'queued' WHERE status = 'retrying'")
    op.execute("UPDATE mail_deliveries SET status = 'failed' WHERE status IN ('cancelled', 'superseded')")
    op.drop_index("ix_mail_deliveries_status_created", table_name="mail_deliveries")
    op.drop_constraint("uq_mail_deliveries_idempotency_key", "mail_deliveries", type_="unique")
    op.drop_column("mail_deliveries", "skip_reason")
    op.drop_column("mail_deliveries", "failure_kind")
    op.drop_column("mail_deliveries", "message_id")
    op.drop_column("mail_deliveries", "idempotency_key")
