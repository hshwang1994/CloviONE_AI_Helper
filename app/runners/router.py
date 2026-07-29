"""Runner Registry API (spec §15.3, §23.4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.deps import get_db, require_csrf, require_roles
from app.core.versioning import list_versions, load_snapshot
from app.runners.models import Runner
from app.runners.provider_http import RunnerHttpProvider
from app.runners.schemas import RunnerCloneRequest, RunnerConfig, RunnerUpdateRequest
from app.runners.service import (
    OBJECT_TYPE,
    apply_runner_config,
    clone_runner,
    create_runner,
    get_runner_or_404,
    rollback_runner,
    run_runner_health_check,
    runner_snapshot,
    runner_view,
)

router = APIRouter(
    prefix="/api/admin/runners",
    tags=["admin-runners"],
    dependencies=[Depends(require_csrf)],
)

READ_ROLES = ("operator", "admin", "system_admin", "auditor")
OPS_ROLES = ("operator", "admin", "system_admin")
WRITE_ROLES = ("admin", "system_admin")


def _guard_secret_binding_create(request: Request, config: RunnerConfig) -> None:
    """secret 바인딩(auth_type != none) 생성은 system_admin만. 비-system_admin은 거절.

    integrations/router.py와 같은 규칙 — PATCH가 막는 'secret을 목적지에 묶기'를
    '새로 만들기'로 우회하지 못하게 한다. 승인 큐로 보내지 않고 하드 블록인 이유:
    secret 바인딩 CREATE는 (PATCH/rollback과 달리) 아직 존재하지 않는 대상에 처음으로
    secret을 흘려보내는 결정이라 승인자가 '기존 상태 대비 무엇이 바뀌는지' 비교할
    대상 자체가 없다 — tests/security/test_create_secret_binding_gate.py가 이 하드
    블록을 명시적으로 고정한다(승인 우회 시도로 보고 403을 기대).
    """
    from app.approvals.service import needs_approval
    from app.core.errors import ForbiddenError
    from app.core.http_client import AUTH_NONE

    if config.auth_type != AUTH_NONE and needs_approval(request.state.user):
        raise ForbiddenError(
            "secret을 대상에 묶는 Runner 생성은 system_admin 권한이 필요합니다."
        )


@router.get("", dependencies=[Depends(require_roles(*READ_ROLES))])
def list_runners(
    request: Request,
    db: Session = Depends(get_db),
    maintenance_state: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
):
    # registry.js가 이 두 값으로 select 필터를 보낸다(§등록 화면 filters) — 예전엔 여기서
    # 조용히 무시돼(WHERE 없음) UI에만 있고 실제로는 동작 안 하는 컨트롤이었다.
    stmt = select(Runner).order_by(Runner.name)
    if maintenance_state is not None:
        stmt = stmt.where(Runner.maintenance_state == maintenance_state)
    if enabled is not None:
        stmt = stmt.where(Runner.enabled == enabled)
    rows = db.execute(stmt).scalars().all()
    secrets = request.app.state.secret_provider
    return {"items": [runner_view(r, secrets) for r in rows]}


@router.post("", status_code=201, dependencies=[Depends(require_roles(*WRITE_ROLES))])
def create_runner_endpoint(
    request: Request, config: RunnerConfig, db: Session = Depends(get_db)
):
    # Spec §20: secret 바인딩(auth_type != none) 생성은 승인 대상 — 자세한 근거는
    # integrations/router.py._guard_secret_binding_create 주석 참조.
    _guard_secret_binding_create(request, config)
    row = create_runner(
        db, config,
        allowlists=request.app.state.allowlists,
        created_by=request.state.user.id,
    )
    record_audit_from_request(
        request, db, action="runner.create", object_type=OBJECT_TYPE,
        object_id=row.id, after=runner_snapshot(row),
    )
    return {"runner": runner_view(row, request.app.state.secret_provider)}


@router.get("/{runner_id}", dependencies=[Depends(require_roles(*READ_ROLES))])
def get_runner(request: Request, runner_id: str, db: Session = Depends(get_db)):
    row = get_runner_or_404(db, runner_id)
    return {"runner": runner_view(row, request.app.state.secret_provider)}


@router.patch("/{runner_id}", dependencies=[Depends(require_roles(*WRITE_ROLES))])
def update_runner(
    request: Request,
    runner_id: str,
    payload: RunnerUpdateRequest,
    db: Session = Depends(get_db),
):
    row = get_runner_or_404(db, runner_id)
    before = runner_snapshot(row)
    merged = {**before, **payload.model_dump(exclude_unset=True)}
    config = RunnerConfig.model_validate(merged)

    # Spec §20: Runner Endpoint/Secret Reference 변경은 승인 대상. health_url도
    # 포함 — secret이 다른 대상으로 전송될 수 있으므로.
    # auth_type도 포함: none→bearer 로 바꾸면 그 순간 secret이 흐른다(활성화). 빠져 있으면
    # create(none) → patch(auth_type)로 create 게이트를 우회한다. integrations와 같은 규칙.
    sensitive_change = (
        config.base_url != before["base_url"]
        or config.secret_ref != before["secret_ref"]
        or config.health_url != before["health_url"]
        or config.auth_type != before["auth_type"]
    )
    if sensitive_change:
        from app.approvals.service import approval_view, create_approval, needs_approval

        if needs_approval(request.state.user):
            # 승인 전에도 URL은 즉시 검증해 잘못된 요청을 조기에 거른다.
            request.app.state.allowlists.get("runners").check(config.base_url)
            approval = create_approval(
                db,
                request_type="runner.change_config",
                object_type="runner",
                object_id=row.id,
                requested_by=request.state.user,
                payload={"config": config.model_dump()},
                now=request.app.state.clock.now(),
            )
            record_audit_from_request(
                request, db, action="runner.change_requested", object_type=OBJECT_TYPE,
                object_id=row.id, after={"approval_id": approval.id},
            )
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=202,
                content={
                    "status": "approval_pending",
                    "approval": approval_view(approval),
                },
            )

    apply_runner_config(
        db, row, config,
        allowlists=request.app.state.allowlists,
        updated_by=request.state.user.id,
    )
    record_audit_from_request(
        request, db, action="runner.update", object_type=OBJECT_TYPE,
        object_id=row.id, before=before, after=runner_snapshot(row),
    )
    return {"runner": runner_view(row, request.app.state.secret_provider)}


def _set_enabled(request: Request, db: Session, runner_id: str, enabled: bool):
    row = get_runner_or_404(db, runner_id)
    before = runner_snapshot(row)
    config = RunnerConfig.model_validate({**before, "enabled": enabled})
    apply_runner_config(
        db, row, config,
        allowlists=request.app.state.allowlists,
        updated_by=request.state.user.id,
    )
    record_audit_from_request(
        request, db,
        action="runner.enable" if enabled else "runner.disable",
        object_type=OBJECT_TYPE, object_id=row.id,
        before=before, after=runner_snapshot(row),
    )
    return {"ok": True, "enabled": enabled}


@router.post("/{runner_id}/enable", dependencies=[Depends(require_roles(*WRITE_ROLES))])
def enable_runner(request: Request, runner_id: str, db: Session = Depends(get_db)):
    return _set_enabled(request, db, runner_id, True)


@router.post("/{runner_id}/disable", dependencies=[Depends(require_roles(*WRITE_ROLES))])
def disable_runner(request: Request, runner_id: str, db: Session = Depends(get_db)):
    return _set_enabled(request, db, runner_id, False)


@router.post("/{runner_id}/health", dependencies=[Depends(require_roles(*OPS_ROLES))])
def health_check(request: Request, runner_id: str, db: Session = Depends(get_db)):
    row = get_runner_or_404(db, runner_id)
    result = run_runner_health_check(
        db, row,
        outbound=request.app.state.outbound_client,
        now=request.app.state.clock.now(),
    )
    return {"runner_id": row.id, **result}


@router.post("/{runner_id}/test", dependencies=[Depends(require_roles(*OPS_ROLES))])
def test_request(request: Request, runner_id: str, db: Session = Depends(get_db)):
    row = get_runner_or_404(db, runner_id)
    provider = RunnerHttpProvider(request.app.state.outbound_client)
    # Test path bypasses the enabled gate deliberately: new runners are tested
    # while disabled (spec §15.5). Circuit/maintenance rules still apply inside
    # invoke for enabled runners; here we call the raw ping.
    now = request.app.state.clock.now()
    from app.runners.provider_http import RunnerUnavailableError
    from app.runners.service import record_runner_result

    try:
        response = request.app.state.outbound_client.post(
            row.base_url,
            allowlist="runners",
            json={"ping": True, "test": True},
            timeout=float(row.timeout_seconds),
            auth_type=row.auth_type,
            secret_ref=row.secret_ref,
        )
    except Exception as exc:
        record_runner_result(db, row, success=False, now=now)
        from app.core.http_client import is_timeout_error, is_transport_error

        if is_timeout_error(exc) or is_transport_error(exc):
            raise RunnerUnavailableError("Runner에 연결할 수 없습니다.") from exc
        raise
    record_runner_result(db, row, success=response.status_code < 500, now=now)
    return {
        "ok": response.status_code < 400,
        "status_code": response.status_code,
    }


@router.post("/{runner_id}/clone", dependencies=[Depends(require_roles(*WRITE_ROLES))])
def clone(
    request: Request,
    runner_id: str,
    payload: RunnerCloneRequest,
    db: Session = Depends(get_db),
):
    source = get_runner_or_404(db, runner_id)
    # 복제는 원본의 secret 바인딩(auth_type·secret_ref)을 그대로 가져온다. '새로 만들기'와
    # 'PATCH'가 막는 secret 바인딩을 '복제'로 우회하지 못하게 같은 게이트를 적용한다
    # (round16 제품 스윕: admin이 system_admin 전용 secret 바인딩 러너를 복제로 우회).
    _guard_secret_binding_create(
        request, RunnerConfig.model_validate({**runner_snapshot(source), "name": payload.name})
    )
    row = clone_runner(
        db, source, payload.name,
        allowlists=request.app.state.allowlists,
        created_by=request.state.user.id,
    )
    record_audit_from_request(
        request, db, action="runner.clone", object_type=OBJECT_TYPE,
        object_id=row.id, after={"cloned_from": source.id, **runner_snapshot(row)},
    )
    return {"runner": runner_view(row, request.app.state.secret_provider)}


@router.get("/{runner_id}/versions", dependencies=[Depends(require_roles(*READ_ROLES))])
def get_versions(runner_id: str, db: Session = Depends(get_db)):
    get_runner_or_404(db, runner_id)
    rows = list_versions(db, OBJECT_TYPE, runner_id)
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


@router.post("/{runner_id}/rollback", dependencies=[Depends(require_roles(*WRITE_ROLES))])
def rollback(
    request: Request, runner_id: str, payload: _RollbackBody,
    db: Session = Depends(get_db),
):
    from app.core.versioning import get_version, load_snapshot
    from app.runners.schemas import RunnerConfig

    version = payload.version
    row = get_runner_or_404(db, runner_id)
    before = runner_snapshot(row)

    # Spec §20: a rollback that changes base_url/secret_ref is a sensitive change
    # and must go through the same approval gate as PATCH — not a bypass.
    snapshot = load_snapshot(get_version(db, OBJECT_TYPE, row.id, version))
    target = RunnerConfig.model_validate(snapshot)
    sensitive = (
        target.base_url != before["base_url"]
        or target.secret_ref != before["secret_ref"]
        or target.health_url != before["health_url"]
        or target.auth_type != before["auth_type"]
    )
    if sensitive:
        from app.approvals.service import approval_view, create_approval, needs_approval

        if needs_approval(request.state.user):
            approval = create_approval(
                db, request_type="runner.change_config", object_type="runner",
                object_id=row.id, requested_by=request.state.user,
                payload={"config": target.model_dump()},
                now=request.app.state.clock.now(),
            )
            record_audit_from_request(
                request, db, action="runner.rollback_requested", object_type=OBJECT_TYPE,
                object_id=row.id, after={"approval_id": approval.id, "version": version},
            )
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=202,
                content={"status": "approval_pending", "approval": approval_view(approval)},
            )

    rollback_runner(
        db, row, version,
        allowlists=request.app.state.allowlists,
        updated_by=request.state.user.id,
    )
    record_audit_from_request(
        request, db, action="runner.rollback", object_type=OBJECT_TYPE,
        object_id=row.id, before=before,
        after={**runner_snapshot(row), "rolled_back_to": version},
    )
    return {"runner": runner_view(row, request.app.state.secret_provider)}
