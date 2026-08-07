"""Backup service (spec §14.6, §6). Restore is documented/script-only —
this service performs backups + verification, never an in-process restore of
live data (spec §14.6: 실제 Restore는 system_admin, 별도 확인)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backups.models import (
    STATUS_FAILED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    STATUS_VERIFIED,
    Backup,
)
from app.backups.sqlite_backup import backup_database, restore_test, verify_backup
from app.core.config import Settings

logger = logging.getLogger("app.backups")

# verify_backup()/restore_test() reason codes → 사용자 화면에 그대로 노출하던
# "database_error: <raw sqlite3 exception text>" 같은 기술 원문을 한국어 안내로
# 바꾼다. 원문은 버리지 않고 journalctl(logger)로만 남긴다 — 화면엔 조치 가능한
# 안내를, 서버 로그엔 원인 추적용 상세를 둔다.
_REASON_KO = {
    "file_missing": "백업 파일을 찾을 수 없습니다. 삭제되었거나 이동되었을 수 있습니다.",
    "checksum_mismatch": "백업 파일이 손상되었습니다(체크섬 불일치).",
}


def _friendly_verify_reason(reason: str | None) -> str:
    if not reason:
        return "알 수 없는 오류로 검증에 실패했습니다."
    if reason in _REASON_KO:
        return _REASON_KO[reason]
    if reason.startswith("database_error"):
        return "백업 파일을 열 수 없습니다(파일 손상 가능성)."
    if reason.startswith("integrity_check"):
        return "백업 파일의 무결성 검사에 실패했습니다(손상 가능성)."
    return "백업 검증에 실패했습니다."


def _friendly_backup_failure(exc: Exception) -> str:
    return (
        "백업 생성 중 오류가 발생했습니다. 디스크 용량/권한을 확인하거나 "
        "문제가 계속되면 관리자에게 문의하세요."
    )


def backup_view(row: Backup, names: dict | None = None) -> dict:
    """`names` 는 {user_id: {display_name, email}} (app/core/people.py::name_map).

    실행자를 UUID 로만 주면 "이 백업을 누가 돌렸나" 를 화면에서 알 수 없었다. 이름을
    **더하는** 것이지 id 를 감추는 것이 아니다 — id 는 감사 로그 대조에 그대로 쓴다.
    `names` 를 안 주면 이름은 None 이다(모르는 것을 지어내지 않는다).
    """
    creator = (names or {}).get(row.created_by) or {}
    return {
        "id": row.id,
        "backup_type": row.backup_type,
        "path": row.path,
        "status": row.status,
        "size_bytes": row.size_bytes,
        "checksum": row.checksum,
        "created_by": row.created_by,
        "created_by_name": creator.get("display_name"),
        "created_by_email": creator.get("email"),
        "created_at": row.created_at.isoformat(),
        "verified_at": row.verified_at.isoformat() if row.verified_at else None,
        "error_message": row.error_message,
    }


def run_backup(
    db: Session, settings: Settings, *, created_by: str | None, now: datetime
) -> Backup:
    # Include microseconds so two backups in the same second get distinct files.
    # (Same-second collisions previously aliased two DB rows to one file, letting
    # retention unlink a still-referenced backup.)
    stamp = now.strftime("%Y%m%d_%H%M%S_%f")
    dest = Path(settings.data_dir) / "exports" / f"web-{stamp}.sqlite3"
    row = Backup(backup_type="sqlite", path=str(dest), status="running", created_by=created_by,
                 created_at=now)
    db.add(row)
    db.flush()
    try:
        result = backup_database(settings.database_url, dest)
        row.size_bytes = result["size_bytes"]
        row.checksum = result["checksum"]
        row.status = STATUS_SUCCEEDED
        # Immediate temp-restore verification (spec §6.3).
        verify = restore_test(dest)
        if verify["ok"]:
            row.status = STATUS_VERIFIED
            row.verified_at = now
        else:
            logger.warning("backup restore-verify failed: %s (%s)", dest, verify.get("reason"))
            row.status = STATUS_FAILED
            row.error_message = _friendly_verify_reason(verify.get("reason"))
    except Exception as exc:
        logger.exception("backup creation failed: %s", dest)
        row.status = STATUS_FAILED
        row.error_message = _friendly_backup_failure(exc)
    db.flush()
    return row


def verify_existing(db: Session, row: Backup, *, now: datetime) -> dict:
    result = verify_backup(Path(row.path), row.checksum)
    if result["ok"]:
        row.verified_at = now
        if row.status == STATUS_SUCCEEDED:
            row.status = STATUS_VERIFIED
    else:
        # 재검증 실패는 상태를 failed로 낮춘다 — 이전에 verified였어도 이제 못 믿는다
        # (안 그러면 손상된 백업이 계속 '마지막 정상 백업'으로 잡힌다).
        logger.warning("backup re-verify failed: %s (%s)", row.path, result.get("reason"))
        row.status = STATUS_FAILED
        row.error_message = _friendly_verify_reason(result.get("reason"))
    db.flush()
    return result


# 정상적인 백업은 수 초~수십 초 안에 running에서 succeeded/verified/failed로 넘어간다
# (run_backup의 try/except가 항상 끝에서 상태를 확정한다). 그 try/except 진입 전에
# 프로세스가 죽으면(OOM kill, systemd 재시작 등) 행만 running으로 영원히 멈춘다.
STUCK_RUNNING_MINUTES = 60


def reap_stuck_running(
    db: Session, *, now: datetime, stale_after_minutes: int = STUCK_RUNNING_MINUTES
) -> int:
    """오래 running 상태로 멈춘 백업을 failed로 정리한다.

    running 행은 apply_retention()이 절대 건드리지 않고(파일이 쓰이는 중일 수 있어서),
    유일한 행 액션인 '검증'도 running을 제외한다 — 프로세스가 죽어 상태 확정 없이
    멈춘 행은 목록에 영원히 남아 어떤 조작도 할 수 없는 상태가 된다. 일정 시간이
    지난 running 행은 죽은 것으로 보고 failed로 정리해, 최소한 재검증/재백업으로
    이어질 수 있게 한다.
    """
    threshold = now - timedelta(minutes=stale_after_minutes)
    stuck = db.execute(
        select(Backup).where(Backup.status == STATUS_RUNNING, Backup.created_at < threshold)
    ).scalars().all()
    for row in stuck:
        row.status = STATUS_FAILED
        row.error_message = "백업 작업이 예기치 않게 중단된 것으로 보입니다(진행 중 상태로 멈춤)."
    if stuck:
        db.flush()
    return len(stuck)


def last_successful_backup(db: Session) -> Backup | None:
    return db.execute(
        select(Backup)
        .where(Backup.status.in_([STATUS_SUCCEEDED, STATUS_VERIFIED]))
        .order_by(Backup.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def apply_retention(db: Session, *, keep: int = 14) -> int:
    """Keep the most recent N GOOD (succeeded/verified) backups plus prune failed
    ones — never delete a good backup just because newer attempts failed."""
    good = db.execute(
        select(Backup)
        .where(Backup.status.in_([STATUS_SUCCEEDED, STATUS_VERIFIED]))
        .order_by(Backup.created_at.desc())
    ).scalars().all()
    keep_ids = {row.id for row in good[:keep]}

    all_rows = db.execute(select(Backup).order_by(Backup.created_at.desc())).scalars().all()
    # 진행 중(running)인 백업은 건드리지 않는다 — 파일이 쓰이는 중일 수 있다.
    # 가장 최근 실패 1건은 남긴다(장애 추적용).
    latest_failed_id = next((r.id for r in all_rows if r.status == STATUS_FAILED), None)
    removed = 0
    for row in all_rows:
        if row.id in keep_ids:
            continue
        if row.status == STATUS_RUNNING:
            continue
        if row.id == latest_failed_id:
            continue
        # Delete old failed backups and good backups beyond the keep window.
        try:
            Path(row.path).unlink(missing_ok=True)
        except OSError:
            pass
        db.delete(row)
        removed += 1
    db.flush()
    return removed


# ── 자동 백업 스케줄 + 복구 리허설 (0033, PLAN Phase 6) ───────────────────────

DEFAULT_BACKUP_SCHEDULE = {
    "enabled": False,
    "cron": "0 3 * * *",
    "timezone": "Asia/Seoul",
    "keep": 14,
}


def backup_schedule_config(settings_cache) -> dict:
    """설정에서 백업 스케줄을 읽는다. 값이 없거나 모양이 이상하면 기본값."""
    raw = None
    if settings_cache is not None:
        raw = settings_cache.current_value("backup_schedule")
    config = dict(DEFAULT_BACKUP_SCHEDULE)
    if isinstance(raw, dict):
        for key in config:
            if key in raw:
                config[key] = raw[key]
    return config


def due_for_scheduled_backup(db, config: dict, *, now) -> bool:
    """지금 예약 백업을 돌려야 하는가.

    **상태를 따로 저장하지 않는다.** '마지막 실행 시각' 컬럼을 두면 그 값과 실제 백업 목록이
    어긋날 수 있고(수동 백업, 파일 삭제), 그러면 화면이 말하는 것과 디스크에 있는 것이
    달라진다. 대신 질문을 뒤집는다: **직전 예정 시각 이후에 성공한 백업이 있는가.**
    없으면 돌린다. 멱등이고, 워커가 재시작해도 두 번 돌지 않는다.
    """
    if not config.get("enabled"):
        return False
    from app.schedules import cron

    try:
        # cronsim 은 '다음'만 준다. 직전 예정 시각은 하루 전부터 전진하며 now 이하 중
        # 가장 늦은 것을 취한다(간격이 하루보다 긴 cron 은 백업 주기로 쓰지 않는다).
        cursor = now - timedelta(days=1, seconds=1)
        previous = None
        for _ in range(2000):
            nxt = cron.next_after(config["cron"], config.get("timezone", "Asia/Seoul"), cursor)
            if nxt > now:
                break
            previous = nxt
            cursor = nxt
    except Exception:
        logger.exception("backup_schedule cron 해석 실패: 예약 백업을 건너뛴다")
        return False
    if previous is None:
        return False
    last = last_successful_backup(db)
    return last is None or last.created_at < previous


def _announce_backup_failure(db, *, reason: str, now) -> None:
    """백업 실패를 **사람에게** 알린다 (9-9 P4, §E-6).

    이 함수가 생기기 전에는 예약 백업 실패가 `logger.exception` 한 줄로 끝났다.
    journalctl 을 매일 보는 사람은 없다 - 그래서 백업이 멈춘 사실은 **복원이 필요해진 날**에
    처음 알게 됐다. 그날 알아서 할 수 있는 일은 없다.

    ## 메일과 화면 알림 둘 다 보낸다

    메일은 이미 나가고 있었지만 앱 안에서는 여전히 조용했다(N2). 둘은 서로를 대신하지
    못한다: 메일함을 안 보는 날이 있고, 반대로 앱에 안 들어오는 날도 있다. 백업 실패는
    "며칠 뒤에 알아도 되는" 부류가 아니라 **오늘 알아야** 손쓸 수 있는 부류다.

    두 갈래를 각자 try 로 감싼다. 한쪽이 터졌다고 다른 쪽까지 못 나가면, 알리는 길을
    둘로 늘린 것이 오히려 하나였을 때보다 약해진다.

    메일/알림 실패가 본 작업을 막지 않는다는 규칙은 여기서도 유효하다. 다만 조용히 삼키지
    않는다: 못 보낸 사실은 `mail_deliveries` 행으로 남고(status='unconfigured'), 여기서
    예외가 나도 로그에 남긴 뒤 넘어간다.
    """
    try:
        from app.mail.renderers import KIND_BACKUP_FAILED
        from app.mail.service import queue_mail_to_admins

        queue_mail_to_admins(
            db,
            kind=KIND_BACKUP_FAILED,
            subject="[ClovirAssist] 예약 백업이 실패했습니다",
            params={"reason": reason[:500], "at": now.isoformat()},
            now=now,
        )
    except Exception:
        logger.exception("백업 실패 알림 메일을 큐에 넣지 못했다 (백업 기록은 남는다)")

    try:
        from app.notifications.service import notify_admins

        # 딥링크를 붙이지 않는다: 실패한 백업은 행이 남지만(`backup`), 그 화면은 목록이라
        # 관리 콘솔 쪽 표(registry.js)가 이미 `backup` → 백업 화면으로 보낸다.
        notify_admins(
            db, type_="backup_failed",
            title="예약 백업이 실패했습니다",
            body=reason[:200],
            related=("backup", None), now=now,
        )
    except Exception:
        logger.exception("백업 실패 화면 알림을 남기지 못했다 (백업 기록은 남는다)")


def run_scheduled_backup(db, settings, config: dict, *, now):
    """예약 백업 1회. 예외를 밖으로 내보내지 않는다(워커 루프를 죽이지 않는다).

    **실패를 삼키지 않는다**(§E-6). run_backup 은 예외를 잡아 행 상태만 failed 로 바꾸므로
    여기서 예외가 안 보이는 것이 정상이다 - 그래서 예외가 아니라 **행 상태**를 본다.
    """
    try:
        row = run_backup(db, settings, created_by=None, now=now)
        keep = int(config.get("keep", 14) or 14)
        apply_retention(db, keep=keep)
        if row is not None and row.status == STATUS_FAILED:
            _announce_backup_failure(
                db,
                reason=row.error_message or "원인이 기록되지 않았습니다.",
                now=now,
            )
        return row
    except Exception as exc:
        logger.exception("예약 백업 실패")
        _announce_backup_failure(db, reason=f"{type(exc).__name__}: {exc}", now=now)
        return None


def rehearsal_view(row) -> dict:
    import json as _json

    return {
        "id": row.id,
        "source_label": row.source_label,
        "started_at": row.started_at.isoformat(),
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "ok": row.ok,
        "failures": _json.loads(row.failures_json) if row.failures_json else [],
        "summary": _json.loads(row.summary_json) if row.summary_json else {},
        "created_at": row.created_at.isoformat(),
    }
