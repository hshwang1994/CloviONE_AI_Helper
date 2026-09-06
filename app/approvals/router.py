"""Approval API (spec §20)."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.approvals import delegation as delegation_service
from app.approvals.models import (
    APPROVAL_APPROVED,
    APPROVAL_CANCELLED,
    APPROVAL_EXPIRED,
    APPROVAL_PENDING,
    APPROVAL_REJECTED,
    Approval,
    ApprovalDelegation,
)
from app.approvals import service as approval_service
from app.approvals.service import (
    apply_scope,
    approval_view,
    cancel,
    decide,
    get_scoped_approval_or_404,
    resolve_names,
)
from app.core.sort import SortParams, order_by
from app.core.audit import record_audit_from_request
from app.core.authz import CONSOLE_OPS_ROLES, CONSOLE_READ_ROLES, CONSOLE_WRITE_ROLES
from app.core.scope import Principal, management_scope, visible_user_ids
from app.core.deps import get_current_user, get_db, get_principal, require_csrf, require_roles
from app.core.errors import ValidationAppError

# APPR-03: 화면 필터는 이 5개뿐이라(status=all은 아예 보내지 않는다) 실제로 걸릴 일이
# 없었지만, API를 직접 두드리는 쪽(스크립트·연동)은 알 수 없는 값을 "승인이 하나도
# 없다"(빈 목록)로 오해했다 — 조용히 0건 대신 400으로 원인을 말한다.
_KNOWN_STATUSES = frozenset(
    {APPROVAL_PENDING, APPROVAL_APPROVED, APPROVAL_REJECTED, APPROVAL_EXPIRED, APPROVAL_CANCELLED}
)

# 위임 목록의 `state` 도 같은 이유로 검사한다 — 형제 목록(위 `_KNOWN_STATUSES`)은 이미 알 수
# 없는 값을 422 로 거절하는데, 위임 목록만 조회 뒤 파이썬에서 걸러 「모르는 값 = 0건」이었다.
# 값은 `delegation.state()` 가 돌려주는 네 가지가 전부다.
_KNOWN_DELEGATION_STATES = frozenset({"active", "scheduled", "ended", "revoked"})
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
    can_decide: bool = False,
) -> dict:
    """만료 판정은 approval_view 한 곳에서만 한다 — 모든 화면이 그 결론을 공유한다.

    now를 넘기지 않으면 만료 판정이 조용히 생략되어, 같은 데이터가 목록에서는
    expired인데 상세에서는 pending으로 보인다. 라우터의 모든 응답이 이 헬퍼를
    거치게 해서 한쪽 화면만 판정을 빠뜨리는 일을 막는다.

    요청자/결정자/**위임자** 이름은 여기서 해석해 붙인다(단건은 그 행의 id만, 목록은 호출부가
    한 번에 해석해 names로 넘긴다 — N+1 회피).

    `decided_on_behalf_of` 를 빠뜨리면 그 줄이 「174b73d4-…님의 위임으로 결재」가 된다 —
    「운영자가 왜 승인할 수 있었지?」에 답하려고 만든 줄인데 정작 그 답이 UUID 였다.
    """
    if names is None:
        names = resolve_names(
            db, {row.requested_by, row.approver_id, row.decided_on_behalf_of}
        )
    return approval_view(row, request.app.state.clock.now(), names=names, can_decide=can_decide)


def _name_ids(rows) -> set[str | None]:
    """목록 한 페이지에서 이름으로 해석해야 할 user id 전부 (요청자·결정자·위임자)."""
    return {
        i
        for r in rows
        for i in (r.requested_by, r.approver_id, r.decided_on_behalf_of)
    }


def decision_visible_user_ids(
    db: Session, *, principal: Principal, on_behalf_of: str | None
) -> frozenset[str] | None:
    """이 결재자가 결재할 수 있는 요청자 집합. 전역이면 ``None``(= 제한 없음).

    **범위를 누구 기준으로 재는가는 위임 여부가 정한다**(D-385): 위임으로 결재하면 빌려준
    사람이 닿던 곳까지가 한계이고, 역할로 결재하면 본인의 관리 범위다.

    이 계산이 `_decide` 안에만 있었을 때 개인 결재함(`my_approvals`)은 아예 범위를 안 걸었다.
    그래서 부서 범위 관리자의 결재함에 다른 부서의 역할 변경 요청이 요청자 이름·조직 경로·
    바뀌는 역할까지 그대로 실려 보였고(관리 큐에서는 가려 둔 인사 정보다), 그 줄의 승인을
    누르면 결재 경로가 같은 범위를 다시 재서 404 였다 — 「목록에 있으면 결재된다」가 깨진다.
    목록 축과 결재 축이 이 함수 하나를 함께 쓴다.
    """
    if on_behalf_of:
        delegator = db.get(User, on_behalf_of)
        return (
            visible_user_ids(db, management_scope(db, delegator, principal.tree))
            if delegator is not None
            else frozenset()
        )
    return visible_user_ids(db, principal.management)


# ── 개인 결재함 (0060) ────────────────────────────────────────────────────────
#
# 승인은 **개인 업무**이면서 **관리 업무**이기도 하다. 예전에는 그 둘을 한 화면
# (`/api/admin/approvals`)에 뭉쳐 두었고, 그래서 다음 상태가 실제로 존재했다:
#
#   * 결재 권한을 위임받은 일반 사용자는 `approve`/`reject` 를 **부를 수는 있는데**
#     (`_decide` 에는 role 게이트가 없다 — 위임을 막지 않으려고 일부러 그렇게 뒀다)
#   * 그 목록을 **볼 수는 없었다**(`GET` 은 CONSOLE_READ_ROLES 필수, 관리자 콘솔 전용).
#
# 즉 "당신이 결재할 차례입니다" 알림은 받는데 결재함에 들어갈 방법이 없었다. 여기서
# 그 사람의 **개인 결재함**을 연다 — 관리 범위가 아니라 "내가 결재할 수 있는 건" 과
# "내가 올린 건" 만 보이고, 관리자 콘솔의 큐(범위 전체 현황)와 목적이 다르다.
personal_router = APIRouter(
    prefix="/api/approvals",
    tags=["approvals"],
    dependencies=[Depends(require_csrf)],
)


@personal_router.get("/mine")
def my_approvals(
    request: Request,
    db: Session = Depends(get_db),
    page: PageParams = Depends(),
    box: str = Query(default="todo", pattern="^(todo|requested|done)$"),
    user: User = Depends(get_current_user),
    principal: Principal = Depends(get_principal),
    sort: SortParams = Depends(),
):
    """내 결재함. 역할 게이트가 없다 — **위임받은 일반 사용자도 여기로 들어온다.**

    세 칸으로 나눈다. 한 목록에 뭉치면 '지금 처리할 것' 이 이력에 묻힌다:

        todo       내가 지금 결재할 수 있는 **대기** 건
        requested  내가 올린 건(상태 무관)
        done       내가 결재한 건

    「내가 올린 것」·「내가 결재한 것」 두 칸은 판정 축이 부서가 아니라 '나' 라 범위를 걸지
    않는다. **할 일 칸은 다르다** — 그 칸의 모든 줄에는 승인 버튼이 붙으므로, 실제로 결재할 수
    있는 것만 담아야 한다. 그래서 결재 경로(`_decide`)와 **같은 두 조건**을 건다:

      * 유효한 대기 건인가 (`service.pending_clause` — 만료 시각이 지난 pending 은 뺀다)
      * 내가 닿을 수 있는 요청자인가 (`decision_visible_user_ids` — 위임이면 위임자의 범위)

    위임받은 사람의 범위를 **위임자 기준**으로 재기 때문에 위임은 그대로 산다(D-385).
    """
    now = request.app.state.clock.now()
    can_decide, on_behalf_of = delegation_service.resolve_authority(db, user, now)

    stmt = select(Approval)
    if box == "requested":
        stmt = stmt.where(Approval.requested_by == user.id)
    elif box == "done":
        stmt = stmt.where(Approval.approver_id == user.id)
    else:
        if not can_decide:
            # 결재 권한이 없으면 '할 일' 은 정의상 없다. 빈 목록을 주되 그 이유를 함께
            # 말한다 — 화면이 "권한이 없다" 와 "지금 처리할 것이 없다" 를 구별해야 한다.
            return {
                "items": [], "total": 0, "page": page.page, "page_size": page.page_size,
                "can_decide": False,
            }
        stmt = apply_scope(
            stmt.where(approval_service.pending_clause(now)),
            decision_visible_user_ids(db, principal=principal, on_behalf_of=on_behalf_of),
        )
        # 자기 요청은 자기가 결재하지 않는다(서버 설정으로만 조정되는 기본값) — 할 일 칸에
        # 띄워 두면 눌러 봐야 거절당하는 줄이 된다.
        if not load_feature_flags(request.app.state.settings.config_dir).get("self_approval_allowed"):
            stmt = stmt.where(Approval.requested_by != user.id)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = list(
        db.execute(
            # 허용 키와 기본값은 서비스가 든다 — 「상태」 축이 저장 상태가 아니라 **유효 상태**
            # 여야 하고(만료 지난 pending), 그 판정이 위 필터 절과 같은 정의를 써야 한다
            # (`service.effective_status_rank`).
            stmt.order_by(*order_by(approval_service.list_sort_spec(now, admin=False), sort))
            .offset(page.offset).limit(page.page_size)
        ).scalars()
    )
    names = resolve_names(db, _name_ids(rows))
    return {
        "items": [_view(request, db, r, names, can_decide=can_decide) for r in rows],
        "total": total,
        "page": page.page,
        "page_size": page.page_size,
        "can_decide": can_decide,
    }


@router.get("", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def list_approvals(
    request: Request,
    db: Session = Depends(get_db),
    page: PageParams = Depends(),
    status: str | None = Query(default=None, max_length=16),
    request_type: str | None = Query(default=None, max_length=48),
    requested_by: str | None = Query(default=None, max_length=36),
    principal: Principal = Depends(get_principal),
    sort: SortParams = Depends(),
):
    # 절 순서가 계약이다: ① 조건 → ② 범위(D-202) → ③ 정렬 → ④ 상한.
    #
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
    stmt = apply_scope(select(Approval), visible_user_ids(db, principal.management))
    # 시계는 필터와 정렬이 **함께** 본다 — 둘 다 「만료 시각이 지난 pending」을 만료로 친다.
    # 한 함수 안에서 두 번 읽으면 그 사이에 경계를 넘는 행이 두 판정에서 다르게 보인다.
    now = request.app.state.clock.now()
    # 승인 큐는 5개 요청 유형이 뒤섞여 쌓인다 — 대량 큐를 유형/요청자로 좁혀 분류할 수
    # 있게 서버측 필터를 둔다(목록이 서버 페이지네이션이라 clientFilter로는 현재 페이지만
    # 걸러져 부정확하다, round30 감사 E).
    if request_type:
        stmt = stmt.where(Approval.request_type == request_type)
    if requested_by:
        stmt = stmt.where(Approval.requested_by == requested_by)
    if status:
        if status not in _KNOWN_STATUSES:
            raise ValidationAppError(
                "status는 " + ", ".join(sorted(_KNOWN_STATUSES)) + " 중 하나여야 합니다."
            )
        # 목록 배지는 '유효 상태'를 보여준다: 만료시각이 지난 pending은 sweep이 반영하기
        # 전에도 expired로 표시된다(approval_view). 필터도 같은 유효 상태로 골라야
        # 라벨과 결과가 어긋나지 않는다 — 저장된 컬럼만 보면 '만료'가 그런 행을 놓치고
        # '대기'가 화면엔 만료로 뜨는 행을 돌려준다.
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
            # 조건은 `service.pending_clause` 한 곳에만 있다 — 개인 결재함의 할 일 칸이 같은
            # 함수를 부른다(두 곳에 적었을 때 두 화면이 다른 답을 냈다).
            stmt = stmt.where(approval_service.pending_clause(now))
        else:
            stmt = stmt.where(Approval.status == status)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = (
        db.execute(
            # 「상태」로 정렬할 때도 위 필터와 **같은 유효 상태 판정**을 쓴다
            # (`service.effective_status_rank`) — 저장 상태로 정렬하면 화면에 「만료」로
            # 뜨는 행이 「대기」 무리 사이에 앉는다.
            stmt.order_by(*order_by(approval_service.list_sort_spec(now, admin=True), sort))
            .offset(page.offset)
            .limit(page.page_size)
        )
        .scalars()
        .all()
    )
    # 페이지의 요청자/결정자/위임자 id를 한 번에 이름으로 해석해 각 행에 나눠준다(N+1 회피).
    names = resolve_names(db, _name_ids(rows))
    # can_decide(FN-11)는 행이 아니라 **보는 사람**에게 달린 값이라(role 또는 활성 위임)
    # 페이지당 한 번만 계산한다 — 행마다 다시 물으면 N+1이고, 어차피 같은 사람이 보는
    # 한 페이지 안에서는 전부 같은 답이다.
    now = request.app.state.clock.now()
    can_decide, _ = delegation_service.resolve_authority(db, request.state.user, now)
    return {
        "items": [_view(request, db, r, names, can_decide=can_decide) for r in rows],
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
    row = get_scoped_approval_or_404(db, approval_id, visible_user_ids(db, principal.management))
    now = request.app.state.clock.now()
    can_decide, _ = delegation_service.resolve_authority(db, request.state.user, now)
    return {"approval": _view(request, db, row, can_decide=can_decide)}


@contextmanager
def _audit_refused_write(request: Request, db: Session, *, action: str, approval_id: str):
    """거부된 **결재 시도**를 감사에 남긴다 — 응답 코드도 문구도 바꾸지 않는다.

    승인은 권한 부여 실행이라 「누가 결재하려다 막혔는가」는 남아야 하는 사실이다. 그런데
    감사 기록이 `decide()`/`cancel()` **뒤**에만 있어서, 자기 승인(403)·권한 없음(403)·범위 밖
    (404)·만료(409)가 전부 흔적 없이 사라졌다. 부서 범위 관리자가 남의 큐를 id 로 눌러 봐도
    로그가 한 줄도 안 남는다. 읽기 거부는 남기지 않는다 — 남길 것은 쓰기 시도다.

    `app/core/audit.py::audit_failure_on_exception` 과 같은 모양이되 **먼저 롤백한다**: 결재는
    실패해도 그 전에 세션에 대입이 남는다(`approver_id`·`decided_at`, 실행기가 중간에 바꾼 값).
    그대로 커밋하면 감사 행이 반쯤 적용된 결정을 함께 저장해 원장이 「거절인데 승격됨」이 된다.
    롤백 뒤 실패 행만 쓰고 명시적으로 커밋한다 — `get_db` 의 자동 커밋은 예외 경로에서 안 돈다.
    """
    try:
        yield
    except Exception:
        db.rollback()
        record_audit_from_request(
            request, db, action=action, object_type="approval",
            object_id=approval_id, result="failure",
        )
        db.commit()
        raise


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
    # 범위를 **누구 기준으로 재는가**는 위임 여부가 정한다. 위임은 '결재할 수 있는가'를
    # 바꾸고 범위는 '어느 요청이 보이는가'를 바꾸지만, 대리 결재자가 자기 이름으로 재면
    # 두 축이 어긋난다 — 한때 여기가 언제나 결재자 본인의 관리 범위로 쟀고, 그래서
    # **위임받은 일반 사용자는 결재할 수 있는 건이 하나도 없었다**: 일반 사용자의 관리
    # 범위는 `SCOPE_NONE`(= 빈 집합)이라 무엇을 눌러도 404 였다. 내 결재함
    # (`GET /api/approvals/mine`)은 범위를 안 걸어 줄과 승인 버튼을 그대로 보여 주므로,
    # 화면은 「결재하세요」라고 하고 서버는 「그런 요청은 없습니다」라고 답했다.
    # 위임을 받은 일반 사용자에게 자리를 만들어 준 `/my-approvals` 가 정확히 그 사람을
    # 위한 화면이라, 그 화면의 버튼 전부가 죽어 있었던 셈이다.
    #
    # 빌려온 것은 권한이므로 **빌려준 사람이 닿던 곳까지**가 정확한 한계다. 대리인은
    # 위임자를 절대 넘지 못하고(부서 범위 관리자의 위임은 그 부서까지만), 위쪽 IDOR
    # 방어도 그대로다 — 좁히는 축이 '누구의 범위인가' 로 바뀔 뿐이다.
    # (tests/security/test_approval_scope.py 가 양쪽을 다 못 박아 둔다.)
    action = "approval.approve" if approve else "approval.reject"
    with _audit_refused_write(request, db, action=action, approval_id=approval_id):
        on_behalf_of = delegation_service.require_decider(db, actor, now)
        visible = decision_visible_user_ids(
            db, principal=principal, on_behalf_of=on_behalf_of
        )
        row = get_scoped_approval_or_404(db, approval_id, visible)
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
        action=action,
        object_type="approval", object_id=row.id,
        after={"request_type": row.request_type, "status": row.status},
    )
    return {"approval": _view(request, db, row)}


# 결재 경로의 승인 id 는 실패해도 감사 행의 `object_id`(String(64))에 그대로 실린다 —
# 그 계약보다 긴 값은 라우터에서 422 로 끊는다. 끊지 않으면 거부를 기록하려다 컬럼 길이로
# 실패해, 깨끗한 404 여야 할 응답이 500 이 된다.
APPROVAL_ID_PATH = Path(min_length=1, max_length=64)


@router.post("/{approval_id}/approve")
def approve(
    request: Request,
    approval_id: str = APPROVAL_ID_PATH,
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
    approval_id: str = APPROVAL_ID_PATH,
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
    approval_id: str = APPROVAL_ID_PATH,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    # 취소도 결재다 — 남의 팀 인사 결정을 대신 죽일 수 있으면 안 된다. 네 경로(GET·approve·
    # reject·cancel) 중 하나라도 빠지면 그 경로로 그대로 새 나간다.
    with _audit_refused_write(request, db, action="approval.cancel", approval_id=approval_id):
        row = get_scoped_approval_or_404(
            db, approval_id, visible_user_ids(db, principal.management)
        )
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
    principal: Principal = Depends(get_principal),
):
    # 범위 밖 위임은 보이지 않는다 (P-12a). 이 표면 셋(`list`·`create`·`revoke`)이 통째로
    # `principal` 을 안 받고 있었고, 같은 파일의 승인 큐는 이미 관리 범위로 좁히고 있었다.
    # `CONSOLE_WRITE_ROLES` 에는 **부서 범위 admin 이 들어올 수 있으므로**
    # (`users.admin_scope`) 그 상태로는 남의 부서 결재 대리를 만들고 취소할 수 있었다.
    #
    # 조건은 `delegation.apply_scope` 한 곳에만 있다 — 단건 회수가 같은 함수를 지난다.
    #
    # 알 수 없는 `state` 는 **조회 전에** 거절한다. 조용히 0건을 돌려주면 스크립트·저장된 뷰가
    # 「위임이 하나도 없다」로 오해한다 — 형제 목록(`list_approvals`)이 APPR-03 에서 같은 이유로
    # 이미 422 를 낸다.
    if state and state not in _KNOWN_DELEGATION_STATES:
        raise ValidationAppError(
            "state는 " + ", ".join(sorted(_KNOWN_DELEGATION_STATES)) + " 중 하나여야 합니다."
        )
    now = request.app.state.clock.now()
    visible = visible_user_ids(db, principal.management)
    rows = (
        db.execute(
            delegation_service.apply_scope(select(ApprovalDelegation), visible).order_by(
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
    principal: Principal = Depends(get_principal),
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
        visible=visible_user_ids(db, principal.management),
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
def revoke_delegation(
    request: Request,
    delegation_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    now = request.app.state.clock.now()
    row = delegation_service.get_scoped_or_404(
        db, delegation_id, visible_user_ids(db, principal.management)
    )
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
