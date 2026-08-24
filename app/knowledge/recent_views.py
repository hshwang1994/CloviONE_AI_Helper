"""최근 열람 기록 (S14 · C2).

문서 상세를 열 때의 **부수효과**다. 그래서 실패해도 본문 조회 자체를 막지 않는다 —
사용자가 이미 받아 본 글을 「최근 열람을 못 적었다」는 이유로 오류로 바꾸면, 얻는 것 없이
읽기를 잃는다. 최악의 결과는 이번 조회분의 시각이 안 갱신되는 것뿐이다.

한 사람 · 한 문서에 **한 행**이고 시각만 갱신한다. 열 때마다 행을 쌓으면 이 표가 문서
조회 로그가 되는데, 그건 감사 로그가 이미 하는 일이다.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.db import (
    DEFAULT_WRITE_CONFLICT_RETRIES,
    is_insert_race,
    write_conflict_backoff,
)
from app.knowledge.models import DocumentRecentView

logger = logging.getLogger(__name__)

_RETRIES = DEFAULT_WRITE_CONFLICT_RETRIES


def find(db: Session, *, user_id: str, document_id: str) -> DocumentRecentView | None:
    return db.execute(
        select(DocumentRecentView).where(
            DocumentRecentView.user_id == user_id,
            DocumentRecentView.document_id == document_id,
        )
    ).scalar_one_or_none()


def recent(db: Session, user_id: str, *, limit: int = 10) -> list[DocumentRecentView]:
    return list(db.execute(
        select(DocumentRecentView)
        .where(DocumentRecentView.user_id == user_id)
        .order_by(DocumentRecentView.viewed_at.desc())
        .limit(limit)
    ).scalars().all())


def record(db: Session, *, user_id: str, document_id: str, now: datetime) -> None:
    """「이미 있으면 갱신, 없으면 삽입」을 **같은 예산으로** 재시도한다.

    예전 구현은 갱신 분기에만 재시도가 없어서, 이미 성공적으로 읽어 온 본문이 있는데도
    마지막 한 줄의 쓰기 충돌로 문서 상세 전체가 원시 500 이 났다. 두 분기를 한 루프에
    두면 어느 쪽이든 같은 예산을 쓴다.
    """
    for attempt in range(_RETRIES):
        try:
            with db.begin_nested():
                existing = find(db, user_id=user_id, document_id=document_id)
                if existing is not None:
                    existing.viewed_at = now
                else:
                    db.add(DocumentRecentView(
                        user_id=user_id, document_id=document_id, viewed_at=now,
                    ))
                db.flush()
            return
        except (IntegrityError, OperationalError) as exc:
            if not is_insert_race(exc):
                raise
            if attempt == _RETRIES - 1:
                logger.warning(
                    "최근 열람 기록 갱신 재시도를 다 썼습니다(document_id=%s). "
                    "본문 조회는 그대로 진행합니다.",
                    document_id,
                )
                return
            time.sleep(write_conflict_backoff(attempt))
