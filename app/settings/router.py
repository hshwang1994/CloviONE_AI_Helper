"""Settings + Maintenance API (spec §14.4, §14.5)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.authz import CONSOLE_READ_ROLES, CONSOLE_WRITE_ROLES
from app.core.deps import (
    audit_forbidden_write,
    get_db,
    get_principal,
    require_csrf,
    require_roles,
)
from app.core.errors import ForbiddenError, ValidationAppError
from app.core.scope import Principal, require_global_management
from app.core.versioning import list_versions, load_snapshot
from app.settings.registry import REGISTRY
from app.settings.service import (
    OBJECT_TYPE,
    apply_setting,
    dry_run,
    effective_settings,
    rollback_setting,
)

router = APIRouter(
    prefix="/api/admin/settings",
    tags=["admin-settings"],
    dependencies=[Depends(require_csrf)],
)



class SettingChange(BaseModel):
    value: Any


# 사용자에게 그대로 보이는 주어. `require_global_management` 가 조사를 붙여
# "시스템 설정은 전체 범위 관리자만 바꿀 수 있습니다." 한 문장으로 만든다.
_SUBJECT = "시스템 설정"


def _guard_scope(request: Request, db: Session, principal: Principal) -> None:
    """설정 표의 값은 **설치 한 벌 전체**를 정한다 — 전역 관리 범위만 바꿀 수 있다.

    `CONSOLE_WRITE_ROLES` 의 `admin` 은 부서 범위로 좁혀질 수 있는데(`admin_scope="dept"`),
    이 표에는 부서라는 개념이 없다. 점검 모드 하나로 전 사원의 쓰기가 멈추고, 허용 이메일
    도메인 하나로 전 조직의 계정 생성 규칙이 바뀐다. 실제로 부서 범위 관리자가 점검 모드를
    켜서 다른 부서 사용자의 티켓 생성을 503 으로 막을 수 있었다.

    **레지스트리를 먼저 확인했다.** `app/settings/registry.py::REGISTRY` 의 스물두 개 키는
    전부 설치 단위 값이다(보존 기간·브랜딩·점검 모드·비밀번호/세션/잠금 정책·허용 도메인·
    색인 주기·문서 자동화·백업 일정·SMTP·LLM). 부서 단위로 뜻이 갈리는 키는 하나도 없으므로
    예외를 두지 않는다. 부서마다 달라야 하는 값이 새로 생기면 그때 그 키만 여기서 빼고
    이유를 적는다 — 표 전체를 여는 것이 아니다.

    `SYSTEM_ADMIN_ONLY_KEYS`(아래 `_guard_system_admin_key`)와 겹치지 않는다. 그쪽은
    **역할**을 더 좁히고(시스템 관리자만), 이쪽은 **범위**를 좁힌다(전역 관리자만).

    막은 시도는 감사에 남긴다. 역할 게이트(`require_roles`)는 이미
    `app/core/deps.py::audit_forbidden_write` 로 남기는데, 범위 게이트는 핸들러 안에서
    판정하므로 그 자리를 지나지 않는다 — 남기지 않으면 「점검 모드를 켜려던 시도」가
    아무 데도 없다. 예외를 삼키지 않고 그대로 다시 던진다.
    """
    try:
        require_global_management(principal, _SUBJECT)
    except ForbiddenError:
        audit_forbidden_write(request, db, request.state.user)
        raise


def _guard_system_admin_key(request: Request, key: str) -> None:
    """설치 한 벌 전체를 정하는 키는 시스템 관리자만 바꾼다 (9-4, 9-5).

    목록은 `app/settings/registry.py::SYSTEM_ADMIN_ONLY_KEYS` 에 이유와 함께 있다.
    여기서 막는 이유: `CONSOLE_WRITE_ROLES` 의 `admin` 은 부서 범위로 좁혀질 수 있는데,
    노션 데이터베이스 id 와 AI 실행 파일 경로에는 '부서' 라는 개념 자체가 없다.
    """
    from app.core.errors import ForbiddenError
    from app.settings.registry import SYSTEM_ADMIN_ONLY_KEYS
    from app.users.models import ROLE_SYSTEM_ADMIN

    if key in SYSTEM_ADMIN_ONLY_KEYS and request.state.user.role != ROLE_SYSTEM_ADMIN:
        raise ForbiddenError("이 설정은 시스템 관리자만 바꿀 수 있습니다.")


def _guard_dedicated_key(key: str) -> None:
    """전용 API 가 있는 키는 범용 설정 API 로 쓰지 않는다(D-545 · D-548).

    메일 설정(`smtp`)은 메일 화면의 `PUT /api/admin/mail/settings` 가 형식(모르는 칸 거절)과 비밀번호 저장, 저장 직후 연결 확인을
    한 번에 한다. 범용 경로로 쓰면 그 셋을 건너뛴다 - 시스템 관리자라도 같다.
    """
    from app.settings.registry import DEDICATED_API_KEYS

    if key in DEDICATED_API_KEYS:
        raise ValidationAppError(DEDICATED_API_KEYS[key])


@router.get("", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def list_settings(request: Request, db: Session = Depends(get_db)):
    return {"settings": effective_settings(db, request.app.state.settings_cache)}


@router.post("/{key}/dry-run", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def dry_run_setting(
    request: Request,
    key: str,
    payload: SettingChange,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    # 시험 실행도 저장 경로의 일부다 — 여기만 열어 두면 화면이 「이 값은 됩니다」까지
    # 안내한 뒤 저장에서 막는 막다른 길이 된다. `db` 는 거절을 감사에 남기려고 받는다.
    _guard_scope(request, db, principal)
    _guard_system_admin_key(request, key)
    _guard_dedicated_key(key)
    return dry_run(key, payload.value)


@router.put("/{key}", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def update_setting(
    request: Request,
    key: str,
    payload: SettingChange,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    _guard_scope(request, db, principal)
    _guard_system_admin_key(request, key)
    _guard_dedicated_key(key)
    result = apply_setting(
        db,
        request.app.state.settings_cache,
        key=key,
        value=payload.value,
        updated_by=request.state.user.id,
        now=request.app.state.clock.now(),
    )
    record_audit_from_request(
        request, db, action="setting.update", object_type=OBJECT_TYPE,
        object_id=key, before={"value": result["before"]}, after={"value": result["after"]},
    )
    # Maintenance-announcement notify (spec §13.5) now lives in
    # app.settings.service.apply_setting, the shared save path for both this
    # handler and `rollback` below — see that function for why.
    return result


@router.get("/{key}/versions", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def setting_versions(key: str, db: Session = Depends(get_db)):
    rows = list_versions(db, OBJECT_TYPE, key)
    # 설정을 되돌리는 화면에서 '누가 바꿨나'는 accountability의 기본 질문인데 지금껏
    # 응답에 없어(감사 로그를 따로 열어야 했다) created_by를 이름/이메일로 해석해 붙인다
    # (감사 로그와 동일 패턴, round30 감사 E).
    from app.approvals.service import resolve_names

    names = resolve_names(db, {r.created_by for r in rows})
    return {
        "items": [
            {
                "version": r.version,
                "snapshot": load_snapshot(r),
                "created_at": r.created_at.isoformat(),
                "created_by": r.created_by,
                "created_by_name": (
                    names.get(r.created_by, {}).get("display_name") if r.created_by else None
                ),
                "created_by_email": (
                    names.get(r.created_by, {}).get("email") if r.created_by else None
                ),
            }
            for r in rows
        ]
    }


class _RollbackBody(BaseModel):
    version: int


@router.post("/{key}/rollback", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def rollback(
    request: Request, key: str, payload: _RollbackBody, db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    # 되돌리기도 저장이다 — 옛 판을 고르는 것만으로 점검 모드가 다시 켜질 수 있다
    # (`app/settings/service.py::rollback_setting` 이 `apply_setting` 을 그대로 부른다).
    _guard_scope(request, db, principal)
    _guard_system_admin_key(request, key)
    _guard_dedicated_key(key)
    version = payload.version
    result = rollback_setting(
        db, request.app.state.settings_cache, key=key, version=version,
        updated_by=request.state.user.id, now=request.app.state.clock.now(),
    )
    record_audit_from_request(
        request, db, action="setting.rollback", object_type=OBJECT_TYPE,
        object_id=key, before={"value": result["before"]},
        after={"value": result["after"], "rolled_back_to": version},
    )
    return result
