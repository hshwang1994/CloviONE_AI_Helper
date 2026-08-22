"""파일 저장소 백업과 복원 — 「복사했다」가 아니라 「같은 파일이 저쪽에 있다」 (S8).

파일을 만든 것만으로 SUCCESS 를 찍지 않는다(D-204 가 PostgreSQL 쪽에 같은 규칙을 적어
뒀다). 쓴 뒤 다시 읽어 sha256 을 비교한다 — NFS/SMB 는 쓰기가 성공한 것처럼 보이고
나중에 다른 내용이 되는 실패 모드가 실제로 있다.

일정·보존·manifest 는 여기 없다. 그것은 S12 의 몫이고(`BACKLOG.md` P-23), 이 모듈은
그쪽이 부를 수 있는 조각으로 남는다.
"""

from __future__ import annotations

import pytest

from app.storage import adapters, archive, service
from app.storage.models import StorageProvider

pytestmark = pytest.mark.integration

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture()
def pair(db, settings, tmp_path):
    """운영 저장소 하나 + 백업 저장소 하나."""
    operational = service.ensure_default_provider(db, settings)
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    backup = StorageProvider(
        name="백업 저장소", kind="LOCAL", role="BACKUP", base_path=backup_dir.as_posix()
    )
    db.add(backup)
    db.commit()
    return operational, backup


def _store(db, n=3):
    return [
        service.store_bytes(db, filename=f"파일{i}.png", content=PNG + bytes([i]))
        for i in range(n)
    ]


# ── 옮기고 확인한다 ─────────────────────────────────────────────────────────


def test_every_file_lands_on_the_backup_store_with_the_same_bytes(db, pair):
    operational, backup = pair
    records = _store(db)
    db.commit()

    result = archive.archive_to_backup(db)
    assert result["ok"] and result["copied"] == 3, result

    backup_ref = service.ref_of(backup)
    for record in records:
        assert adapters.read_object(backup_ref, record.storage_key) == \
            adapters.read_object(service.ref_of(operational), record.storage_key)


def test_running_it_twice_copies_nothing_new(db, pair):
    """백업은 반복해서 도는 작업이다. 매번 전량을 다시 쓰면 회차가 길어지고,
    그 길이가 곧 실패 확률이 된다."""
    _store(db, 2)
    db.commit()
    archive.archive_to_backup(db)

    again = archive.archive_to_backup(db)
    assert again["copied"] == 0
    assert again["skipped"] == 2
    assert again["ok"]


def test_a_file_that_changed_on_the_backup_store_is_copied_again(db, pair):
    """체크섬으로 본다. 크기로만 보면 같은 크기의 다른 내용을 영원히 건너뛴다."""
    _, backup = pair
    records = _store(db, 1)
    db.commit()
    archive.archive_to_backup(db)

    backup_ref = service.ref_of(backup)
    adapters.object_path(backup_ref, records[0].storage_key).write_bytes(b"tampered")

    again = archive.archive_to_backup(db)
    assert again["copied"] == 1
    assert adapters.read_object(backup_ref, records[0].storage_key) == PNG + bytes([0])


def test_a_source_file_that_does_not_match_its_checksum_is_reported_not_copied(db, pair):
    """🔴 깨진 원본을 그대로 옮기면 백업까지 깨진다. 그리고 그 사실을 아무도 모른다."""
    operational, backup = pair
    records = _store(db, 1)
    db.commit()
    adapters.object_path(service.ref_of(operational), records[0].storage_key).write_bytes(
        b"corrupted on disk"
    )

    result = archive.archive_to_backup(db)
    assert not result["ok"]
    assert result["failed"] == 1
    assert not adapters.object_exists(service.ref_of(backup), records[0].storage_key)


def test_bytes_nobody_points_at_are_not_backed_up(db, pair):
    """행이 정본이다. 저장소를 훑어 옮기면 고아 파일까지 함께 가고, 그러면 백업이
    운영보다 커지면서 그 차이가 무엇인지 설명할 수 없게 된다."""
    operational, backup = pair
    _store(db, 1)
    db.commit()
    orphan = adapters.new_storage_key(extension=".txt")
    adapters.write_object(service.ref_of(operational), orphan, b"nobody points at me")

    result = archive.archive_to_backup(db)
    assert result["copied"] == 1
    assert not adapters.object_exists(service.ref_of(backup), orphan)


# ── 복원 ─────────────────────────────────────────────────────────────────────


def test_restore_brings_the_bytes_back(db, pair):
    operational, _ = pair
    records = _store(db, 2)
    db.commit()
    archive.archive_to_backup(db)

    operational_ref = service.ref_of(operational)
    for record in records:
        adapters.delete_object(operational_ref, record.storage_key)
    assert service.verify_files(db)["missing"] == [r.id for r in records]

    result = archive.restore_from_backup(db)
    assert result["ok"] and result["copied"] == 2, result
    after = service.verify_files(db)
    assert after["missing"] == [] and after["corrupt"] == []


# ── 시작조차 못 하는 경우 ────────────────────────────────────────────────────


def test_with_no_backup_store_it_says_impossible_not_zero_copied(db, settings):
    """🔴 「0건 복사 성공」과 구별한다. 같은 모양으로 보고하면 마운트가 빠진 밤에도
    백업 이력이 초록으로 남는다."""
    service.ensure_default_provider(db, settings)
    db.commit()
    with pytest.raises(archive.ArchiveNotPossible):
        archive.archive_to_backup(db)


def test_an_unmounted_backup_store_stops_before_reading_anything(db, settings, tmp_path):
    service.ensure_default_provider(db, settings)
    mountpoint = tmp_path / "nas"
    mountpoint.mkdir()
    db.add(StorageProvider(
        name="안 붙은 백업", kind="NFS", role="BACKUP",
        base_path=mountpoint.as_posix(), mount_point=mountpoint.as_posix(),
        config_json='{"source": "nas:/backup"}',
    ))
    db.commit()
    _store(db, 1)
    db.commit()

    with pytest.raises(archive.ArchiveNotPossible):
        archive.archive_to_backup(db)
    assert list(mountpoint.iterdir()) == []
