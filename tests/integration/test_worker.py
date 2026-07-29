import threading

import pytest

from app.jobs import repository
from app.jobs.exceptions import PermanentJobError
from app.jobs.models import Job
from app.jobs.worker import Worker, WorkerContext, parse_payload

pytestmark = pytest.mark.integration


@pytest.fixture()
def worker_env(app, settings, fake_clock):
    factory = app.state.session_factory
    executed = []

    def ok_handler(db, job, ctx):
        executed.append(("ok", parse_payload(job)))

    def flaky_handler(db, job, ctx):
        raise RuntimeError("transient failure")

    def fatal_handler(db, job, ctx):
        raise PermanentJobError("입력이 유효하지 않습니다")

    ctx = WorkerContext(settings=settings, clock=fake_clock)
    worker = Worker(
        factory,
        fake_clock,
        {"ok": ok_handler, "flaky": flaky_handler, "fatal": fatal_handler},
        ctx,
        poll_interval=0.01,
    )
    return worker, factory, executed


def _enqueue(factory, clock, job_type, payload=None, **kwargs):
    with factory() as db:
        job = repository.enqueue(
            db, job_type=job_type, payload=payload or {}, now=clock.now(), **kwargs
        )
        db.commit()
        return job.id


def _job_status(factory, job_id):
    with factory() as db:
        return db.get(Job, job_id).status


def test_worker_processes_success(worker_env, fake_clock):
    worker, factory, executed = worker_env
    job_id = _enqueue(factory, fake_clock, "ok", {"hello": "world"})
    assert worker.run_once() is True
    assert executed == [("ok", {"hello": "world"})]
    assert _job_status(factory, job_id) == "succeeded"
    assert worker.run_once() is False  # queue empty


def test_worker_transient_failure_requeues_with_backoff(worker_env, fake_clock):
    worker, factory, _ = worker_env
    job_id = _enqueue(factory, fake_clock, "flaky")
    assert worker.run_once() is True
    assert _job_status(factory, job_id) == "queued"

    # Before backoff elapses nothing to do; after, it retries again.
    assert worker.run_once() is False
    fake_clock.advance(6)
    assert worker.run_once() is True
    assert _job_status(factory, job_id) == "queued"  # attempt 2 also failed

    with factory() as db:
        job = db.get(Job, job_id)
        assert job.attempt_count == 2
        assert "transient failure" in job.last_error

    # Third (final) attempt exhausts max_attempts=3 → failed.
    fake_clock.advance(11)
    assert worker.run_once() is True
    assert _job_status(factory, job_id) == "failed"


def test_worker_permanent_error_fails_immediately(worker_env, fake_clock):
    worker, factory, _ = worker_env
    job_id = _enqueue(factory, fake_clock, "fatal")
    worker.run_once()
    assert _job_status(factory, job_id) == "failed"
    with factory() as db:
        assert "유효하지 않습니다" in db.get(Job, job_id).last_error


def test_worker_unknown_job_type_fails_permanently(worker_env, fake_clock):
    worker, factory, _ = worker_env
    job_id = _enqueue(factory, fake_clock, "no_such_handler")
    worker.run_once()
    assert _job_status(factory, job_id) == "failed"


def test_worker_corrupt_payload_is_permanent(worker_env, fake_clock):
    worker, factory, executed = worker_env
    job_id = _enqueue(factory, fake_clock, "ok")
    with factory() as db:
        db.get(Job, job_id).payload_json = "{corrupt"
        db.commit()
    worker.run_once()
    assert _job_status(factory, job_id) == "failed"
    assert executed == []


def test_worker_startup_sweep_recovers_stuck_jobs(worker_env, fake_clock):
    worker, factory, executed = worker_env
    job_id = _enqueue(factory, fake_clock, "ok")
    # Simulate a crash: job claimed but never finished.
    with factory() as db:
        repository.claim_next(db, fake_clock.now())
    assert _job_status(factory, job_id) == "running"

    fake_clock.advance(4000)  # past DEFAULT_RUNNING_TIMEOUT_SECONDS (3900)
    worker.sweep()
    assert _job_status(factory, job_id) == "queued"
    # Recovery reuses the retry path, so the requeued job carries a backoff.
    fake_clock.advance(10)
    worker.run_once()
    assert _job_status(factory, job_id) == "succeeded"


def test_run_forever_graceful_shutdown(worker_env, fake_clock):
    worker, factory, executed = worker_env
    _enqueue(factory, fake_clock, "ok")
    stop = threading.Event()
    thread = threading.Thread(target=worker.run_forever, args=(stop,), daemon=True)
    thread.start()
    # Give the loop a moment to process, then stop.
    for _ in range(200):
        if executed:
            break
        threading.Event().wait(0.01)
    stop.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert executed
