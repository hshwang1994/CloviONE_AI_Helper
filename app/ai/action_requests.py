"""승인을 기다리는 AI 쓰기 — 작업 공간 초안의 저장 승인 (계획 3.9, D-519).

## 흐름

1. 쓰기 승인 정책이 걸린 사람이 작업 공간에서 초안을 저장한다(`POST /api/ai/documents`).
2. 초안은 만들어지지만 **문서는 아직 없다.** 이 모듈이 `ai_action_requests` 한 행에 초안을 두고 승인 요청
   (`ai.document_create`)을 만든다. 승인 요청의 내용(payload)에는 제목과 글자 수만 싣는다 - 긴 본문은 중복 검사
   인덱스에 들어갈 수 없다.
3. 결재자가 승인하면 실행기(`execute_document_create`)가 **그 순간의** 요청자 권한을 다시 확인하고(계정이 살아
   있는가, 문서를 만들 권한이 있는가, 그 자리를 볼 수 있는가) 문서를 만든다. 하나라도 틀리면 409 로 승인을 막는다 -
   승인이 요청자에게 없는 권한을 대신 행사하게 두지 않는다.
4. 거절, 만료, 취소는 아무것도 만들지 않는다.

초안 미리 보기(`GET /api/approvals/ai-drafts/{id}`, `app/approvals/router.py`)는 요청한 사람과, 그 승인 요청을 볼 수 있는 사람(결재할 수 있는
사람, 관리 범위 안의 콘솔 사용자)만 연다.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, ForbiddenError, NotFoundError

REQUEST_TYPE = "ai.document_create"
OBJECT_TYPE = "ai_action_request"


def target_of(row) -> dict:
    try:
        value = json.loads(row.target_json or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def request_document(db: Session, user, *, action_key: str, title: str, text: str, space_id: str | None,
                     project_id: str | None, folder_id: str | None, policy_id: str | None, now: datetime):
    """초안을 문서 대신 승인 요청으로 남긴다. (요청 행, 승인 요청)을 돌려준다."""
    from app.ai.models import AiActionRequest
    from app.approvals.service import create_approval

    clean_title = (title or "").strip()
    row = AiActionRequest(
        id=str(uuid.uuid4()), action_key=action_key, requested_by=user.id, title=clean_title,
        target_json=json.dumps({"space_id": space_id, "project_id": project_id, "folder_id": folder_id}),
        output_text=text, policy_id=policy_id, created_at=now,
    )
    db.add(row)
    db.flush()
    approval = create_approval(
        db, request_type=REQUEST_TYPE, object_type=OBJECT_TYPE, object_id=row.id, requested_by=user,
        # 결재함은 `target_name` 으로 「무엇을」 한 문장에 적는다(`MyApprovals.jsx::decisionSummary`).
        payload={"title": clean_title, "target_name": clean_title, "chars": len(text or ""),
                 "space_id": space_id, "project_id": project_id},
        now=now,
    )
    row.approval_id = approval.id
    db.flush()
    return row, approval


def execute_document_create(db: Session, approval, app_state) -> None:
    """승인 실행기. 요청자의 권한을 **지금** 다시 보고 문서를 만든다. 틀리면 409 로 승인을 막는다."""
    from app.ai.models import AiActionRequest
    from app.authz import permissions as perms
    from app.authz.service import effective_permissions
    from app.core.audit import record_audit
    from app.knowledge import blocks
    from app.knowledge import service as knowledge_service
    from app.knowledge.models import SOURCE_AI
    from app.users.models import User

    row = db.get(AiActionRequest, approval.object_id)
    if row is None:
        raise ConflictError("승인할 AI 초안이 더 이상 없습니다.")
    if row.document_id:
        raise ConflictError("이미 문서로 만든 초안입니다.")
    user = db.get(User, row.requested_by)
    if user is None or not user.active or user.archived_at is not None:
        raise ConflictError("요청한 사람의 계정이 활성 상태가 아니라 문서를 만들 수 없습니다.")
    if perms.DOCUMENT_CREATE not in effective_permissions(db, user):
        raise ConflictError("요청한 사람에게 문서를 만들 권한이 없어져 승인할 수 없습니다.")
    target = target_of(row)
    try:
        document = knowledge_service.create_document(
            db, user, space_id=target.get("space_id"), project_id=target.get("project_id"),
            folder_id=target.get("folder_id"), title=row.title, body=blocks.from_plain_text(row.output_text),
            source_type=SOURCE_AI,
        )
    except (NotFoundError, ForbiddenError):
        raise ConflictError("요청한 사람이 지정한 위치에 문서를 만들 수 없게 되어 승인할 수 없습니다.") from None
    now = app_state.clock.now()
    row.document_id = document.id
    row.executed_at = now
    db.flush()
    record_audit(
        db, actor_id=approval.approver_id, action="ai.document.created_on_approval",
        object_type="knowledge_document", object_id=document.id,
        after={"request_id": row.id, "requested_by": row.requested_by, "space_id": document.space_id},
    )


def request_view(db: Session, row) -> dict:
    """미리 보기 한 건. 요청자 이름과 승인 상태를 함께 준다."""
    from app.ai.actions import ACTIONS
    from app.approvals.models import Approval
    from app.impersonation.service import resolve_names

    approval = db.get(Approval, row.approval_id) if row.approval_id else None
    person = resolve_names(db, [row.requested_by]).get(row.requested_by, {})
    return {
        "id": row.id,
        "action_key": row.action_key,
        "action_label": ACTIONS[row.action_key].label if row.action_key in ACTIONS else row.action_key,
        "title": row.title,
        "output_text": row.output_text,
        "target": target_of(row),
        "requested_by": row.requested_by,
        "requester_name": person.get("display_name"),
        "approval_id": row.approval_id,
        "approval_status": approval.status if approval is not None else None,
        "document_id": row.document_id,
        "document_route": f"/knowledge/{row.document_id}" if row.document_id else None,
        "created_at": row.created_at.isoformat(),
    }
