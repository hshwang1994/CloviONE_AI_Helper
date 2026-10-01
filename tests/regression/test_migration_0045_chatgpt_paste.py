"""0045 — ChatGPT 계정 연결은 붙여 넣기 하나: 열린 시도를 닫고 짝짓기 토큰 칸을 걷는다 (D-540).

못박는 성질:
1. 올리면 열린 시도(`waiting_helper` · `browser`)가 `failed` · `superseded` 로 닫히고, 끝난 시도(`done` · `failed`)는 그대로다.
2. 올리면 `pairing_token_hash` 칸과 그 유일 제약이 사라진다. state 의 유일 제약은 남는다.
3. 내리면 칸이 nullable 로 돌아온다(유일 제약 포함). 다시 올려도 같은 결과다(재실행 무해).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa

from tests.regression.test_migration_0041_ai_policies import _alembic, _engine

pytestmark = pytest.mark.regression

BEFORE = "0044_assistant_tools"
TARGET = "0045_chatgpt_paste_login"
WHEN = datetime(2026, 9, 1, 0, 0, 0)


def _attempt(conn, admin_id: str, *, phase: str, error_code: str | None = None) -> str:
    row_id = str(uuid.uuid4())
    conn.execute(sa.text(
        "INSERT INTO ai_oauth_transactions (id, provider, pairing_token_hash, state, nonce, admin_user_id, phase, "
        "failures, error_code, created_at, updated_at, expires_at) VALUES (:id, 'openai', :pair, :state, :nonce, "
        ":admin, :phase, 0, :err, :at, :at, :exp)"
    ), {"id": row_id, "pair": uuid.uuid4().hex + uuid.uuid4().hex, "state": "s-" + row_id, "nonce": "n-" + row_id,
        "admin": admin_id, "phase": phase, "err": error_code, "at": WHEN, "exp": WHEN + timedelta(minutes=10)})
    return row_id


def _phases(conn) -> dict[str, tuple]:
    return {row_id: (phase, code) for row_id, phase, code in
            conn.execute(sa.text("SELECT id, phase, error_code FROM ai_oauth_transactions")).all()}


@pytest.mark.real_db
def test_open_attempts_close_and_the_pairing_column_goes(db, db_url, make_user):
    admin = make_user("mig-0045-sa@goodmit.co.kr", role="system_admin").id
    engine = _engine(db, db_url)
    try:
        _alembic(db_url, "downgrade", BEFORE)
        with engine.begin() as conn:
            waiting = _attempt(conn, admin, phase="waiting_helper")
            browser = _attempt(conn, admin, phase="browser")
            done = _attempt(conn, admin, phase="done")
            failed = _attempt(conn, admin, phase="failed", error_code="expired")

        _alembic(db_url, "upgrade", TARGET)
        with engine.connect() as conn:
            phases = _phases(conn)
        assert phases[waiting] == ("failed", "superseded")
        assert phases[browser] == ("failed", "superseded")
        assert phases[done] == ("done", None), "끝난 시도를 건드렸다"
        assert phases[failed] == ("failed", "expired"), "실패한 시도의 까닭을 덮었다"

        inspector = sa.inspect(engine)
        columns = {c["name"] for c in inspector.get_columns("ai_oauth_transactions")}
        assert "pairing_token_hash" not in columns
        uniques = {tuple(u["column_names"]) for u in inspector.get_unique_constraints("ai_oauth_transactions")}
        assert ("state",) in uniques and ("pairing_token_hash",) not in uniques

        _alembic(db_url, "downgrade", BEFORE)
        inspector = sa.inspect(engine)
        column = next(c for c in inspector.get_columns("ai_oauth_transactions") if c["name"] == "pairing_token_hash")
        assert column["nullable"] is True
        uniques = {tuple(u["column_names"]) for u in inspector.get_unique_constraints("ai_oauth_transactions")}
        assert ("pairing_token_hash",) in uniques

        _alembic(db_url, "upgrade", TARGET)
        _alembic(db_url, "upgrade", "head")
        with engine.connect() as conn:
            assert _phases(conn)[done] == ("done", None), "다시 올려도 같은 결과다"
    finally:
        with engine.begin() as conn:
            conn.execute(sa.text("DELETE FROM ai_oauth_transactions"))
        engine.dispose()
