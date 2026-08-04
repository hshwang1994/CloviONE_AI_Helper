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

# CSP: 외부 리소스를 전면 허용한다 (사용자 지시, 2026-08-04).
#
# 지시 원문: "CDN과 외부 라이브러리 사용을 금지하지 않는다 … UI 품질과 기능 구현에 도움이
# 된다면 CDN, 웹폰트, 아이콘, 애니메이션, 차트, 시각화 및 기타 외부 라이브러리를 자유롭게
# 사용하라. 기존 CSP나 보안 설정을 유지하기 위해 구현 수준을 낮추거나 기능을 포기하지 마라."
#
# 무엇이 열렸나:
#   script-src  'unsafe-inline' 'unsafe-eval' https:  — CDN 스크립트, 인라인 부트스트랩,
#               런타임 컴파일(차트·애니메이션 라이브러리 일부가 Function 생성자를 쓴다)
#   style-src   'unsafe-inline' https:                — Emotion 런타임 주입 + 외부 스타일시트
#   font-src    data: https:                          — 웹폰트
#   img-src     data: blob: https:                    — 외부 이미지, 캔버스 blob
#   connect-src https: wss:                           — 외부 API·WebSocket
#   frame-src   https:                                — 외부 임베드
#
# **무엇을 잃었는지 정직하게 적어 둔다**: 예전에는 script-src 'self' 가 XSS 방어의 축이었다.
# 이제 없다. 그러니 아래 둘은 계속 지킨다 — 공짜로 남는 방어이고 구현 수준을 낮추지도 않는다:
#   1) 서버 데이터를 innerHTML 에 넣지 않는다(React 이스케이프 / textContent 전용).
#   2) 사용자 입력을 스크립트·스타일 문자열에 이어 붙이지 않는다.
#
# 그대로 둔 것(외부 리소스와 무관한 방어라 풀 이유가 없다):
#   object-src 'none'(플러그인) · base-uri 'self'(<base> 주입으로 상대경로 납치)
#   frame-ancestors 'none'(클릭재킹) · form-action 'self'(폼 전송지 탈취)
CSP_POLICY = (
    "default-src 'self' https:; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval' https:; "
    "style-src 'self' 'unsafe-inline' https:; "
    "img-src 'self' data: blob: https:; "
    "connect-src 'self' https: wss:; "
    "font-src 'self' data: https:; "
    "frame-src 'self' https:; "
    "media-src 'self' data: blob: https:; "
    "worker-src 'self' blob:; "
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
# 파일 업로드(이미지/PDF)는 최대 10MB(app/core/uploads.py MAX_UPLOAD_BYTES). multipart
# 봉투(경계·헤더·파일명) 여유를 두고 12MB로 올린다. 아래 목록만 예외이며 나머지는 256k 유지.
# nginx vhost에도 같은 예외 location이 있어야 프로덕션에서 413이 나지 않는다(방어 이중화).
#
# **목록으로 만든 이유.** 게시판 하나만 정규식으로 예외를 두고 있었는데, 그 뒤에 들어온
# 팀 채팅 이미지(`/rooms/{id}/images`)와 프로필 사진은 그 목록에 들어가지 않아 **10MB 를
# 받는다고 해 놓고 256k 에서 413** 이 났다. 업로드 라우트를 새로 만들 때 여기 한 줄을 빠뜨리면
# 같은 일이 반복되므로, 한곳에 모아 두고 tests/regression 이 개수를 지킨다.
UPLOAD_BODY_BYTES = 12 * 1024 * 1024
BOARD_UPLOAD_BODY_BYTES = UPLOAD_BODY_BYTES   # 기존 이름(테스트·문서에서 참조) 유지
_UPLOAD_ROUTE_RES = (
    re.compile(r"^/api/board/posts/[^/]+/attachments$"),
    re.compile(r"^/api/team-chat/rooms/[^/]+/images$"),
    re.compile(r"^/api/tickets/[^/]+/attachments$"),
    re.compile(r"^/api/me/avatar$"),
)

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
            # 기본은 no-store: 인증된 응답이 디스크에 남지 않게 한다.
            #
            # setdefault 인 이유(PLAN Phase 4 — 스케일 심): 폴링 엔드포인트 세 곳이
            # ETag/304 를 쓰려면 브라우저가 응답을 **저장했다가 재검증**할 수 있어야 하는데,
            # `no-store` 는 저장 자체를 금지하므로 브라우저가 If-None-Match 를 영영 보내지
            # 않는다 — 그러면 ETag 는 붙어만 있고 아무것도 아끼지 못하는 죽은 헤더가 된다.
            # 그래서 그 세 핸들러만 `private, no-cache`(저장은 하되 쓰기 전 반드시 재검증)를
            # 직접 설정하고, 여기서는 **덮어쓰지 않는다**. 나머지 전부는 예전 그대로 no-store 다.
            response.headers.setdefault("Cache-Control", "no-store")

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
    if request.method == "POST" and any(
        rx.match(request.url.path) for rx in _UPLOAD_ROUTE_RES
    ):
        return UPLOAD_BODY_BYTES
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
