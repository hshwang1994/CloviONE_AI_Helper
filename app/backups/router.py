"""Backup management API (spec §14.6, §23.7).

Backups and verification: system_admin (spec §14.6 — Restore는 system_admin).
Reading status: operator+. Actual restore is intentionally NOT an API action —
it is script-only (rollback-clovirone-web-assistant.sh); this returns guidance.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backups.models import Backup
from app.backups.service import (
    apply_retention,
    backup_view,
    reap_stuck_running,
    run_backup,
    verify_existing,
)
from app.core.audit import record_audit_from_request
from app.core.authz import CONSOLE_READ_ROLES, SYSTEM_ADMIN_ONLY
from app.core.deps import get_db, require_csrf, require_roles
from app.core.errors import NotFoundError

router = APIRouter(
    prefix="/api/admin/backups",
    tags=["admin-backups"],
    dependencies=[Depends(require_csrf)],
)



@router.get("", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def list_backups(request: Request, db: Session = Depends(get_db)):
    # 목록을 열 때마다 오래 running으로 멈춘 행을 정리한다 — 그래야 프로세스가 죽어
    # 상태 확정 없이 멈춘 백업이 영원히 '실행 중'으로 보이며 아무 조작도 못 하게
    # 남는 일이 없다(reap_stuck_running 참조).
    reap_stuck_running(db, now=request.app.state.clock.now())
    rows = (
        db.execute(select(Backup).order_by(Backup.created_at.desc()).limit(50))
        .scalars()
        .all()
    )
    return {"items": [backup_view(r) for r in rows]}


@router.post("", status_code=201, dependencies=[Depends(require_roles(*SYSTEM_ADMIN_ONLY))])
def create_backup(request: Request, db: Session = Depends(get_db)):
    now = request.app.state.clock.now()
    row = run_backup(
        db, request.app.state.settings, created_by=request.state.user.id, now=now
    )
    apply_retention(db)
    record_audit_from_request(
        request, db, action="backup.create", object_type="backup", object_id=row.id,
        after={"status": row.status, "path": row.path},
    )
    return {"backup": backup_view(row)}


@router.post("/{backup_id}/verify", dependencies=[Depends(require_roles(*SYSTEM_ADMIN_ONLY))])
def verify(request: Request, backup_id: str, db: Session = Depends(get_db)):
    row = db.get(Backup, backup_id)
    if row is None:
        raise NotFoundError("백업을 찾을 수 없습니다.")
    result = verify_existing(db, row, now=request.app.state.clock.now())
    record_audit_from_request(
        request, db, action="backup.verify", object_type="backup", object_id=row.id,
        after=result,
    )
    return {"backup": backup_view(row), "verify": result}


@router.get("/restore-instructions", dependencies=[Depends(require_roles(*SYSTEM_ADMIN_ONLY))])
def restore_instructions():
    """Spec §14.6: 실제 Restore는 스크립트로만. 추가 확인 + Snapshot 필요.

    주의: 이 화면이 나열하는 백업(웹 콘솔에서 '백업 실행'으로 만든 것)은 단일 파일
    스냅샷(var/exports/web-*.sqlite3)이라 rollback 스크립트의 입력이 아니다. rollback은
    cron/업그레이드 백업이 만든 '디렉터리'(web.sqlite3 + app.tar.gz + SHA256SUMS)를
    요구한다. 두 저장소가 다르다는 사실을 안내에 분명히 적어, 목록의 파일 경로를 그대로
    rollback에 넣어 실패하는 일을 막는다.
    """
    return {
        "note": (
            "실제 복원은 웹에서 수행하지 않습니다. 아래 스크립트를 서버에서 실행하세요. "
            "이 화면의 목록은 웹 콘솔에서 만든 단일 파일 DB 스냅샷"
            "(var/exports/web-*.sqlite3)일 뿐이며, 아래 rollback 스크립트의 입력이 아닙니다."
        ),
        "web_snapshot_note": (
            "웹 콘솔 백업은 DB만 담은 단일 .sqlite3 파일입니다. 이 파일로 되돌리려면 "
            "서비스를 멈춘 뒤 해당 파일을 운영 DB 경로로 직접 복사해야 합니다"
            "(rollback 스크립트로는 복원되지 않습니다)."
        ),
        "rollback_input": (
            "rollback 스크립트의 <BACKUP_DIR>는 cron·업그레이드 백업이 만든 디렉터리"
            "(/var/backups/clovirone-web-assistant/<타임스탬프>/, web.sqlite3 + app.tar.gz "
            "+ SHA256SUMS 포함)여야 합니다. 위 목록의 단일 파일 경로는 넣지 마세요."
        ),
        "steps": [
            "1) 유지보수 모드로 전환하고 진행 중 Job이 없는지 확인",
            "2) 현재 상태를 별도 백업(스냅샷)으로 보존",
            "3) sudo /opt/clovirone-web-assistant/scripts/rollback-clovirone-web-assistant.sh "
            "/var/backups/clovirone-web-assistant/<타임스탬프>",
            "4) systemctl 상태 및 /healthz, /readyz 확인 후 유지보수 모드 해제",
        ],
    }
