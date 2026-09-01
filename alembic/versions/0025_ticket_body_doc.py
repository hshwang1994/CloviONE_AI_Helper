"""티켓 본문의 정본을 문서와 같은 것(Block JSON)으로 만든다.

Revision ID: 0025_ticket_body_doc
Revises: 0024_technology_tags
Create Date: 2026-09-01

## 무엇이 문제였나

티켓의 「설명」과 문서의 본문은 **편집기가 아니라 자료가 달랐다.** 문서는 ProseMirror
문서를 정본으로 두고 마크다운·평문을 파생시키는데(`app/knowledge/blocks.py`), 티켓은
마크다운 문자열이 정본이라 굵게·기울임·밑줄·취소선·인라인코드·표·이미지를 담을 자리가
아예 없었다. 그래서 티켓 편집기는 문서와 같은 아이콘 툴바를 달 수 없었다 — 단추를 두면
눌러서 쓴 것이 저장할 곳이 없어 **조용히 사라진다.**

## 무엇을 하는가

`tickets.body_doc` 한 칸(JSONB, nullable)을 더한다. 그것뿐이다.

## 왜 전량 백필을 안 하는가

옛 행은 `body_doc` 이 비어 있고, 읽을 때 `app/tickets/body_doc.py::doc_from_markdown`
을 지나 편집기가 아는 모양이 된다. 한 번 저장하면 그 행의 정본이 doc 으로 바뀐다.

전량으로 옮기지 않는 이유는 하나다 — **되돌릴 수 있어야 한다.** 옮기는 코드가 틀렸을 때
원문이 `body_markdown` 에 그대로 남아 있어야 원래대로 읽을 수 있고, 백필을 해 버리면
그 판단을 사람이 아니라 이 마이그레이션이 미리 해 버린 것이 된다. 그리고 `body_markdown`
은 없어지지 않는다 — 검색·AI 문맥·목록 미리보기가 이미 그 칸을 읽으므로 앞으로도
**파생값으로** 계속 채워진다.

## 되돌리기

`body_doc` 칸을 지운다. 그 순간 정본은 다시 `body_markdown` 이고, doc 으로 저장하면서
파생시켜 둔 마크다운이 거기 그대로 있으므로 본문이 사라지지 않는다 — 다만 doc 에만
있던 것(굵게·표·이미지)은 마크다운이 표현할 수 있는 만큼만 남는다. 그것을 알고 지운다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0025_ticket_body_doc'
down_revision = '0024_technology_tags'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'tickets',
        sa.Column('body_doc', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('tickets', 'body_doc')
