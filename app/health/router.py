"""Liveness, readiness, and admin dashboard/diagnostics (spec §23.1, §14.1, §14.7)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.authz import (
    CONSOLE_OPS_ROLES,
    CONSOLE_READ_ROLES,
    SENSITIVE_READ_ROLES,
)
from app.core.deps import get_db, require_roles
from app.core.source_registry import SOURCE_NATIVE
from app.health.service import build_dashboard, build_diagnostic_bundle

logger = logging.getLogger("app.health")

router = APIRouter(tags=["health"])



@router.get("/healthz")
def healthz(request: Request) -> dict:
    # `ticket_source` 는 예전에 저장소 배선을 바꾸는 운영 킬 스위치였고, SSH 로 web.env 를
    # 직접 읽는 것 말고는 지금 어느 모드로 떠 있는지 확인할 방법이 없어서 여기에 실었다.
    # 스위치는 사라졌지만 이 값은 남긴다. 구현이 하나뿐이라는 사실 자체가 운영자가 확인해야
    # 하는 사실이고, 밖에서 이 응답을 지켜보는 감시 도구가 이미 이 키를 읽고 있다. secret 이
    # 아니라 어떤 저장소가 도는지 가리키는 이름일 뿐이라(§2 불변 규칙 3의 secret_ref 대상이
    # 아님) 인증 없는 liveness 엔드포인트에 얹어도 안전하다.
    return {
        "status": "ok",
        "ticket_source": SOURCE_NATIVE,
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
    # OPS-03: 배포 스크립트가 이 엔드포인트를 1회성 게이트로만 curl한다(systemd Restart=에
    # 물려 있지 않다 — OPS-10처럼 재시작 루프를 만들 위험이 없다). 디스크 용량과 별개로
    # uploads 디렉터리 소유권/권한 드리프트(OPS-01 실사고)를 배포 직후 바로 잡아낸다.
    from app.core.uploads import uploads_writable

    if not uploads_writable(request.app.state.settings.data_dir):
        return JSONResponse(
            status_code=503,
            content={"status": "unready", "reason": "uploads_not_writable"},
        )
    # S8: 켜진 운영 저장소에 **지금 쓸 수 있는가**. 위의 `uploads_writable` 과 다른
    # 결함을 잡는다 — 저 검사는 로컬 `data_dir` 만 보므로, NFS/SMB 저장소가 안 붙은
    # 상태를 못 본다. 그 상태에서 뜨면 업로드가 로컬 디스크에 쌓인다(D-199 13번).
    # 저장소가 아직 하나도 없는 설치(설치 중)는 `unready` 가 아니다 — 그때는 Stage 11
    # 이 아직 안 돈 것이고, 그 사실은 설치 로그가 말한다.
    from app.storage.service import storage_health

    try:
        with session_factory() as db:
            health = storage_health(db)
    except Exception:
        logger.exception("storage readiness check failed")
        return JSONResponse(status_code=503, content={"status": "unready", "reason": "storage"})
    if health["providers"] and not health["operational_ok"]:
        return JSONResponse(
            status_code=503,
            content={"status": "unready", "reason": "storage_not_writable"},
        )
    # S9: AI 를 **켜기로 해 놓고** 못 쓰는 상태만 unready 다. 끄고 설치한 것은 정상이고,
    # 생성 Provider 가 없는 것도 정상이다 — 그때 정지하는 것은 요약·분석·문서생성뿐이고
    # 검색·Retrieval 은 그대로 돈다(D-201). 임베딩이 안 되는 것은 다르다: 켜기로 했는데
    # 런타임이나 모델이 없다는 뜻이고, 그 상태로 뜨면 색인이 조용히 벡터 없이 쌓인다.
    #
    # 꺼져 있으면 Gateway 를 만들지도 않는다. 이 엔드포인트는 배포 게이트로 자주 불리는데,
    # AI 를 안 쓰는 설치에서 매번 모델 디렉터리를 stat 할 이유가 없다.
    from app.ai.gateway import registry as ai_registry

    settings = request.app.state.settings
    if ai_registry.resolve_config(settings).enabled:
        try:
            embed = ai_registry.build_gateway(settings).capabilities().embed
        except Exception:
            logger.exception("AI readiness check failed")
            return JSONResponse(status_code=503, content={"status": "unready", "reason": "ai"})
        if not embed.available:
            return JSONResponse(
                status_code=503,
                content={"status": "unready", "reason": f"ai_{embed.status}"},
            )
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
    dependencies=[Depends(require_roles(*CONSOLE_OPS_ROLES))],
)
def diagnostics_bundle(request: Request, db: Session = Depends(get_db)):
    # PA-RC-0026: diagnostics is a read-only health-check bundle (spec §14.7 —
    # masked settings, no secrets, no raw journals), which is exactly what the
    # product's own capability table (app/core/authz.py CAPABILITIES) calls
    # "console.ops" ("헬스체크" is named explicitly) — a role gate stricter
    # than that (CONSOLE_WRITE_ROLES, admin+) contradicted the published RBAC
    # matrix and blocked the on-call operator from the one screen that
    # aggregates the pieces they otherwise have to gather from four separate
    # ones during an incident. Every embedded piece was audited against what
    # operator can already see elsewhere before this gate was widened
    # (docs/DECISIONS.md) — the one gap found (the embedded dashboard's
    # critical-audit slice) is closed by passing role through below rather
    # than by leaving the gate narrow.
    role = getattr(getattr(request.state, "user", None), "role", None)
    return build_diagnostic_bundle(
        db,
        request.app.state.settings,
        request.app.state.clock.now(),
        cache=request.app.state.settings_cache,
        include_critical_audit=role in SENSITIVE_READ_ROLES,
    )
