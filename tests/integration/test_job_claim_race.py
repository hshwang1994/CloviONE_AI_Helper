"""Proof that the single-statement claim is atomic: N threads, each with its
own engine/connection to the same database file, never claim the same job twice."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest

from app.core.db import make_engine, make_session_factory
from app.jobs import repository

pytestmark = pytest.mark.integration

JOB_COUNT = 30
THREADS = 4


def test_concurrent_claims_are_exclusive(db_path):
    url = f"sqlite:///{db_path.as_posix()}"
    now = datetime(2026, 7, 14, 0, 0, 0)

    seed_engine = make_engine(url)
    seed_factory = make_session_factory(seed_engine)
    with seed_factory() as db:
        for i in range(JOB_COUNT):
            repository.enqueue(db, job_type="race", payload={"i": i}, now=now)
        db.commit()
    seed_engine.dispose()

    def claim_all(worker_idx: int) -> list[str]:
        engine = make_engine(url)
        factory = make_session_factory(engine)
        claimed: list[str] = []
        try:
            while True:
                with factory() as db:
                    job = repository.claim_next(db, now)
                    if job is None:
                        return claimed
                    claimed.append(job.id)
        finally:
            engine.dispose()

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        results = list(pool.map(claim_all, range(THREADS)))

    all_claims = [job_id for chunk in results for job_id in chunk]
    assert len(all_claims) == JOB_COUNT, "some jobs were never claimed"
    assert len(set(all_claims)) == JOB_COUNT, "a job was claimed more than once!"
