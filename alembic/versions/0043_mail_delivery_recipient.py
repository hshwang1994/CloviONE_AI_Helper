"""메일 발송 기록의 받는 사람 축과 실패 단계 (D-547 · D-546).

Revision ID: 0043_mail_delivery_recipient
Revises: 0042_smtp_password_slot

## 무엇이 바뀌나

- `mail_deliveries.recipient_user_id` (users.id, 지워지면 비움) + `(recipient_user_id, created_at)` 색인.
  발송 기록은 받는 주소 · 티켓 제목 · 알림 본문을 싣는데, 목록과 상세가 역할만 보고 범위를 보지 않아 부서 범위
  관리자 · 운영자 · 감사자가 다른 부서 사람의 메일을 읽었다. 이 칸이 범위로 거르는 축이다.
- `failure_stage` (String 16), `relay_response` (String 300) — 실패한 단계와 다음 서버의 마지막 응답.

## 옛 행 채우기

params 의 `user_id` 가 있는 사용자를 가리키면 그 사람이다(알림 · 초대 · 재설정). 없으면 받는 주소를 소문자로
사용자 이메일과 맞춘다(승인 요청 · 백업 실패 · 시험). 둘 다 못 맞추면 비워 둔다 - 그 행은 전역 관리자만 본다.
행 수가 많지 않은 표라(설치당 수천 행) 파이썬으로 한 번에 읽고 맞춘 것만 고쳐 쓴다.

## 되돌리기

칸 셋과 색인을 지운다. 채운 값은 함께 사라진다.
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa
from alembic import op

revision = "0043_mail_delivery_recipient"
down_revision = "0042_smtp_password_slot"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.0043")


def upgrade() -> None:
    op.add_column("mail_deliveries", sa.Column("recipient_user_id", sa.String(36), nullable=True))
    op.add_column("mail_deliveries", sa.Column("failure_stage", sa.String(16), nullable=True))
    op.add_column("mail_deliveries", sa.Column("relay_response", sa.String(300), nullable=True))
    op.create_foreign_key(
        "fk_mail_deliveries_recipient_user_id", "mail_deliveries", "users",
        ["recipient_user_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index(
        "ix_mail_deliveries_recipient_created", "mail_deliveries", ["recipient_user_id", "created_at"],
    )

    bind = op.get_bind()
    users = bind.execute(sa.text("SELECT id, email FROM users")).all()
    ids = {row[0] for row in users}
    by_email: dict[str, str] = {}
    for user_id, email in users:
        key = (email or "").strip().lower()
        if key:
            by_email.setdefault(key, user_id)

    matched = unmatched = 0
    rows = bind.execute(sa.text("SELECT id, to_email, params_json FROM mail_deliveries")).all()
    for delivery_id, to_email, params_json in rows:
        try:
            # 칸은 jsonb 라 드라이버가 dict 로 준다(문자열이면 읽는다).
            params = params_json if isinstance(params_json, dict) else json.loads(params_json or "{}")
        except (TypeError, ValueError):
            params = {}
        candidate = params.get("user_id") if isinstance(params, dict) else None
        user_id = candidate if candidate in ids else by_email.get((to_email or "").strip().lower())
        if user_id is None:
            unmatched += 1
            continue
        bind.execute(
            sa.text("UPDATE mail_deliveries SET recipient_user_id = :u WHERE id = :i"),
            {"u": user_id, "i": delivery_id},
        )
        matched += 1
    logger.info("mail_deliveries 받는 사람 채우기: 맞춤 %d, 못 맞춤 %d (못 맞춘 행은 전역 관리자만 본다)", matched, unmatched)


def downgrade() -> None:
    op.drop_index("ix_mail_deliveries_recipient_created", table_name="mail_deliveries")
    op.drop_constraint("fk_mail_deliveries_recipient_user_id", "mail_deliveries", type_="foreignkey")
    op.drop_column("mail_deliveries", "relay_response")
    op.drop_column("mail_deliveries", "failure_stage")
    op.drop_column("mail_deliveries", "recipient_user_id")
