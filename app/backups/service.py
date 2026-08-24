"""Backup service (spec §14.6, §6) — **백업 세트**를 만들고 검증한다 (S12 · D-204).

살아 있는 데이터를 이 자리에서 되돌리지는 않는다(spec §14.6: 실제 Restore는 system_admin,
별도 확인). 복원이 실제로 되는지는 `scripts/restore_rehearsal.py` 가 별도 프로세스로
증명한다 — 복원본으로 **앱을 띄워** 읽기 경로까지 부르기 때문에 웹 요청 안에서 할 일이
아니다.

## 백업 하나는 파일 하나가 아니라 **디렉터리 하나**다

S2 까지는 `web-<stamp>.dump` 파일 하나였다. S12 가 세트로 바꾼 이유는 **매니페스트**다
(D-204). 스키마 판·범위·체크섬은 백업과 **함께 이동해야** 의미가 있고, 그러려면 덤프
옆에 있어야 한다. 그래서:

    <data_dir>/exports/backup-<stamp>/{database.dump, manifest.json, SHA256SUMS}

옛 `.dump` 파일 행은 그대로 목록에 선다(`is_set()` 이 둘을 가른다). 되돌려야 하는 날에
「이 행은 무엇인가」를 못 읽는 것이 가장 나쁘다.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backups import manifest as manifest_mod
from app.backups import policy
from app.backups.models import (
    FILE_PRESENT,
    FILE_REMOVED,
    STATUS_FAILED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    STATUS_VERIFIED,
    Backup,
)
from app.backups.pg_backup import backup_database, restore_test, verify_backup
from app.core.config import Settings
from app.core.elapsed import format_elapsed_korean
from app.core.models_base import utcnow

logger = logging.getLogger("app.backups")

# verify_backup()/restore_test() reason code → 한국어 안내. 기술 원문(도구 stderr 등)을
# 화면에 그대로 내보내지 않는다 — 원문은 버리지 않고 journalctl(logger)로만 남긴다.
# 화면엔 조치 가능한 안내를, 서버 로그엔 원인 추적용 상세를 둔다.
_REASON_KO = {
    "file_missing": "백업 파일을 찾을 수 없습니다. 삭제되었거나 이동되었을 수 있습니다.",
    "checksum_mismatch": "백업 파일이 손상되었습니다(체크섬 불일치).",
    "archive_empty": "백업 파일에 아무것도 담겨 있지 않습니다. 다시 백업해 주세요.",
    # 세트 단위 검증(S12). 「덤프는 멀쩡한데 세트가 바뀌었다」는 별개의 사고다 —
    # 범위를 말하는 파일이 바뀌면 「무엇이 안 담겼나」의 답이 조용히 달라진다.
    "set_missing": "백업 세트를 찾을 수 없습니다. 삭제되었거나 이동되었을 수 있습니다.",
    "checksums_missing": (
        "백업 세트에 체크섬 파일이 없어 내용을 확인할 수 없습니다. 다시 백업해 주세요."
    ),
    "set_modified": "백업을 만든 뒤에 세트 안의 파일이 바뀌었습니다.",
    "file_removed": "이 백업 파일은 서버에서 삭제했습니다(손상이 아닙니다).",
}

# 부분 검증. **실패가 아니지만 «검증됨» 도 아니다** (D-204).
PARTIAL_VERIFY_PREFIX = "structure_only"


def _friendly_verify_reason(reason: str | None) -> str:
    if not reason:
        return "알 수 없는 오류로 검증에 실패했습니다."
    if reason in _REASON_KO:
        return _REASON_KO[reason]
    if reason.startswith("tool_missing"):
        return (
            "PostgreSQL 백업 도구를 찾을 수 없습니다. 설치 상태와 PG_BIN_DIR 설정을 "
            "확인해 주세요."
        )
    if reason.startswith("archive_unreadable"):
        return "백업 파일을 열 수 없습니다(파일 손상 가능성)."
    if reason.startswith("restore_failed"):
        return "백업 파일이 실제로는 복원되지 않습니다. 이 백업으로 되돌릴 수 없습니다."
    return "백업 검증에 실패했습니다."


def _partial_verify_note(reason: str | None) -> str:
    """구조까지만 확인했을 때 화면에 남길 말.

    **조용히 «검증됨» 이라고 하지 않는다.** 그렇게 하면 정작 복원이 안 되는 백업이
    대시보드에서 초록으로 보이고, 그 사실을 되돌려야 하는 날에 알게 된다(D-204).
    """
    return (
        "백업 파일 구조는 확인했지만 임시 복원까지는 하지 못했습니다. "
        "복원 가능 여부는 아직 확인되지 않았습니다."
    )


def _friendly_backup_failure(exc: Exception) -> str:
    return (
        "백업 생성 중 오류가 발생했습니다. 디스크 용량/권한을 확인하거나 "
        "문제가 계속되면 관리자에게 문의하세요."
    )


# ── 세트인가 낱개 파일인가 ───────────────────────────────────
#
# S2 까지의 행은 `path` 가 `.dump` **파일**을 가리킨다. S12 부터는 **디렉터리**다.
# 둘을 가르는 것은 이름 접두사가 아니라 **실제 디스크 모양**이다 — 이름 규칙으로
# 판정하면 누가 파일을 옮긴 순간 그 행은 영원히 틀린 종류로 읽힌다.
SET_PREFIX = "backup-"


def is_set(path: str | Path) -> bool:
    """세트 디렉터리를 가리키는 행인가."""
    return Path(path).is_dir()


def dump_path(path: str | Path) -> Path:
    """행의 `path` 에서 **덤프 파일**을 얻는다. 낱개 행이면 그 자신이다."""
    target = Path(path)
    return target / manifest_mod.DATABASE_DUMP_NAME if target.is_dir() else target


def backup_view(row: Backup, names: dict | None = None) -> dict:
    """`names` 는 {user_id: {display_name, email}} (app/core/people.py::name_map).

    실행자를 UUID 로만 주면 "이 백업을 누가 돌렸나" 를 화면에서 알 수 없었다. 이름을
    **더하는** 것이지 id 를 감추는 것이 아니다 — id 는 감사 로그 대조에 그대로 쓴다.
    `names` 를 안 주면 이름은 None 이다(모르는 것을 지어내지 않는다).
    """
    import json as _json

    creator = (names or {}).get(row.created_by) or {}
    stored = None
    if row.manifest_json:
        try:
            stored = _json.loads(row.manifest_json)
        except ValueError:
            stored = None
    scope = (stored or {}).get("scope") or {}
    schema = (stored or {}).get("schema") or {}
    destination = (stored or {}).get("destination") or None
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
        # ── S12 ────────────────────────────────────────────────────
        "file_state": row.file_state,
        "downloaded_at": row.downloaded_at.isoformat() if row.downloaded_at else None,
        "alembic_head": schema.get("alembic_head_database"),
        "excluded_table_data": [
            item.get("label") for item in scope.get("excluded_table_data") or []
        ],
        "warnings": (stored or {}).get("warnings") or [],
        # 「사본이 백업 저장소에 갔는가」. 안 갔으면 안 갔다고 말한다 — 이 칸이 비어 있는
        # 것과 「보냈는데 실패」는 화면에서 다르게 보여야 한다.
        "destination_name": (destination or {}).get("provider_name"),
        "destination_ok": None if destination is None else bool(destination.get("ok")),
    }


def backup_warnings(db: Session) -> list[str]:
    """이 백업을 지금 믿어도 되는가에 대한 **경고**. 매니페스트와 화면이 함께 읽는다."""
    from app.backups import destination as destination_mod
    from app.storage import service as storage_service

    warnings: list[str] = []
    try:
        same_device = storage_service.same_device_warning(db)
    except Exception:
        logger.warning("동일 장치 판정에 실패했습니다", exc_info=True)
        same_device = None
    if same_device:
        warnings.append(same_device)
    try:
        if destination_mod.backup_provider(db) is None:
            warnings.append(
                "백업 저장소가 설정되지 않아 백업이 앱과 같은 디스크에만 있습니다. "
                "그 디스크가 고장 나면 백업도 함께 잃습니다."
            )
    except Exception:
        logger.warning("백업 저장소 확인에 실패했습니다", exc_info=True)
    return warnings


def run_backup(
    db: Session, settings: Settings, *, created_by: str | None, now: datetime
) -> Backup:
    """백업 세트 하나. **파일이 생겼다는 것만으로 성공이 아니다** (D-204)."""
    # Include microseconds so two backups in the same second get distinct sets.
    # (Same-second collisions previously aliased two DB rows to one file, letting
    # retention unlink a still-referenced backup.)
    stamp = now.strftime("%Y%m%d_%H%M%S_%f")
    set_dir = Path(settings.data_dir) / "exports" / f"{SET_PREFIX}{stamp}"
    dest = set_dir / manifest_mod.DATABASE_DUMP_NAME
    # `backup_type` 은 **덤프 형식**이다. 되돌릴 때 어떤 도구로 여는지가 이 값에 달렸다
    # — 옛 `sqlite` 파일과 새 `pg_dump` 아카이브를 한 목록에서 구별할 수 있어야 한다.
    row = Backup(backup_type="pg_dump", path=str(set_dir), status="running",
                 created_by=created_by, created_at=now)
    db.add(row)
    db.flush()
    row_id = row.id

    # 경고와 스키마 판은 **커밋 전에** 읽는다 — 아래 느린 구간은 세션을 오래 안 쓴다.
    warnings = backup_warnings(db)
    head_db = manifest_mod.db_alembic_version(db)
    head_code = manifest_mod.code_alembic_head()

    # UA-03: 쓰기 락을 쥔 채 느린 I/O 를 하지 않는다 (trash/service.py::purge_expired 의
    # S7과 같은 실패 양식). 이 지점까지의 `db.flush()`가 SQLite 의 쓰기 락을 잡았는데,
    # 예전엔 그 상태로 전체 DB 복사(backup_database) + 임시 복원 + 무결성 검사 2벌
    # (restore_test)을 수행하고 커밋은 요청 끝에야 일어났다 — 그동안 앱의 다른 모든
    # 쓰기가 `busy_timeout` 후 "database is locked" 500이었다. 여기서 커밋해 락을
    # 놓고, 느린 구간은 락 없이 돈다. 아래에서 죽어도(OOM 등) 행은 'running'으로 남아
    # `reap_stuck_running`이 정리한다 — 원래 있던 실패 처리 그대로다.
    db.commit()

    stored_manifest: dict | None = None
    try:
        bin_dir = getattr(settings, "pg_bin_dir", "") or None
        # 파생 데이터의 **행**은 안 담는다(D-203 · D-204). 무엇을 왜 빼는지는
        # `app/backups/policy.py` 하나가 정하고 매니페스트가 그대로 싣는다.
        result = backup_database(
            settings.database_url, dest, bin_dir=bin_dir,
            exclude_table_data=policy.excluded_tables(),
        )
        size_bytes = result["size_bytes"]
        checksum = result["checksum"]
        # Immediate temp-restore verification (spec §6.3).
        # **임시 DB 로 실제 복원해 본다**(D-204). 파일이 생겼다는 것만으로 SUCCESS 가
        # 아니다 — `reason` 에 «structure_only» 가 오면 거기까지만 봤다는 뜻이다.
        verify = restore_test(dest, database_url=settings.database_url, bin_dir=bin_dir)
        reason = verify.get("reason") or ""
        if verify["ok"] and reason.startswith(PARTIAL_VERIFY_PREFIX):
            # 구조는 봤고 실복원은 못 했다. **`verified` 로 올리지 않는다** — 그 상태값의
            # 뜻은 "되돌릴 수 있음을 확인했다" 이고, 여기서는 그걸 확인하지 못했다.
            logger.warning("backup verified only structurally: %s (%s)", dest, reason)
            status = STATUS_SUCCEEDED
            verified_at: datetime | None = None
            error_message = _partial_verify_note(reason)
        elif verify["ok"]:
            status = STATUS_VERIFIED
            verified_at = now
            error_message = None
        else:
            logger.warning("backup restore-verify failed: %s (%s)", dest, verify.get("reason"))
            status = STATUS_FAILED
            verified_at = None
            error_message = _friendly_verify_reason(verify.get("reason"))

        # 원본 파일·첨부와 세트 사본을 백업 저장소로. **실패해도 덤프 검증 결과를 뒤집지
        # 않는다** — 「DB 백업은 됐고 사본 전송은 실패했다」가 사실이고, 그 둘을 한 상태값
        # 으로 뭉개면 어느 쪽이 문제인지 화면에서 못 읽는다. 경고로 남긴다.
        files_result = _archive_files(db, warnings)
        destination_result = None
        if status != STATUS_FAILED:
            destination_result = _copy_to_destination(db, set_dir, warnings)

        stored_manifest = manifest_mod.build(
            created_at=now,
            created_by=created_by,
            database={
                "file": manifest_mod.DATABASE_DUMP_NAME,
                "size_bytes": size_bytes,
                "sha256": checksum,
                "format": "pg_dump custom (-Fc)",
                "verified": status == STATUS_VERIFIED,
            },
            alembic_head_code=head_code,
            alembic_head_db=head_db,
            destination=destination_result,
            files=files_result,
            warnings=warnings,
        )
        manifest_mod.write(set_dir, stored_manifest)
        # 매니페스트를 쓴 뒤에 사본을 다시 맞춘다 — 안 그러면 저쪽 세트에 매니페스트가
        # 빠진 채로 남고, 그 사본만 들고 있는 서버에서는 범위를 읽을 방법이 없다.
        #
        # **덤프는 다시 안 보낸다.** 위 회차가 이미 보냈고, 통째로 다시 보내면 수 GB 를
        # 두 번 쓴다 — 백업 회차 길이가 곧 실패 확률이다.
        if destination_result is not None and destination_result.get("ok"):
            _copy_to_destination(
                db, set_dir, warnings,
                only={manifest_mod.MANIFEST_NAME, manifest_mod.CHECKSUMS_NAME},
            )
    except Exception as exc:
        logger.exception("backup creation failed: %s", set_dir)
        size_bytes = checksum = None
        status = STATUS_FAILED
        verified_at = None
        error_message = _friendly_backup_failure(exc)

    # 짧은 마무리 쓰기 — 한 문장(행 하나)만 바꾸므로 락을 쥐는 시간이 이 I/O 시간과
    # 무관해진다.
    row = db.get(Backup, row_id)
    row.size_bytes = size_bytes
    row.checksum = checksum
    row.status = status
    row.error_message = error_message
    if stored_manifest is not None:
        import json as _json

        row.manifest_json = _json.dumps(stored_manifest, ensure_ascii=False)
    if verified_at is not None:
        row.verified_at = verified_at
    db.flush()
    return row


def _archive_files(db: Session, warnings: list[str]) -> dict | None:
    """업로드 원본·첨부를 백업 저장소로 (S8 `archive_to_backup`).

    **정본 범위에 들어 있다**(D-204: 원본 파일 · 첨부). DB 덤프만 뜨고 파일을 안 옮기면
    복원본은 행이 가리키는 바이트가 없는 상태가 되고, 그 사실은 첨부를 여는 사람이 처음
    발견한다.
    """
    from app.backups import destination as destination_mod
    from app.storage import archive

    try:
        return archive.archive_to_backup(db)
    except archive.ArchiveNotPossible as exc:
        # 「백업 저장소가 아예 없다」는 `backup_warnings` 가 이미 한 문장으로 말했다.
        # 여기서 또 말하면 화면에 같은 사실이 두 번 뜨고, 두 번째 문장에는 내부 역할
        # 이름(`OPERATIONAL`/`BACKUP`)까지 섞여 나간다. 저장소가 **있는데** 실패한
        # 경우만 새로 알린다 — 그것이 새 사실이다.
        if destination_mod.backup_provider(db) is not None:
            warnings.append(f"업로드 파일을 백업 저장소로 옮기지 못했습니다: {exc}")
        return {"ok": False, "reason": str(exc)}
    except Exception as exc:
        logger.exception("파일 저장소 아카이브 실패")
        warnings.append(f"업로드 파일 사본에 실패했습니다: {type(exc).__name__}")
        return {"ok": False, "reason": type(exc).__name__}


def _copy_to_destination(
    db: Session, set_dir: Path, warnings: list[str], *, only: set[str] | None = None
) -> dict | None:
    from app.backups import destination as destination_mod

    try:
        result = destination_mod.copy_set(db, set_dir, only=only)
    except destination_mod.DestinationUnavailable as exc:
        # 「설정 안 함」은 이미 `backup_warnings` 가 말했다. 여기서 또 말하면 같은 문장이
        # 두 번 뜬다 — 준비 안 된 마운트만 새로 알린다.
        message = f"백업 세트를 백업 저장소로 못 보냈습니다: {exc}"
        if destination_mod.backup_provider(db) is not None and message not in warnings:
            warnings.append(message)
        return None
    except Exception as exc:
        logger.exception("백업 세트 사본 실패: %s", set_dir)
        warnings.append(f"백업 세트 사본에 실패했습니다: {type(exc).__name__}")
        return {"ok": False, "reason": type(exc).__name__}
    if not result["ok"]:
        warnings.append(
            "백업 저장소에 쓴 파일이 원본과 달랐습니다: " + ", ".join(result["mismatched"])
        )
    return result


def verify_existing(
    db: Session, row: Backup, *, now: datetime, settings: Settings | None = None
) -> dict:
    """다시 확인한다 — **세트 전체**를, 그리고 덤프 아카이브를.

    세트 검증(`SHA256SUMS`)을 먼저 하는 이유: 덤프만 보면 매니페스트가 바뀐 것을 못 잡고,
    그러면 「무엇이 안 담겼나」에 대한 답이 조용히 달라진다.
    """
    if row.file_state == FILE_REMOVED:
        # 「사람이 지웠다」와 「없어졌다」는 다르다. 후자만 손상이다.
        return {"ok": False, "reason": "file_removed"}
    bin_dir = getattr(settings, "pg_bin_dir", "") or None
    target = Path(row.path)
    set_result = None
    if is_set(target):
        set_result = manifest_mod.verify_set(target)
        if not set_result["ok"]:
            row.status = STATUS_FAILED
            row.error_message = _friendly_verify_reason(set_result["reason"])
            db.flush()
            return {"ok": False, "reason": set_result["reason"], "set": set_result}
    # `settings` 는 `pg_bin_dir` 하나 때문에 받는다. 안 주면 `PATH` 에서 찾는다 —
    # 그 경로가 통하는 환경도 있으므로 필수로 만들지 않는다.
    result = verify_backup(dump_path(target), row.checksum, bin_dir=bin_dir)
    if set_result is not None:
        result = dict(result, set=set_result)
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


# ── 다운로드와 그 뒤 (D-204: 자동 삭제하지 않는다) ───────────────────


def mark_downloaded(db: Session, row: Backup, *, now: datetime) -> None:
    """내려받은 사실만 적는다. **이 값 때문에 서버가 파일을 지우지 않는다.**

    자동 삭제가 편해 보이지만, 브라우저가 받다 만 것과 다 받은 것을 서버는 구별하지
    못한다. 지우는 것은 사람이 「받았다」고 답한 뒤여야 한다.
    """
    row.downloaded_at = now
    db.flush()


def discard_file(db: Session, row: Backup, *, now: datetime) -> dict:
    """세트를 **앱 디스크에서** 지운다 — 행도, 백업 저장소 사본도 남긴다.

    행까지 지우면 「그때 백업을 만들어 받아 갔다」는 사실이 사라진다. 그 사실은 감사
    로그와 짝을 이루므로 지울 이유가 없다.

    🔴 **백업 저장소 사본은 안 지운다.** 사람이 답한 질문은 「서버에 저장된 백업 파일을
    지울까요」이고, 그 사람이 원한 것은 앱 디스크의 공간이다. 백업 저장소의 사본은
    **재해 복구용 사본**이라 이 요청과 다른 물건이다 — 공간 회수의 부수 효과로 그것까지
    지우면, 정작 필요한 날 물어본 적 없는 삭제로 사라진 것을 알게 된다.

    저쪽 사본이 영원히 남지는 않는다: 행은 살아 있으므로 보존 정리가 나중에 그 행을
    지울 때 사본도 함께 지운다(`apply_retention`).
    """
    removed_local = _unlink_target(Path(row.path))
    row.file_state = FILE_REMOVED
    row.error_message = None
    db.flush()
    return {"removed_local": removed_local, "removed_remote": False}


def _unlink_target(target: Path) -> bool:
    """파일이든 디렉터리든 치운다. 이미 없으면 False."""
    try:
        if target.is_dir():
            shutil.rmtree(target)
            return True
        if target.exists():
            target.unlink()
            return True
    except OSError:
        logger.warning("백업 파일을 지우지 못했습니다: %s", target, exc_info=True)
    return False


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


#: 며칠은 무조건 남긴다. 개수만으로 자르면 **하루에 여러 번 돌린 날**이 그 전 며칠치
#: 복원 지점을 한꺼번에 밀어낸다 — 옛 백업 cron 이 배포 스냅숏에서 겪고
#: 「개수가 아니라 나이로 지운다」로 고쳤던 바로 그 실패다. 여기서는 **둘 다** 건다.
DEFAULT_KEEP_DAYS = 7


def apply_retention(
    db: Session,
    *,
    keep: int = 14,
    keep_days: int = DEFAULT_KEEP_DAYS,
    now: datetime | None = None,
) -> int:
    """보존 정책 한 번. **개수 바닥과 나이 바닥을 둘 다** 지킨다.

    정상 백업은 다음 둘을 **모두** 만족할 때만 지워진다:

      * 최근 `keep` 개 안에 없다 (개수 바닥)
      * 만든 지 `keep_days` 일이 넘었다 (나이 바닥)

    둘 중 하나만 걸면 각각 다른 방식으로 복원 지점을 잃는다. 개수만 걸면 하루에 여러 번
    돌린 날이 지난 주를 통째로 밀어내고, 나이만 걸면 하루에 수백 번 도는 사고에서
    디스크가 찬다. 그래서 **둘 다** 통과해야 지운다 — 지우는 쪽이 더 어렵게.

    실패 행과 파일이 이미 없는 행(`file_state=removed`)은 복원 지점이 아니므로 개수
    바닥을 안 준다. 다만 **가장 최근 실패 하나**는 장애 추적을 위해 남긴다.
    """
    from app.backups import destination as destination_mod

    now = now or utcnow()
    age_floor = now - timedelta(days=max(int(keep_days), 0))

    restorable = db.execute(
        select(Backup)
        .where(
            Backup.status.in_([STATUS_SUCCEEDED, STATUS_VERIFIED]),
            Backup.file_state == FILE_PRESENT,
        )
        .order_by(Backup.created_at.desc())
    ).scalars().all()
    keep_ids = {row.id for row in restorable[:keep]}

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
        if row.created_at > age_floor:
            continue
        target = Path(row.path)
        _unlink_target(target)
        if target.name.startswith(SET_PREFIX):
            destination_mod.remove_set(db, target.name)
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
    # 나이 바닥. `apply_retention` 이 개수와 **함께** 본다 — 왜 둘 다인지는 그 함수에 있다.
    "keep_days": DEFAULT_KEEP_DAYS,
}


def retention_from_config(config: dict) -> dict:
    """설정 dict 에서 보존 인자만 뽑는다.

    예약 경로와 수동 경로가 각자 `config.get("keep", 14)` 를 적으면, 하나만 고친 날
    같은 설치에서 **보존이 두 가지로 동작한다.** 실제로 그런 적이 있다(수동 백업이
    하드코딩 14 를 썼다). 뽑는 자리를 하나로 둔다.
    """
    # `or` 로 기본값을 주지 않는다 — `keep_days: 0`(「개수만으로 자른다」를 **명시적으로**
    # 고른 값)이 falsy 라서 조용히 7 로 바뀐다. 없는 것과 0 은 다른 뜻이다.
    def _int(key: str, fallback: int) -> int:
        value = config.get(key)
        return fallback if value is None else int(value)

    return {"keep": _int("keep", 14), "keep_days": _int("keep_days", DEFAULT_KEEP_DAYS)}


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


def announce_backup_failure(db, *, reason: str, now, title: str = "예약 백업이 실패했습니다") -> None:
    """백업 실패를 **사람에게** 알린다 (9-9 P4, §E-6).

    `title` 기본값은 예약 백업 경로(아래 `run_scheduled_backup`)의 문구다 — 수동 백업
    경로(app/backups/router.py::create_backup, FN-09)는 다른 문구로 이 함수를 부른다.

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
            subject=f"[ClovirAssist] {title}",
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
            title=title,
            body=reason[:200],
            related=("backup", None), now=now,
        )
    except Exception:
        logger.exception("백업 실패 화면 알림을 남기지 못했다 (백업 기록은 남는다)")


