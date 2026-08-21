"""백업이 **행 잠금을 쥔 채 느린 I/O 를 하지 않는다** (UA-03).

예전 `run_backup` 은 `db.flush()` 뒤 커밋 없이 전체 DB 복사 + 임시 복원 + 무결성 검사를
수행하고 커밋은 요청 끝에야 일어났다. `trash/service.py::purge_expired`(S7)가 이미
문서화한 것과 같은 실패 양식이다.

이 테스트는 "커밋했다"를 보지 않는다. **그 시각에 다른 연결이 그 행을 실제로 잡을 수
있는지**를 본다 — `tests/integration/test_retention_lock.py` 와 같은 기법이다.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.backups import service

# 이 파일의 시험은 **전용 DB** 가 필요하다(D-190) — 두 번째 커넥션이나 별도
# 프로세스가 이 시험의 데이터를 봐야 하기 때문이다. 공유 DB + 트랜잭션 되감기
# 계층에서는 그 데이터가 트랜잭션 밖으로 안 나가서 아무것도 증명하지 못한다.
pytestmark = [pytest.mark.integration, pytest.mark.real_db]


def _second_connection(db_url):
    """웹 프로세스 역할의 **두 번째 커넥션**.

    qa-contract-change: SQLite 는 첫 쓰기에서 DB 전체 쓰기 락을 잡았기 때문에 busy_timeout 0 하나로 프로브가 성립했다. PG 에는 그런 락이 없어(MVCC · 행 단위) 그대로 옮기면 무엇이든 통과하는 검사가 되므로, 같은 뜻을 갖는 FOR UPDATE NOWAIT 로 다시 썼다.
    즉시 실패" 를 만들었다. SQLite 는 첫 쓰기에서 **DB 전체 쓰기 락**을 잡았기 때문에 그

    **막으려는 사고는 그대로다** — 느린 외부 I/O 를 트랜잭션 안에서 하면 그동안 그 행들이
    잠겨 있고, 같은 행을 건드리는 요청이 전부 대기한다.
    """
    from app.core.db import normalize_database_url

    return create_engine(normalize_database_url(db_url))


def _try_lock_row(engine, table: str, row_id: str) -> str:
    """그 행을 **기다리지 않고** 잠가 본다. 상대가 쥐고 있으면 `locked: …` 를 돌려준다."""
    try:
        with engine.begin() as conn:
            conn.execute(
                text(f"SELECT 1 FROM {table} WHERE id = :id FOR UPDATE NOWAIT"),  # noqa: S608
                {"id": row_id},
            )
        return "ok"
    except OperationalError as exc:
        return f"locked: {exc.orig}"


def test_the_web_can_still_write_while_a_backup_is_running(
    db, db_url, settings, monkeypatch
):
    web = _second_connection(db_url)
    attempts: list[str] = []

    def backup_and_check_the_lock(database_url, dest_path, *, bin_dir=None):
        """느린 덤프를 흉내내면서, 바로 그 순간 백업 행이 잠겨 있는지 확인한다."""
        row_id = db.execute(
            text("SELECT id FROM backups ORDER BY created_at DESC LIMIT 1")
        ).scalar()
        attempts.append(_try_lock_row(web, "backups", row_id))
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_text("fake backup file", encoding="utf-8")
        return {"size_bytes": 17, "checksum": "deadbeef"}

    def fake_restore_test(backup_path, *, database_url=None, bin_dir=None):
        return {"ok": True, "reason": None}

    monkeypatch.setattr(service, "backup_database", backup_and_check_the_lock)
    monkeypatch.setattr(service, "restore_test", fake_restore_test)

    row = service.run_backup(db, settings, created_by=None, now=datetime(2026, 8, 10))
    db.commit()

    assert attempts, "backup_database가 한 번도 안 불렸다 — 이 테스트의 전제가 깨졌다"
    blocked = [a for a in attempts if a != "ok"]
    assert blocked == [], (
        f"백업 I/O 중에 웹 쓰기가 막혔다({len(blocked)}/{len(attempts)}건): {blocked[0]}"
    )
    # 락을 놓은 것과 백업이 실제로 끝난 것은 다르다 — 결과는 그대로 확정돼야 한다.
    assert row.status == "verified"
    assert row.checksum == "deadbeef"
    web.dispose()


def test_the_probe_itself_can_detect_a_held_lock(db, db_url):
    """위 테스트가 **무엇이든 통과시키는 검사**가 아님을 증명한다.

    행을 실제로 잠근 채 커밋하지 않고(= 예전 구조가 하던 그 상태) 같은 프로브를 돌려
    `locked` 가 나오는지 본다. 이게 없으면 위 테스트는 "언제나 초록" 일 수 있고, 그러면
    아무 뜻도 없다.
    """
    from app.backups.models import Backup

    web = _second_connection(db_url)

    row = Backup(backup_type="pg_dump", path="/tmp/x.dump", status="running",
                 created_by=None, created_at=datetime(2026, 8, 10))
    db.add(row)
    # **먼저 커밋한다.** 커밋 안 한 INSERT 는 다른 트랜잭션에 아예 안 보이므로,
    # `FOR UPDATE NOWAIT` 가 «행이 없다» 로 그냥 성공해 프로브가 헛돈다. 잠금을 재려면
    # 상대가 볼 수 있는 행이 먼저 있어야 한다.
    db.commit()
    # 이제 그 행을 잠근 채 커밋하지 않는다 = 예전 구조가 하던 그 상태.
    db.execute(
        text("UPDATE backups SET status = 'running' WHERE id = :id"), {"id": row.id}
    )

    assert _try_lock_row(web, "backups", row.id) != "ok", (
        "프로브가 잡혀 있는 잠금을 못 알아본다 — 위 시험은 아무것도 증명하지 못한다"
    )
    db.rollback()
    web.dispose()
