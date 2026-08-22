"""오프보딩 API (Phase 6).

경로 설계 메모: 단건 경로가 `/{run_id}` 하나뿐이라 `/preview/{user_id}` 처럼 **두 세그먼트**인
경로는 그것과 절대 충돌하지 않는다(Starlette 는 선언 순서로 매칭하지만, 세그먼트 수가 다르면
순서와 무관하게 안전하다). 정적 경로가 경로 파라미터에 가려지는 함정을 구조로 없앤다.

감사: 실행과 되돌리기 모두 `audit_log` 에 남는다. `offboarding_runs` 는 **되돌리기의 입력**을
1급 컬럼으로 갖는 표이고, 감사 로그는 '무슨 일이 있었나'의 기록이다 — 둘은 목적이 다르므로
둘 다 남긴다(models.py docstring).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.authz.permissions import USER_MANAGE
from app.core.deps import get_db, get_principal, require_csrf, require_permission
from app.core.pagination import PageParams
from app.core.scope import Principal
from app.offboarding import service
from app.offboarding.schemas import OffboardingRunRequest

router = APIRouter(
    prefix="/api/admin/offboarding",
    tags=["admin-offboarding"],
    dependencies=[Depends(require_permission(USER_MANAGE)), Depends(require_csrf)],
)


def _repo(request: Request):
    """티켓은 저장소 seam 으로만 읽고 쓴다(app/tickets/repository.py)."""
    return request.app.state.repositories.tickets


@router.get("")
def list_offboarding_runs(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    page: PageParams = Depends(),
):
    items, total = service.list_runs(
        db, principal.management, offset=page.offset, limit=page.page_size
    )
    return {"items": items, "total": total, "page": page.page, "page_size": page.page_size}


@router.get("/preview/{user_id}")
def preview_offboarding(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """실행 전에 보여 줄 전부. 실행 경로는 이 응답 없이는 무엇을 옮길지 알 수 없다."""
    target = service.resolve_target(db, user_id, principal.management)
    return service.preview(
        db, request.app.state.outbound_client, request.app.state.settings,
        target=target, actor=request.state.user, repo=_repo(request),
    )


@router.post("/run/{user_id}")
def run_offboarding(
    request: Request,
    user_id: str,
    payload: OffboardingRunRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    target = service.resolve_target(db, user_id, principal.management)
    successor = (
        service.resolve_target(db, payload.successor_user_id, principal.management)
        if payload.successor_user_id
        else None
    )
    result = service.run_offboarding(
        db,
        request.app.state.outbound_client,
        request.app.state.settings,
        actor=request.state.user,
        target=target,
        successor=successor,
        page_ids=list(payload.ticket_page_ids),
        deactivate=payload.deactivate,
        archive=payload.archive,
        note=payload.note,
        session_service=request.app.state.session_service,
        now=request.app.state.clock.now(),
        repo=_repo(request),
    )
    run = result["run"]
    record_audit_from_request(
        request, db, action="offboarding.run", object_type="offboarding_run",
        object_id=run["id"],
        after={
            "user_id": run["user_id"], "successor_user_id": run["successor_user_id"],
            "status": run["status"], "ticket_total": run["ticket_total"],
            "ticket_moved": run["ticket_moved"], "ticket_failed": run["ticket_failed"],
            "deactivated": run["deactivated"], "archived": run["archived"],
        },
    )
    return result


@router.get("/{run_id}")
def get_offboarding_run(
    run_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    run = service.get_scoped_run_or_404(db, run_id, principal.management)
    return {"run": service.run_detail(db, run)}


@router.post("/{run_id}/undo")
def undo_offboarding_run(
    request: Request,
    run_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """되돌리기 — 계정을 먼저 살리고 그다음 티켓을 원래 담당자 구성으로 되돌린다."""
    run = service.get_scoped_run_or_404(db, run_id, principal.management)
    before = service.run_view(run)
    result = service.undo(
        db,
        request.app.state.outbound_client,
        request.app.state.settings,
        actor=request.state.user,
        run=run,
        session_service=request.app.state.session_service,
        now=request.app.state.clock.now(),
        repo=_repo(request),
    )
    record_audit_from_request(
        request, db, action="offboarding.undo", object_type="offboarding_run",
        object_id=run.id,
        before={"status": before["status"]},
        after={"status": result["run"]["status"], "revert_failed": result["revert_failed"]},
    )
    return result
