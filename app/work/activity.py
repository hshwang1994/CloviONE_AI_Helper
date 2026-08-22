"""티켓 활동 기록 — **감사 로그와 다른 것**을 남긴다.

| | `audit_logs` | `ticket_activities` |
|---|---|---|
| 답하는 질문 | 누가 시스템에 무엇을 했는가 | 이 티켓이 어떻게 흘러왔는가 |
| 보는 사람 | 운영·보안 | 일하는 사람 (상세 화면) |
| 보존 | 감사 정책 | 티켓과 같이 산다 |

한 표로 합치면 티켓 타임라인 한 줄을 그리려고 전 감사 로그를 훑게 되고, 반대로
감사 보존 정책이 티켓 이력을 지운다. 둘 다 각자 자리에서는 옳은 정책이다.

**둘 다 남긴다.** 상태 변경 하나가 감사에도 활동에도 남는 것은 중복이 아니라 서로
다른 질문에 대한 답이다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models_base import new_uuid, utcnow
from app.work.models import (
    ACT_ASSIGNEE,
    ACT_CREATED,
    ACT_FIELD,
    ACT_KINDS,
    ACT_RANK,
    ACT_RELATION,
    ACT_SPRINT,
    ACT_STATUS,
    TicketActivity,
)

__all__ = [
    "ACT_ASSIGNEE", "ACT_CREATED", "ACT_FIELD", "ACT_RANK", "ACT_RELATION",
    "ACT_SPRINT", "ACT_STATUS", "record", "timeline",
]

# 한 화면에 싣는 최대 줄 수. 티켓 하나에 수백 건이 쌓이면 상세 화면이 그것 때문에 느려진다.
TIMELINE_LIMIT = 100


def record(
    db: Session,
    *,
    ticket_id: str,
    kind: str,
    actor_id: str | None = None,
    field: str | None = None,
    from_value: str | None = None,
    to_value: str | None = None,
    now: datetime | None = None,
) -> TicketActivity | None:
    """활동 한 줄. **값이 안 바뀌었으면 안 남긴다.**

    안 바뀐 저장까지 남기면 타임라인이 「저장했음」으로 가득 차고, 그 안에서 진짜
    변화를 찾을 수 없게 된다 — 기록이 있는데 못 읽는 상태가 기록이 없는 것보다 낫지
    않다.

    `actor_id` 가 `None` 이면 시스템이 한 일이다(동기화·마이그레이션). 사람이 한 일과
    구별되지 않으면 "내가 안 바꿨는데 내 이름이 있다" 가 생긴다.
    """
    if kind not in ACT_KINDS:
        raise ValueError(f"unknown activity kind: {kind}")
    if kind != ACT_CREATED and from_value == to_value:
        return None
    row = TicketActivity(
        id=new_uuid(),
        ticket_id=ticket_id,
        actor_user_id=actor_id,
        kind=kind,
        field=field,
        from_value=from_value,
        to_value=to_value,
        created_at=now or utcnow(),
    )
    db.add(row)
    db.flush()
    return row


def timeline(db: Session, ticket_id: str, *, limit: int = TIMELINE_LIMIT) -> list[dict]:
    """이 티켓의 최근 활동. **`seq` 로 정렬한다.**

    `created_at` 만으로는 같은 순간의 두 사건 순서가 매번 달라진다 — PG 에는 rowid 가
    없다(`ticket_comments.seq` 가 같은 이유로 있다). 상태 변경과 담당자 변경이 한
    트랜잭션에서 일어나면 정확히 그 상황이다.
    """
    rows = db.execute(
        select(TicketActivity)
        .where(TicketActivity.ticket_id == ticket_id)
        .order_by(TicketActivity.seq.desc())
        .limit(max(1, limit))
    ).scalars().all()
    return [
        {
            "id": r.id,
            "kind": r.kind,
            "field": r.field,
            "from": r.from_value,
            "to": r.to_value,
            "actor_user_id": r.actor_user_id,
            "at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in reversed(rows)
    ]
