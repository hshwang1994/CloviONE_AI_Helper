"""Proof that concurrent get_or_create_mapping calls for the same user_id
never crash and never produce two rows — whole-product re-audit finding 5.

`get_or_create_mapping()` was check-then-insert with no locking: the
per-user `POST /{user_id}/verify` endpoint racing against the bulk
`notion_mapping_sync` job handler (which flushes per-user inside one
long-running transaction) for the same brand-new user could both see "no
mapping yet" and both insert — the loser hit user_id's UNIQUE constraint
as a raw, unhandled IntegrityError/OperationalError (500).

get_or_create_mapping() now wraps the insert in begin_nested() and, on a
write conflict, re-reads and returns the winner's row instead of raising —
this is a get-or-create contract, so the loser should get *a* row, not an
error (mirrors app/team_docs/service.py::record_view).
"""

from concurrent.futures import ThreadPoolExecutor

import pytest

from app.core.db import make_engine, make_session_factory

pytestmark = pytest.mark.integration

THREADS = 8


def _seed_user(url: str) -> str:
    from app.users.models import ROLE_USER, User

    engine = make_engine(url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            user = User(
                email="mapping-racer@goodmit.co.kr",
                display_name="매핑 레이서",
                password_hash="not-a-real-hash",
                role=ROLE_USER,
                active=True,
            )
            db.add(user)
            db.commit()
            return user.id
    finally:
        engine.dispose()


def test_concurrent_get_or_create_mapping_never_duplicates(db_path):
    from app.notion_mapping.models import UserNotionMapping
    from app.notion_mapping.service import get_or_create_mapping

    url = f"sqlite:///{db_path.as_posix()}"
    user_id = _seed_user(url)

    def attempt(_i: int) -> str:
        engine = make_engine(url)
        factory = make_session_factory(engine)
        try:
            with factory() as db:
                row = get_or_create_mapping(db, user_id)
                db.commit()
                return row.id
        finally:
            engine.dispose()

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        ids = list(pool.map(attempt, range(THREADS)))

    assert len(set(ids)) == 1, f"race created duplicate mappings for one user: {ids}"

    engine = make_engine(url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            from sqlalchemy import func, select

            count = db.execute(
                select(func.count()).select_from(UserNotionMapping).where(
                    UserNotionMapping.user_id == user_id
                )
            ).scalar_one()
            assert count == 1, f"경합 뒤 같은 user_id에 매핑이 {count}개 남았다"

            # 나중에 다시 불러도 크래시 없이 같은 행을 돌려준다(처리 안 된 IntegrityError였다면
            # 여기서 또 UNIQUE 위반 raw 500이 났을 것).
            again = get_or_create_mapping(db, user_id)
            assert again.id == ids[0]
    finally:
        engine.dispose()
