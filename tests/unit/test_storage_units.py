"""마운트 유닛 — 이름은 **경로에서 기계적으로** 나온다 (S8 · D-199).

## 왜 이름을 우리가 지으면 안 되는가

systemd 는 `.mount` 유닛 이름을 마운트포인트에서 정한다. 이름을 따로 지으면 systemd 가
그 유닛을 **그 경로의 마운트로 인정하지 않는다** — `systemctl start` 는 되는데
`RequiresMountsFor=` 가 안 걸리는, 원인을 찾기 어려운 상태가 된다. 그리고 부팅 경합에서
앱이 마운트보다 먼저 뜨고, 그 창에 들어온 업로드가 로컬 디스크에 쌓인다.
"""

from __future__ import annotations

import pytest

from app.storage.adapters import ProviderRef
from app.storage.units import DROPIN_NAME, escape_path, render_dropin, render_mount_unit, unit_name

pytestmark = pytest.mark.unit


# ── 이름 ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/var/lib/clovirassist/files/nas", "var-lib-clovirassist-files-nas"),
        ("/mnt/nas", "mnt-nas"),
        # `-` 는 구분자로 쓰이므로 이스케이프한다. 안 하면 `/mnt/a-b` 와 `/mnt/a/b` 가
        # 같은 유닛 이름이 되고, 그 둘은 다른 마운트다.
        ("/mnt/my-share", r"mnt-my\x2dshare"),
        ("/srv/data.d", "srv-data.d"),
        ("/", "-"),
        # 끝의 `/` 와 중복 `/` 는 같은 경로다. 다른 이름이 나오면 유닛이 둘로 갈린다.
        ("/mnt/nas/", "mnt-nas"),
        ("/mnt//nas", "mnt-nas"),
    ],
)
def test_the_unit_name_follows_systemd_escaping(path, expected):
    assert escape_path(path) == expected
    assert unit_name(path) == f"{expected}.mount"


def test_a_path_with_a_space_is_escaped_not_broken():
    """공백이 그대로 들어가면 유닛 파일 이름이 깨진다."""
    assert escape_path("/mnt/my share") == r"mnt-my\x20share"


# ── 유닛 본문 ────────────────────────────────────────────────────────────────


def _nfs() -> ProviderRef:
    return ProviderRef(
        kind="NFS", base_path="/mnt/nas/files", mount_point="/mnt/nas", name="사내 NAS"
    )


def test_the_nfs_unit_names_the_mountpoint_and_the_type():
    body = render_mount_unit(_nfs(), source="nas.example:/export")
    assert "Where=/mnt/nas" in body
    assert "What=nas.example:/export" in body
    assert "Type=nfs" in body
    assert "WantedBy=multi-user.target" in body, "재부팅 뒤 자동으로 안 붙는다"


def test_every_unit_waits_for_the_network():
    """`_netdev` 가 없으면 부팅이 네트워크보다 먼저 마운트를 시도하고, 실패한 뒤
    다시 시도하지 않는다."""
    body = render_mount_unit(_nfs(), source="nas:/export")
    assert "_netdev" in body
    assert "After=network-online.target" in body


def test_an_nfs_mount_fails_instead_of_hanging_forever():
    """🔴 S8 실검증에서 실제로 밟았다 — 기본값(`hard,timeo=600`)에서는 서버가 죽으면
    쓰기 한 번이 **5분이 지나도 안 돌아온다.**

    그 상태에서는 「Storage unavailable 은 503 이지 500 이 아니다」(D-199 7번)가
    성립할 수가 없다. 503 도 500 도 안 나가고 요청이 영영 안 끝난다.
    """
    body = render_mount_unit(_nfs(), source="nas:/export")
    options = [ln for ln in body.splitlines() if ln.startswith("Options=")][0]
    assert "soft" in options, options
    assert "timeo=" in options and "retrans=" in options, options


def test_an_operator_who_chose_hard_keeps_it():
    """운영자가 적은 값은 덮지 않는다. `hard` 는 판단이지 실수가 아니다."""
    body = render_mount_unit(_nfs(), source="nas:/export", options="hard,timeo=900")
    options = [ln for ln in body.splitlines() if ln.startswith("Options=")][0]
    assert "hard" in options and "soft" not in options
    assert "timeo=900" in options and "timeo=50" not in options


