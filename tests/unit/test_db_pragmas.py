import pytest
from sqlalchemy import text

from app.core.db import make_engine, make_session_factory

pytestmark = pytest.mark.unit


def test_sqlite_pragmas_applied(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'pragma.sqlite3').as_posix()}")
    factory = make_session_factory(engine)
    with factory() as db:
        assert db.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert db.execute(text("PRAGMA busy_timeout")).scalar() == 5000
        assert db.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert db.execute(text("PRAGMA synchronous")).scalar() == 1  # NORMAL
    engine.dispose()


def test_utcnow_is_naive_utc():
    from app.core.models_base import utcnow

    now = utcnow()
    assert now.tzinfo is None
