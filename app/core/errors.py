"""Application error hierarchy and JSON envelope handlers.

Every error response has the shape (spec §25.2 — no stack traces leak):

    {"error": {"code": "...", "message": "...", "request_id": "...", "details": [...]}}
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import ValidationError as PydanticValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.urls import safe_next_path

logger = logging.getLogger("app.errors")


# PA-RC-0014: Pydantic 검증 실패가 영문 그대로 사용자에게 나갔다("Invalid request data
# String should have at most 120 characters"). `err["msg"]`는 절대 파싱하지 않는다 —
# Pydantic 버전이 올라가면 문구가 바뀐다. 안정적인 `err["type"]` + `err["ctx"]`(예:
# max_length)만으로 한국어 문구를 만든다. 매핑에 없는 type도 영어가 새지 않도록 일반
# 문구로 떨어진다(완전 나열이 아니라 안전망이다).
def _validation_error_message_ko(err: dict) -> str:
    err_type = err.get("type") or ""
    ctx = err.get("ctx") or {}

    if err_type == "value_error":
        # 이 저장소의 커스텀 validator(예: 이메일 형식)는 이미 한국어 ValueError를 던진다
        # (app/users/schemas.py::_validate_email_shape 등) — Pydantic이 그 문구를 그대로
        # ctx.error에 담아 주고, msg에는 "Value error, " 영문 접두어를 붙인 것만 다르다.
        # ctx.error를 쓰면 접두어 없이 원래 한국어 문구를 그대로 돌려줄 수 있다.
        custom = ctx.get("error")
        if custom:
            return str(custom)
        return "입력값을 확인해 주세요."
    if err_type == "missing":
        return "필수 항목입니다."
    if err_type == "extra_forbidden":
        return "허용되지 않는 값입니다."
    if err_type == "string_too_short":
        n = ctx.get("min_length")
        return f"최소 {n}자 이상 입력하세요." if n is not None else "너무 짧습니다."
    if err_type == "string_too_long":
        n = ctx.get("max_length")
        return f"최대 {n}자까지 입력할 수 있습니다." if n is not None else "너무 깁니다."
    if err_type == "too_short":
        n = ctx.get("min_length")
        unit = "개" if (ctx.get("field_type") or "").lower() != "string" else "자"
        return f"최소 {n}{unit} 이상이어야 합니다." if n is not None else "너무 짧습니다."
    if err_type == "too_long":
        n = ctx.get("max_length")
        unit = "개" if (ctx.get("field_type") or "").lower() != "string" else "자"
        return f"최대 {n}{unit}까지 허용됩니다." if n is not None else "너무 깁니다."
    if err_type in ("greater_than_equal", "greater_than"):
        n = ctx.get("ge", ctx.get("gt"))
        op = "이상" if err_type == "greater_than_equal" else "초과"
        return f"{n}{op}이어야 합니다." if n is not None else "값이 너무 작습니다."
    if err_type in ("less_than_equal", "less_than"):
        n = ctx.get("le", ctx.get("lt"))
        op = "이하" if err_type == "less_than_equal" else "미만"
        return f"{n}{op}여야 합니다." if n is not None else "값이 너무 큽니다."
    if err_type in ("literal_error", "enum"):
        expected = ctx.get("expected")
        return f"허용되지 않는 값입니다(허용: {expected})." if expected else "허용되지 않는 값입니다."
    if err_type in ("int_parsing", "int_type", "float_parsing", "float_type"):
        return "숫자를 입력하세요."
    if err_type in ("bool_parsing", "bool_type"):
        return "값을 확인하세요."
    if err_type in ("string_type",):
        return "문자열이어야 합니다."
    if err_type in ("list_type",):
        return "목록 형식이어야 합니다."
    if err_type in ("json_invalid", "json_type"):
        return "형식이 올바르지 않습니다."
    # 나열에 없는 type — 영어가 새지 않는 것이 우선이다, 그 다음이 구체성이다.
    return "값을 확인해 주세요."


class AppError(Exception):
    status_code: int = 400
    code: str = "bad_request"
    default_message: str = "Bad request"

    def __init__(self, message: str | None = None, *, details: Any = None) -> None:
        self.message = message or self.default_message
        self.details = details
        super().__init__(self.message)


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"
    # 한국어 UI에 영어가 새지 않도록 기본 메시지도 한국어로 둔다. 세션이 실제로 만료돼
    # get_current_auth가 인자 없이 이 에러를 올릴 때(예: /change-password 제출 중 만료)
    # 사용자에게 그대로 보이던 'Authentication required'를 없앤다.
    default_message = "로그인이 필요합니다. 다시 로그인해 주세요."


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"
    # 한국어 UI에 영어가 새지 않도록 기본 메시지도 한국어로 둔다. 권한 부족 응답이
    # 인자 없이 이 에러를 올릴 때(require_roles 등) 사용자에게 그대로 보이던
    # 'Not allowed'를 없앤다.
    default_message = "권한이 없습니다."


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    default_message = "Resource not found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    default_message = "Conflict"


class ValidationAppError(AppError):
    status_code = 422
    code = "validation_error"
    default_message = "Invalid input"


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"
    default_message = "Too many requests"

    def __init__(
        self,
        message: str | None = None,
        *,
        details: Any = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        # 429 화면(로그인/비밀번호 변경)의 쿨다운 카운트다운이 실제 리미터 설정과
        # 무관한 하드코딩 상수였다 — 리미터를 재조정하면 화면 안내가 조용히 어긋난다.
        # 호출부가 RateLimiter.retry_after_seconds()로 계산한 실제 대기 시간을 실어
        # 보내면, register_error_handlers가 이를 응답 본문(및 Retry-After 헤더)에 싣는다.
        super().__init__(message, details=details)
        self.retry_after_seconds = retry_after_seconds


# ── 외부 소스(Notion) 오류 ────────────────────────────────────────────────────
# 라우터들이 이 둘을 잡아 configured=false / ok=false 로 번역한다(화면이 오류 페이지 대신
# '연동 필요'·'조회 실패'를 그린다). 원래 app/reports/notion_source.py 가 정의했는데, 그러면
# 티켓·스프린트·리포트 라우터가 Notion 구현 모듈을 import 해야 해서 저장소 seam 경계
# 정적검사에 걸린다. 정의는 여기로 올리고 notion_source 는 그대로 재수출한다 —
# 클래스 이름과 code 문자열은 응답 계약이라 바꾸지 않는다.
class NotionNotConfiguredError(AppError):
    """Notion 연동 토큰이 아직 서버에 없다(사용자가 provisioning 하기 전)."""

    status_code = 503
    code = "notion_not_configured"
    default_message = "Notion 연동 토큰이 설정되지 않았습니다."


class NotionQueryError(AppError):
    status_code = 502
    code = "notion_query_failed"
    default_message = "Notion 조회에 실패했습니다."


# 위 둘과 **같은 이유로** 여기 있다. 이 오류는 원래 app/tickets/notion_write.py 가
# 정의했는데, 티켓 저장소 구현체가 둘(Notion · 자체 DB)이 되면서 소스를 안 부르는 쪽도
# 「그 티켓이 없다」를 말해야 하게 됐다. 정의가 Notion 구현 모듈에 남아 있으면 자체 DB
# 구현체가 그 모듈을 import 해야 하고, 그러면 저장소 seam 경계 정적검사에 걸린다
# (그리고 그 import 하나 때문에 소스를 걷어낼 때 고칠 곳이 하나 더 숨는다).
# notion_write 는 이 이름을 그대로 재수출한다 — 클래스 이름과 code 문자열은 응답
# 계약이라 바꾸지 않는다.
class TicketNotFoundError(AppError):
    """대상 티켓이 없거나 접근할 수 없다."""

    status_code = 404
    code = "ticket_not_found"
    default_message = "티켓을 찾을 수 없습니다."


class StorageUnavailableError(AppError):
    """서버 로컬 파일시스템에 쓸 수 없을 때(디스크 풀, 권한 드리프트 등, OPS-05).

    원인(OSError 원문·경로)은 절대 message 에 담지 않는다 — 호출부가
    logger.exception 으로 서버 로그에만 남기고, 사용자에게는 이 기본 메시지만 간다
    (app/core/errors.py 상단 정책: 스택트레이스·내부 경로 미노출).
    """

    status_code = 503
    code = "storage_unavailable"
    default_message = "파일을 저장할 수 없습니다. 잠시 후 다시 시도해 주세요."


class WriteUnavailableError(AppError):
    """요청 처리 자체는 끝까지 성공했는데, 마지막 커밋이 직렬화 경합
    (`is_serialization_conflict`, `app/core/db.py`)으로 실패했을 때(D-75).

    **유니크 위반은 여기 오지 않는다**(D-191). 그것은 "다시 하면 된다"가 아니라 "그
    라우트가 같은 행을 두 번 만들려 했다"는 뜻이라, 재시도를 권하는 503 으로 포장하면
    진짜 원인이 로그에서 사라진다.

    `app/core/deps.py::get_db`의 요청-스코프 바깥 커밋에는 재시도가 없다 — 이미
    `db.rollback()`을 부른 뒤라 방금 flush됐던 행은 사라졌고, 안전하게 재시도하려면
    커밋 재시도가 아니라 요청 처리 전체를 다시 실행해야 한다(SAVEPOINT 재시도 계층과
    다른 문제, `docs/DECISIONS.md` D-75 참고). 그 전체 재실행은 이 커밋 지점에서 아직
    구현되지 않았으므로, 최소한 사용자에게 "무엇이 실패했고 무엇을 하면 되는지"는
    분명히 준다 — 원인(OperationalError 원문)은 StorageUnavailableError와 같은 이유로
    message에 담지 않는다.
    """

    status_code = 503
    code = "write_unavailable"
    default_message = "일시적인 서버 혼잡으로 저장하지 못했습니다. 잠시 후 다시 시도해 주세요."


_HTTP_STATUS_CODES = {
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    413: "payload_too_large",
    429: "rate_limited",
}


def error_response(
    request: Request,
    *,
    code: str,
    message: str,
    status_code: int,
    details: Any = None,
    retry_after_seconds: float | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "request_id": getattr(request.state, "request_id", None),
        }
    }
    if details is not None:
        body["error"]["details"] = details
    if retry_after_seconds is not None:
        body["error"]["retry_after_seconds"] = max(1, round(retry_after_seconds))
    response = JSONResponse(status_code=status_code, content=body)
    if retry_after_seconds is not None:
        response.headers["Retry-After"] = str(max(1, round(retry_after_seconds)))
    return response


def _is_login_form_fallback(request: Request) -> bool:
    """True only for the documented no-JS ``<form method=post action=/login
    novalidate>`` fallback (see app/auth/router.py's ``_is_json_request``
    docstring) — never for login.js's normal fetch() submission, which must
    keep receiving a JSON error body it can parse without a full navigation.

    The success path (auth/router.py's login()) was already fixed to answer
    this exact case with a page redirect instead of a bare JSON body a real
    browser navigation can't do anything with; every failure path (rate
    limit, wrong credentials, locked/disabled/archived account, origin
    mismatch — all raised as AppError subclasses) still fell through to this
    generic JSON handler and left a no-JS user staring at a raw JSON dump.
    """
    if request.url.path != "/login" or request.method != "POST":
        return False
    content_type = request.headers.get("content-type", "")
    return not content_type.startswith("application/json")


async def _login_fallback_redirect(request: Request, code: str) -> RedirectResponse:
    """Build the ``/login?error=<code>`` redirect for a failed no-JS ``<form>``
    POST /login so login_page() (auth/router.py) can re-render the same
    #login-error markup server-side.

    Threads the submitted email and the safe "next" destination back so a failed
    no-JS retry doesn't wipe the form or lose the "return to where you were"
    redirect that login.html's hidden ``<input name="next">`` carries.
    Request.form() is cached by Starlette after the route's _extract_credentials
    dependency already awaited it once, so this re-read does not touch the
    (already consumed) request stream again. Best-effort: if the body can't be
    re-read for any reason, fall back to the plain error redirect.
    """
    query = f"error={code}"
    try:
        form = await request.form()
        submitted_email = str(form.get("email", "")).strip()
        submitted_next = safe_next_path(str(form.get("next", "")))
    except Exception:
        submitted_email = ""
        submitted_next = None
    if submitted_email:
        query += f"&email={quote(submitted_email)}"
    if submitted_next:
        query += f"&next={quote(submitted_next)}"
    return RedirectResponse(f"/login?{query}", status_code=303)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        if _is_login_form_fallback(request):
            return await _login_fallback_redirect(request, exc.code)
        return error_response(
            request,
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
            details=exc.details,
            retry_after_seconds=getattr(exc, "retry_after_seconds", None),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_STATUS_CODES.get(exc.status_code, "http_error")
        return error_response(
            request, code=code, message=str(exc.detail), status_code=exc.status_code
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Field locations and messages only — never echo submitted values back.
        details = [
            {"loc": [str(part) for part in err.get("loc", [])], "msg": _validation_error_message_ko(err)}
            for err in exc.errors()
        ]
        return error_response(
            request,
            code="validation_error",
            message="입력값을 확인해 주세요.",
            status_code=422,
            details=details,
        )

    @app.exception_handler(PydanticValidationError)
    async def _model_validation_error(
        request: Request, exc: PydanticValidationError
    ) -> JSONResponse:
        # FastAPI만 RequestValidationError(요청 바디 자체)를 자동으로 422로 바꿔 준다 —
        # 서비스 코드가 병합된 dict를 직접 SomeModel.model_validate(...)로 재검증하다 실패하는
        # pydantic.ValidationError는 여기 걸리지 않으면 그냥 Exception으로 떨어져 무조건 500이 된다
        # (예: PATCH로 필드를 null로 비웠는데 그 모델이 Optional을 허용 안 하는 계약 실수). 값은
        # 절대 되돌려주지 않는다(위와 동일한 원칙).
        details = [
            {"loc": [str(part) for part in err.get("loc", [])], "msg": _validation_error_message_ko(err)}
            for err in exc.errors()
        ]
        logger.warning(
            "model validation error request_id=%s errors=%s",
            getattr(request.state, "request_id", None),
            details,
        )
        return error_response(
            request,
            code="validation_error",
            message="입력값을 확인해 주세요.",
            status_code=422,
            details=details,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        return await unhandled_error_response(request, exc)


async def unhandled_error_response(request: Request, exc: Exception):
    """The 500 an unhandled exception turns into — shared so CORE-04's fix can
    reuse it (see below), not just the ``@app.exception_handler(Exception)``
    registration above.

    CORE-04: that registration becomes Starlette's ``ServerErrorMiddleware``
    handler, which sits **outside** every ``app.add_middleware(...)`` layer
    (including ``RequestContextMiddleware``, which adds the security headers
    and writes the access log on its way back out through ``call_next``). An
    exception that reaches here never passes back through that middleware —
    the 500 response it produces has no CSP/X-Frame-Options/etc. and never
    gets logged. So ``RequestContextMiddleware.dispatch`` now catches the
    exception itself, calls this same function to build the identical
    response, and adds headers + logs it exactly like a normal response —
    meaning this handler becomes a backstop for whatever still slips past
    the middleware layer (e.g. an ASGI-level failure outside dispatch),
    not the only place a 500 body gets built.
    """
    logger.exception(
        "unhandled error request_id=%s", getattr(request.state, "request_id", None)
    )
    # A no-JS <form> POST /login that hits a genuinely unexpected 500 used to
    # get raw JSON here (unlike every AppError failure path, which redirects
    # via _app_error). A real browser navigation can't consume a bare JSON
    # body, so the no-JS user saw a JSON dump instead of a rendered Korean
    # error page. Route it through the same fallback redirect; login_page()
    # renders _LOGIN_ERROR_MESSAGES["internal_error"].
    if _is_login_form_fallback(request):
        return await _login_fallback_redirect(request, "internal_error")
    return error_response(
        request,
        code="internal_error",
        message="Internal server error",
        status_code=500,
    )
