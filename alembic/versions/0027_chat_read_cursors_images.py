"""팀 채팅 완성도 — chat_read_cursors / chat_message_images (PLAN §D)

Revision ID: 0027
Revises: 0024
Create Date: 2026-08-03

두 표를 더한다.

1. `chat_read_cursors(user_id, room_id, last_read_seq, hidden_at, updated_at)`
   — 멤버십 행이 없는 방(전체 채팅)의 개인별 안읽음과, 1:1 '나에게만 숨김'.
   전체 채팅에 `chat_room_members` 행을 게으르게 만들지 않는 이유: 그러면
   `_room_summary.member_count` 의 뜻이 '멤버 수'에서 '한 번이라도 연 사람 수'로 조용히
   바뀐다. 이 표는 **읽을 때만** 쓰인다(폴링은 절대 쓰지 않는다).

2. `chat_message_images(message_id, room_id, filename, stored_name, media_type, size_bytes)`
   — 붙여넣기 이미지. 파일은 `data_dir/uploads/team_chat/<room_id>/` 아래에 있고, 서빙은
   방 접근 검사를 하는 `GET /api/team-chat/messages/{mid}/images/{iid}` 만 한다
   (게시판 첨부 라우트를 재사용하면 1:1 DM 이미지가 전사 공개가 된다).

시드 없음 — 새 표 두 개뿐이라 타임스탬프 함정(CLAUDE.md §8, SQLite STRFTIME '%f')에
걸릴 일이 없다. downgrade 는 두 표를 그대로 되돌린다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027"
# 병합 시점의 실제 head 에 붙인다. 머리가 둘이면 `alembic upgrade head` 가
# "Multiple head revisions are present" 로 죽는다 — 배포 실패다.
# 0025/0026 이 나중에 들어오면 이 값을 그 새 head 로 올려야 한다.
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_read_cursors",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("room_id", sa.String(36), sa.ForeignKey("chat_rooms.id"), nullable=False),
        sa.Column("last_read_seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hidden_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "room_id", name="uq_chat_read_cursor"),
    )
    op.create_index("ix_chat_read_cursors_user_id", "chat_read_cursors", ["user_id"])
    op.create_index("ix_chat_read_cursors_room_id", "chat_read_cursors", ["room_id"])

    op.create_table(
        "chat_message_images",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("message_id", sa.String(36), sa.ForeignKey("chat_messages.id"), nullable=False),
        sa.Column("room_id", sa.String(36), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("stored_name", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_chat_message_images_message_id", "chat_message_images", ["message_id"])
    op.create_index("ix_chat_message_images_room_id", "chat_message_images", ["room_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_message_images_room_id", table_name="chat_message_images")
    op.drop_index("ix_chat_message_images_message_id", table_name="chat_message_images")
    op.drop_table("chat_message_images")
    op.drop_index("ix_chat_read_cursors_room_id", table_name="chat_read_cursors")
    op.drop_index("ix_chat_read_cursors_user_id", table_name="chat_read_cursors")
    op.drop_table("chat_read_cursors")
