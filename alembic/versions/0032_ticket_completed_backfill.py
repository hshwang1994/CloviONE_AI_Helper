"""tickets.completed_at 되채우기 — 월간 리포트의 완료일 축이 이관 티켓도 세게 한다 (계획 3.7).

Revision ID: 0032_ticket_completed_backfill
Revises: 0031_project_stats_computed_at

`completed_at` 은 상태가 완료가 되는 순간 찍힌다(`repository_native._stamp_completion`). 그런데
그 규칙이 생기기 전에 완료된 티켓과 이관 티켓은 값이 없다(`0018` 이 되채우지 않았다). 그 티켓들은
"이 달에 끝낸 일" 에 영영 안 잡힌다.

## 믿을 수 있는 원천만 쓴다

1. `ticket_activities` 의 상태 기록(`kind='status'`, `to_value='완료'`) 중 가장 늦은 시각.
2. 없으면 감사 기록(`action='ticket.update'`, `object_type='notion_task'`, `after_json->>'status'='완료'`)
   중 가장 늦은 시각. 감사 기록은 보존 정리 대상이 아니다.

`notion_last_edited`(아무 편집이든 움직인다)와 `due_date`(계획일 뿐이다)로는 **지어내지 않는다.**
둘 다 없는 티켓은 NULL 로 남고, 리포트가 "끝낸 날짜를 모르는 완료 티켓" 으로 따로 센다.

## 되돌리기

하지 않는다. 채운 값은 두 기록에 있던 사실이라, 되돌리면 사실을 지우는 셈이다. 되채운 값과 나중에
찍힌 값을 가를 표시도 없다.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "0032_ticket_completed_backfill"
down_revision = "0031_project_stats_computed_at"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.0032")

DONE = "완료"


def upgrade() -> None:
    conn = op.get_bind()
    from_activity = conn.execute(sa.text(
        "UPDATE tickets t SET completed_at = a.last_at "
        "FROM (SELECT ticket_id, max(created_at) AS last_at FROM ticket_activities "
        "      WHERE kind = 'status' AND to_value = :done GROUP BY ticket_id) a "
        "WHERE t.id = a.ticket_id AND t.completed_at IS NULL AND t.status = :done"
    ), {"done": DONE}).rowcount
    from_audit = conn.execute(sa.text(
        "UPDATE tickets t SET completed_at = l.last_at "
        "FROM (SELECT object_id, max(created_at) AS last_at FROM audit_logs "
        "      WHERE action = 'ticket.update' AND object_type = 'notion_task' "
        "        AND after_json ->> 'status' = :done GROUP BY object_id) l "
        "WHERE l.object_id = coalesce(t.notion_page_id, t.id) "
        "  AND t.completed_at IS NULL AND t.status = :done"
    ), {"done": DONE}).rowcount
    remaining = conn.execute(sa.text(
        "SELECT count(*) FROM tickets WHERE status = :done AND completed_at IS NULL"
    ), {"done": DONE}).scalar()
    logger.info(
        "0032 completed_at 되채우기: 상태 기록 %s건, 감사 기록 %s건, 끝낸 날짜를 모르는 완료 티켓 %s건",
        from_activity, from_audit, remaining,
    )


def downgrade() -> None:
    # 되돌리지 않는다(머리말). 스키마 변경이 없으므로 내려가는 것 자체는 안전하다.
    pass
