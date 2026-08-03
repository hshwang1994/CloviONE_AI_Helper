"""Workflow Registry API (spec §16, §23.5 metadata part)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.authz import CONSOLE_OPS_ROLES, CONSOLE_READ_ROLES, CONSOLE_WRITE_ROLES
from app.core.deps import get_db, require_csrf, require_roles
from app.core.versioning import list_versions, load_snapshot
from app.workflows.models import Workflow
from app.workflows.provider_n8n import N8nWorkflowProvider
from app.workflows.schemas import WorkflowConfig, WorkflowUpdateRequest
from app.workflows.service import (
    OBJECT_TYPE,
    apply_workflow_config,
    create_workflow,
    get_workflow_or_404,
    rollback_workflow,
    workflow_snapshot,
    workflow_view,
)

router = APIRouter(
    prefix="/api/admin/workflows",
    tags=["admin-workflows"],
    dependencies=[Depends(require_csrf)],
)



@router.get("", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def list_workflows(db: Session = Depends(get_db)):
    rows = db.execute(select(Workflow).order_by(Workflow.name)).scalars().all()
    return {"items": [workflow_view(r) for r in rows]}


@router.post("", status_code=201, dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def create_workflow_endpoint(
    request: Request, config: WorkflowConfig, db: Session = Depends(get_db)
):
    row = create_workflow(
        db, config,
        allowlists=request.app.state.allowlists,
        created_by=request.state.user.id,
    )
    record_audit_from_request(
        request, db, action="workflow.create", object_type=OBJECT_TYPE,
        object_id=row.id, after=workflow_snapshot(row),
    )
    return {"workflow": workflow_view(row)}


@router.get("/{workflow_id}", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def get_workflow(workflow_id: str, db: Session = Depends(get_db)):
    return {"workflow": workflow_view(get_workflow_or_404(db, workflow_id))}


@router.patch("/{workflow_id}", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def update_workflow(
    request: Request,
    workflow_id: str,
    payload: WorkflowUpdateRequest,
    db: Session = Depends(get_db),
):
    row = get_workflow_or_404(db, workflow_id)
    before = workflow_snapshot(row)
    merged = {**before, **payload.model_dump(exclude_unset=True)}
    # WorkflowConfig.tags는 list[str](None 불허)이지만, 폼에서 이전에 채운 태그를 모두 지우면
    # kit.jsx 관례상 명시적으로 null을 보낸다 — merged['tags']가 None이 되어 검증이 깨졌었다
    # (재현: PATCH {"tags": null} -> 500). '지움'을 빈 배열로 정규화한다.
    if merged.get("tags") is None:
        merged["tags"] = []
    config = WorkflowConfig.model_validate(merged)
    apply_workflow_config(
        db, row, config,
        allowlists=request.app.state.allowlists,
        updated_by=request.state.user.id,
    )
    record_audit_from_request(
        request, db, action="workflow.update", object_type=OBJECT_TYPE,
        object_id=row.id, before=before, after=workflow_snapshot(row),
    )
    return {"workflow": workflow_view(row)}


def _set_enabled(request: Request, db: Session, workflow_id: str, enabled: bool):
    row = get_workflow_or_404(db, workflow_id)
    before = workflow_snapshot(row)
    config = WorkflowConfig.model_validate({**before, "enabled": enabled})
    apply_workflow_config(
        db, row, config,
        allowlists=request.app.state.allowlists,
        updated_by=request.state.user.id,
    )
    record_audit_from_request(
        request, db,
        action="workflow.enable" if enabled else "workflow.disable",
        object_type=OBJECT_TYPE, object_id=row.id, before=before,
        after=workflow_snapshot(row),
    )
    return {"ok": True, "enabled": enabled}


@router.post("/{workflow_id}/enable", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def enable_workflow(request: Request, workflow_id: str, db: Session = Depends(get_db)):
    return _set_enabled(request, db, workflow_id, True)


@router.post("/{workflow_id}/disable", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def disable_workflow(request: Request, workflow_id: str, db: Session = Depends(get_db)):
    return _set_enabled(request, db, workflow_id, False)


@router.post("/{workflow_id}/test", dependencies=[Depends(require_roles(*CONSOLE_OPS_ROLES))])
def test_workflow(request: Request, workflow_id: str, db: Session = Depends(get_db)):
    row = get_workflow_or_404(db, workflow_id)
    provider = N8nWorkflowProvider(request.app.state.outbound_client)
    result = provider.test(db, row, now=request.app.state.clock.now())
    # create/update/enable/disable/rollback 모두 감사에 남는데 test만 빠져 있었다 —
    # 연결성 검사도 last_test_status/last_test_at을 실제로 영속시키는 변경이라 남긴다.
    record_audit_from_request(
        request, db, action="workflow.test", object_type=OBJECT_TYPE,
        object_id=row.id, after={"status": result.get("status"), "detail": result.get("detail")},
    )
    return {"workflow_id": row.id, **result}


@router.get("/{workflow_id}/versions", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def get_versions(workflow_id: str, db: Session = Depends(get_db)):
    get_workflow_or_404(db, workflow_id)
    rows = list_versions(db, OBJECT_TYPE, workflow_id)
    # 프롬프트/정책 버전 기록은 created_by를 이름/이메일로 해석해 보여 주는데 여기만 원시
    # UUID였다 — '누가 이 변경을 했나/되돌릴까'가 목적이므로 같은 해석을 붙인다(round30 감사 E).
    from app.approvals.service import resolve_names

    names = resolve_names(db, {r.created_by for r in rows})
    return {
        "items": [
            {
                "version": r.version,
                "snapshot": load_snapshot(r),
                "created_by": r.created_by,
                "created_by_name": (
                    names.get(r.created_by, {}).get("display_name") if r.created_by else None
                ),
                "created_by_email": (
                    names.get(r.created_by, {}).get("email") if r.created_by else None
                ),
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }


class _RollbackBody(BaseModel):
    version: int


@router.post("/{workflow_id}/rollback", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def rollback(
    request: Request, workflow_id: str, payload: _RollbackBody,
    db: Session = Depends(get_db),
):
    version = payload.version
    row = get_workflow_or_404(db, workflow_id)
    before = workflow_snapshot(row)
    rollback_workflow(
        db, row, version,
        allowlists=request.app.state.allowlists,
        updated_by=request.state.user.id,
    )
    record_audit_from_request(
        request, db, action="workflow.rollback", object_type=OBJECT_TYPE,
        object_id=row.id, before=before,
        after={**workflow_snapshot(row), "rolled_back_to": version},
    )
    return {"workflow": workflow_view(row)}
