"""Job queue admin API (spec §14.1 queue status, §10.2 operator retry, §23.7)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.deps import get_db, require_csrf, require_roles
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.core.pagination import PageParams
from app.jobs.models import ALL_STATUSES, STATUS_FAILED, STATUS_QUEUED, Job
from app.jobs.repository import cancel_queued, queue_stats, retry_failed

router = APIRouter(
    prefix="/api/admin/jobs",
    tags=["admin-jobs"],
    dependencies=[
        Depends(require_roles("operator", "admin", "system_admin")),
        Depends(require_csrf),
    ],
)


def _duration_ms(job: Job) -> int | None:
    if job.started_at is None or job.finished_at is None:
        return None
    return int((job.finished_at - job.started_at).total_seconds() * 1000)


# payload_json에서 '연결 식별자'만 골라 노출한다 — 내용(채팅 원문·이메일·설정 본문)은
# 절대 포함하지 않는다. conversation_id/message_id가 이미 참조값으로 노출되는 것과 같은
# 성격의 링크 ID다. 이게 없으면 schedule_run/document_generate job이 자신이 구동하는
# 스케줄/문서로 갈 길이 idempotency_key 문자열 파싱뿐이었다(round30 감사 E).
_LINK_ID_KEYS = ("schedule_id", "schedule_run_id", "generation_id")


def _link_ids(job: Job) -> dict:
    import json as _json

    try:
        payload = _json.loads(job.payload_json or "{}")
    except ValueError:
        return {}
    if not isinstance(payload, dict):
        return {}
    result = {}
    for key in _LINK_ID_KEYS:
        value = payload.get(key)
        # 문자열 참조 ID만 싣는다(dict/list 같은 내용 구조는 배제).
        if isinstance(value, str) and value:
            result[key] = value
    return result


def _job_view(job: Job) -> dict:
    """운영이 필요로 하는 것은 '작업의 상태'이지 '사람이 쓴 말'이 아니다.

    payload 본문(채팅 원문·첨부 이미지 바이트·요청자 이메일/이름)은 여기서 노출하지
    않는다. 같은 내용을 대화 API로 읽으면 소유자가 아닌 이상 403인데, 큐 화면이
    우회로가 되면 최소 권한 원칙이 무너진다. 원문 열람이 필요하면 상위 권한 +
    감사 기록이 남는 별도 경로로 다뤄야 한다. 단, 연결 식별자(schedule_id 등)는
    내용이 아니라 참조값이라 별도로 노출한다(_link_ids).
    """
    return {
        "id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        # 소유자 상관관계 추적용 식별자 — 내용이 아니라 참조값이다.
        "user_id": job.user_id,
        "conversation_id": job.conversation_id,
        "message_id": job.message_id,
        "attempt_count": job.attempt_count,
        "max_attempts": job.max_attempts,
        "idempotency_key": job.idempotency_key,
        "available_at": job.available_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "duration_ms": _duration_ms(job),
        "last_error": job.last_error,
        "created_at": job.created_at.isoformat(),
        # schedule_run → schedule_id/schedule_run_id, document_generate → generation_id.
        **_link_ids(job),
    }


@router.get("")
def list_jobs(
    db: Session = Depends(get_db),
    page: PageParams = Depends(),
    status: str | None = Query(default=None),
    job_type: str | None = Query(default=None, max_length=64),
):
    stmt = select(Job)
    if status is not None:
        if status not in ALL_STATUSES:
            raise ValidationAppError(f"알 수 없는 상태입니다: {status}")
        stmt = stmt.where(Job.status == status)
    if job_type:
        stmt = stmt.where(Job.job_type == job_type)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(Job.created_at.desc()).offset(page.offset).limit(page.page_size)
        )
        .scalars()
        .all()
    )
    return {
        "items": [_job_view(j) for j in rows],
        "total": total,
        "page": page.page,
        "page_size": page.page_size,
    }


@router.get("/stats")
def stats(request: Request, db: Session = Depends(get_db)):
    return queue_stats(db, now=request.app.state.clock.now())


@router.get("/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise NotFoundError("Job을 찾을 수 없습니다.")
    return {"job": _job_view(job)}


@router.post("/{job_id}/retry")
def retry(request: Request, job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise NotFoundError("Job을 찾을 수 없습니다.")
    if job.status != STATUS_FAILED:
        raise ConflictError("실패 상태의 Job만 재시도할 수 있습니다.")
    retry_failed(db, job, now=request.app.state.clock.now())
    record_audit_from_request(
        request, db, action="job.retry", object_type="job", object_id=job.id,
    )
    return {"ok": True, "job": _job_view(job)}


@router.post("/{job_id}/cancel")
def cancel(request: Request, job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise NotFoundError("Job을 찾을 수 없습니다.")
    if job.status != STATUS_QUEUED:
        raise ConflictError("대기 상태의 Job만 취소할 수 있습니다.")
    now = request.app.state.clock.now()
    cancel_queued(db, job, now=now)
    # If this job drives a schedule_run/document, terminalize that record so the
    # schedule is not wedged (CONCURRENCY_SKIP would otherwise block forever).
    _terminalize_linked_record(db, job, now)
    record_audit_from_request(
        request, db, action="job.cancel", object_type="job", object_id=job.id,
    )
    return {"ok": True, "job": _job_view(job)}


def _terminalize_linked_record(db: Session, job: Job, now) -> None:
    import json as _json

    payload = _json.loads(job.payload_json or "{}")
    if job.job_type == "schedule_run":
        from app.schedules.models import RUN_SKIPPED, ScheduleRun

        run = db.get(ScheduleRun, payload.get("schedule_run_id", ""))
        if run is not None and run.status in ("queued", "running"):
            run.status = RUN_SKIPPED
            run.finished_at = now
            run.error_message = "job cancelled by operator"
            db.flush()
    elif job.job_type == "document_generate":
        from app.documents.models import (
            STATUS_AWAITING_APPROVAL,
            STATUS_FAILED,
            STATUS_PENDING,
            DocumentGeneration,
        )

        gen = db.get(DocumentGeneration, payload.get("generation_id", ""))
        # 이 문서를 다음 상태로 옮기는 것은 취소된 job뿐이다. 승인 후 발행 job을
        # 취소한 경우(status=awaiting_approval)까지 종결하지 않으면 문서가
        # awaiting_approval에 영구히 남아 어느 화면에서도 되살릴 수 없다.
        if gen is not None and gen.status in (STATUS_PENDING, STATUS_AWAITING_APPROVAL):
            gen.status = STATUS_FAILED
            gen.error_message = "job cancelled by operator"
            db.flush()
    elif job.job_type == "chat_message":
        from app.conversations.models import PROC_FAILED, Message
        from sqlalchemy import select as _select

        msg = db.execute(
            _select(Message).where(Message.message_id == payload.get("message_id", ""))
        ).scalar_one_or_none()
        if msg is not None and msg.processing_status in ("pending", "processing"):
            msg.processing_status = PROC_FAILED
            msg.error_code = "cancelled"
            db.flush()
