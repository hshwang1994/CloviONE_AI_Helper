"""Proof that concurrently trashing the same item never 500s — whole-product
re-audit finding 5.

`move_to_trash()` was check-then-insert with no locking: a double-click
delete, or two people deleting the same item at nearly the same moment,
could both see "not in trash yet" and both insert — the loser hit
uq_trash_item's UNIQUE constraint (item_type, notion_page_id) as a raw,
unhandled IntegrityError/OperationalError (500) instead of the clean 409
the sequential-duplicate path already had ready.

move_to_trash() now wraps the insert in begin_nested() and, on a write
conflict, raises the same "이미 휴지통에 있습니다." ConflictError instead —
unlike get_or_create_mapping, this is a genuine "already deleted" conflict,
not an idempotent get-or-create, so the loser should see 409, not a silent
row swap (mirrors app/quotas/router.py::create_quota).
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest

from app.core.db import make_engine, make_session_factory

pytestmark = pytest.mark.integration

THREADS = 8
PAGE_ID = "race-trash-page"


def _seed_user(url: str) -> str:
    from app.users.models import ROLE_USER, User

    engine = make_engine(url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            user = User(
                email="trash-racer@goodmit.co.kr",
                display_name="휴지통 레이서",
                password_hash="not-a-real-hash",
                role=ROLE_USER,
                active=True,
            )
            db.add(user)
            db.commit()
            return user.id
    finally:
        engine.dispose()


def test_concurrent_move_to_trash_of_same_item_never_500s(db_path):
    from app.core.errors import ConflictError
    from app.trash.models import TRASH_TICKET, TrashItem
    from app.trash.service import move_to_trash
    from app.users.models import User

    url = f"sqlite:///{db_path.as_posix()}"
    now = datetime(2026, 8, 13, 0, 0, 0)
    user_id = _seed_user(url)

    def attempt(_i: int) -> str:
        engine = make_engine(url)
        factory = make_session_factory(engine)
        try:
            with factory() as db:
                user = db.get(User, user_id)
                try:
                    move_to_trash(
                        db, item_type=TRASH_TICKET, notion_page_id=PAGE_ID,
                        title="경합 대상", url=None, user=user, now=now,
                    )
                    db.commit()
                    return "trashed"
                except ConflictError:
                    db.rollback()
                    return "conflict"
        finally:
            engine.dispose()

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        results = list(pool.map(attempt, range(THREADS)))

    assert results.count("trashed") == 1, f"정확히 하나만 성공해야 한다: {results}"
    assert all(r in ("trashed", "conflict") for r in results), f"500이 섞였다: {results}"

    engine = make_engine(url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            from sqlalchemy import func, select

            count = db.execute(
                select(func.count()).select_from(TrashItem).where(
                    TrashItem.item_type == TRASH_TICKET, TrashItem.notion_page_id == PAGE_ID,
                )
            ).scalar_one()
            assert count == 1, f"경합 뒤 같은 항목이 휴지통에 {count}개 남았다"
    finally:
        engine.dispose()
