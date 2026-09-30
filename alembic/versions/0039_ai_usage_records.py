"""AI 호출 기록 표 — 한도의 원장이자 사용 통계의 원천 (계획 3.10 · 3.11, D-517).

Revision ID: 0039_ai_usage_records
Revises: 0038_ai_oauth_transactions

## 왜 새 표인가

AI 호출은 `usage_events(event='ai.call')` 에 성공한 것만 한 줄씩 남았다. 제공자, 모델, 토큰, 지연, 결과가 없어서
통계 화면은 「스케줄이 참조하는가」를 보여 주는 설정 개요였고, 실패와 막힌 호출은 어디에도 없었다. 이제 AI 런타임이
호출마다 한 행을 남긴다(성공, 실패, 막힘). 프롬프트 본문과 응답 본문은 남기지 않는다.

## 옛 기록 옮기기

`usage_events` 의 `ai.call` 을 이 표로 옮겨 이번 달의 한도 계산이 끊기지 않게 한다. 기능 이름은 옛 `meta.kind` 에서
액션으로 바꾸고(모르는 것은 그대로 둔다), 결과는 성공, 토큰과 지연은 모른다(NULL). 옛 행은 지우지 않는다.

## 되돌리기

표를 지운다. 옛 `usage_events` 는 그대로라 되돌린 코드가 그 표로 다시 센다.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "0039_ai_usage_records"
down_revision = "0038_ai_oauth_transactions"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.0039")

def upgrade() -> None:
    op.create_table(
        "ai_usage_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("actor_kind", sa.String(16), nullable=False),
        sa.Column("user_id", sa.String(36)),
        sa.Column("org_id", sa.String(36)),
        sa.Column("department_id", sa.String(36)),
        sa.Column("department_name", sa.String(200)),
        sa.Column("action_key", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(32)),
        sa.Column("auth_method", sa.String(32)),
        sa.Column("model", sa.String(200)),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("prompt_slot", sa.String(64)),
        sa.Column("prompt_version", sa.Integer()),
        sa.Column("prompt_source", sa.String(16)),
        sa.Column("policy_ids_json", sa.Text()),
        sa.Column("truncated_input", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("truncated_output", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("request_id", sa.String(64)),
        sa.Column("job_id", sa.String(36)),
    )
    op.create_index("ix_ai_usage_records_created_at", "ai_usage_records", ["created_at"])
    op.create_index("ix_ai_usage_records_user_created", "ai_usage_records", ["user_id", "created_at"])
    op.create_index("ix_ai_usage_records_action_created", "ai_usage_records", ["action_key", "created_at"])

    conn = op.get_bind()
    moved = conn.execute(sa.text(
        "INSERT INTO ai_usage_records (id, created_at, actor_kind, user_id, org_id, action_key, status) "
        "SELECT gen_random_uuid()::text, e.created_at, CASE WHEN e.user_id IS NULL THEN 'system' ELSE 'user' END, "
        "e.user_id, e.org_id, "
        "CASE coalesce(e.meta_json ->> 'kind', e.object_id, '') "
        "  WHEN 'chat_message' THEN 'chat.answer' WHEN 'ai_ask' THEN 'workspace.ask' "
        "  WHEN 'ai_draft' THEN 'workspace.draft' WHEN 'assistant_narrative' THEN 'home.narrative' "
        "  ELSE coalesce(nullif(e.meta_json ->> 'kind', ''), nullif(e.object_id, ''), 'unknown') END, "
        "'ok' FROM usage_events e WHERE e.event = 'ai.call'"
    )).rowcount
    logger.info("0039: 옛 AI 호출 기록 %s건을 옮겼다", moved)


def downgrade() -> None:
    op.drop_index("ix_ai_usage_records_action_created", table_name="ai_usage_records")
    op.drop_index("ix_ai_usage_records_user_created", table_name="ai_usage_records")
    op.drop_index("ix_ai_usage_records_created_at", table_name="ai_usage_records")
    op.drop_table("ai_usage_records")
