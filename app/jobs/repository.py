"""Job queue persistence: atomic claim, retry with backoff, stuck recovery.

The claim is a single UPDATE … RETURNING statement — atomic under SQLite WAL
with busy_timeout, so N workers can never claim the same job twice
(proven by tests/integration/test_job_claim_race.py).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.jobs.models import (
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    Job,
)

# Backoff: 5s, 10s, 20s, … (base * 2^(attempt-1))
BACKOFF_BASE_SECONDS = 5.0
# Must exceed the longest legitimate handler runtime (scheduler timeout up to
# 3600s) so recovery never requeues a job that is genuinely still running.
DEFAULT_RUNNING_TIMEOUT_SECONDS = 3900


def enqueue(
    db: Session,
    *,
    job_type: str,
    payload: dict,
    now: datetime,
    user_id: str | None = None,
    conversation_id: str | None = None,
    message_id: str | None = None,
    idempotency_key: str | None = None,
    max_attempts: int = 3,
    available_at: datetime | None = None,
) -> Job:
    if idempotency_key is not None:
        existing = get_by_idempotency_key(db, idempotency_key)
        if existing is not None:
            return existing

    job = Job(
        job_type=job_type,
        user_id=user_id,
        conversation_id=conversation_id,
        message_id=message_id,
        payload_json=json.dumps(payload, ensure_ascii=False),
        status=STATUS_QUEUED,
        max_attempts=max_attempts,
        idempotency_key=idempotency_key,
        available_at=available_at or now,
        created_at=now,
        updated_at=now,
    )
    try:
        with db.begin_nested():
            db.add(job)
            db.flush()
    except IntegrityError:
        # Another writer inserted the same idempotency key first.
        existing = get_by_idempotency_key(db, idempotency_key) if idempotency_key else None
        if existing is not None:
            return existing
        raise
    return job


def get_by_idempotency_key(db: Session, key: str) -> Job | None:
    return db.execute(
        select(Job).where(Job.idempotency_key == key)
    ).scalar_one_or_none()


def claim_next(db: Session, now: datetime) -> Job | None:
    """Atomically claim the oldest ready job. Commits the claim."""
    # Must match SQLAlchemy's SQLite DATETIME storage format exactly
    # (microseconds always present) — string comparison depends on it.
    now_str = now.strftime("%Y-%m-%d %H:%M:%S.%f")
    row = db.execute(
        text(
            """
            UPDATE jobs
            SET status = 'running',
                started_at = :now,
                attempt_count = attempt_count + 1,
                updated_at = :now
            WHERE id = (
                SELECT id FROM jobs
                WHERE status = 'queued' AND available_at <= :now
                ORDER BY created_at, id
                LIMIT 1
            )
            RETURNING id
            """
        ),
        {"now": now_str},
    ).fetchone()
    db.commit()
    if row is None:
        return None
    job = db.get(Job, row[0])
    # The raw UPDATE bypassed the ORM — refresh so the instance reflects
    # the claimed state (identity map would otherwise serve stale values).
    db.refresh(job)
    return job


def finish(db: Session, job: Job, *, now: datetime) -> None:
    job.status = STATUS_SUCCEEDED
    job.finished_at = now
    job.last_error = None
    db.flush()


def fail(
    db: Session,
    job: Job,
    *,
    error: str,
    now: datetime,
    permanent: bool = False,
) -> None:
    job.last_error = (error or "")[:2000]
    if permanent or job.attempt_count >= job.max_attempts:
        job.status = STATUS_FAILED
        job.finished_at = now
    else:
        job.status = STATUS_QUEUED
        delay = BACKOFF_BASE_SECONDS * (2 ** (job.attempt_count - 1))
        job.available_at = now + timedelta(seconds=delay)
        job.started_at = None
    db.flush()


def retry_failed(db: Session, job: Job, *, now: datetime) -> Job:
    """Manual retry of a failed job (spec §10.2 operator capability)."""
    job.status = STATUS_QUEUED
    job.attempt_count = 0
    job.available_at = now
    job.finished_at = None
    job.started_at = None  # clear the prior run's start so the requeued job is clean
    db.flush()
    return job


def cancel_queued(db: Session, job: Job, *, now: datetime) -> Job:
    job.status = STATUS_CANCELLED
    job.finished_at = now
    job.started_at = None
    db.flush()
    return job


def recover_stuck(
    db: Session,
    *,
    now: datetime,
    running_timeout_seconds: int = DEFAULT_RUNNING_TIMEOUT_SECONDS,
) -> list[Job]:
    """Requeue (or fail) jobs left 'running' by a crashed worker (spec §22).
    Returns the recovered jobs so the caller can fire failure hooks."""
    cutoff = now - timedelta(seconds=running_timeout_seconds)
    stuck = (
        db.execute(
            select(Job).where(Job.status == STATUS_RUNNING, Job.started_at < cutoff)
        )
        .scalars()
        .all()
    )
    for job in stuck:
        fail(db, job, error="worker timeout — stuck job recovered", now=now)
    db.flush()
    return list(stuck)


def queue_stats(db: Session, *, now: datetime) -> dict:
    from sqlalchemy import func

    counts = dict(
        db.execute(select(Job.status, func.count()).group_by(Job.status)).all()
    )
    ready = db.execute(
        select(func.count())
        .select_from(Job)
        .where(Job.status == STATUS_QUEUED, Job.available_at <= now)
    ).scalar_one()
    oldest_queued = db.execute(
        select(func.min(Job.created_at)).where(Job.status == STATUS_QUEUED)
    ).scalar_one()
    return {
        "queued": counts.get(STATUS_QUEUED, 0),
        "running": counts.get(STATUS_RUNNING, 0),
        "succeeded": counts.get(STATUS_SUCCEEDED, 0),
        "failed": counts.get(STATUS_FAILED, 0),
        "cancelled": counts.get(STATUS_CANCELLED, 0),
        "ready": ready,
        "oldest_queued_at": oldest_queued.isoformat() if oldest_queued else None,
    }
