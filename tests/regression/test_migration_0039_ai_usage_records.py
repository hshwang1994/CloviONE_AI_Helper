"""0039 — AI 호출 기록 표와 옛 기록 옮기기 (계획 3.10 · 3.11, D-517).

못박는 성질:
1. 올리면 옛 `usage_events(event='ai.call')` 이 한 줄도 빠짐없이 호출 기록으로 옮겨진다. 기능 이름은 옛 종류에서
   액션으로 바뀌고(모르는 종류는 그대로), 결과는 성공이며, 토큰과 지연은 모른다(NULL). 다른 이벤트는 옮기지 않는다.
2. 옮긴 행으로 이번 달의 한도 계산이 끊기지 않는다 - 업그레이드한 날 한도가 0 부터 다시 세지 않는다.
3. 0039 는 옛 행을 지우지 않는다. 내리면 표만 사라지고, 다시 올려도 된다.
4. 머리까지 올리면 0046(옛 AI 데이터 정리, D-544)이 옮겨 둔 옛 `ai.call` 행을 지운다 — 옮긴 호출 기록과 한도 셈은 그대로다.

qa-contract-change: 0046 이 옛 `usage_events(event='ai.call')` 를 지우게 됐다(D-544). 「옛 기록을 지우지 않는다」는 0039 의 성질이라
0039 까지만 올려 그 단언을 그대로 재고, 머리에서는 지워졌는지와 옮긴 기록 · 한도 셈이 남았는지를 더 잰다.
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
BEFORE = "0038_ai_oauth_transactions"
AFTER = "0039_ai_usage_records"
WHEN = datetime(2026, 7, 14, 1, 0, 0)


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


def _event(conn, *, event: str, user_id, kind=None, object_id=None) -> None:
    from app.org.constants import DEFAULT_ORG_ID

    conn.execute(sa.text(
        "INSERT INTO usage_events (id, org_id, user_id, event, object_type, object_id, meta_json, created_at) "
        "VALUES (:id, :org, :user_id, :event, 'ai', :object_id, CAST(:meta AS jsonb), :at)"
    ), {"id": str(uuid.uuid4()), "org": DEFAULT_ORG_ID, "user_id": user_id,
        "event": event, "object_id": object_id, "meta": None if kind is None else f'{{"kind": "{kind}"}}',
        "at": WHEN})


@pytest.mark.real_db
def test_old_calls_move_over_and_keep_counting_against_the_limit(db, db_url):
    from sqlalchemy.orm import Session

    from app.quotas import service as quotas

    engine = _engine(db, db_url)
    person = str(uuid.uuid4())
    try:
        _alembic(db_url, "downgrade", BEFORE)
        with engine.begin() as conn:
            for kind in ("chat_message", "ai_ask", "ai_draft", "assistant_narrative"):
                _event(conn, event="ai.call", user_id=person, kind=kind, object_id=kind)
            _event(conn, event="ai.call", user_id=person, object_id="chat_message")  # 종류가 object_id 에만 있다
            _event(conn, event="ai.call", user_id=None, kind="weird_kind", object_id="weird_kind")
            _event(conn, event="login", user_id=person)
        _alembic(db_url, "upgrade", AFTER)

        with engine.connect() as conn:
            rows = conn.execute(sa.text(
                "SELECT action_key, status, actor_kind, input_tokens, latency_ms FROM ai_usage_records "
                "ORDER BY action_key, actor_kind"
            )).all()
            kept = conn.execute(sa.text("SELECT count(*) FROM usage_events WHERE event = 'ai.call'")).scalar_one()
        assert sorted(r.action_key for r in rows) == sorted([
            "chat.answer", "chat.answer", "home.narrative", "weird_kind", "workspace.ask", "workspace.draft",
        ])
        assert {r.status for r in rows} == {"ok"}
        assert {r.actor_kind for r in rows if r.action_key == "weird_kind"} == {"system"}
        assert all(r.input_tokens is None and r.latency_ms is None for r in rows), "모르는 토큰을 지어냈다"
        assert kept == 6, "옛 기록을 지웠다"

        with Session(engine) as session:
            assert quotas.used(session, user_id=person, period="day", now=WHEN) == 5, (
                "업그레이드한 날 한도가 처음부터 다시 셌다"
            )

        # 머리(0046)는 옮겨 둔 옛 행을 지운다 — 옮긴 기록과 한도 셈은 그대로다(D-544).
        _alembic(db_url, "upgrade", "head")
        with engine.connect() as conn:
            moved = conn.execute(sa.text("SELECT count(*) FROM ai_usage_records")).scalar_one()
            left = conn.execute(sa.text("SELECT count(*) FROM usage_events WHERE event = 'ai.call'")).scalar_one()
            other = conn.execute(sa.text("SELECT count(*) FROM usage_events WHERE event = 'login'")).scalar_one()
        assert moved == 6, "0046 이 옮긴 호출 기록까지 지웠다"
        assert left == 0, "0046 이 옛 ai.call 행을 남겼다"
        assert other == 1, "0046 이 다른 이벤트까지 지웠다"
        with Session(engine) as session:
            assert quotas.used(session, user_id=person, period="day", now=WHEN) == 5, "정리 뒤 한도 셈이 끊겼다"

        _alembic(db_url, "downgrade", BEFORE)
        assert "ai_usage_records" not in sa.inspect(engine).get_table_names()
        _alembic(db_url, "upgrade", "head")
        assert "ai_usage_records" in sa.inspect(engine).get_table_names()
    finally:
        engine.dispose()
