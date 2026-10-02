"""0047 — 알림 받을 메일 주소와 주소 확인 (계획 M4, D-550).

못박는 성질:
1. 기존 알림 설정 행은 그대로이고 새 열(`notify_email` · `notify_email_verified_at`)은 비어 있다 - 고르기 전까지 계정 주소로 받는다.
2. 한 사람 · 한 목적에 열린 확인은 하나다(부분 유일 색인). 끝났거나 취소된 확인은 몇 건이든 남는다.
3. 사용자를 지우면 그 사람의 확인 행도 지워진다(FK CASCADE).
4. 내리면 표와 열이 사라지고 다른 설정 값은 남는다. 다시 올려도 같다(재실행 무해).
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
import sqlalchemy as sa

from tests.regression.test_migration_0041_ai_policies import _alembic, _engine

pytestmark = pytest.mark.regression

BEFORE = "0046_ai_legacy_cleanup"
TARGET = "0047_notify_email"
WHEN = datetime(2026, 9, 1, 0, 0, 0)


def _verification(conn, user_id: str, *, consumed: bool = False, cancelled: bool = False) -> str:
    row_id = str(uuid.uuid4())
    conn.execute(sa.text(
        "INSERT INTO mail_address_verifications (id, user_id, purpose, email, attempts, consumed_at, cancelled_at, "
        "created_at, updated_at) VALUES (:id, :user, 'notify_email', 'other@example.com', 0, :consumed, :cancelled, :at, :at)"
    ), {"id": row_id, "user": user_id, "consumed": WHEN if consumed else None, "cancelled": WHEN if cancelled else None,
        "at": WHEN})
    return row_id


def _columns(engine, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(engine).get_columns(table)}


@pytest.mark.real_db
def test_notify_email_columns_and_verifications(db, db_url, make_user):
    keeper = make_user("mig-0047-keeper@goodmit.co.kr", role="user").id
    leaver = make_user("mig-0047-leaver@goodmit.co.kr", role="user").id
    engine = _engine(db, db_url)
    try:
        _alembic(db_url, "downgrade", BEFORE)
        assert "notify_email" not in _columns(engine, "user_preferences")
        with engine.begin() as conn:
            conn.execute(sa.text(
                "INSERT INTO user_preferences (id, user_id, muted_types, mail_enabled, mail_types, created_at, updated_at) "
                "VALUES (:id, :user, 'job_failed', true, '[\"ticket_assigned\"]', :at, :at)"
            ), {"id": str(uuid.uuid4()), "user": keeper, "at": WHEN})

        _alembic(db_url, "upgrade", TARGET)
        with engine.connect() as conn:
            row = conn.execute(sa.text(
                "SELECT muted_types, mail_enabled, mail_types, notify_email, notify_email_verified_at "
                "FROM user_preferences WHERE user_id = :user"
            ), {"user": keeper}).one()
        assert tuple(row) == ("job_failed", True, '["ticket_assigned"]', None, None), "기존 설정은 그대로, 새 열은 비어 있다"

        with engine.begin() as conn:
            _verification(conn, keeper, consumed=True)
            _verification(conn, keeper, cancelled=True)
            _verification(conn, keeper)
        with pytest.raises(sa.exc.IntegrityError):
            with engine.begin() as conn:
                _verification(conn, keeper)
        with engine.begin() as conn:
            _verification(conn, leaver)
            conn.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": leaver})
        with engine.connect() as conn:
            counts = dict(conn.execute(sa.text(
                "SELECT user_id, count(*) FROM mail_address_verifications GROUP BY user_id"
            )).all())
        assert counts == {keeper: 3}, "열린 확인은 하나, 끝난 확인은 남고, 지운 사용자의 확인은 함께 지워진다"

        _alembic(db_url, "downgrade", BEFORE)
        assert "mail_address_verifications" not in sa.inspect(engine).get_table_names()
        assert "notify_email" not in _columns(engine, "user_preferences")
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT muted_types FROM user_preferences WHERE user_id = :user"),
                                {"user": keeper}).scalar_one() == "job_failed"
        _alembic(db_url, "upgrade", TARGET)
        _alembic(db_url, "upgrade", "head")
        assert {"notify_email", "notify_email_verified_at"} <= _columns(engine, "user_preferences")
    finally:
        with engine.begin() as conn:
            if "mail_address_verifications" in sa.inspect(conn).get_table_names():
                conn.execute(sa.text("DELETE FROM mail_address_verifications"))
            conn.execute(sa.text("DELETE FROM user_preferences WHERE user_id = :user"), {"user": keeper})
        engine.dispose()
