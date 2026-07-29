"""Notion user mapping service (spec §12).

Mapping is keyed on the login account email matching a Notion People email.
The web app never sends the email string as a People property value and never
accepts a Notion user id from the browser (spec §12.3) — the id is resolved
only via the approved mapping workflow, or set explicitly by an admin.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.notion_mapping.models import (
    SOURCE_MANUAL,
    SOURCE_WORKFLOW,
    STATUS_CONFLICT,
    STATUS_UNMAPPED,
    STATUS_VERIFIED,
    UserNotionMapping,
)
from app.users.models import User
from app.workflows.models import Workflow
from app.workflows.provider_n8n import N8nWorkflowProvider

# Reserved workflow name that resolves login email → Notion People user.
MAPPING_WORKFLOW_NAME = "notion-user-mapping"

_NOTION_USER_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def get_or_create_mapping(db: Session, user_id: str) -> UserNotionMapping:
    row = db.execute(
        select(UserNotionMapping).where(UserNotionMapping.user_id == user_id)
    ).scalar_one_or_none()
    if row is None:
        row = UserNotionMapping(user_id=user_id, status=STATUS_UNMAPPED)
        db.add(row)
        db.flush()
    return row


def mapping_status(db: Session, user_id: str) -> str:
    row = db.execute(
        select(UserNotionMapping).where(UserNotionMapping.user_id == user_id)
    ).scalar_one_or_none()
    return row.status if row is not None else STATUS_UNMAPPED


def get_mapping_workflow(db: Session) -> Workflow | None:
    return db.execute(
        select(Workflow).where(Workflow.name == MAPPING_WORKFLOW_NAME)
    ).scalar_one_or_none()


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


def verify_mapping(
    db: Session,
    user: User,
    *,
    outbound,
    now: datetime,
) -> UserNotionMapping:
    """Query the mapping workflow and cache the result (spec §12.1)."""
    row = get_or_create_mapping(db, user.id)
    workflow = get_mapping_workflow(db)
    if workflow is None or not workflow.enabled:
        # Clear any previously cached mapping so a now-disabled workflow does not
        # leave a stale verified notion_user_id/source behind (must read as unmapped).
        row.status = STATUS_UNMAPPED
        row.notion_user_id = None
        row.notion_email = None
        row.source = None
        row.candidates_json = None
        row.error_message = "Notion 매핑 Workflow가 구성/활성화되지 않았습니다."
        row.last_verified_at = now
        db.flush()
        return row

    provider = N8nWorkflowProvider(outbound)
    try:
        result = provider.invoke(
            workflow, {"action": "lookup_user", "email": user.email}, timeout=30.0
        )
    except Exception as exc:
        row.error_message = f"매핑 조회 실패: {type(exc).__name__}"
        row.last_verified_at = now
        db.flush()
        return row

    matches = result.get("matches", []) if isinstance(result, dict) else []
    if not isinstance(matches, list):
        matches = []

    row.last_verified_at = now
    row.source = SOURCE_WORKFLOW
    if len(matches) == 1 and (matches[0].get("notion_user_id") or "").strip():
        m = matches[0]
        row.status = STATUS_VERIFIED
        row.notion_user_id = str(m.get("notion_user_id")).strip()
        row.notion_email = m.get("notion_email")
        row.error_message = None
        row.candidates_json = None
    elif len(matches) == 1:
        # A single match with no usable notion_user_id is not a valid mapping.
        row.status = STATUS_UNMAPPED
        row.notion_user_id = None
        row.notion_email = None
        row.error_message = "일치 항목에 Notion user id가 없습니다."
        row.candidates_json = None
    elif len(matches) == 0:
        row.status = STATUS_UNMAPPED
        row.notion_user_id = None
        row.notion_email = None
        row.error_message = "일치하는 Notion 사용자가 없습니다."
        row.candidates_json = None
    else:
        # 충돌로 내려갈 때도 이전에 검증됐던 notion_email을 지운다 — 안 지우면 배지는
        # '충돌'인데 목록/상세엔 더 이상 유효하지 않은 옛 이메일이 그대로 남는다.
        row.status = STATUS_CONFLICT
        row.notion_user_id = None
        row.notion_email = None
        row.error_message = f"{len(matches)}명이 일치하여 충돌합니다. 관리자 해결 필요."
        row.candidates_json = json.dumps(matches, ensure_ascii=False)
    db.flush()
    return row


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


def resolve_conflict(
    db: Session, user: User, *, notion_user_id: str, now: datetime
) -> UserNotionMapping:
    row = get_or_create_mapping(db, user.id)
    if row.status != STATUS_CONFLICT:
        raise ConflictError("충돌 상태의 매핑만 해결할 수 있습니다.")
    candidates = json.loads(row.candidates_json or "[]")
    chosen = next(
        (c for c in candidates if str(c.get("notion_user_id")) == notion_user_id), None
    )
    if chosen is None:
        raise ValidationAppError("후보 목록에 없는 Notion user id입니다.")
    return manual_map(
        db, user, notion_user_id=notion_user_id,
        notion_email=chosen.get("notion_email"), now=now,
    )


# First-person request detection for safe-refusal (spec §12.3).
_FIRST_PERSON = re.compile(
    r"(내\s*(티켓|프로젝트|담당|할당|업무|작업)|나의|제\s*(티켓|프로젝트)|my\s+(ticket|project))",
    re.IGNORECASE,
)


def is_first_person_request(content: str) -> bool:
    return bool(_FIRST_PERSON.search(content or ""))
