"""읽기 전용 임퍼소네이션 API (0033, PLAN Phase 6).

시작·종료는 상태를 바꾸므로 CSRF 를 지난다. **종료(`/stop`)는 임퍼소네이션 중에도 통과해야
하는 유일한 쓰기**이며, 그 예외는 `app/core/deps.py::IMPERSONATION_ALLOWED_WRITES` 한 곳에만
적혀 있다(로그아웃과 함께). 여기서 다시 정의하지 않는다.

역할은 `CONSOLE_WRITE_ROLES`(admin·system_admin). 운영자는 남의 화면을 볼 수 없고,
감사자는 기록만 읽는다 — 기록 조회(`GET /sessions`)만 `SENSITIVE_READ_ROLES` 다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.authz import CONSOLE_WRITE_ROLES, SENSITIVE_READ_ROLES
from app.core.deps import (
    AuthContext,
    get_client_ip,
    get_current_auth,
    get_db,
    require_csrf,
    require_roles,
)
from app.core.errors import NotFoundError
from app.core.pagination import PageParams
from app.core.scope import build_scope
from app.impersonation import service
from app.impersonation.models import END_MANUAL, ImpersonationSession
from app.users.models import User

router = APIRouter(
    prefix="/api/admin/impersonation",
    tags=["admin-impersonation"],
    dependencies=[Depends(require_csrf)],
)


class StartRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=36)
    reason: str | None = Field(default=None, max_length=500)


@router.get("/state")
def current_state(auth: AuthContext = Depends(get_current_auth), db: Session = Depends(get_db)) -> dict:
    """지금 이 세션이 임퍼소네이션 중인가.

    **모든 화면이 이걸 본다** — 사용자 콘솔의 배너도 여기서 나온다. 그래서 역할 게이트를
    걸지 않는다(임퍼소네이션 중에는 요청자의 역할이 '대상'의 역할로 보이기 때문에, 역할
    게이트를 걸면 일반 사용자를 흉내 내는 순간 자기가 임퍼소네이션 중인지 알 수 없게 된다).
    응답에는 요청자 자신에 대한 사실만 들어간다.
    """
    if not auth.impersonating:
        return {"impersonating": False}
    row = (
        db.get(ImpersonationSession, auth.session.impersonation_id)
        if auth.session.impersonation_id
        else None
    )
    # 읽은 횟수는 이 조회에서만 올린다. 요청마다 올리면 폴링이 곧 쓰기가 된다(0026 규칙).
    if row is not None:
        row.read_count = (row.read_count or 0) + 1
        db.flush()
    return {
        "impersonating": True,
        "actor_id": auth.audit_actor.id,
        "actor_name": auth.audit_actor.display_name,
        "target_id": auth.user.id,
        "target_name": auth.user.display_name,
        "target_email": auth.user.email,
        "started_at": row.started_at.isoformat() if row is not None else None,
        "max_duration_seconds": service.MAX_DURATION_SECONDS,
        "blocked_write_count": row.blocked_write_count if row is not None else 0,
    }


@router.post("/start", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def start_impersonation(
    request: Request,
    payload: StartRequest,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    target = db.get(User, payload.user_id)
    if target is None:
        raise NotFoundError("사용자를 찾을 수 없습니다.")
    actor = auth.audit_actor
    now = request.app.state.clock.now()
    row = service.start(
        db,
        actor=actor,
        target=target,
        session=auth.session,
        scope=build_scope(db, actor),
        now=now,
        reason=payload.reason,
        client_ip=get_client_ip(request),
    )
    record_audit_from_request(
        request,
        db,
        action="impersonation.start",
        object_type="user",
        object_id=target.id,
        after={
            "target_email": target.email,
            "target_role": target.role,
            "reason": row.reason,
            "impersonation_id": row.id,
        },
    )
    return {"ok": True, "impersonation": service.view(row, service.resolve_names(db, [actor.id, target.id]))}


@router.post("/stop")
def stop_impersonation(
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    """임퍼소네이션 종료. 멱등이다 — 이미 끝나 있어도 200 이다.

    역할 게이트를 걸지 않는 이유: 임퍼소네이션 중에는 `require_roles` 가 **대상의 역할**을
    본다. 일반 사용자를 흉내 내는 중이면 admin 게이트에 자기 자신이 걸려 빠져나올 수 없다.
    이 라우트는 요청자 자신의 세션 표식만 지우므로 남의 것을 건드릴 방법이 없다.
    """
    now = request.app.state.clock.now()
    row = service.end(db, session=auth.session, now=now, reason=END_MANUAL)
    if row is not None:
        record_audit_from_request(
            request,
            db,
            action="impersonation.stop",
            object_type="user",
            object_id=row.target_user_id,
            after={
                "impersonation_id": row.id,
                "duration_seconds": int((row.ended_at - row.started_at).total_seconds()),
                "blocked_write_count": row.blocked_write_count,
            },
        )
    return {"ok": True, "ended": row is not None}


@router.get("/sessions", dependencies=[Depends(require_roles(*SENSITIVE_READ_ROLES))])
def list_sessions(
    db: Session = Depends(get_db),
    page: PageParams = Depends(),
    actor_user_id: str | None = None,
    target_user_id: str | None = None,
    active: bool | None = None,
) -> dict:
    stmt = select(ImpersonationSession)
    if actor_user_id:
        stmt = stmt.where(ImpersonationSession.actor_user_id == actor_user_id)
    if target_user_id:
        stmt = stmt.where(ImpersonationSession.target_user_id == target_user_id)
    if active is True:
        stmt = stmt.where(ImpersonationSession.ended_at.is_(None))
    elif active is False:
        stmt = stmt.where(ImpersonationSession.ended_at.is_not(None))

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(
                ImpersonationSession.started_at.desc(), ImpersonationSession.id.desc()
            )
            .offset(page.offset)
            .limit(page.page_size)
        )
        .scalars()
        .all()
    )
    names = service.resolve_names(
        db, [r.actor_user_id for r in rows] + [r.target_user_id for r in rows]
    )
    return {
        "items": [service.view(r, names) for r in rows],
        "total": total,
        "page": page.page,
        "page_size": page.page_size,
    }
