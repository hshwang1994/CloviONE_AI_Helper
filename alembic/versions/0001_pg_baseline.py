"""PostgreSQL 기준선 — 목표 스키마 전부를 이 한 revision 이 만든다 (D-189).

Revision ID: 0001_pg_baseline
Revises:
Create Date: 2026-08-21

SQLite 시절 61개 revision 은 `alembic/legacy_sqlite/` 에 비활성으로 보관한다(그 README 가
왜 이식하지 않았는지 적고 있다). **데이터는 이 파일이 옮기지 않는다** — 이관은 Migration
Tool 의 일이다(S13).

앱 코드를 import 하지 않는다. 마이그레이션은 **그 시점 스키마의 얼어붙은 스냅숏**이라,
`app.core.models_base.JsonText` 같은 앱 타입을 참조하면 나중에 그 타입을 고치는 날
이 파일의 뜻이 소리 없이 함께 바뀐다. 저장 타입인 `postgresql.JSONB` 를 직접 쓴다.

⚠️ **이 파일은 모델에서 자동 생성된다.** 그래서 모델에 없는 것은 여기에도 없다 —
옛 체인이 만든 인덱스 10개가 실제로 그렇게 빠질 뻔했다(D-221).
`tests/regression/test_baseline_carries_every_legacy_index.py` 가 그 구멍을 지킨다.
"""
from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '0001_pg_baseline'
down_revision = None
branch_labels = None
depends_on = None


# ── 부트스트랩 시드 값 ───────────────────────────────────────────────────────
#
# 마이그레이션은 **얼어붙은 스냅숏**이라 앱 상수를 import 하지 않는다(모듈 docstring).
# 그래서 값을 여기 그대로 적는다 — 옛 체인도 같은 규약이었다(0022 의 `_DEFAULT_ORG_ID`).
#
# 두 곳에 적힌 값이 어긋나면 조용히 깨지므로, **시험이 둘을 맞물려 둔다**:
# `tests/unit/test_pg_baseline_seed.py`.
_DEFAULT_ORG_ID = "00000000-0000-0000-0000-00000000org1"
_DEFAULT_ORG_SLUG = "default"
# 조직 이름은 **제품명이 아니다**. 0034 가 리브랜딩하며 둘을 같은 것으로 취급해 제품명이
# 조직명 자리에 들어갔고, 화면에 조직 이름이 나오는 자리마다 회사 이름 대신 제품 이름이
# 찍혔다(0038 이 고쳤다). 여기에는 처음부터 실제 조직 이름을 넣는다.
_DEFAULT_ORG_NAME = "굿모닝아이텍"
_GLOBAL_CHAT_ROOM_ID = "00000000-0000-0000-0000-0000cha70001"
_TICKET_SINGLETON_ID = "tickets"
_DOCUMENT_SYNC_ID = "documents"


