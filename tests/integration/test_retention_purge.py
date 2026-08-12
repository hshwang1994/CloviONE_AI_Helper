"""Retention purge of terminal jobs and schedule-run history (§21.6, §21.14).

The jobs and schedule_runs tables have no inbound foreign keys, so aged terminal
rows can be deleted outright to stop the queue/history growing without bound.
These tests pin: terminal + aged rows are purged; recent or non-terminal rows
are kept; and conversation deletes chunk their id list under SQLite's variable
limit.
"""

from datetime import timedelta

import pytest

from app.auth.models import UserSession
from app.core.retention import (
    purge_old_conversations,
    purge_old_jobs,
    purge_old_schedule_runs,
    purge_old_sessions,
    run_retention,
)
from app.jobs.models import (
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    Job,
)
from app.schedules.models import RUN_SUCCEEDED, ScheduleRun

pytestmark = pytest.mark.integration


def _make_job(db, *, status: str, updated_at, available_at=None) -> Job:
    job = Job(
        job_type="chat_message",
        payload_json="{}",
        status=status,
        available_at=available_at or updated_at,
        created_at=updated_at,
        updated_at=updated_at,
    )
    db.add(job)
    db.flush()
    return job


def _make_run(db, *, status: str, created_at) -> ScheduleRun:
    run = ScheduleRun(
        schedule_id="sched-1",
        scheduled_at=created_at,
        idempotency_key=f"run:{created_at.isoformat()}",
        status=status,
        created_at=created_at,
    )
    db.add(run)
    db.flush()
    return run


def test_purge_old_jobs_removes_aged_terminal_only(db, fake_clock):
    now = fake_clock.now()
    old = now - timedelta(days=61)
    recent = now - timedelta(days=1)

    aged_terminal = [
        _make_job(db, status=STATUS_SUCCEEDED, updated_at=old),
        _make_job(db, status=STATUS_FAILED, updated_at=old),
        _make_job(db, status=STATUS_CANCELLED, updated_at=old),
    ]
    # Kept: aged but non-terminal.
    kept_queued = _make_job(db, status=STATUS_QUEUED, updated_at=old)
    kept_running = _make_job(db, status=STATUS_RUNNING, updated_at=old)
    # Kept: terminal but still within retention.
    kept_recent = _make_job(db, status=STATUS_SUCCEEDED, updated_at=recent)
    db.commit()

    deleted = purge_old_jobs(db, now=now, retention_days=60)
    db.commit()

    assert deleted == 3
    remaining = {row.id for row in db.query(Job).all()}
    assert remaining == {kept_queued.id, kept_running.id, kept_recent.id}
    for job in aged_terminal:
        assert db.get(Job, job.id) is None


def test_purge_old_jobs_empty_when_none_aged(db, fake_clock):
    now = fake_clock.now()
    _make_job(db, status=STATUS_SUCCEEDED, updated_at=now - timedelta(days=5))
    db.commit()

    assert purge_old_jobs(db, now=now, retention_days=60) == 0
    assert db.query(Job).count() == 1


def test_purge_old_schedule_runs_removes_aged(db, fake_clock):
    now = fake_clock.now()
    aged = _make_run(db, status=RUN_SUCCEEDED, created_at=now - timedelta(days=61))
    kept = _make_run(db, status=RUN_SUCCEEDED, created_at=now - timedelta(days=2))
    db.commit()

    deleted = purge_old_schedule_runs(db, now=now, retention_days=60)
    db.commit()

    assert deleted == 1
    remaining = {row.id for row in db.query(ScheduleRun).all()}
    assert remaining == {kept.id}
    assert db.get(ScheduleRun, aged.id) is None


def _make_session(db, *, user_id, revoked_at=None, expires_at) -> UserSession:
    row = UserSession(
        token_hash=f"hash-{user_id}-{expires_at.isoformat()}",
        user_id=user_id,
        csrf_token="csrf",
        expires_at=expires_at,
        revoked_at=revoked_at,
    )
    db.add(row)
    db.flush()
    return row


