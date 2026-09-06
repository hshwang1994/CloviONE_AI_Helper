"""재시도 정책과 유효 기간을 **실행 직전에** 읽는 스케줄러 규칙 (FakeClock, sleep 없음).

`test_scheduler_tick.py` 는 만기·미스파이어·동시 실행 정책을 본다. 이 파일이 보는 것은
그 옆의 두 가지다:

  1. 저장된 `retry_policy` 를 읽을 수 없을 때 — 예전에는 `int("abc")` 가 그대로 터져
     자동 실행에서는 `tick()` 의 포괄 except 가 로그 한 줄로 삼켰고(실행 이력에 행조차
     안 남았다) 수동 실행에서는 500 이 됐다. 지금은 **그 실행을 실패로 남긴다.**
  2. `end_at` — 예전에는 다음 실행 시각을 계산한 **뒤**에만 읽혀서, 유효 기간이 이미
     끝난 일정이 창 밖에서 한 번은 실제로 돌았다.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.jobs.models import Job
from app.schedules.models import Schedule, ScheduleRun
from app.schedules.scheduler import (
    MAX_ATTEMPTS_CEILING,
    MAX_ATTEMPTS_DEFAULT,
    MAX_ATTEMPTS_FLOOR,
    UNREADABLE_RETRY_POLICY_MESSAGE,
    InvalidRetryPolicy,
    SchedulerService,
    _max_attempts,
)

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
            "retry_policy_json": "{}",
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


# ── _max_attempts: 읽을 수 있는 값과 없는 값 ────────────────────────────────


@pytest.mark.parametrize(
    "stored, expected",
    [
        ("{}", MAX_ATTEMPTS_DEFAULT),
        ('{"max_attempts": 1}', 1),
        ('{"max_attempts": 5}', 5),
        ('{"max_attempts": 10}', 10),
        # 범위 밖 **정수**는 예전처럼 자른다 — 이미 저장돼 돌고 있는 값이고, 자르기는
        # 예전부터 정의돼 있던 동작이라 지금 실패로 바꾸면 멀쩡히 돌던 일정이 멈춘다.
        ('{"max_attempts": 999}', MAX_ATTEMPTS_CEILING),
        ('{"max_attempts": 0}', MAX_ATTEMPTS_FLOOR),
        ('{"max_attempts": -1}', MAX_ATTEMPTS_FLOOR),
        # 모르는 키는 이 함수가 읽지 않는다.
        ('{"backoff": "linear"}', MAX_ATTEMPTS_DEFAULT),
    ],
)
def test_max_attempts_reads_a_policy_it_can_run(make_schedule, stored, expected):
    assert _max_attempts(make_schedule(retry_policy_json=stored)) == expected


@pytest.mark.parametrize(
    "stored",
    [
        '{"max_attempts": "abc"}',
        '{"max_attempts": "3"}',
        '{"max_attempts": [1]}',
        '{"max_attempts": 3.5}',
        '{"max_attempts": null}',
        '{"max_attempts": true}',   # bool 은 int 의 하위형이다 — 1 로 읽지 않는다
        "[1]",                       # 객체가 아니다
        # 깨진 JSON 은 여기 없다 — `JsonText`(jsonb) 가 쓰는 쪽에서 이미 거부한다.
        # `_max_attempts` 의 JSONDecodeError 갈래는 그 방어를 지나온 값을 위한 것이다.
    ],
)
def test_max_attempts_refuses_a_policy_it_cannot_run(make_schedule, stored):
    with pytest.raises(InvalidRetryPolicy):
        _max_attempts(make_schedule(retry_policy_json=stored))


# ── tick: 읽을 수 없는 정책은 조용히 사라지지 않는다 ────────────────────────


def test_tick_records_a_failed_run_when_the_policy_cannot_be_read(
    db, scheduler, make_schedule, fake_clock
):
    schedule = make_schedule(
        name="못 읽는 정책", retry_policy_json='{"max_attempts": "abc"}'
    )
    fake_clock.advance(3600)  # BASE+1h — 만기

    # tick 자체는 죽지 않고, '큐에 넣은 건수'로는 0 이다(넣지 못했으므로).
    assert scheduler.tick() == 0

    db.expire_all()
    runs = _runs(db, schedule.id)
    assert len(runs) == 1
    assert runs[0].status == "failed"
    assert runs[0].error_message == UNREADABLE_RETRY_POLICY_MESSAGE
    assert runs[0].finished_at is not None

    # 잡은 만들지 않는다 — 실을 시도 횟수를 모르기 때문이다.
    jobs = db.execute(select(Job).where(Job.job_type == "schedule_run")).scalars().all()
    assert jobs == []

    # 다음 발생으로 넘어가 큐가 이 일정에 걸려 멈추지 않는다.
    db.refresh(schedule)
    assert schedule.enabled is True
    assert schedule.next_run_at == BASE + timedelta(hours=2)


def test_tick_still_enqueues_a_schedule_whose_policy_is_readable(
    db, scheduler, make_schedule, fake_clock
):
    """반례 — 읽을 수 있는 정책은 예전 그대로 큐에 들어간다."""
    schedule = make_schedule(
        name="읽히는 정책", retry_policy_json='{"max_attempts": 2}'
    )
    fake_clock.advance(3600)
    assert scheduler.tick() == 1

    db.expire_all()
    runs = _runs(db, schedule.id)
    assert len(runs) == 1
    assert runs[0].status == "queued"
    assert runs[0].error_message is None

    job = (
        db.execute(select(Job).where(Job.job_type == "schedule_run")).scalars().one()
    )
    assert job.max_attempts == 2


# ── tick: 유효 기간이 끝난 발생은 실행하지 않는다 ───────────────────────────


def test_tick_does_not_run_an_occurrence_past_end_at(
    db, scheduler, make_schedule, fake_clock
):
    schedule = make_schedule(
        name="기간 밖 발생",
        next_run_at=BASE + timedelta(hours=1),
        end_at=BASE + timedelta(minutes=30),
    )
    fake_clock.advance(3600)
    assert scheduler.tick() == 0

    db.expire_all()
    assert _runs(db, schedule.id) == []

    db.refresh(schedule)
    assert schedule.enabled is False
    assert schedule.next_run_at is None


def test_tick_runs_an_occurrence_inside_the_window(
    db, scheduler, make_schedule, fake_clock
):
    """반례 — 유효 기간 **안**의 발생은 그대로 실행된다."""
    schedule = make_schedule(
        name="기간 안 발생",
        next_run_at=BASE + timedelta(hours=1),
        end_at=BASE + timedelta(hours=3),
    )
    fake_clock.advance(3600)
    assert scheduler.tick() == 1

    db.expire_all()
    runs = _runs(db, schedule.id)
    assert len(runs) == 1
    assert runs[0].status == "queued"
