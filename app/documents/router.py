"""Document automation API (spec §19)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.observability.service import EVENT_DOCUMENT_GENERATE, record_usage
from app.core.authz import CONSOLE_READ_ROLES, CONSOLE_WRITE_ROLES
from app.core.deps import get_db, require_csrf, require_roles
from app.core.pagination import PageParams
from app.documents.models import DocumentGeneration
from app.documents.service import (
    generation_view,
    get_generation_or_404,
    request_generation,
    retry_generation,
)

router = APIRouter(
    prefix="/api/admin/documents",
    tags=["admin-documents"],
    dependencies=[Depends(require_csrf)],
)



class GenerateRequest(BaseModel):
    workflow_id: str
    mode: str = "preview_then_approve"
    period: str = Field(min_length=1, max_length=64)
    config: dict = Field(default_factory=dict)

    @field_validator("config", mode="before")
    @classmethod
    def _config_default(cls, v):
        # 관리자 콘솔의 빈 JSON 입력은 null로 온다 — 선택 필드이므로 빈 객체로 본다(round16 스윕 B2).
        return {} if v is None else v


@router.get("", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def list_generations(
    db: Session = Depends(get_db),
    page: PageParams = Depends(),
    status: str | None = Query(default=None, max_length=24),
):
    stmt = select(DocumentGeneration)
    if status:
        stmt = stmt.where(DocumentGeneration.status == status)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(DocumentGeneration.created_at.desc())
            .offset(page.offset)
            .limit(page.page_size)
        )
        .scalars()
        .all()
    )
    # 요청자(requested_by)는 지금껏 원시 UUID로만 내려가 운영/감사 화면에서 '누가
    # 요청했나'를 알 수 없었다 — 승인 화면과 같은 패턴으로 페이지의 요청자 id를 한 번에
    # 이름/이메일로 해석해(N+1 회피) 각 행에 붙인다(round30 감사 E).
    from app.approvals.service import resolve_names

    names = resolve_names(db, {r.requested_by for r in rows})

    def _with_requester(r: DocumentGeneration) -> dict:
        view = generation_view(r)
        info = names.get(r.requested_by or "")
        view["requested_by_name"] = info.get("display_name") if info else None
        view["requested_by_email"] = info.get("email") if info else None
        return view

    return {
        "items": [_with_requester(r) for r in rows],
        "total": total,
        "page": page.page,
        "page_size": page.page_size,
    }


@router.post("/generate", status_code=202, dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def generate(request: Request, payload: GenerateRequest, db: Session = Depends(get_db)):
    # document_automation_enabled는 이제 관리 콘솔 Settings 화면에서 켜고 끌 수 있는
    # settings_cache 값이다(예전엔 서버 파일로만 존재해 화면에 노출되지 않았다).
    doc_automation_enabled = bool(
        request.app.state.settings_cache.current_value("document_automation_enabled")
    )
    gen = request_generation(
        db,
        workflow_id=payload.workflow_id,
        mode=payload.mode,
        config=payload.config,
        period=payload.period,
        requested_by=request.state.user.id,
        now=request.app.state.clock.now(),
        document_automation_enabled=doc_automation_enabled,
    )
    record_audit_from_request(
        request, db, action="document.generate_requested",
        object_type="document_generation", object_id=gen.id,
        after={"mode": gen.mode, "workflow_id": gen.workflow_id},
    )
    # 사용 통계(0026) — 저빈도 지점(문서 생성은 사람이 폼으로 한 번 누르는 행동이다).
    record_usage(
        db, event=EVENT_DOCUMENT_GENERATE, user_id=request.state.user.id,
        org_id=getattr(request.state.user, "org_id", None),
        object_type="document_generation", object_id=gen.id,
        now=request.app.state.clock.now(),
    )
    return {"generation": generation_view(gen)}


@router.post(
    "/{generation_id}/retry",
    status_code=202,
    dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))],
)
def retry(request: Request, generation_id: str, db: Session = Depends(get_db)):
    # 실패/품질 실패 행을 같은 레코드로 다시 큐에 넣는다 — 생성 폼 재오픈(같은 기간·대상
    # 새 생성 → idempotency 중복 409)의 막다른 길을 없앤다(round30 감사 E High).
    gen = get_generation_or_404(db, generation_id)
    retry_generation(db, gen, now=request.app.state.clock.now())
    record_audit_from_request(
        request, db, action="document.retry_requested",
        object_type="document_generation", object_id=gen.id,
        after={"status": gen.status},
    )
    return {"generation": generation_view(gen)}


@router.get("/{generation_id}", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def get_generation(generation_id: str, db: Session = Depends(get_db)):
    return {"generation": generation_view(get_generation_or_404(db, generation_id))}
