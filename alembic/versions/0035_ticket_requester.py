"""tickets.requester_user_id — 누가 이 일을 요청했는가 (계획 3.4).

Revision ID: 0035_ticket_requester
Revises: 0034_mail_delivery_queue

티켓이 끝나면 요청한 사람이 결과 알림(`ticket_resolved`)을 받는다. 그러려면 요청자가 누구인지 알아야 한다.
제품에서 만든 티켓은 이제 만든 사람을 적는다(`app/tickets/service.py::create_ticket`). 이 마이그레이션은 이미
있는 티켓을 **믿을 수 있는 기록에서만** 되채운다:

1. 생성 활동(`ticket_activities.kind='created'`)의 행위자 — 가장 이른 것.
2. 없으면 생성 감사(`audit_logs.action='ticket.create'`, `object_type='notion_task'`)의 행위자.

둘 다 있는 계정만 쓴다(지워진 계정 id 를 적지 않는다). 옛 소스에서 옮겨 온 티켓은 두 기록이 없어 비어
있고, 그 티켓의 결과 알림은 요청자에게 가지 않는다 - 지어내지 않는다.

되돌리면 칸을 지운다(되채운 값도 함께 사라진다 - 두 기록에 그대로 남아 있어 잃는 사실은 없다).
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "0035_ticket_requester"
down_revision = "0034_mail_delivery_queue"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.0035")


def upgrade() -> None:
    op.add_column("tickets", sa.Column("requester_user_id", sa.String(36), nullable=True))
    op.create_foreign_key(
        "fk_tickets_requester_user_id", "tickets", "users", ["requester_user_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_tickets_requester_user_id", "tickets", ["requester_user_id"])

    conn = op.get_bind()
    from_activity = conn.execute(sa.text(
        "UPDATE tickets t SET requester_user_id = a.actor "
        "FROM (SELECT DISTINCT ON (ticket_id) ticket_id, actor_user_id AS actor FROM ticket_activities "
        "      WHERE kind = 'created' AND actor_user_id IS NOT NULL ORDER BY ticket_id, created_at) a "
        "WHERE t.id = a.ticket_id AND t.requester_user_id IS NULL "
        "  AND EXISTS (SELECT 1 FROM users u WHERE u.id = a.actor)"
    )).rowcount
    from_audit = conn.execute(sa.text(
        "UPDATE tickets t SET requester_user_id = l.actor "
        "FROM (SELECT DISTINCT ON (object_id) object_id, user_id AS actor FROM audit_logs "
        "      WHERE action = 'ticket.create' AND object_type = 'notion_task' AND user_id IS NOT NULL "
        "      ORDER BY object_id, created_at) l "
        "WHERE l.object_id = coalesce(t.notion_page_id, t.id) AND t.requester_user_id IS NULL "
        "  AND EXISTS (SELECT 1 FROM users u WHERE u.id = l.actor)"
    )).rowcount
    remaining = conn.execute(sa.text("SELECT count(*) FROM tickets WHERE requester_user_id IS NULL")).scalar()
    logger.info(
        "0035 requester_user_id 되채우기: 생성 활동 %s건, 생성 감사 %s건, 요청자를 모르는 티켓 %s건",
        from_activity, from_audit, remaining,
    )


def downgrade() -> None:
    op.drop_index("ix_tickets_requester_user_id", table_name="tickets")
    op.drop_constraint("fk_tickets_requester_user_id", "tickets", type_="foreignkey")
    op.drop_column("tickets", "requester_user_id")
