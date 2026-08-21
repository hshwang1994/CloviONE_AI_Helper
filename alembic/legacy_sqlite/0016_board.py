"""자유게시판 (팀 공간 §18) — board_posts / board_comments / board_reactions / board_attachments

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-28

신규 테이블만 추가한다(기존 스키마 무접촉). 게시글·댓글은 soft delete(deleted_at)로
되돌릴 수 있게 남긴다. 반응은 (대상종류, 대상id, 사용자, 이모지) 유니크로 중복을 막고,
첨부는 메타만 저장한다(실제 파일은 data_dir/uploads/board/<post_id>/).

downgrade는 네 테이블을 통째로 드롭한다 — 게시판 데이터가 사라진다(신규 기능이라 담을
이전 스키마가 없다). 배포 전 백업이 있으므로 롤백은 백업 복원과 함께 한다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "board_posts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "author_user_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "is_pinned", sa.Boolean(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "view_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_board_posts_author_user_id", "board_posts", ["author_user_id"])
    op.create_index("ix_board_posts_category", "board_posts", ["category"])
    op.create_index("ix_board_posts_is_pinned", "board_posts", ["is_pinned"])
    op.create_index("ix_board_posts_deleted_at", "board_posts", ["deleted_at"])

    op.create_table(
        "board_comments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "post_id",
            sa.String(36),
            sa.ForeignKey("board_posts.id"),
            nullable=False,
        ),
        sa.Column(
            "author_user_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "parent_comment_id",
            sa.String(36),
            sa.ForeignKey("board_comments.id"),
            nullable=True,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_board_comments_post_id", "board_comments", ["post_id"])
    op.create_index(
        "ix_board_comments_author_user_id", "board_comments", ["author_user_id"]
    )
    op.create_index(
        "ix_board_comments_parent_comment_id", "board_comments", ["parent_comment_id"]
    )
    op.create_index("ix_board_comments_deleted_at", "board_comments", ["deleted_at"])

    op.create_table(
        "board_reactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("target_type", sa.String(16), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("emoji", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "target_type", "target_id", "user_id", "emoji", name="uq_board_reaction"
        ),
    )
    op.create_index("ix_board_reactions_target_id", "board_reactions", ["target_id"])

    op.create_table(
        "board_attachments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "post_id",
            sa.String(36),
            sa.ForeignKey("board_posts.id"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("stored_name", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_board_attachments_post_id", "board_attachments", ["post_id"])


def downgrade() -> None:
    op.drop_index("ix_board_attachments_post_id", table_name="board_attachments")
    op.drop_table("board_attachments")
    op.drop_index("ix_board_reactions_target_id", table_name="board_reactions")
    op.drop_table("board_reactions")
    op.drop_index("ix_board_comments_deleted_at", table_name="board_comments")
    op.drop_index("ix_board_comments_parent_comment_id", table_name="board_comments")
    op.drop_index("ix_board_comments_author_user_id", table_name="board_comments")
    op.drop_index("ix_board_comments_post_id", table_name="board_comments")
    op.drop_table("board_comments")
    op.drop_index("ix_board_posts_deleted_at", table_name="board_posts")
    op.drop_index("ix_board_posts_is_pinned", table_name="board_posts")
    op.drop_index("ix_board_posts_category", table_name="board_posts")
    op.drop_index("ix_board_posts_author_user_id", table_name="board_posts")
    op.drop_table("board_posts")
