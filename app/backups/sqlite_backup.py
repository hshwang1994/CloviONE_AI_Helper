"""SQLite backup via the online Backup API + checksum + integrity verify
(spec §6.1, §12 — never a naive file copy)."""

from __future__ import annotations

import hashlib
import sqlite3
import tempfile
from pathlib import Path


def _sqlite_path_from_url(database_url: str) -> Path:
    """Standard SQLAlchemy convention:
    sqlite:///relative -> relative ; sqlite:////abs -> /abs ;
    sqlite:///C:/x -> C:/x (Windows)."""
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("SQLite 백업은 sqlite:/// URL에서만 지원됩니다.")
    return Path(database_url[len(prefix):])


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup_database(database_url: str, dest_path: Path) -> dict:
    """Consistent online backup using sqlite3.Connection.backup()."""
    src = _sqlite_path_from_url(database_url)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(str(src))
    try:
        dest = sqlite3.connect(str(dest_path))
        try:
            source.backup(dest)
        finally:
            dest.close()
    finally:
        source.close()
    return {
        "path": str(dest_path),
        "size_bytes": dest_path.stat().st_size,
        "checksum": sha256_file(dest_path),
    }


def verify_backup(backup_path: Path, expected_checksum: str | None = None) -> dict:
    """Re-open the backup and run PRAGMA integrity_check (spec §12 verify)."""
    if not backup_path.exists():
        return {"ok": False, "reason": "file_missing"}
    if expected_checksum is not None and sha256_file(backup_path) != expected_checksum:
        return {"ok": False, "reason": "checksum_mismatch"}
    try:
        conn = sqlite3.connect(str(backup_path))
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        return {"ok": False, "reason": f"database_error: {exc}"}
    ok = bool(result) and result[0] == "ok"
    return {"ok": ok, "reason": None if ok else f"integrity_check={result}"}


def restore_test(backup_path: Path) -> dict:
    """Copy the backup into a temp dir and verify — never touches live data
    (spec §6.3)."""
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "restore-test.sqlite3"
        conn_src = sqlite3.connect(str(backup_path))
        try:
            conn_dst = sqlite3.connect(str(target))
            try:
                conn_src.backup(conn_dst)
            finally:
                conn_dst.close()
        finally:
            conn_src.close()
        return verify_backup(target)
