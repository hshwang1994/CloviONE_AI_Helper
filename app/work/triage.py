"""Migration Exception — **임의 배정을 하지 않는다** (U11 · D-197).

## 이 파일이 하지 않는 일이 이 파일의 내용이다

소속 Project 를 정할 수 없는 티켓에 프로젝트를 **골라 주지 않는다.** 골라 주면
잘못 고른 티켓이 남의 부서로 새고, 그 사고는 화면이 정상으로 보이기 때문에 아무도
신고하지 않는다. 대신 「왜 정할 수 없는가」를 근거와 함께 남겨서 **사람이 하나씩
결정**하게 한다.

소속이 없으므로 D-193 의 fail-closed 에 의해 일반 사용자에게 보이지 않는다 —
**의도된 동작이다.** 빈 화면이 조용히 전량이 열리는 것보다 낫다.

## 분류가 곧 채번 게이트다

`classify()` 가 예외로 잡은 티켓에는 번호를 주지 않는다. 관리자가 `assign()` 으로
프로젝트를 지정하는 순간 D-196 의 채번이 돌고 `canonical_key` 가 생긴다.
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select, text as sa_text
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.core.models_base import utcnow
from app.projects.models import Project
from app.tickets.models import (
    PROJECT_LINK_AMBIGUOUS,
    PROJECT_LINK_MISSING,
    PROJECT_LINK_OK,
    PROJECT_LINK_UNRESOLVED,
    Ticket,
    split_names,
)
from app.work import numbering
from app.work.models import (
    EXC_AMBIGUOUS,
    EXC_MISSING,
    EXC_SOURCE_MISSING,
    EXC_UNRESOLVED,
    MigrationException,
)

# 소속을 못 정하는 이유 → 예외 사유. 순서가 있다 — 두 이유가 겹치면 **채번을 막는
# 쪽**이 사유다. 소스에서 사라진 것은 되돌아올 수 있지만, relation 이 둘인 것은
# 사람이 고르기 전에는 안 풀린다.
_LINK_REASON: dict[str, str] = {
    PROJECT_LINK_AMBIGUOUS: EXC_AMBIGUOUS,
    PROJECT_LINK_MISSING: EXC_MISSING,
    PROJECT_LINK_UNRESOLVED: EXC_UNRESOLVED,
}


def reason_for(ticket: Ticket) -> str | None:
    """이 티켓이 예외인가, 그렇다면 왜인가. 아니면 `None`.

    **순수 함수다.** DB 를 안 보므로 시험이 행 하나를 만들어 판정을 직접 확인할 수
    있고, `classify()` 와 화면이 같은 판정을 쓴다.
    """
    mapped = _LINK_REASON.get(ticket.project_link or "")
    if mapped is not None:
        return mapped
    if ticket.project_uid is None:
        # `ok` 인데 Portal 짝이 없는 상태. `project_link` 가 아직 재해석되지 않은
        # 회차에 생긴다 — 소속을 모르는 것은 같으므로 예외로 본다.
        return EXC_UNRESOLVED
    if ticket.notion_missing_at is not None:
        return EXC_SOURCE_MISSING
    return None


def _evidence(ticket: Ticket) -> str:
    """사람이 결정하려면 「무엇을 보고 그렇게 판단했는지」가 있어야 한다.

    사유 문자열만 남기면 결정하려는 사람이 원본을 다시 조사해야 하고, 그 조사가
    필요한 순간에는 소스가 이미 바뀌어 있을 수 있다.
    """
    return json.dumps(
        {
            "project_link": ticket.project_link,
            "project_uid": ticket.project_uid,
            "source_project_ids": split_names(ticket.project_ids or ""),
            "source_project_names": split_names(ticket.project_names or ""),
            "notion_page_id": ticket.notion_page_id,
            "notion_missing_at": (
                ticket.notion_missing_at.isoformat() if ticket.notion_missing_at else None
            ),
        },
        ensure_ascii=False,
    )


def classify(db: Session, *, now: datetime | None = None) -> dict[str, int]:
    """예외를 갱신한다. **프로젝트도 번호도 건드리지 않는다.**

    - 새로 예외가 된 티켓 → 열린 예외 한 줄
    - 사유가 바뀐 티켓 → 그 줄의 사유와 근거를 갱신(줄을 늘리지 않는다)
    - 더 이상 예외가 아닌 티켓 → 열린 줄을 해결로 표시

    재실행해도 같은 결과다. 회차마다 줄이 쌓이면 「몇 건 남았나」에 답할 수 없다.
    """
    stamp = now or utcnow()
    tickets = db.execute(select(Ticket)).scalars().all()
    open_rows = {
        row.ticket_id: row
        for row in db.execute(
            select(MigrationException).where(MigrationException.resolved_at.is_(None))
        ).scalars().all()
    }

    opened = updated = closed = 0
    for ticket in tickets:
        reason = reason_for(ticket)
        row = open_rows.pop(ticket.id, None)
        if reason is None:
            if row is not None:
                row.resolved_at = stamp
                closed += 1
            continue
        evidence = _evidence(ticket)
        if row is None:
            db.add(
                MigrationException(
                    ticket_id=ticket.id, reason=reason,
                    source_evidence=evidence, created_at=stamp,
                )
            )
            opened += 1
        elif row.reason != reason or row.source_evidence != evidence:
            row.reason = reason
            row.source_evidence = evidence
            updated += 1

    # 티켓이 사라진 열린 예외는 CASCADE 가 지운다 — 여기 남은 것은 위 순회에서 만난
    # 티켓뿐이므로 `open_rows` 에 남는 것은 없다. 방어적으로 닫지 않는다: 조용히
    # 닫으면 티켓 목록 질의가 틀렸을 때 그 사실이 예외 0건으로 보인다.
    db.flush()
    return {"opened": opened, "updated": updated, "closed": closed}


def open_count(db: Session) -> int:
    return int(
        db.execute(
            sa_text("SELECT count(*) FROM migration_exceptions WHERE resolved_at IS NULL")
        ).scalar_one()
    )


def assign(
    db: Session,
    *,
    ticket_id: str,
    project_id: str,
    actor_id: str,
    now: datetime | None = None,
) -> dict:
    """관리자가 소속을 정한다 — **그 순간 채번이 돈다** (D-197).

    자동으로 하지 않는 일을 사람이 하는 자리다. 프로젝트를 넣고, 번호를 받고,
    `canonical_key` 는 트리거가 만들고, 예외를 닫는다. 넷이 한 트랜잭션이라
    「프로젝트는 붙었는데 번호가 없는」 중간 상태가 남지 않는다.
    """
    stamp = now or utcnow()
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise NotFoundError("티켓을 찾을 수 없습니다.")
    project = db.get(Project, project_id)
    if project is None:
        raise NotFoundError("프로젝트를 찾을 수 없습니다.")
    if ticket.seq is not None:
        raise ConflictError("이 티켓에는 이미 번호가 있습니다.")

    ticket.project_uid = project_id
    ticket.project_link = PROJECT_LINK_OK
    db.flush()
    ticket.seq = numbering.allocate(db, project_id)
    db.flush()
    db.refresh(ticket)

    row = db.execute(
        select(MigrationException).where(
            MigrationException.ticket_id == ticket_id,
            MigrationException.resolved_at.is_(None),
        )
    ).scalar_one_or_none()
    if row is not None:
        row.resolved_at = stamp
        row.resolved_by = actor_id
    db.flush()
    return {
        "ticket_id": ticket_id,
        "project_id": project_id,
        "seq": ticket.seq,
        "canonical_key": ticket.canonical_key,
    }
