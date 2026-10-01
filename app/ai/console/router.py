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
from app.ai.credentials import oauth
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


# ── ChatGPT 계정 연결 (계획 3.14, D-516) ─────────────────────────────────────


class ManualCallback(BaseModel):
    model_config = ConfigDict(extra="forbid")

    callback_url: str = Field(max_length=8192)


def _server_url(request: Request) -> str:
    """도우미가 부를 서버 주소 - 관리자 브라우저가 지금 쓰는 주소다. 같은 PC 에서 도는 도우미도 그 주소에 닿는다."""
    from urllib.parse import urlsplit

    origin = request.headers.get("origin") or ""
    parts = urlsplit(origin)
    if parts.scheme in ("http", "https") and parts.netloc and parts.netloc == request.headers.get("host", ""):
        return f"{parts.scheme}://{parts.netloc}"
    configured = str(getattr(request.app.state.settings, "app_base_url", "") or "").rstrip("/")
    return configured or str(request.base_url).rstrip("/")


def _cert_fingerprint(request: Request, server_url: str) -> str | None:
    """서버 인증서의 sha256. 도우미는 이 지문의 인증서만 믿는다 - 설치가 만든 자체 서명 인증서에서도 안전하게 붙는다."""
    import hashlib
    import ssl
    from pathlib import Path

    if not server_url.startswith("https://"):
        return None
    path = getattr(request.app.state.settings, "tls_cert_path", None)
    if not path:
        return None
    try:
        der = ssl.PEM_cert_to_DER_cert(Path(path).read_text(encoding="ascii"))
    except (OSError, ValueError):
        return None
    return "sha256:" + hashlib.sha256(der).hexdigest()


def _commands(server_url: str, token: str, fingerprint: str | None) -> dict:
    pin_ps = f' -Fingerprint "{fingerprint}"' if fingerprint else ""
    pin_py = f" --fingerprint {fingerprint}" if fingerprint else ""
    return {
        "windows": (
            'powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\\Downloads\\clovirassist-connect.ps1"'
            f' -Server "{server_url}" -Token "{token}"{pin_ps}'
        ),
        "unix": f"python3 ~/Downloads/clovirassist-connect.py --server {server_url} --token {token}{pin_py}",
    }


@router.post("/oauth/openai/start")
def oauth_start(request: Request, db: Session = Depends(get_db)) -> dict:
    """연결 시도를 시작한다. 짝짓기 토큰 원문은 이 응답의 명령 안에만 있다 - 감사에는 시도 id 만 적는다."""
    from app.ai.connect_router import HELPER_FILES, helper_sha256

    admin_id, session_id = _actor_and_session(request)
    now = request.app.state.clock.now()
    row, token = oauth.start(db, admin_user_id=admin_id, session_id=session_id,
                             session_secret=_session_secret(request), now=now)
    record_audit_from_request(
        request, db, action="ai.oauth.start", object_type=service.OBJECT_TYPE, object_id=row.id,
        after={"provider": "openai", "auth_method": "chatgpt"},
    )
    server_url = _server_url(request)
    fingerprint = _cert_fingerprint(request, server_url)
    return {
        **oauth.view(row),
        "server_url": server_url,
        "fingerprint": fingerprint,
        "commands": _commands(server_url, token, fingerprint),
        "downloads": [
            {"name": name, "href": f"/connect/{name}", "sha256": helper_sha256(name)} for name in HELPER_FILES
        ],
    }


@router.get("/oauth/openai/transactions/{transaction_id}")
def oauth_transaction(transaction_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    admin_id, session_id = _actor_and_session(request)
    return oauth.poll(db, transaction_id=transaction_id, admin_user_id=admin_id, session_id=session_id,
                      now=request.app.state.clock.now())


@router.post("/oauth/openai/transactions/{transaction_id}/manual")
def oauth_manual_authorize(transaction_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    admin_id, session_id = _actor_and_session(request)
    return oauth.manual_authorize(
        db, transaction_id=transaction_id, admin_user_id=admin_id, session_id=session_id,
        session_secret=_session_secret(request), now=request.app.state.clock.now(),
    )


@router.post("/oauth/openai/transactions/{transaction_id}/complete")
def oauth_complete_manual(transaction_id: str, payload: ManualCallback, request: Request,
                          db: Session = Depends(get_db)) -> dict:
    from app.ai.connect_router import complete_context

    admin_id, session_id = _actor_and_session(request)
    now = request.app.state.clock.now()
    done = oauth.complete_manual(
        db, transaction_id=transaction_id, admin_user_id=admin_id, session_id=session_id,
        callback_url=payload.callback_url, context=complete_context(request, now),
    )
    record_audit_from_request(
        request, db, action="ai.oauth.connect", object_type=service.OBJECT_TYPE, object_id=transaction_id,
        after={"account": done["account_label"], "via": "manual"},
    )
    return {"ok": True, "account_label": done["account_label"]}


@router.post("/oauth/openai/logout")
def oauth_logout(request: Request, db: Session = Depends(get_db)) -> dict:
    runtime = _runtime(request)
    now = request.app.state.clock.now()
    result = oauth.logout(db, tokens=runtime.chatgpt_tokens(), outbound=request.app.state.outbound_client, now=now)
    record_audit_from_request(
        request, db, action="ai.oauth.logout", object_type=service.OBJECT_TYPE, object_id="openai.chatgpt",
        after={"revoked": result["revoked"], "removed": result["removed"]},
    )
    return {**result, "overview": service.overview(db, runtime, _secrets(request), request.app.state.settings_cache)}
