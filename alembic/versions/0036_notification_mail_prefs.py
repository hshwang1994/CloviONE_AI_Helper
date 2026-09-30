"""user_preferences.mail_enabled · mail_types — 알림을 메일로도 받기 (계획 3.4, D-514).

Revision ID: 0036_notification_mail_prefs
Revises: 0035_ticket_requester

기본은 꺼짐이다. 켜 둔 사람만 메일을 받는다(스스로 고른다). `mail_types` 는 NULL 로 두어 「아직 고르지 않음」을
나타낸다 - 그 사람은 관리자가 허용한 유형을 전부 받는다. 되채울 값은 없다.

되돌리면 두 칸을 지운다(사용자가 고른 값도 함께 사라진다).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0036_notification_mail_prefs"
down_revision = "0035_ticket_requester"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_preferences",
        sa.Column("mail_enabled", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.add_column("user_preferences", sa.Column("mail_types", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_preferences", "mail_types")
    op.drop_column("user_preferences", "mail_enabled")
