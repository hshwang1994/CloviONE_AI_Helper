"""Liveness, readiness, and admin dashboard/diagnostics (spec §23.1, §14.1, §14.7)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles
from app.health.service import build_dashboard, build_diagnostic_bundle

logger = logging.getLogger("app.health")

router = APIRouter(tags=["health"])

READ_ROLES = ("operator", "admin", "system_admin", "auditor")


@router.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


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
    "/api/admin/dashboard", dependencies=[Depends(require_roles(*READ_ROLES))]
)
def dashboard(request: Request, db: Session = Depends(get_db)):
    # operator는 대시보드는 보지만 감사 로그 열람 권한이 없다 — 민감한 '최근 주요 변경'
    # 슬라이스를 감사 열람 역할(admin/system_admin/auditor)에만 내린다.
    role = getattr(getattr(request.state, "user", None), "role", None)
    include_critical_audit = role in ("admin", "system_admin", "auditor")
    return build_dashboard(
        db,
        request.app.state.settings,
        request.app.state.clock.now(),
        include_critical_audit=include_critical_audit,
        cache=request.app.state.settings_cache,
    )


@router.get(
    "/api/admin/diagnostics/bundle",
    dependencies=[Depends(require_roles("admin", "system_admin"))],
)
def diagnostics_bundle(request: Request, db: Session = Depends(get_db)):
    return build_diagnostic_bundle(
        db,
        request.app.state.settings,
        request.app.state.clock.now(),
        cache=request.app.state.settings_cache,
    )
