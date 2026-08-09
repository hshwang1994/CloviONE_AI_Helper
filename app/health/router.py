"""Liveness, readiness, and admin dashboard/diagnostics (spec §23.1, §14.1, §14.7)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.authz import (
    CONSOLE_READ_ROLES,
    CONSOLE_WRITE_ROLES,
    SENSITIVE_READ_ROLES,
)
from app.core.deps import get_db, require_roles
from app.health.service import build_dashboard, build_diagnostic_bundle

logger = logging.getLogger("app.health")

router = APIRouter(tags=["health"])



@router.get("/healthz")
def healthz(request: Request) -> dict:
    # ticket_source(app/core/config.py:136-164 설명 참고)는 저장소 배선을 바꾸는 운영
    # 킬 스위치인데 지금까지 SSH로 web.env를 직접 읽는 것 말고는 현재 모드를 확인할 방법이
    # 없었다. secret이 아니라 'notion'/'notion_cache'/'native' 중 하나를 가리키는 운영
    # 모드 문자열일 뿐이라(§2 불변 규칙 3의 secret_ref 대상이 아님) 이 인증 없는 liveness
    # 엔드포인트에 얹어도 안전하다 — curl 한 번으로 지금 어느 모드로 떠 있는지 알 수 있다.
    return {
        "status": "ok",
        "ticket_source": request.app.state.settings.ticket_source,
    }


@router.get("/readyz")
def readyz(request: Request):
    try:
        session_factory = request.app.state.session_factory
        with session_factory() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("readiness check failed")
        return JSONResponse(status_code=503, content={"status": "unready"})
    return {"status": "ready"}


@router.get(
    "/api/admin/dashboard", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))]
)
def dashboard(request: Request, db: Session = Depends(get_db)):
    # operator는 대시보드는 보지만 감사 로그 열람 권한이 없다 — 민감한 '최근 주요 변경'
    # 슬라이스를 감사 열람 역할(admin/system_admin/auditor)에만 내린다.
    role = getattr(getattr(request.state, "user", None), "role", None)
    include_critical_audit = role in SENSITIVE_READ_ROLES
    return build_dashboard(
        db,
        request.app.state.settings,
        request.app.state.clock.now(),
        include_critical_audit=include_critical_audit,
        cache=request.app.state.settings_cache,
    )


@router.get(
    "/api/admin/diagnostics/bundle",
    dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))],
)
def diagnostics_bundle(request: Request, db: Session = Depends(get_db)):
    return build_diagnostic_bundle(
        db,
        request.app.state.settings,
        request.app.state.clock.now(),
        cache=request.app.state.settings_cache,
    )
