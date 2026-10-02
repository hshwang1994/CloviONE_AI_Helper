"""0047 — 알림 받을 메일 주소와 주소 확인 (계획 M4, D-550).

## 무엇을 더하는가

- `user_preferences.notify_email` · `notify_email_verified_at` — 확인을 마친 알림 주소와 그 시각. 둘 다 비어 있으면 계정 주소로 받는다
  (모든 기존 사용자의 값이다 - 고르기 전까지 동작이 같다).
- `mail_address_verifications` — 주소 확인 한 건. 코드는 저장하지 않고 HMAC(`code_hash`)만 둔다. 코드는 워커가 메일을 그릴 때
  만들어지므로 처음에는 `code_hash` · `code_sent_at` · `expires_at` 이 비어 있다. 한 사람 · 한 목적에 열린 확인은 하나다(부분 유일 색인).

## 되돌리기

열과 표를 지운다. 확인한 다른 주소를 잃으므로 그 사람들은 계정 주소로 받는다(업그레이드 스냅숏이 복구 길이다, D-524).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0047_notify_email"
down_revision = "0046_ai_legacy_cleanup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_preferences", sa.Column("notify_email", sa.String(320), nullable=True))
    op.add_column("user_preferences", sa.Column("notify_email_verified_at", sa.DateTime(), nullable=True))
    op.create_table(
        "mail_address_verifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=True),
        sa.Column("code_sent_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("delivery_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_mail_address_verifications_user", "mail_address_verifications", ["user_id", "created_at"])
    op.create_index(
        "ux_mail_address_verifications_open", "mail_address_verifications", ["user_id", "purpose"], unique=True,
        postgresql_where=sa.text("consumed_at IS NULL AND cancelled_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_mail_address_verifications_open", table_name="mail_address_verifications")
    op.drop_index("ix_mail_address_verifications_user", table_name="mail_address_verifications")
    op.drop_table("mail_address_verifications")
    op.drop_column("user_preferences", "notify_email_verified_at")
    op.drop_column("user_preferences", "notify_email")
