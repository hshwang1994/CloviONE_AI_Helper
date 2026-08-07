from datetime import timedelta

import pytest

from app.core.errors import ConflictError
from app.jobs import repository
from app.jobs.models import Job

pytestmark = pytest.mark.unit


@pytest.fixture()
def now(fake_clock):
    return fake_clock.now()


def _enqueue(db, now, **kwargs):
    defaults = {"job_type": "test_job", "payload": {"n": 1}, "now": now}
    return repository.enqueue(db, **{**defaults, **kwargs})


def test_enqueue_and_claim_fifo(db, now):
    first = _enqueue(db, now, payload={"n": 1})
    _advance = now + timedelta(seconds=1)
    second = repository.enqueue(db, job_type="test_job", payload={"n": 2}, now=_advance)
    db.commit()

    claimed = repository.claim_next(db, now + timedelta(seconds=2))
    assert claimed.id == first.id
    assert claimed.status == "running"
    assert claimed.attempt_count == 1
    assert claimed.started_at is not None

    claimed2 = repository.claim_next(db, now + timedelta(seconds=2))
    assert claimed2.id == second.id

    assert repository.claim_next(db, now + timedelta(seconds=2)) is None


def test_future_available_at_not_claimable(db, now):
    _enqueue(db, now, available_at=now + timedelta(seconds=300))
    db.commit()
    assert repository.claim_next(db, now) is None
    assert repository.claim_next(db, now + timedelta(seconds=301)) is not None


def test_idempotency_key_dedup(db, now):
    a = _enqueue(db, now, idempotency_key="msg:abc")
    b = _enqueue(db, now, idempotency_key="msg:abc")
    db.commit()
    assert a.id == b.id
    assert db.query(Job).count() == 1


def test_fail_schedules_exponential_backoff(db, now):
    _enqueue(db, now)
    db.commit()
    job = repository.claim_next(db, now)  # attempt 1

    repository.fail(db, job, error="boom", now=now)
    db.commit()
    assert job.status == "queued"
    assert job.available_at == now + timedelta(seconds=5)  # 5 * 2^0

    # Not claimable until backoff elapses.
    assert repository.claim_next(db, now + timedelta(seconds=4)) is None
    job = repository.claim_next(db, now + timedelta(seconds=6))  # attempt 2
    assert job.attempt_count == 2

    repository.fail(db, job, error="boom2", now=now)
    db.commit()
    assert job.available_at == now + timedelta(seconds=10)  # 5 * 2^1


def test_exhausted_attempts_becomes_failed(db, now):
    _enqueue(db, now, max_attempts=2)
    db.commit()
    for i in range(2):
        job = repository.claim_next(db, now + timedelta(seconds=100 * i))
        assert job is not None
        repository.fail(db, job, error=f"fail {i}", now=now + timedelta(seconds=100 * i))
        db.commit()
    assert job.status == "failed"
    assert job.finished_at is not None


def test_permanent_failure_skips_retries(db, now):
    _enqueue(db, now, max_attempts=5)
    db.commit()
    job = repository.claim_next(db, now)
    repository.fail(db, job, error="fatal", now=now, permanent=True)
    db.commit()
    assert job.status == "failed"
    assert job.attempt_count == 1


def test_recover_stuck_requeues(db, now):
    _enqueue(db, now)
    db.commit()
    job = repository.claim_next(db, now)
    assert job.status == "running"

    later = now + timedelta(seconds=700)
    recovered = repository.recover_stuck(db, now=later, running_timeout_seconds=600)
    db.commit()
    assert len(recovered) == 1
    db.refresh(job)
    assert job.status == "queued"  # attempt 1 of 3 → retried


def test_recover_stuck_fails_exhausted_job(db, now):
    _enqueue(db, now, max_attempts=1)
    db.commit()
    job = repository.claim_next(db, now)
    later = now + timedelta(seconds=700)
    repository.recover_stuck(db, now=later, running_timeout_seconds=600)
    db.commit()
    db.refresh(job)
    assert job.status == "failed"


def test_manual_retry_resets_attempts(db, now):
    _enqueue(db, now, max_attempts=1)
    db.commit()
    job = repository.claim_next(db, now)
    repository.fail(db, job, error="x", now=now)
    db.commit()
    assert job.status == "failed"

    repository.retry_failed(db, job, now=now)
    db.commit()
    assert job.status == "queued"
    assert job.attempt_count == 0
    assert repository.claim_next(db, now) is not None


def test_cancel_queued_happy_path(db, now):
    job = _enqueue(db, now)
    db.commit()
    repository.cancel_queued(db, job, now=now)
    db.commit()
    assert job.status == "cancelled"
    assert job.finished_at == now
    assert job.started_at is None


def test_cancel_queued_rejects_a_job_the_worker_already_claimed(db, now):
    """Regression (backend-approvals-jobs 감사 #4): TOCTOU race between an operator's
    cancel request and the worker's `claim_next`.

    `cancel_queued` used to be an unconditional `UPDATE ... WHERE id = :id` — if the
    worker's atomic `claim_next` (queued→running, self-committing) won the race between
    the router's Python-level status check and this write actually landing, the old
    code silently clobbered `running` back to `cancelled` on a job the worker now owns
    and is actively executing. It must instead behave like `claim_next` itself: a
    compare-and-swap that only touches rows still `queued`, and refuse (rather than
    silently no-op-overwrite) when the row has already moved on.
    """
    job = _enqueue(db, now)
    db.commit()

    # Simulate: the worker's claim_next won the race and already flipped this job to
    # 'running' (and committed) before cancel_queued's own write lands.
    claimed = repository.claim_next(db, now)
    assert claimed.id == job.id
    assert claimed.status == "running"

    with pytest.raises(ConflictError):
        repository.cancel_queued(db, claimed, now=now)

    db.refresh(claimed)
    assert claimed.status == "running"  # NOT clobbered back to 'cancelled'


def test_queue_stats(db, now):
    _enqueue(db, now, payload={"a": 1})
    _enqueue(db, now, payload={"b": 2}, available_at=now + timedelta(seconds=999))
    db.commit()
    stats = repository.queue_stats(db, now=now)
    assert stats["queued"] == 2
    assert stats["ready"] == 1
    assert stats["oldest_queued_at"] is not None
