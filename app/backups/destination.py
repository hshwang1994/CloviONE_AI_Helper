"""백업 세트를 **백업 저장소**(NFS/SMB/Local Provider)로 옮긴다 (S12 · D-204 16번).

## 왜 앱 디스크에만 두면 안 되는가

`data_dir/exports/` 는 앱이 사는 그 디스크다. 그 디스크가 죽는 것이 우리가 백업을
만드는 이유의 절반인데, 백업이 같은 디스크에만 있으면 그 절반에 대해 아무 대비가 없다.
그래서 세트를 만든 뒤 **`role=BACKUP` 저장소로 사본을 보낸다.**

## 왜 `adapters.write_object` 를 안 쓰는가

S8 의 객체 API 는 (1) 키 모양을 `ab/cd/<uuid32>` 로 못박고 (2) 바이트 전체를 메모리에
올린다. 첨부 하나를 다루기에는 맞지만 데이터베이스 덤프에는 둘 다 틀리다 — 덤프는
사람이 읽을 수 있는 이름이어야 하고(사고 당일 `ls` 로 찾는다), 크기가 메모리를 넘는다.

**마운트 가드는 그대로 지난다**(`adapters.ensure_ready`). 그것이 S8 의 핵심 계약이고,
빠뜨리면 NFS 가 빠진 밤에 백업이 조용히 **로컬 디스크**로 간다 — 그리고 다음 날 아침
`df` 가 차기 전까지 아무도 모른다.

## 「썼다」가 아니라 「같은 것이 저쪽에 있다」

쓴 뒤 다시 읽어 sha256 을 비교한다. `app/storage/archive.py` 와 같은 규칙이고 이유도
같다 — NFS/SMB 에는 쓰기가 성공한 것처럼 보이고 나중에 다른 내용이 되는 실패 모드가
실제로 있다.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from app.backups.pg_backup import sha256_file
from app.storage import adapters, service
from app.storage.adapters import ROLE_BACKUP, StorageNotReady

logger = logging.getLogger("app.backups.destination")

#: 백업 저장소 안에서 데이터베이스 세트가 사는 자리. 첨부 사본(S8 `archive_to_backup`)이
#: 같은 뿌리에 객체 키 모양으로 쌓이므로, 세트는 **한 겹 아래**로 내려 서로 안 섞이게 한다.
SET_ROOT = "db-backups"

_COPY_CHUNK = 1024 * 1024


class DestinationUnavailable(Exception):
    """백업 저장소가 없거나 준비되지 않았다.

    「사본을 0건 보냈다」와 구별하려고 예외로 낸다. 그 둘을 같은 모양으로 보고하면
    마운트가 빠진 밤에도 「사본 보냄」이 초록으로 남는다.
    """


def backup_provider(db: Session):
    """켜져 있는 `role=BACKUP` 저장소. 없으면 `None` (설정 안 한 것은 오류가 아니다)."""
    return service.active_provider(db, role=ROLE_BACKUP)


def copy_set(db: Session, set_dir: Path, *, only: set[str] | None = None) -> dict:
    """세트 디렉터리를 백업 저장소로 옮기고 **다시 읽어 확인한다**.

    `only` 를 주면 그 이름들만 보낸다. 매니페스트는 **덤프를 보낸 결과를 담아야** 하므로
    덤프보다 늦게 쓰이는데, 그렇다고 세트를 두 번 통째로 보내면 수 GB 를 두 번 쓴다.
    두 번째 회차는 뒤늦게 생긴 작은 파일 둘만 보낸다.
    """
    provider = backup_provider(db)
    if provider is None:
        raise DestinationUnavailable("백업 저장소가 설정되지 않았습니다.")
    ref = service.ref_of(provider)
    try:
        adapters.ensure_ready(ref)
    except StorageNotReady as exc:
        raise DestinationUnavailable(f"{exc.state.path}: {exc.state.detail}") from None

    target = Path(ref.base_path) / SET_ROOT / set_dir.name
    target.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    mismatched: list[str] = []
    total = 0
    for entry in sorted(set_dir.iterdir()):
        if not entry.is_file():
            continue
        if only is not None and entry.name not in only:
            continue
        expected = sha256_file(entry)
        digest = _copy_file(entry, target / entry.name)
        if digest != expected:
            mismatched.append(entry.name)
            continue
        copied.append(entry.name)
        total += entry.stat().st_size

    return {
        "provider_id": provider.id,
        "provider_name": provider.name,
        "provider_kind": provider.kind,
        "path": str(target),
        "copied": copied,
        "mismatched": mismatched,
        "bytes": total,
        "ok": not mismatched,
    }


def remove_set(db: Session, set_name: str) -> bool:
    """보존 정리가 로컬 세트를 지울 때 **저쪽 사본도 함께** 지운다.

    안 지우면 백업 저장소만 무한히 자란다 — 그리고 그 사실은 그 저장소가 찰 때 처음
    드러난다. 저장소가 없거나 안 붙어 있으면 조용히 넘어간다(지우기 실패가 보존 정리
    전체를 멈추게 하지 않는다). 대신 로그에는 남긴다.
    """
    provider = backup_provider(db)
    if provider is None:
        return False
    ref = service.ref_of(provider)
    try:
        adapters.ensure_ready(ref)
    except StorageNotReady:
        logger.warning("백업 저장소가 준비되지 않아 사본을 못 지웠습니다: %s", set_name)
        return False
    target = Path(ref.base_path) / SET_ROOT / set_name
    if not target.is_dir():
        return False
    try:
        shutil.rmtree(target)
        return True
    except OSError:
        logger.warning("백업 저장소 사본을 지우지 못했습니다: %s", target, exc_info=True)
        return False


def _copy_file(source: Path, dest: Path) -> str:
    """스트리밍 복사. 돌려주는 것은 **다시 읽은** 바이트의 sha256 이다.

    쓰면서 계산한 해시를 돌려주면 「내가 보낸 바이트」만 확인하는 셈이라, 저쪽이 다른
    것을 저장하는 실패를 못 잡는다. 임시 이름으로 쓴 뒤 제자리로 옮기므로 중간에 죽어도
    **반쪽 파일이 최종 이름을 갖는 일이 없다**.
    """
    tmp = dest.with_name(dest.name + ".part")
    try:
        with open(source, "rb") as src, open(tmp, "wb") as out:
            while chunk := src.read(_COPY_CHUNK):
                out.write(chunk)
            out.flush()
            os.fsync(out.fileno())
        tmp.replace(dest)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    digest = hashlib.sha256()
    with open(dest, "rb") as fh:
        while chunk := fh.read(_COPY_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()
