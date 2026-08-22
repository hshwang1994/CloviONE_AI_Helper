"""멘션 — 본문이 가리키는 것을 표로 옮긴다 (S7).

본문 JSON 안에 이미 있는 사실을 왜 표로 또 두는가는 `models.py::DocumentMention` 에
적었다. 여기서 지키는 것은 하나다: **표는 언제나 현재 판의 것과 같다.**

그래서 판이 바뀔 때마다 이 파일의 `sync()` 를 부른다. 늘리기만 하면 3년 전 지운
문장이 「나를 언급한 문서」에 계속 나오고, 통째로 지웠다 다시 넣으면 같은 멘션의
`created_at` 이 저장할 때마다 갱신돼 「언제부터 이 문서가 나를 언급했나」가 사라진다.
그래서 **차집합만 건드린다**.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.knowledge import blocks
from app.knowledge.models import Document, DocumentMention

__all__ = ["sync", "backlinks"]


def sync(db: Session, document: Document, body: dict) -> tuple[int, int]:
    """현재 판의 멘션과 표를 맞춘다. `(추가, 삭제)` 를 낸다.

    `body` 는 **정규화된** 본문이다(`blocks.derive().body`). 정규화 전 값을 주면 블록
    id 가 아직 없어서 멘션이 전부 버려진다.
    """
    wanted = set(blocks.extract_mentions(body))

    rows = list(
        db.execute(
            select(DocumentMention).where(DocumentMention.document_id == document.id)
        ).scalars().all()
    )
    have = {(r.block_id, r.target_kind, r.target_id): r for r in rows}

    removed = 0
    for key, row in have.items():
        if key not in wanted:
            db.delete(row)
            removed += 1

    added = 0
    for block_id, kind, target_id in wanted:
        if (block_id, kind, target_id) in have:
            continue
        db.add(DocumentMention(
            document_id=document.id,
            block_id=block_id,
            target_kind=kind,
            target_id=target_id,
        ))
        added += 1

    db.flush()
    return added, removed


def backlinks(
    db: Session, *, target_kind: str, target_id: str, document_ids: list[str] | None = None
) -> list[DocumentMention]:
    """나를 언급한 문서들. **이 표가 존재하는 이유다.**

    `document_ids` 는 부르는 쪽이 이미 가시성으로 좁힌 집합이다. 여기서 권한을 다시
    판정하지 않는 이유는 폴더와 같다 — 판정은 `effective_visibility_clause` 한 곳이고
    (D-194), 이 함수는 그 결과를 받는다. 목록을 안 좁히고 부르면 남의 공간 문서가
    「나를 언급함」에 나온다.
    """
    stmt = select(DocumentMention).where(
        DocumentMention.target_kind == target_kind,
        DocumentMention.target_id == target_id,
    )
    if document_ids is not None:
        if not document_ids:
            return []
        stmt = stmt.where(DocumentMention.document_id.in_(document_ids))
    return list(db.execute(stmt.order_by(DocumentMention.created_at.desc())).scalars().all())