def test_an_smb_mount_is_owned_by_the_service_account():
    """🔴 S8 실검증에서 실제로 밟았다 — `uid=0,gid=0` 으로 붙은 공유에서 서비스 계정이
    **아무것도 못 썼다.**

    cifs 는 마운트할 때 정한 uid/gid 로 모든 파일의 주인이 고정되고 `chown` 도 안 받는다.
    그런데 마운트 자체는 멀쩡해서 `st_dev` 가드도 fstype 검사도 전부 통과한다 —
    증상은 「올릴 때마다 503」뿐이고 원인은 옵션 한 줄에 있다.
    """
    from app.core.product import SERVICE_USER

    ref = ProviderRef(kind="SMB", base_path="/mnt/smb", mount_point="/mnt/smb")
    options = [
        ln for ln in render_mount_unit(ref, source="//nas/s").splitlines()
        if ln.startswith("Options=")
    ][0]
    assert f"uid={SERVICE_USER}" in options, options
    assert f"gid={SERVICE_USER}" in options, options
    # 첨부는 남이 읽으면 안 된다. 기본이 0644 면 같은 서버의 다른 계정이 전부 읽는다.
    assert "file_mode=0640" in options and "dir_mode=0750" in options, options


def test_an_operator_who_set_the_owner_keeps_it():
    ref = ProviderRef(kind="SMB", base_path="/mnt/smb", mount_point="/mnt/smb")
    options = [
        ln for ln in render_mount_unit(ref, source="//nas/s", options="uid=2000,gid=2000")
        .splitlines() if ln.startswith("Options=")
    ][0]
    assert "uid=2000" in options and "uid=clovirassist" not in options


def test_nfs_does_not_get_the_cifs_ownership_knobs():
    """`uid=`/`file_mode=` 는 cifs 의 이름이다. NFS 에 넘기면 마운트가 통째로 실패한다."""
    options = [
        ln for ln in render_mount_unit(_nfs(), source="nas:/e").splitlines()
        if ln.startswith("Options=")
    ][0]
    assert "uid=" not in options and "file_mode=" not in options


def test_smb_does_not_get_the_nfs_timeout_knobs():
    """`timeo` 는 NFS 의 이름이다. cifs 에 넘기면 마운트가 통째로 실패한다."""
    ref = ProviderRef(kind="SMB", base_path="/mnt/smb", mount_point="/mnt/smb")
    options = [
        ln for ln in render_mount_unit(ref, source="//nas/s").splitlines()
        if ln.startswith("Options=")
    ][0]
    assert "timeo=" not in options and "retrans=" not in options


def test_a_smb_unit_passes_credentials_by_path_never_by_value():
    """🔴 유닛 파일은 0644 로 깔린다. 비밀번호를 여기 적으면 모든 로컬 사용자가 읽는다."""
    ref = ProviderRef(kind="SMB", base_path="/mnt/smb", mount_point="/mnt/smb", name="공유")
    body = render_mount_unit(
        ref, source="//nas/share", options="uid=1000",
        credentials_path="/etc/clovirassist/secrets/smb_nas",
    )
    assert "Type=cifs" in body
    assert "credentials=/etc/clovirassist/secrets/smb_nas" in body
    assert "password" not in body.lower()


def test_a_local_provider_has_no_mount_unit():
    """로컬 디스크에 마운트 유닛을 만들면 systemd 가 그 경로를 마운트로 관리하려 든다."""
    ref = ProviderRef(kind="LOCAL", base_path="/var/lib/clovirassist/files")
    with pytest.raises(ValueError):
        render_mount_unit(ref, source="")


# ── drop-in ──────────────────────────────────────────────────────────────────


def test_the_dropin_lists_every_mountpoint():
    body = render_dropin(["/mnt/nas", "/mnt/smb"])
    assert "RequiresMountsFor=/mnt/nas /mnt/smb" in body


def test_the_dropin_clears_the_old_value_first():
    """🔴 systemd 의 `RequiresMountsFor=` 는 **누적**된다. 빈 지시자로 지우지 않으면
    저장소를 옮긴 뒤에도 옛 경로를 영원히 기다린다."""
    body = render_dropin(["/mnt/new"])
    lines = [ln.strip() for ln in body.splitlines() if ln.strip().startswith("RequiresMountsFor")]
    assert lines[0] == "RequiresMountsFor="
    assert lines[1] == "RequiresMountsFor=/mnt/new"


def test_with_no_remote_storage_the_dropin_only_clears():
    """파일을 아예 안 만들면 예전에 깔린 drop-in 이 남은 설치에서 옛 경로를 계속 기다린다."""
    body = render_dropin([])
    lines = [ln.strip() for ln in body.splitlines() if ln.strip().startswith("RequiresMountsFor")]
    assert lines == ["RequiresMountsFor="]


def test_the_dropin_filename_is_stable():
    """설치가 매번 다른 이름을 쓰면 옛 파일이 쌓이고, 그중 하나가 여전히 유효하다."""
    assert DROPIN_NAME == "10-storage-mounts.conf"
