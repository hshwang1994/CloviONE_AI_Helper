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

# 이 파일의 시험은 **전용 DB** 가 필요하다(D-190) — 두 번째 커넥션이나 별도
# 프로세스가 이 시험의 데이터를 봐야 하기 때문이다. 공유 DB + 트랜잭션 되감기
# 계층에서는 그 데이터가 트랜잭션 밖으로 안 나가서 아무것도 증명하지 못한다.
pytestmark = [pytest.mark.integration, pytest.mark.real_db]

THREADS = 8
NAME = "race-prompt"


def _seed_two_draft_versions(url: str, *, names=(NAME, NAME)) -> tuple[str, str]:
    """발행을 기다리는 초안 둘. 생명주기는 초안 → 발행 → 보관이다(D-518). 발행에는 사용처가 있어야 한다."""
    from app.prompts.models import STATUS_DRAFT, Prompt

    engine = make_engine(url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            a = Prompt(name=names[0], version=1, content="v1", status=STATUS_DRAFT, slot="draft")
            b = Prompt(name=names[1], version=1 if names[0] != names[1] else 2, content="v2", status=STATUS_DRAFT,
                       slot="draft")
            db.add_all([a, b])
            db.commit()
            return a.id, b.id
    finally:
        engine.dispose()


def test_concurrent_publish_of_two_versions_never_duplicates(db_url):
    from app.prompts.models import STATUS_PUBLISHED, Prompt
    from app.prompts.service import transition

    url = db_url
    now = datetime(2026, 8, 10, 0, 0, 0)
    id_a, id_b = _seed_two_draft_versions(url)
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


def test_two_prompts_racing_for_one_use_leave_exactly_one_in_use(db_url):
    """사용처마다 발행본은 하나다(D-518). 이름이 다른 두 프롬프트가 같은 사용처에 거의 동시에 발행돼도 하나만 남는다 -
    둘이 남으면 런타임이 어느 지시문을 쓸지 정할 수 없다."""
    from app.prompts.models import STATUS_PUBLISHED, Prompt
    from app.prompts.service import transition

    url = db_url
    now = datetime(2026, 8, 10, 0, 0, 0)
    id_a, id_b = _seed_two_draft_versions(url, names=("answer-a", "answer-b"))

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
        results = list(pool.map(attempt, [id_a, id_b] * (THREADS // 2)))
    assert "published" in results, f"아무도 발행에 성공하지 못했다: {results}"

    engine = make_engine(url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            from sqlalchemy import func, select

            count = db.execute(
                select(func.count()).select_from(Prompt).where(
                    Prompt.slot == "draft", Prompt.status == STATUS_PUBLISHED,
                )
            ).scalar_one()
            assert count == 1, f"경합 뒤 한 사용처에 발행본이 {count}개 남았다"
    finally:
        engine.dispose()
