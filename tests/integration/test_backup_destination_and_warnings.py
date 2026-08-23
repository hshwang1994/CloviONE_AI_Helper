"""백업 세트가 **백업 저장소로 간다**, 그리고 갈 곳이 없으면 그렇게 말한다 (S12 · D-204 16번).

`data_dir/exports/` 는 앱이 사는 그 디스크다. 그 디스크가 죽는 것이 백업을 만드는 이유의
절반인데, 백업이 같은 디스크에만 있으면 그 절반에 대해 아무 대비가 없다.

여기서 못박는 것:

* 백업 저장소가 있으면 세트가 **거기에도** 생기고, 저쪽 바이트가 이쪽과 같다.
* **매니페스트가 함께 간다.** 사본만 들고 있는 서버에서 「무엇이 안 담겼나」를 읽을 수
  있어야 한다. 순서를 잘못 짜면 매니페스트를 쓰기 전에 복사가 끝나 이 파일만 빠진다.
* 백업 저장소가 **없으면** 경고가 붙는다. 「사본을 0건 보냈다」와 「보낼 곳이 없다」는
  다른 사실이고, 같은 모양으로 보고하면 아무도 설정하지 않는다.
* 보존이 로컬 세트를 지우면 **저쪽 사본도** 지운다. 안 지우면 백업 저장소만 무한히 자라고,
  그 사실은 그 저장소가 찰 때 처음 드러난다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.backups import destination as destination_mod
from app.backups import manifest as manifest_mod
from app.backups.service import apply_retention, backup_warnings, run_backup
from app.storage import service as storage_service
from app.storage.models import StorageProvider

pytestmark = pytest.mark.integration


@pytest.fixture()
def backup_store(db, settings, tmp_path):
    """켜져 있는 `role=BACKUP` 저장소 하나 — 운영 저장소와 **다른** 디렉터리."""
    storage_service.ensure_default_provider(db, settings)
    root = tmp_path / "backup-store"
    root.mkdir()
    provider = StorageProvider(
        name="백업 NAS", kind="LOCAL", role="BACKUP", base_path=root.as_posix()
    )
    db.add(provider)
    db.commit()
    return provider


def _copied_set(provider, set_name: str) -> Path:
    return Path(provider.base_path) / destination_mod.SET_ROOT / set_name


# ── 사본이 실제로 간다 ───────────────────────────────────────────────────────


def test_the_set_lands_on_the_backup_store_byte_for_byte(
    db, settings, fake_clock, stub_pg_dump, backup_store
):
    row = run_backup(db, settings, created_by=None, now=fake_clock.now())
    db.commit()

    local = Path(row.path)
    remote = _copied_set(backup_store, local.name)
    assert remote.is_dir(), "백업 저장소에 세트가 안 생겼다"
    for entry in sorted(local.iterdir()):
        assert (remote / entry.name).read_bytes() == entry.read_bytes(), entry.name


def test_the_manifest_travels_with_the_copy(
    db, settings, fake_clock, stub_pg_dump, backup_store
):
    """🔴 사본만 들고 있는 서버에서 **범위를 읽을 수 있어야** 한다.

    복사를 매니페스트보다 먼저 하면 저쪽 세트에 이 파일만 빠진다 — 그리고 그 사실은
    이쪽 디스크가 사라진 날에야 드러난다.
    """
    row = run_backup(db, settings, created_by=None, now=fake_clock.now())
    db.commit()

    remote = _copied_set(backup_store, Path(row.path).name)
    stored = json.loads((remote / manifest_mod.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert stored["scope"]["excluded_table_data"], "사본의 매니페스트에 범위가 없다"
    assert manifest_mod.verify_set(remote)["ok"] is True, "사본의 체크섬이 안 맞는다"


def test_the_row_says_where_the_copy_went(db, settings, fake_clock, stub_pg_dump, backup_store):
    from app.backups.service import backup_view

    row = run_backup(db, settings, created_by=None, now=fake_clock.now())
    db.commit()
    view = backup_view(row)
    assert view["destination_name"] == "백업 NAS"
    assert view["destination_ok"] is True


# ── 갈 곳이 없으면 그렇게 말한다 ─────────────────────────────────────────────


def test_without_a_backup_store_the_backup_carries_a_warning(
    db, settings, fake_clock, stub_pg_dump
):
    storage_service.ensure_default_provider(db, settings)
    db.commit()

    assert any("백업 저장소가 설정되지 않아" in line for line in backup_warnings(db))

    row = run_backup(db, settings, created_by=None, now=fake_clock.now())
    db.commit()
    stored = manifest_mod.read(Path(row.path)) or {}
    warnings = stored.get("warnings", [])
    assert any("백업 저장소가 설정되지 않아" in line for line in warnings)
    # 같은 사실을 두 번 말하지 않는다. 두 번째 문장에는 내부 역할 이름까지 섞여 나갔다.
    assert len(warnings) == 1, f"같은 사실이 여러 문장으로 나갔다: {warnings}"
    assert not any("OPERATIONAL" in line for line in warnings), "내부 역할 이름이 새 나갔다"
    from app.backups.service import backup_view

    assert backup_view(row)["destination_ok"] is None, (
        "보낼 곳이 없는 것과 보냈는데 실패한 것이 같은 값으로 보인다"
    )


def test_a_configured_backup_store_removes_that_warning(
    db, settings, fake_clock, stub_pg_dump, backup_store
):
    """반례 — 위 시험이 **언제나 경고를 내는 검사**가 아님을 보인다."""
    assert not any("백업 저장소가 설정되지 않아" in line for line in backup_warnings(db))


def test_same_device_is_reported_as_a_warning(db, settings, tmp_path):
    """운영과 백업이 같은 장치면 장치가 죽는 순간 둘 다 잃는다 (D-199 16번).

    시험 환경에서는 두 디렉터리가 같은 디스크에 있으므로 이 경고가 **떠야 한다** — 그것이
    실제 사실이다.
    """
    storage_service.ensure_default_provider(db, settings)
    root = tmp_path / "same-device-backup"
    root.mkdir()
    db.add(StorageProvider(name="같은 디스크", kind="LOCAL", role="BACKUP",
                           base_path=root.as_posix()))
    db.commit()

    warning = storage_service.same_device_warning(db)
    if warning is None:
        pytest.skip("이 환경에서는 두 경로가 다른 장치다 — 경고가 없는 것이 사실이다")
    assert any("같은 장치" in line for line in backup_warnings(db))


# ── 보존이 저쪽 사본도 치운다 ────────────────────────────────────────────────


def test_retention_removes_the_remote_copy_too(
    db, settings, fake_clock, stub_pg_dump, backup_store
):
    from datetime import timedelta

    row = run_backup(db, settings, created_by=None, now=fake_clock.now() - timedelta(days=90))
    db.commit()
    remote = _copied_set(backup_store, Path(row.path).name)
    assert remote.is_dir()

    apply_retention(db, keep=0, keep_days=7, now=fake_clock.now())
    db.commit()

    assert not Path(row.path).exists(), "로컬 세트가 안 지워졌다"
    assert not remote.exists(), "백업 저장소 사본만 남아 저장소가 무한히 자란다"