# RSTR-03: 예약 백업이 실패하면 announce_backup_failure가 알린다 — 하지만 이 설치의 실제
# 문제는 실패가 아니라 **애초에 안 도는 것**이었다(기본값이 꺼짐, 마지막 성공 백업이 20일
# 전). "백업이 실패했습니다" 알림은 실행 자체가 없으면 한 번도 안 나가므로, 아무도 그
# 사실을 몰랐다 — /restore-drills 화면을 직접 열어야만 보이는데 아무도 그 화면을 안 봤다.
BACKUP_STALE_ALERT_DAYS = 7
# 이 틱은 10분마다 돈다(worker_main.py) — "꺼져 있음"·"오래 안 돎"은 다음 백업이 생기거나
# 설정이 바뀌기 전까지 계속 참이라, 매 틱 알리면 관리자 알림함이 도배된다. 다른 반복 경보
# (app/runners/service.py::record_runner_result)이 이미 쓰는 원칙과 같다 — "정상→나쁨 전환"
# 에만 보낸다. 백업은 전환을 표시할 전용 상태 컬럼이 없으므로, 최근 이미 같은 유형의 관리자
# 알림을 보냈는지(Notification 테이블 자체가 이미 갖고 있는 사실) 확인하는 것으로 대신한다 —
# 새 상태를 하나 더 만들면 그 상태와 Notification 이 어긋나는 날이 온다.
BACKUP_ALERT_COOLDOWN_HOURS = 24


