"""사람이 문서에 남긴 것을 정본 문서에 다시 붙인다 (S14 · C2).

Revision ID: 0016_document_axis_to_documents
Revises: 0015_drop_dead_mirror_sync_rows
Create Date: 2026-08-24

## 무엇이 문제였나

댓글 · 즐겨찾기 · 최근 열람 세 표가 옛 미러의 `notion_page_id` 를 조회 키로 들고 있었다.
그 키가 가리키는 `document_cache` 는 이제 사용자에게 보이는 어떤 경로도 읽지 않는 옛
미러이고(D1), 문서의 정본은 `documents` 다. 키를 그대로 두면 사람이 남긴 글이 아무도 안
읽는 표에 계속 붙어 있게 된다.

## 어떻게 옮기나

다리는 `documents.legacy_page_id` 하나다. 운영에서 `documents` 110건과
`document_cache` 110건이 이 값으로 정확히 1:1 이라(양쪽 고아 0), 옛 page id 를 가진 행은
그 다리를 건널 수 있다.

## 못 건너는 행은 지운다 — 조용히는 아니다

건널 다리가 없는 행(그 page id 를 가진 문서가 이관되지 않았거나 애초에 없던 경우)은 새
조회 키를 채울 수 없다. `document_id` 를 NULL 인 채로 두면 「어느 문서의 것인지 모르는
즐겨찾기」가 남는데, 그 행은 어느 화면에도 안 나오면서 유일 제약만 갉아먹는다. 그래서
**지우되, 몇 건을 왜 지웠는지 로그에 남긴다**(`alembic.runtime.migration`).

옮기기 직전 운영 실측(2026-08-24):

  * `document_comments` **0행** — 옛 화면에 댓글이 한 건도 안 달렸다. 잃을 것이 없다.
  * `document_favorites` **1행** — 그 행의 `document_id` 는 `document_cache` 에도
    `documents` 에도 맞지 않는 죽은 참조였다. 남는지 아닌지는 그 행의 page id 가 다리를
    건너는지가 정한다.
  * `document_recent_views` **54행** — 그중 `document_id` 가 `document_cache.id` 에 맞는
    것은 7행뿐이었다(`documents.id` 에 맞는 것은 0행). 즉 **옛 `document_id` 컬럼은 이미
    거의 전부 죽어 있었다.** 그래서 이 revision 은 그 컬럼을 안 믿고 page id 로 다시
    잇는다. 최근 열람은 「내가 언제 무엇을 봤나」이고, 못 이은 행은 그 문서를 다시 열면
    한 번에 되살아난다.

## 되감기

`notion_page_id` 를 `documents.legacy_page_id` 에서 되채운다. **옛 page id 가 없는 문서를
가리키는 행이 하나라도 있으면 되감기가 실패한다** — 이 서버에서 새로 만든 문서에 달린
댓글이 그것이고, 그 행에 적을 page id 는 존재하지 않는다. 아무 값이나 채우면 되감은 뒤에
그 댓글이 엉뚱한 문서에 붙거나 사라진다. 그래서 **왜 못 되감는지 세어서 말한다.**
"""
from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = '0016_document_axis_to_documents'
down_revision = '0015_drop_dead_mirror_sync_rows'
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

# (표 이름, 사람에게 보이는 이름)
_TABLES = (
    ("document_comments", "문서 댓글"),
    ("document_favorites", "문서 즐겨찾기"),
    ("document_recent_views", "문서 최근 열람"),
)


def _rebridge(table: str, label: str) -> None:
    """옛 page id 로 정본 문서를 다시 찾아 `document_id` 를 채우고, 못 찾은 행은 지운다."""
    bind = op.get_bind()
    # 지금 들어 있는 값은 안 믿는다 — 옛 미러의 UUID 라 정본 문서의 id 가 아니다.
    bind.execute(sa.text(
        f"UPDATE {table} AS t SET document_id = "
        "(SELECT d.id FROM documents d WHERE d.legacy_page_id = t.notion_page_id)"
    ))
    orphans = int(bind.execute(sa.text(
        f"SELECT count(*) FROM {table} WHERE document_id IS NULL"
    )).scalar_one())
    if orphans:
        logger.warning(
            "%s %d건은 가리킬 문서를 못 찾아 지웁니다. 그 옛 page id 를 가진 문서가 "
            "이관되지 않았습니다.", label, orphans,
        )
        bind.execute(sa.text(f"DELETE FROM {table} WHERE document_id IS NULL"))
    else:
        logger.info("%s 는 전부 정본 문서로 옮겼습니다.", label)


