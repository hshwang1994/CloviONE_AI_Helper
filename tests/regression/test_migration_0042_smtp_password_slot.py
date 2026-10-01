"""0042 — 메일 비밀번호 칸 고정: `smtp` 설정에서 `password_ref` 를 걷는다 (D-545).

못박는 성질:
1. 옛 `smtp` 값의 `password_ref` 는 사라지고 나머지 키는 그대로다.
2. `smtp` 행이 없거나 `password_ref` 가 없으면 아무것도 바꾸지 않는다.
3. 다시 돌려도(내렸다 올려도) 무해하다 - 걷은 이름은 되살아나지 않는다.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest
import sqlalchemy as sa

from tests.regression.test_migration_0041_ai_policies import _alembic, _engine

pytestmark = pytest.mark.regression

BEFORE = "0041_ai_policies"
TARGET = "0042_smtp_password_slot"
WHEN = datetime(2026, 9, 1, 0, 0, 0)

LEGACY_SMTP = {
    "enabled": True, "host": "smtp.internal", "port": 587, "security": "starttls",
    "from_address": "noreply@example.com", "from_name": "ClovirAssist", "username": "mailer",
    "password_ref": "ai.openai.api_key", "timeout_seconds": 20, "tls_verify": True, "ca_pem": "",
}


def _put_smtp(conn, value: dict) -> None:
    conn.execute(sa.text("DELETE FROM app_settings WHERE key = 'smtp'"))
    conn.execute(sa.text(
        "INSERT INTO app_settings (key, value_json, value_type, restart_required, updated_at) "
        "VALUES ('smtp', CAST(:v AS jsonb), 'object', false, :at)"
    ), {"v": json.dumps(value), "at": WHEN})


def _smtp(conn):
    row = conn.execute(sa.text("SELECT value_json FROM app_settings WHERE key = 'smtp'")).first()
    if row is None:
        return None
    return row[0] if isinstance(row[0], dict) else json.loads(row[0])


@pytest.mark.real_db
def test_the_secret_name_is_removed_and_the_rest_is_kept(db, db_url):
    engine = _engine(db, db_url)
    try:
        _alembic(db_url, "downgrade", BEFORE)
        with engine.begin() as conn:
            _put_smtp(conn, LEGACY_SMTP)
        _alembic(db_url, "upgrade", TARGET)
        with engine.begin() as conn:
            value = _smtp(conn)
        assert "password_ref" not in value, "다른 비밀을 가리키는 이름이 남았다"
        assert {k: v for k, v in value.items()} == {k: v for k, v in LEGACY_SMTP.items() if k != "password_ref"}

        # 내렸다 다시 올려도 걷은 이름은 되살아나지 않고 값도 그대로다.
        _alembic(db_url, "downgrade", BEFORE)
        _alembic(db_url, "upgrade", TARGET)
        with engine.begin() as conn:
            again = _smtp(conn)
        assert again == value
    finally:
        _alembic(db_url, "upgrade", "head")
        engine.dispose()


@pytest.mark.real_db
def test_nothing_changes_without_a_secret_name(db, db_url):
    engine = _engine(db, db_url)
    try:
        _alembic(db_url, "downgrade", BEFORE)
        with engine.begin() as conn:
            conn.execute(sa.text("DELETE FROM app_settings WHERE key = 'smtp'"))
        _alembic(db_url, "upgrade", TARGET)
        with engine.begin() as conn:
            assert _smtp(conn) is None, "smtp 행이 없는데 만들어졌다"

        plain = {k: v for k, v in LEGACY_SMTP.items() if k != "password_ref"}
        _alembic(db_url, "downgrade", BEFORE)
        with engine.begin() as conn:
            _put_smtp(conn, plain)
        _alembic(db_url, "upgrade", TARGET)
        with engine.begin() as conn:
            assert _smtp(conn) == plain
    finally:
        _alembic(db_url, "upgrade", "head")
        engine.dispose()
