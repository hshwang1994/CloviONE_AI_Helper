"""AI 쿼터 관리 API (0033, PLAN Phase 6).

목록에는 **상한과 함께 현재 소비량**이 실린다. 상한만 보여 주는 화면은 "지금 위험한가"를
답하지 못해서, 결국 관리자가 감사 로그를 뒤지게 만든다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.authz import CONSOLE_READ_ROLES, CONSOLE_WRITE_ROLES
from app.core.scope import Principal
from app.core.db import is_write_conflict
from app.core.deps import get_current_user, get_db, get_principal, require_csrf, require_roles
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.quotas import service
from app.quotas.models import (
    ALL_PERIODS,
    GLOBAL_USER_ID,
    SCOPE_GLOBAL,
    SCOPE_USER,
    AiQuota,
)
from app.users.models import User

router = APIRouter(
    prefix="/api/admin/ai-quotas",
    tags=["admin-ai-quotas"],
    dependencies=[Depends(require_csrf)],
)


class QuotaRequest(BaseModel):
    scope_type: str = Field(default=SCOPE_GLOBAL, max_length=16)
    user_id: str | None = Field(default=None, max_length=36)
    period: str = Field(default="day", max_length=16)
    max_calls: int = Field(ge=0, le=1_000_000)
    note: str | None = Field(default=None, max_length=200)


class QuotaPatch(BaseModel):
    max_calls: int | None = Field(default=None, ge=0, le=1_000_000)
    note: str | None = Field(default=None, max_length=200)


def _ensure_target_in_scope(db: Session, user_id: str, principal: Principal) -> None:
    """이 사람에게 쿼터를 걸 수 있는가 (3순위 IDOR).

    읽기(`/usage`)는 이미 `get_scoped_user_or_404` 를 지나는데 **쓰기는 `user_id` 를 그대로
    받았다.** 그래서 부서 범위 관리자가 남의 팀 사람의 AI 상한을 **0 으로 만들어 업무를 막거나**
    크게 올려 비용을 태울 수 있었다. 목록에서 가린 사람을 id 로 뚫는 전형적인 IDOR 이다.
    범위 밖은 **404** — 403 은 그 계정이 존재한다는 사실을 알려 준다.
    """
    from app.users.service import get_scoped_user_or_404

    get_scoped_user_or_404(db, user_id, principal.scope)


def _ensure_may_touch_global(principal: Principal) -> None:
    """전역 쿼터는 **포탈 전체**에 걸린다 — 자기 범위를 넘는 일이다.

    부서 관리자가 전역 상한을 0 으로 만들면 **전 사용자의 AI 가 멈춘다.** 범위를 좁혀 놓고
    이 문을 열어 두면 좁힌 의미가 없다. 여기서는 **404 가 아니라 403** 이다 — 그 행의 존재는
    이미 목록에서 보이고(자기 사람들에게도 걸리는 상한이므로 보여야 한다), 문제는 존재가
    아니라 권한이다.
    """
    if not principal.scope.is_global:
        raise ForbiddenError("전역 쿼터는 전체 범위 관리자만 바꿀 수 있습니다.")


def _get_or_404(db: Session, row_id: str, principal: Principal) -> AiQuota:
    row = db.get(AiQuota, row_id)
    if row is None:
        raise NotFoundError("쿼터를 찾을 수 없습니다.")
    if row.scope_type == SCOPE_USER and row.user_id:
        _ensure_target_in_scope(db, row.user_id, principal)
    else:
        _ensure_may_touch_global(principal)
    return row


@router.get("", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def list_quotas(
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> dict:
    now = request.app.state.clock.now()
    rows = (
        db.execute(select(AiQuota).order_by(AiQuota.scope_type, AiQuota.period, AiQuota.user_id))
        .scalars()
        .all()
    )
    # 사용자 쿼터에는 **누가 얼마나 쓰는지**가 이름과 함께 실린다(그 사람의 업무 강도에 가깝다).
    # 전역 행은 남긴다 — 그 상한은 이 관리자의 사람들에게도 걸리므로 가리면 화면이 거짓말한다.
    if not principal.scope.is_global:
        from app.core.scope import visible_user_ids

        visible = set(visible_user_ids(db, principal.scope) or set())
        rows = [r for r in rows if r.scope_type != SCOPE_USER or r.user_id in visible]
    from app.impersonation.service import resolve_names

    names = resolve_names(db, [r.user_id for r in rows if r.user_id])
    # UB-10: 행마다 used()를 따로 부르면 N+1이다 — 사용자 전용 행의 (user_id, period)
    # 쌍을 모아 한 번에 묻는다(전역 행은 max_user_used가 이미 기간별로만 도니 그대로 둠).
    used_pairs = {
        (row.user_id, row.period) for row in rows if row.scope_type != SCOPE_GLOBAL and row.user_id
    }
    used_by_pair = service.used_batch(db, pairs=used_pairs, now=now)
    max_user_used_by_period: dict[str, int] = {}
    items = []
    for row in rows:
        item = service.view(row, names)
        # UB-02: `enforce()`는 전역 상한도 사용자별로 판정한다 — 화면은 그 판정과 같은
        # 축(개인별 최댓값)을 보여줘야 "X / 상한"이 실제로 누군가를 막는 숫자가 된다.
        # 예전의 `used_all`(전 사용자 합계)은 아무도 안 막힌 상황에서도 상한 도달을
        # 알리는 화면을 만들었다.
        if row.scope_type == SCOPE_GLOBAL:
            if row.period not in max_user_used_by_period:
                max_user_used_by_period[row.period] = service.max_user_used(
                    db, period=row.period, now=now
                )
            item["used"] = max_user_used_by_period[row.period]
        else:
            item["used"] = used_by_pair.get((row.user_id, row.period), 0)
        item["resets_at"] = service.period_end(row.period, now).isoformat()
        items.append(item)
    return {
        "items": items,
        # 화면이 "쿼터를 어디에 거는가"를 스스로 지어내지 않게 서버가 말해 준다.
        "enforced_on": [
            {"kind": service.KIND_ASSISTANT_NARRATIVE, "label": "AI 도우미 문장 생성"},
            {"kind": service.KIND_DOCUMENT_GENERATE, "label": "문서 자동 생성 요청"},
            {"kind": service.KIND_CHAT_MESSAGE, "label": "AI 도우미 채팅"},
        ],
        "periods": list(ALL_PERIODS),
    }


@router.get("/usage", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def usage_summary(
    request: Request,
    db: Session = Depends(get_db),
    user_id: str | None = None,
    principal: Principal = Depends(get_principal),
) -> dict:
    """전체(또는 한 사용자)의 현재 기간 소비량.

    `user_id` 를 **그대로 받으면 안 된다** (2순위 #5 / IDOR). 범위 밖 사람의 AI 사용량을
    id 하나로 조회할 수 있었다 — 누가 얼마나 쓰는지는 그 사람의 업무 강도이자 근태에 가깝다.
    `get_scoped_user_or_404` 를 지나 **범위 밖은 404** 로 답한다(저장소 규칙).
    """
    now = request.app.state.clock.now()
    if user_id:
        from app.users.service import get_scoped_user_or_404

        get_scoped_user_or_404(db, user_id, principal.scope)
        return service.status(db, user_id=user_id, now=now)
    return {
        "user_id": None,
        "periods": [
            {
                "period": period,
                "limit": None,
                "source": None,
                "used": service.used_all(db, period=period, now=now),
                "resets_at": service.period_end(period, now).isoformat(),
            }
            for period in ALL_PERIODS
        ],
    }


@router.post("", status_code=201, dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def create_quota(
    request: Request,
    payload: QuotaRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
    principal: Principal = Depends(get_principal),
) -> dict:
    service.validate(payload.scope_type, payload.period, payload.max_calls)
    user_id = (payload.user_id or "").strip()
    if payload.scope_type == SCOPE_USER:
        if not user_id:
            raise ValidationAppError("사용자 쿼터에는 user_id 가 필요합니다.")
        _ensure_target_in_scope(db, user_id, principal)
    else:
        _ensure_may_touch_global(principal)
        user_id = GLOBAL_USER_ID
    existing = db.execute(
        select(AiQuota).where(
            AiQuota.scope_type == payload.scope_type,
            AiQuota.user_id == user_id,
            AiQuota.period == payload.period,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("같은 범위, 기간의 쿼터가 이미 있습니다. 기존 항목을 수정하세요.")

    now = request.app.state.clock.now()
    row = AiQuota(
        scope_type=payload.scope_type,
        user_id=user_id,
        period=payload.period,
        max_calls=payload.max_calls,
        note=payload.note,
        created_by=actor.id,
        created_at=now,
        updated_at=now,
    )
    # uq_ai_quota_scope UNIQUE(scope_type, user_id, period) — 이중 클릭이나 두 관리자의
    # 동시 생성이 위 조회 사이를 비집고 들어오면 둘 다 "기존 없음"을 보고 삽입을 시도할
    # 수 있다(app/prompts/service.py::transition과 같은 관용). 이건 get_or_create가
    # 아니라 명시적 "새로 만들기" 요청이라 진 쪽에 남의 값을 조용히 돌려주지 않고, 위와
    # 똑같은 409 문구로 알린다.
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except (IntegrityError, OperationalError) as exc:
        if not is_write_conflict(exc):
            raise
        raise ConflictError("같은 범위, 기간의 쿼터가 이미 있습니다. 기존 항목을 수정하세요.") from None
    record_audit_from_request(
        request, db, action="ai_quota.create", object_type="ai_quota",
        object_id=row.id, after=service.view(row),
    )
    return service.view(row)


@router.patch("/{row_id}", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def update_quota(
    request: Request, row_id: str, payload: QuotaPatch,
    db: Session = Depends(get_db), principal: Principal = Depends(get_principal),
) -> dict:
    row = _get_or_404(db, row_id, principal)
    before = service.view(row)
    data = payload.model_dump(exclude_unset=True)
    # UB-30: max_calls는 DB에서 NOT NULL이고(0="차단", 무제한을 원하면 행을 지운다 — 모델
    # 주석), null로 둘 수 있는 상태 자체가 없다. 예전엔 `data["max_calls"] is not None`만
    # 보고 넘어가 `{"max_calls": null}`이 200 + 변화 없는 감사 행으로 조용히 no-op됐다 —
    # 보낸 사람은 상한이 바뀐 줄 안다. 명시적으로 거부한다(아래 note는 nullable이라 그대로 둠).
    if "max_calls" in data:
        if data["max_calls"] is None:
            raise ValidationAppError("max_calls는 비울 수 없습니다. 쿼터를 없애려면 삭제하세요.")
        service.validate(row.scope_type, row.period, data["max_calls"])
        row.max_calls = data["max_calls"]
    if "note" in data:
        row.note = data["note"]
    row.updated_at = request.app.state.clock.now()
    db.flush()
    record_audit_from_request(
        request, db, action="ai_quota.update", object_type="ai_quota",
        object_id=row.id, before=before, after=service.view(row),
    )
    return service.view(row)


@router.delete("/{row_id}", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def delete_quota(
    request: Request, row_id: str, db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> dict:
    row = _get_or_404(db, row_id, principal)
    before = service.view(row)
    db.delete(row)
    db.flush()
    record_audit_from_request(
        request, db, action="ai_quota.delete", object_type="ai_quota",
        object_id=row_id, before=before,
    )
    return {"ok": True}
