"""팀 채팅 — chat_rooms / chat_room_members / chat_messages + 전체 채팅 방 시드

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-29

놀이와 같은 폴링/이벤트-시퀀스 채팅. 홈 위젯이 붙는 '전체 채팅' 방 하나를 고정 id로 시드한다.
시드 타임스탬프는 반드시 파이썬에서 만들어 파라미터로 바인딩한다(SQLite STRFTIME %f 금지 — 초를
두 번 써서 나중에 ORM isoformat 파싱이 깨진다, CLAUDE.md §8 함정).
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

_GLOBAL_ROOM_ID = "00000000-0000-0000-0000-0000cha70001"


def upgrade() -> None:
    op.create_table(
        "chat_rooms",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False, server_default="group"),
        sa.Column("title", sa.String(200), nullable=False, server_default=""),
        sa.Column("created_by_user_id", sa.String(36), nullable=True),
        sa.Column("is_global", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("dm_key", sa.String(80), nullable=True),
        sa.Column("event_seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_chat_rooms_kind", "chat_rooms", ["kind"])
    op.create_index("ix_chat_rooms_deleted_at", "chat_rooms", ["deleted_at"])
    op.create_index("uq_chat_rooms_dm_key", "chat_rooms", ["dm_key"], unique=True)

    op.create_table(
        "chat_room_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("room_id", sa.String(36), sa.ForeignKey("chat_rooms.id"), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="member"),
        sa.Column("last_read_seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("joined_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("room_id", "user_id", name="uq_chat_member"),
    )
    op.create_index("ix_chat_room_members_room_id", "chat_room_members", ["room_id"])
    op.create_index("ix_chat_room_members_user_id", "chat_room_members", ["user_id"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("room_id", sa.String(36), sa.ForeignKey("chat_rooms.id"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("sender_user_id", sa.String(36), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False, server_default="text"),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("client_message_id", sa.String(64), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("room_id", "seq", name="uq_chat_message_seq"),
    )
    op.create_index("ix_chat_messages_room_id", "chat_messages", ["room_id"])
    op.create_index("ix_chat_messages_seq", "chat_messages", ["seq"])

    # 전체 채팅 방 시드 — 타임스탬프는 파이썬에서 만들어 바인딩(STRFTIME %f 금지).
    now = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S.%f")
    op.execute(
        sa.text(
            "INSERT INTO chat_rooms (id, kind, title, is_global, dm_key, event_seq, created_at, updated_at) "
            "VALUES (:id, 'group', :title, 1, NULL, 0, :now, :now)"
        ).bindparams(id=_GLOBAL_ROOM_ID, title="전체 채팅", now=now)
    )


def downgrade() -> None:
    op.drop_index("ix_chat_messages_seq", table_name="chat_messages")
    op.drop_index("ix_chat_messages_room_id", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_chat_room_members_user_id", table_name="chat_room_members")
    op.drop_index("ix_chat_room_members_room_id", table_name="chat_room_members")
    op.drop_table("chat_room_members")
    op.drop_index("uq_chat_rooms_dm_key", table_name="chat_rooms")
    op.drop_index("ix_chat_rooms_deleted_at", table_name="chat_rooms")
    op.drop_index("ix_chat_rooms_kind", table_name="chat_rooms")
    op.drop_table("chat_rooms")
