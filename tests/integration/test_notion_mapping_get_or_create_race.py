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
from sqlalchemy.exc import IntegrityError

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


def test_get_or_create_mapping_gives_up_cleanly_after_exhausting_retries(db, monkeypatch):
    """PA-RC-0008 — 예산을 다 쓰고도 승자가 안 보이면 raw 500(처리 안 된
    IntegrityError)이 아니라 깨끗한 409여야 한다. 실 스레드 경합 대신 `db.add()`가
    항상 (가짜) `IntegrityError`로 실패하게 고정한다 — 실제로는 아무 것도 추가되지
    않으므로 매 반복의 "이미 있나" 재조회도 빈 손으로 끝나 결정적으로 예산을 소진한다.
    """
    import app.notion_mapping.service as svc
    from app.core.errors import ConflictError
    from app.users.models import ROLE_USER, User

    user = User(
        email="exhaust-mapping-racer@goodmit.co.kr",
        display_name="매핑 소진 레이서",
        password_hash="not-a-real-hash",
        role=ROLE_USER,
        active=True,
    )
    db.add(user)
    db.commit()
    user_id = user.id

    attempts = []

    def _add_that_always_conflicts(_instance):
        attempts.append(1)
        raise IntegrityError("INSERT INTO user_notion_mappings", {}, Exception("UNIQUE constraint failed (fake)"))

    monkeypatch.setattr(db, "add", _add_that_always_conflicts)
    monkeypatch.setattr(svc.time, "sleep", lambda _seconds: None)  # 재시도 횟수/결과만 본다 — 실제로 자면 느려진다

    with pytest.raises(ConflictError):
        svc.get_or_create_mapping(db, user_id)
    assert len(attempts) == svc._GET_OR_CREATE_RETRIES, f"정확히 예산만큼 시도해야 한다: {attempts}"
