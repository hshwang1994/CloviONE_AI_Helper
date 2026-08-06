"""Approval API (spec §20)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.approvals import delegation as delegation_service
from app.approvals.models import (
    APPROVAL_EXPIRED,
    APPROVAL_PENDING,
    Approval,
    ApprovalDelegation,
)
from app.approvals.service import (
    apply_scope,
    approval_view,
    cancel,
    decide,
    get_scoped_approval_or_404,
    resolve_names,
)
from app.core.audit import record_audit_from_request
from app.core.authz import CONSOLE_OPS_ROLES, CONSOLE_READ_ROLES, CONSOLE_WRITE_ROLES
from app.core.scope import Principal, visible_user_ids
from app.core.deps import get_current_user, get_db, get_principal, require_csrf, require_roles
from app.core.errors import NotFoundError
from app.core.feature_flags import load_feature_flags
from app.core.pagination import PageParams
from app.users.models import User

router = APIRouter(
    prefix="/api/admin/approvals",
    tags=["admin-approvals"],
    dependencies=[Depends(require_csrf)],
)



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


@router.get("", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def list_approvals(
    request: Request,
    db: Session = Depends(get_db),
    page: PageParams = Depends(),
    status: str | None = Query(default=None, max_length=16),
    request_type: str | None = Query(default=None, max_length=48),
    requested_by: str | None = Query(default=None, max_length=36),
    principal: Principal = Depends(get_principal),
):
    # 범위 밖 사람이 올린 승인 요청은 보이지 않는다 (2순위 #4).
    #
    # 승인 큐에는 **역할 변경·설정 변경 같은 것이 그대로 적혀 있다** — 요청자·대상·바뀌는
    # 값이 다 들어 있어서, 다른 부서의 큐를 훑을 수 있으면 그 부서의 인사·설정 변경을
    # 실시간으로 들여다보는 셈이다.
    #
    # (감사 로그와 달리 `requested_by` 는 **NOT NULL** 이라 '시스템 요청' 예외가 없다 —
    #  넣어 뒀다가 모델을 확인하고 지웠다. 죽은 분기는 다음 사람에게 거짓 정보다.)
    #
    # 조건은 `service.apply_scope` 한 곳에만 있다 — 단건 GET·approve·reject·cancel 이 같은
    # 함수를 지난다. 여기에 손으로 다시 적으면 두 판정이 갈라진다 (§0-A 1순위).
    stmt = apply_scope(select(Approval), visible_user_ids(db, principal.scope))
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


@router.get("/{approval_id}", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def get_approval(
    request: Request,
    approval_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    # 목록에서 가린 것이 상세에서 새면 가린 의미가 없다 — payload 에 '누구를 무슨 역할로'
    # 가 그대로 적혀 있다. 목록과 **같은** 함수로 판정한다.
    row = get_scoped_approval_or_404(db, approval_id, visible_user_ids(db, principal.scope))
    return {"approval": _view(request, db, row)}


def _decide(
    request: Request,
    approval_id: str,
    db: Session,
    approve: bool,
    comment,
    actor: User,
    principal: Principal,
):
    now = request.app.state.clock.now()
    # 권한 판정을 라우트 데코레이터가 아니라 여기서 하는 이유(0033): 위임을 받은 사람은
    # CONSOLE_WRITE_ROLES 가 아닐 수 있다. `require_roles` 로 잠그면 대리 승인자가 결재하는
    # 순간 403 이 되어 위임이라는 기능 자체가 성립하지 않는다. 대신 위임까지 아는 단일
    # 판정 함수를 쓰고, 그 결과(누구를 대신했는가)를 결재 기록에 남긴다.
    #
    # **권한 확인이 조회보다 먼저다.** 순서가 바뀌면 권한 없는 사람이 승인 id 를 찍어 보며
    # 404/409 를 세어 큐의 존재를 열거할 수 있다.
    #
    # **범위 판정은 조회와 한 몸이라 그 다음이다** — 그리고 그래야 옳다. 범위는 '이 행이
    # 누구 것인가' 를 묻는 질문이라 행 없이는 답할 수 없고, 답이 404(없는 것과 동일)라서
    # 순서를 뒤로 미뤄도 새로 새는 정보가 없다. 반대로 범위를 권한보다 앞에 두려고 조회를
    # 먼저 하면 위의 열거 구멍이 그대로 돌아온다.
    #
    # 범위는 **결재자(위임 여부)와 무관하다**: 위임은 '결재할 수 있는가'를 바꾸고, 범위는
    # '어느 요청이 보이는가'를 바꾼다. 위임받은 운영자는 build_scope 상 대개 전역이므로
    # 좁혀지지 않는다(tests/security/test_approval_scope.py 가 이걸 못 박아 둔다).
    on_behalf_of = delegation_service.require_decider(db, actor, now)
    row = get_scoped_approval_or_404(db, approval_id, visible_user_ids(db, principal.scope))
    flags = load_feature_flags(request.app.state.settings.config_dir)
    decide(
        db,
        row,
        actor,
        approve=approve,
        comment=comment,
        now=now,
        self_approval_allowed=bool(flags.get("self_approval_allowed", False)),
        app_state=request.app.state,
        on_behalf_of=on_behalf_of,
    )
    record_audit_from_request(
        request, db,
        action="approval.approve" if approve else "approval.reject",
        object_type="approval", object_id=row.id,
        after={"request_type": row.request_type, "status": row.status},
    )
    return {"approval": _view(request, db, row)}


@router.post("/{approval_id}/approve")
def approve(
    request: Request,
    approval_id: str,
    payload: DecisionRequest | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
    principal: Principal = Depends(get_principal),
):
    comment = payload.comment if payload else None
    return _decide(request, approval_id, db, True, comment, actor, principal)


@router.post("/{approval_id}/reject")
def reject(
    request: Request,
    approval_id: str,
    payload: DecisionRequest | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
    principal: Principal = Depends(get_principal),
):
    comment = payload.comment if payload else None
    return _decide(request, approval_id, db, False, comment, actor, principal)


@router.post(
    "/{approval_id}/cancel",
    dependencies=[Depends(require_roles(*CONSOLE_OPS_ROLES))],
)
def cancel_approval(
    request: Request,
    approval_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    # 취소도 결재다 — 남의 팀 인사 결정을 대신 죽일 수 있으면 안 된다. 네 경로(GET·approve·
    # reject·cancel) 중 하나라도 빠지면 그 경로로 그대로 새 나간다.
    row = get_scoped_approval_or_404(db, approval_id, visible_user_ids(db, principal.scope))
    cancel(db, row, request.state.user, now=request.app.state.clock.now())
    record_audit_from_request(
        request, db, action="approval.cancel", object_type="approval", object_id=row.id,
    )
    return {"approval": _view(request, db, row)}


# ── 승인 위임 (0033, PLAN Phase 6) ────────────────────────────────────────────
#
# **왜 `/api/admin/approvals/delegations` 가 아닌가.** 위 라우터에는 이미 `/{approval_id}` 가
# 있다. 같은 prefix 아래에 `/delegations` 를 더하면 FastAPI 는 등록 순서대로 매칭하므로
# `GET /api/admin/approvals/delegations` 가 `/{approval_id}` 에 먼저 잡혀 "delegations 라는
# 승인을 찾을 수 없습니다"(404)가 된다. 순서에 의존해 푸는 것도 가능하지만, 그 규칙은
# 파일을 편집하는 사람 눈에 안 보인다 — 형제 prefix 로 나누면 순서와 무관하게 옳다.
#
# 같은 파일에 두는 이유는 그대로다: 위임은 승인 큐의 운영 규칙이라 같이 읽혀야 하고,
# `require_csrf` 를 여기서 한 번 더 명시적으로 걸어 새 라우터에서 빠뜨리는 일을 막는다
# (tests/security/test_csrf_coverage.py 의 교훈).

delegations_router = APIRouter(
    prefix="/api/admin/approval-delegations",
    tags=["admin-approvals"],
    dependencies=[Depends(require_csrf)],
)


class DelegationRequest(BaseModel):
    delegator_user_id: str = Field(min_length=1, max_length=36)
    delegate_user_id: str = Field(min_length=1, max_length=36)
    starts_at: datetime
    ends_at: datetime
    reason: str | None = Field(default=None, max_length=500)


def _delegation_user_or_404(db: Session, user_id: str) -> User:
    row = db.get(User, user_id)
    if row is None:
        raise NotFoundError("사용자를 찾을 수 없습니다.")
    return row


@delegations_router.get("", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def list_delegations(
    request: Request,
    db: Session = Depends(get_db),
    state: str | None = Query(default=None, max_length=16),
):
    now = request.app.state.clock.now()
    rows = (
        db.execute(
            select(ApprovalDelegation).order_by(
                ApprovalDelegation.starts_at.desc(), ApprovalDelegation.id.desc()
            )
        )
        .scalars()
        .all()
    )
    names = resolve_names(
        db, {i for r in rows for i in (r.delegator_user_id, r.delegate_user_id)}
    )
    items = [delegation_service.view(r, now, names) for r in rows]
    if state:
        items = [i for i in items if i["state"] == state]
    return {"items": items}


@delegations_router.post(
    "", status_code=201, dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))]
)
def create_delegation(
    request: Request,
    payload: DelegationRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    now = request.app.state.clock.now()
    row = delegation_service.create(
        db,
        delegator=_delegation_user_or_404(db, payload.delegator_user_id),
        delegate=_delegation_user_or_404(db, payload.delegate_user_id),
        starts_at=_naive_utc(payload.starts_at),
        ends_at=_naive_utc(payload.ends_at),
        reason=payload.reason,
        created_by=actor.id,
        now=now,
    )
    record_audit_from_request(
        request, db, action="approval_delegation.create",
        object_type="approval_delegation", object_id=row.id,
        after=delegation_service.view(row, now),
    )
    names = resolve_names(db, {row.delegator_user_id, row.delegate_user_id})
    return delegation_service.view(row, now, names)


@delegations_router.post(
    "/{delegation_id}/revoke", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))]
)
def revoke_delegation(request: Request, delegation_id: str, db: Session = Depends(get_db)):
    now = request.app.state.clock.now()
    row = delegation_service.get_or_404(db, delegation_id)
    before = delegation_service.view(row, now)
    delegation_service.revoke(db, row, now=now)
    record_audit_from_request(
        request, db, action="approval_delegation.revoke",
        object_type="approval_delegation", object_id=row.id,
        before=before, after=delegation_service.view(row, now),
    )
    names = resolve_names(db, {row.delegator_user_id, row.delegate_user_id})
    return delegation_service.view(row, now, names)


def _naive_utc(value: datetime) -> datetime:
    """타임존이 붙어 오면 UTC 로 바꿔 naive 로 만든다(저장소 전역 규약)."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
