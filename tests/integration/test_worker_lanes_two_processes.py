"""D-118 Phase 2 — real on-disk SQLite, two independent `Worker` instances (batch +
conversational) each with their own engine/session_factory pointed at the SAME file,
simulating two separate OS processes the way test_job_claim_race.py already does for
the single-lane case. `:memory:` would not prove anything about the actual
multi-connection concern these guard against (CLAUDE.md §3 — WAL/multi-connection
semantics must not be faked).

These are the five scenarios D-118's Phase 2 checklist named as the minimum bar before
the conversational lane can be turned on for real:
  (i)   a long-running batch job does not block a chat_message from being claimed
  (ii)  neither lane ever claims the other's job_type
  (iii) the conversational lane's sweep does not touch a running batch job
  (iv)  with the flag off (no lane kwargs), a single worker still processes chat exactly
        as before this feature existed
  (v)   if the conversational lane never shows up, the batch lane eventually takes over
        a stale chat_message after the takeover grace period (not never)
"""

from datetime import datetime, timedelta

import pytest

from app.core.config import Settings
from app.core.db import make_engine, make_session_factory
from app.jobs import repository
from app.jobs.lanes import CONVERSATIONAL_JOB_TYPES
from app.jobs.worker import Worker, WorkerContext
from tests.fakes.clock import FakeClock

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 17, 0, 0, 0)


def _make_worker(db_path, handlers, clock, *, settings, **lane_kwargs):
    """A worker with its own engine/session_factory — a separate connection to the
    same on-disk file, standing in for a separate OS process."""
    url = f"sqlite:///{db_path.as_posix()}"
    engine = make_engine(url)
    factory = make_session_factory(engine)
    ctx = WorkerContext(settings=settings, clock=clock)
    worker = Worker(factory, clock, handlers, ctx, **lane_kwargs)
    return worker, engine


