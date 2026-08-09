"""Proof that concurrent publish transitions for two versions of the same
prompt name never produce two PUBLISHED rows (UB-04).

`transition()`'s publish path is read-then-write with no locking (commit
only happens at the request's end, in get_db): it reads the current
published row, archives it, then sets the target row to published. Two
admins publishing different versions of the same name at nearly the same
moment could both see the same "current published" state and each set
their own row to published — after that, every future transition()/
get_published() call for that name crashed with MultipleResultsFound (500).

Migration 0053 adds a partial unique index (name) WHERE status='published'
on both prompts and policies; transition() now catches the resulting
IntegrityError and raises a clean ConflictError (409) instead.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest

from app.core.db import make_engine, make_session_factory
from app.core.errors import ConflictError

pytestmark = pytest.mark.integration

THREADS = 8
NAME = "race-prompt"


def _seed_two_review_versions(url: str) -> tuple[str, str]:
    from app.prompts.models import STATUS_REVIEW, Prompt

    engine = make_engine(url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            a = Prompt(name=NAME, version=1, content="v1", status=STATUS_REVIEW)
            b = Prompt(name=NAME, version=2, content="v2", status=STATUS_REVIEW)
            db.add_all([a, b])
            db.commit()
            return a.id, b.id
    finally:
        engine.dispose()


def test_concurrent_publish_of_two_versions_never_duplicates(db_path):
    from app.prompts.models import STATUS_PUBLISHED, Prompt
    from app.prompts.service import transition

    url = f"sqlite:///{db_path.as_posix()}"
    now = datetime(2026, 8, 10, 0, 0, 0)
    id_a, id_b = _seed_two_review_versions(url)
    target_ids = [id_a, id_b] * (THREADS // 2)

    def attempt(row_id: str) -> str:
        engine = make_engine(url)
        factory = make_session_factory(engine)
        try:
            with factory() as db:
                row = db.get(Prompt, row_id)
                try:
                    transition(db, row, STATUS_PUBLISHED, now=now)
                    db.commit()
                    return "published"
                except ConflictError:
                    db.rollback()
                    return "conflict"
        finally:
            engine.dispose()

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        results = list(pool.map(attempt, target_ids))

    assert "published" in results, f"아무도 발행에 성공하지 못했다: {results}"

    # A later call must not crash even though the race exercised the conflict
    # path (previously: MultipleResultsFound once a duplicate existed).
    engine = make_engine(url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            from sqlalchemy import func, select

            count = db.execute(
                select(func.count()).select_from(Prompt).where(
                    Prompt.name == NAME, Prompt.status == STATUS_PUBLISHED,
                )
            ).scalar_one()
            assert count == 1, f"경합 뒤 같은 이름에 발행본이 {count}개 남았다"
    finally:
        engine.dispose()
