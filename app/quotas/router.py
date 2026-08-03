"""AI 쿼터 관리 API (0033, PLAN Phase 6).

목록에는 **상한과 함께 현재 소비량**이 실린다. 상한만 보여 주는 화면은 "지금 위험한가"를
답하지 못해서, 결국 관리자가 감사 로그를 뒤지게 만든다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.authz import CONSOLE_READ_ROLES, CONSOLE_WRITE_ROLES
from app.core.deps import get_current_user, get_db, require_csrf, require_roles
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.quotas import service
from app.quotas.models import (
    ALL_PERIODS,
    GLOBAL_USER_ID,
    SCOPE_GLOBAL,
    SCOPE_USER,
    AiQuota,
)
from app.users.models import User

router = APIRouter(
    prefix="/api/admin/ai-quotas",
    tags=["admin-ai-quotas"],
    dependencies=[Depends(require_csrf)],
)


class QuotaRequest(BaseModel):
    scope_type: str = Field(default=SCOPE_GLOBAL, max_length=16)
    user_id: str | None = Field(default=None, max_length=36)
    period: str = Field(default="day", max_length=16)
    max_calls: int = Field(ge=0, le=1_000_000)
    note: str | None = Field(default=None, max_length=200)


class QuotaPatch(BaseModel):
    max_calls: int | None = Field(default=None, ge=0, le=1_000_000)
    note: str | None = Field(default=None, max_length=200)


def _get_or_404(db: Session, row_id: str) -> AiQuota:
    row = db.get(AiQuota, row_id)
    if row is None:
        raise NotFoundError("쿼터를 찾을 수 없습니다.")
    return row


@router.get("", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def list_quotas(request: Request, db: Session = Depends(get_db)) -> dict:
    now = request.app.state.clock.now()
    rows = (
        db.execute(select(AiQuota).order_by(AiQuota.scope_type, AiQuota.period, AiQuota.user_id))
        .scalars()
        .all()
    )
    from app.impersonation.service import resolve_names

    names = resolve_names(db, [r.user_id for r in rows if r.user_id])
    items = []
    for row in rows:
        item = service.view(row, names)
        item["used"] = (
            service.used_all(db, period=row.period, now=now)
            if row.scope_type == SCOPE_GLOBAL
            else service.used(db, user_id=row.user_id, period=row.period, now=now)
        )
        item["resets_at"] = service.period_end(row.period, now).isoformat()
        items.append(item)
    return {
        "items": items,
        # 화면이 "쿼터를 어디에 거는가"를 스스로 지어내지 않게 서버가 말해 준다.
        "enforced_on": [
            {"kind": service.KIND_ASSISTANT_NARRATIVE, "label": "AI 도우미 문장 생성"},
            {"kind": service.KIND_DOCUMENT_GENERATE, "label": "문서 자동 생성 요청"},
        ],
        "periods": list(ALL_PERIODS),
    }


@router.get("/usage", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def usage_summary(request: Request, db: Session = Depends(get_db), user_id: str | None = None) -> dict:
    """전체(또는 한 사용자)의 현재 기간 소비량."""
    now = request.app.state.clock.now()
    if user_id:
        return service.status(db, user_id=user_id, now=now)
    return {
        "user_id": None,
        "periods": [
            {
                "period": period,
                "limit": None,
                "source": None,
                "used": service.used_all(db, period=period, now=now),
                "resets_at": service.period_end(period, now).isoformat(),
            }
            for period in ALL_PERIODS
        ],
    }


@router.post("", status_code=201, dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def create_quota(
    request: Request,
    payload: QuotaRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> dict:
    service.validate(payload.scope_type, payload.period, payload.max_calls)
    user_id = (payload.user_id or "").strip()
    if payload.scope_type == SCOPE_USER:
        if not user_id:
            raise ValidationAppError("사용자 쿼터에는 user_id 가 필요합니다.")
        if db.get(User, user_id) is None:
            raise NotFoundError("사용자를 찾을 수 없습니다.")
    else:
        user_id = GLOBAL_USER_ID
    existing = db.execute(
        select(AiQuota).where(
            AiQuota.scope_type == payload.scope_type,
            AiQuota.user_id == user_id,
            AiQuota.period == payload.period,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("같은 범위·기간의 쿼터가 이미 있습니다. 기존 항목을 수정하세요.")

    now = request.app.state.clock.now()
    row = AiQuota(
        scope_type=payload.scope_type,
        user_id=user_id,
        period=payload.period,
        max_calls=payload.max_calls,
        note=payload.note,
        created_by=actor.id,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    record_audit_from_request(
        request, db, action="ai_quota.create", object_type="ai_quota",
        object_id=row.id, after=service.view(row),
    )
    return service.view(row)


@router.patch("/{row_id}", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def update_quota(
    request: Request, row_id: str, payload: QuotaPatch, db: Session = Depends(get_db)
) -> dict:
    row = _get_or_404(db, row_id)
    before = service.view(row)
    data = payload.model_dump(exclude_unset=True)
    if "max_calls" in data and data["max_calls"] is not None:
        service.validate(row.scope_type, row.period, data["max_calls"])
        row.max_calls = data["max_calls"]
    if "note" in data:
        row.note = data["note"]
    row.updated_at = request.app.state.clock.now()
    db.flush()
    record_audit_from_request(
        request, db, action="ai_quota.update", object_type="ai_quota",
        object_id=row.id, before=before, after=service.view(row),
    )
    return service.view(row)


@router.delete("/{row_id}", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def delete_quota(request: Request, row_id: str, db: Session = Depends(get_db)) -> dict:
    row = _get_or_404(db, row_id)
    before = service.view(row)
    db.delete(row)
    db.flush()
    record_audit_from_request(
        request, db, action="ai_quota.delete", object_type="ai_quota",
        object_id=row_id, before=before,
    )
    return {"ok": True}