def _enqueue(db_path, job_type, now, **kwargs):
    url = f"sqlite:///{db_path.as_posix()}"
    engine = make_engine(url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            job = repository.enqueue(db, job_type=job_type, payload={}, now=now, **kwargs)
            db.commit()
            return job.id
    finally:
        engine.dispose()


def _status(db_path, job_id):
    from app.jobs.models import Job

    url = f"sqlite:///{db_path.as_posix()}"
    engine = make_engine(url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            return db.get(Job, job_id).status
    finally:
        engine.dispose()


@pytest.fixture()
def lane_settings(settings: Settings) -> Settings:
    settings.worker_conversational_lane_enabled = True
    settings.worker_conversational_takeover_seconds = 120.0
    return settings


def _claim_and_leave_running(db_path, now, **claim_kwargs):
    """Simulate a job whose handler is genuinely still executing — `Worker.run_once`
    always finishes (or fails) the job in the same call once the handler returns, so
    to get a job stuck in `running` (the state a real long schedule_run sits in for
    up to 3600s) we claim it directly and stop there, exactly like
    test_worker.py::test_worker_startup_sweep_recovers_stuck_jobs does."""
    url = f"sqlite:///{db_path.as_posix()}"
    engine = make_engine(url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            job = repository.claim_next(db, now, **claim_kwargs)
            return job.id if job else None
    finally:
        engine.dispose()


def test_long_batch_job_does_not_block_a_chat_message(db_path, lane_settings):
    executed = []
    conv_handlers = {"chat_message": lambda db, job, ctx: executed.append(job.id)}
    conv, conv_engine = _make_worker(
        db_path, conv_handlers, FakeClock(NOW), settings=lane_settings,
        include_types=CONVERSATIONAL_JOB_TYPES,
    )
    try:
        schedule_id = _enqueue(db_path, "schedule_run", NOW)
        chat_id = _enqueue(db_path, "chat_message", NOW)

        claimed = _claim_and_leave_running(
            db_path, NOW, exclude_types=CONVERSATIONAL_JOB_TYPES,
            takeover_after_seconds=lane_settings.worker_conversational_takeover_seconds,
        )
        assert claimed == schedule_id
        assert _status(db_path, schedule_id) == "running"

        assert conv.run_once(NOW) is True  # unaffected by the stuck batch job
        assert executed == [chat_id]
        assert _status(db_path, chat_id) == "succeeded"
    finally:
        conv_engine.dispose()


def test_neither_lane_ever_claims_the_others_job_type(db_path, lane_settings):
    claimed_by_batch, claimed_by_conv = [], []
    batch_handlers = {"schedule_run": lambda db, job, ctx: claimed_by_batch.append(job.id)}
    conv_handlers = {"chat_message": lambda db, job, ctx: claimed_by_conv.append(job.id)}

    batch, batch_engine = _make_worker(
        db_path, batch_handlers, FakeClock(NOW), settings=lane_settings,
        exclude_types=CONVERSATIONAL_JOB_TYPES, takeover_after_seconds=lane_settings.worker_conversational_takeover_seconds,
    )
    conv, conv_engine = _make_worker(
        db_path, conv_handlers, FakeClock(NOW), settings=lane_settings,
        include_types=CONVERSATIONAL_JOB_TYPES,
    )
    try:
        chat_id = _enqueue(db_path, "chat_message", NOW)
        schedule_id = _enqueue(db_path, "schedule_run", NOW, available_at=NOW + timedelta(seconds=1))

        # Each lane polls repeatedly — a bug here would show up as cross-claiming, not
        # just on the first call.
        for _ in range(3):
            batch.run_once(NOW + timedelta(seconds=2))
            conv.run_once(NOW + timedelta(seconds=2))

        assert claimed_by_batch == [schedule_id]
        assert claimed_by_conv == [chat_id]
    finally:
        batch_engine.dispose()
        conv_engine.dispose()


def test_conversational_sweep_does_not_touch_a_running_batch_job(db_path, lane_settings):
    batch_handlers = {"schedule_run": lambda db, job, ctx: None}
    conv_handlers = {"chat_message": lambda db, job, ctx: None}

    batch, batch_engine = _make_worker(
        db_path, batch_handlers, FakeClock(NOW), settings=lane_settings,
        exclude_types=CONVERSATIONAL_JOB_TYPES, takeover_after_seconds=lane_settings.worker_conversational_takeover_seconds,
    )
    conv, conv_engine = _make_worker(
        db_path, conv_handlers, FakeClock(NOW), settings=lane_settings,
        include_types=CONVERSATIONAL_JOB_TYPES,
    )
    try:
        schedule_id = _enqueue(db_path, "schedule_run", NOW)
        claimed = _claim_and_leave_running(
            db_path, NOW, exclude_types=CONVERSATIONAL_JOB_TYPES,
            takeover_after_seconds=lane_settings.worker_conversational_takeover_seconds,
        )
        assert claimed == schedule_id
        assert _status(db_path, schedule_id) == "running"

        # Far past any running-timeout — a lane-blind sweep would recover this.
        later = NOW + timedelta(seconds=4000)
        recovered_by_conv = conv.sweep(later)
        assert recovered_by_conv == 0
        assert _status(db_path, schedule_id) == "running", (
            "대화형 sweep이 실행 중인 schedule_run을 건드렸다 — WorkerLock이 막으려는 "
            "이중 실행이 sweep 경로로 재발한다"
        )

        # The batch lane's OWN sweep still recovers it normally (sanity check that the
        # filter is lane-scoped, not a blanket "sweep never recovers anything" bug).
        recovered_by_batch = batch.sweep(later)
        assert recovered_by_batch == 1
    finally:
        batch_engine.dispose()
        conv_engine.dispose()


def test_flag_off_a_single_unfiltered_worker_still_processes_chat_exactly_as_before(db_path, settings):
    """settings.worker_conversational_lane_enabled defaults False — build_batch_worker
    then passes no lane kwargs at all, i.e. plain Worker(...) exactly like pre-D-118."""
    executed = []
    handlers = {"chat_message": lambda db, job, ctx: executed.append(job.id)}
    worker, engine = _make_worker(db_path, handlers, FakeClock(NOW), settings=settings)
    try:
        chat_id = _enqueue(db_path, "chat_message", NOW)
        assert worker.run_once(NOW) is True
        assert executed == [chat_id]
    finally:
        engine.dispose()


def test_takeover_fires_when_the_conversational_lane_never_shows_up(db_path, lane_settings):
    """The conversational lane process never starts (crashed, never installed) — the
    batch lane must eventually claim the stranded chat_message, not leave it forever."""
    executed = []
    handlers = {"chat_message": lambda db, job, ctx: executed.append(job.id)}
    batch, engine = _make_worker(
        db_path, handlers, FakeClock(NOW), settings=lane_settings,
        exclude_types=CONVERSATIONAL_JOB_TYPES, takeover_after_seconds=120,
    )
    try:
        chat_id = _enqueue(db_path, "chat_message", NOW)

        # Still within the grace period — batch must not grab it (the conversational
        # lane might just be a little slow to poll, not actually gone).
        assert batch.run_once(NOW + timedelta(seconds=60)) is False
        assert executed == []

        # Past the grace period — batch takes over rather than leaving it stranded.
        assert batch.run_once(NOW + timedelta(seconds=121)) is True
        assert executed == [chat_id]
    finally:
        engine.dispose()
