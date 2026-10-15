"""0050 — AI 도우미 대화의 마지막 대화 시각.

못박는 성질:
1. 올리면 대화마다 지우지 않은 메시지의 가장 늦은 시각이 채워진다. 메시지가 없거나 지운 것만 있으면 대화를 만든 시각이다.
2. 다른 칸(제목 · 보관 · `updated_at`)은 그대로다 — 보존 기한은 여전히 `updated_at` 을 본다.
3. 내리면 칸이 사라지고 대화와 메시지는 남으며, 다시 올려도 된다.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from pathlib import Path

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.regression

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BEFORE = "0049_celebration_pref"
CREATED = datetime(2026, 9, 1, 9, 0, 0)
UPDATED = datetime(2026, 9, 20, 9, 0, 0)


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


def _engine(db, db_url):
    from app.core.db import normalize_database_url

    db.close()
    db.get_bind().dispose()
    return sa.create_engine(normalize_database_url(db_url), future=True)


def _conversation(conn, user_id: str, title: str) -> str:
    row_id = str(uuid.uuid4())
    conn.execute(sa.text(
        "INSERT INTO conversations (id, user_id, title, archived, created_at, updated_at) "
        "VALUES (:id, :user, :title, false, :created, :updated)"
    ), {"id": row_id, "user": user_id, "title": title, "created": CREATED, "updated": UPDATED})
    return row_id


def _message(conn, conversation_id: str, at: datetime, *, deleted: bool = False) -> None:
    conn.execute(sa.text(
        "INSERT INTO messages (id, conversation_id, message_id, role, content, processing_status, "
        "created_at, updated_at, deleted_at) VALUES (:id, :conv, :mid, 'user', '질문', 'done', :at, :at, :deleted)"
    ), {"id": str(uuid.uuid4()), "conv": conversation_id, "mid": "m-" + uuid.uuid4().hex[:16], "at": at,
        "deleted": at if deleted else None})


@pytest.mark.real_db
def test_last_message_at_is_backfilled_and_reversible(db, db_url, make_user):
    owner = make_user("mig-0050@goodmit.co.kr").id
    engine = _engine(db, db_url)
    try:
        _alembic(db_url, "downgrade", BEFORE)
        with engine.begin() as conn:
            talked = _conversation(conn, owner, "이야기한 대화")
            _message(conn, talked, datetime(2026, 9, 3, 10, 0, 0))
            _message(conn, talked, datetime(2026, 9, 5, 11, 30, 0))
            _message(conn, talked, datetime(2026, 9, 9, 8, 0, 0), deleted=True)
            empty = _conversation(conn, owner, "새 대화")
            only_deleted = _conversation(conn, owner, "지운 것만")
            _message(conn, only_deleted, datetime(2026, 9, 7, 7, 0, 0), deleted=True)
        _alembic(db_url, "upgrade", "head")

        with engine.connect() as conn:
            rows = {r.id: r for r in conn.execute(sa.text(
                "SELECT id, title, archived, updated_at, last_message_at FROM conversations WHERE user_id = :u"
            ), {"u": owner})}
        assert rows[talked].last_message_at == datetime(2026, 9, 5, 11, 30, 0), "지운 메시지의 시각을 셌다"
        assert rows[empty].last_message_at == CREATED
        assert rows[only_deleted].last_message_at == CREATED
        assert {(r.title, r.archived, r.updated_at) for r in rows.values()} == {
            ("이야기한 대화", False, UPDATED), ("새 대화", False, UPDATED), ("지운 것만", False, UPDATED)}

        _alembic(db_url, "downgrade", BEFORE)
        inspector = sa.inspect(engine)
        assert "last_message_at" not in {c["name"] for c in inspector.get_columns("conversations")}
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT count(*) FROM conversations WHERE user_id = :u"),
                                {"u": owner}).scalar_one() == 3
            assert conn.execute(sa.text("SELECT count(*) FROM messages WHERE conversation_id = :c"),
                                {"c": talked}).scalar_one() == 3
        _alembic(db_url, "upgrade", "head")
        assert "last_message_at" in {c["name"] for c in sa.inspect(engine).get_columns("conversations")}
    finally:
        engine.dispose()