def upgrade() -> None:
    # 한국어 검색의 정본이 이 확장이다(D-209). 아래 `gin_trgm_ops` 인덱스보다 **먼저**
    # 있어야 한다 — 없으면 그 인덱스 생성이 「operator class does not exist」로 죽는다.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table('ai_quotas',
    sa.Column('scope_type', sa.String(length=16), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('period', sa.String(length=16), nullable=False),
    sa.Column('max_calls', sa.Integer(), nullable=False),
    sa.Column('note', sa.String(length=200), nullable=True),
    sa.Column('created_by', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('scope_type', 'user_id', 'period', name='uq_ai_quota_scope')
    )
    op.create_table('announcements',
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('level', sa.String(length=16), nullable=False),
    sa.Column('audience', sa.String(length=16), nullable=False),
    sa.Column('starts_at', sa.DateTime(), nullable=True),
    sa.Column('ends_at', sa.DateTime(), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('dismissible', sa.Boolean(), nullable=False),
    sa.Column('link_url', sa.String(length=500), nullable=True),
    sa.Column('link_label', sa.String(length=80), nullable=True),
    sa.Column('created_by', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_announcements_active'), 'announcements', ['active'], unique=False)
    op.create_table('app_settings',
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('value_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('value_type', sa.String(length=16), nullable=False),
    sa.Column('validation_schema_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('secret_reference', sa.String(length=128), nullable=True),
    sa.Column('restart_required', sa.Boolean(), nullable=False),
    sa.Column('updated_by', sa.String(length=36), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('approval_delegations',
    sa.Column('delegator_user_id', sa.String(length=36), nullable=False),
    sa.Column('delegate_user_id', sa.String(length=36), nullable=False),
    sa.Column('reason', sa.String(length=500), nullable=True),
    sa.Column('starts_at', sa.DateTime(), nullable=False),
    sa.Column('ends_at', sa.DateTime(), nullable=False),
    sa.Column('revoked_at', sa.DateTime(), nullable=True),
    sa.Column('created_by', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_approval_delegations_delegate_user_id'), 'approval_delegations', ['delegate_user_id'], unique=False)
    op.create_index(op.f('ix_approval_delegations_delegator_user_id'), 'approval_delegations', ['delegator_user_id'], unique=False)
    op.create_table('approvals',
    sa.Column('request_type', sa.String(length=64), nullable=False),
    sa.Column('object_type', sa.String(length=64), nullable=False),
    sa.Column('object_id', sa.String(length=64), nullable=False),
    sa.Column('requested_by', sa.String(length=36), nullable=False),
    sa.Column('approver_id', sa.String(length=36), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('request_payload_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('decision_comment', sa.Text(), nullable=True),
    sa.Column('requested_at', sa.DateTime(), nullable=False),
    sa.Column('decided_at', sa.DateTime(), nullable=True),
    sa.Column('expires_at', sa.DateTime(), nullable=True),
    sa.Column('due_at', sa.DateTime(), nullable=True),
    sa.Column('sla_notified_at', sa.DateTime(), nullable=True),
    sa.Column('decided_on_behalf_of', sa.String(length=36), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_approvals_request_type'), 'approvals', ['request_type'], unique=False)
    op.create_index(op.f('ix_approvals_status'), 'approvals', ['status'], unique=False)
    op.create_index('ux_approvals_pending_dedup', 'approvals', ['request_type', 'object_id', 'request_payload_json'], unique=True, postgresql_where=sa.text("status = 'pending'"))
    op.create_table('audit_logs',
    sa.Column('user_id', sa.String(length=36), nullable=True),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('object_type', sa.String(length=64), nullable=False),
    sa.Column('object_id', sa.String(length=64), nullable=True),
    sa.Column('before_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('after_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('result', sa.String(length=16), nullable=False),
    sa.Column('client_ip', sa.String(length=64), nullable=True),
    sa.Column('request_id', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_audit_logs_created_at'), 'audit_logs', ['created_at'], unique=False)
    op.create_index('ix_audit_logs_object_id', 'audit_logs', ['object_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_object_type'), 'audit_logs', ['object_type'], unique=False)
    op.create_index(op.f('ix_audit_logs_user_id'), 'audit_logs', ['user_id'], unique=False)
    op.create_table('automation_templates',
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
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_automation_templates_name'), 'automation_templates', ['name'], unique=True)
    op.create_table('backups',
    sa.Column('backup_type', sa.String(length=32), nullable=False),
    sa.Column('path', sa.String(length=500), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=True),
    sa.Column('checksum', sa.String(length=64), nullable=True),
    sa.Column('created_by', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('verified_at', sa.DateTime(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('config_versions',
    sa.Column('object_type', sa.String(length=64), nullable=False),
    sa.Column('object_id', sa.String(length=64), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('snapshot_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_by', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_config_versions_object_id'), 'config_versions', ['object_id'], unique=False)
    op.create_index(op.f('ix_config_versions_object_type'), 'config_versions', ['object_type'], unique=False)
    op.create_index('uq_config_versions_object_version', 'config_versions', ['object_type', 'object_id', 'version'], unique=True)
    op.create_table('document_favorites',
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('notion_page_id', sa.String(length=64), nullable=False),
    sa.Column('document_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'notion_page_id', name='uq_doc_favorite')
    )
    op.create_index(op.f('ix_document_favorites_document_id'), 'document_favorites', ['document_id'], unique=False)
    op.create_index(op.f('ix_document_favorites_user_id'), 'document_favorites', ['user_id'], unique=False)
    op.create_table('document_generations',
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
    sa.UniqueConstraint('idempotency_key')
    )
    op.create_table('document_recent_views',
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('notion_page_id', sa.String(length=64), nullable=False),
    sa.Column('document_id', sa.String(length=36), nullable=True),
    sa.Column('viewed_at', sa.DateTime(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'notion_page_id', name='uq_doc_recent')
    )
    op.create_index(op.f('ix_document_recent_views_document_id'), 'document_recent_views', ['document_id'], unique=False)
    op.create_index(op.f('ix_document_recent_views_user_id'), 'document_recent_views', ['user_id'], unique=False)
    op.create_table('document_sync_state',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('last_run_at', sa.DateTime(), nullable=True),
    sa.Column('last_success_at', sa.DateTime(), nullable=True),
    sa.Column('doc_count', sa.Integer(), nullable=False),
    sa.Column('pruned_count', sa.Integer(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('heartbeats',
    sa.Column('component', sa.String(length=32), nullable=False),
    sa.Column('last_beat_at', sa.DateTime(), nullable=False),
    sa.Column('detail', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('component')
    )
    op.create_table('impersonation_sessions',
    sa.Column('actor_user_id', sa.String(length=36), nullable=False),
    sa.Column('target_user_id', sa.String(length=36), nullable=False),
    sa.Column('session_id', sa.String(length=36), nullable=False),
    sa.Column('reason', sa.String(length=500), nullable=True),
    sa.Column('client_ip', sa.String(length=64), nullable=True),
    sa.Column('started_at', sa.DateTime(), nullable=False),
    sa.Column('ended_at', sa.DateTime(), nullable=True),
    sa.Column('ended_reason', sa.String(length=32), nullable=True),
    sa.Column('read_count', sa.Integer(), nullable=False),
    sa.Column('blocked_write_count', sa.Integer(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_impersonation_sessions_actor_user_id'), 'impersonation_sessions', ['actor_user_id'], unique=False)
    op.create_index(op.f('ix_impersonation_sessions_started_at'), 'impersonation_sessions', ['started_at'], unique=False)
    op.create_index(op.f('ix_impersonation_sessions_target_user_id'), 'impersonation_sessions', ['target_user_id'], unique=False)
    op.create_table('integrations',
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('provider_type', sa.String(length=32), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('base_url', sa.String(length=500), nullable=False),
    sa.Column('health_url', sa.String(length=500), nullable=True),
    sa.Column('auth_type', sa.String(length=32), nullable=False),
    sa.Column('secret_ref', sa.String(length=128), nullable=True),
    sa.Column('capabilities_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('last_health_status', sa.String(length=16), nullable=False),
    sa.Column('last_health_at', sa.DateTime(), nullable=True),
    sa.Column('config_version', sa.Integer(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_integrations_name'), 'integrations', ['name'], unique=True)
    op.create_table('jobs',
    sa.Column('job_type', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=True),
    sa.Column('conversation_id', sa.String(length=36), nullable=True),
    sa.Column('message_id', sa.String(length=64), nullable=True),
    sa.Column('payload_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('attempt_count', sa.Integer(), nullable=False),
    sa.Column('max_attempts', sa.Integer(), nullable=False),
    sa.Column('idempotency_key', sa.String(length=200), nullable=True),
    sa.Column('available_at', sa.DateTime(), nullable=False),
    sa.Column('started_at', sa.DateTime(), nullable=True),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('idempotency_key')
    )
    op.create_index(op.f('ix_jobs_available_at'), 'jobs', ['available_at'], unique=False)
    op.create_index('ix_jobs_claim', 'jobs', ['status', 'available_at', 'created_at'], unique=False)
    op.create_index(op.f('ix_jobs_job_type'), 'jobs', ['job_type'], unique=False)
    op.create_index(op.f('ix_jobs_status'), 'jobs', ['status'], unique=False)
    op.create_index(op.f('ix_jobs_user_id'), 'jobs', ['user_id'], unique=False)
    op.create_table('mail_deliveries',
    sa.Column('kind', sa.String(length=64), nullable=False),
    sa.Column('to_email', sa.String(length=320), nullable=False),
    sa.Column('subject', sa.String(length=300), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('attempt_count', sa.Integer(), nullable=False),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('params_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('job_id', sa.String(length=36), nullable=True),
    sa.Column('sent_at', sa.DateTime(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_mail_deliveries_created_at', 'mail_deliveries', ['created_at'], unique=False)
    op.create_index(op.f('ix_mail_deliveries_kind'), 'mail_deliveries', ['kind'], unique=False)
    op.create_index(op.f('ix_mail_deliveries_status'), 'mail_deliveries', ['status'], unique=False)
    op.create_table('notifications',
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('type', sa.String(length=64), nullable=False),
    sa.Column('audience', sa.String(length=16), server_default='user', nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('read_at', sa.DateTime(), nullable=True),
    sa.Column('related_object_type', sa.String(length=64), nullable=True),
    sa.Column('related_object_id', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notifications_audience'), 'notifications', ['audience'], unique=False)
    op.create_index(op.f('ix_notifications_created_at'), 'notifications', ['created_at'], unique=False)
    op.create_index(op.f('ix_notifications_user_id'), 'notifications', ['user_id'], unique=False)
    op.create_index('ix_notifications_user_unread', 'notifications', ['user_id', 'read_at'], unique=False)
    op.create_table('organizations',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('settings_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_organizations_slug'), 'organizations', ['slug'], unique=True)
    op.create_table('policies',
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('purpose', sa.Text(), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('content_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('created_by', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('published_at', sa.DateTime(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name', 'version', name='uq_policies_name_version')
    )
    op.create_index(op.f('ix_policies_name'), 'policies', ['name'], unique=False)
    op.create_index('ux_policies_published_dedup', 'policies', ['name'], unique=True, postgresql_where=sa.text("status = 'published'"))
    op.create_table('project_sync_state',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('last_run_at', sa.DateTime(), nullable=True),
    sa.Column('last_success_at', sa.DateTime(), nullable=True),
    sa.Column('project_count', sa.Integer(), nullable=False),
    sa.Column('truncated', sa.Boolean(), nullable=False),
    sa.Column('pruned_count', sa.Integer(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('prompts',
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('purpose', sa.Text(), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('runner_id', sa.String(length=36), nullable=True),
    sa.Column('created_by', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('published_at', sa.DateTime(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name', 'version', name='uq_prompts_name_version')
    )
    op.create_index(op.f('ix_prompts_name'), 'prompts', ['name'], unique=False)
    op.create_index('ux_prompts_published_dedup', 'prompts', ['name'], unique=True, postgresql_where=sa.text("status = 'published'"))
    op.create_table('rate_limit_buckets',
    sa.Column('key', sa.String(length=200), nullable=False),
    sa.Column('tokens', sa.Float(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_index(op.f('ix_rate_limit_buckets_updated_at'), 'rate_limit_buckets', ['updated_at'], unique=False)
    op.create_table('restore_rehearsals',
    sa.Column('source_label', sa.String(length=200), nullable=True),
    sa.Column('started_at', sa.DateTime(), nullable=False),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.Column('ok', sa.Boolean(), nullable=False),
    sa.Column('failures_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('summary_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_by', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_restore_rehearsals_started_at'), 'restore_rehearsals', ['started_at'], unique=False)
    op.create_table('runners',
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
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_runners_name'), 'runners', ['name'], unique=True)
    op.create_table('schedule_runs',
    sa.Column('schedule_id', sa.String(length=36), nullable=False),
    sa.Column('scheduled_at', sa.DateTime(), nullable=False),
    sa.Column('idempotency_key', sa.String(length=200), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('request_payload_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('response_summary', sa.Text(), nullable=True),
    sa.Column('started_at', sa.DateTime(), nullable=True),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('retry_count', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('idempotency_key')
    )
    op.create_index('ix_schedule_runs_created_at', 'schedule_runs', ['created_at'], unique=False)
    op.create_index(op.f('ix_schedule_runs_schedule_id'), 'schedule_runs', ['schedule_id'], unique=False)
    op.create_table('schedules',
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('schedule_type', sa.String(length=16), nullable=False),
    sa.Column('cron_expression', sa.String(length=120), nullable=True),
    sa.Column('timezone', sa.String(length=64), nullable=False),
    sa.Column('owner_user_id', sa.String(length=36), nullable=True),
    sa.Column('target_type', sa.String(length=16), nullable=False),
    sa.Column('target_ref', sa.String(length=64), nullable=False),
    sa.Column('payload_template_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('prompt_id', sa.String(length=36), nullable=True),
    sa.Column('runner_id', sa.String(length=36), nullable=True),
    sa.Column('approval_policy_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('retry_policy_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('misfire_policy', sa.String(length=16), nullable=False),
    sa.Column('concurrency_policy', sa.String(length=16), nullable=False),
    sa.Column('timeout_seconds', sa.Integer(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('start_at', sa.DateTime(), nullable=True),
    sa.Column('end_at', sa.DateTime(), nullable=True),
    sa.Column('next_run_at', sa.DateTime(), nullable=True),
    sa.Column('last_run_at', sa.DateTime(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_schedules_next_run_at'), 'schedules', ['next_run_at'], unique=False)
    op.create_table('sync_status',
    sa.Column('component', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('last_run_at', sa.DateTime(), nullable=True),
    sa.Column('last_success_at', sa.DateTime(), nullable=True),
    sa.Column('item_count', sa.Integer(), nullable=False),
    sa.Column('truncated', sa.Boolean(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('detail_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('component')
    )
    op.create_table('ticket_meta_cache',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('statuses', sa.Text(), nullable=False),
    sa.Column('priorities', sa.Text(), nullable=False),
    sa.Column('difficulties', sa.Text(), nullable=False),
    sa.Column('projects_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('synced_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('ticket_sync_state',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('last_run_at', sa.DateTime(), nullable=True),
    sa.Column('last_success_at', sa.DateTime(), nullable=True),
    sa.Column('ticket_count', sa.Integer(), nullable=False),
    sa.Column('truncated', sa.Boolean(), nullable=False),
    sa.Column('pruned_count', sa.Integer(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('workflows',
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
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_workflows_name'), 'workflows', ['name'], unique=True)
    op.create_table('announcement_dismissals',
    sa.Column('announcement_id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('dismissed_at', sa.DateTime(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['announcement_id'], ['announcements.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('announcement_id', 'user_id', name='uq_announcement_dismissal')
    )
    op.create_index(op.f('ix_announcement_dismissals_user_id'), 'announcement_dismissals', ['user_id'], unique=False)
    op.create_table('chat_rooms',
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('created_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('is_global', sa.Boolean(), nullable=False),
    sa.Column('dm_key', sa.String(length=80), nullable=True),
    sa.Column('department_id', sa.String(length=36), nullable=True),
    sa.Column('event_seq', sa.Integer(), nullable=False),
    sa.Column('archived_at', sa.DateTime(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.Column('org_id', sa.String(length=36), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('dm_key')
    )
    op.create_index(op.f('ix_chat_rooms_deleted_at'), 'chat_rooms', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_chat_rooms_department_id'), 'chat_rooms', ['department_id'], unique=False)
    op.create_index(op.f('ix_chat_rooms_kind'), 'chat_rooms', ['kind'], unique=False)
    op.create_index(op.f('ix_chat_rooms_org_id'), 'chat_rooms', ['org_id'], unique=False)
    op.create_table('departments',
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('parent_id', sa.String(length=36), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('org_id', sa.String(length=36), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['parent_id'], ['departments.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_departments_name'), 'departments', ['name'], unique=False)
    op.create_index(op.f('ix_departments_org_id'), 'departments', ['org_id'], unique=False)
    op.create_index(op.f('ix_departments_parent_id'), 'departments', ['parent_id'], unique=False)
    op.create_index('uq_departments_org_name', 'departments', ['org_id', 'name'], unique=True)
    op.create_table('game_rooms',
    sa.Column('title', sa.String(length=120), nullable=False),
    sa.Column('game_type', sa.String(length=32), nullable=False),
    sa.Column('host_user_id', sa.String(length=36), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('max_players', sa.Integer(), nullable=False),
    sa.Column('allow_spectators', sa.Boolean(), nullable=False),
    sa.Column('config_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('state_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('event_seq', sa.Integer(), nullable=False),
    sa.Column('closed_at', sa.DateTime(), nullable=True),
    sa.Column('org_id', sa.String(length=36), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_game_rooms_closed_at'), 'game_rooms', ['closed_at'], unique=False)
    op.create_index(op.f('ix_game_rooms_host_user_id'), 'game_rooms', ['host_user_id'], unique=False)
    op.create_index(op.f('ix_game_rooms_org_id'), 'game_rooms', ['org_id'], unique=False)
    op.create_index(op.f('ix_game_rooms_status'), 'game_rooms', ['status'], unique=False)
    op.create_table('job_titles',
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('org_id', sa.String(length=36), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_job_titles_name'), 'job_titles', ['name'], unique=True)
    op.create_index(op.f('ix_job_titles_org_id'), 'job_titles', ['org_id'], unique=False)
    op.create_table('search_documents',
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('ref_id', sa.String(length=64), nullable=False),
    sa.Column('owner_user_ids', sa.Text(), nullable=False),
    sa.Column('owner_kind', sa.String(length=16), server_default='unset', nullable=False),
    sa.Column('owner_dept_id', sa.String(length=36), nullable=True),
    sa.Column('owner_project_id', sa.String(length=36), nullable=True),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('subtitle', sa.String(length=300), nullable=True),
    sa.Column('route', sa.String(length=300), nullable=False),
    sa.Column('url', sa.String(length=1000), nullable=True),
    sa.Column('sort_key', sa.String(length=40), nullable=True),
    sa.Column('indexed_at', sa.DateTime(), nullable=False),
    sa.Column('org_id', sa.String(length=36), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_search_documents_body_trgm', 'search_documents', ['body'], unique=False, postgresql_using='gin', postgresql_ops={'body': 'gin_trgm_ops'})
    op.create_index(op.f('ix_search_documents_kind'), 'search_documents', ['kind'], unique=False)
    op.create_index(op.f('ix_search_documents_org_id'), 'search_documents', ['org_id'], unique=False)
    op.create_index('ix_search_documents_title_trgm', 'search_documents', ['title'], unique=False, postgresql_using='gin', postgresql_ops={'title': 'gin_trgm_ops'})
    op.create_table('trash_items',
    sa.Column('item_type', sa.String(length=16), nullable=False),
    sa.Column('notion_page_id', sa.String(length=64), nullable=False),
    sa.Column('title', sa.String(length=400), nullable=False),
    sa.Column('url', sa.String(length=1000), nullable=True),
    sa.Column('target_uid', sa.String(length=36), nullable=True),
    sa.Column('deleted_by_user_id', sa.String(length=36), nullable=False),
    sa.Column('deleted_by_name', sa.String(length=200), nullable=False),
    sa.Column('deleted_at', sa.DateTime(), nullable=False),
    sa.Column('org_id', sa.String(length=36), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('item_type', 'notion_page_id', name='uq_trash_item')
    )
    op.create_index(op.f('ix_trash_items_deleted_at'), 'trash_items', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_trash_items_item_type'), 'trash_items', ['item_type'], unique=False)
    op.create_index(op.f('ix_trash_items_notion_page_id'), 'trash_items', ['notion_page_id'], unique=False)
    op.create_index(op.f('ix_trash_items_org_id'), 'trash_items', ['org_id'], unique=False)
    op.create_index(op.f('ix_trash_items_target_uid'), 'trash_items', ['target_uid'], unique=False)
    op.create_table('usage_events',
    sa.Column('user_id', sa.String(length=36), nullable=True),
    sa.Column('event', sa.String(length=64), nullable=False),
    sa.Column('object_type', sa.String(length=48), nullable=True),
    sa.Column('object_id', sa.String(length=64), nullable=True),
    sa.Column('meta_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('org_id', sa.String(length=36), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_usage_events_created_at'), 'usage_events', ['created_at'], unique=False)
    op.create_index(op.f('ix_usage_events_event'), 'usage_events', ['event'], unique=False)
    op.create_index(op.f('ix_usage_events_org_id'), 'usage_events', ['org_id'], unique=False)
    op.create_index(op.f('ix_usage_events_user_id'), 'usage_events', ['user_id'], unique=False)
    op.create_table('chat_messages',
    sa.Column('room_id', sa.String(length=36), nullable=False),
    sa.Column('seq', sa.Integer(), nullable=False),
    sa.Column('sender_user_id', sa.String(length=36), nullable=True),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('client_message_id', sa.String(length=64), nullable=True),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['room_id'], ['chat_rooms.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('room_id', 'seq', name='uq_chat_message_seq')
    )
    op.create_index(op.f('ix_chat_messages_room_id'), 'chat_messages', ['room_id'], unique=False)
    op.create_index(op.f('ix_chat_messages_seq'), 'chat_messages', ['seq'], unique=False)
    op.create_table('chat_read_cursors',
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('room_id', sa.String(length=36), nullable=False),
    sa.Column('last_read_seq', sa.Integer(), nullable=False),
    sa.Column('hidden_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['room_id'], ['chat_rooms.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'room_id', name='uq_chat_read_cursor')
    )
    op.create_index(op.f('ix_chat_read_cursors_room_id'), 'chat_read_cursors', ['room_id'], unique=False)
    op.create_index(op.f('ix_chat_read_cursors_user_id'), 'chat_read_cursors', ['user_id'], unique=False)
    op.create_table('chat_room_members',
    sa.Column('room_id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('last_read_seq', sa.Integer(), nullable=False),
    sa.Column('joined_at', sa.DateTime(), nullable=False),
    sa.Column('last_seen', sa.DateTime(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['room_id'], ['chat_rooms.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('room_id', 'user_id', name='uq_chat_member')
    )
    op.create_index(op.f('ix_chat_room_members_room_id'), 'chat_room_members', ['room_id'], unique=False)
    op.create_index(op.f('ix_chat_room_members_user_id'), 'chat_room_members', ['user_id'], unique=False)
    op.create_table('game_events',
    sa.Column('room_id', sa.String(length=36), nullable=False),
    sa.Column('seq', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('actor_user_id', sa.String(length=36), nullable=True),
    sa.Column('payload_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['room_id'], ['game_rooms.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('room_id', 'seq', name='uq_game_event_seq')
    )
    op.create_index(op.f('ix_game_events_room_id'), 'game_events', ['room_id'], unique=False)
    op.create_index(op.f('ix_game_events_seq'), 'game_events', ['seq'], unique=False)
    op.create_table('game_room_members',
    sa.Column('room_id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('display_name', sa.String(length=120), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('ready', sa.Boolean(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('last_seen', sa.DateTime(), nullable=False),
    sa.Column('joined_at', sa.DateTime(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['room_id'], ['game_rooms.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('room_id', 'user_id', name='uq_game_member')
    )
    op.create_index(op.f('ix_game_room_members_room_id'), 'game_room_members', ['room_id'], unique=False)
    op.create_table('users',
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('display_name', sa.String(length=120), nullable=False),
    sa.Column('department_id', sa.String(length=36), nullable=True),
    sa.Column('title_id', sa.String(length=36), nullable=True),
    sa.Column('membership_kind', sa.String(length=16), server_default='unassigned', nullable=False),
    sa.Column('admin_scope', sa.String(length=16), server_default='global', nullable=False),
    sa.Column('scope_org_id', sa.String(length=36), nullable=True),
    sa.Column('scope_dept_id', sa.String(length=36), nullable=True),
    sa.Column('role', sa.String(length=32), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('must_change_password', sa.Boolean(), nullable=False),
    sa.Column('failed_login_count', sa.Integer(), nullable=False),
    sa.Column('locked_until', sa.DateTime(), nullable=True),
    sa.Column('created_by', sa.String(length=36), nullable=True),
    sa.Column('last_login_at', sa.DateTime(), nullable=True),
    sa.Column('archived_at', sa.DateTime(), nullable=True),
    sa.Column('org_id', sa.String(length=36), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['department_id'], ['departments.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['scope_dept_id'], ['departments.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['scope_org_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['title_id'], ['job_titles.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_archived_at'), 'users', ['archived_at'], unique=False)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_membership_kind'), 'users', ['membership_kind'], unique=False)
    op.create_index(op.f('ix_users_org_id'), 'users', ['org_id'], unique=False)
    op.create_table('board_posts',
    sa.Column('author_user_id', sa.String(length=36), nullable=False),
    sa.Column('kind', sa.String(length=16), server_default='free', nullable=False),
    sa.Column('idea_status', sa.String(length=16), nullable=True),
    sa.Column('ticket_page_id', sa.String(length=64), nullable=True),
    sa.Column('category', sa.String(length=32), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('is_pinned', sa.Boolean(), nullable=False),
    sa.Column('view_count', sa.Integer(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.Column('org_id', sa.String(length=36), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['author_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_board_posts_author_user_id'), 'board_posts', ['author_user_id'], unique=False)
    op.create_index(op.f('ix_board_posts_category'), 'board_posts', ['category'], unique=False)
    op.create_index('ix_board_posts_created_at', 'board_posts', ['created_at'], unique=False)
    op.create_index(op.f('ix_board_posts_deleted_at'), 'board_posts', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_board_posts_idea_status'), 'board_posts', ['idea_status'], unique=False)
    op.create_index(op.f('ix_board_posts_is_pinned'), 'board_posts', ['is_pinned'], unique=False)
    op.create_index(op.f('ix_board_posts_kind'), 'board_posts', ['kind'], unique=False)
    op.create_index(op.f('ix_board_posts_org_id'), 'board_posts', ['org_id'], unique=False)
    op.create_index(op.f('ix_board_posts_ticket_page_id'), 'board_posts', ['ticket_page_id'], unique=False)
    op.create_table('board_reactions',
    sa.Column('target_type', sa.String(length=16), nullable=False),
    sa.Column('target_id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('emoji', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('target_type', 'target_id', 'user_id', 'emoji', name='uq_board_reaction')
    )
    op.create_index(op.f('ix_board_reactions_target_id'), 'board_reactions', ['target_id'], unique=False)
    op.create_table('chat_message_images',
    sa.Column('message_id', sa.String(length=36), nullable=False),
    sa.Column('room_id', sa.String(length=36), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('stored_name', sa.String(length=255), nullable=False),
    sa.Column('media_type', sa.String(length=100), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['message_id'], ['chat_messages.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chat_message_images_message_id'), 'chat_message_images', ['message_id'], unique=False)
    op.create_index(op.f('ix_chat_message_images_room_id'), 'chat_message_images', ['room_id'], unique=False)
    op.create_table('conversations',
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('backend_conversation_id', sa.String(length=128), nullable=True),
    sa.Column('archived', sa.Boolean(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_conversations_updated_at', 'conversations', ['updated_at'], unique=False)
    op.create_index(op.f('ix_conversations_user_id'), 'conversations', ['user_id'], unique=False)
    op.create_table('offboarding_runs',
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('actor_user_id', sa.String(length=36), nullable=False),
    sa.Column('successor_user_id', sa.String(length=36), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('deactivated', sa.Boolean(), nullable=False),
    sa.Column('archived', sa.Boolean(), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('rooms_transferred', sa.Integer(), nullable=False),
    sa.Column('ticket_total', sa.Integer(), nullable=False),
    sa.Column('ticket_moved', sa.Integer(), nullable=False),
    sa.Column('ticket_failed', sa.Integer(), nullable=False),
    sa.Column('undone_at', sa.DateTime(), nullable=True),
    sa.Column('undone_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('undo_error', sa.Text(), nullable=True),
    sa.Column('org_id', sa.String(length=36), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['successor_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['undone_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_offboarding_runs_actor_user_id'), 'offboarding_runs', ['actor_user_id'], unique=False)
    op.create_index(op.f('ix_offboarding_runs_org_id'), 'offboarding_runs', ['org_id'], unique=False)
    op.create_index(op.f('ix_offboarding_runs_undone_at'), 'offboarding_runs', ['undone_at'], unique=False)
    op.create_index(op.f('ix_offboarding_runs_user_id'), 'offboarding_runs', ['user_id'], unique=False)
    op.create_index('ux_offboarding_runs_open_user', 'offboarding_runs', ['user_id'], unique=True, postgresql_where=sa.text('undone_at IS NULL'))
    op.create_table('password_reset_tokens',
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('purpose', sa.String(length=32), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('used_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('created_ip', sa.String(length=64), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    op.create_index(op.f('ix_password_reset_tokens_expires_at'), 'password_reset_tokens', ['expires_at'], unique=False)
    op.create_index(op.f('ix_password_reset_tokens_user_id'), 'password_reset_tokens', ['user_id'], unique=False)
    op.create_table('projects',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('dept_id', sa.String(length=36), nullable=True),
    sa.Column('owner_user_id', sa.String(length=36), nullable=True),
    sa.Column('starts_on', sa.String(length=40), nullable=True),
    sa.Column('ends_on', sa.String(length=40), nullable=True),
    sa.Column('goal', sa.Text(), nullable=True),
    sa.Column('biz_type', sa.String(length=200), nullable=True),
    sa.Column('product', sa.String(length=200), nullable=True),
    sa.Column('progress_pct', sa.Float(), nullable=True),
    sa.Column('health_score', sa.Integer(), nullable=True),
    sa.Column('archived_at', sa.DateTime(), nullable=True),
    sa.Column('notion_page_id', sa.String(length=64), nullable=True),
    sa.Column('notion_progress_pct', sa.Float(), nullable=True),
    sa.Column('notion_status', sa.String(length=64), nullable=True),
    sa.Column('notion_owner_ids', sa.Text(), nullable=False),
    sa.Column('notion_missing_at', sa.DateTime(), nullable=True),
    sa.Column('notion_last_edited', sa.String(length=40), nullable=True),
    sa.Column('notion_synced_at', sa.DateTime(), nullable=True),
    sa.Column('notion_sync_error', sa.Text(), nullable=True),
    sa.Column('org_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['dept_id'], ['departments.id'], ),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_projects_archived_at'), 'projects', ['archived_at'], unique=False)
    op.create_index(op.f('ix_projects_dept_id'), 'projects', ['dept_id'], unique=False)
    op.create_index(op.f('ix_projects_notion_missing_at'), 'projects', ['notion_missing_at'], unique=False)
    op.create_index(op.f('ix_projects_notion_page_id'), 'projects', ['notion_page_id'], unique=True)
    op.create_index(op.f('ix_projects_org_id'), 'projects', ['org_id'], unique=False)
    op.create_index(op.f('ix_projects_owner_user_id'), 'projects', ['owner_user_id'], unique=False)
    op.create_index('uq_projects_org_code', 'projects', ['org_id', 'code'], unique=True)
    op.create_table('saved_views',
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('screen_key', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('query', sa.Text(), server_default='', nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'screen_key', 'name', name='uq_saved_views_user_screen_name')
    )
    op.create_table('sessions',
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('csrf_token', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('revoked_at', sa.DateTime(), nullable=True),
    sa.Column('client_ip', sa.String(length=64), nullable=True),
    sa.Column('user_agent', sa.String(length=255), nullable=True),
    sa.Column('impersonated_user_id', sa.String(length=36), nullable=True),
    sa.Column('impersonation_id', sa.String(length=36), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sessions_token_hash'), 'sessions', ['token_hash'], unique=True)
    op.create_index(op.f('ix_sessions_user_id'), 'sessions', ['user_id'], unique=False)
    op.create_table('user_notion_mappings',
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('notion_user_id', sa.String(length=64), nullable=True),
    sa.Column('notion_email', sa.String(length=255), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('source', sa.String(length=16), nullable=True),
    sa.Column('last_verified_at', sa.DateTime(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('candidates_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_notion_mappings_user_id'), 'user_notion_mappings', ['user_id'], unique=True)
    op.create_table('user_preferences',
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('avatar_stored_name', sa.String(length=64), nullable=True),
    sa.Column('avatar_media_type', sa.String(length=64), nullable=True),
    sa.Column('avatar_updated_at', sa.DateTime(), nullable=True),
    sa.Column('muted_types', sa.Text(), server_default='', nullable=False),
    sa.Column('dnd_enabled', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('dnd_until', sa.DateTime(), nullable=True),
    sa.Column('quiet_hours_enabled', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('quiet_start', sa.String(length=5), server_default='22:00', nullable=False),
    sa.Column('quiet_end', sa.String(length=5), server_default='08:00', nullable=False),
    sa.Column('tour_seen_version', sa.Integer(), server_default='0', nullable=False),
    sa.Column('tour_skipped', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('tour_completed_at', sa.DateTime(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id')
    )
    op.create_table('board_attachments',
    sa.Column('post_id', sa.String(length=36), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('stored_name', sa.String(length=255), nullable=False),
    sa.Column('media_type', sa.String(length=100), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['post_id'], ['board_posts.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_board_attachments_post_id'), 'board_attachments', ['post_id'], unique=False)
    op.create_table('board_comments',
    sa.Column('post_id', sa.String(length=36), nullable=False),
    sa.Column('author_user_id', sa.String(length=36), nullable=False),
    sa.Column('parent_comment_id', sa.String(length=36), nullable=True),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['author_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['parent_comment_id'], ['board_comments.id'], ),
    sa.ForeignKeyConstraint(['post_id'], ['board_posts.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_board_comments_author_user_id'), 'board_comments', ['author_user_id'], unique=False)
    op.create_index(op.f('ix_board_comments_deleted_at'), 'board_comments', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_board_comments_parent_comment_id'), 'board_comments', ['parent_comment_id'], unique=False)
    op.create_index(op.f('ix_board_comments_post_id'), 'board_comments', ['post_id'], unique=False)
    op.create_table('document_cache',
    sa.Column('owner_kind', sa.String(length=16), server_default='unset', nullable=False),
    sa.Column('owner_dept_id', sa.String(length=36), nullable=True),
    sa.Column('owner_project_id', sa.String(length=36), nullable=True),
    sa.Column('notion_page_id', sa.String(length=64), nullable=False),
    sa.Column('url', sa.String(length=500), nullable=True),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('type_names', sa.Text(), nullable=False),
    sa.Column('category_names', sa.Text(), nullable=False),
    sa.Column('project_names', sa.Text(), nullable=False),
    sa.Column('project_external_ids', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=64), nullable=True),
    sa.Column('priority', sa.String(length=64), nullable=True),
    sa.Column('document_type', sa.String(length=32), nullable=True),
    sa.Column('work_field', sa.String(length=32), nullable=True),
    sa.Column('tech_tags', sa.Text(), nullable=False),
    sa.Column('classification_manual', sa.Boolean(), nullable=False),
    sa.Column('restricted', sa.Boolean(), nullable=False),
    sa.Column('author_names', sa.Text(), nullable=False),
    sa.Column('author_notion_ids', sa.Text(), nullable=False),
    sa.Column('owner', sa.String(length=255), nullable=False),
    sa.Column('doc_date', sa.String(length=40), nullable=True),
    sa.Column('orig_date', sa.String(length=40), nullable=True),
    sa.Column('created_time', sa.String(length=40), nullable=True),
    sa.Column('last_edited', sa.String(length=40), nullable=True),
    sa.Column('original_url', sa.String(length=1000), nullable=True),
    sa.Column('source_url', sa.String(length=1000), nullable=True),
    sa.Column('memo', sa.Text(), nullable=False),
    sa.Column('has_files', sa.Boolean(), nullable=False),
    sa.Column('notion_favorite', sa.Boolean(), nullable=False),
    sa.Column('archived', sa.Boolean(), nullable=False),
    sa.Column('synced_at', sa.DateTime(), nullable=False),
    sa.Column('body_markdown', sa.Text(), nullable=True),
    sa.Column('body_sync_error', sa.Text(), nullable=True),
    sa.Column('body_synced_at', sa.DateTime(), nullable=True),
    sa.Column('org_id', sa.String(length=36), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['owner_dept_id'], ['departments.id'], ),
    sa.ForeignKeyConstraint(['owner_project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_document_cache_archived'), 'document_cache', ['archived'], unique=False)
    op.create_index(op.f('ix_document_cache_document_type'), 'document_cache', ['document_type'], unique=False)
    op.create_index(op.f('ix_document_cache_notion_page_id'), 'document_cache', ['notion_page_id'], unique=True)
    op.create_index(op.f('ix_document_cache_org_id'), 'document_cache', ['org_id'], unique=False)
    op.create_index(op.f('ix_document_cache_owner_dept_id'), 'document_cache', ['owner_dept_id'], unique=False)
    op.create_index(op.f('ix_document_cache_owner_kind'), 'document_cache', ['owner_kind'], unique=False)
    op.create_index(op.f('ix_document_cache_owner_project_id'), 'document_cache', ['owner_project_id'], unique=False)
    op.create_index(op.f('ix_document_cache_restricted'), 'document_cache', ['restricted'], unique=False)
    op.create_index(op.f('ix_document_cache_status'), 'document_cache', ['status'], unique=False)
    op.create_index(op.f('ix_document_cache_work_field'), 'document_cache', ['work_field'], unique=False)
    op.create_table('messages',
    sa.Column('conversation_id', sa.String(length=36), nullable=False),
    sa.Column('message_id', sa.String(length=128), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('structured_payload_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('processing_status', sa.String(length=16), nullable=False),
    sa.Column('error_code', sa.String(length=64), nullable=True),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.Column('feedback', sa.String(length=16), nullable=True),
    sa.Column('seq', sa.BigInteger(), sa.Identity(always=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('conversation_id', 'message_id', name='uq_messages_conversation_message_id')
    )
    op.create_index(op.f('ix_messages_conversation_id'), 'messages', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_messages_deleted_at'), 'messages', ['deleted_at'], unique=False)
    op.create_table('offboarding_ticket_moves',
    sa.Column('run_id', sa.String(length=36), nullable=False),
    sa.Column('ticket_page_id', sa.String(length=64), nullable=False),
    sa.Column('ticket_uid', sa.String(length=36), nullable=True),
    sa.Column('ticket_number', sa.Integer(), nullable=True),
    sa.Column('ticket_title', sa.String(length=500), nullable=False),
    sa.Column('before_user_ids', sa.Text(), nullable=False),
    sa.Column('after_user_ids', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('reverted_at', sa.DateTime(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['offboarding_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_offboarding_ticket_moves_run_id'), 'offboarding_ticket_moves', ['run_id'], unique=False)
    op.create_index(op.f('ix_offboarding_ticket_moves_ticket_page_id'), 'offboarding_ticket_moves', ['ticket_page_id'], unique=False)
    op.create_table('project_health_snapshots',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('week_of', sa.String(length=10), nullable=False),
    sa.Column('score', sa.Integer(), nullable=False),
    sa.Column('reasons_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_project_health_snapshots_project_id'), 'project_health_snapshots', ['project_id'], unique=False)
    op.create_index('uq_project_health_snapshots_week', 'project_health_snapshots', ['project_id', 'week_of'], unique=True)
    op.create_table('project_members',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_project_members_project_id'), 'project_members', ['project_id'], unique=False)
    op.create_index(op.f('ix_project_members_user_id'), 'project_members', ['user_id'], unique=False)
    op.create_index('uq_project_members', 'project_members', ['project_id', 'user_id'], unique=True)
    op.create_table('project_milestones',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('due_on', sa.String(length=40), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_project_milestones_project_id'), 'project_milestones', ['project_id'], unique=False)
    op.create_table('project_weekly_reports',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('week_of', sa.String(length=10), nullable=False),
    sa.Column('summary_md', sa.Text(), nullable=False),
    sa.Column('source', sa.String(length=8), nullable=False),
    sa.Column('generated_at', sa.DateTime(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_project_weekly_reports_project_id'), 'project_weekly_reports', ['project_id'], unique=False)
    op.create_index('uq_project_weekly_reports_week', 'project_weekly_reports', ['project_id', 'week_of'], unique=True)
    op.create_table('ticket_cache',
    sa.Column('notion_page_id', sa.String(length=64), nullable=True),
    sa.Column('notion_missing_at', sa.DateTime(), nullable=True),
    sa.Column('parent_page_id', sa.String(length=64), nullable=True),
    sa.Column('project_uid', sa.String(length=36), nullable=True),
    sa.Column('project_link', sa.String(length=16), server_default='unresolved', nullable=False),
    sa.Column('notion_ticket_number', sa.Integer(), nullable=True),
    sa.Column('url', sa.String(length=500), nullable=True),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('status', sa.String(length=64), nullable=True),
    sa.Column('priority', sa.String(length=64), nullable=True),
    sa.Column('difficulty', sa.String(length=64), nullable=True),
    sa.Column('est_wd', sa.Float(), nullable=True),
    sa.Column('act_wd', sa.Float(), nullable=True),
    sa.Column('due_date', sa.String(length=40), nullable=True),
    sa.Column('start_date', sa.String(length=40), nullable=True),
    sa.Column('category', sa.String(length=200), nullable=True),
    sa.Column('project_ids', sa.Text(), nullable=False),
    sa.Column('project_names', sa.Text(), nullable=False),
    sa.Column('assignee_notion_ids', sa.Text(), nullable=False),
    sa.Column('body_markdown', sa.Text(), nullable=True),
    sa.Column('body_synced_at', sa.DateTime(), nullable=True),
    sa.Column('body_sync_error', sa.Text(), nullable=True),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('notion_created_time', sa.String(length=40), nullable=True),
    sa.Column('notion_last_edited', sa.String(length=40), nullable=True),
    sa.Column('synced_at', sa.DateTime(), nullable=False),
    sa.Column('org_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['project_uid'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ticket_cache_due_date'), 'ticket_cache', ['due_date'], unique=False)
    op.create_index(op.f('ix_ticket_cache_notion_missing_at'), 'ticket_cache', ['notion_missing_at'], unique=False)
    op.create_index(op.f('ix_ticket_cache_notion_page_id'), 'ticket_cache', ['notion_page_id'], unique=True)
    op.create_index(op.f('ix_ticket_cache_org_id'), 'ticket_cache', ['org_id'], unique=False)
    op.create_index(op.f('ix_ticket_cache_parent_page_id'), 'ticket_cache', ['parent_page_id'], unique=False)
    op.create_index(op.f('ix_ticket_cache_project_link'), 'ticket_cache', ['project_link'], unique=False)
    op.create_index(op.f('ix_ticket_cache_project_uid'), 'ticket_cache', ['project_uid'], unique=False)
    op.create_index(op.f('ix_ticket_cache_status'), 'ticket_cache', ['status'], unique=False)
    op.create_table('document_comments',
    sa.Column('notion_page_id', sa.String(length=64), nullable=False),
    sa.Column('document_id', sa.String(length=36), nullable=True),
    sa.Column('author_user_id', sa.String(length=36), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.Column('seq', sa.BigInteger(), sa.Identity(always=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['author_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['document_id'], ['document_cache.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_document_comments_author_user_id'), 'document_comments', ['author_user_id'], unique=False)
    op.create_index(op.f('ix_document_comments_deleted_at'), 'document_comments', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_document_comments_document_id'), 'document_comments', ['document_id'], unique=False)
    op.create_index(op.f('ix_document_comments_notion_page_id'), 'document_comments', ['notion_page_id'], unique=False)
    op.create_table('ticket_attachments',
    sa.Column('ticket_uid', sa.String(length=36), nullable=False),
    sa.Column('uploaded_by_user_id', sa.String(length=36), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('stored_name', sa.String(length=255), nullable=False),
    sa.Column('media_type', sa.String(length=100), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['ticket_uid'], ['ticket_cache.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['uploaded_by_user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ticket_attachments_ticket_uid'), 'ticket_attachments', ['ticket_uid'], unique=False)
    op.create_index(op.f('ix_ticket_attachments_uploaded_by_user_id'), 'ticket_attachments', ['uploaded_by_user_id'], unique=False)
    op.create_table('ticket_comments',
    sa.Column('ticket_uid', sa.String(length=36), nullable=False),
    sa.Column('author_user_id', sa.String(length=36), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.Column('seq', sa.BigInteger(), sa.Identity(always=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['author_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['ticket_uid'], ['ticket_cache.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ticket_comments_author_user_id'), 'ticket_comments', ['author_user_id'], unique=False)
    op.create_index(op.f('ix_ticket_comments_deleted_at'), 'ticket_comments', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_ticket_comments_ticket_uid'), 'ticket_comments', ['ticket_uid'], unique=False)

    # ── 부트스트랩 행 ────────────────────────────────────────────────────────
    #
    # 스키마만 만들면 앱이 안 뜬다. 옛 체인이 **표를 만들면서 함께 심던** 행들이고,
    # 없으면 각각 이렇게 깨진다:
    #
    #   * `organizations` — 거의 모든 표의 `org_id` 가 이 행을 FK 로 가리킨다
    #     (`OrgScopedMixin` 의 기본값). 없으면 **첫 INSERT 부터** FK 위반이다.
    #   * `document_sync_state` · `ticket_sync_state` · `ticket_meta_cache` — 싱글턴이다.
    #     없으면 첫 조회가 insert-if-absent 를 하다가 동시 요청에서 유니크 충돌로 500 이 난다.
    #   * `chat_rooms` 전체 방 — 채팅 화면이 이 방을 전제로 연다.
    #
    # 옛 체인에서 데이터를 옮기던 revision(0015 의 부서/직급 승격, 0038 의 부서 계층
    # 정정)은 **여기 없다.** 그것들은 이미 있는 행을 보고 움직이는 코드라 새 설치에서는
    # 아무 일도 하지 않았다. 이관은 Migration Tool 의 일이다(S13).
    #
    # ⚠️ 컬럼을 **전부** 적는다. 원시 SQL INSERT 는 모델의 파이썬 기본값(`default=`)을
    # 쓰지 않는다 — `server_default` 가 없는 NOT NULL 컬럼을 빠뜨리면 그 자리에서
    # NOT NULL 위반이 난다(`pruned_count` 가 실제로 그랬다).
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO organizations (id, slug, name, status, created_at, updated_at)"
            " VALUES (:id, :slug, :name, 'active', :now, :now)"
        ),
        {"id": _DEFAULT_ORG_ID, "slug": _DEFAULT_ORG_SLUG, "name": _DEFAULT_ORG_NAME, "now": now},
    )
    bind.execute(
        sa.text(
            "INSERT INTO document_sync_state"
            " (id, status, doc_count, pruned_count, updated_at)"
            " VALUES (:id, 'idle', 0, 0, :now)"
        ),
        {"id": _DOCUMENT_SYNC_ID, "now": now},
    )
    bind.execute(
        sa.text(
            "INSERT INTO ticket_sync_state"
            " (id, status, ticket_count, truncated, pruned_count, updated_at)"
            " VALUES (:id, 'idle', 0, false, 0, :now)"
        ),
        {"id": _TICKET_SINGLETON_ID, "now": now},
    )
    bind.execute(
        sa.text(
            "INSERT INTO ticket_meta_cache"
            " (id, statuses, priorities, difficulties, projects_json, updated_at)"
            " VALUES (:id, '', '', '', '[]', :now)"
        ),
        {"id": _TICKET_SINGLETON_ID, "now": now},
    )
    bind.execute(
        sa.text(
            "INSERT INTO chat_rooms"
            " (id, kind, title, is_global, dm_key, event_seq, org_id, created_at, updated_at)"
            " VALUES (:id, 'group', :title, true, NULL, 0, :org, :now, :now)"
        ),
        {"id": _GLOBAL_CHAT_ROOM_ID, "title": "전체 채팅", "org": _DEFAULT_ORG_ID, "now": now},
    )


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_ticket_comments_ticket_uid'), table_name='ticket_comments')
    op.drop_index(op.f('ix_ticket_comments_deleted_at'), table_name='ticket_comments')
    op.drop_index(op.f('ix_ticket_comments_author_user_id'), table_name='ticket_comments')
    op.drop_table('ticket_comments')
    op.drop_index(op.f('ix_ticket_attachments_uploaded_by_user_id'), table_name='ticket_attachments')
    op.drop_index(op.f('ix_ticket_attachments_ticket_uid'), table_name='ticket_attachments')
    op.drop_table('ticket_attachments')
    op.drop_index(op.f('ix_document_comments_notion_page_id'), table_name='document_comments')
    op.drop_index(op.f('ix_document_comments_document_id'), table_name='document_comments')
    op.drop_index(op.f('ix_document_comments_deleted_at'), table_name='document_comments')
    op.drop_index(op.f('ix_document_comments_author_user_id'), table_name='document_comments')
    op.drop_table('document_comments')
    op.drop_index(op.f('ix_ticket_cache_status'), table_name='ticket_cache')
    op.drop_index(op.f('ix_ticket_cache_project_uid'), table_name='ticket_cache')
    op.drop_index(op.f('ix_ticket_cache_project_link'), table_name='ticket_cache')
    op.drop_index(op.f('ix_ticket_cache_parent_page_id'), table_name='ticket_cache')
    op.drop_index(op.f('ix_ticket_cache_org_id'), table_name='ticket_cache')
    op.drop_index(op.f('ix_ticket_cache_notion_page_id'), table_name='ticket_cache')
    op.drop_index(op.f('ix_ticket_cache_notion_missing_at'), table_name='ticket_cache')
    op.drop_index(op.f('ix_ticket_cache_due_date'), table_name='ticket_cache')
    op.drop_table('ticket_cache')
    op.drop_index('uq_project_weekly_reports_week', table_name='project_weekly_reports')
    op.drop_index(op.f('ix_project_weekly_reports_project_id'), table_name='project_weekly_reports')
    op.drop_table('project_weekly_reports')
    op.drop_index(op.f('ix_project_milestones_project_id'), table_name='project_milestones')
    op.drop_table('project_milestones')
    op.drop_index('uq_project_members', table_name='project_members')
    op.drop_index(op.f('ix_project_members_user_id'), table_name='project_members')
    op.drop_index(op.f('ix_project_members_project_id'), table_name='project_members')
    op.drop_table('project_members')
    op.drop_index('uq_project_health_snapshots_week', table_name='project_health_snapshots')
    op.drop_index(op.f('ix_project_health_snapshots_project_id'), table_name='project_health_snapshots')
    op.drop_table('project_health_snapshots')
    op.drop_index(op.f('ix_offboarding_ticket_moves_ticket_page_id'), table_name='offboarding_ticket_moves')
    op.drop_index(op.f('ix_offboarding_ticket_moves_run_id'), table_name='offboarding_ticket_moves')
    op.drop_table('offboarding_ticket_moves')
    op.drop_index(op.f('ix_messages_deleted_at'), table_name='messages')
    op.drop_index(op.f('ix_messages_conversation_id'), table_name='messages')
    op.drop_table('messages')
    op.drop_index(op.f('ix_document_cache_work_field'), table_name='document_cache')
    op.drop_index(op.f('ix_document_cache_status'), table_name='document_cache')
    op.drop_index(op.f('ix_document_cache_restricted'), table_name='document_cache')
    op.drop_index(op.f('ix_document_cache_owner_project_id'), table_name='document_cache')
    op.drop_index(op.f('ix_document_cache_owner_kind'), table_name='document_cache')
    op.drop_index(op.f('ix_document_cache_owner_dept_id'), table_name='document_cache')
    op.drop_index(op.f('ix_document_cache_org_id'), table_name='document_cache')
    op.drop_index(op.f('ix_document_cache_notion_page_id'), table_name='document_cache')
    op.drop_index(op.f('ix_document_cache_document_type'), table_name='document_cache')
    op.drop_index(op.f('ix_document_cache_archived'), table_name='document_cache')
    op.drop_table('document_cache')
    op.drop_index(op.f('ix_board_comments_post_id'), table_name='board_comments')
    op.drop_index(op.f('ix_board_comments_parent_comment_id'), table_name='board_comments')
    op.drop_index(op.f('ix_board_comments_deleted_at'), table_name='board_comments')
    op.drop_index(op.f('ix_board_comments_author_user_id'), table_name='board_comments')
    op.drop_table('board_comments')
    op.drop_index(op.f('ix_board_attachments_post_id'), table_name='board_attachments')
    op.drop_table('board_attachments')
    op.drop_table('user_preferences')
    op.drop_index(op.f('ix_user_notion_mappings_user_id'), table_name='user_notion_mappings')
    op.drop_table('user_notion_mappings')
    op.drop_index(op.f('ix_sessions_user_id'), table_name='sessions')
    op.drop_index(op.f('ix_sessions_token_hash'), table_name='sessions')
    op.drop_table('sessions')
    op.drop_table('saved_views')
    op.drop_index('uq_projects_org_code', table_name='projects')
    op.drop_index(op.f('ix_projects_owner_user_id'), table_name='projects')
    op.drop_index(op.f('ix_projects_org_id'), table_name='projects')
    op.drop_index(op.f('ix_projects_notion_page_id'), table_name='projects')
    op.drop_index(op.f('ix_projects_notion_missing_at'), table_name='projects')
    op.drop_index(op.f('ix_projects_dept_id'), table_name='projects')
    op.drop_index(op.f('ix_projects_archived_at'), table_name='projects')
    op.drop_table('projects')
    op.drop_index(op.f('ix_password_reset_tokens_user_id'), table_name='password_reset_tokens')
    op.drop_index(op.f('ix_password_reset_tokens_expires_at'), table_name='password_reset_tokens')
    op.drop_table('password_reset_tokens')
    op.drop_index('ux_offboarding_runs_open_user', table_name='offboarding_runs', postgresql_where=sa.text('undone_at IS NULL'))
    op.drop_index(op.f('ix_offboarding_runs_user_id'), table_name='offboarding_runs')
    op.drop_index(op.f('ix_offboarding_runs_undone_at'), table_name='offboarding_runs')
    op.drop_index(op.f('ix_offboarding_runs_org_id'), table_name='offboarding_runs')
    op.drop_index(op.f('ix_offboarding_runs_actor_user_id'), table_name='offboarding_runs')
    op.drop_table('offboarding_runs')
    op.drop_index(op.f('ix_conversations_user_id'), table_name='conversations')
    op.drop_index('ix_conversations_updated_at', table_name='conversations')
    op.drop_table('conversations')
    op.drop_index(op.f('ix_chat_message_images_room_id'), table_name='chat_message_images')
    op.drop_index(op.f('ix_chat_message_images_message_id'), table_name='chat_message_images')
    op.drop_table('chat_message_images')
    op.drop_index(op.f('ix_board_reactions_target_id'), table_name='board_reactions')
    op.drop_table('board_reactions')
    op.drop_index(op.f('ix_board_posts_ticket_page_id'), table_name='board_posts')
    op.drop_index(op.f('ix_board_posts_org_id'), table_name='board_posts')
    op.drop_index(op.f('ix_board_posts_kind'), table_name='board_posts')
    op.drop_index(op.f('ix_board_posts_is_pinned'), table_name='board_posts')
    op.drop_index(op.f('ix_board_posts_idea_status'), table_name='board_posts')
    op.drop_index(op.f('ix_board_posts_deleted_at'), table_name='board_posts')
    op.drop_index('ix_board_posts_created_at', table_name='board_posts')
    op.drop_index(op.f('ix_board_posts_category'), table_name='board_posts')
    op.drop_index(op.f('ix_board_posts_author_user_id'), table_name='board_posts')
    op.drop_table('board_posts')
    op.drop_index(op.f('ix_users_org_id'), table_name='users')
    op.drop_index(op.f('ix_users_membership_kind'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_index(op.f('ix_users_archived_at'), table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_game_room_members_room_id'), table_name='game_room_members')
    op.drop_table('game_room_members')
    op.drop_index(op.f('ix_game_events_seq'), table_name='game_events')
    op.drop_index(op.f('ix_game_events_room_id'), table_name='game_events')
    op.drop_table('game_events')
    op.drop_index(op.f('ix_chat_room_members_user_id'), table_name='chat_room_members')
    op.drop_index(op.f('ix_chat_room_members_room_id'), table_name='chat_room_members')
    op.drop_table('chat_room_members')
    op.drop_index(op.f('ix_chat_read_cursors_user_id'), table_name='chat_read_cursors')
    op.drop_index(op.f('ix_chat_read_cursors_room_id'), table_name='chat_read_cursors')
    op.drop_table('chat_read_cursors')
    op.drop_index(op.f('ix_chat_messages_seq'), table_name='chat_messages')
    op.drop_index(op.f('ix_chat_messages_room_id'), table_name='chat_messages')
    op.drop_table('chat_messages')
    op.drop_index(op.f('ix_usage_events_user_id'), table_name='usage_events')
    op.drop_index(op.f('ix_usage_events_org_id'), table_name='usage_events')
    op.drop_index(op.f('ix_usage_events_event'), table_name='usage_events')
    op.drop_index(op.f('ix_usage_events_created_at'), table_name='usage_events')
    op.drop_table('usage_events')
    op.drop_index(op.f('ix_trash_items_target_uid'), table_name='trash_items')
    op.drop_index(op.f('ix_trash_items_org_id'), table_name='trash_items')
    op.drop_index(op.f('ix_trash_items_notion_page_id'), table_name='trash_items')
    op.drop_index(op.f('ix_trash_items_item_type'), table_name='trash_items')
    op.drop_index(op.f('ix_trash_items_deleted_at'), table_name='trash_items')
    op.drop_table('trash_items')
    op.drop_index('ix_search_documents_title_trgm', table_name='search_documents', postgresql_using='gin', postgresql_ops={'title': 'gin_trgm_ops'})
    op.drop_index(op.f('ix_search_documents_org_id'), table_name='search_documents')
    op.drop_index(op.f('ix_search_documents_kind'), table_name='search_documents')
    op.drop_index('ix_search_documents_body_trgm', table_name='search_documents', postgresql_using='gin', postgresql_ops={'body': 'gin_trgm_ops'})
    op.drop_table('search_documents')
    op.drop_index(op.f('ix_job_titles_org_id'), table_name='job_titles')
    op.drop_index(op.f('ix_job_titles_name'), table_name='job_titles')
    op.drop_table('job_titles')
    op.drop_index(op.f('ix_game_rooms_status'), table_name='game_rooms')
    op.drop_index(op.f('ix_game_rooms_org_id'), table_name='game_rooms')
    op.drop_index(op.f('ix_game_rooms_host_user_id'), table_name='game_rooms')
    op.drop_index(op.f('ix_game_rooms_closed_at'), table_name='game_rooms')
    op.drop_table('game_rooms')
    op.drop_index('uq_departments_org_name', table_name='departments')
    op.drop_index(op.f('ix_departments_parent_id'), table_name='departments')
    op.drop_index(op.f('ix_departments_org_id'), table_name='departments')
    op.drop_index(op.f('ix_departments_name'), table_name='departments')
    op.drop_table('departments')
    op.drop_index(op.f('ix_chat_rooms_org_id'), table_name='chat_rooms')
    op.drop_index(op.f('ix_chat_rooms_kind'), table_name='chat_rooms')
    op.drop_index(op.f('ix_chat_rooms_department_id'), table_name='chat_rooms')
    op.drop_index(op.f('ix_chat_rooms_deleted_at'), table_name='chat_rooms')
    op.drop_table('chat_rooms')
    op.drop_index(op.f('ix_announcement_dismissals_user_id'), table_name='announcement_dismissals')
    op.drop_table('announcement_dismissals')
    op.drop_index(op.f('ix_workflows_name'), table_name='workflows')
    op.drop_table('workflows')
    op.drop_table('ticket_sync_state')
    op.drop_table('ticket_meta_cache')
    op.drop_table('sync_status')
    op.drop_index(op.f('ix_schedules_next_run_at'), table_name='schedules')
    op.drop_table('schedules')
    op.drop_index(op.f('ix_schedule_runs_schedule_id'), table_name='schedule_runs')
    op.drop_index('ix_schedule_runs_created_at', table_name='schedule_runs')
    op.drop_table('schedule_runs')
    op.drop_index(op.f('ix_runners_name'), table_name='runners')
    op.drop_table('runners')
    op.drop_index(op.f('ix_restore_rehearsals_started_at'), table_name='restore_rehearsals')
    op.drop_table('restore_rehearsals')
    op.drop_index(op.f('ix_rate_limit_buckets_updated_at'), table_name='rate_limit_buckets')
    op.drop_table('rate_limit_buckets')
    op.drop_index('ux_prompts_published_dedup', table_name='prompts', postgresql_where=sa.text("status = 'published'"))
    op.drop_index(op.f('ix_prompts_name'), table_name='prompts')
    op.drop_table('prompts')
    op.drop_table('project_sync_state')
    op.drop_index('ux_policies_published_dedup', table_name='policies', postgresql_where=sa.text("status = 'published'"))
    op.drop_index(op.f('ix_policies_name'), table_name='policies')
    op.drop_table('policies')
    op.drop_index(op.f('ix_organizations_slug'), table_name='organizations')
    op.drop_table('organizations')
    op.drop_index('ix_notifications_user_unread', table_name='notifications')
    op.drop_index(op.f('ix_notifications_user_id'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_created_at'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_audience'), table_name='notifications')
    op.drop_table('notifications')
    op.drop_index(op.f('ix_mail_deliveries_status'), table_name='mail_deliveries')
    op.drop_index(op.f('ix_mail_deliveries_kind'), table_name='mail_deliveries')
    op.drop_index('ix_mail_deliveries_created_at', table_name='mail_deliveries')
    op.drop_table('mail_deliveries')
    op.drop_index(op.f('ix_jobs_user_id'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_status'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_job_type'), table_name='jobs')
    op.drop_index('ix_jobs_claim', table_name='jobs')
    op.drop_index(op.f('ix_jobs_available_at'), table_name='jobs')
    op.drop_table('jobs')
    op.drop_index(op.f('ix_integrations_name'), table_name='integrations')
    op.drop_table('integrations')
    op.drop_index(op.f('ix_impersonation_sessions_target_user_id'), table_name='impersonation_sessions')
    op.drop_index(op.f('ix_impersonation_sessions_started_at'), table_name='impersonation_sessions')
    op.drop_index(op.f('ix_impersonation_sessions_actor_user_id'), table_name='impersonation_sessions')
    op.drop_table('impersonation_sessions')
    op.drop_table('heartbeats')
    op.drop_table('document_sync_state')
    op.drop_index(op.f('ix_document_recent_views_user_id'), table_name='document_recent_views')
    op.drop_index(op.f('ix_document_recent_views_document_id'), table_name='document_recent_views')
    op.drop_table('document_recent_views')
    op.drop_table('document_generations')
    op.drop_index(op.f('ix_document_favorites_user_id'), table_name='document_favorites')
    op.drop_index(op.f('ix_document_favorites_document_id'), table_name='document_favorites')
    op.drop_table('document_favorites')
    op.drop_index('uq_config_versions_object_version', table_name='config_versions')
    op.drop_index(op.f('ix_config_versions_object_type'), table_name='config_versions')
    op.drop_index(op.f('ix_config_versions_object_id'), table_name='config_versions')
    op.drop_table('config_versions')
    op.drop_table('backups')
    op.drop_index(op.f('ix_automation_templates_name'), table_name='automation_templates')
    op.drop_table('automation_templates')
    op.drop_index(op.f('ix_audit_logs_user_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_object_type'), table_name='audit_logs')
    op.drop_index('ix_audit_logs_object_id', table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_created_at'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_action'), table_name='audit_logs')
    op.drop_table('audit_logs')
    op.drop_index('ux_approvals_pending_dedup', table_name='approvals', postgresql_where=sa.text("status = 'pending'"))
    op.drop_index(op.f('ix_approvals_status'), table_name='approvals')
    op.drop_index(op.f('ix_approvals_request_type'), table_name='approvals')
    op.drop_table('approvals')
    op.drop_index(op.f('ix_approval_delegations_delegator_user_id'), table_name='approval_delegations')
    op.drop_index(op.f('ix_approval_delegations_delegate_user_id'), table_name='approval_delegations')
    op.drop_table('approval_delegations')
    op.drop_table('app_settings')
    op.drop_index(op.f('ix_announcements_active'), table_name='announcements')
    op.drop_table('announcements')
    op.drop_table('ai_quotas')
