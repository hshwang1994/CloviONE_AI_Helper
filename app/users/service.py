"""User service layer — shared by web admin API and the CLI (spec §29)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.authz import CONSOLE_WRITE_ROLES
from app.core.config import Settings
from app.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationAppError,
)
from app.core.security import (
    generate_temp_password,
    hash_password,
    validate_password_policy,
)
from app.core.models_base import utcnow
from app.core.sessions import SessionService
from app.org.models import Department, JobTitle, Organization
from app.org.service import resolve_assignable
from app.users.models import (
    ADMIN_SCOPE_DEPT,
    ADMIN_SCOPE_GLOBAL,
    ADMIN_SCOPE_ORG,
    ALL_ADMIN_SCOPES,
    ALL_MEMBERSHIP_KINDS,
    ALL_ROLES,
    MEMBERSHIP_DEPARTMENT,
    MEMBERSHIP_UNASSIGNED,
    ROLE_SYSTEM_ADMIN,
    User,
)


class _Unset:
    """'보내지 않음'과 '비우라고 보냄(None)'을 구분하는 표식. 부서·직책은 None이
    "부서 없음"이라는 유효한 값이라, None 하나로는 두 뜻을 담을 수 없다."""


UNSET = _Unset()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_company_email(
    email: str, settings: Settings, *, allowed_domains: list[str] | None = None
) -> None:
    """허용 도메인 목록이 **비어 있으면 제한하지 않는다.**

    같은 저장소 안에서 두 경로가 정반대로 굴었다. DB 설정을 넘기는 경로(create_user 의
    `if configured:` 분기)는 빈 목록을 '제한 없음' 으로 읽었는데, env 기본값만 쓰는 폴백
    경로(CLI·seed)는 `domain not in []` 라서 **모든 이메일을 거절**하고 도메인 이름이
    빠진 "회사 이메일 도메인()만" 이라는 뜻 모를 메시지를 냈다.

    설치처 고유값을 기본값에서 비우면서 그 빈 목록이 기본 상태가 됐으므로, 방향을
    한쪽으로 고정한다. '제한 없음' 을 고른 근거:
      * 로그인은 도메인을 보지 않는다(app/auth/router.py) — 이 검사는 **계정 생성** 전용이라
        비워도 기존 사용자가 잠기지 않는다.
      * 계정 생성은 관리자 전용 경로뿐이다(관리 콘솔·일괄 등록 CSV·CLI·seed). 공개 가입이
        없으므로 '제한 없음' 이 아무나 들어온다는 뜻이 되지 않는다.
      * 반대 방향으로 잡으면 설치 직후 **첫 관리자 계정조차 못 만든다**.
    """
    domains = allowed_domains if allowed_domains else settings.allowed_email_domain_list
    if not domains:
        return
    domain = email.rsplit("@", 1)[-1] if "@" in email else ""
    if not domain or domain not in domains:
        allowed = ", ".join(domains)
        raise ValidationAppError(f"회사 이메일 도메인({allowed})만 사용할 수 있습니다.")


class ArchivedEmailConflictError(ConflictError):
    """이메일은 유일 제약이라 보관된 계정이 그 주소를 계속 쥐고 있다. 그냥 '이미 등록된
    이메일입니다'라고만 하면, 목록 어디에도 없는 계정 때문에 막힌 사용자는 이유를 알
    방법이 없다 — 무엇이 막고 있는지와 다음 행동(복구)을 함께 알린다."""

    code = "archived_email_conflict"
    default_message = "그 이메일은 보관된 계정이 쓰고 있습니다. 복구하시겠습니까?"


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.execute(
        select(User).where(User.email == normalize_email(email))
    ).scalar_one_or_none()


def ensure_can_grant_role(actor_role: str, role: str) -> None:
    """Authority boundary for account CREATION (spec §20, SEC-30): minting an
    admin-or-above account is a role grant, so only system_admin may do it —
    a plain admin (even org/global-scoped) cannot create another admin or
    system_admin account.

    Enforced *inside* ``create_user`` (below) rather than left to each caller,
    because it used to be left to each caller: the single-user web form had
    this check, but the CSV bulk-import path (``app/users/bulk.py``) called
    ``create_user`` directly with no equivalent check at all — an `admin`
    could mint a `system_admin` account through a CSV upload. Putting the
    gate here means every entry point (web form, CSV import, CLI,
    seed_admin.py) is covered by construction; a new caller cannot forget it.
    """
    if role in CONSOLE_WRITE_ROLES and actor_role != ROLE_SYSTEM_ADMIN:
        raise ForbiddenError("admin 이상 권한 계정 생성은 system_admin만 가능합니다.")


def _resolved_membership(department_id: str | None, membership_kind: str | None) -> str:
    """새 계정의 소속 종류. **추측하지 않는다** (0060).

    부서가 있으면 부서 소속이 자명하다. 부서가 없으면 사람이 명시한 값만 쓰고, 명시가
    없으면 미지정이다 — 미지정은 조직 데이터를 아무것도 못 보는 상태이고, 관리자 진단이
    그 계정을 목록으로 보여 준다. 예전에는 이 자리에서 전역으로 폴백했고, 그 편의가
    실측 25명 중 21명을 전 포털 가시성으로 만들었다.
    """
    if department_id:
        return MEMBERSHIP_DEPARTMENT
    if membership_kind in ALL_MEMBERSHIP_KINDS:
        if membership_kind == MEMBERSHIP_DEPARTMENT:
            raise ValidationAppError("부서 소속으로 두려면 부서를 함께 지정해야 합니다.")
        return membership_kind
    return MEMBERSHIP_UNASSIGNED


def create_user(
    db: Session,
    *,
    email: str,
    display_name: str,
    password: str,
    settings: Settings,
    actor_role: str,
    role: str = "user",
    active: bool = True,
    must_change_password: bool = True,
    department_id: str | None = None,
    title_id: str | None = None,
    membership_kind: str | None = None,
    created_by: str | None = None,
    enforce_password_policy: bool = True,
    effective_settings: dict | None = None,
) -> User:
    email = normalize_email(email)
    if not display_name.strip():
        raise ValidationAppError("이름을 입력해야 합니다.")
    if role not in ALL_ROLES:
        raise ValidationAppError(f"알 수 없는 역할입니다: {role}")
    ensure_can_grant_role(actor_role, role)

    eff = effective_settings or {}
    if "allowed_email_domains" in eff:
        # 설정에 명시된 값을 그대로 존중한다. 빈 목록([])은 '도메인 제한 없음'을 뜻하므로
        # 회사 이메일 검사를 건너뛴다(Settings 화면 안내·registry 검증기와 일치).
        configured = [d.strip().lower() for d in (eff.get("allowed_email_domains") or [])]
        if configured:
            validate_company_email(email, settings, allowed_domains=configured)
    else:
        # effective_settings가 없는 경로(예: 일부 CLI)는 env 기본 도메인으로 검사한다.
        validate_company_email(email, settings)
    if enforce_password_policy:
        policy = eff.get("password_policy") or {}
        problems = validate_password_policy(
            password,
            min_length=policy.get("min_length", 12),
            min_classes=policy.get("min_classes", 3),
        )
        if problems:
            raise ValidationAppError("비밀번호 정책 위반", details=problems)
    existing = get_user_by_email(db, email)
    if existing is not None:
        if existing.archived_at is not None:
            raise ArchivedEmailConflictError(
                details={"archived_user_id": existing.id, "email": existing.email}
            )
        raise ConflictError("이미 등록된 이메일입니다.")

    user = User(
        email=email,
        display_name=display_name.strip(),
        role=role,
        active=active,
        password_hash=hash_password(password),
        must_change_password=must_change_password,
        # 명부에 없는 id나 비활성 항목을 그대로 쓰면 FK 위반이 500으로 터진다.
        department_ref=resolve_assignable(db, Department, department_id),
        title_ref=resolve_assignable(db, JobTitle, title_id),
        # 소속 종류(0060). 부서를 주면 그 사실 그대로 'department', 아니면 명시한 값,
        # 아무 것도 안 주면 **미지정**(조직 데이터를 못 본다). 기본값을 넓게 두지 않는다 —
        # "부서를 아직 안 정했다" 를 조직 직속으로 추측하면 그 추측은 유출이 된다.
        membership_kind=_resolved_membership(department_id, membership_kind),
        created_by=created_by,
    )
    db.add(user)
    db.flush()
    return user


def get_user_or_404(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("사용자를 찾을 수 없습니다.")
    return user


def get_scoped_user_or_404(db: Session, user_id: str, scope) -> User:
    """범위를 존중하는 단건 조회 — **범위 밖은 403이 아니라 404** 다.

    403 은 "그 id 는 존재한다"를 알려 주는 유출이다. 남의 부서 사용자 id 를 넣어 보며
    403/404 를 세면 조직도를 통째로 열거할 수 있다. 목록에서 가린 것이 단건에서 새면
    가린 의미가 없으므로 존재하지 않는 것과 **똑같은 응답**을 준다.

    관리자 라우터의 모든 `/{user_id}` 경로가 이 함수 하나를 통과해야 한다 — 한 군데라도
    `get_user_or_404` 를 그대로 쓰면 그 경로만 범위를 무시한다.
    """
    from app.core.scope import scope_allows_user

    user = get_user_or_404(db, user_id)
    if not scope_allows_user(scope, user):
        raise NotFoundError("사용자를 찾을 수 없습니다.")
    return user


def user_snapshot(user: User) -> dict:
    """Audit-safe snapshot — the password hash is never included."""
    return {
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "active": user.active,
        "must_change_password": user.must_change_password,
        "department": user.department,
        "title": user.title,
        "archived_at": user.archived_at.isoformat() if user.archived_at else None,
        # 범위는 **권한이다** — 넓히면 볼 수 있는 것이 늘어난다. 역할과 같은 무게로 남긴다.
        # 여기 없으면 "누가 언제 이 관리자를 전체 범위로 올렸나" 를 답할 수 없다.
        "admin_scope": user.admin_scope,
        "scope_org_id": user.scope_org_id,
        "scope_dept_id": user.scope_dept_id,
        # 소속도 권한이다(0060) — 미지정에서 조직 직속으로 바꾸면 조직 전체가 보인다.
        # 감사에 안 남기면 "누가 이 계정을 조직 전체로 열었나" 에 답할 수 없다.
        "membership_kind": user.membership_kind,
    }


def count_active_system_admins(db: Session, *, exclude_user_id: str | None = None) -> int:
    """보관된 계정은 세지 않는다. 보관은 active 플래그를 건드리지 않으므로(복구 시
    원래 상태로 돌아와야 한다), 여기서 빼지 않으면 '보관돼서 로그인도 못 하는
    system_admin'이 마지막 관리자 자리를 채우고 있는 것으로 세어져, 진짜 마지막
    관리자를 비활성화·강등하는 문이 열린다."""
    stmt = (
        select(func.count())
        .select_from(User)
        .where(
            User.role == ROLE_SYSTEM_ADMIN,
            User.active.is_(True),
            User.archived_at.is_(None),
        )
    )
    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)
    return db.execute(stmt).scalar_one()


def ensure_not_last_system_admin(db: Session, user: User) -> None:
    """Block disabling/archiving/demoting the only active system_admin (spec §32.8)."""
    if user.role != ROLE_SYSTEM_ADMIN or not user.active:
        return
    if count_active_system_admins(db, exclude_user_id=user.id) == 0:
        raise ConflictError(
            "마지막 system_admin 계정은 비활성화, 보관하거나 역할을 변경할 수 없습니다."
        )


def ensure_can_manage_target(actor_role: str, target: User) -> None:
    """Authority boundary for account-lifecycle mutations (reset-password,
    enable/disable, unlock, revoke-sessions, profile edits): a non-system_admin
    may not act on a system_admin account. Prevents a plain admin from taking
    over a higher-privileged account (e.g. resetting its password and logging
    in). Enforced in the service layer so the HTTP routers, the CLI, and any
    approval executor are all covered."""
    if target.role == ROLE_SYSTEM_ADMIN and actor_role != ROLE_SYSTEM_ADMIN:
        raise ForbiddenError("system_admin 계정은 system_admin만 관리할 수 있습니다.")


def update_user(
    db: Session,
    user: User,
    *,
    session_service: SessionService,
    actor_role: str,
    display_name: str | None = None,
    department_id: str | None | _Unset = UNSET,
    title_id: str | None | _Unset = UNSET,
    membership_kind: str | None = None,
    role: str | None = None,
    must_change_password: bool | None = None,
    admin_scope: str | None = None,
    scope_org_id: str | None | _Unset = UNSET,
    scope_dept_id: str | None | _Unset = UNSET,
) -> User:
    ensure_can_manage_target(actor_role, user)
    if display_name is not None:
        if not display_name.strip():
            raise ValidationAppError("이름은 비울 수 없습니다.")
        user.display_name = display_name.strip()
    # 부서·직책만 None이 뜻을 갖는다: "부서 없음"은 유효한 값이라 '안 보냄'과 구분해야
    # 한다(다른 필드는 None=안 보냄이면 충분하다). router가 exclude_unset으로 걸러
    # 보내므로, 여기 도달한 None은 명시적으로 비우라는 요청이다.
    # 이미 이 사용자에게 배정된 항목이면 그 사이 비활성으로 바뀌었어도 재전송을
    # 허용한다 — 안 그러면 비활성 직책/부서를 가진 사용자를 편집(이름 변경 등)할 때
    # 폼이 같은 id를 다시 보내는 것만으로 저장이 막힌다. 새 비활성 항목 지정은 여전히 거부.
    if department_id is not UNSET:
        user.department_ref = resolve_assignable(
            db, Department, department_id, allow_current=user.department_id
        )
        # 부서를 바꾸면 소속 종류도 따라간다(0060). 부서를 **비우면** 그 사람이 조직 직속인지
        # 아직 미정인지 코드가 알 수 없으므로 미지정으로 되돌린다 — 그 상태는 관리자 진단에
        # 목록으로 뜨고, 사람이 조직 직속을 명시하면 그때 열린다. 같은 요청이 membership_kind 를
        # 함께 보냈으면 아래에서 그 값이 이긴다(사람의 명시가 추측보다 우선).
        user.membership_kind = (
            MEMBERSHIP_DEPARTMENT if user.department_id else MEMBERSHIP_UNASSIGNED
        )
    if membership_kind is not None:
        if membership_kind not in ALL_MEMBERSHIP_KINDS:
            raise ValidationAppError(f"알 수 없는 소속 종류입니다: {membership_kind}")
        if membership_kind == MEMBERSHIP_DEPARTMENT and not user.department_id:
            raise ValidationAppError("부서 소속으로 두려면 부서를 함께 지정해야 합니다.")
        if membership_kind != MEMBERSHIP_DEPARTMENT and user.department_id:
            raise ValidationAppError(
                "부서가 배정된 계정은 부서 소속입니다. 먼저 부서를 비우세요."
            )
        user.membership_kind = membership_kind
    if title_id is not UNSET:
        user.title_ref = resolve_assignable(
            db, JobTitle, title_id, allow_current=user.title_id
        )
    if must_change_password is not None:
        user.must_change_password = must_change_password
    if role is not None and role != user.role:
        if role not in ALL_ROLES:
            raise ValidationAppError(f"알 수 없는 역할입니다: {role}")
        ensure_not_last_system_admin(db, user)
        user.role = role
        # Privilege change invalidates existing sessions.
        session_service.revoke_all_for_user(db, user.id)
    _apply_admin_scope(
        db, user,
        admin_scope=admin_scope, scope_org_id=scope_org_id, scope_dept_id=scope_dept_id,
        session_service=session_service,
    )
    db.flush()
    return user


def _apply_admin_scope(
    db: Session, user: User, *, admin_scope, scope_org_id, scope_dept_id, session_service
) -> None:
    """관리 범위를 바꾼다 (F2).

    ## 경계에서 거른다

    `app/core/scope.py` 는 모르는 범위 값을 만나면 `MATCH_NOTHING` 으로 떨어진다 — 즉
    **오타 하나가 그 관리자의 화면을 통째로 비운다.** 그리고 그 증상은 "권한이 없습니다" 가
    아니라 "목록이 비어 있음" 이라 원인을 찾기가 매우 어렵다. 그래서 여기서 막는다:

      * 모르는 값 → 거부
      * `dept` 인데 대상 부서가 없음 → 거부 (아무것도 못 보는 계정이 만들어진다)
      * `org` 인데 대상 조직이 없음 → 거부
      * `global` → 대상 두 개를 **비운다** (남겨 두면 나중에 좁힐 때 옛 값이 되살아난다)

    ## 세션을 끊는 이유

    범위를 좁히는 것은 **권한을 줄이는 일**이다. 역할 변경과 같은 급이므로 같은 처리를 한다 —
    안 그러면 이미 열려 있는 세션이 좁아진 범위 밖 화면을 계속 보여 준다.
    """
    if admin_scope is None and scope_org_id is UNSET and scope_dept_id is UNSET:
        return

    target_scope = admin_scope or user.admin_scope
    if target_scope not in ALL_ADMIN_SCOPES:
        raise ValidationAppError(
            f"알 수 없는 관리 범위입니다: {target_scope}. "
            f"가능한 값: {', '.join(sorted(ALL_ADMIN_SCOPES))}"
        )

    org_id = user.scope_org_id if scope_org_id is UNSET else scope_org_id
    dept_id = user.scope_dept_id if scope_dept_id is UNSET else scope_dept_id

    if target_scope == ADMIN_SCOPE_GLOBAL:
        org_id = None
        dept_id = None
    elif target_scope == ADMIN_SCOPE_DEPT:
        if not dept_id:
            raise ValidationAppError("부서 범위에는 대상 부서를 지정해야 합니다.")
        if db.get(Department, dept_id) is None:
            raise ValidationAppError("대상 부서를 찾을 수 없습니다.")
    elif target_scope == ADMIN_SCOPE_ORG:
        if not org_id:
            raise ValidationAppError("조직 범위에는 대상 조직을 지정해야 합니다.")
        if db.get(Organization, org_id) is None:
            raise ValidationAppError("대상 조직을 찾을 수 없습니다.")

    changed = (
        user.admin_scope != target_scope
        or user.scope_org_id != org_id
        or user.scope_dept_id != dept_id
    )
    user.admin_scope = target_scope
    user.scope_org_id = org_id
    user.scope_dept_id = dept_id
    if changed:
        session_service.revoke_all_for_user(db, user.id)


def set_user_active(
    db: Session,
    user: User,
    active: bool,
    *,
    session_service: SessionService,
    actor_role: str,
) -> User:
    ensure_can_manage_target(actor_role, user)
    if user.active == active:
        return user
    if not active:
        ensure_not_last_system_admin(db, user)
    user.active = active
    if not active:
        # Spec §11.5: 비활성화 시 기존 세션 즉시 폐기.
        session_service.revoke_all_for_user(db, user.id)
        _disable_owned_schedules(db, user.id)
        _transfer_owned_chat_rooms(db, user)
    db.flush()
    return user


def ensure_not_self(actor_id: str | None, user: User) -> None:
    """자기 자신은 보관할 수 없다. 보관하는 순간 자기 세션이 끊기고, 보관된 계정은
    목록에서 사라지므로 스스로를 되돌릴 사람이 화면 안에 아무도 없게 된다."""
    if actor_id is not None and actor_id == user.id:
        raise ConflictError("자기 자신의 계정은 보관할 수 없습니다. 다른 관리자에게 요청하세요.")


def archive_user(
    db: Session,
    user: User,
    *,
    session_service: SessionService,
    actor_role: str,
    actor_id: str | None = None,
    now: datetime | None = None,
) -> User:
    """계정을 보관한다 — 행은 남기고 목록·검색·로그인에서만 뺀다(삭제 아님).

    수명주기 변경이므로 disable과 같은 안전장치를 전부 거친다: 권한 경계
    (ensure_can_manage_target), 마지막 system_admin 보호, 자기 자신 금지.
    ``active``는 건드리지 않는다 — 복구했을 때 보관 전 상태로 정확히 돌아와야 한다.
    """
    ensure_can_manage_target(actor_role, user)
    ensure_not_self(actor_id, user)
    if user.archived_at is not None:
        return user  # 멱등: 이미 보관됨
    ensure_not_last_system_admin(db, user)
    user.archived_at = now or utcnow()
    # 보관은 '되돌릴 수 있는 퇴사 처리'다 — 로그인만 막고 이미 열린 세션을 살려 두면
    # 감춘 시늉만 한 것이 된다(§11.5의 비활성화와 같은 이유).
    session_service.revoke_all_for_user(db, user.id)
    _disable_owned_schedules(db, user.id)
    _transfer_owned_chat_rooms(db, user)
    db.flush()
    return user


def unarchive_user(
    db: Session,
    user: User,
    *,
    actor_role: str,
) -> User:
    """보관을 되돌린다. active는 보관 때 건드리지 않았으므로 그대로 돌아온다 —
    보관 전에 비활성이던 계정은 비활성인 채로 복구된다(없던 권한을 주지 않는다)."""
    ensure_can_manage_target(actor_role, user)
    user.archived_at = None
    db.flush()
    return user


def _disable_owned_schedules(db: Session, user_id: str) -> int:
    """Spec §11.5: a deactivated user's enabled schedules must not keep firing.
    Disable them so an admin can reassign/re-enable deliberately."""
    from app.schedules.models import Schedule

    rows = db.execute(
        select(Schedule).where(
            Schedule.owner_user_id == user_id, Schedule.enabled.is_(True)
        )
    ).scalars().all()
    for schedule in rows:
        schedule.enabled = False
        schedule.next_run_at = None
    db.flush()
    return len(rows)


def _transfer_owned_chat_rooms(db: Session, user: User) -> int:
    """로그인 못 하게 되는 계정이 채팅방 방장으로 남지 않게 넘긴다(X8, step 9 #2).

    `_disable_owned_schedules`와 같은 이유·같은 자리다: 여기서 계정을 로그인 못 하게
    만들면(비활성화·보관) 그 순간부터 그 사람이 방장인 그룹 방은 `ensure_can_manage_room`에
    관리자 우회가 없어 **아무도** 이름을 바꾸거나 사람을 초대하거나 방을 파할 수 없다.

    예전엔 이 인계(`app.team_chat.service.transfer_owned_rooms`, 옛 이름
    `_transfer_room_ownership`)가 오프보딩 마법사 전체 실행 경로에만 있었다 — 관리자가
    `/users`에서 바로 비활성화·보관하면(오프보딩 마법사를 거치지 않고도 계정은 똑같이
    로그인을 못 하게 된다) 이 인계를 건너뛰었다. 후임 개념이 없는 경로라 `successor=None`
    으로 부른다(그 방의 가장 오래된 다른 멤버에게 넘어간다)."""
    from app.team_chat.service import transfer_owned_rooms

    return transfer_owned_rooms(db, target=user, successor=None)


def admin_reset_password(
    db: Session,
    user: User,
    *,
    session_service: SessionService,
    actor_role: str,
    new_password: str | None = None,
    effective_settings: dict | None = None,
    now: datetime | None = None,
) -> str:
    """Reset to a temp (or given) password. Returns the plaintext exactly once."""
    ensure_can_manage_target(actor_role, user)
    if new_password is not None:
        policy = (effective_settings or {}).get("password_policy") or {}
        problems = validate_password_policy(
            new_password,
            min_length=policy.get("min_length", 12),
            min_classes=policy.get("min_classes", 3),
        )
        if problems:
            raise ValidationAppError("비밀번호 정책 위반", details=problems)
        password = new_password
    else:
        password = generate_temp_password()
    user.password_hash = hash_password(password)
    user.must_change_password = True
    user.failed_login_count = 0
    user.locked_until = None
    session_service.revoke_all_for_user(db, user.id)
    # spec §13.5의 '비밀번호 만료/변경 요청' 알림 유형 — 재발급으로 must_change_password가
    # 켜지는 시점(그 대상 본인)에 보낸다. 세션을 이미 전부 폐기했으니 다음 로그인 때
    # 임시 비밀번호로 들어와서야 이 알림을 보게 된다(그 자체가 안내 역할을 한다).
    from app.notifications.service import notify_user

    notify_user(
        db, user.id, type_="password_change_required",
        title="비밀번호 변경이 필요합니다",
        body="관리자가 비밀번호를 재발급했습니다. 다음 로그인 시 새 비밀번호로 변경해 주세요.",
        now=now or utcnow(),
    )
    db.flush()
    return password


def unlock_user(db: Session, user: User, *, actor_role: str) -> User:
    ensure_can_manage_target(actor_role, user)
    user.locked_until = None
    user.failed_login_count = 0
    db.flush()
    return user
