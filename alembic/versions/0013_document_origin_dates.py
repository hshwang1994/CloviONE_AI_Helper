"""문서가 옛 시스템에서 생기고 고쳐진 날 (S14).

Revision ID: 0013_document_origin_dates
Revises: 0012_project_code_policy
Create Date: 2026-08-24

## 왜 칸을 더하는가

`documents` 에는 `created_at`·`updated_at` 밖에 없고 그 둘은 **우리 행이 생긴 시각**이다.
이관한 문서 110건은 전부 같은 날 같은 시각에 만들어지므로, 원본이 들고 있던 3년치
날짜가 그 순간 사라진다 — 그리고 사라졌다는 사실은 목록을 「최근 수정순」으로 정렬해
보기 전에는 아무 데도 안 나온다.

우리 시각을 옛 값으로 덮는 방법도 있다. 안 쓴다: 「이 행이 언제 우리 DB 에 들어왔는가」는
장애를 되짚을 때 필요한 값이고, 덮으면 그것을 다시 만들 방법이 없다. 두 질문은 다르므로
칸을 둘 둔다.

`tickets` 는 같은 값을 이미 갖고 있다(`notion_created_time`·`notion_last_edited`).
이름을 그대로 베끼지 않은 이유는 이 표가 제품이 소유한 정본이기 때문이다 — 같은 표의
`legacy_page_id` 와 짝이 맞는 이름을 쓴다.

## 되감기

칸 둘을 내린다. 그 값은 안 돌아오지만 원본에서 다시 읽어 채울 수 있다
(`migrate_cli reimport-bodies`).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0013_document_origin_dates'
down_revision = '0012_project_code_policy'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('legacy_created_at', sa.DateTime(), nullable=True))
    op.add_column('documents', sa.Column('legacy_updated_at', sa.DateTime(), nullable=True))
    # 「옛 시스템 기준 최근 수정순」이 목록의 기본 정렬 후보다. 인덱스가 없으면 문서가
    # 늘수록 그 화면만 느려지고, 느려진 이유는 화면에 안 나온다.
    op.create_index(
        op.f('ix_documents_legacy_updated_at'), 'documents', ['legacy_updated_at']
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_documents_legacy_updated_at'), table_name='documents')
    op.drop_column('documents', 'legacy_updated_at')
    op.drop_column('documents', 'legacy_created_at')
