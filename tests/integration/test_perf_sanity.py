"""Light performance sanity (spec §31.11) — generous assertions, no real load.
Confirms the system stays correct under modest concurrency, not throughput."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from app.core.db import make_engine, make_session_factory
from app.jobs import repository

pytestmark = pytest.mark.integration


def test_100_job_queue_drains_exactly_once(db_path, fake_clock):
    url = f"sqlite:///{db_path.as_posix()}"
    now = fake_clock.now()
    engine = make_engine(url)
    factory = make_session_factory(engine)
    with factory() as db:
        for i in range(100):
            repository.enqueue(db, job_type="perf", payload={"i": i}, now=now)
        db.commit()
    engine.dispose()

    def drain():
        e = make_engine(url)
        f = make_session_factory(e)
        claimed = []
        try:
            while True:
                with f() as db:
                    job = repository.claim_next(db, now)
                    if job is None:
                        return claimed
                    claimed.append(job.id)
        finally:
            e.dispose()

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: drain(), range(4)))
    all_ids = [j for chunk in results for j in chunk]
    assert len(all_ids) == 100
    assert len(set(all_ids)) == 100  # each job claimed exactly once


def test_50_schedule_next_run_computation(db):
    from datetime import datetime

    from app.schedules import cron

    # Computing the next fire time for 50 schedules must be fast and correct.
    after = datetime(2026, 7, 14, 12, 0, 0)
    for i in range(50):
        expr = f"{i % 60} * * * *"
        nxt = cron.next_after(expr, "Asia/Seoul", after)
        assert nxt > after


def test_10_concurrent_logins(app, make_user):
    from fastapi.testclient import TestClient

    from tests.conftest import DEFAULT_TEST_PASSWORD

    for i in range(10):
        make_user(f"concurrent{i}@goodmit.co.kr")

    def login(i):
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.post(
                "/login",
                json={"email": f"concurrent{i}@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD},
            )
            return r.status_code

    with ThreadPoolExecutor(max_workers=5) as pool:
        codes = list(pool.map(login, range(10)))
    assert all(c == 200 for c in codes)


def test_pagination_bounds(client, login_as):
    csrf = login_as("admin")
    # Over-large page_size is clamped by the PageParams validator (max 100).
    r = client.get("/api/admin/users", params={"page_size": 500}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 422  # exceeds max — rejected, never unbounded
    r = client.get("/api/admin/users", params={"page_size": 100}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
