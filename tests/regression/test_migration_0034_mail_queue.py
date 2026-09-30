"""0034 — 메일 큐 열 넷과 새 상태의 왕복 (계획 3.3).

못박는 성질:
1. 올리면 열 넷(`idempotency_key` · `message_id` · `failure_kind` · `skip_reason`)과 유일 제약이 선다.
2. 내리면 옛 앱이 아는 어휘로 돌아간다: `retrying` → `queued`, `cancelled` · `superseded` → `failed`.
   그 밖의 상태와 행 수는 그대로다.
3. 다시 올려도 행이 그대로 남는다.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import text

pytestmark = pytest.mark.regression

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BEFORE = "0033_project_org_backfill"


def _alembic(url: str, action: str, target: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    prior = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        getattr(command, action)(cfg, target)
    finally:
        if prior is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prior


def _columns(conn) -> set[str]:
    return set(conn.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'mail_deliveries'"
    )).scalars())


@pytest.mark.real_db
def test_the_queue_columns_round_trip(db, db_url):
    from app.core.db import normalize_database_url
    from app.mail.models import MailDelivery

    when = datetime(2026, 9, 1, 0, 0)
    ids = {}
    for status in ("queued", "retrying", "sent", "failed", "unconfigured", "cancelled", "superseded"):
        row = MailDelivery(id=str(uuid.uuid4()), kind="invite", to_email=f"{status}@goodmit.co.kr",
                           subject=status, status=status, params_json="{}", created_at=when, updated_at=when,
                           idempotency_key=f"key:{status}")
        db.add(row)
        ids[status] = row.id
    db.commit()
    db.close()
    db.get_bind().dispose()

    engine = sa.create_engine(normalize_database_url(db_url), future=True)
    try:
        _alembic(db_url, "downgrade", BEFORE)
        with engine.connect() as conn:
            assert not ({"idempotency_key", "message_id", "failure_kind", "skip_reason"} & _columns(conn))
            down = dict(conn.execute(text("SELECT id, status FROM mail_deliveries")).all())
        _alembic(db_url, "upgrade", "head")
        with engine.connect() as conn:
            assert {"idempotency_key", "message_id", "failure_kind", "skip_reason"} <= _columns(conn)
            count = conn.execute(text("SELECT count(*) FROM mail_deliveries")).scalar()
            constraint = conn.execute(text(
                "SELECT count(*) FROM pg_constraint WHERE conname = 'uq_mail_deliveries_idempotency_key'"
            )).scalar()
    finally:
        engine.dispose()

    assert down[ids["retrying"]] == "queued", "끝나지 않은 재시도를 옛 앱이 모르는 상태로 남겼다"
    assert down[ids["cancelled"]] == "failed" and down[ids["superseded"]] == "failed"
    for status in ("queued", "sent", "failed", "unconfigured"):
        assert down[ids[status]] == status, f"{status} 가 바뀌었다"
    assert count == 7, "왕복에서 행을 잃었다"
    assert constraint == 1
