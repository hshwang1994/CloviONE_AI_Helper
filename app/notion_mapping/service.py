"""Notion user mapping service (spec §12).

Mapping is keyed on the login account email matching a Notion People email.
The web app never sends the email string as a People property value and never
accepts a Notion user id from the browser (spec §12.3) — the id is resolved
only by an admin — S11 이 n8n 을 걷어내면서 자동 조회 경로가 사라졌다.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.db import DEFAULT_WRITE_CONFLICT_RETRIES, is_insert_race, write_conflict_backoff
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.notion_mapping.models import (
    SOURCE_MANUAL,
    STATUS_UNMAPPED,
    STATUS_VERIFIED,
    UserNotionMapping,
)
from app.users.models import User


_NOTION_USER_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")


_GET_OR_CREATE_RETRIES = DEFAULT_WRITE_CONFLICT_RETRIES  # PA-RC-0008: 예전엔 5, 지터 없음


def get_or_create_mapping(db: Session, user_id: str) -> UserNotionMapping:
    # user_id는 UNIQUE — 사람이 누른 "검증"과 신규 사용자를 훑는 대량 동기화 잡이 같은
    # user_id를 거의 동시에 처음 보면 둘 다 아래 조회에서 "없음"을 보고 삽입을 시도할 수
    # 있다. get_or_create 계약상 진 쪽도 실패가 아니라 "그 행을 돌려준다"가 맞으므로
    # 409로 알리지 않고 승자의 행을 돌려준다(app/approvals/service.py::create_approval과
    # 같은 관용) — **단순 재조회로는 부족하다**: 이 세션의 스냅샷이 낡아 재조회 시점에도
    # 아직 승자의 커밋이 안 보일 수 있다(SAVEPOINT 롤백은 스냅샷을 새로 뜨지 않는다,
    # CORE-13). 그래서 실패 뒤 `db.commit()`으로 스냅샷을 새로 뜨고(진 삽입은 이미
    # SAVEPOINT로 걷혔으니 커밋해도 잃을 게 없다), 그래도 아직 안 보이면 다시 시도한다.
    for attempt in range(_GET_OR_CREATE_RETRIES):
        row = db.execute(
            select(UserNotionMapping).where(UserNotionMapping.user_id == user_id)
        ).scalar_one_or_none()
        if row is not None:
            return row
        row = UserNotionMapping(user_id=user_id, status=STATUS_UNMAPPED)
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
            return row
        except (IntegrityError, OperationalError) as exc:
            if not is_insert_race(exc):
                raise
            if attempt == _GET_OR_CREATE_RETRIES - 1:
                # PA-RC-0008: 예산을 다 썼는데도 여전히 안 보이면(재조회에서도 승자의
                # 커밋이 안 보이는 낡은 스냅샷이 반복) 처리 안 된 예외를 그대로 올려
                # 500을 내던 자리다 — 사용자에게 뜻이 통하는 409로 바꾼다.
                raise ConflictError(
                    "사용자 매핑을 만들지 못했습니다. 잠시 후 다시 시도해 주세요."
                ) from None
            # 스냅샷을 새로 뜨는 이 commit 자체도 경합에서 같은 이유로 거부될 수 있다
            # (org/service.py::create_item과 같은 자리, D-75/PA-08과 같은 패턴) —
            # 처리 안 하면 예산이 남았는데도 raw OperationalError가 새 나간다.
            try:
                db.commit()
            except (IntegrityError, OperationalError) as commit_exc:
                if not is_insert_race(commit_exc):
                    raise
                db.rollback()
            time.sleep(write_conflict_backoff(attempt))
    raise AssertionError("unreachable")  # pragma: no cover


def mapping_status(db: Session, user_id: str) -> str:
    row = db.execute(
        select(UserNotionMapping).where(UserNotionMapping.user_id == user_id)
    ).scalar_one_or_none()
    return row.status if row is not None else STATUS_UNMAPPED


def _mask_notion_id(notion_id: str | None) -> str | None:
    if not notion_id:
        return None
    if len(notion_id) <= 8:
        return "****"
    return f"{notion_id[:4]}…{notion_id[-4:]}"


def mapping_view(row: UserNotionMapping, user: User | None = None) -> dict:
    return {
        "user_id": row.user_id,
        "user_email": user.email if user else None,
        "user_display_name": user.display_name if user else None,
        "notion_user_id_masked": _mask_notion_id(row.notion_user_id),
        "notion_email": row.notion_email,
        "status": row.status,
        "source": row.source,
        "last_verified_at": row.last_verified_at.isoformat() if row.last_verified_at else None,
        "error_message": row.error_message,
        "candidates": json.loads(row.candidates_json) if row.candidates_json else None,
    }


def mapping_view_for_user(user: User, row: UserNotionMapping | None) -> dict:
    """매핑 행이 아직 없는 사용자도 같은 모양으로 보여준다.

    행이 없다는 것은 '아직 연결을 시도한 적이 없다'는 뜻이지 목록에서 빠질 이유가
    아니다. 목록에 나와야 관리자가 그 사람을 골라 연결을 시작할 수 있다.
    """
    if row is not None:
        return mapping_view(row, user)
    return {
        "user_id": user.id,
        "user_email": user.email,
        "user_display_name": user.display_name,
        "notion_user_id_masked": None,
        "notion_email": None,
        "status": STATUS_UNMAPPED,
        "source": None,
        "last_verified_at": None,
        "error_message": None,
        "candidates": None,
    }


def manual_map(
    db: Session, user: User, *, notion_user_id: str, notion_email: str | None, now: datetime
) -> UserNotionMapping:
    """Admin sets the mapping explicitly (spec §12.2). The id is validated
    but never sourced from an end user's browser."""
    if not _NOTION_USER_ID.match(notion_user_id or ""):
        raise ValidationAppError("Notion user id 형식이 올바르지 않습니다.")
    row = get_or_create_mapping(db, user.id)
    row.notion_user_id = notion_user_id
    row.notion_email = notion_email
    row.status = STATUS_VERIFIED
    row.source = SOURCE_MANUAL
    row.last_verified_at = now
    row.error_message = None
    row.candidates_json = None
    db.flush()
    return row


def unmap(db: Session, user_id: str) -> UserNotionMapping:
    row = get_or_create_mapping(db, user_id)
    row.notion_user_id = None
    row.notion_email = None
    row.status = STATUS_UNMAPPED
    row.source = None
    row.error_message = None
    row.candidates_json = None
    db.flush()
    return row
