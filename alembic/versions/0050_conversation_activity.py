"""0050 — AI 도우미 대화의 마지막 대화 시각 (AI 채팅 개선 회차).

## 무엇을 더하는가

`conversations.last_message_at` — 그 대화에 마지막으로 메시지가 생긴 시각(Z 없는 UTC). 대화 목록은 이 값(없으면 만든 시각)으로
정렬하고 행의 시각도 이 값을 보인다. 예전에는 `updated_at` 으로 정렬해, 이름을 바꾸거나 보관만 해도 그 대화가 맨 위로 올라갔다.
보존 기한은 지금처럼 `updated_at` 을 본다(이 칸은 정렬과 표시용이다).

백필은 지우지 않은 메시지의 가장 늦은 `created_at`, 메시지가 없으면 대화를 만든 시각이다.

## 되돌리기

칸을 지운다. 메시지에서 다시 셀 수 있는 값이라 잃는 것이 없다.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "0050_conversation_activity"
down_revision = "0049_celebration_pref"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.0050")


def upgrade() -> None:
    op.add_column("conversations", sa.Column("last_message_at", sa.DateTime(), nullable=True))
    result = op.get_bind().execute(sa.text(
        "UPDATE conversations c SET last_message_at = coalesce("
        "(SELECT max(m.created_at) FROM messages m WHERE m.conversation_id = c.id AND m.deleted_at IS NULL), "
        "c.created_at)"
    ))
    logger.info("0050: 대화 %s개에 마지막 대화 시각을 채웠다", result.rowcount)


def downgrade() -> None:
    op.drop_column("conversations", "last_message_at")
