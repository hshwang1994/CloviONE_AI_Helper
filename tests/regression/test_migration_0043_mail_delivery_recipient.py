"""0043 — 메일 발송 기록의 받는 사람 축과 실패 단계 (D-547 · D-546).

못박는 성질:
1. params 의 `user_id` 가 있는 사용자를 가리키면 그 사람이 받는 사람이다.
2. 없으면 받는 주소를 대소문자를 접어 사용자 이메일과 맞춘다.
3. 둘 다 못 맞추면 비워 둔다(그 행은 전역 관리자만 본다).
4. 내리면 칸 셋이 사라지고, 다시 올리면 다시 채운다.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest
import sqlalchemy as sa

from tests.regression.test_migration_0041_ai_policies import _alembic, _engine

pytestmark = pytest.mark.regression

BEFORE = "0042_smtp_password_slot"
TARGET = "0043_mail_delivery_recipient"
WHEN = datetime(2026, 9, 1, 0, 0, 0)


def _delivery(conn, *, kind: str, to_email: str, params: dict) -> str:
    row_id = str(uuid.uuid4())
    conn.execute(sa.text(
        "INSERT INTO mail_deliveries (id, kind, to_email, subject, status, attempt_count, params_json, "
        "created_at, updated_at) VALUES (:id, :kind, :to, '제목', 'unconfigured', 0, CAST(:p AS jsonb), :at, :at)"
    ), {"id": row_id, "kind": kind, "to": to_email, "p": json.dumps(params), "at": WHEN})
    return row_id


def _recipients(conn) -> dict[str, str | None]:
    return dict(conn.execute(sa.text("SELECT id, recipient_user_id FROM mail_deliveries")).all())


@pytest.mark.real_db
def test_old_rows_get_their_recipient(db, db_url, make_user):
    invited = make_user("mig-invited@goodmit.co.kr").id
    admin = make_user("Mig-Admin@goodmit.co.kr", role="admin").id
    engine = _engine(db, db_url)
    try:
        _alembic(db_url, "downgrade", BEFORE)
        with engine.begin() as conn:
            conn.execute(sa.text("DELETE FROM mail_deliveries"))
            by_param = _delivery(conn, kind="invite", to_email="other@goodmit.co.kr", params={"user_id": invited})
            by_mail = _delivery(conn, kind="backup_failed", to_email="mig-admin@GOODMIT.co.kr", params={"reason": "x"})
            stranger = _delivery(conn, kind="test", to_email="nobody@example.com", params={})
            ghost = _delivery(conn, kind="password_reset", to_email="ghost@goodmit.co.kr", params={"user_id": "gone"})
        _alembic(db_url, "upgrade", TARGET)
        with engine.begin() as conn:
            got = _recipients(conn)
            cols = {c["name"] for c in sa.inspect(conn).get_columns("mail_deliveries")}
        assert got[by_param] == invited, "params 의 사용자를 받는 사람으로 쓰지 않았다"
        assert got[by_mail] == admin, "주소를 대소문자를 접어 맞추지 않았다"
        assert got[stranger] is None and got[ghost] is None, "못 맞춘 행에 누군가를 붙였다"
        assert {"recipient_user_id", "failure_stage", "relay_response"} <= cols

        _alembic(db_url, "downgrade", BEFORE)
        with engine.begin() as conn:
            cols = {c["name"] for c in sa.inspect(conn).get_columns("mail_deliveries")}
        assert not ({"recipient_user_id", "failure_stage", "relay_response"} & cols)
        _alembic(db_url, "upgrade", TARGET)
        with engine.begin() as conn:
            assert _recipients(conn)[by_param] == invited, "다시 올렸을 때 다시 채우지 않았다"
    finally:
        _alembic(db_url, "upgrade", "head")
        engine.dispose()
