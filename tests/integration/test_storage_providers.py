"""저장소 설정 API — 「업로드가 어디로 가는가」에 답이 하나여야 한다 (S8 · D-199).

## 이 파일이 지키는 것 셋

1. **역할마다 켜진 저장소는 하나다.** 둘이면 어제 올린 파일과 오늘 올린 파일이 다른
   장치에 있고, 그 사실은 백업을 복원할 때 처음 드러난다.
2. **마운트가 안 붙었으면 그렇다고 말한다.** 「설정이 있다」와 「지금 쓸 수 있다」는
   다른 사실이고, 화면이 그 둘을 같은 것으로 보여 주면 아무도 안 붙은 것을 모른다.
3. **운영과 백업이 같은 장치면 경고한다.** 그 백업은 장치가 죽는 순간 함께 죽는다.
"""

from __future__ import annotations

import pytest

from app.storage import service
from app.storage.models import StorageProvider

pytestmark = pytest.mark.integration


@pytest.fixture()
def local_provider(db, settings):
    provider = service.ensure_default_provider(db, settings)
    db.commit()
    return provider


# ── 권한 ─────────────────────────────────────────────────────────────────────


def test_a_normal_user_cannot_see_the_storage_settings(client, login_as, local_provider):
    """목록은 경로·마운트 소스·용량을 담는다. 그것만으로도 서버 구조가 드러난다."""
    login_as("user")
    assert client.get("/api/storage/providers").status_code == 403
    assert client.get("/api/storage/status").status_code == 403


def test_a_system_admin_can_see_them(client, login_as, local_provider):
    login_as("system_admin")
    response = client.get("/api/storage/providers")
    assert response.status_code == 200, response.text
    names = [i["name"] for i in response.json()["items"]]
    assert local_provider.name in names


