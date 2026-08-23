"""Admin user management API (spec §11.4, §14.2, §23.3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.auth.models import UserSession
from app.core.audit import record_audit_from_request
from app.authz.permissions import USER_MANAGE
from app.core.deps import get_db, get_principal, require_csrf, require_permission
from app.core.errors import ForbiddenError, ValidationAppError
from app.core.pagination import PageParams
from app.core.scope import Principal, apply_user_scope, scope_allows_user
from app.mail.models import MAIL_QUEUED
from app.users import bulk
from app.users.models import ALL_ROLES, User
from app.users.schemas import (
    BulkUserActionRequest,
    ImportUsersRequest,
    ResetPasswordRequest,
    UserCreateRequest,
    UserUpdateRequest,
)
from app.users.service import (
    admin_reset_password,
    archive_user,
    create_user,
    ensure_can_manage_target,
    get_scoped_user_or_404,
    set_user_active,
    unarchive_user,
    unlock_user,
    update_user,
    user_snapshot,
)

router = APIRouter(
    prefix="/api/admin/users",
    tags=["admin-users"],
    dependencies=[Depends(require_permission(USER_MANAGE)), Depends(require_csrf)],
)


def _user_row(user: User, now, *, notion_status: str = "unmapped") -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "active": user.active,
        "must_change_password": user.must_change_password,
        # 이름은 표에 보여 주기 위해, id는 수정 폼이 '지금 값'을 고를 수 있게 하기 위해
        # 함께 내보낸다(둘 중 하나만 있으면 화면 어느 한쪽이 동작하지 않는다).
        "department": user.department,
        "title": user.title,
        "department_id": user.department_id,
        # 소속 종류(0060) — 화면이 "부서 미지정" 과 "조직 직속" 을 구별해 보여야 한다.
        # 둘은 완전히 다른 상태인데 예전에는 둘 다 "부서 없음" 한 칸으로만 보였다.
        "membership_kind": user.membership_kind,
        # 관리 범위 — 화면이 지금 값을 보여 줄 수 있어야 한다. 설정만 되고 안 보이면
        # "이 사람이 지금 어디까지 보나" 를 확인할 방법이 없다(F2).
        "admin_scope": user.admin_scope,
        "scope_org_id": user.scope_org_id,
        "scope_dept_id": user.scope_dept_id,
        "title_id": user.title_id,
        "locked": bool(user.locked_until and user.locked_until > now),
        "archived_at": user.archived_at.isoformat() if user.archived_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "created_at": user.created_at.isoformat(),
        "notion_mapping_status": notion_status,
    }


def _notion_status_map(db: Session, user_ids: list[str]) -> dict[str, str]:
    from app.notion_mapping.models import UserNotionMapping

    if not user_ids:
        return {}
    rows = db.execute(
        select(UserNotionMapping).where(UserNotionMapping.user_id.in_(user_ids))
    ).scalars().all()
    return {r.user_id: r.status for r in rows}


def _filtered_users_stmt(
    scope, *, q, role, active, department_id, title_id, archived, locked=None, now=None,
):
    """목록과 CSV 내보내기가 **같은 문장**을 쓴다.

    두 벌로 적으면 화면에서 필터를 걸고 내보낸 파일에 필터가 안 걸린 전 직원이 담기는 식으로
    갈라진다 — 그리고 그것은 파일을 열어 보기 전까지 아무도 모른다.
    """
    # 보관된 계정은 기본으로 감춘다 — 검색도 목록의 다른 문일 뿐이라 같은 조건을 탄다.
    # archived=true는 '보관함'을 여는 것이다: 복구하려면 볼 수 있어야 하므로 그때만
    # 보관된 계정만 따로 보여 준다.
    stmt = select(User).where(
        User.archived_at.is_not(None) if archived else User.archived_at.is_(None)
    )
    # 관리 범위(0024). 전역 관리자면 apply_user_scope 가 그대로 돌려주므로 기존 동작과
    # 바이트 단위로 같다. 조직/부서 관리자면 여기서 좁혀지고, 같은 규칙을 단건 조회
    # (get_scoped_user_or_404)가 다시 쓴다 — 목록과 단건이 갈라지지 않게.
    stmt = apply_user_scope(stmt, scope)
    if q:
        needle = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(User.email).like(needle),
                func.lower(User.display_name).like(needle),
            )
        )
    if role is not None:
        if role not in ALL_ROLES:
            raise ValidationAppError(f"알 수 없는 역할입니다: {role}")
        stmt = stmt.where(User.role == role)
    if active is not None:
        stmt = stmt.where(User.active.is_(active))
    # 부서/직책 화면의 '소속 인원 N명' 카운트를 실제 사용자 목록으로 드릴다운할 수 있게
    # 서버측 필터를 둔다(#/users?department_id=… / ?title_id=… 딥링크, round30 감사 E).
    if department_id:
        stmt = stmt.where(User.department_id == department_id)
    if title_id:
        stmt = stmt.where(User.title_id == title_id)
    # ADM-06R: 화면·배지·잠금 해제 버튼은 이미 다 있는데 "지금 잠긴 사람만 보기"가 안 됐다
    # — `_user_row`가 이미 같은 식(`locked_until and locked_until > now`)으로 `locked`를
    # 계산해 목록에 싣고 있었으니 필터도 같은 식이어야 한다(두 벌이 되면 화면 배지와
    # 필터 결과가 어긋나는 날이 온다).
    if locked is not None:
        is_locked = and_(User.locked_until.is_not(None), User.locked_until > now)
        stmt = stmt.where(is_locked if locked else ~is_locked)
    return stmt


@router.get("")
def list_users(
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    page: PageParams = Depends(),
    q: str | None = Query(default=None, max_length=255),
    role: str | None = Query(default=None),
    active: bool | None = Query(default=None),
    department_id: str | None = Query(default=None, max_length=36),
    title_id: str | None = Query(default=None, max_length=36),
    archived: bool = Query(
        default=False,
        description="true면 보관된 계정'만' 보여준다. 기본(false)은 보관된 계정을 숨긴다.",
    ),
    locked: bool | None = Query(
        default=None,
        description="true면 지금 잠긴 계정만, false면 안 잠긴 계정만. 기본(생략)은 안 거른다.",
    ),
):
    now = request.app.state.clock.now()
    stmt = _filtered_users_stmt(
        principal.management, q=q, role=role, active=active,
        department_id=department_id, title_id=title_id, archived=archived,
        locked=locked, now=now,
    )

    total = db.execute(
        select(func.count()).select_from(stmt.subquery())
    ).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(User.created_at.desc(), User.id.desc()).offset(page.offset).limit(page.page_size)
        )
        .scalars()
        .all()
    )
    statuses = _notion_status_map(db, [u.id for u in rows])
    return {
        "items": [
            _user_row(u, now, notion_status=statuses.get(u.id, "unmapped")) for u in rows
        ],
        "total": total,
        "page": page.page,
        "page_size": page.page_size,
    }


# ── 대량 작업 · CSV (Phase 6) ─────────────────────────────────────────────────
#
# 경로를 **두 세그먼트**로 둔 이유: 아래의 단건 경로는 전부 `/{user_id}` 로 시작하는 한
# 세그먼트 패턴이다. `/bulk/apply` · `/export/csv` · `/import/csv` 는 두 번째 세그먼트가
# 리터럴이라 `/{user_id}/enable` 류와 절대 겹치지 않는다 — 선언 순서에 의존하지 않고
# 구조로 충돌을 없앤다(정적 경로가 경로 파라미터에 가려지는 전형적인 함정 회피).

@router.post("/bulk/apply")
def bulk_apply_users(
    request: Request,
    payload: BulkUserActionRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """선택한 사용자들에게 같은 작업을 적용한다. **부분 실패를 그대로 돌려준다.**"""
    result = bulk.bulk_apply(
        db,
        user_ids=list(payload.user_ids),
        action=payload.action,
        value=payload.value,
        actor=request.state.user,
        scope=principal.management,
        session_service=request.app.state.session_service,
        now=request.app.state.clock.now(),
    )
    # 감사는 **건별**로 남긴다. 한 줄로 뭉치면 "누가 언제 이 사람을 비활성화했나"를
    # 대상 id 로 조회할 수 없다(감사 화면의 object_id 필터가 그 방식으로 동작한다).
    for row in result["applied"]:
        if not row["changed"]:
            continue
        record_audit_from_request(
            request, db, action=f"user.bulk_{payload.action}", object_type="user",
            object_id=row["id"], before=row["before"], after=row["after"],
        )
    return result


@router.get("/export/csv")
def export_users_csv(
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    q: str | None = Query(default=None, max_length=255),
    role: str | None = Query(default=None),
    active: bool | None = Query(default=None),
    department_id: str | None = Query(default=None, max_length=36),
    title_id: str | None = Query(default=None, max_length=36),
    archived: bool = Query(default=False),
    locked: bool | None = Query(default=None),
):
    """지금 화면에 걸린 필터 **그대로** 내보낸다(같은 문장을 쓴다 — _filtered_users_stmt).

    범위(0024)가 그대로 적용되므로 부서 관리자는 자기 서브트리만 받는다. 비밀번호 해시는
    어떤 열에도 없다(app/users/bulk.py EXPORT_COLUMNS).
    """
    now = request.app.state.clock.now()
    stmt = _filtered_users_stmt(
        principal.management, q=q, role=role, active=active,
        department_id=department_id, title_id=title_id, archived=archived,
        locked=locked, now=now,
    )
    rows = db.execute(stmt.order_by(User.created_at.desc(), User.id.desc())).scalars().all()
    body = bulk.export_csv(list(rows), now=now)
    record_audit_from_request(
        request, db, action="user.export_csv", object_type="user",
        after={"row_count": len(rows), "archived": archived},
    )
    # 파일명은 ASCII 로만 둔다 — 한글 파일명은 브라우저마다 인코딩 규칙이 달라 깨진 이름이
    # 저장된다. 날짜는 서버 시각(UTC)이 아니라 표시 규약(KST)과 맞출 필요가 없는 식별자다.
    filename = f"users-{now.strftime('%Y%m%d-%H%M%S')}.csv"
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import/csv")
def import_users_csv(
    request: Request,
    payload: ImportUsersRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """CSV 로 계정을 만든다. 기본은 **미리보기(dry_run)** — 실제 생성은 명시해야 한다."""
    rows = bulk.parse_import_csv(payload.csv_text)
    result = bulk.import_users(
        db, rows,
        actor=request.state.user,
        scope=principal.management,
        settings=request.app.state.settings,
        effective_settings=request.app.state.settings_cache.current(),
        dry_run=payload.dry_run,
    )
    if not payload.dry_run:
        for row in result["results"]:
            if row.get("status") == "created" and row.get("user_id"):
                record_audit_from_request(
                    request, db, action="user.import_create", object_type="user",
                    object_id=row["user_id"],
                    after={"email": row["email"], "role": row["role"]},
                )
    return result


@router.post("", status_code=201)
def create_user_endpoint(
    request: Request,
    payload: UserCreateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    from app.core.security import generate_temp_password

    # SEC-30: the admin+ role-grant gate now lives inside create_user() itself
    # (ensure_can_grant_role) so every entry point shares one rule — see that
    # function's docstring for why (the CSV import path used to skip it).
    settings = request.app.state.settings
    # Blank/whitespace from the admin form means "generate one" — never accept it
    # as a real password.
    provided = (payload.password or "").strip() or None
    generated = provided is None
    password = provided if provided is not None else generate_temp_password()

    user = create_user(
        db,
        email=payload.email,
        display_name=payload.display_name,
        password=password,
        settings=settings,
        actor_role=request.state.user.role,
        role=payload.role,
        active=payload.active,
        must_change_password=payload.must_change_password,
        department_id=payload.department_id,
        title_id=payload.title_id,
        membership_kind=payload.membership_kind,
        created_by=request.state.user.id,
        effective_settings=request.app.state.settings_cache.current(),
    )
    # 범위가 걸린 관리자는 자기 범위 **밖에 계정을 새로 만들 수도 없다**. 막지 않으면 부서
    # 관리자가 다른 부서 소속으로 계정을 만들어 두고(자기 목록에는 보이지도 않는다) 그것을
    # 발판으로 삼는 우회로가 열린다.
    # 판정을 payload 가 아니라 **실제로 만들어진 행**에 대고 하는 이유: 목록·단건과 정확히
    # 같은 규칙(scope_allows_user) 하나만 쓰게 되어, org_id 기본값 같은 세부가 나중에 바뀌어도
    # 세 곳이 갈라지지 않는다. 여기서 예외가 나면 get_db 가 롤백하므로 계정은 남지 않는다.
    # 목록이 아니라 '생성 시도'라 존재를 숨길 것이 없으므로 404 가 아니라 403 이다.
    if not scope_allows_user(principal.management, user):
        raise ForbiddenError("관리 범위 밖으로는 계정을 만들 수 없습니다.")

    record_audit_from_request(
        request,
        db,
        action="user.create",
        object_type="user",
        object_id=user.id,
        after=user_snapshot(user),
    )

    now = request.app.state.clock.now()
    body = {"user": _user_row(user, now)}
    if generated:
        # Shown exactly once (spec §11.1) — never logged or audited.
        body["temp_password"] = password
        body["temp_password_notice"] = "임시 비밀번호는 이번 응답에서만 확인할 수 있습니다."
    body["invite_mail"] = _queue_invite_mail(request, db, user, now)
    return body


def _queue_invite_mail(request: Request, db: Session, user, now) -> dict:
    """초대 메일을 큐에 넣고 **결과를 응답에 싣는다** (9-9 P4).

    결과를 돌려주는 것이 핵심이다. 조용히 실패하면 관리자는 "초대가 나갔겠지" 라고 믿고
    아무 안내도 안 한다 - 그러면 새 직원은 아무 메일도 못 받은 채 첫 출근을 한다.

    **메일에 임시 비밀번호를 싣지 않는다.** 1회용 재설정 링크를 보낸다. 비밀번호를 메일에
    실으면 그 문자열이 잡 payload 나 아웃박스에 앉거나(불변 §4 위반), 메일함에 영구히
    남아 계정 하나가 그 메일함과 같은 수명을 갖게 된다.
    """
    from app.mail.renderers import KIND_INVITE
    from app.mail.service import queue_mail

    try:
        row = queue_mail(
            db,
            kind=KIND_INVITE,
            to_email=user.email,
            subject="[ClovirAssist] 업무 포털 계정이 만들어졌습니다",
            params={"user_id": user.id},
            now=now,
            secret_provider=getattr(request.app.state, "secret_provider", None),
        )
    except Exception:  # noqa: BLE001 - 계정 생성이 메일 때문에 실패하면 안 된다
        import logging

        logging.getLogger("app.users").exception("초대 메일을 큐에 넣지 못했다")
        return {"queued": False, "reason": "초대 메일을 큐에 넣지 못했습니다."}
    queued = row.status == MAIL_QUEUED
    return {
        "queued": queued,
        "reason": None if queued else (row.last_error or "메일을 보낼 수 없습니다."),
    }


@router.get("/{user_id}")
def get_user_detail(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    from app.core.errors import ForbiddenError

    user = get_scoped_user_or_404(db, user_id, principal.management)
    now = request.app.state.clock.now()
    status = _notion_status_map(db, [user.id]).get(user.id, "unmapped")
    row = _user_row(user, now, notion_status=status)
    # 세션 '개수'도 세션 목록(/sessions)과 같은 권한 경계 안에서만 보여야 한다 — /sessions는
    # 이미 막는데 여기 count만 새면 상위 권한 계정 정찰 차단이 반만 지켜진다. 상세 자체는
    # 볼 수 있게 두되(프런트가 canManage로 처리) count만 뺀다.
    try:
        ensure_can_manage_target(request.state.user.role, user)
    except ForbiddenError:
        return row
    # SEC-05 — revoked_at IS NULL 만으로는 "지금 살아있다"가 아니다. 만료됐지만 그 토큰으로
    # 다시 요청이 온 적 없는 세션은 SessionService.validate(core/sessions.py)가 지연 채점할
    # 기회 자체가 없어 revoked_at이 영원히 비어 있다 — expires_at도 같이 걸러야 한다.
    active_sessions = db.execute(
        select(func.count())
        .select_from(UserSession)
        .where(
            UserSession.user_id == user.id, UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
    ).scalar_one()
    return {**row, "active_session_count": active_sessions}


@router.patch("/{user_id}")
def patch_user(
    request: Request,
    user_id: str,
    payload: UserUpdateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    user = get_scoped_user_or_404(db, user_id, principal.management)
    before = user_snapshot(user)
    fields = payload.model_dump(exclude_unset=True)

    if not fields:
        # 프런트(diffFields, Users.jsx)는 실제로 바뀐 필드만 담아 보내므로, 빈 본문은
        # '아무것도 안 바뀐 저장'이다. 그래도 update_user()를 부르고 user.update 감사
        # 행을 남기면(before==after) '무엇이 바뀌었나'를 추적하는 감사 로그에 아무 의미
        # 없는 이벤트가 계속 쌓인다. 조기 반환한다.
        now = request.app.state.clock.now()
        return {"user": _user_row(user, now)}

    from app.core.errors import ForbiddenError

    new_role = fields.get("role")
    role_changing = new_role is not None and new_role != user.role
    # Changing system_admin membership (grant OR revoke) is system_admin's
    # authority alone — a plain admin cannot request it, so no such approval is
    # ever created (closes the two-admins-collude-to-system_admin escalation and
    # the ungated-demotion gap).
    if role_changing and (new_role == "system_admin" or user.role == "system_admin"):
        if request.state.user.role != "system_admin":
            raise ForbiddenError("system_admin 권한의 부여/회수는 system_admin만 가능합니다.")

    # Spec §20: 일반 admin으로의 승격은 승인 대상(비-sysadmin은 승인 요청 생성).
    if role_changing and new_role == "admin":
        from app.approvals.service import approval_view, create_approval, needs_approval

        if needs_approval(request.state.user):
            # 역할 승격만 승인 대상이다. 같은 요청에 담긴 다른 필드(이름·부서·직책 등)는 승인이
            # 필요 없으므로 즉시 적용한다 — 승인 payload가 role만 담아, 함께 보낸 필드가 202와 함께
            # 조용히 유실되고 승인 후에도 영영 반영되지 않던 결함(round16 스윕).
            non_role_fields = {k: v for k, v in fields.items() if k != "role"}
            if non_role_fields:
                update_user(
                    db, user,
                    session_service=request.app.state.session_service,
                    actor_role=request.state.user.role,
                    **non_role_fields,
                )
                record_audit_from_request(
                    request, db, action="user.update", object_type="user",
                    object_id=user.id, before=before, after=user_snapshot(user),
                )
            approval = create_approval(
                db,
                request_type="user.role_change",
                object_type="user",
                object_id=user.id,
                requested_by=request.state.user,
                # previous_role lets the approver see 현재 역할 → 요청 역할 without
                # leaving the approvals screen to look the user up — without it a
                # rubber-stamp approve can't be told apart from a dangerous
                # escalation (e.g. operator→admin vs admin→admin re-request).
                # target_name/target_email so the approver sees WHO is being
                # promoted, not just a bare object_id UUID — requester/approver
                # already get name+email resolution (resolve_names below), but
                # the approval TARGET didn't (round22). objectField in
                # registry.js's approvals.detailFields renders every payload
                # key as a label/value row, so adding these here surfaces them
                # without any further lookup.
                payload={
                    "role": new_role,
                    "previous_role": user.role,
                    "target_name": user.display_name,
                    "target_email": user.email,
                },
                now=request.app.state.clock.now(),
            )
            record_audit_from_request(
                request, db, action="user.role_change_requested", object_type="user",
                object_id=user.id, after={"approval_id": approval.id, "role": new_role},
            )
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=202,
                content={
                    "status": "approval_pending",
                    "approval": approval_view(approval),
                },
            )

    update_user(
        db,
        user,
        session_service=request.app.state.session_service,
        actor_role=request.state.user.role,
        **fields,
    )
    record_audit_from_request(
        request,
        db,
        action="user.update",
        object_type="user",
        object_id=user.id,
        before=before,
        after=user_snapshot(user),
    )
    now = request.app.state.clock.now()
    return {"user": _user_row(user, now)}


@router.post("/{user_id}/enable")
def enable_user(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    user = get_scoped_user_or_404(db, user_id, principal.management)
    before = user_snapshot(user)
    set_user_active(db, user, True, session_service=request.app.state.session_service,
                    actor_role=request.state.user.role)
    record_audit_from_request(
        request, db, action="user.enable", object_type="user",
        object_id=user.id, before=before, after=user_snapshot(user),
    )
    return {"ok": True}


@router.post("/{user_id}/disable")
def disable_user(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    user = get_scoped_user_or_404(db, user_id, principal.management)
    before = user_snapshot(user)
    set_user_active(db, user, False, session_service=request.app.state.session_service,
                    actor_role=request.state.user.role)
    record_audit_from_request(
        request, db, action="user.disable", object_type="user",
        object_id=user.id, before=before, after=user_snapshot(user),
    )
    return {"ok": True}


@router.post("/{user_id}/archive")
def archive(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """계정 보관 — 삭제가 아니다. 행은 DB에 남고 목록·검색·로그인에서만 빠진다."""
    user = get_scoped_user_or_404(db, user_id, principal.management)
    before = user_snapshot(user)
    archive_user(
        db,
        user,
        session_service=request.app.state.session_service,
        actor_role=request.state.user.role,
        actor_id=request.state.user.id,
        now=request.app.state.clock.now(),
    )
    record_audit_from_request(
        request, db, action="user.archive", object_type="user",
        object_id=user.id, before=before, after=user_snapshot(user),
    )
    return {"ok": True}


@router.post("/{user_id}/unarchive")
def unarchive(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """보관 복구 — 보관 전의 활성/비활성 상태 그대로 목록에 돌아온다."""
    user = get_scoped_user_or_404(db, user_id, principal.management)
    before = user_snapshot(user)
    unarchive_user(db, user, actor_role=request.state.user.role)
    record_audit_from_request(
        request, db, action="user.unarchive", object_type="user",
        object_id=user.id, before=before, after=user_snapshot(user),
    )
    return {"ok": True}


@router.post("/{user_id}/reset-password")
def reset_password(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    payload: ResetPasswordRequest | None = None,
):
    user = get_scoped_user_or_404(db, user_id, principal.management)
    provided = payload.password if payload is not None else None
    password = admin_reset_password(
        db,
        user,
        session_service=request.app.state.session_service,
        actor_role=request.state.user.role,
        new_password=provided,
        effective_settings=request.app.state.settings_cache.current(),
        now=request.app.state.clock.now(),
    )
    record_audit_from_request(
        request, db, action="user.reset_password", object_type="user", object_id=user.id,
    )
    body: dict = {"ok": True, "must_change_password": True}
    if provided is None:
        body["temp_password"] = password
        body["temp_password_notice"] = "임시 비밀번호는 이번 응답에서만 확인할 수 있습니다."
    return body


@router.post("/{user_id}/unlock")
def unlock(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    user = get_scoped_user_or_404(db, user_id, principal.management)
    unlock_user(db, user, actor_role=request.state.user.role)
    record_audit_from_request(
        request, db, action="user.unlock", object_type="user", object_id=user.id,
    )
    return {"ok": True}


@router.get("/{user_id}/sessions")
def list_sessions(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    user = get_scoped_user_or_404(db, user_id, principal.management)
    # 세션 메타데이터도 권한 경계 안에서만 조회한다(상위 권한 계정 정보 정찰 차단).
    ensure_can_manage_target(request.state.user.role, user)  # authority boundary
    # SEC-05 — revoked_at IS NULL 만으로는 부족하다(위 active_session_count와 같은 이유).
    now = request.app.state.clock.now()
    rows = (
        db.execute(
            select(UserSession)
            .where(
                UserSession.user_id == user.id, UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
            )
            .order_by(UserSession.last_seen_at.desc())
        )
        .scalars()
        .all()
    )
    return {
        "items": [
            {
                "id": s.id,
                "created_at": s.created_at.isoformat(),
                "last_seen_at": s.last_seen_at.isoformat(),
                "expires_at": s.expires_at.isoformat(),
                "client_ip": s.client_ip,
                "user_agent": s.user_agent,
            }
            for s in rows
        ]
    }


@router.post("/{user_id}/revoke-sessions")
def revoke_sessions(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    user = get_scoped_user_or_404(db, user_id, principal.management)
    ensure_can_manage_target(request.state.user.role, user)  # authority boundary
    count = request.app.state.session_service.revoke_all_for_user(db, user.id)
    record_audit_from_request(
        request, db, action="user.revoke_sessions", object_type="user",
        object_id=user.id, after={"revoked_count": count},
    )
    return {"ok": True, "revoked_count": count}
