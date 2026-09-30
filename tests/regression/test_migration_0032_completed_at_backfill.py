"""0032 — 완료 티켓의 `completed_at` 을 믿을 수 있는 기록에서만 되채운다 (계획 3.7).

못박는 성질:
1. 상태 기록(`ticket_activities`)이 있으면 가장 늦은 '완료' 시각을 쓴다.
2. 상태 기록이 없으면 감사 기록(`ticket.update` 의 after.status == 완료)의 가장 늦은 시각을 쓴다.
3. 둘 다 있으면 상태 기록이 이긴다.
4. 둘 다 없으면 NULL 로 남는다 - 지어내지 않는다.
5. 지금 완료가 아닌 티켓(다시 연 티켓)은 건드리지 않는다.
6. 이미 값이 있는 티켓은 덮지 않는다.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import text

pytestmark = pytest.mark.regression

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BEFORE = "0031_project_stats_computed_at"


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


def _activity(db, ticket_id, when):
    from app.work.models import TicketActivity

    db.add(TicketActivity(
        id=str(uuid.uuid4()), ticket_id=ticket_id, kind="status", field="status",
        from_value="진행", to_value="완료", created_at=when,
    ))


def _audit(db, object_id, when):
    from app.audit.models import AuditLog

    db.add(AuditLog(
        action="ticket.update", object_type="notion_task", object_id=object_id,
        before_json=json.dumps({"status": "진행"}), after_json=json.dumps({"status": "완료"}),
        result="success", created_at=when,
    ))


@pytest.mark.real_db
def test_backfill_uses_only_trustworthy_records(db, db_url, make_ticket):
    from app.core.db import normalize_database_url

    by_activity = make_ticket(title="상태 기록", status="완료")
    by_audit = make_ticket(title="감사 기록", status="완료", page_id="legacy-page-audit")
    both = make_ticket(title="둘 다", status="완료")
    nothing = make_ticket(title="기록 없음", status="완료")
    reopened = make_ticket(title="다시 연 티켓", status="진행")
    stamped = make_ticket(title="이미 찍힘", status="완료")
    db.flush()
    stamped.completed_at = datetime(2026, 6, 30, 1, 0)
    for row in (by_activity, by_audit, both, nothing, reopened):
        row.completed_at = None

    _activity(db, by_activity.id, datetime(2026, 7, 1, 0, 0))
    _activity(db, by_activity.id, datetime(2026, 7, 10, 5, 0))
    _audit(db, "legacy-page-audit", datetime(2026, 7, 12, 6, 0))
    _activity(db, both.id, datetime(2026, 7, 5, 0, 0))
    _audit(db, both.id, datetime(2026, 7, 20, 0, 0))
    _activity(db, reopened.id, datetime(2026, 7, 3, 0, 0))
    _activity(db, stamped.id, datetime(2026, 7, 30, 0, 0))
    db.commit()
    ids = {name: row.id for name, row in {
        "activity": by_activity, "audit": by_audit, "both": both, "nothing": nothing,
        "reopened": reopened, "stamped": stamped,
    }.items()}
    db.close()
    db.get_bind().dispose()

    engine = sa.create_engine(normalize_database_url(db_url), future=True)
    try:
        _alembic(db_url, "downgrade", BEFORE)
        _alembic(db_url, "upgrade", "head")
        with engine.connect() as conn:
            got = dict(conn.execute(text(
                "SELECT id, completed_at FROM tickets WHERE id = ANY(:ids)"
            ), {"ids": list(ids.values())}).all())
    finally:
        engine.dispose()

    assert got[ids["activity"]] == datetime(2026, 7, 10, 5, 0), "가장 늦은 상태 기록을 안 썼다"
    assert got[ids["audit"]] == datetime(2026, 7, 12, 6, 0), "감사 기록으로 채우지 않았다"
    assert got[ids["both"]] == datetime(2026, 7, 5, 0, 0), "상태 기록이 감사 기록을 이겨야 한다"
    assert got[ids["nothing"]] is None, "기록이 없는데 날짜를 지어냈다"
    assert got[ids["reopened"]] is None, "지금 완료가 아닌 티켓에 끝낸 날짜를 붙였다"
    assert got[ids["stamped"]] == datetime(2026, 6, 30, 1, 0), "이미 있던 값을 덮었다"
