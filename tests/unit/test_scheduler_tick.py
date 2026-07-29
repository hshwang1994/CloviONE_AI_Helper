"""Scheduler tick logic (spec §18.4, §18.5) — FakeClock only, no sleeps."""

import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.jobs.models import Job
from app.schedules.models import Schedule, ScheduleRun
from app.schedules.scheduler import SchedulerService, create_run_and_enqueue

pytestmark = pytest.mark.unit

BASE = datetime(2026, 7, 14, 0, 0, 0)


@pytest.fixture()
def scheduler(app, fake_clock):
    return SchedulerService(app.state.session_factory, fake_clock)


@pytest.fixture()
def make_schedule(db):
    def _make(**overrides):
        defaults = {
            "name": f"스케줄-{len(db.query(Schedule).all())}",
            "schedule_type": "cron",
            "cron_expression": "0 * * * *",  # 매시 정각
            "timezone": "UTC",
            "target_type": "system",
            "target_ref": "noop",
            "payload_template_json": "{}",
            "enabled": True,
            "next_run_at": BASE + timedelta(hours=1),
        }
        row = Schedule(**{**defaults, **overrides})
        db.add(row)
        db.commit()
        return row

    return _make


def _runs(db, schedule_id):
    return (
        db.execute(select(ScheduleRun).where(ScheduleRun.schedule_id == schedule_id))
        .scalars()
        .all()
    )


def test_due_schedule_creates_run_and_job(db, scheduler, make_schedule, fake_clock):
    schedule = make_schedule()
    fake_clock.advance(3600)  # BASE+1h — due
    assert scheduler.tick() == 1

    db.expire_all()
    runs = _runs(db, schedule.id)
    assert len(runs) == 1
    assert runs[0].status == "queued"
    job = db.execute(select(Job).where(Job.job_type == "schedule_run")).scalar_one()
    assert json.loads(job.payload_json)["schedule_run_id"] == runs[0].id

    # next_run_at advanced to the following hour.
    db.refresh(schedule)
    assert schedule.next_run_at == BASE + timedelta(hours=2)


def test_not_due_schedule_untouched(db, scheduler, make_schedule):
    schedule = make_schedule()
    assert scheduler.tick() == 0  # now == BASE, due at BASE+1h
    assert _runs(db, schedule.id) == []


def test_disabled_schedule_never_runs(db, scheduler, make_schedule, fake_clock):
    schedule = make_schedule(enabled=False)
    fake_clock.advance(7200)
    assert scheduler.tick() == 0
    assert _runs(db, schedule.id) == []


def test_duplicate_occurrence_claim_is_idempotent(db, make_schedule, fake_clock):
    schedule = make_schedule()
    when = BASE + timedelta(hours=1)
    first = create_run_and_enqueue(db, schedule, scheduled_at=when, now=when)
    second = create_run_and_enqueue(db, schedule, scheduled_at=when, now=when)
    db.commit()
    assert first is not None
    assert second is None
    assert len(_runs(db, schedule.id)) == 1
    # Only one job as well.
    assert db.query(Job).filter(Job.job_type == "schedule_run").count() == 1


def test_misfire_skip_policy(db, scheduler, make_schedule, fake_clock):
    schedule = make_schedule(misfire_policy="skip")
    fake_clock.advance(3600 * 5)  # 4 hours past due — beyond the 300s grace
    assert scheduler.tick() == 0

    db.expire_all()
    runs = _runs(db, schedule.id)
    assert len(runs) == 1
    assert runs[0].status == "skipped"
    assert runs[0].error_message == "misfire_skip"
    db.refresh(schedule)
    assert schedule.next_run_at > fake_clock.now()  # 미래로 재정렬
    assert db.query(Job).count() == 0


def test_misfire_run_once_policy(db, scheduler, make_schedule, fake_clock):
    schedule = make_schedule(misfire_policy="run_once")
    fake_clock.advance(3600 * 5)
    assert scheduler.tick() == 1  # 한 번만 따라잡기 실행

    db.expire_all()
    runs = _runs(db, schedule.id)
    assert len(runs) == 1
    assert runs[0].status == "queued"
    db.refresh(schedule)
    assert schedule.next_run_at > fake_clock.now()  # run-all-missed 금지


def test_concurrency_skip_while_run_active(db, scheduler, make_schedule, fake_clock):
    schedule = make_schedule(concurrency_policy="skip")
    fake_clock.advance(3600)
    scheduler.tick()  # 첫 실행 queued

    fake_clock.advance(3600)  # 다음 정각 — 앞선 run이 아직 queued
    scheduler.tick()

    db.expire_all()
    runs = _runs(db, schedule.id)
    statuses = sorted(r.status for r in runs)
    assert statuses == ["queued", "skipped"]


def test_concurrency_allow(db, scheduler, make_schedule, fake_clock):
    schedule = make_schedule(concurrency_policy="allow", name="동시허용")
    fake_clock.advance(3600)
    scheduler.tick()
    fake_clock.advance(3600)
    scheduler.tick()
    db.expire_all()
    assert sorted(r.status for r in _runs(db, schedule.id)) == ["queued", "queued"]


def test_once_schedule_disables_itself(db, scheduler, make_schedule, fake_clock):
    schedule = make_schedule(
        schedule_type="once", cron_expression=None,
        next_run_at=BASE + timedelta(minutes=10), name="한번만",
    )
    fake_clock.advance(600)
    assert scheduler.tick() == 1
    db.expire_all()
    db.refresh(schedule)
    assert schedule.enabled is False
    assert schedule.next_run_at is None

    fake_clock.advance(3600)
    assert scheduler.tick() == 0  # 다시 실행되지 않음


def test_end_at_disables_when_passed(db, scheduler, make_schedule, fake_clock):
    schedule = make_schedule(
        end_at=BASE + timedelta(hours=1, minutes=30), name="종료기한",
    )
    fake_clock.advance(3600)  # 1st occurrence at +1h runs; next (+2h) > end_at
    scheduler.tick()
    db.expire_all()
    db.refresh(schedule)
    assert schedule.enabled is False
    assert schedule.next_run_at is None
