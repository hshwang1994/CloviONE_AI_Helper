"""ChatGPT 계정 연결 도우미의 문 — `/api/connect/openai/*` 와 도우미 파일 `/connect/<파일>` (계획 3.14, D-516).

## 왜 로그인 세션이 없는가

도우미는 관리자 PC 에서 도는 작은 스크립트다. 브라우저의 로그인 쿠키를 갖지 않고 갖게 해서도 안 된다(쿠키를
스크립트에 옮기는 순간 세션 탈취와 같다). 그래서 도우미는 관리자가 화면에서 받은 **짝짓기 토큰**으로만 자신을 증명한다:
256비트 무작위 값이고, 서버에는 해시만 있으며, 한 번 쓰면 끝나고, 10분 뒤에 사라진다(`app/ai/credentials/oauth.py`).

쿠키가 없으므로 CSRF 가 성립하지 않는다. 대신 세 겹을 둔다: 브라우저가 다른 사이트에서 보낸 요청을 막는 Origin 검사
(`verify_connect_origin`), IP 단위 속도 제한, 그리고 짝짓기 토큰 자체. 응답에는 토큰이 없다 - 계정 이름만 있다.

## 도우미 파일

`/connect/clovirassist-connect.ps1`(Windows)과 `/connect/clovirassist-connect.py`(macOS, Linux)를 그대로 내려준다.
로그인이 필요 없다 - 비밀이 없는 공개 스크립트이고, 저장소에도 그대로 있다. 화면은 파일의 sha256 을 함께 보인다.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.ai.credentials import oauth
from app.core.deps import get_db
from app.core.errors import AppError, NotFoundError, RateLimitedError

router = APIRouter(tags=["ai-connect"])

HELPER_DIR = Path(__file__).resolve().parents[2] / "tools" / "connect"
HELPER_FILES = {
    "clovirassist-connect.ps1": "text/plain; charset=utf-8",
    "clovirassist-connect.py": "text/x-python; charset=utf-8",
}
RATE_BUCKET = "ai-connect"


class ConnectOriginMismatchError(AppError):
    status_code = 403
    code = "origin_mismatch"
    default_message = "다른 사이트에서 보낸 연결 요청은 받지 않습니다."


def verify_connect_origin(request: Request) -> None:
    """브라우저가 다른 사이트에서 보낸 요청을 막는다. 도우미는 이 머리글을 보내지 않으므로 지나간다.

    로그인 경로의 검사(`app/auth/router.py::_verify_login_origin`)와 같은 규칙이다: Fetch Metadata 가 있으면 그것을,
    없으면 Origin 과 Host 를 비교한다. 둘 다 없으면(스크립트) 이 검사는 판단하지 않는다 - 짝짓기 토큰이 증명한다.
    """
    site = request.headers.get("sec-fetch-site")
    if site is not None:
        if site not in ("same-origin", "none"):
            raise ConnectOriginMismatchError()
        return
    source = request.headers.get("origin")
    if not source:
        return
    from urllib.parse import urlsplit

    host = request.headers.get("host", "")
    if urlsplit(source).netloc and host and urlsplit(source).netloc != host:
        raise ConnectOriginMismatchError()


def _guard_rate(request: Request) -> None:
    from app.core.deps import client_ip_from_request

    limiter = getattr(request.app.state, "login_ratelimiter", None)
    if limiter is None:
        return
    key = f"{RATE_BUCKET}:{client_ip_from_request(request)}"
    if not limiter.allow(key):
        raise RateLimitedError(
            "연결 요청이 너무 많습니다. 잠시 뒤 다시 시도하세요.",
            retry_after_seconds=limiter.retry_after_seconds(key),
        )


class BeginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pairing_token: str = Field(min_length=20, max_length=200)
    port: int


class CallbackValues(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: str | None = Field(default=None, max_length=4096)
    state: str | None = Field(default=None, max_length=200)
    client_id: str | None = Field(default=None, max_length=200)
    scope: str | None = Field(default=None, max_length=1000)
    error: str | None = Field(default=None, max_length=200)


class CompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pairing_token: str = Field(min_length=20, max_length=200)
    transaction_id: str = Field(max_length=36)
    callback: CallbackValues


def complete_context(request: Request, now):
    from app.ai.runtime import runtime_for_app

    runtime = runtime_for_app(request.app)
    cache = getattr(request.app.state, "settings_cache", None)
    return oauth.CompleteContext(
        now=now, outbound=request.app.state.outbound_client, tokens=runtime.chatgpt_tokens(),
        session_secret=str(getattr(request.app.state.settings, "session_secret", "") or ""),
        settings_values=cache.current() if cache is not None else {},
    )


@router.post("/api/connect/openai/begin", dependencies=[Depends(verify_connect_origin)])
def connect_begin(payload: BeginRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    _guard_rate(request)
    now = request.app.state.clock.now()
    reply = oauth.begin(
        db, pairing_token=payload.pairing_token, port=payload.port, now=now,
        session_secret=str(getattr(request.app.state.settings, "session_secret", "") or ""),
    )
    db.commit()
    return reply


@router.post("/api/connect/openai/complete", dependencies=[Depends(verify_connect_origin)])
def connect_complete(payload: CompleteRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    from app.core.audit import record_audit
    from app.core.deps import client_ip_from_request

    _guard_rate(request)
    now = request.app.state.clock.now()
    done = oauth.complete_from_helper(
        db, pairing_token=payload.pairing_token, transaction_id=payload.transaction_id,
        callback=payload.callback.model_dump(), context=complete_context(request, now),
    )
    # 행위자는 연결을 시작한 관리자다 - 도우미는 그 사람의 손이다. 토큰이나 코드는 적지 않는다.
    record_audit(
        db, actor_id=done["admin_user_id"], action="ai.oauth.connect", object_type="ai_config",
        object_id=done["transaction_id"], after={"account": done["account_label"], "via": "helper"},
        client_ip=client_ip_from_request(request), request_id=getattr(request.state, "request_id", None),
    )
    db.commit()
    return {"ok": True, "account_label": done["account_label"]}


def helper_sha256(name: str) -> str | None:
    path = HELPER_DIR / name
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


@router.get("/connect/{name}")
def connect_helper_file(name: str) -> Response:
    content_type = HELPER_FILES.get(name)
    if content_type is None:
        raise NotFoundError("도우미 파일을 찾을 수 없습니다.")
    try:
        body = (HELPER_DIR / name).read_bytes()
    except OSError:
        raise NotFoundError("도우미 파일을 찾을 수 없습니다.") from None
    return Response(
        content=body, media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )
