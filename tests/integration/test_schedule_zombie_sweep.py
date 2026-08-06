"""좀비 `ScheduleRun` 이 스케줄을 영구히 막지 않는다 (S8).

`handle_schedule_run` 은 시작하면서 실행을 `running` 으로 적고 커밋한다. 실패하면
`on_failure` 가 `failed` 로 바꾼다 — **그런데 `on_failure` 자체가 실패하면** 워커가 그것을
`logger.exception("on_failure hook ... crashed")` 로 삼켜서 실행이 `running` 인 채로 남는다.

그 한 행이 `_has_active_run()` 에 걸린다. `concurrency_policy == "skip"` 인 스케줄이면
**그 스케줄의 모든 미래 실행이 영구히 skip 된다.** 그런데 화면상 스케줄은 멀쩡하다 —
`enabled` 이고 `next_run_at` 은 계속 전진한다. 이력에는 `skipped` 만 쌓이고,
자동으로 풀리는 경로가 저장소에 **없었다**(`Worker.sweep` 은 `Job` 만 본다).

운영자가 겪는 일: "이 스케줄이 어느 날부터 안 돈다. 그런데 켜져 있고 다음 실행 시각도 있다."
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.jobs.models import STATUS_FAILED, STATUS_RUNNING, Job
from app.schedules.models import (
    RUN_FAILED,
    RUN_RUNNING,
    RUN_SKIPPED,
    Schedule,
    ScheduleRun,
)
from app.schedules.scheduler import SchedulerService, create_run_and_enqueue, sweep_zombie_runs

pytestmark = pytest.mark.integration

BASE = datetime(2026, 7, 14, 0, 0, 0)


@pytest.fixture()
def skip_schedule(db):
    row = Schedule(
        name="막히는 스케줄", schedule_type="cron", cron_expression="0 * * * *",
        timezone="UTC", target_type="system", target_ref="noop",
        payload_template_json="{}", enabled=True, next_run_at=BASE + timedelta(hours=1),
        concurrency_policy="skip",
    )
    db.add(row)
    db.commit()
    return row


def _make_zombie(db, schedule, *, created_at=BASE, job_status=STATUS_FAILED):
    """실행은 `running`, 그 잡은 이미 끝난 상태 — `on_failure` 가 터진 뒤의 모습이다."""
    run = create_run_and_enqueue(db, schedule, scheduled_at=created_at, now=created_at)
    run.status = RUN_RUNNING
    run.started_at = created_at
    job = db.execute(
        select(Job).where(Job.idempotency_key == f"schedrun:{run.idempotency_key}")
    ).scalar_one()
    job.status = job_status
    db.commit()
    return run


def test_a_zombie_run_blocks_every_future_run_of_that_schedule(
    db, skip_schedule, app, fake_clock
):
    """전제 확인 — 이 결함이 실재한다는 것을 먼저 보인다."""
    _make_zombie(db, skip_schedule)

    scheduler = SchedulerService(app.state.session_factory, fake_clock)
    fake_clock.advance(3600 * 24)          # 하루가 지나도
    for _ in range(3):                      # 몇 번을 돌아도
        scheduler.tick(fake_clock.now())
        fake_clock.advance(3600)

    db.expire_all()
    runs = db.execute(
        select(ScheduleRun).where(ScheduleRun.schedule_id == skip_schedule.id)
    ).scalars().all()
    # 이유까지 본다 — misfire 로 건너뛴 것과 **동시 실행 방지로 막힌 것**은 다른 얘기다.
    blocked = [r for r in runs if r.status == RUN_SKIPPED
               and r.error_message == "concurrent_run_active"]
    assert blocked, f"동시 실행 방지로 막힌 회차가 없다: {[r.error_message for r in runs]}"
    # 스케줄 자체는 멀쩡해 보인다 — 그래서 아무도 못 알아챈다.
    db.refresh(skip_schedule)
    assert skip_schedule.enabled is True and skip_schedule.next_run_at is not None


def test_the_sweep_clears_the_zombie_and_the_schedule_runs_again(
    db, skip_schedule, app, fake_clock
):
    zombie = _make_zombie(db, skip_schedule)
    fake_clock.advance(3600 * 24)
    now = fake_clock.now()

    swept = sweep_zombie_runs(db, now=now)
    db.commit()
    assert swept == 1, "좀비를 못 찾았다 — 스케줄은 계속 막혀 있다"

    db.refresh(zombie)
    assert zombie.status == RUN_FAILED
    assert zombie.finished_at is not None
    assert "다음 실행이 막혀" in (zombie.error_message or ""), "왜 실패했는지 화면이 못 말한다"

    # 그리고 이제 실제로 다시 돈다 — 이것이 사용자가 겪는 층이다.
    # (막혀 있는 동안에도 `next_run_at` 은 매시 전진했으므로, 지금 시각이 다음 발생이다.
    #  misfire 유예 300초와 좀비 유예 900초가 겹치지 않게 여기서 맞춰 준다.)
    skip_schedule.next_run_at = now
    db.commit()
    scheduler = SchedulerService(app.state.session_factory, fake_clock)
    assert scheduler.tick(now) == 1
    db.expire_all()
    fresh = db.execute(
        select(ScheduleRun).where(
            ScheduleRun.schedule_id == skip_schedule.id, ScheduleRun.id != zombie.id
        )
    ).scalars().all()
    assert any(r.status != RUN_SKIPPED for r in fresh), "스윕 후에도 여전히 skip 된다"


def test_the_sweep_never_touches_a_run_whose_job_is_still_alive(
    db, skip_schedule, fake_clock
):
    """가장 위험한 오탐 — 느린 워크플로(최대 3600초)를 죽이면 안 된다.

    그래서 판정 근거를 타임아웃이 아니라 **잡이 아직 살아 있는지**로 둔다.
    """
    alive = _make_zombie(db, skip_schedule, job_status=STATUS_RUNNING)
    fake_clock.advance(3600 * 24)

    assert sweep_zombie_runs(db, now=fake_clock.now()) == 0
    db.refresh(alive)
    assert alive.status == RUN_RUNNING, "아직 도는 실행을 실패로 만들었다"


def test_a_freshly_created_run_is_left_alone(db, skip_schedule):
    """삽입 직후의 짧은 창에서 오판하지 않는다(유예)."""
    run = create_run_and_enqueue(db, skip_schedule, scheduled_at=BASE, now=BASE)
    db.commit()
    assert sweep_zombie_runs(db, now=BASE + timedelta(seconds=30)) == 0
    db.refresh(run)
    assert run.status != RUN_FAILED
