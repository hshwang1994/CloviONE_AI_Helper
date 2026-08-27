"""문서 휴지통 — 「누가 언제 버렸는가」가 없어서 되살릴 수도 없었다.

Revision ID: 0021_document_trash
Revises: 0020_sprint_decisions
Create Date: 2026-08-27

## 무엇이 문제였나

문서를 지우면 행이 사라지는 것이 아니라 `documents.archived` 가 선다. 그것 자체는 옳다 —
행을 지우면 판·멘션·관계가 CASCADE 로 함께 사라지고 셋 다 재계산으로 안 돌아온다.

문제는 그 뒤였다. 보관된 문서를 다시 보여 주는 화면이 없었고, `archived` 를 다시 내리는
API 도 없었다. 즉 **문서 삭제는 되돌릴 수 없었다** — 화면에는 「휴지통」 버튼이 있었지만
그 휴지통은 옛 Notion 미러(`document_cache`)의 것이라 Native 문서는 애초에 거기 안 들어간다.

## 왜 `trash_items` 에 넣지 않는가

공용 휴지통 표는 `notion_page_id` 를 not-null 유일키로 쓴다. Native 문서에는 그런 id 가
없고, 만들어 넣으면 없는 개념을 지어내는 것이 된다. 지시 22.7 도 「Legacy `trash_items`/
Notion page id 구조를 Native Knowledge 복원의 정본으로 쓰지 말라」고 적었다.

정본은 `documents.archived` 하나다. 여기서 더하는 것은 그 사실에 **누가 · 언제**를 붙이는
칸 둘뿐이다. 그 둘이 없으면 휴지통 화면이 「삭제한 사람」과 「삭제 예정」을 말할 수 없고,
7일 보관 정책도 잴 기준이 없다.

## 기존 행

보관된 문서는 지금 0건이다(2026-08-27 운영 DB 실측). 그래서 채울 값이 없고, 백필도 없다.
나중에 보관된 문서가 생기면 그 행부터 두 칸이 채워진다 — 옛 행의 두 칸이 NULL 인 것은
「모른다」는 뜻이고, 화면은 그 경우 삭제 시각 대신 `updated_at` 을 쓰지 않는다(거짓말이
되므로 그냥 비워 둔다).

## 되감기

되감을 수 있다. 칸 둘을 지운다 — 그러면 보관된 문서는 다시 「누가 언제」를 잃지만
`archived` 자체는 그대로라 문서가 사라지지는 않는다.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0021_document_trash'
down_revision = '0020_sprint_decisions'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("archived_at", sa.DateTime(), nullable=True))
    op.add_column("documents", sa.Column("archived_by", sa.String(length=36), nullable=True))
    # 휴지통 목록은 「보관된 것을 최근 순으로」다. 보관된 문서는 전체의 일부라 부분
    # 인덱스로 충분하다 — 전체 인덱스는 안 쓰는 행 대부분을 함께 들고 다닌다.
    op.create_index(
        "ix_document_archived_at", "documents", ["archived_at"],
        postgresql_where=sa.text("archived"),
    )
    op.create_foreign_key(
        "documents_archived_by_fkey", "documents", "users",
        ["archived_by"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("documents_archived_by_fkey", "documents", type_="foreignkey")
    op.drop_index("ix_document_archived_at", table_name="documents")
    op.drop_column("documents", "archived_by")
    op.drop_column("documents", "archived_at")
