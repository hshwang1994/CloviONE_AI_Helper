"""외부 자동화 표 넷을 내린다 — n8n · 러너 셋이 사라졌다 (S11).

Revision ID: 0009_drop_external_automation
Revises: 0008_ai_retrieval
Create Date: 2026-08-23

## 왜 표까지 내리는가

넷 다 **부를 곳이 사라져서** 남는 표다.

| 표 | 무엇이었나 |
|---|---|
| `workflows` | n8n 웹훅 레지스트리. 등록할 수 있던 주소가 `127.0.0.1:5678` 하나였고 그 허용 목록도 함께 지웠다 |
| `runners` | `claude-{work-assistant,ticket-runner,request-interpreter}` 세 서비스의 레지스트리 |
| `automation_templates` | 위 둘을 대상(`target_type = workflow | runner`)으로만 삼던 템플릿 |
| `document_generations` | n8n 워크플로로 Notion 문서를 만들던 실행 이력. 후계는 `/api/ai/documents` 다(D-264) |

컬럼 둘도 함께 내린다: `prompts.runner_id` · `schedules.runner_id`. 둘 다 `runners.id` 를
가리키는 **참조값**이었고 화면은 러너 목록에서 골라 넣었다. 가리킬 표가 없으면 그 값은
아무것도 가리키지 않는 36자 문자열이다.

비워 두고 남기지 않는 이유는 하나다: **행을 만들 수 있는 경로가 없는 표는 화면에서
「아직 아무것도 없습니다」로 보이고, 그 화면은 영원히 그 상태다.** S13 의 이관 도구가
채울 대상도 아니다(옮겨 올 원본이 n8n 인데 그것을 지운다).

## 되감기

`downgrade()` 는 `0001_pg_baseline` 이 만들던 모양 그대로 넷을 다시 세운다. **데이터는
안 돌아온다** — 표 구조만이다. 이 저장소의 되감기 규약이 그렇고(마이그레이션은 스키마를
옮기지 실데이터를 복원하지 않는다), 실제 복구 지점은 백업이다.

`tests/regression/test_migration_roundtrip.py` 가 `upgrade → downgrade → upgrade` 를 실
PostgreSQL 에서 돌려 표·인덱스·제약 수가 대칭인지 본다.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0009_drop_external_automation'
down_revision = '0008_ai_retrieval'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column('prompts', 'runner_id')
    op.drop_column('schedules', 'runner_id')
    op.drop_index(op.f('ix_workflows_name'), table_name='workflows')
    op.drop_table('workflows')
    op.drop_index(op.f('ix_runners_name'), table_name='runners')
    op.drop_table('runners')
    op.drop_index(op.f('ix_automation_templates_name'), table_name='automation_templates')
    op.drop_table('automation_templates')
    op.drop_table('document_generations')


def downgrade() -> None:
    # 순서는 `0001_pg_baseline` 의 생성 순서를 그대로 따른다. FK 가 없는 넷이라
    # 순서 자체가 제약은 아니지만, 같은 순서를 지켜야 두 파일을 나란히 읽을 수 있다.
    op.create_table(
        'automation_templates',
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('input_schema_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('target_type', sa.String(length=16), nullable=False),
        sa.Column('target_ref', sa.String(length=64), nullable=False),
        sa.Column('prompt_id', sa.String(length=36), nullable=True),
        sa.Column('policy_id', sa.String(length=36), nullable=True),
        sa.Column('approval_policy_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('created_by', sa.String(length=36), nullable=True),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_automation_templates_name'), 'automation_templates', ['name'], unique=True
    )
    op.create_table(
        'document_generations',
        sa.Column('template_id', sa.String(length=36), nullable=True),
        sa.Column('workflow_id', sa.String(length=36), nullable=False),
        sa.Column('mode', sa.String(length=32), nullable=False),
        sa.Column('idempotency_key', sa.String(length=300), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('config_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('preview_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('quality_problems_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('published_ref', sa.String(length=500), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('requested_by', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key'),
    )
    op.create_table(
        'runners',
        sa.Column('integration_id', sa.String(length=36), nullable=True),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('provider_type', sa.String(length=32), nullable=False),
        sa.Column('base_url', sa.String(length=500), nullable=False),
        sa.Column('health_url', sa.String(length=500), nullable=True),
        sa.Column('version', sa.String(length=64), nullable=True),
        sa.Column('capabilities_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('auth_type', sa.String(length=32), nullable=False),
        sa.Column('secret_ref', sa.String(length=128), nullable=True),
        sa.Column('timeout_seconds', sa.Integer(), nullable=False),
        sa.Column('concurrency_limit', sa.Integer(), nullable=False),
        sa.Column('retry_policy_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('maintenance_state', sa.String(length=16), nullable=False),
        sa.Column('last_health_status', sa.String(length=16), nullable=False),
        sa.Column('last_health_at', sa.DateTime(), nullable=True),
        sa.Column('config_version', sa.Integer(), nullable=False),
        sa.Column('owner', sa.String(length=120), nullable=True),
        sa.Column('tags_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('consecutive_failures', sa.Integer(), nullable=False),
        sa.Column('circuit_open_until', sa.DateTime(), nullable=True),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_runners_name'), 'runners', ['name'], unique=True)
    op.create_table(
        'workflows',
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('purpose', sa.Text(), nullable=True),
        sa.Column('webhook_url', sa.String(length=500), nullable=False),
        sa.Column('http_method', sa.String(length=8), nullable=False),
        sa.Column('payload_schema_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('response_schema_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('operation_mode', sa.String(length=8), nullable=False),
        sa.Column('approval_required', sa.Boolean(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('owner', sa.String(length=120), nullable=True),
        sa.Column('tags_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('last_test_status', sa.String(length=16), nullable=True),
        sa.Column('last_test_at', sa.DateTime(), nullable=True),
        sa.Column('config_version', sa.Integer(), nullable=False),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_workflows_name'), 'workflows', ['name'], unique=True)
    op.add_column('schedules', sa.Column('runner_id', sa.String(length=36), nullable=True))
    op.add_column('prompts', sa.Column('runner_id', sa.String(length=36), nullable=True))
