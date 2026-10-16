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
    RUN_FAILED,
    RUN_QUEUED,
    RUN_RUNNING,
    RUN_SKIPPED,
    TYPE_CRON,
    TYPE_ONCE,
    Schedule,
    ScheduleRun,
)

logger = logging.getLogger("app.scheduler")

#: 재시도 횟수의 허용 범위. 스키마 경계(app/schedules/router.py::ScheduleRequest)와
#: 실행 경계(_max_attempts)가 **같은 값**을 본다 — 두 곳이 갈라지면 저장은 되는데 실행은
#: 안 되는 값이 다시 생긴다.
MAX_ATTEMPTS_FLOOR = 1
MAX_ATTEMPTS_CEILING = 10
MAX_ATTEMPTS_DEFAULT = 3

#: 저장된 재시도 정책을 읽을 수 없을 때 실행 이력에 남기는 문장. 운영자가 실행 이력의
#: '오류' 칸에서 바로 읽고 무엇을 고치면 되는지 알 수 있어야 한다.
UNREADABLE_RETRY_POLICY_MESSAGE = (
    "재시도 정책을 읽을 수 없어 이 실행을 시작하지 못했습니다. "
    "일정을 수정해 재시도 횟수를 1~10 사이 정수로 바꾸면 다시 실행할 수 있습니다."
)


class InvalidRetryPolicy(ValueError):
    """저장된 `retry_policy` 를 실행 계획으로 읽을 수 없다.

    `int(policy["max_attempts"])` 가 그대로 터지면 수동 실행은 500 이 되고 자동 실행은
    tick 의 포괄 except 에 삼켜져 **아무 흔적도 남지 않는다**. 전용 예외로 올려 두면
    부르는 쪽이 "실행을 실패로 남긴다"(자동)와 "무엇을 고치라고 답한다"(수동)를 갈라
    처리할 수 있다.
    """


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


