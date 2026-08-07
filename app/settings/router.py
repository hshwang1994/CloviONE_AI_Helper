"""Settings + Maintenance API (spec §14.4, §14.5)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.authz import CONSOLE_READ_ROLES, CONSOLE_WRITE_ROLES
from app.core.deps import get_db, require_csrf, require_roles
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


@router.get("", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def list_settings(request: Request, db: Session = Depends(get_db)):
    return {"settings": effective_settings(db, request.app.state.settings_cache)}


@router.post("/{key}/dry-run", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def dry_run_setting(request: Request, key: str, payload: SettingChange):
    _guard_system_admin_key(request, key)
    return dry_run(key, payload.value)


@router.put("/{key}", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def update_setting(
    request: Request, key: str, payload: SettingChange, db: Session = Depends(get_db)
):
    _guard_system_admin_key(request, key)
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
):
    _guard_system_admin_key(request, key)
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
