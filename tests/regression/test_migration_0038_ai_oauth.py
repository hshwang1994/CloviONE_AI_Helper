"""0038 — ChatGPT 계정 연결 시도 표와 갱신 토큰 만료 알림 시각 (계획 3.14 · 3.15, D-516).

못박는 성질:
1. 올리면 시도 표와 알림 시각 칸이 생기고, 짝짓기 토큰 해시와 state 는 중복될 수 없다.
2. 내리면 둘 다 사라지고 연결 상태 표의 다른 칸은 그대로다. 다시 올려도 된다.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.regression

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BEFORE = "0037_ai_runtime"


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


@pytest.mark.real_db
def test_upgrade_creates_the_attempt_table_and_downgrade_removes_it(db, db_url):
    engine = _engine(db, db_url)
    try:
        inspector = sa.inspect(engine)
        assert "ai_oauth_transactions" in inspector.get_table_names()
        columns = {c["name"] for c in inspector.get_columns("ai_credential_state")}
        assert "refresh_warned_at" in columns
        uniques = {tuple(u["column_names"]) for u in inspector.get_unique_constraints("ai_oauth_transactions")}
        assert {("pairing_token_hash",), ("state",)} <= uniques

        _alembic(db_url, "downgrade", BEFORE)
        inspector = sa.inspect(engine)
        assert "ai_oauth_transactions" not in inspector.get_table_names()
        columns = {c["name"] for c in inspector.get_columns("ai_credential_state")}
        assert "refresh_warned_at" not in columns and "access_expires_at" in columns

        _alembic(db_url, "upgrade", "head")
        assert "ai_oauth_transactions" in sa.inspect(engine).get_table_names()
    finally:
        engine.dispose()
