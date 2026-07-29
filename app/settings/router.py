"""Settings + Maintenance API (spec §14.4, §14.5)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
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

READ_ROLES = ("operator", "admin", "system_admin", "auditor")
WRITE_ROLES = ("admin", "system_admin")


class SettingChange(BaseModel):
    value: Any


@router.get("", dependencies=[Depends(require_roles(*READ_ROLES))])
def list_settings(request: Request, db: Session = Depends(get_db)):
    return {"settings": effective_settings(db, request.app.state.settings_cache)}


@router.post("/{key}/dry-run", dependencies=[Depends(require_roles(*WRITE_ROLES))])
def dry_run_setting(key: str, payload: SettingChange):
    return dry_run(key, payload.value)


@router.put("/{key}", dependencies=[Depends(require_roles(*WRITE_ROLES))])
def update_setting(
    request: Request, key: str, payload: SettingChange, db: Session = Depends(get_db)
):
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
    # spec §13.5의 8개 알림 유형 중 'Maintenance 공지'가 여기 하나다 — maintenance_mode가
    # False→True로 실제 켜지는 전이에만 보낸다(끌 때·이미 켜진 값 재저장까지 매번 보내면
    # 관리자가 값을 다시 저장할 때마다 전 사용자가 알림을 또 받는다).
    if key == "maintenance_mode" and result["after"] is True and result["before"] is not True:
        from app.notifications.service import notify_active_users
        from app.settings.service import maintenance_message

        notify_active_users(
            db, type_="maintenance_announcement", title="시스템 점검 안내",
            body=maintenance_message(db, request.app.state.settings_cache),
            now=request.app.state.clock.now(),
        )
    return result


@router.get("/{key}/versions", dependencies=[Depends(require_roles(*READ_ROLES))])
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


@router.post("/{key}/rollback", dependencies=[Depends(require_roles(*WRITE_ROLES))])
def rollback(
    request: Request, key: str, payload: _RollbackBody, db: Session = Depends(get_db),
):
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
