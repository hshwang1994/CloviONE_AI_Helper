"""AI 채팅 메시지에 삭제(soft delete)·피드백 컬럼 추가 (AI-36/AI-68)

메시지 삭제·재생성·피드백(👍/👎) 기능을 위한 스키마. 재생성은 새로 만들지 않고
"삭제된 이전 답변 + 새 잡 재큐잉"으로 구현한다(retry_message가 이미 쓰는 것과 같은
enqueue 경로) — deleted_at 하나로 삭제와 재생성 둘 다 지원한다.

board/team_chat의 기존 deleted_at(DateTime, index=True) 관례를 그대로 따른다.
`list_messages`가 `deleted_at IS NULL`로 거르므로 이 컬럼에 index를 둔다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("messages")}
    if "deleted_at" not in cols:
        op.add_column("messages", sa.Column("deleted_at", sa.DateTime()))
        op.create_index("ix_messages_deleted_at", "messages", ["deleted_at"])
    if "feedback" not in cols:
        op.add_column("messages", sa.Column("feedback", sa.String(16)))


def downgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("messages")}
    if "feedback" in cols:
        op.drop_column("messages", "feedback")
    if "deleted_at" in cols:
        op.drop_index("ix_messages_deleted_at", table_name="messages")
        op.drop_column("messages", "deleted_at")
