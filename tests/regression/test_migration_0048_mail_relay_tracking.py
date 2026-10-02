"""0048 — 로컬 릴레이의 바깥 전달 추적 칸 (계획 M7, D-551).

못박는 성질:
1. 기존 발송 행은 그대로이고 새 칸은 비어 있다 - 외부 SMTP 로 보낸 메일은 「메일 서버가 접수함」까지가 전부다.
2. 끝나지 않은 바깥 결과(queued · deferred)만 담는 부분 색인이 있다(추적 틱이 1분마다 그 행만 읽는다).
3. 내리면 칸과 색인이 사라지고 행은 남는다. 다시 올려도 같다(재실행 무해).
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
import sqlalchemy as sa

from tests.regression.test_migration_0041_ai_policies import _alembic, _engine

pytestmark = pytest.mark.regression

BEFORE = "0047_notify_email"
TARGET = "0048_mail_relay_tracking"
WHEN = datetime(2026, 9, 1, 0, 0, 0)
COLUMNS = {"relay_queue_id", "relay_delivery", "remote_status", "remote_stage", "remote_detail", "remote_checked_at"}


def _columns(engine) -> set[str]:
    return {c["name"] for c in sa.inspect(engine).get_columns("mail_deliveries")}


def _indexes(engine) -> dict[str, dict]:
    return {i["name"]: i for i in sa.inspect(engine).get_indexes("mail_deliveries")}


@pytest.mark.real_db
def test_relay_tracking_columns_and_pending_index(db, db_url):
    engine = _engine(db, db_url)
    row_id = str(uuid.uuid4())
    try:
        _alembic(db_url, "downgrade", BEFORE)
        assert not (COLUMNS & _columns(engine))
        with engine.begin() as conn:
            conn.execute(sa.text(
                "INSERT INTO mail_deliveries (id, kind, to_email, subject, status, attempt_count, params_json, sent_at, "
                "created_at, updated_at) VALUES (:id, 'test', 'a@example.com', '[ClovirAssist] 시험', 'sent', 0, '{}', :at, :at, :at)"
            ), {"id": row_id, "at": WHEN})

        _alembic(db_url, "upgrade", TARGET)
        assert COLUMNS <= _columns(engine)
        with engine.connect() as conn:
            row = conn.execute(sa.text(
                "SELECT status, relay_queue_id, relay_delivery, remote_status, remote_checked_at FROM mail_deliveries WHERE id = :id"
            ), {"id": row_id}).one()
        assert tuple(row) == ("sent", None, None, None, None), "옛 행은 그대로이고 바깥 결과는 비어 있다"
        index = _indexes(engine)["ix_mail_deliveries_remote_pending"]
        assert index["column_names"] == ["remote_status", "sent_at"]
        where = str((index.get("dialect_options") or {}).get("postgresql_where") or "")
        assert "queued" in where and "deferred" in where, "끝나지 않은 행만 담는 부분 색인이다"

        with engine.begin() as conn:
            conn.execute(sa.text(
                "UPDATE mail_deliveries SET relay_queue_id = 'C87DBF6954', relay_delivery = 'direct', remote_status = 'queued' "
                "WHERE id = :id"), {"id": row_id})
        _alembic(db_url, "downgrade", BEFORE)
        assert not (COLUMNS & _columns(engine))
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT status FROM mail_deliveries WHERE id = :id"), {"id": row_id}).scalar_one() == "sent"
        _alembic(db_url, "upgrade", TARGET)
        _alembic(db_url, "upgrade", "head")
        assert COLUMNS <= _columns(engine)
    finally:
        with engine.begin() as conn:
            conn.execute(sa.text("DELETE FROM mail_deliveries WHERE id = :id"), {"id": row_id})
        engine.dispose()
