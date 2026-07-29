"""Scheduler tick: due-schedule evaluation with misfire, idempotency, and
concurrency policies (spec §18.4–18.7).

Duplicate-run prevention is insert-first: schedule_runs.idempotency_key =
"{schedule_id}:{scheduled_at}" with a UNIQUE constraint. Whoever inserts the
row owns the run; an IntegrityError means another scheduler instance won.
Pure logic — no sleeps; the worker loop calls tick() via tick_callbacks.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.jobs import repository as jobs_repo
from app.schedules import cron
from app.schedules.models import (
    CONCURRENCY_SKIP,
    MISFIRE_RUN_ONCE,
    MISFIRE_SKIP,
    RUN_QUEUED,
    RUN_RUNNING,
    RUN_SKIPPED,
    TYPE_CRON,
    TYPE_ONCE,
    Schedule,
    ScheduleRun,
)

logger = logging.getLogger("app.scheduler")

DEFAULT_MISFIRE_GRACE_SECONDS = 300
# once 스케줄은 다음 발생이 없어 skip이 곧 영구 소실이다. grace를 넘겨 misfire로 판정돼도
# 이 창 안이면 지금이라도 한 번 따라잡아 실행한다. 창을 넘기면 진짜 버리되 소유자에게 알린다.
DEFAULT_ONCE_CATCHUP_SECONDS = 3600


def run_key(schedule_id: str, scheduled_at: datetime) -> str:
    return f"{schedule_id}:{scheduled_at.strftime('%Y%m%d%H%M%S')}"


def advance_next_run(schedule: Schedule, *, after: datetime) -> None:
    if schedule.schedule_type == TYPE_ONCE:
        # 특정 일시 1회 (spec §18.1) — consumed after its single occurrence.
        schedule.enabled = False
        schedule.next_run_at = None
        return
    schedule.next_run_at = cron.next_after(
        schedule.cron_expression, schedule.timezone, after
    )
    if schedule.end_at is not None and schedule.next_run_at > schedule.end_at:
        schedule.enabled = False
        schedule.next_run_at = None


def _has_active_run(db: Session, schedule_id: str) -> bool:
    return (
        db.execute(
            select(ScheduleRun.id).where(
                ScheduleRun.schedule_id == schedule_id,
                ScheduleRun.status.in_([RUN_QUEUED, RUN_RUNNING]),
            )
        ).first()
        is not None
    )


def create_run_and_enqueue(
    db: Session,
    schedule: Schedule,
    *,
    scheduled_at: datetime,
    now: datetime,
    key: str | None = None,
    manual: bool = False,
) -> ScheduleRun | None:
    """Insert the run row (idempotency gate) and enqueue its job.
    Returns None if another instance already owns this occurrence."""
    key = key or run_key(schedule.id, scheduled_at)
    run = ScheduleRun(
        schedule_id=schedule.id,
        scheduled_at=scheduled_at,
        idempotency_key=key,
        status=RUN_QUEUED,
        request_payload_json=schedule.payload_template_json,
        created_at=now,
    )
    try:
        with db.begin_nested():
            db.add(run)
            db.flush()
    except IntegrityError:
        logger.info("run %s already claimed by another instance", key)
        return None

    jobs_repo.enqueue(
        db,
        job_type="schedule_run",
        payload={"schedule_run_id": run.id, "schedule_id": schedule.id, "manual": manual},
        now=now,
        idempotency_key=f"schedrun:{key}",
        max_attempts=_max_attempts(schedule),
    )
    return run


def _max_attempts(schedule: Schedule) -> int:
    try:
        policy = json.loads(schedule.retry_policy_json)
    except json.JSONDecodeError:
        policy = {}
    return max(1, min(int(policy.get("max_attempts", 3)), 10))


class SchedulerService:
    def __init__(
        self,
        session_factory: sessionmaker,
        clock,
        *,
        misfire_grace_seconds: int = DEFAULT_MISFIRE_GRACE_SECONDS,
        once_catchup_seconds: int = DEFAULT_ONCE_CATCHUP_SECONDS,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._grace = timedelta(seconds=misfire_grace_seconds)
        self._once_catchup = timedelta(seconds=once_catchup_seconds)

    def tick(self, now: datetime | None = None) -> int:
        now = now or self._clock.now()
        enqueued = 0
        with self._session_factory() as db:
            due = (
                db.execute(
                    select(Schedule).where(
                        Schedule.enabled.is_(True),
                        Schedule.next_run_at.is_not(None),
                        Schedule.next_run_at <= now,
                    )
                )
                .scalars()
                .all()
            )
            for schedule in due:
                try:
                    if self._process(db, schedule, now):
                        enqueued += 1
                except Exception:
                    logger.exception("schedule %s tick failed", schedule.id)
            db.commit()
        return enqueued

    def _process(self, db: Session, schedule: Schedule, now: datetime) -> bool:
        scheduled_at = schedule.next_run_at

        if schedule.start_at is not None and now < schedule.start_at:
            return False

        # Misfire (spec §18.4): the occurrence is long past (server downtime).
        if now - scheduled_at > self._grace:
            if schedule.misfire_policy == MISFIRE_SKIP:
                # once 스케줄은 다음 발생이 없다 — skip은 곧 영구 소실이다. 따라잡기 창
                # 안이면 지금이라도 실행(아래로 fall through)하고, 창을 넘겨 진짜로 버릴
                # 때만 소유자에게 알린다. cron은 다음 발생이 있으므로 기존대로 건너뛴다.
                if (
                    schedule.schedule_type == TYPE_ONCE
                    and now - scheduled_at <= self._once_catchup
                ):
                    pass  # catch-up: 아래 정상 실행 경로로 진행
                else:
                    self._record_skip(db, schedule, scheduled_at, now, "misfire_skip")
                    if schedule.schedule_type == TYPE_ONCE:
                        self._notify_owner_dropped(db, schedule, scheduled_at, now)
                    advance_next_run(schedule, after=now)
                    return False
            else:
                # RUN_ONCE: run a single catch-up occurrence now; missed ones drop.
                assert schedule.misfire_policy == MISFIRE_RUN_ONCE

        # 동시 실행 방지 (spec §18.5).
        if schedule.concurrency_policy == CONCURRENCY_SKIP and _has_active_run(
            db, schedule.id
        ):
            self._record_skip(db, schedule, scheduled_at, now, "concurrent_run_active")
            advance_next_run(schedule, after=now)
            return False

        run = create_run_and_enqueue(db, schedule, scheduled_at=scheduled_at, now=now)
        schedule.last_run_at = now
        advance_next_run(schedule, after=max(scheduled_at, now))
        return run is not None

    def _record_skip(
        self,
        db: Session,
        schedule: Schedule,
        scheduled_at: datetime,
        now: datetime,
        reason: str,
    ) -> None:
        run = ScheduleRun(
            schedule_id=schedule.id,
            scheduled_at=scheduled_at,
            idempotency_key=run_key(schedule.id, scheduled_at),
            status=RUN_SKIPPED,
            error_message=reason,
            created_at=now,
            finished_at=now,
        )
        try:
            with db.begin_nested():
                db.add(run)
                db.flush()
        except IntegrityError:
            pass  # 다른 인스턴스가 이미 처리

    def _notify_owner_dropped(
        self,
        db: Session,
        schedule: Schedule,
        scheduled_at: datetime,
        now: datetime,
    ) -> None:
        """once 스케줄이 따라잡기 창을 넘겨 영구히 버려질 때 소유자에게 알린다.

        그냥 'skipped' run 하나만 남기면 아무도 못 보고 조용히 사라진다(spec §18.4).
        소유자가 없으면(owner_user_id가 비어 있으면) 알릴 대상이 없으므로 건너뛴다.
        알림 실패가 tick 전체를 무너뜨리지 않게 방어한다.
        """
        if not schedule.owner_user_id:
            return
        try:
            from app.notifications.service import notify_user

            notify_user(
                db,
                schedule.owner_user_id,
                type_="schedule_failed",
                title=f"스케줄 '{schedule.name}' 실행 누락",
                body=(
                    f"1회성 스케줄이 예정 시각({scheduled_at.isoformat()})에 실행되지 못했고 "
                    f"따라잡기 허용 시간을 넘겨 취소되었습니다. 필요하면 다시 예약하세요."
                ),
                related=("schedule", schedule.id),
                now=now,
            )
        except Exception:
            logger.exception(
                "failed to notify owner of dropped once-schedule %s", schedule.id
            )
