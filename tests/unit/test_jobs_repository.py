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


# VIS-120: 대기/실행 중/실행 가능(ready)은 "지금 이 순간"만 잰다 — 최근에 계속 실패해
# 왔거나(재시도로 결국 큐를 빠져나간다) 처리가 느려지고 있다는 신호는 그 셋에 없다.
def test_queue_stats_recent_failed_24h_excludes_failures_outside_the_window(db, now):
    _enqueue(db, now, payload={"a": 1})
    _enqueue(db, now, payload={"b": 2})
    db.commit()
    recent = repository.claim_next(db, now)
    repository.fail(db, recent, error="boom", now=now + timedelta(hours=1), permanent=True)
    old = repository.claim_next(db, now)
    repository.fail(db, old, error="boom", now=now - timedelta(hours=25), permanent=True)
    db.commit()

    stats = repository.queue_stats(db, now=now)
    assert stats["recent_failed_24h"] == 1  # 24시간보다 전에 끝난 실패는 창 밖


def test_queue_stats_avg_processing_seconds_counts_succeeded_only(db, now):
    _enqueue(db, now, payload={"a": 1})
    _enqueue(db, now, payload={"b": 2})
    db.commit()
    succeeded = repository.claim_next(db, now)
    repository.finish(db, succeeded, now=now + timedelta(seconds=30))
    failed = repository.claim_next(db, now)
    # 실패는 재시도 백오프까지 걸린 시간이 섞이므로 평균에서 빠져야 한다 — 극단적으로
    # 오래(1시간) 걸린 실패를 섞어서, 만약 잘못 포함되면 평균이 크게 어긋나 바로 드러난다.
    repository.fail(db, failed, error="boom", now=now + timedelta(hours=1), permanent=True)
    db.commit()

    stats = repository.queue_stats(db, now=now + timedelta(hours=1))
    assert stats["avg_processing_seconds_24h"] == 30.0


def test_queue_stats_avg_processing_seconds_is_none_not_zero_when_nothing_recent(db, now):
    """0초와 '잴 것이 없음'은 다른 사실이다 — 성공 이력이 아예 없으면 None이지 0이 아니다."""
    stats = repository.queue_stats(db, now=now)
    assert stats["avg_processing_seconds_24h"] is None
    assert stats["recent_failed_24h"] == 0


# D-118 Phase 1 — 레인 필터(claim_next/recover_stuck). 아직 아무 실행 경로도 이 인자들을
# 넘기지 않는다(배선만) — 여기 시험이 그 배선이 실제로 동작하는지 미리 증명해 둔다.


def test_claim_next_default_args_claim_across_all_types(db, now):
    """기본 호출(레인 인자 없음)은 이 변경 전과 똑같이 job_type과 무관하게 클레임한다."""
    _enqueue(db, now, job_type="chat_message")
    _enqueue(db, now, job_type="schedule_run", available_at=now + timedelta(seconds=1))
    db.commit()
    first = repository.claim_next(db, now)
    second = repository.claim_next(db, now + timedelta(seconds=2))
    assert {first.job_type, second.job_type} == {"chat_message", "schedule_run"}


def test_claim_next_include_types_only_claims_matching_types(db, now):
    _enqueue(db, now, job_type="schedule_run")
    _enqueue(db, now, job_type="chat_message", available_at=now + timedelta(seconds=1))
    db.commit()
    claimed = repository.claim_next(db, now + timedelta(seconds=2), include_types=("chat_message",))
    assert claimed.job_type == "chat_message"
    # 배치 잡은 여전히 대기 중이다 — 대화형 레인이 안 채간다.
    remaining = db.query(Job).filter(Job.job_type == "schedule_run").one()
    assert remaining.status == "queued"


def test_claim_next_exclude_types_skips_matching_types(db, now):
    _enqueue(db, now, job_type="chat_message")
    _enqueue(db, now, job_type="schedule_run", available_at=now + timedelta(seconds=1))
    db.commit()
    claimed = repository.claim_next(db, now + timedelta(seconds=2), exclude_types=("chat_message",))
    assert claimed.job_type == "schedule_run"
    remaining = db.query(Job).filter(Job.job_type == "chat_message").one()
    assert remaining.status == "queued"


def test_claim_next_exclude_types_takeover_claims_stale_excluded_job(db, now):
    """대화형 레인이 죽었거나 없을 때, 오래 대기한 대화형 잡은 배치 레인이 대신 처리한다
    (조용히 영원히 안 처리되는 것보다 낫다)."""
    _enqueue(db, now, job_type="chat_message")
    db.commit()
    # 아직 유예 시간(120초) 안 — 배치 레인이 안 채간다.
    assert repository.claim_next(
        db, now + timedelta(seconds=60), exclude_types=("chat_message",), takeover_after_seconds=120,
    ) is None
    # 유예 시간을 넘기면 배치 레인이 인수한다.
    claimed = repository.claim_next(
        db, now + timedelta(seconds=121), exclude_types=("chat_message",), takeover_after_seconds=120,
    )
    assert claimed is not None
    assert claimed.job_type == "chat_message"


def test_recover_stuck_default_args_sweep_across_all_types(db, now):
    _enqueue(db, now, job_type="chat_message", max_attempts=1)
    _enqueue(db, now, job_type="schedule_run", max_attempts=1, available_at=now + timedelta(seconds=1))
    db.commit()
    repository.claim_next(db, now)
    repository.claim_next(db, now + timedelta(seconds=2))
    recovered = repository.recover_stuck(db, now=now + timedelta(seconds=4000))
    assert {j.job_type for j in recovered} == {"chat_message", "schedule_run"}


def test_recover_stuck_exclude_types_does_not_touch_a_running_batch_job(db, now):
    """레인 필터가 없으면 대화형 레인의 sweep이 배치 레인에서 실제로 아직 도는
    schedule_run을 '멈췄다'고 오판해 재큐잉할 수 있다 — WorkerLock이 막으려는 바로 그
    이중 실행이 sweep 경로로 재발한다(D-118). exclude_types가 이걸 막는다."""
    _enqueue(db, now, job_type="chat_message", max_attempts=1)
    _enqueue(db, now, job_type="schedule_run", max_attempts=1, available_at=now + timedelta(seconds=1))
    db.commit()
    repository.claim_next(db, now)
    repository.claim_next(db, now + timedelta(seconds=2))
    later = now + timedelta(seconds=4000)
    recovered = repository.recover_stuck(
        db, now=later, exclude_types=("schedule_run",),
    )
    assert [j.job_type for j in recovered] == ["chat_message"]
    still_running = db.query(Job).filter(Job.job_type == "schedule_run").one()
    assert still_running.status == "running"
