"""마운트 가드 — **가장 조용한 저장소 사고**를 막는 한 함수 (S8 · D-199 13번).

## 이 시험이 지키는 사실

NFS 서버가 안 떠 있어도 `/var/lib/clovirassist/files/nas` 는 사라지지 않는다. 로컬
디스크의 빈 디렉터리로 남고, 앱은 거기에 잘 쓰고, 체크섬도 맞고, 며칠 뒤 마운트가
붙는 순간 그 파일들이 한꺼번에 안 보이게 된다. **오류는 한 번도 나지 않는다.**

## 양방향으로 본다

「거절한다」만 확인하면 **전부 거절하는 가드**도 통과하고, 그 상태에서는 아무것도 못
올린다. 그래서 각 단정에 「정상 상태는 통과한다」를 함께 둔다.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.storage import mount

pytestmark = pytest.mark.unit


def _mountinfo(mountpoint: Path, fstype: str, source: str) -> str:
    """실제 `/proc/self/mountinfo` 한 줄과 같은 모양.

    필드 수가 가변이라(선택 필드가 `-` 앞에 온다) 파서가 `-` 를 기준으로 나눈다.
    그 성질을 시험이 실제로 밟게 하려고 선택 필드(`shared:1`)를 넣어 둔다.
    """
    return (
        "25 1 259:1 / / rw,relatime shared:1 - ext4 /dev/root rw\n"
        f"36 25 0:52 / {mountpoint.as_posix()} rw,relatime shared:9 - {fstype} {source} rw,vers=4.2\n"
    )


# ── mountinfo 파싱 ───────────────────────────────────────────────────────────


def test_mountinfo_reads_the_mountpoint_and_the_filesystem(tmp_path):
    entries = mount.read_mountinfo(_mountinfo(tmp_path, "nfs4", "nas.example:/export"))
    assert ("/", "ext4", "/dev/root") in entries
    assert (tmp_path.as_posix(), "nfs4", "nas.example:/export") in entries


def test_mountinfo_unescapes_spaces_in_the_mountpoint():
    """공백은 `\\040` 으로 들어온다. 안 풀면 그 마운트는 영원히 「없는 것」이 된다."""
    text = "36 25 0:52 / /srv/my\\040share rw - cifs //nas/s rw\n"
    assert mount.read_mountinfo(text) == [("/srv/my share", "cifs", "//nas/s")]


def test_mountinfo_ignores_lines_without_the_separator():
    """잘린 줄에서 죽으면 가드 전체가 죽는다. 못 읽는 줄은 없는 줄이다."""
    assert mount.read_mountinfo("garbage without dash\n") == []


def test_a_missing_mountinfo_is_an_empty_list_not_a_crash(monkeypatch):
    monkeypatch.setattr(mount, "MOUNTINFO", "/nonexistent/mountinfo")
    assert mount.read_mountinfo() == []


# ── 판정: 마운트가 필요한 저장소 ─────────────────────────────────────────────


def test_a_mounted_share_is_ok(tmp_path):
    text = _mountinfo(tmp_path, "nfs4", "nas.example:/export")
    state = mount.mount_state(
        tmp_path, require_mount=True, expect_fstypes=("nfs", "nfs4"), mountinfo_text=text
    )
    assert state.ok and state.status == mount.MOUNT_OK
    assert state.fstype == "nfs4"
    assert state.source == "nas.example:/export"


def test_an_unmounted_directory_is_refused(tmp_path):
    """🔴 이것이 이 파일의 이유다. 디렉터리는 있고, 쓸 수도 있고, 아무 오류도 안 난다."""
    empty = tmp_path / "nas"
    empty.mkdir()
    state = mount.mount_state(
        empty, require_mount=True, expect_fstypes=("nfs", "nfs4"),
        mountinfo_text=_mountinfo(tmp_path, "ext4", "/dev/root"),
    )
    assert not state.ok
    assert state.status == mount.MOUNT_NOT_MOUNTED
    assert "로컬 디스크" in state.detail


def test_the_parent_being_mounted_is_not_this_path_being_mounted(tmp_path):
    """부모가 마운트포인트인 것은 「이 자리에 무언가 붙었다」가 아니다.

    이 구별이 없으면 마운트 아래 하위 디렉터리를 저장 경로로 준 설정이 전부
    「마운트됨」으로 읽히고, 마운트가 빠진 날 그 아래에 그대로 쌓인다.
    """
    child = tmp_path / "sub"
    child.mkdir()
    text = _mountinfo(tmp_path, "nfs4", "nas.example:/export")
    assert mount.mountinfo_entry(child, text=text) is None
    state = mount.mount_state(child, require_mount=True, mountinfo_text=text)
    assert state.status == mount.MOUNT_NOT_MOUNTED


def test_a_share_of_the_wrong_kind_is_refused(tmp_path):
    """SMB 자리에 NFS 가 붙어 있으면 설정이 틀린 것이다. 「붙어 있다」로 넘기면
    옮겨 간 뒤에도 옛 공유를 계속 쓴다."""
    state = mount.mount_state(
        tmp_path, require_mount=True, expect_fstypes=("cifs", "smb3"),
        mountinfo_text=_mountinfo(tmp_path, "nfs4", "nas.example:/export"),
    )
    assert state.status == mount.MOUNT_WRONG_FSTYPE
    assert "nfs4" in state.detail


def test_a_missing_path_is_missing_not_unmounted(tmp_path):
    state = mount.mount_state(tmp_path / "nope", require_mount=True, mountinfo_text="")
    assert state.status == mount.MOUNT_MISSING


def test_a_file_where_a_directory_belongs_is_refused(tmp_path):
    victim = tmp_path / "afile"
    victim.write_bytes(b"x")
    state = mount.mount_state(victim, require_mount=True, mountinfo_text="")
    assert state.status == mount.MOUNT_NOT_DIR


# ── 판정: 로컬 저장소 ────────────────────────────────────────────────────────


def test_a_local_directory_does_not_need_a_mount(tmp_path):
    state = mount.mount_state(tmp_path, require_mount=False, mountinfo_text="")
    assert state.ok
    assert state.st_dev is not None


def test_a_missing_local_directory_is_still_refused(tmp_path):
    """로컬이라고 아무 경로나 통과하지 않는다. 없는 경로에 쓰면 앱이 만들어 버린다."""
    state = mount.mount_state(tmp_path / "gone", require_mount=False, mountinfo_text="")
    assert not state.ok


# ── mountinfo 를 못 읽는 환경: `st_dev` 가 답한다 ────────────────────────────


def test_without_mountinfo_the_device_comparison_decides(tmp_path, monkeypatch):
    """개발용 Windows·축소된 컨테이너에는 `/proc` 이 없다. 그때도 판정은 있어야 한다."""
    child = tmp_path / "nas"
    child.mkdir()
    # 부모와 같은 장치 = 아무것도 안 붙었다.
    state = mount.mount_state(child, require_mount=True, mountinfo_text="")
    assert state.status == mount.MOUNT_NOT_MOUNTED

    # 반대쪽: 장치가 다르면 붙은 것으로 본다.
    real = mount.device_of
    monkeypatch.setattr(
        mount, "device_of",
        lambda p: 9999 if os.path.normpath(str(p)) == os.path.normpath(str(child)) else real(p),
    )
    state = mount.mount_state(child, require_mount=True, mountinfo_text="")
    assert state.ok


# ── 쓰기 경로까지 본다 ───────────────────────────────────────────────────────


def test_the_write_path_must_sit_on_the_mounted_device(tmp_path, monkeypatch):
    """마운트는 붙었는데 **저장 경로가 그 장치 위가 아닌** 경우를 잡는다.

    마운트가 붙기 전에 만들어진 하위 디렉터리가 정확히 이 모양이다 — 마운트에 덮여
    보이지 않게 되고, 그 안의 파일도 함께 사라진 것처럼 보인다.
    """
    mountpoint = tmp_path / "nas"
    mountpoint.mkdir()
    base = mountpoint / "files"
    base.mkdir()
    text = _mountinfo(mountpoint, "nfs4", "nas:/export")

    # 정상: 둘이 같은 장치다.
    good = mount.write_target_state(
        base, mountpoint, require_mount=True, expect_fstypes=("nfs4",), mountinfo_text=text
    )
    assert good.ok

    # 이상: 저장 경로만 다른 장치다.
    real = mount.device_of
    monkeypatch.setattr(
        mount, "device_of",
        lambda p: 4242 if os.path.normpath(str(p)) == os.path.normpath(str(base)) else real(p),
    )
    bad = mount.write_target_state(
        base, mountpoint, require_mount=True, expect_fstypes=("nfs4",), mountinfo_text=text
    )
    assert not bad.ok
    assert "마운트된 장치 위에 있지 않습니다" in bad.detail


# ── 운영과 백업이 같은 장치인가 (D-199 16번) ─────────────────────────────────


def test_two_paths_on_the_same_disk_are_reported_as_the_same_device(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    assert mount.same_device(a, b) is True


def test_an_unreadable_path_answers_unknown_not_false(tmp_path):
    """모르는 것을 「다르다」로 답하면 경고가 조용히 사라진다."""
    assert mount.same_device(tmp_path, tmp_path / "gone") is None


# ── 용량 ─────────────────────────────────────────────────────────────────────


def test_capacity_never_raises(tmp_path):
    """이 값은 화면과 증거 로그가 쓴다. 여기서 죽으면 대시보드가 통째로 죽는다."""
    good = mount.capacity(tmp_path)
    assert set(good) == {"total_bytes", "free_bytes", "used_bytes"}
    missing = mount.capacity(tmp_path / "gone")
    assert missing["total_bytes"] is None
