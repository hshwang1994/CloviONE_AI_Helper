"""Proof that the single-statement claim is atomic: N threads, each with its
own engine/connection to the same database file, never claim the same job twice."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest

from app.core.db import make_engine, make_session_factory
from app.jobs import repository

# 이 파일의 시험은 **전용 DB** 가 필요하다(D-190) — 두 번째 커넥션이나 별도
# 프로세스가 이 시험의 데이터를 봐야 하기 때문이다. 공유 DB + 트랜잭션 되감기
# 계층에서는 그 데이터가 트랜잭션 밖으로 안 나가서 아무것도 증명하지 못한다.
pytestmark = [pytest.mark.integration, pytest.mark.real_db]

JOB_COUNT = 30
THREADS = 4


def test_concurrent_claims_are_exclusive(db_url):
    url = db_url
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
