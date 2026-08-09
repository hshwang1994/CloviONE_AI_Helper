"""백업이 **쓰기 락을 쥔 채 느린 I/O 를 하지 않는다** (UA-03).

예전 `run_backup` 은 `db.flush()`(쓰기 락을 잡음) 뒤, 커밋 없이 전체 DB 복사
(`backup_database`) + 임시 복원 + 무결성 검사 2벌(`restore_test`)을 수행하고 커밋은
요청 끝에야 일어났다. `trash/service.py::purge_expired`(S7)가 이미 문서화한 것과 같은
실패 양식이다 — 그동안 웹의 다른 모든 쓰기가 `database is locked` 500 이 된다.

이 테스트는 "커밋했다"를 보지 않는다. **그 시각에 다른 연결이 실제로 쓸 수 있는지**를
본다 — `tests/integration/test_retention_lock.py` 와 같은 기법이다.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.backups import service
from app.core.db import EngineOptions, make_engine

pytestmark = pytest.mark.integration


def _second_connection(db_path):
    """웹 프로세스 역할. busy_timeout 0 → 락이 잡혀 있으면 즉시 실패한다."""
    return make_engine(
        f"sqlite:///{db_path.as_posix()}",
        EngineOptions(busy_timeout_ms=0, pool_pre_ping=False),
    )


def test_the_web_can_still_write_while_a_backup_is_running(
    db, db_path, settings, monkeypatch
):
    web = _second_connection(db_path)
    attempts: list[str] = []

    def backup_and_check_the_lock(database_url, dest_path):
        """전체 DB 복사(느린 I/O)를 흉내내면서, 바로 그 순간 웹이 쓸 수 있는지 확인한다."""
        try:
            with web.begin() as conn:
                conn.execute(text("CREATE TABLE IF NOT EXISTS ua03_probe (id INTEGER)"))
                conn.execute(text("INSERT INTO ua03_probe (id) VALUES (1)"))
            attempts.append("ok")
        except OperationalError as exc:
            attempts.append(f"locked: {exc.orig}")
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_text("fake backup file", encoding="utf-8")
        return {"size_bytes": 17, "checksum": "deadbeef"}

    def fake_restore_test(backup_path):
        return {"ok": True}

    monkeypatch.setattr(service, "backup_database", backup_and_check_the_lock)
    monkeypatch.setattr(service, "restore_test", fake_restore_test)

    row = service.run_backup(db, settings, created_by=None, now=datetime(2026, 8, 10))
    db.commit()

    assert attempts, "backup_database가 한 번도 안 불렸다 — 이 테스트의 전제가 깨졌다"
    blocked = [a for a in attempts if a != "ok"]
    assert not blocked, (
        f"백업 I/O 중에 웹 쓰기가 막혔다({len(blocked)}/{len(attempts)}건): {blocked[0]}"
    )
    # 락을 놓은 것과 백업이 실제로 끝난 것은 다르다 — 결과는 그대로 확정돼야 한다.
    assert row.status == "verified"
    assert row.checksum == "deadbeef"
    web.dispose()


def test_the_probe_itself_can_detect_a_held_lock(db, db_path):
    """위 테스트가 **무엇이든 통과시키는 검사**가 아님을 증명한다.

    쓰기 트랜잭션을 실제로 열어 두고 같은 프로브를 돌려 `locked`가 나오는지 본다.
    """
    from app.backups.models import Backup

    web = _second_connection(db_path)

    db.add(Backup(backup_type="sqlite", path="/tmp/x.sqlite3", status="running",
                   created_by=None, created_at=datetime(2026, 8, 10)))
    db.flush()  # 쓰기 락을 잡되 커밋하지 않는다 = 예전 구조가 하던 그 상태

    with pytest.raises(OperationalError) as caught:
        with web.begin() as conn:
            conn.execute(text("CREATE TABLE IF NOT EXISTS ua03_probe2 (id INTEGER)"))
    assert "locked" in str(caught.value.orig).lower()
    db.rollback()
    web.dispose()