def _insert_run(
    db: Session,
    schedule: Schedule,
    *,
    scheduled_at: datetime,
    now: datetime,
    key: str,
    status: str,
    error_message: str | None = None,
) -> ScheduleRun | None:
    """실행 행 하나를 넣는다 — 멱등 키가 이미 있으면 `None`(남이 먼저 가져갔다).

    큐에 넣을 실행과 시작도 못 한 실행이 **같은 자리**를 쓴다. 두 경로가 각자 INSERT 를
    쓰면 한쪽만 멱등 키를 지키게 되고, 그 순간 같은 발생에 행이 둘 생긴다.
    """
    run = ScheduleRun(
        schedule_id=schedule.id,
        scheduled_at=scheduled_at,
        idempotency_key=key,
        status=status,
        request_payload_json=schedule.payload_template_json,
        created_at=now,
        error_message=error_message,
        started_at=now if status == RUN_FAILED else None,
        finished_at=now if status == RUN_FAILED else None,
    )
    try:
        with db.begin_nested():
            db.add(run)
            db.flush()
    except IntegrityError:
        logger.info("run %s already claimed by another instance", key)
        return None
    return run


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
    Returns None if another instance already owns this occurrence.

    재시도 정책을 읽을 수 없으면 **예외로 빠져나가지 않고 그 실행을 실패로 남긴다.**
    예전에는 여기서 터진 예외가 자동 실행(tick)에서는 로그 한 줄로 삼켜지고 수동
    실행에서는 500 이 됐다 — 둘 다 실행 이력에 아무 행도 남기지 않아서, 관리자에게는
    "아직 시간이 안 됐다" 와 "이 일정은 영원히 못 돈다" 가 똑같이 보였다.
    """
    key = key or run_key(schedule.id, scheduled_at)
    try:
        attempts = _max_attempts(schedule)
    except InvalidRetryPolicy:
        logger.warning(
            "schedule %s: 재시도 정책을 읽을 수 없어 실행을 실패로 남긴다", schedule.id
        )
        return _insert_run(
            db, schedule, scheduled_at=scheduled_at, now=now, key=key,
            status=RUN_FAILED, error_message=UNREADABLE_RETRY_POLICY_MESSAGE,
        )

    run = _insert_run(
        db, schedule, scheduled_at=scheduled_at, now=now, key=key, status=RUN_QUEUED
    )
    if run is None:
        return None

    jobs_repo.enqueue(
        db,
        job_type="schedule_run",
        payload={"schedule_run_id": run.id, "schedule_id": schedule.id, "manual": manual},
        now=now,
        idempotency_key=f"schedrun:{key}",
        max_attempts=attempts,
    )
    return run


ZOMBIE_GRACE_SECONDS = 900.0


def sweep_zombie_runs(db: Session, *, now: datetime, grace_seconds: float = ZOMBIE_GRACE_SECONDS) -> int:
    """끝난 잡을 뒤에 남긴 `queued`/`running` 실행을 정리한다 (S8).

    ## 무엇이 고장났었나

    `handle_schedule_run` 은 시작하면서 실행을 `running` 으로 적고 커밋한다. 실패하면
    `on_failure` 가 `failed` 로 바꾼다 — **그런데 `on_failure` 자체가 실패하면**
    (워커가 `logger.exception("on_failure hook ... crashed")` 로 삼킨다) 실행은 `running`
    인 채로 영원히 남는다.

    그 한 행이 `_has_active_run()` 에 걸린다. `concurrency_policy == skip` 인 스케줄이면
    **그 스케줄의 모든 미래 실행이 영구히 skip 된다.** 화면상 스케줄은 멀쩡하고
    (`enabled`, `next_run_at` 은 계속 전진한다) 이력에는 `skipped` 만 쌓인다.
    자동으로 풀리는 경로가 **저장소에 없었다** — `Worker.sweep` 은 `Job` 만 본다.

    ## 판정 근거를 임의의 타임아웃으로 두지 않는다

    실행 하나는 잡 하나와 1:1 이고 그 링크가 `idempotency_key` 에 있다
    (`create_run_and_enqueue` 가 `schedrun:<run key>` 로 넣는다). 그래서 **잡이 이미
    끝났는지**를 보면 된다 — 아직 `queued`/`running` 인 잡은 건드리지 않으므로 오탐이 없다.
    타임아웃으로 판정하면 느린 워크플로(최대 3600초)를 죽이게 된다.

    `grace_seconds` 는 잡 행이 아직 안 보이는 짧은 창(삽입 직후)에서 오판하지 않기 위한
    것이지 판정 기준이 아니다.
    """
    from app.jobs.models import STATUS_QUEUED as JOB_QUEUED
    from app.jobs.models import STATUS_RUNNING as JOB_RUNNING
    from app.jobs.models import Job

    cutoff = now - timedelta(seconds=max(0.0, grace_seconds))
    candidates = db.execute(
        select(ScheduleRun).where(
            ScheduleRun.status.in_([RUN_QUEUED, RUN_RUNNING]),
            ScheduleRun.created_at < cutoff,
        )
    ).scalars().all()
    if not candidates:
        return 0

    keys = {f"schedrun:{r.idempotency_key}": r for r in candidates}
    live = set(
        db.execute(
            select(Job.idempotency_key).where(
                Job.idempotency_key.in_(list(keys)),
                Job.status.in_([JOB_QUEUED, JOB_RUNNING]),
            )
        ).scalars().all()
    )

    swept = 0
    for key, run in keys.items():
        if key in live:
            continue   # 잡이 아직 살아 있다 — 정상이다
        run.status = RUN_FAILED
        run.finished_at = run.finished_at or now
        # 왜 실패로 남았는지 화면에 적는다. "그냥 실패" 로 두면 운영자가 워크플로를 판다.
        run.error_message = (
            "실행을 처리하던 작업이 끝났는데 결과가 기록되지 않아 정리했습니다"
            "(같은 실행 일정의 다음 실행이 막혀 있었습니다)."
        )
        swept += 1
    if swept:
        db.flush()
        logger.warning("좀비 실행 %d건을 정리했다", swept)
    return swept


def _max_attempts(schedule: Schedule) -> int:
    """이 스케줄의 잡에 실을 최대 시도 횟수.

    **정수가 아닌 값은 기본값으로 눙치지 않는다.** 예전에는 `int(...)` 가 그 자리에서
    ValueError 로 터졌고, 그 예외가 수동 실행에서는 500 으로, 자동 실행에서는 로그 한
    줄로 끝났다 — 어느 쪽도 관리자가 "이 일정은 못 돈다" 를 알 수 있는 신호가 아니다.
    기본값 3 으로 조용히 떨어뜨리는 것도 답이 아니다: 관리자가 적어 넣은 값과 다른
    횟수로 도는 것이라 화면이 말하는 정책과 실제 동작이 갈린다.

    범위를 벗어난 **정수**는 예전처럼 자른다(1~10). 그 값들은 이미 저장돼 돌고 있고,
    자르기는 예전부터 정의돼 있던 동작이라 지금 실패로 바꾸면 멀쩡히 돌던 일정이 멈춘다.
    새로 들어오는 값은 스키마가 이미 범위 안으로 막는다.
    """
    try:
        policy = json.loads(schedule.retry_policy_json or "{}")
    except json.JSONDecodeError as exc:
        raise InvalidRetryPolicy("retry_policy가 JSON이 아닙니다.") from exc
    if not isinstance(policy, dict):
        raise InvalidRetryPolicy("retry_policy는 객체여야 합니다.")
    raw = policy.get("max_attempts", MAX_ATTEMPTS_DEFAULT)
    # bool 은 int 의 하위형이다 — True 를 1 로 읽으면 잘못 저장된 값을 삼키게 된다.
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise InvalidRetryPolicy("max_attempts는 정수여야 합니다.")
    return max(MAX_ATTEMPTS_FLOOR, min(raw, MAX_ATTEMPTS_CEILING))


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

        # 유효 기간의 끝은 **실행 직전에도** 본다. 지금까지 `end_at` 은 다음 실행 시각을
        # 계산한 **뒤**에만 읽혔다(advance_next_run) — 그래서 기간이 이미 끝난 일정을
        # 활성화하면 그 일정은 창 밖에서 한 번은 실제로 돌고 그 다음에야 내려갔다.
        # 관리자가 목록의 '종료' 열을 읽는 뜻은 "그 시각 뒤에는 안 돈다"이다.
        if schedule.end_at is not None and scheduled_at > schedule.end_at:
            schedule.enabled = False
            schedule.next_run_at = None
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
        # tick 의 반환값은 "몇 건을 큐에 넣었나"다. 시작도 못 하고 실패로 남은 실행을
        # 여기서 세면 그 수가 거짓말이 된다(실행 이력에는 그 실패가 남아 있다).
        return run is not None and run.status == RUN_QUEUED

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
                title=f"실행 일정 '{schedule.name}' 실행 누락",
                body=(
                    f"1회 실행 일정이 예정 시각({_kst_minute(scheduled_at)})에 실행되지 못했고 "
                    f"따라잡기 허용 시간을 넘겨 취소되었습니다. 필요하면 다시 예약하세요."
                ),
                related=("schedule", schedule.id),
                now=now,
            )
        except Exception:
            logger.exception(
                "failed to notify owner of dropped once-schedule %s", schedule.id
            )

def _kst_minute(value) -> str:
    """알림 문장에 넣는 시각 — 저장값(Z 없는 UTC)을 한국 시간 분 단위로 쓴다. ISO 원문(2026-10-16T05:00:00)이 본문에 섰다."""
    from datetime import timezone as _tz
    from zoneinfo import ZoneInfo
    aware = value if value.tzinfo else value.replace(tzinfo=_tz.utc)
    return aware.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M") + " 한국 시간"
