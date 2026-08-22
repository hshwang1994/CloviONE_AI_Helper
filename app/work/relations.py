"""티켓 사이의 관계 — **계층의 정본은 여기 하나다** (§5.2).

## 두 벌이 되지 않게 하는 방법

미러의 `tickets.parent_page_id` 는 0044 가 만든 컬럼이고, 그 주석이 이미 옳은 말을
적어 두었다: "계층이 두 벌이 되면 둘이 갈라진 뒤 갈라진 쪽을 아무도 못 고친다."

S6 이 `ticket_relations` 를 만들면서 정확히 그 위험이 생겼다. 그래서 **한 방향만**
둔다: 동기화가 `parent_page_id` 를 읽어 `subtask_of` 행을 만들고(`sync_parent_links`),
**읽는 쪽은 전부 이 표만 본다.** `parent_page_id` 는 입력이지 두 번째 정본이 아니다.

한 방향이라는 것을 코드가 지키는지는 `scripts/check_domain_single_source.py`
가 본다 — 주석으로 약속할 수 있는 성질이 아니다(D-231 이 배운 것).

## 순환은 DB 가 아니라 여기서 막는다

`A 의 상위는 B, B 의 상위는 A` 는 제약으로 표현할 수 없다(재귀 질의가 필요하다).
막지 않으면 WBS 트리를 그리는 코드가 무한히 돈다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, text as sa_text
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, ValidationAppError
from app.core.models_base import utcnow
from app.work.models import (
    REL_BLOCKS,
    REL_KINDS,
    REL_RELATES_TO,
    REL_SUBTASK_OF,
    TicketRelation,
)

# 반대편에서 부르는 이름. 화면이 「이 티켓을 막고 있는 것」을 보여주려면 필요하다.
INVERSE_LABEL: dict[str, str] = {
    REL_SUBTASK_OF: "상위 작업",
    REL_BLOCKS: "선행 작업",
    REL_RELATES_TO: "관련 작업",
}
FORWARD_LABEL: dict[str, str] = {
    REL_SUBTASK_OF: "하위 작업",
    REL_BLOCKS: "후속 작업",
    REL_RELATES_TO: "관련 작업",
}


def _ordered(from_id: str, to_id: str, kind: str) -> tuple[str, str]:
    """방향 없는 관계는 한 행이다 — 순서를 고정한다(제약과 같은 규칙)."""
    if kind == REL_RELATES_TO and from_id > to_id:
        return to_id, from_id
    return from_id, to_id


def would_cycle(db: Session, *, child_id: str, parent_id: str) -> bool:
    """`child` 의 상위를 `parent` 로 두면 순환이 되는가.

    `parent` 에서 위로 올라가다 `child` 를 만나면 순환이다. 재귀 CTE 에 깊이 제한을
    두는 이유: 이미 순환이 들어가 있는 데이터에서 이 질의 자체가 안 끝난다.
    """
    if child_id == parent_id:
        return True
    hit = db.execute(
        sa_text(
            # `CAST(... AS text)` 이지 `:parent::text` 가 아니다 — 바인드 이름 바로 뒤에
            # 붙은 `::` 는 SQLAlchemy 의 파라미터 인식에서 빠져나가고, 그러면 `:parent` 가
            # 치환되지 않은 채 그대로 서버에 가서 구문 오류가 난다.
            "WITH RECURSIVE up(id, depth) AS ("
            "  SELECT CAST(:parent AS text), 0"
            "  UNION ALL"
            "  SELECT r.to_ticket_id, up.depth + 1 FROM ticket_relations r"
            "  JOIN up ON r.from_ticket_id = up.id"
            "  WHERE r.kind = :kind AND up.depth < 64"
            ") SELECT 1 FROM up WHERE id = :child LIMIT 1"
        ),
        {"parent": parent_id, "child": child_id, "kind": REL_SUBTASK_OF},
    ).scalar_one_or_none()
    return hit is not None


def add(
    db: Session,
    *,
    from_ticket_id: str,
    to_ticket_id: str,
    kind: str,
    actor_id: str | None = None,
    now: datetime | None = None,
) -> TicketRelation:
    """관계 하나. 이미 있으면 그 행을 그대로 돌려준다(재실행 안전).

    `subtask_of` 의 방향은 **`from` 이 하위, `to` 가 상위**다. 헷갈리기 쉬운 자리라
    이름을 그렇게 지었다 — "from is a subtask of to".
    """
    if kind not in REL_KINDS:
        raise ValidationAppError(f"모르는 관계 종류입니다: {kind}")
    if from_ticket_id == to_ticket_id:
        raise ValidationAppError("같은 티켓끼리는 이을 수 없습니다.")

    left, right = _ordered(from_ticket_id, to_ticket_id, kind)
    if kind == REL_SUBTASK_OF:
        if would_cycle(db, child_id=left, parent_id=right):
            raise ConflictError("상위 작업이 서로를 가리키게 됩니다.")
        current = db.execute(
            select(TicketRelation).where(
                TicketRelation.from_ticket_id == left,
                TicketRelation.kind == REL_SUBTASK_OF,
            )
        ).scalar_one_or_none()
        if current is not None and current.to_ticket_id != right:
            raise ConflictError(
                "이 티켓에는 이미 상위 작업이 있습니다. 먼저 해제한 뒤 다시 지정해 주세요."
            )

    existing = db.execute(
        select(TicketRelation).where(
            TicketRelation.from_ticket_id == left,
            TicketRelation.to_ticket_id == right,
            TicketRelation.kind == kind,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    row = TicketRelation(
        from_ticket_id=left, to_ticket_id=right, kind=kind,
        created_by=actor_id, created_at=now or utcnow(),
    )
    db.add(row)
    db.flush()
    return row


def remove(db: Session, *, from_ticket_id: str, to_ticket_id: str, kind: str) -> bool:
    """관계를 끊는다. 없었으면 `False`."""
    left, right = _ordered(from_ticket_id, to_ticket_id, kind)
    row = db.execute(
        select(TicketRelation).where(
            TicketRelation.from_ticket_id == left,
            TicketRelation.to_ticket_id == right,
            TicketRelation.kind == kind,
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True


def for_ticket(db: Session, ticket_id: str) -> list[dict]:
    """이 티켓에 붙은 관계 전부 — **양쪽 방향**.

    한 방향만 주면 화면이 「이 티켓을 막고 있는 것」을 못 보여 준다. 그런데 그쪽이
    사람이 실제로 궁금해하는 방향이다.
    """
    rows = db.execute(
        select(TicketRelation).where(
            (TicketRelation.from_ticket_id == ticket_id)
            | (TicketRelation.to_ticket_id == ticket_id)
        ).order_by(TicketRelation.kind, TicketRelation.created_at)
    ).scalars().all()
    out: list[dict] = []
    for r in rows:
        outgoing = r.from_ticket_id == ticket_id
        other = r.to_ticket_id if outgoing else r.from_ticket_id
        out.append({
            "kind": r.kind,
            "direction": "outgoing" if outgoing else "incoming",
            "label": (FORWARD_LABEL if not outgoing else INVERSE_LABEL)[r.kind],
            "ticket_id": other,
        })
    return out


def parent_of(db: Session, ticket_id: str) -> str | None:
    """상위 티켓 id. 없으면 `None`. **이 표만 본다.**"""
    return db.execute(
        sa_text(
            "SELECT to_ticket_id FROM ticket_relations "
            "WHERE from_ticket_id = :tid AND kind = :kind"
        ),
        {"tid": ticket_id, "kind": REL_SUBTASK_OF},
    ).scalar_one_or_none()


def parent_map(db: Session, ticket_ids) -> dict[str, str]:
    """{하위 티켓 id: 상위 티켓 id} — 진행률과 WBS 가 계층을 얻는 **유일한 자리**.

    행 목록을 받아 한 번에 읽는다. 행마다 `parent_of` 를 부르면 프로젝트 하나에 티켓이
    수백 건일 때 질의가 그만큼 늘어난다.
    """
    ids = [t for t in ticket_ids if t]
    if not ids:
        return {}
    rows = db.execute(
        select(TicketRelation.from_ticket_id, TicketRelation.to_ticket_id).where(
            TicketRelation.kind == REL_SUBTASK_OF,
            TicketRelation.from_ticket_id.in_(ids),
        )
    ).all()
    return {child: parent for child, parent in rows}


def parent_ids(db: Session) -> set[str]:
    """하위를 하나라도 가진 티켓의 id 집합.

    진행률이 **리프만 세려고** 쓴다 — 부모까지 세면 부모 1건 + 자식 3건이 같은 일을
    네 번 센다(`app/projects/progress.py` 가 실측한 Notion rollup 의 결함이 그것이다).
    """
    rows = db.execute(
        sa_text("SELECT DISTINCT to_ticket_id FROM ticket_relations WHERE kind = :kind"),
        {"kind": REL_SUBTASK_OF},
    ).scalars().all()
    return {r for r in rows if r}


def sync_parent_links(db: Session, *, now: datetime | None = None) -> dict[str, int]:
    """미러의 `parent_page_id` → `subtask_of` 행. **한 방향 파생이다.**

    동기화가 끝난 뒤에 부른다. 여기가 유일한 쓰기 경로이므로 두 표현이 갈라질 자리가
    없다 — 갈라지려면 누군가 이 함수 말고 다른 데서 `subtask_of` 를 만들어야 하고,
    그것은 `check_domain_single_source.py` 가 본다.

    순환은 만들지 않는다: 소스가 순환을 주면 그 변(邊)만 건너뛴다. 동기화 전체를
    세우는 것보다 낫다 — 한 티켓의 상위가 안 보이는 것과 미러가 멈추는 것은 다른
    크기의 사고다.
    """
    stamp = now or utcnow()
    pairs = db.execute(
        sa_text(
            "SELECT c.id AS child_id, p.id AS parent_id FROM tickets c "
            "JOIN tickets p ON p.notion_page_id = c.parent_page_id "
            "WHERE c.parent_page_id IS NOT NULL"
        )
    ).all()
    wanted = {(row.child_id, row.parent_id) for row in pairs}

    current = {
        (row.from_ticket_id, row.to_ticket_id)
        for row in db.execute(
            select(TicketRelation.from_ticket_id, TicketRelation.to_ticket_id).where(
                TicketRelation.kind == REL_SUBTASK_OF
            )
        ).all()
    }

    removed = 0
    for child_id, parent_id in current - wanted:
        if remove(
            db, from_ticket_id=child_id, to_ticket_id=parent_id, kind=REL_SUBTASK_OF
        ):
            removed += 1

    added = skipped = 0
    for child_id, parent_id in sorted(wanted - current):
        try:
            add(
                db, from_ticket_id=child_id, to_ticket_id=parent_id,
                kind=REL_SUBTASK_OF, actor_id=None, now=stamp,
            )
            added += 1
        except (ConflictError, ValidationAppError):
            skipped += 1
    db.flush()
    return {"added": added, "removed": removed, "skipped": skipped}