def upgrade() -> None:
    # 옛 FK 를 **먼저** 푼다. `document_comments.document_id` 는 아직 옛 미러
    # (`document_cache.id`)를 가리키고 있어서, 그 제약이 붙어 있는 채로 정본 문서 id 를 써
    # 넣으면 그 UPDATE 자체가 거절당한다. 운영은 이 표가 0행이라 조용히 지나갔을 자리다.
    op.drop_constraint(
        'document_comments_document_id_fkey', 'document_comments', type_='foreignkey'
    )

    for table, label in _TABLES:
        _rebridge(table, label)

    # ── 댓글 ────────────────────────────────────────────────────────────────
    op.alter_column(
        'document_comments', 'document_id',
        existing_type=sa.String(length=36), nullable=False,
    )
    op.create_foreign_key(
        'document_comments_document_id_fkey', 'document_comments', 'documents',
        ['document_id'], ['id'], ondelete='CASCADE',
    )
    op.drop_index('ix_document_comments_notion_page_id', table_name='document_comments')
    op.drop_column('document_comments', 'notion_page_id')

    # ── 즐겨찾기 ────────────────────────────────────────────────────────────
    op.drop_constraint('uq_doc_favorite', 'document_favorites', type_='unique')
    op.alter_column(
        'document_favorites', 'document_id',
        existing_type=sa.String(length=36), nullable=False,
    )
    op.create_foreign_key(
        'document_favorites_document_id_fkey', 'document_favorites', 'documents',
        ['document_id'], ['id'], ondelete='CASCADE',
    )
    op.create_unique_constraint(
        'uq_doc_favorite_document', 'document_favorites', ['user_id', 'document_id']
    )
    op.drop_column('document_favorites', 'notion_page_id')

    # ── 최근 열람 ───────────────────────────────────────────────────────────
    op.drop_constraint('uq_doc_recent', 'document_recent_views', type_='unique')
    op.alter_column(
        'document_recent_views', 'document_id',
        existing_type=sa.String(length=36), nullable=False,
    )
    op.create_foreign_key(
        'document_recent_views_document_id_fkey', 'document_recent_views', 'documents',
        ['document_id'], ['id'], ondelete='CASCADE',
    )
    op.create_unique_constraint(
        'uq_doc_recent_document', 'document_recent_views', ['user_id', 'document_id']
    )
    op.drop_column('document_recent_views', 'notion_page_id')


def _restore_page_ids(table: str, label: str) -> None:
    bind = op.get_bind()
    op.add_column(table, sa.Column('notion_page_id', sa.String(length=64), nullable=True))
    bind.execute(sa.text(
        f"UPDATE {table} AS t SET notion_page_id = "
        "(SELECT d.legacy_page_id FROM documents d WHERE d.id = t.document_id)"
    ))
    missing = int(bind.execute(sa.text(
        f"SELECT count(*) FROM {table} WHERE notion_page_id IS NULL"
    )).scalar_one())
    if missing:
        raise RuntimeError(
            f"{label} {missing}건이 옛 page id 가 없는 문서를 가리켜 되감을 수 없습니다. "
            "이 서버에서 새로 만든 문서에 달린 것입니다. "
            "그 행들을 지울지 무엇을 적을지 먼저 정하십시오."
        )
    op.alter_column(
        table, 'notion_page_id', existing_type=sa.String(length=64), nullable=False
    )


def downgrade() -> None:
    # ── 최근 열람 ───────────────────────────────────────────────────────────
    _restore_page_ids('document_recent_views', '문서 최근 열람')
    op.drop_constraint('uq_doc_recent_document', 'document_recent_views', type_='unique')
    op.drop_constraint(
        'document_recent_views_document_id_fkey', 'document_recent_views', type_='foreignkey'
    )
    op.alter_column(
        'document_recent_views', 'document_id',
        existing_type=sa.String(length=36), nullable=True,
    )
    op.create_unique_constraint(
        'uq_doc_recent', 'document_recent_views', ['user_id', 'notion_page_id']
    )

    # ── 즐겨찾기 ────────────────────────────────────────────────────────────
    _restore_page_ids('document_favorites', '문서 즐겨찾기')
    op.drop_constraint('uq_doc_favorite_document', 'document_favorites', type_='unique')
    op.drop_constraint(
        'document_favorites_document_id_fkey', 'document_favorites', type_='foreignkey'
    )
    op.alter_column(
        'document_favorites', 'document_id',
        existing_type=sa.String(length=36), nullable=True,
    )
    op.create_unique_constraint(
        'uq_doc_favorite', 'document_favorites', ['user_id', 'notion_page_id']
    )

    # ── 댓글 ────────────────────────────────────────────────────────────────
    _restore_page_ids('document_comments', '문서 댓글')
    op.create_index(
        'ix_document_comments_notion_page_id', 'document_comments', ['notion_page_id']
    )
    op.drop_constraint(
        'document_comments_document_id_fkey', 'document_comments', type_='foreignkey'
    )
    op.alter_column(
        'document_comments', 'document_id',
        existing_type=sa.String(length=36), nullable=True,
    )
    op.create_foreign_key(
        'document_comments_document_id_fkey', 'document_comments', 'document_cache',
        ['document_id'], ['id'], ondelete='SET NULL',
    )
