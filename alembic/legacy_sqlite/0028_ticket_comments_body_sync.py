"""ticket_comments + 티켓 본문 동기화 상태 (PLAN Phase 3 §E)

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-03

두 가지를 더한다.

1. `ticket_comments(ticket_uid → ticket_cache.id, author_user_id, body, deleted_at)`
   — 티켓 댓글. **FK 대상은 `ticket_cache.id`(자체 UUID)이지 Notion page id 가 아니다.**
   0023 으로 티켓 캐시를 만든 이유 중 하나가 이것이다: 내부 참조가 외부 시스템 식별자에
   묶여 있으면 소스를 바꾸는 순간 댓글이 전부 고아가 된다.
   ON DELETE CASCADE — Notion 에서 티켓이 사라지면 `sync._prune` 이 캐시 행을 지우는데,
   FK 가 걸린 댓글이 남아 있으면 그 DELETE 가 실패하고 sync 는 예외를 삼키므로 티켓
   미러 전체가 조용히 멈춘다(SQLite 는 PRAGMA foreign_keys=ON 으로 돌린다).

2. `ticket_cache.body_synced_at` / `ticket_cache.body_sync_error`
   — 본문 저장은 **정본(body_markdown) 먼저, Notion push 는 그다음** 순서로 한다. 그래야
   Notion 이 죽어도 사용자가 친 글이 남는다. 그 대신 '저장은 됐지만 원본과 어긋난' 상태가
   생기므로 여기에 기록해 두고 상세 화면이 배너로 보여준다(조용히 성공한 척하지 않는다).

시드 없음 — 새 표 하나와 nullable 컬럼 둘뿐이라 타임스탬프 함정(CLAUDE.md §8, SQLite
STRFTIME '%f' 금지)에 걸릴 일이 없다. downgrade 는 표를 지우고 컬럼 둘을 되돌린다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ticket_comments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "ticket_uid",
            sa.String(36),
            sa.ForeignKey("ticket_cache.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("author_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        # soft-delete. 목록 API 는 삭제된 댓글도 본문 없는 툼스톤으로 계속 돌려준다 —
        # 이미 목록을 받아 둔 클라이언트가 '사라짐'이 아니라 '삭제됨'을 볼 수 있어야 한다.
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_ticket_comments_ticket_uid", "ticket_comments", ["ticket_uid"])
    op.create_index("ix_ticket_comments_author_user_id", "ticket_comments", ["author_user_id"])
    op.create_index("ix_ticket_comments_deleted_at", "ticket_comments", ["deleted_at"])

    op.add_column("ticket_cache", sa.Column("body_synced_at", sa.DateTime(), nullable=True))
    op.add_column("ticket_cache", sa.Column("body_sync_error", sa.Text(), nullable=True))


def downgrade() -> None:
    # 컬럼 둘은 인덱스도 제약도 걸려 있지 않아 SQLite 의 ALTER TABLE DROP COLUMN 으로 지워진다
    # (3.35+, 이 저장소는 3.45). batch_alter_table 로 표를 재생성하면 오히려 컬럼 순서·기본값이
    # 조용히 달라져 왕복 리허설(scripts/migration_rehearsal.sh)이 잡아내는 종류의 표류가 생긴다.
    op.drop_column("ticket_cache", "body_sync_error")
    op.drop_column("ticket_cache", "body_synced_at")

    op.drop_index("ix_ticket_comments_deleted_at", table_name="ticket_comments")
    op.drop_index("ix_ticket_comments_author_user_id", table_name="ticket_comments")
    op.drop_index("ix_ticket_comments_ticket_uid", table_name="ticket_comments")
    op.drop_table("ticket_comments")
