"""저장소 서비스 — 업로드 파이프라인과 저장소 상태 (S8 · D-199).

## 순서가 계약이다: 파일 먼저, DB 행 다음

거꾸로 하면 「행은 있는데 파일이 없다」가 생긴다. 그것은 **거짓말**이다 — 목록에
이름이 보이고, 크기가 보이고, 눌러야 없다는 것을 안다. 반대 순서로 하면 최악이
「가리키는 사람이 없는 파일」이고, 그건 쓰레기이지 거짓말이 아니다.
아무도 안 가리키게 된 파일은 `sweep_orphans()` 가 치운다.

DB flush 가 실패하면 방금 쓴 바이트를 **되돌린다.** 그래야 「부분 실패 시 파일도
행도 없다」(D-199 9번)가 성립한다.

## 503 으로 바꾸는 자리는 여기 하나다

`app/storage/adapters.py` 는 `StorageNotReady` · `StorageWriteFailed` 를 던지고,
HTTP 지위로 바꾸는 것은 이 파일이다. **500 이 아니라 503 이다** — 마운트가 안 붙은
것은 「서버가 깨졌다」가 아니라 「지금은 못 한다」이고, 그 둘은 사용자가 할 수 있는
일이 다르다(기다린다 vs 신고한다).

## 마운트를 여기서 판정하지 않는다

`mount.py::mount_state` 하나가 답한다. 이 파일은 그 답을 읽어 화면 모양으로 옮길 뿐이다
(`scripts/check_domain_single_source.py` 가 이 규칙을 지킨다).
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import (
    ConflictError,
    NotFoundError,
    StorageUnavailableError,
    ValidationAppError,
)
from app.core.uploads import (
    DOCUMENT_MEDIA_TYPES,
    MAX_UPLOAD_BYTES,
    extension_for,
    sanitize_filename,
    sniff_media_type,
)
from app.storage import adapters
from app.storage.adapters import (
    KIND_LOCAL,
    ROLE_BACKUP,
    ROLE_OPERATIONAL,
    ProviderRef,
    StorageNotReady,
    StorageWriteFailed,
)
from app.storage.models import File, StorageProvider
from app.storage.mount import same_device

logger = logging.getLogger("app.storage")

#: 설치 직후 자동으로 서는 저장소의 이름. 이름으로 찾으므로 바꾸지 않는다.
DEFAULT_PROVIDER_NAME = "기본 로컬 저장소"


# ── 저장소 조회 ──────────────────────────────────────────────────────────────


def ref_of(provider: StorageProvider) -> ProviderRef:
    """ORM 행 → Adapter 가 받는 값. **여기가 유일한 다리다.**"""
    return ProviderRef(
        kind=provider.kind,
        base_path=provider.base_path,
        mount_point=provider.mount_point,
        name=provider.name,
    )


def active_provider(db: Session, *, role: str = ROLE_OPERATIONAL) -> StorageProvider | None:
    """그 역할의 켜진 저장소. 부분 유니크 인덱스가 하나임을 보장한다."""
    return db.execute(
        select(StorageProvider)
        .where(StorageProvider.role == role, StorageProvider.enabled.is_(True))
    ).scalars().first()


def require_operational(db: Session) -> StorageProvider:
    provider = active_provider(db, role=ROLE_OPERATIONAL)
    if provider is None:
        # 설치가 안 끝난 상태다. 500 이 아니라 503 인 이유는 위 docstring 과 같다.
        logger.error("storage: 켜진 운영 저장소가 없습니다")
        raise StorageUnavailableError()
    return provider


def ensure_default_provider(db: Session, settings: Settings) -> StorageProvider:
    """설치 직후 기본 LOCAL 저장소를 세운다. **이미 있으면 아무것도 안 한다.**

    경로를 마이그레이션에 박지 않은 이유가 여기 있다 — `data_dir` 은 설치처마다 다르다.
    Installer Stage 11 과 개발 서버 기동이 같은 함수를 부른다.
    """
    existing = active_provider(db, role=ROLE_OPERATIONAL)
    if existing is not None:
        return existing
    base = Path(settings.data_dir).resolve() / "files"
    base.mkdir(parents=True, exist_ok=True)
    provider = StorageProvider(
        name=DEFAULT_PROVIDER_NAME,
        kind=KIND_LOCAL,
        role=ROLE_OPERATIONAL,
        base_path=base.as_posix(),
        mount_point=None,
        config_json="{}",
        enabled=True,
    )
    db.add(provider)
    db.flush()
    return provider


# ── 저장소 설정 ──────────────────────────────────────────────────────────────


def get_provider_or_404(db: Session, provider_id: str) -> StorageProvider:
    provider = db.get(StorageProvider, provider_id)
    if provider is None:
        raise NotFoundError("저장소를 찾지 못했습니다.")
    return provider


def _validate_shape(*, kind: str, base_path: str, mount_point: str | None) -> None:
    """종류와 경로의 짝을 본다. **DB CHECK 과 같은 규칙을 422 로 먼저 말해 준다.**

    제약에만 맡기면 사용자는 500 을 보고, 무엇이 틀렸는지 알 수 없다.
    """
    spec = adapters.spec_for(kind)
    if spec.requires_mount and not mount_point:
        raise ValidationAppError(f"{spec.label}에는 마운트포인트가 필요합니다.")
    if not spec.requires_mount and mount_point:
        raise ValidationAppError("로컬 저장소에는 마운트포인트를 지정하지 않습니다.")
    if mount_point:
        base = Path(base_path).as_posix().rstrip("/") or "/"
        mount = Path(mount_point).as_posix().rstrip("/") or "/"
        if base != mount and not base.startswith(f"{mount}/"):
            # 저장 경로가 마운트 밖이면 가드가 물어보는 자리와 실제로 쓰는 자리가
            # 달라진다. 그 상태에서는 마운트가 붙어 있어도 로컬 디스크에 쌓인다.
            raise ValidationAppError("저장 경로가 마운트포인트 아래에 있어야 합니다.")


def _assert_role_free(db: Session, *, role: str, exclude_id: str | None = None) -> None:
    """그 역할에 켜진 저장소가 이미 있으면 거절한다.

    자동으로 옛것을 끄지 않는다. 업로드가 어디로 가는지 바뀌는 변경이라, 두 단계로
    나눠야 「끄는 것」을 사람이 실제로 결정한다. 부분 유니크 인덱스가 마지막에 한 번 더
    막지만, 거기까지 가면 사용자가 보는 것은 500 이다.
    """
    current = active_provider(db, role=role)
    if current is not None and current.id != exclude_id:
        raise ConflictError(
            f"이미 켜져 있는 저장소가 있습니다({current.name}). 먼저 그 저장소를 끄십시오."
        )


def create_provider(
    db: Session,
    *,
    name: str,
    kind: str,
    role: str,
    base_path: str,
    mount_point: str | None = None,
    source: str = "",
    options: str = "",
    credentials_ref: str | None = None,
    enabled: bool = True,
) -> StorageProvider:
    _validate_shape(kind=kind, base_path=base_path, mount_point=mount_point)
    if enabled:
        _assert_role_free(db, role=role)
    provider = StorageProvider(
        name=name.strip(),
        kind=kind,
        role=role,
        base_path=Path(base_path).as_posix().rstrip("/") or "/",
        mount_point=(Path(mount_point).as_posix().rstrip("/") if mount_point else None),
        config_json=json.dumps(
            {"source": source.strip(), "options": options.strip()}, ensure_ascii=False
        ),
        credentials_ref=(credentials_ref or None),
        enabled=enabled,
    )
    db.add(provider)
    db.flush()
    return provider


def update_provider(
    db: Session,
    provider: StorageProvider,
    *,
    expected_version: int | None = None,
    **changes,
) -> StorageProvider:
    """설정을 고친다. **종류는 못 바꾼다.**

    종류가 바뀌면 이미 저장된 파일이 어느 규칙으로 쓰였는지 알 수 없게 된다. 바꾸려면
    새 저장소를 만들고 파일을 옮긴다 — 그 과정이 곧 「옮겼다」의 증거가 된다.
    """
    if expected_version is not None and provider.version != expected_version:
        raise ConflictError("다른 사람이 먼저 저장했습니다. 새로 고친 뒤 다시 시도해 주세요.")

    base_path = changes.get("base_path") or provider.base_path
    mount_point = changes.get("mount_point", provider.mount_point)
    _validate_shape(kind=provider.kind, base_path=base_path, mount_point=mount_point)

    enabled = changes.get("enabled")
    if enabled and not provider.enabled:
        _assert_role_free(db, role=provider.role, exclude_id=provider.id)

    if changes.get("name"):
        provider.name = changes["name"].strip()
    provider.base_path = Path(base_path).as_posix().rstrip("/") or "/"
    provider.mount_point = (
        Path(mount_point).as_posix().rstrip("/") if mount_point else None
    )
    if "credentials_ref" in changes:
        provider.credentials_ref = changes["credentials_ref"] or None
    if changes.get("source") is not None or changes.get("options") is not None:
        config = json.loads(provider.config_json or "{}")
        if changes.get("source") is not None:
            config["source"] = changes["source"].strip()
        if changes.get("options") is not None:
            config["options"] = changes["options"].strip()
        provider.config_json = json.dumps(config, ensure_ascii=False)
    if enabled is not None:
        provider.enabled = enabled
    provider.version += 1
    db.flush()
    return provider


# ── 업로드 파이프라인 ────────────────────────────────────────────────────────


def store_bytes(
    db: Session,
    *,
    filename: str,
    content: bytes,
    owner_ref: str | None = None,
    created_by: str | None = None,
    allowed_media_types: frozenset[str] = DOCUMENT_MEDIA_TYPES,
    provider: StorageProvider | None = None,
) -> File:
    """검증 → 저장 → 행. **이 순서를 바꾸지 않는다.**

    반환은 아직 flush 만 된 `File` 이다. 커밋은 요청 스코프가 한다 — 커밋이 실패하면
    행은 사라지고 바이트는 고아로 남는다(치울 수 있다). 반대로 바이트를 먼저 지우면
    커밋된 행이 없는 파일을 가리킬 수 있다.
    """
    size = len(content)
    if size == 0:
        raise ValidationAppError("빈 파일은 올릴 수 없습니다.")
    if size > MAX_UPLOAD_BYTES:
        mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        raise ValidationAppError(f"파일이 너무 큽니다. 최대 {mb}MB까지 올릴 수 있습니다.")

    media_type = sniff_media_type(content[:16], full=content)
    if media_type is None or media_type not in allowed_media_types:
        raise ValidationAppError(
            "허용되지 않은 파일 형식입니다. 이미지와 PDF, 오피스 문서, 텍스트 파일만 올릴 수 있습니다."
        )

    row = provider or require_operational(db)
    ref = ref_of(row)
    storage_key = adapters.new_storage_key(extension=extension_for(media_type))
    checksum = _write(ref, storage_key, content)

    record = File(
        storage_provider_id=row.id,
        storage_key=storage_key,
        filename=sanitize_filename(filename),
        mime_type=media_type,
        size_bytes=size,
        checksum_sha256=checksum,
        owner_ref=owner_ref,
        created_by=created_by,
    )
    db.add(record)
    try:
        db.flush()
    except Exception:
        # 행이 안 생겼으면 바이트도 남기지 않는다. 실패해도 원래 예외를 덮지 않는다.
        try:
            adapters.delete_object(ref, storage_key)
        except Exception:  # noqa: BLE001
            logger.exception("storage: 되돌리기 실패 key=%s", storage_key)
        raise
    return record


def read_bytes(db: Session, file_row: File) -> bytes:
    ref = ref_of(_provider_of(db, file_row))
    try:
        return adapters.read_object(ref, file_row.storage_key)
    except StorageNotReady as exc:
        _log_not_ready(exc)
        raise StorageUnavailableError() from None
    except (StorageWriteFailed, ValueError):
        logger.exception("storage: 읽기 실패 file_id=%s", file_row.id)
        raise NotFoundError("파일을 찾을 수 없습니다.") from None


def file_path(db: Session, file_row: File) -> Path:
    """서빙용 실제 경로. 마운트가 안 붙었으면 503 으로 끊는다.

    `FileResponse` 는 경로를 받으므로 바이트를 다 읽지 않는다 — 큰 첨부에서 메모리를
    아끼는 것이 목적이고, 마운트 판정은 여기서도 똑같이 지난다.
    """
    provider = _provider_of(db, file_row)
    ref = ref_of(provider)
    try:
        adapters.ensure_ready(ref)
    except StorageNotReady as exc:
        _log_not_ready(exc)
        raise StorageUnavailableError() from None
    try:
        path = adapters.object_path(ref, file_row.storage_key)
    except ValueError:
        logger.error("storage: 저장 키 모양이 잘못됐습니다 file_id=%s", file_row.id)
        raise NotFoundError("파일을 찾을 수 없습니다.") from None
    if not path.is_file():
        raise NotFoundError("파일을 찾을 수 없습니다.")
    return path


def delete_file(db: Session, file_row: File) -> None:
    """행과 바이트를 함께 없앤다. **바이트 먼저 지우지 않는다.**

    행을 먼저 지우면 커밋이 실패했을 때 「행은 살아 있는데 바이트가 없다」가 된다.
    바이트를 나중에 지우면 최악이 고아 파일이고, 그것은 `sweep_orphans` 가 치운다.
    """
    ref = ref_of(_provider_of(db, file_row))
    storage_key = file_row.storage_key
    db.delete(file_row)
    db.flush()
    try:
        adapters.delete_object(ref, storage_key)
    except (StorageNotReady, StorageWriteFailed):
        # 지금 못 지웠을 뿐이다. 행이 없으므로 다음 청소가 고아로 보고 치운다.
        logger.warning("storage: 삭제를 미룹니다 key=%s", storage_key)


#: 고아로 판정하기까지 기다리는 시간. 업로드는 바이트를 먼저 쓰고 DB 행을 나중에
#: 만들기 때문에(D-250), 그 사이에 청소가 지나가면 **방금 올린 파일**을 지운다.
ORPHAN_MIN_AGE_SECONDS = 3600


def sweep_orphans(
    db: Session,
    *,
    provider: StorageProvider | None = None,
    min_age_seconds: int = ORPHAN_MIN_AGE_SECONDS,
) -> int:
    """아무 행도 가리키지 않는 **충분히 늙은** 바이트를 치운다.

    🔴 나이를 보는 이유가 이 함수의 핵심이다. 순서가 「파일 먼저, 행 다음」이라
    (D-250) 그 사이의 파일은 **정상인데도** 가리키는 행이 없다. 나이를 안 보면
    청소가 그 창에 지나갈 때마다 사용자의 파일이 사라지고, 화면에는 성공이라고
    적혀 있다.

    반대 방향(행은 있는데 파일이 없다)은 **치우지 않는다.** 그것은 사고이고, 조용히
    지우면 사고가 있었다는 사실까지 사라진다 — `verify_files()` 가 세어서 보고한다.
    """
    row = provider or active_provider(db, role=ROLE_OPERATIONAL)
    if row is None:
        return 0
    ref = ref_of(row)
    try:
        adapters.ensure_ready(ref)
    except StorageNotReady as exc:
        _log_not_ready(exc)
        return 0
    known = {
        str(k)
        for k in db.execute(
            select(File.storage_key).where(File.storage_provider_id == row.id)
        ).scalars().all()
    }
    removed = 0
    for key in adapters.iter_keys(ref, min_age_seconds=min_age_seconds):
        if key in known:
            continue
        try:
            if adapters.delete_object(ref, key):
                removed += 1
        except (StorageNotReady, StorageWriteFailed):
            break
    removed += adapters.sweep_tmp(ref)
    return removed


def verify_files(db: Session, *, provider: StorageProvider | None = None) -> dict:
    """행이 가리키는 파일이 실제로 있고 체크섬이 맞는가. 복원 검증이 부르는 함수다."""
    row = provider or active_provider(db, role=ROLE_OPERATIONAL)
    if row is None:
        return {"checked": 0, "missing": [], "corrupt": []}
    ref = ref_of(row)
    missing: list[str] = []
    corrupt: list[str] = []
    rows = list(
        db.execute(
            select(File).where(File.storage_provider_id == row.id).order_by(File.created_at)
        ).scalars().all()
    )
    for record in rows:
        try:
            data = adapters.read_object(ref, record.storage_key)
        except (StorageNotReady, StorageWriteFailed, ValueError):
            missing.append(record.id)
            continue
        if hashlib.sha256(data).hexdigest() != record.checksum_sha256:
            corrupt.append(record.id)
    return {"checked": len(rows), "missing": missing, "corrupt": corrupt}


# ── 상태 ─────────────────────────────────────────────────────────────────────


def provider_status(provider: StorageProvider) -> dict:
    """저장소 하나의 지금 상태. 화면·health probe·증거 로그가 같은 값을 본다."""
    ref = ref_of(provider)
    state = adapters.state_of(ref)
    out = {
        "id": provider.id,
        "name": provider.name,
        "kind": provider.kind,
        "role": provider.role,
        "enabled": provider.enabled,
        "base_path": provider.base_path,
        "mount_point": provider.mount_point,
        "writable": state.ok,
        "mount": state.as_dict(),
    }
    out.update(adapters.capacity_of(ref) if state.ok else {
        "total_bytes": None, "free_bytes": None, "used_bytes": None,
    })
    return out


def same_device_warning(db: Session) -> str | None:
    """운영과 백업이 같은 장치면 경고 문장, 아니면 None (D-199 16번).

    같은 장치의 백업은 장치가 죽는 순간 함께 죽는다. 「백업이 있다」가 거짓이 되는
    유일한 경우라 화면에서 말해 준다.
    """
    operational = active_provider(db, role=ROLE_OPERATIONAL)
    backup = active_provider(db, role=ROLE_BACKUP)
    if operational is None or backup is None:
        return None
    if same_device(operational.base_path, backup.base_path) is True:
        return "운영 저장소와 백업 저장소가 같은 장치에 있습니다. 장치가 고장 나면 백업도 함께 잃습니다."
    return None


def storage_health(db: Session) -> dict:
    """`/readyz` 와 대시보드가 함께 쓰는 한 벌."""
    providers = list(
        db.execute(select(StorageProvider).order_by(StorageProvider.role, StorageProvider.name))
        .scalars().all()
    )
    items = [provider_status(p) for p in providers]
    operational = [i for i in items if i["role"] == ROLE_OPERATIONAL and i["enabled"]]
    return {
        "providers": items,
        "operational_ok": bool(operational) and all(i["writable"] for i in operational),
        "warning": same_device_warning(db),
        "file_count": int(db.execute(select(func.count()).select_from(File)).scalar_one()),
    }


# ── 내부 ─────────────────────────────────────────────────────────────────────


def _write(ref: ProviderRef, storage_key: str, content: bytes) -> str:
    try:
        return adapters.write_object(ref, storage_key, content)
    except StorageNotReady as exc:
        _log_not_ready(exc)
        raise StorageUnavailableError() from None
    except StorageWriteFailed:
        # 원문(OSError·경로)은 서버 로그에만 남긴다(OPS-05).
        logger.exception("storage: 쓰기 실패 provider=%s key=%s", ref.name, storage_key)
        raise StorageUnavailableError() from None


def _provider_of(db: Session, file_row: File) -> StorageProvider:
    provider = db.get(StorageProvider, file_row.storage_provider_id)
    if provider is None:
        # FK 가 RESTRICT 라 정상 경로로는 못 생긴다. 생겼다면 데이터가 깨진 것이다.
        logger.error("storage: 파일이 없는 저장소를 가리킵니다 file_id=%s", file_row.id)
        raise StorageUnavailableError()
    return provider


def _log_not_ready(exc: StorageNotReady) -> None:
    state = exc.state
    logger.error(
        "storage: 쓰기를 거부했습니다 status=%s path=%s st_dev=%s parent_st_dev=%s fstype=%s",
        state.status, state.path, state.st_dev, state.parent_st_dev, state.fstype,
    )
