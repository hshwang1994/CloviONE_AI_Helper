"""ChatGPT 계정 연결 시도 표와 갱신 토큰 만료 알림 시각 (계획 3.14 · 3.15, D-516).

Revision ID: 0038_ai_oauth_transactions
Revises: 0037_ai_runtime

## ai_oauth_transactions

관리자가 「Continue with ChatGPT」를 누를 때마다 한 행이 생긴다. 연결 도우미가 짝짓기 토큰으로 자신을 알리고, 브라우저
승인이 돌아오면 서버가 인가 코드를 토큰으로 바꾼다. 짝짓기 토큰은 해시만 두고, PKCE verifier 와 인가 코드와 토큰은
두지 않는다. 오래된 행은 AI 주기 확인이 지운다(`app/ai/health.py`).

## ai_credential_state.refresh_warned_at

갱신 토큰이 곧 끝난다는 알림을 한 갱신 토큰에 한 번만 보내려고 알린 시각을 둔다.

## 되돌리기

표와 칸을 지운다. 진행 중이던 연결 시도는 사라지고, 사람이 다시 시작하면 된다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0038_ai_oauth_transactions"
down_revision = "0037_ai_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_credential_state", sa.Column("refresh_warned_at", sa.DateTime()))
    op.create_table(
        "ai_oauth_transactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("pairing_token_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(100), nullable=False),
        sa.Column("nonce", sa.String(100), nullable=False),
        sa.Column("client_id_used", sa.String(200)),
        sa.Column("redirect_port", sa.Integer()),
        sa.Column("admin_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(64)),
        sa.Column("phase", sa.String(20), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(64)),
        sa.Column("account_label", sa.String(200)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime()),
        sa.UniqueConstraint("pairing_token_hash", name="uq_ai_oauth_transactions_pairing"),
        sa.UniqueConstraint("state", name="uq_ai_oauth_transactions_state"),
    )
    op.create_index("ix_ai_oauth_transactions_expires_at", "ai_oauth_transactions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_oauth_transactions_expires_at", table_name="ai_oauth_transactions")
    op.drop_table("ai_oauth_transactions")
    op.drop_column("ai_credential_state", "refresh_warned_at")
