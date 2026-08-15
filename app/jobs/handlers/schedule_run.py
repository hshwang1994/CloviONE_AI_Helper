"""schedule_run job handler — executes a schedule occurrence (spec §18).

Supported targets:
- workflow: invoke the registered n8n workflow (enabled, allowlisted).
  Write workflows with approval_required are NOT auto-executed (spec §19.3);
  the run fails with approval_required until the approval flow (M9/M10)
  creates pre-approved runs.
- system:noop — used by dry-run tests and health verification.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.core.http_client import is_timeout_error, is_transport_error
from app.jobs.exceptions import PermanentJobError
from app.jobs.models import Job
from app.jobs.worker import WorkerContext, parse_payload
from app.schedules.models import (
    RUN_FAILED,
    RUN_RUNNING,
    RUN_SUCCEEDED,
    TARGET_SYSTEM,
    TARGET_WORKFLOW,
    Schedule,
    ScheduleRun,
)
from app.workflows.models import Workflow
from app.workflows.provider_n8n import N8nWorkflowProvider

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

    request_payload = json.loads(run.request_payload_json or "{}")

    if schedule.target_type == TARGET_SYSTEM:
        result: dict = {"target": schedule.target_ref, "ok": True}
    elif schedule.target_type == TARGET_WORKFLOW:
        workflow = db.get(Workflow, schedule.target_ref)
        if workflow is None:
            raise PermanentJobError("대상 Workflow가 존재하지 않습니다.")
        if workflow.operation_mode == "write" and workflow.approval_required:
            if not payload.get("approved", False):
                raise PermanentJobError(
                    "승인이 필요한 write workflow는 자동 실행되지 않습니다 (approval_required)."
                )
        provider = N8nWorkflowProvider(ctx.outbound_client)
        # §32.8 스타일 멱등성: n8n이 쓰기를 이미 처리했는데 HTTP 응답만 유실되면(타임아웃/
        # 5xx) `repository.fail`이 이 job을 백오프 후 재큐잉하고 동일한 request_payload가
        # 다시 POST된다. `chat_message`/`document_generate` 핸들러는 각각 이 위험을 문서화
        # 하고 안정적인 idempotency_key를 실어 n8n이 중복 쓰기를 걸러낼 수 있게 하는데, 이
        # 핸들러만 빠져 있었다. `Job.idempotency_key`(스케줄 occurrence 중복 방지)와 달리
        # `run.idempotency_key`는 이 run의 재시도 전체에서 안정적이므로 그대로 쓴다.
        invoke_payload = (
            {**request_payload, "idempotency_key": run.idempotency_key}
            if isinstance(request_payload, dict)
            else request_payload
        )
        # DBTX: 아웃바운드 호출 직전 커밋 — 위 db.get(Workflow, ...) 읽기가 연 스냅샷을
        # 쥔 채로 호출을 통과하면, 응답을 받은 뒤의 쓰기가 "database is locked"로
        # 거부될 수 있다(app/core/db.py의 "begin" 이벤트 주석, app/jobs/handlers/
        # chat_message.py의 실측 사고와 같은 근거).
        db.commit()
        try:
            result = provider.invoke(
                workflow, invoke_payload, timeout=float(schedule.timeout_seconds)
            )
        except Exception as exc:
            # 타임아웃·연결 실패는 일시적일 수 있으니 큐가 재시도한다(그대로 올린다). 그 외
            # (잘못된 webhook_url, 허용 목록 불일치, n8n의 비-JSON 응답 등)는 재시도해도
            # 똑같이 실패하는 확정적 오류다 — notion_mapping_sync.py의 분류와 맞춘다.
            # 그렇지 않으면 worker.py의 기본 재시도 경로가 이런 결정적 오류를 백오프하며
            # 반복해서 재시도만 하다가 워커 용량을 낭비한다.
            if is_timeout_error(exc) or is_transport_error(exc):
                raise
            raise PermanentJobError(f"Workflow 호출 실패: {type(exc).__name__}") from exc
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
