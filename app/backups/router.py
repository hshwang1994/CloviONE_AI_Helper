"""Backup management API (spec §14.6, §23.7).

Backups and verification: system_admin (spec §14.6 — Restore는 system_admin).
Reading status: operator+. Actual restore is intentionally NOT an API action —
it is script-only (deploy/install.sh rollback); this returns guidance.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backups.models import (
    FILE_REMOVED,
    STATUS_FAILED,
    STATUS_RUNNING,
    Backup,
    RestoreRehearsal,
)
from app.backups.policy import scope_manifest
from app.backups.service import (
    announce_backup_failure,
    apply_retention,
    backup_schedule_config,
    backup_view,
    backup_warnings,
    discard_file,
    dump_path,
    is_set,
    last_successful_backup,
    mark_downloaded,
    rehearsal_view,
    retention_from_config,
    run_backup,
    verify_existing,
)
from app.core import people, product
from app.core.audit import record_audit_from_request
from app.authz.permissions import BACKUP_EXECUTE, BACKUP_READ
from app.core.deps import get_db, require_csrf, require_permission
from app.core.errors import ConflictError, NotFoundError

router = APIRouter(
    prefix="/api/admin/backups",
    tags=["admin-backups"],
    dependencies=[Depends(require_csrf)],
)



@router.get("", dependencies=[Depends(require_permission(BACKUP_READ))])
def list_backups(request: Request, db: Session = Depends(get_db)):
    # UA-18: 오래 running으로 멈춘 행 정리는 이제 순수 읽기인 이 GET이 아니라
    # worker_main.py의 10분 백업 틱이 한다 — "화면을 열 때만 청소되고 require_csrf가
    # 안전 메서드로 통과시켜 CSRF에도 무방비"였던 write-in-GET을 없앴다(그 자리에
    # 있던 reap_stuck_running(db, now=...) 호출 제거, 정리 자체는 그대로 계속 돈다).
    rows = (
        db.execute(select(Backup).order_by(Backup.created_at.desc()).limit(50))
        .scalars()
        .all()
    )
    # 실행자 이름은 **한 번의 질의로** — 행마다 조회하면 이 목록이 N+1 이 된다.
    names = people.name_map(db, [r.created_by for r in rows])
    return {"items": [backup_view(r, names) for r in rows]}


@router.post("", status_code=201, dependencies=[Depends(require_permission(BACKUP_EXECUTE))])
def create_backup(request: Request, db: Session = Depends(get_db)):
    now = request.app.state.clock.now()
    row = run_backup(
        db, request.app.state.settings, created_by=request.state.user.id, now=now
    )
    # FN-09 — run_backup은 실패를 삼키고 행 상태만 바꾼다(run_scheduled_backup과 같은 이유,
    # backups/service.py 주석 참고). 예약 경로는 이미 실패를 알리는데 수동 '지금 백업' 경로는
    # 여기서 그 상태를 한 번도 확인한 적이 없었다 — 누른 사람은 응답으로 바로 알지만, 다른
    # 관리자들은 다음 예약 백업이 실패할 때까지 전혀 모른다.
    if row.status == STATUS_FAILED:
        announce_backup_failure(
            db, reason=row.error_message or "원인이 기록되지 않았습니다.",
            now=now, title="수동 백업이 실패했습니다",
        )
    # 예약 백업(run_scheduled_backup)은 backup_schedule 을 읽어 보존을 정하는데, 여기서
    # 인자 없이 apply_retention(db) 를 부르면 하드코딩된 기본값이 적용돼 관리자가 설정
    # 화면에서 좁힌 값이 수동 '지금 백업'에는 지켜지지 않았다. 뽑는 자리는 하나다
    # (service.retention_from_config).
    config = backup_schedule_config(getattr(request.app.state, "settings_cache", None))
    apply_retention(db, now=now, **retention_from_config(config))
    record_audit_from_request(
        request, db, action="backup.create", object_type="backup", object_id=row.id,
        after={"status": row.status, "path": row.path},
    )
    return {"backup": backup_view(row)}


# 정적 경로는 `/{backup_id}/...` **앞에** 둔다 — 아래 verify 라우트가 먼저 등록돼 있으면
# `/rehearsals` 가 backup_id 로 해석될 여지가 생긴다(경로 모양이 달라 지금은 충돌하지
# 않지만, 규칙을 지켜 두면 나중에 세그먼트 하나를 더할 때 사고가 안 난다).
@router.get("/rehearsals", dependencies=[Depends(require_permission(BACKUP_READ))])
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
        "command": "python scripts/restore_rehearsal.py --record",
        "note": (
            "복구 리허설은 앱을 한 번 더 띄워 실제 읽기 경로까지 확인하므로 워커가 아니라 "
            "스크립트로 돌립니다. --record 를 붙이면 결과가 이 목록에 남습니다. "
            "리허설은 임시 데이터베이스에만 복원하므로 운영 데이터를 건드리지 않습니다."
        ),
    }


@router.get("/schedule", dependencies=[Depends(require_permission(BACKUP_READ))])
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
        # 무엇이 담기고 무엇이 안 담기는가. 백업을 만들기 **전에** 읽을 수 있어야 한다 —
        # 복원한 뒤 「검색이 비어 있는데 정상인가」를 묻게 되는 것이 그 다음으로 나쁘다.
        "scope": scope_manifest(),
        # 지금 이 설치에서 백업을 믿을 수 없게 만드는 것들(같은 장치 · 백업 저장소 없음).
        "warnings": backup_warnings(db),
    }


@router.post("/{backup_id}/verify", dependencies=[Depends(require_permission(BACKUP_EXECUTE))])
def verify(request: Request, backup_id: str, db: Session = Depends(get_db)):
    row = db.get(Backup, backup_id)
    if row is None:
        raise NotFoundError("백업을 찾을 수 없습니다.")
    # UA-19: reap_stuck_running()의 문서화된 계약("유일한 행 액션인 '검증'도 running을
    # 제외한다")이 여기서는 지켜지지 않았다 — 프런트는 이미 running 행에서 검증 버튼을
    # 숨기지만(registry/platform.js), 그건 힌트일 뿐 서버가 독립적으로 다시 확인해야 하는
    # 경계다. running 상태는 파일이 아직 쓰이는 중일 수 있어, 그 파일을 체크섬 검증하면
    # 우연히 그 순간의 불완전한 파일만 보고 **진행 중인 정상 백업을 failed로 격하시킬 수
    # 있다**(verify_existing이 실패 시 status를 failed로 낮춘다).
    if row.status == STATUS_RUNNING:
        raise ConflictError("아직 진행 중인 백업입니다. 완료된 뒤 다시 시도하세요.")
    result = verify_existing(
        db, row, now=request.app.state.clock.now(), settings=request.app.state.settings
    )
    record_audit_from_request(
        request, db, action="backup.verify", object_type="backup", object_id=row.id,
        after=result,
    )
    return {"backup": backup_view(row), "verify": result}


@router.get(
    "/{backup_id}/download", dependencies=[Depends(require_permission(BACKUP_EXECUTE))]
)
def download(request: Request, backup_id: str, db: Session = Depends(get_db)):
    """백업 덤프를 내려받는다. **`BACKUP_EXECUTE` 다** — 읽기 권한이 아니다.

    이 파일은 데이터베이스 전체다. 목록을 볼 수 있는 역할(operator 포함)이 그것을 받아
    갈 수 있으면 「백업 목록 조회」 권한이 사실상 「전체 데이터 반출」이 된다. 그래서
    실행 권한과 같은 칸에 둔다.

    세트에서는 **덤프 하나만** 내보낸다. 매니페스트는 `GET /api/admin/backups` 가 이미
    행에 실어 보내므로, 받는 쪽이 tar 를 풀 이유를 만들지 않는다.
    """
    row = db.get(Backup, backup_id)
    if row is None:
        raise NotFoundError("백업을 찾을 수 없습니다.")
    if row.status == STATUS_RUNNING:
        raise ConflictError("아직 진행 중인 백업입니다. 완료된 뒤 다시 시도하세요.")
    if row.file_state == FILE_REMOVED:
        raise ConflictError("이 백업 파일은 서버에서 이미 삭제했습니다.")
    target = dump_path(row.path)
    if not target.is_file():
        raise NotFoundError("백업 파일이 서버에 없습니다.")
    now = request.app.state.clock.now()
    # 받아 간 사실만 적는다. **이 값 때문에 서버가 파일을 지우지 않는다**(D-204).
    mark_downloaded(db, row, now=now)
    record_audit_from_request(
        request, db, action="backup.download", object_type="backup", object_id=row.id,
        after={"path": row.path},
    )
    # 파일 이름은 세트 이름을 따른다 — 받는 사람의 다운로드 폴더에서 `database.dump` 가
    # 여럿 쌓이면 어느 것이 언제 것인지 알 수 없다.
    name = Path(row.path).name
    filename = f"{name}.dump" if is_set(row.path) else name
    return FileResponse(
        target,
        media_type="application/octet-stream",
        filename=filename,
        headers={"Cache-Control": "no-store"},
    )


@router.post(
    "/{backup_id}/discard-file",
    dependencies=[Depends(require_permission(BACKUP_EXECUTE))],
)
def discard(request: Request, backup_id: str, db: Session = Depends(get_db)):
    """내려받은 뒤 **사람이 지우기로 답했을 때** 서버 파일을 지운다 (D-204).

    자동으로 하지 않는 이유는 하나다: 브라우저가 받다 만 것과 다 받은 것을 서버는
    구별하지 못한다. 다 받았다고 답할 수 있는 것은 사람뿐이다.

    행은 남긴다 — 「그때 백업을 만들어 받아 갔다」는 사실은 감사 로그와 짝을 이룬다.
    """
    row = db.get(Backup, backup_id)
    if row is None:
        raise NotFoundError("백업을 찾을 수 없습니다.")
    if row.status == STATUS_RUNNING:
        raise ConflictError("아직 진행 중인 백업입니다. 완료된 뒤 다시 시도하세요.")
    if row.file_state == FILE_REMOVED:
        raise ConflictError("이미 서버에서 삭제한 백업입니다.")
    now = request.app.state.clock.now()
    result = discard_file(db, row, now=now)
    record_audit_from_request(
        request, db, action="backup.discard_file", object_type="backup", object_id=row.id,
        after={"path": row.path, **result},
    )
    return {"backup": backup_view(row), "removed": result}


@router.get("/restore-instructions", dependencies=[Depends(require_permission(BACKUP_EXECUTE))])
def restore_instructions():
    """Spec §14.6: 실제 Restore는 스크립트로만. 추가 확인 + Snapshot 필요.

    **두 가지 되돌리기가 있고 입력이 서로 다르다.** 그 사실을 여기서 분명히 적지 않으면
    목록의 경로를 rollback 에 넣어 실패하고, 그 실패는 되돌려야 하는 날에 일어난다.

      * **데이터를 되돌린다** — 이 화면의 백업 세트(`backup-<타임스탬프>/`)로 `pg_restore`.
      * **배포를 되돌린다** — `install.sh rollback` 이고 입력은 업그레이드 스냅숏
        디렉터리(DB 덤프 + `app.tar.gz` + `SHA256SUMS`)다. **이 목록의 세트가 아니다.**

    절차는 D-204 가 정한 순서 그대로다: 유지보수 모드 → 복원 → PG 검증 → 파일 검증 →
    관계 검증 → 필요한 재색인 → 앱 검증 → 서비스 개방. 재색인이 **절차에 들어 있는 이유**는
    백업이 파생 데이터를 일부러 안 담기 때문이다(D-270) — 복원 직후 검색이 비어 있는 것은
    사고가 아니라 예정된 상태이고, 그 사실을 모르면 정상 복원을 장애로 신고하게 된다.

    **미리 해 보는 자리가 따로 있다**: `scripts/restore_rehearsal.py` 는 임시 데이터베이스에만
    복원하므로 운영 데이터를 건드리지 않는다. 사고 당일에 이 절차를 처음 밟지 않으려면
    그것을 정기적으로 돌린다.
    """
    return {
        "note": (
            "실제 복원은 웹에서 수행하지 않습니다. 서버에서 아래 순서대로 진행하세요. "
            "미리 시험해 보려면 복구 리허설을 쓰세요. 임시 데이터베이스에만 복원하므로 "
            "운영 데이터를 건드리지 않습니다."
        ),
        "web_snapshot_note": (
            "이 목록의 백업은 세트 디렉터리입니다(데이터베이스 덤프 + manifest.json + "
            "SHA256SUMS). 파일을 복사하는 방식으로는 되돌릴 수 없습니다. PostgreSQL 은 "
            "파일 하나가 데이터베이스가 아닙니다. 되돌리려면 서비스를 멈춘 뒤 pg_restore "
            "로 복원해야 합니다."
        ),
        "rollback_input": (
            "배포를 되돌리는 것은 별개입니다. install.sh rollback 의 <BACKUP_DIR>는 "
            f"업그레이드 스냅숏 디렉터리({product.BACKUP_DIR}/<타임스탬프>/, DB 덤프 + "
            "app.tar.gz + SHA256SUMS 포함)여야 합니다. 위 목록의 세트 경로는 넣지 마세요."
        ),
        "scope_note": (
            "복원 직후 검색과 AI 색인이 비어 있는 것은 정상입니다. 백업은 다시 만들 수 "
            "있는 데이터를 일부러 담지 않습니다. 색인 레인과 검색 색인 갱신이 원본에서 "
            "다시 채웁니다."
        ),
        "rehearsal_command": "python scripts/restore_rehearsal.py --record",
        "steps": [
            "1) 유지보수 모드를 켜고 진행 중인 작업이 없는지 확인합니다.",
            "2) 지금 상태를 백업으로 먼저 남깁니다. 되돌린 뒤에 되돌아올 지점입니다.",
            "3) 세트의 SHA256SUMS 를 확인합니다: cd <세트> && sha256sum -c SHA256SUMS",
            "4) manifest.json 의 스키마 판이 지금 코드와 같은지 확인합니다.",
            "5) 서비스를 멈추고 pg_restore --clean --if-exists 로 database.dump 를 "
            "복원합니다.",
            "6) 파일과 관계를 확인합니다. 업로드 파일은 백업 저장소에서 되돌립니다.",
            "7) 서비스를 올리고 /healthz, /readyz 와 실제 화면 몇 개를 확인합니다.",
            "8) 색인이 다시 도는지 확인한 뒤 유지보수 모드를 끕니다.",
        ],
    }
