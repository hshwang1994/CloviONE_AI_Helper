"""티켓 상태가 바뀌었을 때 누구에게 무엇을 알리는가 — **한 곳에서** 정한다 (계획 3.4, D-513).

## 왜 한 곳인가

예전에는 상태 변경 알림이 작업 보드의 카드 이동(`app/work/service.py::_notify_move`)에만 붙어 있었다. 목록이나
상세에서 상태를 바꾸면(`update_ticket`) 아무도 알림을 받지 않았다. 게다가 카드 이동은 `update_ticket` 을 지나면서
상태 활동을 한 번 더 적었다. 이제 상태를 바꾸는 모든 길이 `update_ticket` 하나를 지나고, 알림도 거기서 한 번 나간다.

## 누가 받는가

  관찰자 · 지금 담당자   `ticket_status_changed` — 상태가 바뀔 때마다
  요청자                 `ticket_resolved` — 완료나 취소로 끝날 때만. 관찰자이거나 담당자여도 이 한 통만 받는다
  바꾼 사람              받지 않는다

요청자는 티켓을 만든 사람이다(`tickets.requester_user_id`). 옛 소스에서 옮겨 온 티켓은 요청자를 몰라 결과 알림이
없다. 알림 실패는 상태 변경을 막지 않는다(배정 알림과 같은 규약).
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger("app.tickets.notify")

TYPE_STATUS_CHANGED = "ticket_status_changed"
TYPE_RESOLVED = "ticket_resolved"


def recipients_for_status_change(
    db: Session, *, ticket_uid: str, assignee_user_ids, to_status: str, actor_id: str | None,
) -> dict[str, str]:
    """`{user_id: 알림 유형}` — 한 사람에게 한 통이다(요청자의 결과 알림이 이긴다)."""
    from app.tickets.models import Ticket
    from app.work import workflow
    from app.work.models import TicketWatcher

    recipients: dict[str, str] = {}
    watchers = db.execute(select(TicketWatcher.user_id).where(TicketWatcher.ticket_id == ticket_uid)).scalars()
    for uid in list(watchers) + list(assignee_user_ids or []):
        if uid:
            recipients[uid] = TYPE_STATUS_CHANGED
    ticket = db.get(Ticket, ticket_uid)
    closing = workflow.category_of(to_status) in (workflow.CAT_DONE, workflow.CAT_CANCELED)
    if closing and ticket is not None and ticket.requester_user_id:
        recipients[ticket.requester_user_id] = TYPE_RESOLVED
    if actor_id:
        recipients.pop(actor_id, None)
    return recipients


def notify_status_changed(
    db: Session, *, ticket_uid: str | None, page_id: str, key: str | None, title: str | None,
    assignee_user_ids, actor, from_status: str | None, to_status: str | None, now: datetime,
) -> int:
    """상태가 실제로 바뀌었을 때만 알린다. 보낸 알림 수를 돌려준다."""
    if not ticket_uid or not to_status or from_status == to_status:
        return 0
    try:
        from app.notifications.service import notify_user
        from app.work import workflow

        label = workflow.label_of(to_status)
        name = key or "티켓"
        recipients = recipients_for_status_change(
            db, ticket_uid=ticket_uid, assignee_user_ids=assignee_user_ids, to_status=to_status,
            actor_id=getattr(actor, "id", None),
        )
        for uid, type_ in recipients.items():
            heading = f"{name} 처리 결과: {label}" if type_ == TYPE_RESOLVED else f"{name} 상태 변경: {label}"
            notify_user(
                db, uid, type_=type_, title=heading, body=(title or "")[:200],
                related=("ticket", page_id), now=now,
            )
        return len(recipients)
    except Exception:  # noqa: BLE001 - 알림이 상태 변경을 막으면 안 된다
        logger.exception("티켓 상태 알림에 실패했다 (ticket=%s)", ticket_uid)
        return 0
