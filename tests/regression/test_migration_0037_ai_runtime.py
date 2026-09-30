"""0037 — 옛 AI 설정을 `ai_*` 로 옮긴다 (계획 3.13 · 3.16, D-515).

못박는 성질:
1. API 로 쓰던 설치는 Anthropic API 키 설정으로 옮겨지고, 켜져 있었으면 켜진 채다. 모델과 제한 시간이 따라온다.
2. 명령줄 도구로 켜져 있던 설치는 꺼지고 관리자가 알림을 받는다 - 몰래 다른 자격으로 바꾸지 않는다.
3. `llm_*` 행은 남지 않는다.
4. 되돌리면 API 설치의 설정이 `llm_*` 로 돌아간다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import text

pytestmark = pytest.mark.regression

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BEFORE = "0036_notification_mail_prefs"


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


def _settings(conn, prefix: str) -> dict:
    rows = conn.execute(text("SELECT key, value_json::text FROM app_settings WHERE key LIKE :p"), {"p": prefix + "%"})
    return {k: json.loads(v) for k, v in rows}


def _seed_old(conn, values: dict) -> None:
    types = {"llm_enabled": "string", "llm_backend": "string", "llm_model": "string",
             "llm_timeout_seconds": "int", "llm_max_concurrency": "int"}
    for key, value in values.items():
        conn.execute(text(
            "INSERT INTO app_settings (key, value_json, value_type, restart_required, updated_at) "
            "VALUES (:k, :v, :t, false, now()) ON CONFLICT (key) DO UPDATE SET value_json = EXCLUDED.value_json"
        ), {"k": key, "v": json.dumps(value), "t": types[key]})


def _engine(db, db_url):
    from app.core.db import normalize_database_url

    db.close()
    db.get_bind().dispose()
    return sa.create_engine(normalize_database_url(db_url), future=True)


@pytest.mark.real_db
def test_an_api_install_keeps_working_as_an_anthropic_api_key_install(db, db_url):
    engine = _engine(db, db_url)
    try:
        _alembic(db_url, "downgrade", BEFORE)
        with engine.begin() as conn:
            _seed_old(conn, {"llm_enabled": "on", "llm_backend": "api", "llm_model": "claude-old",
                             "llm_timeout_seconds": 900, "llm_max_concurrency": 3})
        _alembic(db_url, "upgrade", "head")
        with engine.connect() as conn:
            new, old = _settings(conn, "ai_"), _settings(conn, "llm_")
    finally:
        engine.dispose()
    assert new == {
        "ai_provider": "anthropic", "ai_auth_method": "api_key", "ai_model": "claude-old",
        "ai_generation_enabled": True, "ai_timeout_seconds": 300, "ai_max_concurrency": 3,
    }, new
    assert old == {}, "옛 설정 행이 남았다"


@pytest.mark.real_db
def test_a_cli_install_is_switched_off_and_admins_are_told(db, db_url, make_user):
    admin = make_user("mig37-admin@goodmit.co.kr", role="system_admin")
    user = make_user("mig37-user@goodmit.co.kr", role="user")
    db.commit()
    ids = {"admin": admin.id, "user": user.id}
    engine = _engine(db, db_url)
    try:
        _alembic(db_url, "downgrade", BEFORE)
        with engine.begin() as conn:
            _seed_old(conn, {"llm_enabled": "on", "llm_backend": "cli", "llm_model": "claude-old"})
        _alembic(db_url, "upgrade", "head")
        with engine.connect() as conn:
            new = _settings(conn, "ai_")
            notices = dict(conn.execute(text(
                "SELECT user_id, title FROM notifications WHERE type = 'ai_provider_state'"
            )).all())
    finally:
        engine.dispose()
    assert new == {"ai_generation_enabled": False}, "명령줄 도구 설치를 다른 자격으로 몰래 바꿨다"
    assert ids["admin"] in notices and ids["user"] not in notices, notices
    assert "다시 설정" in notices[ids["admin"]]


@pytest.mark.real_db
def test_downgrade_brings_the_api_settings_back(db, db_url):
    engine = _engine(db, db_url)
    try:
        _alembic(db_url, "downgrade", BEFORE)
        with engine.begin() as conn:
            _seed_old(conn, {"llm_enabled": "off", "llm_backend": "api", "llm_model": "claude-old"})
        _alembic(db_url, "upgrade", "head")
        _alembic(db_url, "downgrade", BEFORE)
        with engine.connect() as conn:
            old = _settings(conn, "llm_")
            tables = set(conn.execute(text(
                "SELECT table_name FROM information_schema.tables WHERE table_name = 'ai_credential_state'"
            )).scalars())
        _alembic(db_url, "upgrade", "head")
    finally:
        engine.dispose()
    assert old == {"llm_backend": "api", "llm_model": "claude-old", "llm_enabled": "off"}, old
    assert tables == set()
