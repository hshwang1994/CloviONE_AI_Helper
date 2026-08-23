"""옛 식별자와 우리 식별자를 잇는 다리 (S13).

Revision ID: 0011_legacy_mapping
Revises: 0010_backup_operations
Create Date: 2026-08-23

## 표 하나만 만든다

S13 이 필요로 하는 도메인 표는 이미 전부 서 있다 — `migration_exceptions`(0003) ·
`ticket_key_aliases`(0003) · `project_key_registry`(0003) · `documents.legacy_page_id`
(0004) 가 그것이다. 그 자리들을 만들 때부터 「S13 이 채운다」고 적어 두었다.

남아 있던 것은 **`legacy_mapping`** 하나다. 이유는 `app/migration/models.py` 에 있다:
옛 링크가 계속 열리게 하는 별칭(`legacy_key`·`legacy_page_id`)과 **이관 이력**은 다른
것이고, 후자를 도메인 표에 흩어 두면 「어디를 봐야 하는가」가 자원마다 달라진다.

## 되감기

표를 내린다. 데이터는 안 돌아온다(이 저장소의 되감기 규약). 되감기 뒤에 다시 이관을
돌리면 **이미 옮긴 것을 다시 옮긴다** — 그것이 이 표를 내리는 대가이고, 그래서
Cutover 이후에는 이 revision 을 되감지 않는다.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0011_legacy_mapping'
down_revision = '0010_backup_operations'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'legacy_mapping',
        sa.Column('legacy_source', sa.String(length=16), nullable=False),
        sa.Column('legacy_source_id', sa.String(length=128), nullable=False),
        sa.Column('target_type', sa.String(length=32), nullable=False),
        sa.Column('target_id', sa.String(length=64), nullable=False),
        sa.Column('migrated_at', sa.DateTime(), nullable=False),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_legacy_mapping_legacy_source'), 'legacy_mapping', ['legacy_source']
    )
    op.create_index(
        op.f('ix_legacy_mapping_target_type'), 'legacy_mapping', ['target_type']
    )
    op.create_index(
        op.f('ix_legacy_mapping_target_id'), 'legacy_mapping', ['target_id']
    )
    # 옛 식별자 하나가 두 대상을 가리키지 않는다.
    op.create_index(
        'uq_legacy_mapping_source', 'legacy_mapping',
        ['legacy_source', 'legacy_source_id', 'target_type'], unique=True,
    )
    # 한 대상이 두 옛 식별자를 주장하지 않는다 — 그것은 두 페이지가 하나로 합쳐졌다는 뜻이다.
    op.create_index(
        'uq_legacy_mapping_target', 'legacy_mapping',
        ['legacy_source', 'target_type', 'target_id'], unique=True,
    )


def downgrade() -> None:
    op.drop_index('uq_legacy_mapping_target', table_name='legacy_mapping')
    op.drop_index('uq_legacy_mapping_source', table_name='legacy_mapping')
    op.drop_index(op.f('ix_legacy_mapping_target_id'), table_name='legacy_mapping')
    op.drop_index(op.f('ix_legacy_mapping_target_type'), table_name='legacy_mapping')
    op.drop_index(op.f('ix_legacy_mapping_legacy_source'), table_name='legacy_mapping')
    op.drop_table('legacy_mapping')
