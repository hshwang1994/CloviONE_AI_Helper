"""팀 공간 > 놀이 (§5·§13·§20) — game_rooms / game_room_members / game_events

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-28

폴링 기반 게임방 인프라. 이벤트는 방별 순번(seq)으로 쌓인다. 게임 데이터는 방이 끝나고
정리되므로(§16.1) 장기 보존 대상 아님 — downgrade는 세 테이블을 드롭한다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "game_rooms",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("game_type", sa.String(32), nullable=False),
        sa.Column("host_user_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="waiting"),
        sa.Column("max_players", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("allow_spectators", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("state_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("event_seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_game_rooms_host_user_id", "game_rooms", ["host_user_id"])
    op.create_index("ix_game_rooms_status", "game_rooms", ["status"])
    op.create_index("ix_game_rooms_closed_at", "game_rooms", ["closed_at"])

    op.create_table(
        "game_room_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("room_id", sa.String(36), sa.ForeignKey("game_rooms.id"), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False, server_default=""),
        sa.Column("role", sa.String(16), nullable=False, server_default="player"),
        sa.Column("ready", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("last_seen", sa.DateTime(), nullable=False),
        sa.Column("joined_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("room_id", "user_id", name="uq_game_member"),
    )
    op.create_index("ix_game_room_members_room_id", "game_room_members", ["room_id"])

    op.create_table(
        "game_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("room_id", sa.String(36), sa.ForeignKey("game_rooms.id"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("actor_user_id", sa.String(36), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("room_id", "seq", name="uq_game_event_seq"),
    )
    op.create_index("ix_game_events_room_id", "game_events", ["room_id"])
    op.create_index("ix_game_events_seq", "game_events", ["seq"])


def downgrade() -> None:
    op.drop_index("ix_game_events_seq", table_name="game_events")
    op.drop_index("ix_game_events_room_id", table_name="game_events")
    op.drop_table("game_events")
    op.drop_index("ix_game_room_members_room_id", table_name="game_room_members")
    op.drop_table("game_room_members")
    op.drop_index("ix_game_rooms_closed_at", table_name="game_rooms")
    op.drop_index("ix_game_rooms_status", table_name="game_rooms")
    op.drop_index("ix_game_rooms_host_user_id", table_name="game_rooms")
    op.drop_table("game_rooms")
