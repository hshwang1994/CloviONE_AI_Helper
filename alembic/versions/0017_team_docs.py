"""팀 공간 > 문서 (§17) — document_cache / document_sync_state / document_favorites / document_recent_views

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-28

신규 테이블만 추가(기존 스키마 무접촉). document_cache 는 Notion "문서" DB의 로컬 미러라
동기화로 언제든 재생성되는 파생 데이터다 — downgrade로 통째 드롭해도 원본(Notion)은 안전하다.
즐겨찾기/최근열람은 사용자 데이터라 백업 대상.
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_cache",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("notion_page_id", sa.String(64), nullable=False),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("title", sa.String(500), nullable=False, server_default=""),
        sa.Column("type_names", sa.Text(), nullable=False, server_default=""),
        sa.Column("category_names", sa.Text(), nullable=False, server_default=""),
        sa.Column("project_names", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(64), nullable=True),
        sa.Column("priority", sa.String(64), nullable=True),
        sa.Column("author_names", sa.Text(), nullable=False, server_default=""),
        sa.Column("owner", sa.String(255), nullable=False, server_default=""),
        sa.Column("doc_date", sa.String(40), nullable=True),
        sa.Column("orig_date", sa.String(40), nullable=True),
        sa.Column("created_time", sa.String(40), nullable=True),
        sa.Column("last_edited", sa.String(40), nullable=True),
        sa.Column("original_url", sa.String(1000), nullable=True),
        sa.Column("source_url", sa.String(1000), nullable=True),
        sa.Column("memo", sa.Text(), nullable=False, server_default=""),
        sa.Column("has_files", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("notion_favorite", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("synced_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_document_cache_notion_page_id", "document_cache", ["notion_page_id"], unique=True)
    op.create_index("ix_document_cache_status", "document_cache", ["status"])
    op.create_index("ix_document_cache_archived", "document_cache", ["archived"])

    op.create_table(
        "document_sync_state",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="idle"),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("doc_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    # 싱글턴 sync-state 행을 미리 심는다. 없으면 첫 조회/동기화가 insert-if-absent를 하다가
    # 동시 요청에서 유니크 충돌(500)이 나거나, 첫 flush로 WAL writer 락을 Notion HTTP 내내
    # 붙잡아 다른 쓰기가 'database is locked'로 실패할 수 있다(검수 결함). timestamp는
    # Python에서 만든다(CLAUDE.md §8: SQLite STRFTIME의 %f 함정 회피).
    _now = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S.%f")
    op.execute(
        sa.text(
            "INSERT INTO document_sync_state (id, status, doc_count, updated_at)"
            " VALUES ('documents', 'idle', 0, :now)"
        ).bindparams(now=_now)
    )

    op.create_table(
        "document_favorites",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("notion_page_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "notion_page_id", name="uq_doc_favorite"),
    )
    op.create_index("ix_document_favorites_user_id", "document_favorites", ["user_id"])

    op.create_table(
        "document_recent_views",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("notion_page_id", sa.String(64), nullable=False),
        sa.Column("viewed_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "notion_page_id", name="uq_doc_recent"),
    )
    op.create_index("ix_document_recent_views_user_id", "document_recent_views", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_document_recent_views_user_id", table_name="document_recent_views")
    op.drop_table("document_recent_views")
    op.drop_index("ix_document_favorites_user_id", table_name="document_favorites")
    op.drop_table("document_favorites")
    op.drop_table("document_sync_state")
    op.drop_index("ix_document_cache_archived", table_name="document_cache")
    op.drop_index("ix_document_cache_status", table_name="document_cache")
    op.drop_index("ix_document_cache_notion_page_id", table_name="document_cache")
    op.drop_table("document_cache")