def test_purge_old_sessions_keeps_unexpired_sessions_forever(db, fake_clock, make_user):
    """CORE-02: 아직 만료되지 않은(=살아 있는) 세션은 나이와 무관하게 절대 안 지운다."""
    now = fake_clock.now()
    u = make_user("retention-active@goodmit.co.kr")
    still_active = _make_session(
        db, user_id=u.id, revoked_at=None, expires_at=now + timedelta(days=1)
    )
    db.commit()

    deleted = purge_old_sessions(db, now=now, retention_days=60)
    db.commit()

    assert deleted == 0
    assert db.get(UserSession, still_active.id) is not None


def test_purge_old_sessions_removes_aged_revoked_only(db, fake_clock, make_user):
    now = fake_clock.now()
    u = make_user("retention-revoked@goodmit.co.kr")
    aged_revoked = _make_session(
        db, user_id=u.id, revoked_at=now - timedelta(days=61), expires_at=now - timedelta(days=61)
    )
    kept_recent_revoked = _make_session(
        db, user_id=u.id, revoked_at=now - timedelta(days=2), expires_at=now - timedelta(days=2)
    )
    db.commit()

    deleted = purge_old_sessions(db, now=now, retention_days=60)
    db.commit()

    assert deleted == 1
    assert db.get(UserSession, aged_revoked.id) is None
    assert db.get(UserSession, kept_recent_revoked.id) is not None


def test_purge_old_sessions_removes_aged_expired_never_revoked(db, fake_clock, make_user):
    """RET-01R: 만료됐지만 아무도 다시 찾지 않아 revoked_at이 끝내 안 찍힌 세션도
    expires_at 기준으로 유예 기간이 지나면 지운다(revoked_at IS NOT NULL 조건에만
    의존하면 이런 행은 영원히 안 지워졌다)."""
    now = fake_clock.now()
    u = make_user("retention-abandoned@goodmit.co.kr")
    abandoned_expired = _make_session(
        db, user_id=u.id, revoked_at=None, expires_at=now - timedelta(days=61)
    )
    kept_recently_expired = _make_session(
        db, user_id=u.id, revoked_at=None, expires_at=now - timedelta(days=2)
    )
    db.commit()

    deleted = purge_old_sessions(db, now=now, retention_days=60)
    db.commit()

    assert deleted == 1
    assert db.get(UserSession, abandoned_expired.id) is None
    assert db.get(UserSession, kept_recently_expired.id) is not None


def test_purge_old_conversations_chunks_large_backlog(db, fake_clock, make_user):
    """>500 aged conversations must delete without exceeding SQLite's var limit."""
    from app.conversations.models import Conversation

    owner = make_user(email="owner@goodmit.co.kr")
    now = fake_clock.now()
    old = now - timedelta(days=400)
    count = 1100  # spans multiple 500-id batches
    for i in range(count):
        db.add(
            Conversation(
                id=f"conv-{i}",
                user_id=owner.id,
                title=f"c{i}",
                created_at=old,
                updated_at=old,
            )
        )
    db.commit()

    deleted = purge_old_conversations(db, now=now, retention_days=365)
    db.commit()

    assert deleted == count
    assert db.query(Conversation).count() == 0


def test_run_retention_reports_jobs_and_schedule_runs(db, fake_clock, app):
    now = fake_clock.now()
    old = now - timedelta(days=100)
    _make_job(db, status=STATUS_SUCCEEDED, updated_at=old)
    _make_run(db, status=RUN_SUCCEEDED, created_at=old)
    db.commit()

    result = run_retention(db, now=now, settings_cache=app.state.settings_cache)
    db.commit()

    assert result["jobs"] == 1
    assert result["schedule_runs"] == 1
    assert "conversations" in result
    assert "notifications" in result
