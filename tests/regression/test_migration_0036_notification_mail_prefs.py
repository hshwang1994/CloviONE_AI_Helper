"""0036 — 메일로도 받기 두 칸 (계획 3.4, D-514).

못박는 성질:
1. 올리면 기존 설정 행은 메일 알림이 꺼져 있고(`mail_enabled=false`) 유형은 「아직 고르지 않음」(NULL)이다.
2. 다른 칸(배지 끄기, 방해금지)은 그대로다.
3. 내리면 두 칸이 사라지고 다시 올리면 돌아온다.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import text

pytestmark = pytest.mark.regression

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BEFORE = "0035_ticket_requester"


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
def test_existing_preferences_start_with_mail_off_and_keep_everything_else(db, db_url, make_user):
    from app.core.db import normalize_database_url
    from app.profiles.models import UserPreference

    user = make_user("mig36@goodmit.co.kr")
    db.flush()
    db.add(UserPreference(user_id=user.id, muted_types="job_failed", dnd_enabled=True))
    db.commit()
    user_id = user.id
    db.close()
    db.get_bind().dispose()

    engine = sa.create_engine(normalize_database_url(db_url), future=True)

    def columns() -> set[str]:
        with engine.connect() as conn:
            return set(conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'user_preferences'"
            )).scalars())

    try:
        _alembic(db_url, "downgrade", BEFORE)
        assert {"mail_enabled", "mail_types"}.isdisjoint(columns())
        _alembic(db_url, "upgrade", "head")
        assert {"mail_enabled", "mail_types"} <= columns()
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT mail_enabled, mail_types, muted_types, dnd_enabled FROM user_preferences WHERE user_id = :u"
            ), {"u": user_id}).one()
    finally:
        engine.dispose()

    assert row.mail_enabled is False, "업그레이드가 메일 알림을 몰래 켰다"
    assert row.mail_types is None, "고른 적 없는 사람에게 빈 선택(아무것도 안 받음)을 적었다"
    assert row.muted_types == "job_failed" and row.dnd_enabled is True
