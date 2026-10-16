"""AI 연결 API — `/api/admin/ai` (계획 A3, D-515 · D-539 · D-540). 화면은 `/ai-connection` 이다.

시스템 관리자만 쓴다(`AI_CONFIGURE`). 연결 확인은 기다리지 않는다 - 잡을 넣고 곧바로 잡 id 를 돌려주며, 화면이 결과를
이어서 묻는다. 제공자 호출은 수십 초가 걸릴 수 있고, 웹에서 기다리면 그 처리 칸이 잠겨 다른 사람의 화면이 함께 느려진다.

인증 방식 · 모델을 바꾸거나 AI 사용을 켜면 저장 응답이 연결 확인 잡 id(`verify_job_id`)를 함께 준다 - 사람이 확인 단추를
따로 누르지 않는다(D-539). 모델 목록은 웹에서 제공자에 묻는다(10초 제한, 10분 기억) - 인증이 끝나면 화면이 저절로 부르고,
모델이 비어 있을 때만 추천 모델을 명시적으로 저장한다(`auto_model`, 감사에 `auto: true`).

ChatGPT 계정 연결은 붙여 넣기 로그인 하나다(`app/ai/credentials/login_flow.py`). 예전의 연결 도우미와 그 문은 없다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.ai.console import service
from app.ai.credentials import login_flow, oauth
from app.ai.providers import base
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
    default_message = "AI 제공자에게서 모델 목록을 받지 못했습니다. 잠시 후 다시 시도해 주세요."


class AiConfigChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generation_enabled: bool | None = None
    provider: str | None = Field(default=None, max_length=32)
    auth_method: str | None = Field(default=None, max_length=32)
    model: str | None = Field(default=None, max_length=service.MODEL_MAX_CHARS)
    timeout_seconds: int | None = None
    max_concurrency: int | None = None
    #: 모델을 사람이 아니라 추천 표가 골랐다(처음 설정에서 모델이 비었을 때). 감사에 남기는 표지일 뿐 값을 바꾸지 않는다.
    auto_model: bool = False


def _runtime(request: Request):
    from app.ai.runtime import runtime_for_app

    return runtime_for_app(request.app)


def _secrets(request: Request):
    return getattr(request.app.state, "secret_provider", None)


def _gateway(request: Request):
    return getattr(request.app.state, "ai_gateway", None)


def _overview(request: Request, db: Session) -> dict:
    user = getattr(request.state, "user", None)
    return service.overview(db, _runtime(request), _secrets(request), request.app.state.settings_cache,
                            gateway=_gateway(request), admin_user_id=getattr(user, "id", None),
                            now=request.app.state.clock.now(), settings=request.app.state.settings)


def _session_secret(request: Request) -> str:
    return str(getattr(request.app.state.settings, "session_secret", "") or "")


def _actor_and_session(request: Request) -> tuple[str, str | None]:
    actor = getattr(request.state, "actor", None) or request.state.user
    session = getattr(request.state, "session", None)
    return actor.id, getattr(session, "id", None)


def _fresh_settings(request: Request, db: Session) -> None:
    """설정 캐시를 DB 에서 다시 읽는다. 이 화면의 조회는 드물고, 방금 저장한 값을 봐야 하는 자리다.

    웹은 프로세스가 여럿이다. 예전에는 설정 캐시가 프로세스마다 30초(TTL)마다 새로 읽어서, 저장하고 연결 확인을 누르면 확인
    결과는 맞는데(「API 키가 거부되었습니다」) 같은 응답의 연결 상태 칸은 「미설정」이었다(Release 리허설 실측). 이제 캐시가 판
    번호로 다른 프로세스의 저장을 다음 요청에서 따라잡는다(D-532). 이 자리의 직접 읽기는 남겨도 무해한 보험이다.
    """
    cache = request.app.state.settings_cache
    if cache is not None:
        cache.load(db)


@router.get("")
def ai_overview(request: Request, db: Session = Depends(get_db)) -> dict:
    _fresh_settings(request, db)
    return _overview(request, db)


def _start_verify(request: Request, db: Session, *, reason: str):
    """연결 확인 잡을 넣고 감사에 남긴다. 이미 큐에 있으면 그것을 쓴다."""
    job = service.enqueue_verify(db, user_id=request.state.user.id, now=request.app.state.clock.now())
    record_audit_from_request(
        request, db, action="ai.connection.test", object_type=service.OBJECT_TYPE, object_id=job.id,
        after={"queued": True, "reason": reason},
    )
    return job


@router.put("/config")
def update_config(payload: AiConfigChange, request: Request, db: Session = Depends(get_db)) -> dict:
    runtime = _runtime(request)
    changes = payload.model_dump(exclude_unset=True)
    auto_model = bool(changes.pop("auto_model", False))
    changed = service.apply_config(
        db, request.app.state.settings_cache, current=runtime.config(db),
        changes=changes, user_id=request.state.user.id, now=request.app.state.clock.now(),
    )
    if changed:
        after = dict(changed)
        if auto_model and "ai_model" in changed:
            after["auto"] = True
        record_audit_from_request(
            request, db, action="ai.config.update", object_type=service.OBJECT_TYPE, object_id="generation",
            after=after,
        )
    job = None
    if changed and service.verify_needed(changed, runtime.config(db), _secrets(request)):
        job = _start_verify(request, db, reason="config")
    db.commit()
    return {**_overview(request, db), "verify_job_id": job.id if job is not None else None}


@router.get("/models")
def list_models(
    request: Request,
    provider: str = Query(..., max_length=32),
    auth_method: str = Query(..., max_length=32),
    db: Session = Depends(get_db),
) -> dict:
    """제공자의 모델 목록과 추천 하나(D-539). 추천은 표대로 고른 것이고 저장하지 않는다 - 저장은 화면이 `PUT /config` 로 한다."""
    from app.ai.credentials.state import reason_text

    listing = _runtime(request).list_models(db, provider=provider, auth_method=auth_method)
    if not listing.ok:
        raise ProviderUnavailableError(
            " ".join(filter(None, ["모델 목록을 가져오지 못했습니다.", reason_text(listing.error_code)]))
        )
    recommended = base.recommend(provider, auth_method, listing.models)
    return {
        "models": [{**m, "recommended": m.get("id") == recommended} for m in listing.models],
        "recommended_id": recommended,
    }


@router.post("/verify")
def start_verify(request: Request, db: Session = Depends(get_db)) -> dict:
    """연결 확인을 큐에 넣고 **곧바로** 잡 id 를 돌려준다(「지금 확인」 · 키를 넣은 뒤)."""
    job = _start_verify(request, db, reason="manual")
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
        result = {"ok": False, "message": (job.last_error or "").strip() or "AI 연결을 확인하지 못했습니다. 잠시 후 다시 시도해 주세요."}
    elif job.status == STATUS_CANCELLED:
        result = {"ok": False, "message": "연결 확인이 취소됐습니다."}
    if result is not None:
        # 끝난 확인의 상태 칸은 워커가 방금 적은 결과와 맞아야 한다 - 이 프로세스의 캐시가 저장 전 값이면 어긋난다.
        _fresh_settings(request, db)
    return {
        "job_id": job.id,
        "status": job.status,
        "pending": job.status in (STATUS_QUEUED, STATUS_RUNNING),
        "result": result,
        "state": _runtime(request).status(db),
    }


# ── ChatGPT 계정 연결 (계획 A3, D-516 · D-540) ────────────────────────────────


class PastedCallback(BaseModel):
    model_config = ConfigDict(extra="forbid")

    callback_url: str = Field(max_length=8192)


@router.post("/oauth/openai/start")
def oauth_start(request: Request, db: Session = Depends(get_db)) -> dict:
    """연결 시도를 시작한다. 응답의 `flow` 가 화면의 모양을 정한다(지금은 `paste`). 감사에는 시도 id 만 적는다."""
    admin_id, session_id = _actor_and_session(request)
    flow = login_flow.chatgpt_flow()
    started = flow.start(db, admin_user_id=admin_id, session_id=session_id,
                         session_secret=_session_secret(request), now=request.app.state.clock.now())
    record_audit_from_request(
        request, db, action="ai.oauth.start", object_type=service.OBJECT_TYPE, object_id=started["transaction_id"],
        after={"provider": "openai", "auth_method": "chatgpt", "flow": started["flow"]},
    )
    return started


@router.get("/oauth/openai/transactions/{transaction_id}")
def oauth_transaction(transaction_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    admin_id, session_id = _actor_and_session(request)
    return oauth.poll(db, transaction_id=transaction_id, admin_user_id=admin_id, session_id=session_id,
                      now=request.app.state.clock.now())


@router.post("/oauth/openai/transactions/{transaction_id}/complete")
def oauth_complete(transaction_id: str, payload: PastedCallback, request: Request,
                   db: Session = Depends(get_db)) -> dict:
    """붙여 넣은 주소로 연결을 끝낸다. 지금 설정이 ChatGPT 계정이면 연결 확인을 저절로 시작한다(D-539)."""
    admin_id, session_id = _actor_and_session(request)
    now = request.app.state.clock.now()
    done = login_flow.chatgpt_flow().complete(
        db, transaction_id=transaction_id, admin_user_id=admin_id, session_id=session_id,
        callback_url=payload.callback_url, context=login_flow.complete_context(request, now),
    )
    record_audit_from_request(
        request, db, action="ai.oauth.connect", object_type=service.OBJECT_TYPE, object_id=transaction_id,
        after={"account": done["account_label"], "via": "paste"},
    )
    runtime = _runtime(request)
    config = runtime.config(db)
    job = None
    chatgpt_now = (config.provider, config.auth_method) == (base.PROVIDER_OPENAI, base.AUTH_CHATGPT)
    if chatgpt_now and service.config_complete(config, _secrets(request)):
        job = _start_verify(request, db, reason="login")
    db.commit()
    return {"ok": True, "account_label": done["account_label"], "verify_job_id": job.id if job else None}


@router.post("/oauth/openai/logout")
def oauth_logout(request: Request, db: Session = Depends(get_db)) -> dict:
    runtime = _runtime(request)
    now = request.app.state.clock.now()
    result = oauth.logout(db, tokens=runtime.chatgpt_tokens(), outbound=request.app.state.outbound_client, now=now)
    record_audit_from_request(
        request, db, action="ai.oauth.logout", object_type=service.OBJECT_TYPE, object_id="openai.chatgpt",
        after={"revoked": result["revoked"], "removed": result["removed"]},
    )
    return {**result, "overview": _overview(request, db)}