def backup_health_alert_reason(db: Session, config: dict, *, now: datetime) -> str | None:
    """예약 백업이 꺼져 있거나, 켜져 있는데도 너무 오래 안 돌았으면 그 이유를 돌려준다.
    문제 없으면 None."""
    if not config.get("enabled"):
        return "예약 백업이 꺼져 있어 자동 백업이 되고 있지 않습니다. 백업 화면에서 예약을 켜거나, 정기적으로 수동 백업을 만드세요."
    last = last_successful_backup(db)
    if last is None:
        return "예약 백업이 켜져 있지만 아직 성공한 백업이 하나도 없습니다."
    seconds_elapsed = (now - last.created_at).total_seconds()
    stale_days = seconds_elapsed / 86400
    if stale_days > BACKUP_STALE_ALERT_DAYS:
        return f"마지막으로 성공한 백업이 {format_elapsed_korean(seconds_elapsed)} 전입니다. 예약이 켜져 있는데도 이렇게 오래됐다면 워커나 스케줄 설정을 확인하세요."
    return None


def _recently_alerted_backup_health(db: Session, *, now: datetime) -> bool:
    from app.notifications.models import AUDIENCE_ADMIN, Notification

    cutoff = now - timedelta(hours=BACKUP_ALERT_COOLDOWN_HOURS)
    return db.execute(
        select(Notification.id)
        .where(
            Notification.type == "backup_failed",
            Notification.audience == AUDIENCE_ADMIN,
            Notification.created_at >= cutoff,
        )
        .limit(1)
    ).scalar_one_or_none() is not None


