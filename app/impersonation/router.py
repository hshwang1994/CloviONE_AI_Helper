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
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.db import batched
from app.authz.permissions import AUDIT_READ, IMPERSONATE
from app.core.deps import (
    AuthContext,
    get_client_ip,
    get_current_auth,
    get_db,
    get_principal,
    require_csrf,
    require_permission,
)
from app.core.errors import NotFoundError
from app.core.pagination import PageParams
from app.core.scope import Principal, management_scope, visible_user_ids
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
    # SEC-03: 예전에는 폴링(모든 화면이 이 GET을 부른다)마다 write 가 나갔다 — require_csrf
    # 는 안전 메서드(GET)를 통과시키므로 이 write 는 CSRF 로부터 완전히 무방비였다. 최초
    # 1회만 올려 그 뒤로는 이 GET 이 진짜로 읽기 전용이 되게 한다("관찰됐는가"는 여전히
    # 감사 화면에 남지만, 반복 요청이 더는 상태를 바꾸지 않는다).
    if row is not None and row.read_count == 0:
        row.read_count = 1
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


@router.post("/start", dependencies=[Depends(require_permission(IMPERSONATE))])
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
        scope=management_scope(db, actor),
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


@router.get("/sessions", dependencies=[Depends(require_permission(AUDIT_READ))])
def list_sessions(
    db: Session = Depends(get_db),
    page: PageParams = Depends(),
    actor_user_id: str | None = None,
    target_user_id: str | None = None,
    active: bool | None = None,
    principal: Principal = Depends(get_principal),
) -> dict:
    stmt = select(ImpersonationSession)
    # 범위 밖 대리 보기 이력은 안 보인다 (2순위 #5).
    #
    # 이 표는 "**누가 누구의 계정으로 들어갔나**" 다 — 다른 조직의 이력을 볼 수 있으면
    # 그 조직에 누가 있고 누가 관리자인지, 어떤 계정이 문제를 겪었는지가 드러난다.
    # **대상 기준**으로 좁힌다: 보호받아야 하는 쪽은 대리 보기를 당한 사람이다.
    visible = visible_user_ids(db, principal.management)
    if visible is not None:
        # UB-28: 이 표의 문서화된 목표 규모(scope.py::visible_user_ids 참고, ~1000명)에서도
        # 부서/조직 범위 관리자의 visible 집합이 SQLite 호스트 변수 상한(빌드에 따라
        # 999~32766)에 가까워질 수 있다 — 그 순간 이 조회가 처리 안 된 500이 된다. IN은
        # NOT IN과 달리 청크를 AND로 못 잇는다(그러면 교집합이 비어 아무 것도 안 남는다) —
        # OR로 이어 붙여야 원래의 "합집합 중 하나에 있으면" 의미가 보존된다.
        # visible이 빈 집합이면(범위 안에 아무도 없음) `.in_([])`는 늘 거짓이라 원래 아무 행도
        # 안 돌려줬다 — `or_()`를 인자 없이 부르면 WHERE 절 자체가 빠져 정반대(전체 노출)가
        # 되므로 그 경우를 먼저 걸러 명시적으로 "아무 것도 없음"을 판정한다.
        ids = list(visible)
        if not ids:
            stmt = stmt.where(False)
        else:
            stmt = stmt.where(
                or_(*(ImpersonationSession.target_user_id.in_(batch) for batch in batched(ids)))
            )
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
