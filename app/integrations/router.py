"""Integration Registry API (spec §14.3, §23.4).

Read + health check: operator and above. Mutations: admin and above.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.authz import CONSOLE_OPS_ROLES, CONSOLE_READ_ROLES, CONSOLE_WRITE_ROLES
from app.core.deps import get_db, require_csrf, require_roles
from app.core.versioning import list_versions, load_snapshot
from app.integrations.models import Integration
from app.integrations.schemas import IntegrationConfig, IntegrationUpdateRequest
from app.integrations.service import (
    OBJECT_TYPE,
    apply_integration_config,
    create_integration,
    get_integration_or_404,
    integration_snapshot,
    integration_view,
    rollback_integration,
    run_health_check,
)

router = APIRouter(
    prefix="/api/admin/integrations",
    tags=["admin-integrations"],
    dependencies=[Depends(require_csrf)],
)



def _guard_secret_binding_create(request: Request, config: IntegrationConfig) -> None:
    """secret 바인딩(auth_type != none) 생성은 system_admin만. 비-system_admin은 거절."""
    from app.approvals.service import needs_approval
    from app.core.errors import ForbiddenError
    from app.core.http_client import AUTH_NONE

    if config.auth_type != AUTH_NONE and needs_approval(request.state.user):
        raise ForbiddenError(
            "secret을 대상에 묶는 Integration 생성은 system_admin 권한이 필요합니다."
        )


@router.get("", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def list_integrations(request: Request, db: Session = Depends(get_db)):
    rows = db.execute(select(Integration).order_by(Integration.name)).scalars().all()
    secrets = request.app.state.secret_provider
    return {"items": [integration_view(r, secrets) for r in rows]}


@router.post("", status_code=201, dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def create_integration_endpoint(
    request: Request, config: IntegrationConfig, db: Session = Depends(get_db)
):
    # Spec §20: secret을 대상에 묶는 것(auth_type != none 이면 OutboundClient가 secret_ref를
    # 실어 보낸다)은 승인 대상이다. PATCH가 막는 '기존 대상의 목적지 바꾸기'를 '새로 만들기'로
    # 그대로 달성할 수 있으면 게이트는 무의미하다 — allowlist는 외부 유출만 막고, 허용된 내부
    # 서비스끼리(n8n:5678 → 러너:8787) secret을 옮기는 것은 막지 못한다. 그래서 secret 바인딩
    # 생성은 PATCH와 같은 권한(system_admin)을 요구한다. (승인 실행기는 '기존 객체 수정'만
    # 재생하므로, 생성은 승인-대기 대신 즉시 거절로 게이트한다.)
    _guard_secret_binding_create(request, config)
    row = create_integration(
        db,
        config,
        allowlists=request.app.state.allowlists,
        created_by=request.state.user.id,
    )
    record_audit_from_request(
        request, db, action="integration.create", object_type=OBJECT_TYPE,
        object_id=row.id, after=integration_snapshot(row),
    )
    return {"integration": integration_view(row, request.app.state.secret_provider)}


@router.get("/{integration_id}", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def get_integration(request: Request, integration_id: str, db: Session = Depends(get_db)):
    row = get_integration_or_404(db, integration_id)
    return {"integration": integration_view(row, request.app.state.secret_provider)}


@router.patch("/{integration_id}", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def update_integration(
    request: Request,
    integration_id: str,
    payload: IntegrationUpdateRequest,
    db: Session = Depends(get_db),
):
    row = get_integration_or_404(db, integration_id)
    before = integration_snapshot(row)
    merged = {**before, **payload.model_dump(exclude_unset=True)}
    config = IntegrationConfig.model_validate(merged)

    # Spec §20: base_url / secret_ref 변경은 승인 대상. health_url도 포함 — 헬스체크가
    # 그 주소로 secret을 실어 보내므로(service.py run_health_check: url = health_url or base_url),
    # 이 값을 바꾸는 것은 secret을 다른 대상에게 보내는 일이다.
    # allowlist는 '외부로 못 나간다'만 보장한다. 허용된 내부 서비스끼리는 자유롭게 옮길 수 있어서
    # (n8n:5678 → 러너:8787), '어느 내부 서비스로 가느냐'는 이 게이트가 지켜야 한다.
    # 같은 판정이 runners/router.py에는 이유 주석까지 달려 이미 있었다 — 복붙이 갈라진 자리였다.
    # auth_type도 포함: secret_ref·base_url이 이미 잡힌 객체를 none→bearer로 바꾸면 그 순간
    # secret이 흐르기 시작한다(활성화). auth_type이 빠져 있으면 create(none) → patch(auth_type)로
    # create 게이트를 우회한다.
    sensitive = (
        config.base_url != before["base_url"]
        or config.secret_ref != before["secret_ref"]
        or config.health_url != before["health_url"]
        or config.auth_type != before["auth_type"]
    )
    if sensitive:
        from app.approvals.service import approval_view, create_approval, needs_approval

        if needs_approval(request.state.user):
            request.app.state.allowlists.get("services").check(config.base_url)
            approval = create_approval(
                db, request_type="integration.change_config", object_type=OBJECT_TYPE,
                object_id=row.id, requested_by=request.state.user,
                payload={"config": config.model_dump()},
                now=request.app.state.clock.now(),
            )
            record_audit_from_request(
                request, db, action="integration.change_requested", object_type=OBJECT_TYPE,
                object_id=row.id, after={"approval_id": approval.id},
            )
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=202,
                content={"status": "approval_pending", "approval": approval_view(approval)},
            )

    apply_integration_config(
        db, row, config,
        allowlists=request.app.state.allowlists,
        updated_by=request.state.user.id,
    )
    record_audit_from_request(
        request, db, action="integration.update", object_type=OBJECT_TYPE,
        object_id=row.id, before=before, after=integration_snapshot(row),
    )
    return {"integration": integration_view(row, request.app.state.secret_provider)}


def _set_enabled(request: Request, db: Session, integration_id: str, enabled: bool):
    row = get_integration_or_404(db, integration_id)
    before = integration_snapshot(row)
    config = IntegrationConfig.model_validate({**before, "enabled": enabled})
    apply_integration_config(
        db, row, config,
        allowlists=request.app.state.allowlists,
        updated_by=request.state.user.id,
    )
    record_audit_from_request(
        request, db,
        action="integration.enable" if enabled else "integration.disable",
        object_type=OBJECT_TYPE, object_id=row.id,
        before=before, after=integration_snapshot(row),
    )
    return {"ok": True, "enabled": enabled}


@router.post("/{integration_id}/enable", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def enable_integration(request: Request, integration_id: str, db: Session = Depends(get_db)):
    return _set_enabled(request, db, integration_id, True)


@router.post("/{integration_id}/disable", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def disable_integration(request: Request, integration_id: str, db: Session = Depends(get_db)):
    return _set_enabled(request, db, integration_id, False)


@router.post(
    "/{integration_id}/health",
    dependencies=[Depends(require_roles(*CONSOLE_OPS_ROLES))],
)
def health_check(request: Request, integration_id: str, db: Session = Depends(get_db)):
    row = get_integration_or_404(db, integration_id)
    result = run_health_check(
        db,
        row,
        outbound=request.app.state.outbound_client,
        now=request.app.state.clock.now(),
    )
    return {"integration_id": row.id, **result}


@router.get(
    "/{integration_id}/versions",
    dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))],
)
def get_versions(integration_id: str, db: Session = Depends(get_db)):
    get_integration_or_404(db, integration_id)
    rows = list_versions(db, OBJECT_TYPE, integration_id)
    return {
        "items": [
            {
                "version": r.version,
                "snapshot": load_snapshot(r),
                "created_by": r.created_by,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }


class _RollbackBody(BaseModel):
    version: int


@router.post(
    "/{integration_id}/rollback",
    dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))],
)
def rollback(
    request: Request, integration_id: str, payload: _RollbackBody,
    db: Session = Depends(get_db),
):
    from app.core.versioning import get_version, load_snapshot

    version = payload.version
    row = get_integration_or_404(db, integration_id)
    before = integration_snapshot(row)

    # Spec §20: base_url/secret_ref/health_url을 바꾸는 롤백은 PATCH와 같은 승인 게이트를
    # 지나야 한다. health_url이 빠져 있으면 PATCH만 막는 것이 의미가 없다 — 과거 버전으로
    # 되돌리는 것만으로 secret의 목적지를 옮길 수 있기 때문이다.
    snapshot = load_snapshot(get_version(db, OBJECT_TYPE, row.id, version))
    target = IntegrationConfig.model_validate(snapshot)
    sensitive = (
        target.base_url != before["base_url"]
        or target.secret_ref != before["secret_ref"]
        or target.health_url != before["health_url"]
        or target.auth_type != before["auth_type"]
    )
    if sensitive:
        from app.approvals.service import approval_view, create_approval, needs_approval

        if needs_approval(request.state.user):
            request.app.state.allowlists.get("services").check(target.base_url)
            approval = create_approval(
                db, request_type="integration.change_config", object_type=OBJECT_TYPE,
                object_id=row.id, requested_by=request.state.user,
                payload={"config": target.model_dump()},
                now=request.app.state.clock.now(),
            )
            record_audit_from_request(
                request, db, action="integration.rollback_requested", object_type=OBJECT_TYPE,
                object_id=row.id, after={"approval_id": approval.id, "version": version},
            )
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=202,
                content={"status": "approval_pending", "approval": approval_view(approval)},
            )

    rollback_integration(
        db, row, version,
        allowlists=request.app.state.allowlists,
        updated_by=request.state.user.id,
    )
    record_audit_from_request(
        request, db, action="integration.rollback", object_type=OBJECT_TYPE,
        object_id=row.id, before=before,
        after={**integration_snapshot(row), "rolled_back_to": version},
    )
    return {"integration": integration_view(row, request.app.state.secret_provider)}
