"""관리자 백로그 잔여 (PLAN Phase 6) — 임퍼소네이션·승인 위임/SLA·공지·AI 쿼터·복구 리허설 기록

Revision ID: 0033
Revises: 0032
Create Date: 2026-08-03

여기서 만드는 것: 표 6개(`impersonation_sessions`, `approval_delegations`, `announcements`,
`announcement_dismissals`, `ai_quotas`, `restore_rehearsals`)와 기존 표 두 곳에 붙는 칸
(`sessions` 2개, `approvals` 3개).

한 마이그레이션에 몰아넣는 이유: 전부 **같은 배포 단위**다(관리자 콘솔 백로그 한 묶음).
표마다 리비전을 쪼개면 down_revision 사슬만 여섯 칸 길어지고, 되돌릴 때 여섯 번 내려야
한다. 반대로 서로 참조하지 않으므로 한 번에 올리고 한 번에 내려도 안전하다.

**감사 '저장 필터'를 위한 표는 만들지 않는다.** 0032 의 `saved_views` 가 이미 화면별·
사용자별로 쿼리 문자열을 저장하고, `DataScreen` 이 모든 화면(감사 로그 포함)에 그 컨트롤을
그린다. 같은 일을 하는 두 번째 저장소를 두면 어느 쪽이 정본인지 화면마다 달라진다 —
`app/core/feature_flags.py` 가 고쳤던 split-brain 과 정확히 같은 실수다.

**타임스탬프는 전부 파이썬에서 만들어 바인딩한다** — SQLite `STRFTIME('%f')` 는 이 저장소에서
과거에 부서 화면을 죽인 함정이라 금지돼 있다(CLAUDE.md §8). 이 마이그레이션은 애초에 기존
행을 채우지 않으므로 UPDATE 자체가 없다.

## sessions 에 두 칸을 더한다 (별도 표로 빼지 않는 이유)

임퍼소네이션 중인지 여부는 **모든 인증 요청**이 봐야 한다(`_load_auth`). 별도 표에만 두면
요청마다 조인이나 두 번째 조회가 생긴다. 그래서 세션 행에 `impersonated_user_id`(누구로
보고 있는가)와 `impersonation_id`(어느 기록인가)를 직접 둔다 — 둘 다 NULL 이면 평소 세션이다.
기록 자체(누가·누구로·언제·왜)는 `impersonation_sessions` 가 갖고, 감사 로그에도 남는다.

## ai_quotas.user_id 는 NULL 이 아니라 빈 문자열이다

SQLite 는 UNIQUE 에서 NULL 을 **서로 다른 값**으로 취급한다. 전역 쿼터를 `user_id IS NULL`
로 표현하면 `(scope_type, user_id, period)` 복합 유니크가 전역 행에 대해 무효가 되어
'하루 상한' 행이 여러 개 생긴다(그리고 어느 것이 적용되는지는 정렬 순서에 달린다).
0024 가 `org_id` 를 NULL 대신 실값으로 백필한 것과 같은 이유로, 여기서는 빈 문자열을 쓴다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. 읽기 전용 임퍼소네이션 ────────────────────────────────────────────
    op.create_table(
        "impersonation_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        # 계정이 보관·삭제돼도 "누가 누구로 봤는가"는 남아야 하므로 FK 를 걸지 않는다
        # (감사 로그와 같은 판단).
        sa.Column("actor_user_id", sa.String(36), nullable=False),
        sa.Column("target_user_id", sa.String(36), nullable=False),
        # 어느 세션에서 시작했는가. 세션이 만료돼 사라져도 기록은 남는다.
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("client_ip", sa.String(64), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        # 'manual' | 'logout' | 'target_unavailable' | 'expired'
        sa.Column("ended_reason", sa.String(32), nullable=True),
        sa.Column("read_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("blocked_write_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_impersonation_actor", "impersonation_sessions", ["actor_user_id"])
    op.create_index("ix_impersonation_target", "impersonation_sessions", ["target_user_id"])
    op.create_index("ix_impersonation_started_at", "impersonation_sessions", ["started_at"])

    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("impersonated_user_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("impersonation_id", sa.String(36), nullable=True))

    # ── 2. 승인 위임 + SLA ───────────────────────────────────────────────────
    op.create_table(
        "approval_delegations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("delegator_user_id", sa.String(36), nullable=False),
        sa.Column("delegate_user_id", sa.String(36), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_approval_deleg_delegate", "approval_delegations", ["delegate_user_id"])
    op.create_index("ix_approval_deleg_delegator", "approval_delegations", ["delegator_user_id"])

    with op.batch_alter_table("approvals") as batch:
        # 기한. NULL 이면 '기한 없음'이며 초과 표시 대상이 아니다 — 이미 존재하는 행을
        # 소급해서 '지났다'고 칠하지 않기 위해 백필하지 않는다.
        batch.add_column(sa.Column("due_at", sa.DateTime(), nullable=True))
        # 기한 초과 알림을 한 번만 보내기 위한 표식.
        batch.add_column(sa.Column("sla_notified_at", sa.DateTime(), nullable=True))
        # 위임으로 결재했다면 누구를 대신한 것인가.
        batch.add_column(sa.Column("decided_on_behalf_of", sa.String(36), nullable=True))

    # ── 3. 공지 배너 ─────────────────────────────────────────────────────────
    op.create_table(
        "announcements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        # 'info' | 'warning' | 'critical'
        sa.Column("level", sa.String(16), nullable=False, server_default="info"),
        # 'all' | 'admin' — 관리자 콘솔에만 띄우는 공지가 필요할 때.
        sa.Column("audience", sa.String(16), nullable=False, server_default="all"),
        sa.Column("starts_at", sa.DateTime(), nullable=True),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        # 닫을 수 없는 공지(예: 점검 예고)를 위한 스위치. 기본은 닫을 수 있다.
        sa.Column("dismissible", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("link_url", sa.String(500), nullable=True),
        sa.Column("link_label", sa.String(80), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_announcements_active", "announcements", ["active"])

    op.create_table(
        "announcement_dismissals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("announcement_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("dismissed_at", sa.DateTime(), nullable=False),
        # 같은 사람이 같은 공지를 두 번 닫아도 행은 하나다. 이 제약이 없으면 닫기
        # 요청이 중복 전송될 때(더블클릭·재시도) 행이 쌓인다.
        sa.UniqueConstraint("announcement_id", "user_id", name="uq_announcement_dismissal"),
    )
    op.create_index("ix_dismissals_user", "announcement_dismissals", ["user_id"])

    # ── 4. AI 쿼터 ───────────────────────────────────────────────────────────
    op.create_table(
        "ai_quotas",
        sa.Column("id", sa.String(36), primary_key=True),
        # 'global' | 'user'
        sa.Column("scope_type", sa.String(16), nullable=False),
        # 전역 행은 빈 문자열(모듈 docstring 참조 — NULL 이면 복합 유니크가 무효다).
        sa.Column("user_id", sa.String(36), nullable=False, server_default=""),
        # 'day' | 'month'
        sa.Column("period", sa.String(16), nullable=False),
        sa.Column("max_calls", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("scope_type", "user_id", "period", name="uq_ai_quota_scope"),
    )

    # ── 5. 복구 리허설 기록 ──────────────────────────────────────────────────
    op.create_table(
        "restore_rehearsals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_label", sa.String(200), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("failures_json", sa.Text(), nullable=True),
        sa.Column("summary_json", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_restore_rehearsals_started", "restore_rehearsals", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_restore_rehearsals_started", table_name="restore_rehearsals")
    op.drop_table("restore_rehearsals")

    op.drop_table("ai_quotas")

    op.drop_index("ix_dismissals_user", table_name="announcement_dismissals")
    op.drop_table("announcement_dismissals")
    op.drop_index("ix_announcements_active", table_name="announcements")
    op.drop_table("announcements")

    with op.batch_alter_table("approvals") as batch:
        batch.drop_column("decided_on_behalf_of")
        batch.drop_column("sla_notified_at")
        batch.drop_column("due_at")

    op.drop_index("ix_approval_deleg_delegator", table_name="approval_delegations")
    op.drop_index("ix_approval_deleg_delegate", table_name="approval_delegations")
    op.drop_table("approval_delegations")

    with op.batch_alter_table("sessions") as batch:
        batch.drop_column("impersonation_id")
        batch.drop_column("impersonated_user_id")

    op.drop_index("ix_impersonation_started_at", table_name="impersonation_sessions")
    op.drop_index("ix_impersonation_target", table_name="impersonation_sessions")
    op.drop_index("ix_impersonation_actor", table_name="impersonation_sessions")
    op.drop_table("impersonation_sessions")
