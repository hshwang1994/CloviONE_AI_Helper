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

from app.backups.models import Backup, RestoreRehearsal
from app.backups.service import (
    apply_retention,
    backup_schedule_config,
    backup_view,
    last_successful_backup,
    reap_stuck_running,
    rehearsal_view,
    run_backup,
    verify_existing,
)
from app.core import people
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
    # 실행자 이름은 **한 번의 질의로** — 행마다 조회하면 이 목록이 N+1 이 된다.
    names = people.name_map(db, [r.created_by for r in rows])
    return {"items": [backup_view(r, names) for r in rows]}


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


# 정적 경로는 `/{backup_id}/...` **앞에** 둔다 — 아래 verify 라우트가 먼저 등록돼 있으면
# `/rehearsals` 가 backup_id 로 해석될 여지가 생긴다(경로 모양이 달라 지금은 충돌하지
# 않지만, 규칙을 지켜 두면 나중에 세그먼트 하나를 더할 때 사고가 안 난다).
@router.get("/rehearsals", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def list_rehearsals(db: Session = Depends(get_db)):
    """복구 리허설 기록 — "마지막으로 복원을 시험한 게 언제인가"에 답한다.

    앱은 리허설을 스스로 돌리지 않는다(app/backups/models.py::RestoreRehearsal 참조).
    그래서 기록이 비어 있으면 **한 번도 안 했다**는 뜻이고, 화면은 그 사실과 함께
    실행 방법을 그대로 보여 준다 — 하지 않은 일을 한 것처럼 꾸미지 않는다.
    """
    rows = (
        db.execute(
            select(RestoreRehearsal)
            .order_by(RestoreRehearsal.started_at.desc())
            .limit(20)
        )
        .scalars()
        .all()
    )
    return {
        "items": [rehearsal_view(r) for r in rows],
        "command": ".venv/Scripts/python.exe scripts/restore_rehearsal.py --record",
        "note": (
            "복구 리허설은 앱을 한 번 더 띄워 실제 읽기 경로까지 확인하므로 워커가 아니라 "
            "스크립트로 돌립니다. --record 를 붙이면 결과가 이 목록에 남습니다."
        ),
    }


@router.get("/schedule", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def get_backup_schedule(request: Request, db: Session = Depends(get_db)):
    """자동 백업 일정 + 최근 성공 백업 + 최근 리허설을 한 화면에.

    셋을 따로 보면 "백업은 돌고 있는데 복원은 한 번도 안 해 봤다"를 알아채지 못한다.
    """
    config = backup_schedule_config(getattr(request.app.state, "settings_cache", None))
    last = last_successful_backup(db)
    rehearsal = (
        db.execute(
            select(RestoreRehearsal).order_by(RestoreRehearsal.started_at.desc()).limit(1)
        )
        .scalars()
        .first()
    )
    return {
        "schedule": config,
        # 설정 화면이 정본이다 — 여기서 고치는 API 를 따로 만들면 값이 두 곳에서 바뀐다.
        "edit_hint": "일정은 관리 콘솔 '설정' 화면의 backup_schedule 에서 바꿉니다.",
        "last_backup": backup_view(last) if last is not None else None,
        "last_rehearsal": rehearsal_view(rehearsal) if rehearsal is not None else None,
    }


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
            "rollback 스크립트의 <BACKUP_DIR>는 cron, 업그레이드 백업이 만든 디렉터리"
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
