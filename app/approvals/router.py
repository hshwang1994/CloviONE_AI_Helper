"""Approval API (spec §20)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.approvals.models import APPROVAL_EXPIRED, APPROVAL_PENDING, Approval
from app.approvals.service import (
    approval_view,
    cancel,
    decide,
    get_approval_or_404,
    resolve_names,
)
from app.core.audit import record_audit_from_request
from app.core.deps import get_db, require_csrf, require_roles
from app.core.feature_flags import load_feature_flags
from app.core.pagination import PageParams

router = APIRouter(
    prefix="/api/admin/approvals",
    tags=["admin-approvals"],
    dependencies=[Depends(require_csrf)],
)

READ_ROLES = ("operator", "admin", "system_admin", "auditor")
DECIDE_ROLES = ("admin", "system_admin")


class DecisionRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)


def _view(
    request: Request,
    db: Session,
    row: Approval,
    names: dict | None = None,
) -> dict:
    """만료 판정은 approval_view 한 곳에서만 한다 — 모든 화면이 그 결론을 공유한다.

    now를 넘기지 않으면 만료 판정이 조용히 생략되어, 같은 데이터가 목록에서는
    expired인데 상세에서는 pending으로 보인다. 라우터의 모든 응답이 이 헬퍼를
    거치게 해서 한쪽 화면만 판정을 빠뜨리는 일을 막는다.

    요청자/결정자 이름은 여기서 해석해 붙인다(단건은 그 행의 id만, 목록은 호출부가
    한 번에 해석해 names로 넘긴다 — N+1 회피).
    """
    if names is None:
        names = resolve_names(db, {row.requested_by, row.approver_id})
    return approval_view(row, request.app.state.clock.now(), names=names)


@router.get("", dependencies=[Depends(require_roles(*READ_ROLES))])
def list_approvals(
    request: Request,
    db: Session = Depends(get_db),
    page: PageParams = Depends(),
    status: str | None = Query(default=None, max_length=16),
    request_type: str | None = Query(default=None, max_length=48),
    requested_by: str | None = Query(default=None, max_length=36),
):
    stmt = select(Approval)
    # 승인 큐는 5개 요청 유형이 뒤섞여 쌓인다 — 대량 큐를 유형/요청자로 좁혀 분류할 수
    # 있게 서버측 필터를 둔다(목록이 서버 페이지네이션이라 clientFilter로는 현재 페이지만
    # 걸러져 부정확하다, round30 감사 E).
    if request_type:
        stmt = stmt.where(Approval.request_type == request_type)
    if requested_by:
        stmt = stmt.where(Approval.requested_by == requested_by)
    if status:
        # 목록 배지는 '유효 상태'를 보여준다: 만료시각이 지난 pending은 sweep이 반영하기
        # 전에도 expired로 표시된다(approval_view). 필터도 같은 유효 상태로 골라야
        # 라벨과 결과가 어긋나지 않는다 — 저장된 컬럼만 보면 '만료'가 그런 행을 놓치고
        # '대기'가 화면엔 만료로 뜨는 행을 돌려준다.
        now = request.app.state.clock.now()
        if status == APPROVAL_EXPIRED:
            stmt = stmt.where(
                or_(
                    Approval.status == APPROVAL_EXPIRED,
                    and_(
                        Approval.status == APPROVAL_PENDING,
                        Approval.expires_at.is_not(None),
                        Approval.expires_at <= now,
                    ),
                )
            )
        elif status == APPROVAL_PENDING:
            stmt = stmt.where(
                and_(
                    Approval.status == APPROVAL_PENDING,
                    or_(Approval.expires_at.is_(None), Approval.expires_at > now),
                )
            )
        else:
            stmt = stmt.where(Approval.status == status)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(Approval.requested_at.desc(), Approval.id.desc())
            .offset(page.offset)
            .limit(page.page_size)
        )
        .scalars()
        .all()
    )
    # 페이지의 요청자/결정자 id를 한 번에 이름으로 해석해 각 행에 나눠준다(N+1 회피).
    names = resolve_names(
        db, {i for r in rows for i in (r.requested_by, r.approver_id)}
    )
    return {
        "items": [_view(request, db, r, names) for r in rows],
        "total": total,
        "page": page.page,
        "page_size": page.page_size,
    }


@router.get("/{approval_id}", dependencies=[Depends(require_roles(*READ_ROLES))])
def get_approval(request: Request, approval_id: str, db: Session = Depends(get_db)):
    return {"approval": _view(request, db, get_approval_or_404(db, approval_id))}


def _decide(request: Request, approval_id: str, db: Session, approve: bool, comment):
    row = get_approval_or_404(db, approval_id)
    flags = load_feature_flags(request.app.state.settings.config_dir)
    decide(
        db,
        row,
        request.state.user,
        approve=approve,
        comment=comment,
        now=request.app.state.clock.now(),
        self_approval_allowed=bool(flags.get("self_approval_allowed", False)),
        app_state=request.app.state,
    )
    record_audit_from_request(
        request, db,
        action="approval.approve" if approve else "approval.reject",
        object_type="approval", object_id=row.id,
        after={"request_type": row.request_type, "status": row.status},
    )
    return {"approval": _view(request, db, row)}


@router.post("/{approval_id}/approve", dependencies=[Depends(require_roles(*DECIDE_ROLES))])
def approve(
    request: Request,
    approval_id: str,
    payload: DecisionRequest | None = None,
    db: Session = Depends(get_db),
):
    comment = payload.comment if payload else None
    return _decide(request, approval_id, db, True, comment)


@router.post("/{approval_id}/reject", dependencies=[Depends(require_roles(*DECIDE_ROLES))])
def reject(
    request: Request,
    approval_id: str,
    payload: DecisionRequest | None = None,
    db: Session = Depends(get_db),
):
    comment = payload.comment if payload else None
    return _decide(request, approval_id, db, False, comment)


@router.post(
    "/{approval_id}/cancel",
    dependencies=[Depends(require_roles("operator", "admin", "system_admin"))],
)
def cancel_approval(request: Request, approval_id: str, db: Session = Depends(get_db)):
    row = get_approval_or_404(db, approval_id)
    cancel(db, row, request.state.user, now=request.app.state.clock.now())
    record_audit_from_request(
        request, db, action="approval.cancel", object_type="approval", object_id=row.id,
    )
    return {"approval": _view(request, db, row)}
