"""Job queue admin API (spec §14.1 queue status, §10.2 operator retry, §23.7)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.authz import CONSOLE_OPS_ROLES
from app.core.scope import Principal, visible_user_ids
from app.core.deps import get_db, get_principal, require_csrf, require_roles
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.core.pagination import PageParams
from app.jobs.models import ALL_STATUSES, STATUS_FAILED, STATUS_QUEUED, Job
from app.jobs.repository import (
    apply_scope,
    cancel_queued,
    get_in_scope,
    queue_stats,
    retry_failed,
)

router = APIRouter(
    prefix="/api/admin/jobs",
    tags=["admin-jobs"],
    dependencies=[
        Depends(require_roles(*CONSOLE_OPS_ROLES)),
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


def _scoped_job_or_404(db: Session, job_id: str, principal: Principal) -> Job:
    """단건·재시도·취소가 **전부 여기를 지난다** (§0-A 2순위).

    목록만 가려서는 아무 의미가 없다 — 세 경로 모두 `id` 를 직접 받는다. 그리고 새는 것이
    조회로 끝나지 않는다: **재시도는 남의 범위에서 n8n·Notion 쓰기를 다시 실행한다.**

    판정은 목록과 같은 `repository.scope_clause` 하나다. 범위 밖은 **404** — 403 은
    "그 id 는 존재한다" 를 알려 주고, 상태 충돌(409)도 마찬가지로 존재와 상태를 알려 준다.
    그래서 상태 검사보다 **먼저** 이 문을 지난다.
    """
    job = get_in_scope(db, job_id, visible_user_ids(db, principal.scope))
    if job is None:
        raise NotFoundError("Job을 찾을 수 없습니다.")
    return job


@router.get("")
def list_jobs(
    db: Session = Depends(get_db),
    page: PageParams = Depends(),
    status: str | None = Query(default=None),
    job_type: str | None = Query(default=None, max_length=64),
    schedule_id: str | None = Query(default=None, max_length=64),
    schedule_run_id: str | None = Query(default=None, max_length=64),
    generation_id: str | None = Query(default=None, max_length=64),
    principal: Principal = Depends(get_principal),
):
    stmt = select(Job)
    # 범위 밖 사람의 작업은 안 보인다 (2순위 #6). 잡에는 **요청자의 입력이 payload 로 들어
    # 있다**(문서 생성 요청의 제목·기간, 채팅 메시지 등) — 큐를 훑는 것은 그 사람이 무엇을
    # 요청했는지 읽는 것과 같다.
    #
    # 조건은 단건·재시도·취소와 **같은 것 하나**다(`repository.scope_clause` — 시스템 잡을
    # 남기는 이유도 거기 적혀 있다). 여기 손으로 다시 적으면 두 벌이 되고, 한쪽만 고쳐진
    # 상태의 증상은 "어떤 사람만 안 된다" 라서 찾기가 어렵다.
    stmt = apply_scope(stmt, visible_user_ids(db, principal.scope))
    if status is not None:
        if status not in ALL_STATUSES:
            raise ValidationAppError(f"알 수 없는 상태입니다: {status}")
        stmt = stmt.where(Job.status == status)
    if job_type:
        stmt = stmt.where(Job.job_type == job_type)
    # 스케줄/문서 생성이 자신을 실행한 작업으로 역추적하는 경로(FN-13, IA-02의 반대 방향) —
    # _link_ids(아래)가 응답에 싣는 것과 같은 세 키를 payload_json 안에서 찾는다. 인덱스가
    # 없는 컬럼 스캔이지만 크로스링크를 눌렀을 때 1회만 도는 조회라(목록 전체를 매번 훑는
    # 경로가 아니다) 감내할 수 있는 비용이다.
    for key, value in (
        ("schedule_id", schedule_id),
        ("schedule_run_id", schedule_run_id),
        ("generation_id", generation_id),
    ):
        if value:
            stmt = stmt.where(func.json_extract(Job.payload_json, "$." + key) == value)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(Job.created_at.desc(), Job.id.desc()).offset(page.offset).limit(page.page_size)
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
def stats(
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    return queue_stats(db, now=request.app.state.clock.now(), visible=visible_user_ids(db, principal.scope))


@router.get("/{job_id}")
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    job = _scoped_job_or_404(db, job_id, principal)
    return {"job": _job_view(job)}


@router.post("/{job_id}/retry")
def retry(
    request: Request,
    job_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    job = _scoped_job_or_404(db, job_id, principal)
    if job.status != STATUS_FAILED:
        raise ConflictError("실패 상태의 Job만 재시도할 수 있습니다.")
    retry_failed(db, job, now=request.app.state.clock.now())
    record_audit_from_request(
        request, db, action="job.retry", object_type="job", object_id=job.id,
    )
    return {"ok": True, "job": _job_view(job)}


@router.post("/{job_id}/cancel")
def cancel(
    request: Request,
    job_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    job = _scoped_job_or_404(db, job_id, principal)
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
        from sqlalchemy import or_ as sa_or, select as _select

        # UB-23: message_id는 대화 단위로만 유일하다(migration 0054) — conversation_id로 좁힌다.
        msg = db.execute(
            _select(Message).where(
                Message.conversation_id == job.conversation_id,
                Message.message_id == payload.get("message_id", ""),
            )
        ).scalar_one_or_none()
        if msg is not None and msg.processing_status in ("pending", "processing"):
            msg.processing_status = PROC_FAILED
            msg.error_code = "cancelled"
            db.flush()
