"""문서 사이의 관계 — 잇고 · 끊고 · 양쪽에서 읽는다 (S7).

S6 의 `app/work/relations.py` 와 **같은 규칙**이다. 다르게 만들지 않은 것이 판단이다:
방향 있는 관계 둘과 방향 없는 관계 하나라는 구조가 티켓과 똑같고, 다르게 만들면 화면
둘이 같은 개념을 다른 방식으로 보여 준다.

`supersedes` 만 순환을 막는다. 「A 가 B 를 대체하고 B 가 A 를 대체한다」는 화면에서
어느 쪽이 최신인지 답할 수 없는 상태이고, `references` 는 서로 인용하는 것이 정상이다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, ValidationAppError
from app.knowledge.models import (
    DREL_KINDS,
    DREL_REFERENCES,
    DREL_RELATES_TO,
    DREL_SUPERSEDES,
    DocumentRelation,
)

__all__ = ["add", "remove", "of_document", "FORWARD_LABEL", "INVERSE_LABEL"]

FORWARD_LABEL: dict[str, str] = {
    DREL_SUPERSEDES: "대체한 문서",
    DREL_REFERENCES: "참고한 문서",
    DREL_RELATES_TO: "관련 문서",
}
INVERSE_LABEL: dict[str, str] = {
    DREL_SUPERSEDES: "대체된 문서",
    DREL_REFERENCES: "이 문서를 참고한 문서",
    DREL_RELATES_TO: "관련 문서",
}


def _ordered(from_id: str, to_id: str, kind: str) -> tuple[str, str]:
    """방향 없는 관계는 한 행이다 — 순서를 고정한다(제약과 같은 규칙)."""
    if kind == DREL_RELATES_TO and from_id > to_id:
        return to_id, from_id
    return from_id, to_id


def would_cycle(db: Session, *, from_id: str, to_id: str) -> bool:
    """`from` 이 `to` 를 대체하게 두면 순환이 되는가.

    `to` 에서 「대체한다」를 따라 내려가다 `from` 을 만나면 순환이다. 깊이 제한을
    두는 이유는 S6 과 같다 — 이미 순환이 들어간 데이터에서는 이 질의 자체가 안 끝난다.
    """
    if from_id == to_id:
        return True
    hit = db.execute(
        sa_text(
            "WITH RECURSIVE down(id, depth) AS ("
            "  SELECT CAST(:to_id AS text), 0"
            "  UNION ALL"
            "  SELECT r.to_document_id, down.depth + 1 FROM document_relations r"
            "  JOIN down ON r.from_document_id = down.id"
            "  WHERE r.kind = :kind AND down.depth < 64"
            ") SELECT 1 FROM down WHERE id = :from_id LIMIT 1"
        ),
        {"to_id": to_id, "from_id": from_id, "kind": DREL_SUPERSEDES},
    ).scalar_one_or_none()
    return hit is not None


def add(
    db: Session,
    *,
    from_document_id: str,
    to_document_id: str,
    kind: str,
    actor_id: str | None = None,
    now: datetime | None = None,
) -> DocumentRelation:
    """관계 하나. 이미 있으면 그 행을 그대로 돌려준다(재실행 안전)."""
    if kind not in DREL_KINDS:
        raise ValidationAppError(f"모르는 관계 종류입니다: {kind}")
    if from_document_id == to_document_id:
        raise ValidationAppError("같은 문서끼리는 이을 수 없습니다.")

    left, right = _ordered(from_document_id, to_document_id, kind)
    if kind == DREL_SUPERSEDES and would_cycle(db, from_id=left, to_id=right):
        raise ConflictError("두 문서가 서로를 대체하게 됩니다.")

    existing = db.execute(
        select(DocumentRelation).where(
            DocumentRelation.from_document_id == left,
            DocumentRelation.to_document_id == right,
            DocumentRelation.kind == kind,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    row = DocumentRelation(
        from_document_id=left,
        to_document_id=right,
        kind=kind,
        created_by=actor_id,
    )
    if now is not None:
        row.created_at = now
    db.add(row)
    db.flush()
    return row


def remove(db: Session, *, from_document_id: str, to_document_id: str, kind: str) -> bool:
    """끊는다. 없던 관계를 끊어도 오류가 아니다 — 화면에서 두 번 누른 것뿐이다."""
    if kind not in DREL_KINDS:
        raise ValidationAppError(f"모르는 관계 종류입니다: {kind}")
    left, right = _ordered(from_document_id, to_document_id, kind)
    row = db.execute(
        select(DocumentRelation).where(
            DocumentRelation.from_document_id == left,
            DocumentRelation.to_document_id == right,
            DocumentRelation.kind == kind,
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True


def of_document(db: Session, document_id: str) -> list[dict]:
    """양쪽 방향을 함께. **한 질의**다.

    반대편만 보여 주지 않는 이유: 「이 문서를 대체한 문서」는 이 문서를 여는 사람이
    가장 먼저 알아야 하는 사실이고, 그것은 반대 방향에만 적혀 있다.
    """
    rows = db.execute(
        select(DocumentRelation)
        .where(or_(
            DocumentRelation.from_document_id == document_id,
            DocumentRelation.to_document_id == document_id,
        ))
        .order_by(DocumentRelation.created_at)
    ).scalars().all()

    out: list[dict] = []
    for row in rows:
        forward = row.from_document_id == document_id
        other = row.to_document_id if forward else row.from_document_id
        out.append({
            "document_id": other,
            "kind": row.kind,
            "direction": "forward" if forward else "inverse",
            "label": (FORWARD_LABEL if forward else INVERSE_LABEL)[row.kind],
        })
    return out
