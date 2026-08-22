"""파일 저장소 백업과 복원 (S8 · D-199 14·15번).

## 여기가 하는 것과 안 하는 것

**한다**: 운영 저장소의 바이트를 백업 저장소로 옮기고, 옮긴 뒤 **체크섬을 다시 확인**한다.
복원은 그 반대 방향이다.

**안 한다**: 일정 · 보존 정책 · manifest · PostgreSQL 덤프. 그것은 S12 의 몫이고
(`BACKLOG.md` P-23), 이 모듈은 그쪽이 부를 수 있는 조각으로 남는다. 여기서 정책까지
만들면 S12 가 두 벌을 만나게 된다.

## 「복사했다」가 아니라 「같은 파일이 저쪽에 있다」

파일을 만든 것만으로 SUCCESS 를 찍지 않는다(D-204 가 PostgreSQL 쪽에 같은 규칙을
적어 뒀다). 쓴 뒤 다시 읽어 sha256 을 비교하고, 다르면 그 파일은 실패로 센다.
NFS/SMB 는 쓰기가 성공한 것처럼 보이고 나중에 다른 내용이 되는 실패 모드가 실제로
있다 — 확인하지 않으면 그것을 못 본다.

## 이미 있는 것은 다시 안 쓴다

같은 키가 저쪽에 있고 체크섬이 같으면 건너뛴다. 백업은 반복해서 도는 작업이라,
매번 전량을 다시 쓰면 회차가 길어지고 그 길이가 곧 실패 확률이 된다.
"""

from __future__ import annotations

import hashlib
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.storage import adapters, service
from app.storage.adapters import (
    ROLE_BACKUP,
    ROLE_OPERATIONAL,
    ProviderRef,
    StorageNotReady,
    StorageWriteFailed,
)
from app.storage.models import File

logger = logging.getLogger("app.storage.archive")


class ArchiveNotPossible(Exception):
    """저장소 한쪽이 준비되지 않아 시작조차 하지 않았다.

    「0건 복사 성공」과 구별하기 위해 예외로 낸다. 그 둘을 같은 모양으로 보고하면
    마운트가 빠진 밤에도 백업 이력이 초록으로 남는다.
    """


def archive_to_backup(db: Session, *, limit: int | None = None) -> dict:
    """운영 → 백업. 결과는 세어서 돌려준다."""
    return _copy(db, ROLE_OPERATIONAL, ROLE_BACKUP, limit=limit)


def restore_from_backup(db: Session, *, limit: int | None = None) -> dict:
    """백업 → 운영. 방향만 반대이고 확인 방식은 같다."""
    return _copy(db, ROLE_BACKUP, ROLE_OPERATIONAL, limit=limit)


def _copy(db: Session, from_role: str, to_role: str, *, limit: int | None) -> dict:
    source = service.active_provider(db, role=from_role)
    target = service.active_provider(db, role=to_role)
    if source is None or target is None:
        raise ArchiveNotPossible(
            f"저장소가 없습니다(원본 {from_role}={bool(source)}, 대상 {to_role}={bool(target)})."
        )
    if source.id == target.id:
        raise ArchiveNotPossible("원본과 대상이 같은 저장소입니다.")

    src_ref, dst_ref = service.ref_of(source), service.ref_of(target)
    try:
        adapters.ensure_ready(src_ref)
        adapters.ensure_ready(dst_ref)
    except StorageNotReady as exc:
        raise ArchiveNotPossible(f"{exc.state.path}: {exc.state.detail}") from None

    # 어느 방향이든 **행이 정본**이고, 그 행은 언제나 **운영 저장소**를 가리킨다.
    #
    # 이 구분이 없으면 복원이 0건으로 끝난다: 백업 저장소에는 바이트만 있고
    # `files` 행은 없기 때문이다(백업은 사본이지 별개의 자산이 아니다). 그리고 저장소를
    # 훑어 옮기는 방식으로 바꾸면 고아 파일까지 함께 가서, 백업이 운영보다 커지고 그
    # 차이가 무엇인지 설명할 수 없게 된다.
    ledger = source if source.role == ROLE_OPERATIONAL else target
    stmt = select(File).where(File.storage_provider_id == ledger.id).order_by(File.created_at)
    if limit:
        stmt = stmt.limit(limit)
    rows = list(db.execute(stmt).scalars().all())

    copied = skipped = failed = 0
    failures: list[str] = []
    for record in rows:
        try:
            if _already_there(dst_ref, record):
                skipped += 1
                continue
            data = adapters.read_object(src_ref, record.storage_key)
            if hashlib.sha256(data).hexdigest() != record.checksum_sha256:
                failed += 1
                failures.append(f"{record.id}: 원본 체크섬이 기록과 다릅니다")
                continue
            adapters.write_object(dst_ref, record.storage_key, data)
            if not _already_there(dst_ref, record):
                failed += 1
                failures.append(f"{record.id}: 쓴 뒤 확인에서 체크섬이 달랐습니다")
                continue
            copied += 1
        except (StorageNotReady, StorageWriteFailed, ValueError) as exc:
            failed += 1
            failures.append(f"{record.id}: {type(exc).__name__}")
            logger.exception("archive: 파일 복사 실패 file_id=%s", record.id)

    return {
        "source": source.name,
        "target": target.name,
        "total": len(rows),
        "copied": copied,
        "skipped": skipped,
        "failed": failed,
        "failures": failures[:20],
        "ok": failed == 0,
    }


def _already_there(ref: ProviderRef, record: File) -> bool:
    """대상에 같은 내용이 이미 있는가. **크기가 아니라 체크섬으로 본다.**"""
    if not adapters.object_exists(ref, record.storage_key):
        return False
    try:
        data = adapters.read_object(ref, record.storage_key)
    except (StorageNotReady, StorageWriteFailed, ValueError):
        return False
    return hashlib.sha256(data).hexdigest() == record.checksum_sha256
