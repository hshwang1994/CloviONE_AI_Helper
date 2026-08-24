"""사용자별 문서 즐겨찾기 (S14 · C2).

옛 문서 화면(`/team-docs`)에 있던 기능을 정본 문서(`documents`)로 옮긴 것이다. 하는 일은
「이 사람이 이 문서를 담아 뒀는가」 하나이고, **어느 문서가 이 사람에게 보이는가는 여기서
안 본다** — 그건 부모 문서의 성질이라 부르는 쪽(`app/knowledge/service.py`)이
`get_scoped_document_or_404` 로 먼저 판정한다. 여기서 한 번 더 적으면 두 벌이 되고,
그중 하나가 빠진 자리에서 목록에 없는 문서를 즐겨찾기로 담을 수 있게 된다.

담기·빼기는 **멱등**이다. 같은 요청이 두 번 도착해도(더블클릭·재시도) 결과가 같아야 하고,
동시 요청이 겹쳐 유일 제약에 걸리는 것은 오류가 아니라 「먼저 담긴 것」이다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.db import is_insert_race
from app.knowledge.models import DocumentFavorite


def find(db: Session, *, user_id: str, document_id: str) -> DocumentFavorite | None:
    return db.execute(
        select(DocumentFavorite).where(
            DocumentFavorite.user_id == user_id,
            DocumentFavorite.document_id == document_id,
        )
    ).scalar_one_or_none()


def ids_for(db: Session, user_id: str, document_ids: list[str] | None = None) -> set[str]:
    """이 사람이 담아 둔 문서 id 들. 목록 한 화면치만 물어볼 수 있다.

    목록이 문서마다 한 번씩 묻지 않게 **한 질의**로 답한다 — 그렇게 하지 않으면 페이지
    하나가 문서 수만큼의 질의가 된다.
    """
    stmt = select(DocumentFavorite.document_id).where(DocumentFavorite.user_id == user_id)
    if document_ids is not None:
        if not document_ids:
            return set()
        stmt = stmt.where(DocumentFavorite.document_id.in_(document_ids))
    return set(db.execute(stmt).scalars().all())


def toggle(db: Session, *, user_id: str, document_id: str, on: bool, now: datetime) -> bool:
    existing = find(db, user_id=user_id, document_id=document_id)
    if on:
        if existing is not None:
            return True
        try:
            with db.begin_nested():
                db.add(DocumentFavorite(
                    user_id=user_id, document_id=document_id, created_at=now,
                ))
                db.flush()
        except (IntegrityError, OperationalError) as exc:
            # 동시 요청이 먼저 담았다. 사용자가 원한 상태가 이미 됐으므로 성공이다.
            if not is_insert_race(exc):
                raise
        return True
    if existing is not None:
        db.delete(existing)
        db.flush()
    return False
