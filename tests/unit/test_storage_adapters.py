"""Adapter — 커밋은 rename 하나이고, 실패하면 **아무것도 안 남는다** (S8 · D-199 9번).

## 이 시험이 지키는 사실

쓰다가 죽었는데 최종 이름에 반쪽짜리 파일이 남아 있으면, 그 파일은 크기도 있고 열리기도
한다. 체크섬을 다시 세어 보기 전에는 아무도 모른다. 그래서 최종 이름은 **성공했을 때만**
생긴다 — 임시 이름에 쓰고 `os.replace` 로 한 번에 올린다.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from app.storage import adapters
from app.storage.adapters import ProviderRef

pytestmark = pytest.mark.unit


@pytest.fixture()
def local(tmp_path) -> ProviderRef:
    base = tmp_path / "files"
    base.mkdir()
    return ProviderRef(kind=adapters.KIND_LOCAL, base_path=str(base), name="시험 저장소")


# ── 종류 셋 ──────────────────────────────────────────────────────────────────


def test_the_three_kinds_differ_only_in_whether_a_mount_is_required():
    assert adapters.spec_for("LOCAL").requires_mount is False
    assert adapters.spec_for("NFS").requires_mount is True
    assert adapters.spec_for("SMB").requires_mount is True
    assert "nfs4" in adapters.spec_for("NFS").fstypes
    assert "cifs" in adapters.spec_for("SMB").fstypes


def test_an_unknown_kind_is_a_programming_error_not_a_silent_local():
    """모르는 종류를 LOCAL 로 떨어뜨리면 원격 저장소가 로컬로 조용히 바뀐다."""
    with pytest.raises(ValueError):
        adapters.spec_for("S3")


def test_a_remote_provider_asks_the_mountpoint_not_the_write_path():
    ref = ProviderRef(kind="NFS", base_path="/mnt/nas/files", mount_point="/mnt/nas")
    assert ref.guard_path == "/mnt/nas"
    local = ProviderRef(kind="LOCAL", base_path="/var/lib/x/files")
    assert local.guard_path == "/var/lib/x/files"


# ── 저장 키 ──────────────────────────────────────────────────────────────────


def test_a_storage_key_is_sharded_and_carries_the_extension():
    key = adapters.new_storage_key(extension=".pdf")
    assert adapters.STORAGE_KEY_RE.match(key), key
    assert key.endswith(".pdf")
    assert key[2] == "/" and key[5] == "/"


def test_a_key_without_an_extension_is_still_valid():
    assert adapters.STORAGE_KEY_RE.match(adapters.new_storage_key())


@pytest.mark.parametrize(
    "key",
    [
        "../../etc/passwd",
        "ab/cd/../../../etc/passwd",
        "/etc/passwd",
        "ab/cd/ef.png",           # 이름이 uuid 모양이 아니다
        "AB/CD/" + "0" * 32,      # 대문자
        "",
    ],
)
def test_a_key_that_is_not_ours_never_resolves_to_a_path(local, key):
    """사용자 입력이 여기 닿을 길은 없다. 닿았을 때 뿌리 밖으로 나가지 않게 모양을 좁힌다."""
    with pytest.raises(ValueError):
        adapters.object_path(local, key)


# ── 커밋 ─────────────────────────────────────────────────────────────────────


def test_a_written_object_reads_back_with_the_same_checksum(local):
    key = adapters.new_storage_key(extension=".txt")
    digest = adapters.write_object(local, key, b"hello storage")
    assert digest == hashlib.sha256(b"hello storage").hexdigest()
    assert adapters.read_object(local, key) == b"hello storage"
    assert adapters.object_exists(local, key)


def test_nothing_is_left_behind_when_the_write_fails(local, monkeypatch):
    """🔴 이것이 이 파일의 이유다 — 부분 파일도, 빈 파일도, 임시 파일도 남지 않는다."""
    key = adapters.new_storage_key(extension=".txt")

    real_replace = os.replace

    def boom(src, dst):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(adapters.StorageWriteFailed):
        adapters.write_object(local, key, b"x" * 1024)
    monkeypatch.setattr(os, "replace", real_replace)

    assert not adapters.object_exists(local, key), "최종 이름에 반쪽짜리가 남았다"
    tmp_dir = Path(local.base_path) / adapters.TMP_DIRNAME
    assert list(tmp_dir.glob("*.part")) == [], "임시 파일이 남았다"


def test_the_temp_file_lives_on_the_same_filesystem_as_the_target(local):
    """다른 파일시스템에 두면 `os.replace` 가 rename 이 아니라 복사가 되고,
    그러면 부분 파일이 다시 생긴다."""
    key = adapters.new_storage_key()
    adapters.write_object(local, key, b"z")
    tmp_dir = Path(local.base_path) / adapters.TMP_DIRNAME
    assert tmp_dir.is_dir()
    assert tmp_dir.parent == Path(local.base_path)


def test_overwriting_the_same_key_is_atomic(local):
    key = adapters.new_storage_key(extension=".txt")
    adapters.write_object(local, key, b"first")
    adapters.write_object(local, key, b"second")
    assert adapters.read_object(local, key) == b"second"


# ── 삭제와 청소 ──────────────────────────────────────────────────────────────


def test_deleting_something_that_is_already_gone_is_not_an_error(local):
    key = adapters.new_storage_key()
    adapters.write_object(local, key, b"a")
    assert adapters.delete_object(local, key) is True
    assert adapters.delete_object(local, key) is False


def test_iter_keys_lists_stored_objects_and_skips_the_temp_dir(local):
    keys = {adapters.new_storage_key(extension=".txt") for _ in range(3)}
    for key in keys:
        adapters.write_object(local, key, b"x")
    (Path(local.base_path) / adapters.TMP_DIRNAME).mkdir(exist_ok=True)
    (Path(local.base_path) / adapters.TMP_DIRNAME / "leftover.part").write_bytes(b"y")
    assert set(adapters.iter_keys(local)) == keys


def test_iter_keys_can_skip_files_that_are_too_young(local):
    """🔴 고아 청소가 **방금 올라온 파일**을 지우지 않게 하는 손잡이다.

    업로드는 바이트를 먼저 쓰고 DB 행을 나중에 만든다(D-250) — 그 사이의 파일은
    정상인데도 가리키는 행이 없다.
    """
    fresh = adapters.new_storage_key(extension=".txt")
    adapters.write_object(local, fresh, b"just arrived")
    old = adapters.new_storage_key(extension=".txt")
    adapters.write_object(local, old, b"long ago")
    os.utime(adapters.object_path(local, old), (0, 0))

    assert set(adapters.iter_keys(local, min_age_seconds=3600)) == {old}
    # 상한을 0 으로 주면 전부 본다 — 백업처럼 전량을 훑는 쪽이 그렇게 부른다.
    assert set(adapters.iter_keys(local, min_age_seconds=0)) == {fresh, old}


def test_sweep_removes_only_old_temp_files(local):
    tmp_dir = Path(local.base_path) / adapters.TMP_DIRNAME
    tmp_dir.mkdir(exist_ok=True)
    old = tmp_dir / "old.part"
    old.write_bytes(b"x")
    os.utime(old, (0, 0))
    fresh = tmp_dir / "fresh.part"
    fresh.write_bytes(b"x")

    # 지금 도는 업로드의 임시 파일을 치우면 그 업로드가 실패한다.
    assert adapters.sweep_tmp(local, older_than_seconds=3600) == 1
    assert not old.exists()
    assert fresh.exists()


# ── 마운트가 안 붙었으면 쓰지 않는다 ────────────────────────────────────────


def test_a_remote_provider_that_is_not_mounted_refuses_before_touching_the_disk(tmp_path):
    """거부는 「실패」가 아니라 「하지 않았다」다. 디렉터리에 아무것도 안 생겨야 한다."""
    mountpoint = tmp_path / "nas"
    mountpoint.mkdir()
    ref = ProviderRef(kind="NFS", base_path=str(mountpoint), mount_point=str(mountpoint))
    key = adapters.new_storage_key()
    with pytest.raises(adapters.StorageNotReady) as exc:
        adapters.write_object(ref, key, b"x")
    assert exc.value.state.status == "not_mounted"
    assert list(mountpoint.iterdir()) == [], "거부했는데 디렉터리에 흔적이 남았다"


def test_reading_also_refuses_when_the_mount_is_gone(tmp_path, monkeypatch):
    """안 물으면 마운트가 빠진 뒤 「파일이 없습니다」가 나가고, 그 문장은 「지워졌다」와
    구별되지 않는다."""
    mountpoint = tmp_path / "nas"
    mountpoint.mkdir()
    ref = ProviderRef(kind="NFS", base_path=str(mountpoint), mount_point=str(mountpoint))
    key = adapters.new_storage_key()

    # 붙어 있는 동안에는 쓰고 읽힌다.
    real = adapters.write_target_state
    monkeypatch.setattr(
        adapters, "write_target_state",
        lambda *a, **k: real(*a, **{**k, "require_mount": False}),
    )
    adapters.write_object(ref, key, b"payload")
    assert adapters.read_object(ref, key) == b"payload"

    # 마운트가 빠지면 읽기도 거부한다.
    monkeypatch.setattr(adapters, "write_target_state", real)
    with pytest.raises(adapters.StorageNotReady):
        adapters.read_object(ref, key)
