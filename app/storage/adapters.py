"""Storage Adapter — 저장소 종류 셋과 **실제 바이트를 쓰는 유일한 자리** (D-199).

## 왜 종류가 장비 이름이 아니라 접근 Protocol 인가

실 NAS 장비 정보가 아직 없다(U9). 장비 이름으로 나누면 그 정보가 오는 날 코드를 고쳐야
하고, 그때 고칠 자리는 「업로드」·「백업」·「첨부」로 흩어져 있다. 접근 Protocol 로 나누면
**설정만 바뀐다** — 마운트는 systemd 가 하고 앱은 마운트포인트 경로만 알기 때문이다.

그래서 셋의 차이는 실은 둘뿐이다:

| kind | 마운트가 필요한가 | 기대 파일시스템 |
|---|---|---|
| `LOCAL` | 아니다. 서버 자기 디스크다 | (안 본다) |
| `NFS` | **그렇다** | `nfs` · `nfs4` |
| `SMB` | **그렇다** | `cifs` · `smb3` |

읽고 쓰는 코드는 셋이 같다. 그래야 「NFS 에서만 나는 버그」가 경로 처리에서 생기지 않는다.

## 커밋은 rename 하나다 (D-199 9번)

쓰다가 죽으면 **부분 파일이 남으면 안 된다.** 그래서 최종 이름에 직접 쓰지 않는다:

    1. 같은 파일시스템의 `.tmp/` 에 임시 이름으로 쓴다
    2. `flush` + `fsync` 로 바이트가 실제로 장치에 닿게 한다
    3. `os.replace` 로 최종 이름에 **한 번에** 올린다
    4. 실패하면 임시 파일을 지운다. 최종 이름은 **한 번도 존재한 적이 없다**

`.tmp/` 가 `base_path` 아래인 것이 중요하다. 다른 파일시스템에 두면 3번이 rename 이
아니라 복사가 되고, 그러면 부분 파일이 다시 생긴다.

## 쓰기 전에 반드시 마운트를 묻는다

`app/storage/mount.py::mount_state` 하나가 그 답을 낸다. 이 파일은 그 답이 `ok` 가
아니면 **쓰지 않고 예외를 던진다.** 판정을 여기서 다시 하지 않는다.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.storage.mount import MountState, capacity, write_target_state

# ── 저장소 종류 ──────────────────────────────────────────────────────────────
KIND_LOCAL = "LOCAL"
KIND_NFS = "NFS"
KIND_SMB = "SMB"
KINDS: tuple[str, ...] = (KIND_LOCAL, KIND_NFS, KIND_SMB)

# ── 역할 ─────────────────────────────────────────────────────────────────────
ROLE_OPERATIONAL = "OPERATIONAL"
ROLE_BACKUP = "BACKUP"
ROLES: tuple[str, ...] = (ROLE_OPERATIONAL, ROLE_BACKUP)

#: 임시 파일이 사는 곳. `base_path` 아래여야 rename 이 rename 으로 남는다.
TMP_DIRNAME = ".tmp"

#: 서버가 만든 저장 키만 받는다. 사용자 입력이 여기 닿을 길은 없지만, 닿았을 때
#: 경로가 뿌리 밖으로 나가지 않게 모양 자체를 좁혀 둔다.
STORAGE_KEY_RE = re.compile(r"^[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{32}(?:\.[a-z0-9]{1,8})?$")


@dataclass(frozen=True)
class KindSpec:
    """저장소 종류 하나의 성질. **이 표가 세 Adapter 의 전부다.**"""

    kind: str
    requires_mount: bool
    fstypes: tuple[str, ...]
    #: systemd `.mount` 유닛의 `Type=`. LOCAL 은 유닛 자체가 없다.
    mount_type: str | None
    label: str


SPECS: dict[str, KindSpec] = {
    KIND_LOCAL: KindSpec(KIND_LOCAL, False, (), None, "서버 로컬 디스크"),
    KIND_NFS: KindSpec(KIND_NFS, True, ("nfs", "nfs4"), "nfs", "NFS 공유"),
    KIND_SMB: KindSpec(KIND_SMB, True, ("cifs", "smb3"), "cifs", "SMB 공유"),
}


def spec_for(kind: str) -> KindSpec:
    spec = SPECS.get((kind or "").upper())
    if spec is None:
        # 호출부(우리 코드)의 버그다. DB CHECK 제약이 모르는 값을 이미 거절한다.
        raise ValueError(f"unknown storage kind: {kind!r}")
    return spec


class StorageNotReady(Exception):
    """마운트 판정이 `ok` 가 아니라 **쓰기를 거부했다** (D-199 13번).

    이것은 「실패」가 아니라 「하지 않았다」이다. 예외에 판정 결과를 그대로 달아 둔다.
    503 으로 바꾸는 자리(`app/storage/service.py`)가 로그에 숫자를 남길 수 있게 한다.
    """

    def __init__(self, state: MountState) -> None:
        super().__init__(f"{state.status}: {state.path}")
        self.state = state


class StorageWriteFailed(Exception):
    """실제 쓰기가 OSError 로 실패했다. 원문은 서버 로그에만 남는다(OPS-05)."""


@dataclass(frozen=True)
class ProviderRef:
    """저장소 하나를 가리키는 값. **ORM 을 안 쓴다.**

    실검증 하네스(`scripts/storage_matrix.py`)가 DB 없이 이 모듈을 그대로 쓴다.
    「제품 코드로 검증했다」가 참이 되려면 검증이 다른 구현을 쓰면 안 된다.
    """

    kind: str
    base_path: str
    mount_point: str | None = None
    name: str = ""

    @property
    def spec(self) -> KindSpec:
        return spec_for(self.kind)

    @property
    def guard_path(self) -> str:
        """마운트를 묻는 자리. NFS/SMB 는 **마운트포인트**이지 `base_path` 가 아니다.

        `base_path` 가 마운트포인트의 하위 디렉터리일 수 있다(공유 하나를 여러 용도로
        나눠 쓰는 경우). 그때 하위 디렉터리에 대고 물으면 「마운트포인트가 아니다」가
        나오므로, 묻는 자리와 쓰는 자리를 구분한다.
        """
        if self.spec.requires_mount:
            return self.mount_point or self.base_path
        return self.base_path


def state_of(ref: ProviderRef, *, mountinfo_text: str | None = None) -> MountState:
    """지금 이 저장소에 써도 되는가. **판정은 `mount.py` 하나가 한다.**

    이 함수가 하는 일은 저장소의 성질(마운트가 필요한가 · 어떤 파일시스템인가)을
    판정 함수에 넘기는 것뿐이다. 조건을 여기서 다시 쓰면 판정이 두 벌이 되고, 그중
    하나가 빠진 날 로컬 디스크에 조용히 쌓인다.
    """
    return write_target_state(
        ref.base_path,
        ref.mount_point,
        require_mount=ref.spec.requires_mount,
        expect_fstypes=ref.spec.fstypes,
        mountinfo_text=mountinfo_text,
    )


def ensure_ready(ref: ProviderRef) -> MountState:
    """쓰기 전 관문. `ok` 가 아니면 **아무것도 하지 않고** 예외를 던진다."""
    state = state_of(ref)
    if not state.ok:
        raise StorageNotReady(state)
    return state


def new_storage_key(*, extension: str = "") -> str:
    """서버가 만드는 저장 키. `ab/cd/<uuid32><ext>`.

    두 자리씩 두 겹으로 나눈다. 한 디렉터리에 수십만 개가 쌓이면 NFS 목록이 느려지고,
    그 느림은 백업·복원처럼 전체를 훑는 작업에서 먼저 드러난다.
    """
    stem = uuid.uuid4().hex
    ext = extension if (not extension or extension.startswith(".")) else f".{extension}"
    return f"{stem[0:2]}/{stem[2:4]}/{stem}{ext}"


def object_path(ref: ProviderRef, storage_key: str) -> Path:
    """저장 키의 실제 경로. 모양이 안 맞거나 뿌리 밖이면 `ValueError`."""
    if not STORAGE_KEY_RE.match(storage_key or ""):
        raise ValueError(f"invalid storage key: {storage_key!r}")
    root = Path(ref.base_path)
    path = root / storage_key
    # 마지막 방어. 키 모양을 이미 좁혔지만, 뿌리 밖으로 나가는 경로는 존재 자체가 사고다.
    try:
        path.resolve().relative_to(root.resolve())
    except (ValueError, OSError) as exc:
        raise ValueError(f"storage key escapes root: {storage_key!r}") from exc
    return path


def write_object(ref: ProviderRef, storage_key: str, content: bytes) -> str:
    """바이트를 쓰고 sha256 을 돌려준다. **최종 이름은 성공했을 때만 생긴다.**

    실패하면 임시 파일을 치우고 예외를 던진다. 부분 파일도, 빈 파일도 남지 않는다.
    """
    ensure_ready(ref)
    final = object_path(ref, storage_key)
    tmp_dir = Path(ref.base_path) / TMP_DIRNAME
    tmp = tmp_dir / f"{uuid.uuid4().hex}.part"
    digest = hashlib.sha256(content).hexdigest()
    try:
        tmp_dir.mkdir(parents=True, exist_ok=True)
        with open(tmp, "wb") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp, final)
        _fsync_dir(final.parent)
    except OSError as exc:
        _discard(tmp)
        raise StorageWriteFailed(str(exc)) from exc
    return digest


def read_object(ref: ProviderRef, storage_key: str) -> bytes:
    """읽기도 마운트를 **다시 묻는다.**

    안 물으면 마운트가 빠진 뒤 「파일이 없습니다」가 나가고, 그 문장은 「지워졌다」와
    구별되지 않는다.
    """
    ensure_ready(ref)
    try:
        return object_path(ref, storage_key).read_bytes()
    except OSError as exc:
        raise StorageWriteFailed(str(exc)) from exc


def object_exists(ref: ProviderRef, storage_key: str) -> bool:
    try:
        return object_path(ref, storage_key).is_file()
    except (ValueError, OSError):
        return False


def delete_object(ref: ProviderRef, storage_key: str) -> bool:
    """지운다. 이미 없으면 False. 없는 것을 지우려 한 것은 오류가 아니다."""
    ensure_ready(ref)
    path = object_path(ref, storage_key)
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise StorageWriteFailed(str(exc)) from exc


def iter_keys(ref: ProviderRef, *, min_age_seconds: int = 0):
    """저장소에 실제로 있는 키 전부. 백업과 고아 청소가 쓴다.

    🔴 `min_age_seconds` 는 **방금 올라온 파일을 고아로 오해하지 않게** 하는 값이다.

    업로드는 바이트를 먼저 쓰고 DB 행을 나중에 만든다(D-250). 그 사이에 고아 청소가
    지나가면 **행이 아직 없는 그 파일**을 「아무도 안 가리킨다」로 읽고 지운다 —
    사용자는 올리기에 성공했다는 화면을 보고, 파일은 이미 없다. 창은 밀리초이지만
    데이터 손실이라 확률로 넘길 성질이 아니다.

    그래서 청소는 **충분히 늙은 파일만** 본다. 백업처럼 전부 훑어야 하는 쪽은 0 을 준다.
    """
    root = Path(ref.base_path)
    if not root.is_dir():
        return
    cutoff = time.time() - max(0, min_age_seconds)
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith(f"{TMP_DIRNAME}/"):
            continue
        if not STORAGE_KEY_RE.match(rel):
            continue
        if min_age_seconds:
            try:
                if path.stat().st_mtime > cutoff:
                    continue
            except OSError:
                continue
        yield rel


def sweep_tmp(ref: ProviderRef, *, older_than_seconds: int = 3600) -> int:
    """죽은 임시 파일을 치운다. 프로세스가 쓰는 중에 죽으면 `.part` 가 남는다.

    최종 이름에는 영향이 없다(그것이 이 설계의 요점이다). 여기서 되찾는 것은 디스크뿐이다.
    """
    tmp_dir = Path(ref.base_path) / TMP_DIRNAME
    if not tmp_dir.is_dir():
        return 0
    cutoff = time.time() - max(0, older_than_seconds)
    removed = 0
    for path in tmp_dir.glob("*.part"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def capacity_of(ref: ProviderRef) -> dict:
    return capacity(ref.base_path)


def _fsync_dir(path: Path) -> None:
    """디렉터리 엔트리를 장치에 밀어 넣는다. 없는 플랫폼(Windows)에서는 그냥 넘어간다."""
    if not hasattr(os, "O_DIRECTORY"):
        return
    try:
        fd = os.open(str(path), os.O_DIRECTORY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _discard(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass
