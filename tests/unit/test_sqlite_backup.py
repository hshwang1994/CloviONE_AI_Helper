import sqlite3

import pytest

from app.backups.sqlite_backup import (
    backup_database,
    restore_test,
    sha256_file,
    verify_backup,
)

pytestmark = pytest.mark.unit


def test_backup_and_verify_roundtrip(db_path, tmp_path):
    url = f"sqlite:///{db_path.as_posix()}"
    dest = tmp_path / "backup.sqlite3"
    result = backup_database(url, dest)
    assert dest.exists()
    assert result["size_bytes"] > 0
    assert len(result["checksum"]) == 64

    verify = verify_backup(dest, result["checksum"])
    assert verify["ok"] is True


def test_verify_detects_checksum_mismatch(db_path, tmp_path):
    url = f"sqlite:///{db_path.as_posix()}"
    dest = tmp_path / "backup.sqlite3"
    backup_database(url, dest)
    assert verify_backup(dest, "0" * 64)["ok"] is False


def test_verify_missing_file(tmp_path):
    assert verify_backup(tmp_path / "nope.sqlite3")["ok"] is False


def test_verify_detects_corruption(db_path, tmp_path):
    url = f"sqlite:///{db_path.as_posix()}"
    dest = tmp_path / "backup.sqlite3"
    result = backup_database(url, dest)
    # Corrupt the middle of the file, keeping the size (checksum not passed).
    data = bytearray(dest.read_bytes())
    for i in range(100, min(len(data), 4000)):
        data[i] = data[i] ^ 0xFF
    dest.write_bytes(bytes(data))
    assert verify_backup(dest)["ok"] is False


def test_restore_test_uses_temp_and_verifies(db_path, tmp_path):
    url = f"sqlite:///{db_path.as_posix()}"
    dest = tmp_path / "backup.sqlite3"
    backup_database(url, dest)
    assert restore_test(dest)["ok"] is True
