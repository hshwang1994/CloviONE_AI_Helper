"""self_id_refs — 즐겨찾기·최근열람·휴지통이 자체 id 를 함께 갖는다 (§7.1.A, PLAN Phase 4)

Revision ID: 0025
Revises: 0028
Create Date: 2026-08-03

**리비전 번호와 down_revision 이 왜 어긋나 보이는가.** 계획서의 알렘빅 규칙대로다: 번호는
예약 라벨일 뿐이고 `down_revision` 은 **머지 시점의 실제 head** 로 잡는다. 이 레인이 0024 를
올린 사이 다른 레인이 0027·0028 을 0024 위에 이미 얹었다. 여기서 0025 를 0024 뒤에 끼워
넣으려면 남의 리비전 두 개를 리베이스해야 하는데, 그건 head 를 여러 개로 만들 위험만 크고
얻는 게 없다. 그래서 현재 head(0028) 뒤에 붙인다 — 체인은 여전히 단일 head 다.

**무엇을 하는가.** 외부(Notion) 페이지 id 로만 가리키던 세 테이블에 **우리 쪽 id** 를 함께
둔다. 소스가 자체 DB 로 바뀌어도 참조가 살아남게 하는 것이 목적이다(§7.1.A).
  * `document_favorites.document_id`  → `document_cache.id`
  * `document_recent_views.document_id` → `document_cache.id`
  * `trash_items.target_uid` → `ticket_cache.id` 또는 `document_cache.id`

**레거시 `notion_page_id` 컬럼은 남긴다 — 지우면 안 된다.**
휴지통의 중복 방지 키가 거기 걸려 있다(`uq_trash_item(item_type, notion_page_id)`). 티켓은
아직 목록에서 "휴지통에 있는 notion_page_id 는 빼기"로 걸러지고, 문서도 같은 방식이다.
`notion_page_id` 를 떼면 같은 페이지를 두 번 버릴 수 있게 되고, 복원 시 목록에 **중복 행**이
생긴다. 새 컬럼은 **보조**다.

**FK 를 걸지 않는 이유.** SQLite 는 기존 테이블에 FK 를 붙이려면 테이블을 통째로 다시
만들어야 한다(batch). 세 테이블을 재생성하는 위험이, 참조 무결성이 주는 이득보다 크다 —
게다가 이 값은 **본질적으로 nullable** 이다: 미러가 아직 그 페이지를 동기화하지 않았으면
가리킬 행 자체가 없다. FK 를 걸면 그 정상 상태가 오류가 된다.

백필은 `notion_page_id` 조인 한 번이다. 미러에 없는 행은 NULL 로 남고, 나중에 동기화가
채운다(서비스 계층이 새 행을 만들 때 함께 넣는다).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # ── 문서 즐겨찾기 / 최근 열람 ─────────────────────────────────────────────
    for table in ("document_favorites", "document_recent_views"):
        op.add_column(table, sa.Column("document_id", sa.String(36), nullable=True))
        bind.execute(
            sa.text(
                f"UPDATE {table} SET document_id = ("
                "  SELECT dc.id FROM document_cache dc"
                f"  WHERE dc.notion_page_id = {table}.notion_page_id"
                ") WHERE document_id IS NULL"
            )
        )
        op.create_index(f"ix_{table}_document_id", table, ["document_id"])

    # ── 휴지통 ────────────────────────────────────────────────────────────────
    # 이름이 `item_id` 가 아니라 `target_uid` 인 이유: 이 표에는 이미 `id`(휴지통 행 자체의
    # id)가 있어서 `item_id` 는 둘 중 무엇인지 읽는 사람이 매번 헷갈린다. 가리키는 대상의
    # 자체 UUID 라는 뜻을 이름에 담는다.
    op.add_column("trash_items", sa.Column("target_uid", sa.String(36), nullable=True))
    bind.execute(
        sa.text(
            "UPDATE trash_items SET target_uid = ("
            "  SELECT tc.id FROM ticket_cache tc"
            "  WHERE tc.notion_page_id = trash_items.notion_page_id"
            ") WHERE item_type = 'ticket' AND target_uid IS NULL"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE trash_items SET target_uid = ("
            "  SELECT dc.id FROM document_cache dc"
            "  WHERE dc.notion_page_id = trash_items.notion_page_id"
            ") WHERE item_type = 'document' AND target_uid IS NULL"
        )
    )
    op.create_index("ix_trash_items_target_uid", "trash_items", ["target_uid"])


def downgrade() -> None:
    # 컬럼 삭제는 SQLite 에서 테이블 재생성이다(batch). 각 표의 유니크 제약
    # (uq_trash_item / uq_doc_favorite / uq_doc_recent)은 배치 재생성이 반영해서 다시 만든다 —
    # 왕복 회귀 테스트와 scripts/migration_rehearsal.sh 가 그것을 앞뒤 비교로 확인한다.
    op.drop_index("ix_trash_items_target_uid", table_name="trash_items")
    with op.batch_alter_table("trash_items") as batch:
        batch.drop_column("target_uid")

    for table in ("document_recent_views", "document_favorites"):
        op.drop_index(f"ix_{table}_document_id", table_name=table)
        with op.batch_alter_table(table) as batch:
            batch.drop_column("document_id")