def test_an_operator_cannot_change_where_files_land(client, login_as, local_provider):
    """`STORAGE_CONFIGURE` 는 `SYSTEM_ADMIN_ONLY` 다(S5 가 그렇게 고정했다)."""
    csrf = login_as("operator")
    response = client.post(
        "/api/storage/providers",
        json={
            "name": "몰래", "kind": "LOCAL", "role": "OPERATIONAL",
            "base_path": "/tmp/somewhere",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 403


# ── 상태 ─────────────────────────────────────────────────────────────────────


def test_a_local_provider_reports_itself_writable(client, login_as, local_provider):
    login_as("system_admin")
    item = client.get("/api/storage/providers").json()["items"][0]
    assert item["writable"] is True
    assert item["mount"]["status"] == "ok"
    assert item["total_bytes"] is None or item["total_bytes"] > 0


def test_a_remote_provider_that_is_not_mounted_says_so(client, login_as, db, tmp_path):
    """🔴 「설정이 있다」와 「지금 쓸 수 있다」는 다른 사실이다."""
    mountpoint = tmp_path / "nas"
    mountpoint.mkdir()
    db.add(StorageProvider(
        name="붙지 않은 NAS", kind="NFS", role="BACKUP",
        base_path=mountpoint.as_posix(), mount_point=mountpoint.as_posix(),
        config_json='{"source": "nas:/export"}',
    ))
    db.commit()

    login_as("system_admin")
    items = {i["name"]: i for i in client.get("/api/storage/providers").json()["items"]}
    nas = items["붙지 않은 NAS"]
    assert nas["writable"] is False
    assert nas["mount"]["status"] == "not_mounted"
    assert "로컬 디스크" in nas["mount"]["detail"]


def test_the_probe_tells_the_admin_which_unit_to_start(client, login_as, db, tmp_path):
    """안 붙어 있을 때 관리자가 다음에 칠 명령이 `systemctl start <그 유닛>` 이다."""
    mountpoint = tmp_path / "smb"
    mountpoint.mkdir()
    provider = StorageProvider(
        name="SMB 공유", kind="SMB", role="BACKUP",
        base_path=mountpoint.as_posix(), mount_point=mountpoint.as_posix(),
        config_json='{"source": "//nas/share"}',
    )
    db.add(provider)
    db.commit()

    csrf = login_as("system_admin")
    response = client.post(
        f"/api/storage/providers/{provider.id}/probe", headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 200, response.text
    assert response.json()["mount_unit"].endswith(".mount")


# ── 만들기와 고치기 ──────────────────────────────────────────────────────────


def test_a_second_enabled_provider_for_the_same_role_is_refused(
    client, login_as, local_provider, tmp_path
):
    """🔴 자동으로 옛것을 끄지 않는다. 업로드가 어디로 가는지 바뀌는 변경이라,
    「끄는 것」을 사람이 실제로 결정해야 한다."""
    csrf = login_as("system_admin")
    response = client.post(
        "/api/storage/providers",
        json={
            "name": "두 번째", "kind": "LOCAL", "role": "OPERATIONAL",
            "base_path": (tmp_path / "other").as_posix(),
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 409, response.text
    assert local_provider.name in response.json()["error"]["message"]


def test_a_backup_provider_can_stand_next_to_the_operational_one(
    client, login_as, local_provider, tmp_path
):
    """반대쪽. 전부 거절하는 검사도 위 시험은 통과한다."""
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    csrf = login_as("system_admin")
    response = client.post(
        "/api/storage/providers",
        json={
            "name": "백업 저장소", "kind": "LOCAL", "role": "BACKUP",
            "base_path": backup_dir.as_posix(),
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "BACKUP"


def test_a_remote_provider_without_a_mountpoint_is_refused_with_a_reason(
    client, login_as, local_provider
):
    """DB CHECK 에만 맡기면 사용자는 500 을 보고 무엇이 틀렸는지 알 수 없다."""
    csrf = login_as("system_admin")
    response = client.post(
        "/api/storage/providers",
        json={
            "name": "마운트 없는 NFS", "kind": "NFS", "role": "BACKUP",
            "base_path": "/mnt/nas/files",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422, response.text
    assert "마운트포인트" in response.json()["error"]["message"]


def test_a_write_path_outside_the_mountpoint_is_refused(client, login_as, local_provider):
    """🔴 가드가 물어보는 자리와 실제로 쓰는 자리가 다르면, 마운트가 붙어 있어도
    로컬 디스크에 쌓인다."""
    csrf = login_as("system_admin")
    response = client.post(
        "/api/storage/providers",
        json={
            "name": "엇갈린 경로", "kind": "NFS", "role": "BACKUP",
            "base_path": "/var/lib/elsewhere", "mount_point": "/mnt/nas",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422, response.text
    assert "마운트포인트 아래" in response.json()["error"]["message"]


def test_updating_a_provider_takes_the_optimistic_lock(client, login_as, local_provider):
    """S6 이 정한 규약 그대로다(D-240). 같은 충돌을 자원마다 다른 이름으로 다루면
    프런트가 여러 벌의 처리를 갖게 된다."""
    csrf = login_as("system_admin")
    stale = local_provider.version
    ok = client.patch(
        f"/api/storage/providers/{local_provider.id}",
        json={"name": "이름 변경", "base_version": stale},
        headers={"X-CSRF-Token": csrf},
    )
    assert ok.status_code == 200, ok.text

    conflict = client.patch(
        f"/api/storage/providers/{local_provider.id}",
        json={"name": "덮어쓰기", "base_version": stale},
        headers={"X-CSRF-Token": csrf},
    )
    assert conflict.status_code == 409


# ── 운영과 백업이 같은 장치 (D-199 16번) ─────────────────────────────────────


def test_the_same_device_for_both_roles_is_a_warning(client, login_as, db, settings, tmp_path):
    """그 백업은 장치가 죽는 순간 함께 죽는다. 「백업이 있다」가 거짓이 되는 유일한 경우다."""
    service.ensure_default_provider(db, settings)
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    db.add(StorageProvider(
        name="같은 디스크 백업", kind="LOCAL", role="BACKUP",
        base_path=backup_dir.as_posix(),
    ))
    db.commit()

    login_as("system_admin")
    body = client.get("/api/storage/providers").json()
    assert body["warning"] is not None
    assert "같은 장치" in body["warning"]


def test_with_no_backup_provider_there_is_no_warning(client, login_as, local_provider):
    """경고를 늘 켜 두면 사람이 안 읽는다."""
    login_as("system_admin")
    assert client.get("/api/storage/providers").json()["warning"] is None
