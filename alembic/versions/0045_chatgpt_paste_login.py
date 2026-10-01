"""ChatGPT 계정 연결은 붙여 넣기 하나 — 연결 도우미의 짝짓기 토큰 칸을 걷는다 (D-540).

Revision ID: 0045_chatgpt_paste_login
Revises: 0044_assistant_tools

## 무엇이 바뀌나

- 열린 연결 시도(`waiting_helper` · `browser`)를 닫는다(`phase='failed'`, `error_code='superseded'`). 옛 흐름의 시도는
  도우미를 기다리거나 1455 포트로 인가 주소를 만든 것이라 새 화면이 이어 받을 수 없다. 관리자는 연결을 다시 시작하면 된다.
- `ai_oauth_transactions.pairing_token_hash` 와 그 유일 제약을 지운다. 붙여 넣기 흐름에는 도우미가 없으므로 짝짓기 토큰이
  없다. 자격 · 호스트 id · 토큰(비밀 칸)과 `ai_credential_state` 는 그대로다.

## 되돌리기

칸을 nullable 로 되살린다(유일 제약 포함 — NULL 은 서로 겹치지 않는다). 닫은 시도는 되살리지 않는다(10분짜리 시도이고
되살려도 옛 도우미 경로가 없다).
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "0045_chatgpt_paste_login"
down_revision = "0044_assistant_tools"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

TABLE = "ai_oauth_transactions"
UNIQUE = "uq_ai_oauth_transactions_pairing"


def upgrade() -> None:
    bind = op.get_bind()
    closed = bind.execute(sa.text(
        f"UPDATE {TABLE} SET phase = 'failed', error_code = 'superseded', updated_at = now() at time zone 'utc' "
        "WHERE phase IN ('waiting_helper', 'browser')"
    )).rowcount
    logger.info("0045: 열린 ChatGPT 연결 시도 %s건을 닫았다", closed)
    op.drop_constraint(UNIQUE, TABLE, type_="unique")
    op.drop_column(TABLE, "pairing_token_hash")


def downgrade() -> None:
    op.add_column(TABLE, sa.Column("pairing_token_hash", sa.String(64), nullable=True))
    op.create_unique_constraint(UNIQUE, TABLE, ["pairing_token_hash"])
