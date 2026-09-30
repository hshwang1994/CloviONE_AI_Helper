"""0035 — 요청자를 믿을 수 있는 기록에서만 되채운다 (계획 3.4, D-513).

못박는 성질:
1. 생성 활동이 있으면 가장 이른 생성 활동의 행위자가 요청자다(감사보다 먼저).
2. 생성 활동이 없으면 생성 감사의 행위자다. 감사의 대상 id 는 옛 page id 이거나, 없으면 행 id 다.
3. 기록의 행위자가 지금 없는 계정이면 적지 않는다(지워진 계정 id 를 FK 에 넣지 않는다).
4. 기록이 없는 티켓은 비어 있다(지어내지 않는다).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import text

pytestmark = pytest.mark.regression

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BEFORE = "0034_mail_delivery_queue"


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


@pytest.mark.real_db
def test_backfill_uses_only_records_that_name_an_existing_account(db, db_url, make_user):
    from app.audit.models import AuditLog
    from app.core.db import normalize_database_url
    from app.org.constants import DEFAULT_ORG_ID
    from app.tickets.models import Ticket
    from app.work.models import TicketActivity

    first = make_user("req-first@goodmit.co.kr", display_name="먼저 만든 사람")
    later = make_user("req-later@goodmit.co.kr", display_name="나중 기록")
    auditor = make_user("req-audit@goodmit.co.kr", display_name="감사에만 있는 사람")
    db.flush()

    def ticket(title: str, page_id: str | None) -> Ticket:
        row = Ticket(title=title, notion_page_id=page_id, status="계획", org_id=DEFAULT_ORG_ID)
        db.add(row)
        db.flush()
        return row

    by_activity = ticket("활동이 있는 티켓", "page-req-activity")
    by_audit = ticket("감사만 있는 티켓", "page-req-audit")
    native = ticket("자체 티켓", None)
    ghost = ticket("없는 계정의 기록", "page-req-ghost")
    unknown = ticket("기록이 없는 티켓", "page-req-none")

    t0 = datetime(2026, 9, 1, 3, 0, 0)
    for actor, when in ((later.id, t0 + timedelta(hours=1)), (first.id, t0)):
        db.add(TicketActivity(
            id=str(uuid.uuid4()), ticket_id=by_activity.id, actor_user_id=actor, kind="created",
            to_value="계획", created_at=when,
        ))
    for object_id, user_id in (
        (by_activity.notion_page_id, auditor.id),   # 활동이 있으면 감사는 안 쓴다
        (by_audit.notion_page_id, auditor.id),
        (native.id, later.id),                       # page id 가 없으면 행 id 가 감사 대상이다
        (ghost.notion_page_id, str(uuid.uuid4())),   # 지금은 없는 계정
    ):
        db.add(AuditLog(
            user_id=user_id, action="ticket.create", object_type="notion_task", object_id=object_id,
        ))
    db.commit()
    ids = {
        "by_activity": by_activity.id, "by_audit": by_audit.id, "native": native.id,
        "ghost": ghost.id, "unknown": unknown.id,
    }
    db.close()
    db.get_bind().dispose()

    engine = sa.create_engine(normalize_database_url(db_url), future=True)
    try:
        _alembic(db_url, "downgrade", BEFORE)
        _alembic(db_url, "upgrade", "head")
        with engine.connect() as conn:
            got = dict(conn.execute(text(
                "SELECT id, requester_user_id FROM tickets WHERE id = ANY(:ids)"
            ), {"ids": list(ids.values())}).all())
    finally:
        engine.dispose()

    assert got[ids["by_activity"]] == first.id, "가장 이른 생성 활동보다 다른 기록을 먼저 썼다"
    assert got[ids["by_audit"]] == auditor.id, "생성 감사로 되채우지 않았다"
    assert got[ids["native"]] == later.id, "page id 가 없는 자체 티켓의 감사를 못 찾았다"
    assert got[ids["ghost"]] is None, "지금은 없는 계정을 요청자로 적었다"
    assert got[ids["unknown"]] is None, "기록이 없는 티켓에 요청자를 지어냈다"


@pytest.mark.real_db
def test_downgrade_drops_the_column_and_upgrade_restores_it(db, db_url):
    from app.core.db import normalize_database_url

    db.close()
    db.get_bind().dispose()
    engine = sa.create_engine(normalize_database_url(db_url), future=True)

    def columns() -> set[str]:
        with engine.connect() as conn:
            return set(conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'tickets'"
            )).scalars())

    try:
        _alembic(db_url, "downgrade", BEFORE)
        assert "requester_user_id" not in columns()
        _alembic(db_url, "upgrade", "head")
        assert "requester_user_id" in columns()
    finally:
        engine.dispose()
