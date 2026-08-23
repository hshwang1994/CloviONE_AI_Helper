"""schedule_run job handler — executes a schedule occurrence (spec §18).

Supported target: **`system` 하나뿐이다.**

예전에는 `workflow` 도 있었고 그것이 등록된 n8n 워크플로를 불렀다. S11 이 n8n 을
걷어내면서 그 갈래를 지웠다 — 부를 곳이 없는 갈래를 남겨 두면, 스케줄 화면은 고를 수
있는 대상으로 계속 보여 주고 실행은 매번 실패한다. 모르는 `target_type` 은 아래에서
확정 실패로 끝난다(fail-closed).
"""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.jobs.exceptions import PermanentJobError
from app.jobs.models import Job
from app.jobs.worker import WorkerContext, parse_payload
from app.schedules.models import (
    RUN_FAILED,
    RUN_RUNNING,
    RUN_SUCCEEDED,
    TARGET_SYSTEM,
    Schedule,
    ScheduleRun,
)

logger = logging.getLogger("app.handlers.schedule")

MAX_SUMMARY_LENGTH = 2000


def handle_schedule_run(db: Session, job: Job, ctx: WorkerContext) -> None:
    payload = parse_payload(job)
    run = db.get(ScheduleRun, payload.get("schedule_run_id", ""))
    if run is None:
        raise PermanentJobError("schedule_run 레코드가 존재하지 않습니다.")
    schedule = db.get(Schedule, run.schedule_id)
    if schedule is None:
        raise PermanentJobError("schedule 레코드가 존재하지 않습니다.")

    now = ctx.clock.now()
    run.status = RUN_RUNNING
    run.started_at = run.started_at or now
    run.retry_count = max(0, job.attempt_count - 1)
    db.flush()
    db.commit()

    if schedule.target_type == TARGET_SYSTEM:
        result: dict = {"target": schedule.target_ref, "ok": True}
    else:
        raise PermanentJobError(f"지원하지 않는 target_type: {schedule.target_type}")

    finish = ctx.clock.now()
    run.status = RUN_SUCCEEDED
    run.finished_at = finish
    run.error_message = None
    run.response_summary = json.dumps(result, ensure_ascii=False)[:MAX_SUMMARY_LENGTH]
    db.flush()


def on_failure(db: Session, job: Job, ctx: WorkerContext, error: str) -> None:
    try:
        payload = parse_payload(job)
    except PermanentJobError:
        return
    run = db.get(ScheduleRun, payload.get("schedule_run_id", ""))
    if run is None:
        return
    run.status = RUN_FAILED
    run.finished_at = ctx.clock.now()
    run.error_message = (error or "")[:2000]

    # 소유자에게 Schedule 실패 알림 (spec §13.5).
    schedule = db.get(Schedule, run.schedule_id)
    if schedule is not None and schedule.owner_user_id:
        from app.notifications.service import notify_user

        notify_user(
            db,
            schedule.owner_user_id,
            type_="schedule_failed",
            title=f"스케줄 실행 실패: {schedule.name}",
            body=run.error_message,
            # 알림의 '관련 항목 보기'가 해당 스케줄로 바로 이동하도록 schedule을
            # 가리킨다(OBJ_ID_PARAM.schedule로 딥링크가 만들어진다). 예전엔
            # ("schedule_run", run.id)라 프런트가 딥링크를 못 만들어 이 알림만
            # 클릭 동작이 전혀 없었다. app/schedules/scheduler.py의 1회성 스케줄
            # 취소 알림과 같은 패턴이다.
            related=("schedule", schedule.id),
            now=ctx.clock.now(),
        )
    db.flush()
    logger.warning("schedule run %s failed: %s", run.id, error)


handle_schedule_run.on_failure = on_failure
