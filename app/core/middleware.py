"""Request-scoped middleware: request ID, security headers, access log, body cap.

CSP per spec §25.6 — no inline scripts/styles anywhere in the app.
"""

from __future__ import annotations

import logging
import re
import time
import uuid

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("app.access")

CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'; "
    "form-action 'self'"
)

# Matches nginx client_max_body_size 256k (spec §27.2) — defense in depth.
MAX_BODY_BYTES = 256 * 1024
# Chat messages may carry image attachments (base64). nginx raises the limit for
# this one route the same way; everything else stays at 256k.
ATTACHMENT_BODY_BYTES = 8 * 1024 * 1024
_MESSAGE_POST_RE = re.compile(r"^/api/conversations/[^/]+/messages$")
# 자유게시판 첨부(이미지/PDF)는 최대 10MB(app/core/uploads.py MAX_UPLOAD_BYTES). multipart
# 봉투(경계·헤더·파일명) 여유를 두고 12MB로 올린다. 이 라우트만 예외이며 나머지는 256k 유지.
# nginx vhost에도 같은 예외 location이 있어야 프로덕션에서 413이 나지 않는다(방어 이중화).
BOARD_UPLOAD_BODY_BYTES = 12 * 1024 * 1024
_BOARD_UPLOAD_RE = re.compile(r"^/api/board/posts/[^/]+/attachments$")

STATIC_CACHE_CONTROL = "public, max-age=3600"


def _is_safe_request_id(value: str) -> bool:
    return bool(value) and len(value) <= 64 and value.replace("-", "").isalnum()


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Outermost middleware: request ID in/out, security headers, access log."""

    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("X-Request-ID", "")
        request_id = incoming if _is_safe_request_id(incoming) else uuid.uuid4().hex
        request.state.request_id = request_id

        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000

        response.headers["X-Request-ID"] = request_id
        response.headers["Content-Security-Policy"] = CSP_POLICY
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path.startswith("/static/"):
            # SPA 진입 HTML(예: /static/react/index.html)은 해시된 자산 주소를 담고 있어
            # 절대 캐시하면 안 된다 — 캐시하면 배포로 자산 해시가 바뀌어도 브라우저가 옛 index.html을
            # 붙들어 옛 번들만 계속 로드한다("배포해도 안 바뀐다"). 해시 자산(JS/CSS/이미지)은 내용
            # 주소라 캐시가 안전하므로 그대로 오래 캐시한다.
            if request.url.path.endswith(".html"):
                response.headers["Cache-Control"] = "no-store"
            else:
                response.headers.setdefault("Cache-Control", STATIC_CACHE_CONTROL)
        else:
            response.headers["Cache-Control"] = "no-store"

        logger.info(
            "%s %s %s %.1fms request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            request_id,
        )
        return response


def _body_limit_for(request: Request) -> int:
    if request.method == "POST" and _MESSAGE_POST_RE.match(request.url.path):
        return ATTACHMENT_BODY_BYTES
    if request.method == "POST" and _BOARD_UPLOAD_RE.match(request.url.path):
        return BOARD_UPLOAD_BODY_BYTES
    return MAX_BODY_BYTES


def _replay_receive(body: bytes) -> Receive:
    """Hand the already-buffered body to the app as a single ASGI message."""
    sent = False

    async def receive() -> Message:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


class BodySizeLimitMiddleware:
    """Body cap, enforced whether or not the client declares a length.

    Pure ASGI (not BaseHTTPMiddleware) because a Content-Length check alone is
    not a cap: chunked/streamed requests carry no length, so the only way to
    bound them is to count the bytes as they arrive. Declared-length requests are
    rejected before a single byte is read; undeclared ones are buffered only up
    to the cap and then replayed downstream, so nothing reads past the limit.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        limit = _body_limit_for(request)
        declared = request.headers.get("content-length")

        if declared is not None:
            try:
                length = int(declared)
            except ValueError:
                length = -1
            if length < 0:  # 음수 길이는 상한 비교를 통과해 버린다 — 형식 오류로 막는다.
                response = _reject(request, 400, "bad_request", "Invalid Content-Length")
                await response(scope, receive, send)
                return
            if length > limit:
                response = _reject(
                    request, 413, "payload_too_large", "Request body too large"
                )
                await response(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return

        # 길이 선언이 없고 chunked도 아니면 본문 자체가 없다 (RFC 9112 §6) —
        # 건드리지 않고 흘려보낸다.
        if "chunked" not in request.headers.get("transfer-encoding", "").lower():
            await self.app(scope, receive, send)
            return

        body = bytearray()
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                return  # 클라이언트가 끊겼다 — 응답할 대상이 없다.
            body.extend(message.get("body", b""))
            if len(body) > limit:
                response = _reject(
                    request, 413, "payload_too_large", "Request body too large"
                )
                await response(scope, receive, send)
                return
            more_body = message.get("more_body", False)

        await self.app(scope, _replay_receive(bytes(body)), send)


def _reject(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )
