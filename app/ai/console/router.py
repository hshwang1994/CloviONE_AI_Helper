"""AI 설정 API — `/api/admin/ai` (계획 3.13 · 3.14, D-515).

옛 `/api/admin/llm` 을 대신한다. 시스템 관리자만 쓴다(`AI_CONFIGURE`). 연결 확인은 기다리지 않는다 - 잡을 넣고 곧바로
잡 id 를 돌려주며, 화면이 결과를 이어서 묻는다. 제공자 호출은 수십 초가 걸릴 수 있고, 웹에서 기다리면 그 처리 칸이
잠겨 다른 사람의 화면이 함께 느려진다.

모델 목록만은 웹에서 제공자에 묻는다. 관리자가 모델을 고를 때 한 번이고, 10초 제한에 10분 동안 기억한다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.ai.console import service
from app.authz.permissions import AI_CONFIGURE
from app.core.audit import record_audit_from_request
from app.core.deps import get_db, require_csrf, require_permission
from app.core.errors import AppError, NotFoundError

router = APIRouter(
    prefix="/api/admin/ai",
    tags=["admin-ai"],
    dependencies=[Depends(require_csrf), Depends(require_permission(AI_CONFIGURE))],
)


class ProviderUnavailableError(AppError):
    status_code = 502
    code = "ai_provider_unavailable"
    default_message = "AI 제공자에게서 모델 목록을 받지 못했습니다."


class AiConfigChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generation_enabled: bool | None = None
    provider: str | None = Field(default=None, max_length=32)
    auth_method: str | None = Field(default=None, max_length=32)
    model: str | None = Field(default=None, max_length=service.MODEL_MAX_CHARS)
    timeout_seconds: int | None = None
    max_concurrency: int | None = None


def _runtime(request: Request):
    from app.ai.runtime import runtime_for_app

    return runtime_for_app(request.app)


def _secrets(request: Request):
    return getattr(request.app.state, "secret_provider", None)


@router.get("")
def ai_overview(request: Request, db: Session = Depends(get_db)) -> dict:
    return service.overview(db, _runtime(request), _secrets(request), request.app.state.settings_cache)


@router.put("/config")
def update_config(payload: AiConfigChange, request: Request, db: Session = Depends(get_db)) -> dict:
    runtime = _runtime(request)
    changed = service.apply_config(
        db, request.app.state.settings_cache, current=runtime.config(db),
        changes=payload.model_dump(exclude_unset=True), user_id=request.state.user.id,
        now=request.app.state.clock.now(),
    )
    if changed:
        record_audit_from_request(
            request, db, action="ai.config.update", object_type=service.OBJECT_TYPE, object_id="generation",
            after=changed,
        )
    db.commit()
    return service.overview(db, runtime, _secrets(request), request.app.state.settings_cache)


@router.get("/models")
def list_models(
    request: Request,
    provider: str = Query(..., max_length=32),
    auth_method: str = Query(..., max_length=32),
    db: Session = Depends(get_db),
) -> dict:
    from app.ai.credentials.state import reason_text

    listing = _runtime(request).list_models(db, provider=provider, auth_method=auth_method)
    if not listing.ok:
        raise ProviderUnavailableError(
            " ".join(filter(None, ["AI 제공자에게서 모델 목록을 받지 못했습니다.", reason_text(listing.error_code)]))
        )
    return {"models": list(listing.models)}


@router.post("/verify")
def start_verify(request: Request, db: Session = Depends(get_db)) -> dict:
    """연결 확인을 큐에 넣고 **곧바로** 잡 id 를 돌려준다."""
    from app.jobs.repository import enqueue

    job = enqueue(
        db, job_type=service.JOB_TYPE_VERIFY, payload={}, now=request.app.state.clock.now(),
        user_id=request.state.user.id,
        # 다시 시도하지 않는다. 키가 틀렸으면 5초 뒤에도 같은 답이다.
        max_attempts=1,
    )
    record_audit_from_request(
        request, db, action="ai.connection.test", object_type=service.OBJECT_TYPE, object_id=job.id,
        after={"queued": True},
    )
    return {"job_id": job.id, "status": job.status}


@router.get("/verify/{job_id}")
def verify_result(job_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    """확인 하나의 결과. 아직 안 끝났으면 **끝난 척하지 않는다**(`result` 가 null 이다)."""
    from app.jobs.models import (
        STATUS_CANCELLED,
        STATUS_FAILED,
        STATUS_QUEUED,
        STATUS_RUNNING,
        STATUS_SUCCEEDED,
        Job,
    )

    job = db.get(Job, job_id)
    if job is None or job.job_type != service.JOB_TYPE_VERIFY:
        raise NotFoundError("연결 확인 기록을 찾을 수 없습니다.")
    result = None
    if job.status == STATUS_SUCCEEDED:
        result = {"ok": True, "message": "AI 제공자에 연결해 답을 받았습니다."}
    elif job.status == STATUS_FAILED:
        result = {"ok": False, "message": (job.last_error or "").strip() or "AI 연결을 확인하지 못했습니다."}
    elif job.status == STATUS_CANCELLED:
        result = {"ok": False, "message": "연결 확인이 취소됐습니다."}
    return {
        "job_id": job.id,
        "status": job.status,
        "pending": job.status in (STATUS_QUEUED, STATUS_RUNNING),
        "result": result,
        "state": _runtime(request).status(db),
    }