def check_backup_health(db: Session, config: dict, *, now: datetime) -> None:
    """예약 백업이 꺼져 있거나 정체됐으면 하루에 최대 한 번 관리자에게 알린다."""
    reason = backup_health_alert_reason(db, config, now=now)
    if reason is None or _recently_alerted_backup_health(db, now=now):
        return
    announce_backup_failure(db, reason=reason, now=now, title="예약 백업 상태를 확인해 주세요")


def run_scheduled_backup(db, settings, config: dict, *, now):
    """예약 백업 1회. 예외를 밖으로 내보내지 않는다(워커 루프를 죽이지 않는다).

    **실패를 삼키지 않는다**(§E-6). run_backup 은 예외를 잡아 행 상태만 failed 로 바꾸므로
    여기서 예외가 안 보이는 것이 정상이다 - 그래서 예외가 아니라 **행 상태**를 본다.
    """
    try:
        row = run_backup(db, settings, created_by=None, now=now)
        apply_retention(db, now=now, **retention_from_config(config))
        if row is not None and row.status == STATUS_FAILED:
            announce_backup_failure(
                db,
                reason=row.error_message or "원인이 기록되지 않았습니다.",
                now=now,
            )
        return row
    except Exception as exc:
        logger.exception("예약 백업 실패")
        announce_backup_failure(db, reason=f"{type(exc).__name__}: {exc}", now=now)
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
