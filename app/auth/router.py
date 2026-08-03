"""Login, logout, and password-change endpoints (spec §11.3, §23.1)."""

from __future__ import annotations

import functools
from datetime import timedelta, timezone
from urllib.parse import quote as _urlquote
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.audit import record_audit, record_audit_from_request
from app.observability.service import EVENT_LOGIN, record_usage
from app.core.deps import (
    AuthContext,
    get_client_ip,
    get_current_auth,
    get_db,
    get_page_auth,
    require_csrf,
)
from app.core.errors import (
    AppError,
    RateLimitedError,
    UnauthorizedError,
    ValidationAppError,
)
from app.core.security import (
    hash_password,
    validate_password_policy,
    verify_password,
)
from app.core.sessions import clear_session_cookie, set_session_cookie
from app.core.urls import safe_next_path
from app.users.service import get_user_by_email, normalize_email

router = APIRouter(tags=["auth"])

# login.js의 setLoginHint()는 mailto subject를 encodeURIComponent로 완전히 인코딩한다.
# 서버 렌더 폴백(no-JS)은 예전에 "계정%20문의"처럼 공백만 손으로 %20 치환해, 같은 기능이
# 두 경로마다 다른 인코딩을 냈다(한글 자체는 인코딩되지 않은 채 href에 그대로 들어감 —
# RFC 3986 위반이자 JS 경로와 불일치). 여기서 한 번만 계산해 두 화면·두 문구가 모두
# 같은 값을 쓰게 한다.
_MAILTO_SUBJECT_ACCOUNT = _urlquote("계정 문의")
_MAILTO_SUBJECT_RESET = _urlquote("비밀번호 재발급 요청")


class AccountLockedError(AppError):
    status_code = 403
    code = "account_locked"
    default_message = "계정이 잠겨 있습니다. 잠시 후 다시 시도하거나 관리자에게 문의하세요."


class AccountDisabledError(AppError):
    status_code = 403
    code = "account_disabled"
    default_message = "비활성화된 계정입니다. 관리자에게 문의하세요."


class AccountArchivedError(AppError):
    """보관된 계정. '비활성'과 구분되는 별개의 상태다 — 관리자가 원인을 찾을 때
    '비활성화된 계정'이라고만 나오면 활성 목록에서 계정을 찾다가 헤맨다(보관된 계정은
    기본 목록에 아예 없다). 자격 증명이 확인된 뒤에만 나가므로 계정 열거에 쓸 수 없다."""

    status_code = 403
    code = "account_archived"
    default_message = "보관된 계정입니다. 사용하려면 관리자에게 복구를 요청하세요."


class InvalidCredentialsError(UnauthorizedError):
    code = "invalid_credentials"
    default_message = "이메일 또는 비밀번호가 올바르지 않습니다."


class WrongCurrentPasswordError(UnauthorizedError):
    """비밀번호 변경 시 '현재 비밀번호 불일치'. 상태코드는 401로 같지만 세션 만료(코드
    'unauthorized')와 구분되는 별도 코드를 준다 — 프런트가 오답일 때는 화면에 머물고,
    진짜 세션 만료일 때만 /login으로 보낼 수 있게(무한 리다이렉트 루프 방지)."""

    code = "wrong_current_password"
    default_message = "현재 비밀번호가 올바르지 않습니다."


class OriginMismatchError(AppError):
    status_code = 403
    code = "origin_mismatch"
    default_message = "요청 출처를 확인할 수 없습니다. 새로고침 후 다시 시도해 주세요."


def _verify_login_origin(request: Request) -> None:
    """Login-CSRF guard: POST /login has no session yet, so it can't use the
    normal X-CSRF-Token check (require_csrf) — it also accepts a no-JS
    form-urlencoded fallback (_extract_credentials) for users without
    JavaScript. Without this, a third-party page could silently auto-submit a
    hidden cross-origin <form method=post action=/login> pre-filled with the
    ATTACKER's own credentials; the victim's browser executes it with no
    interaction and honors the resulting Set-Cookie, leaving the victim
    authenticated into the attacker's account ('login CSRF') — anything the
    victim then does (e.g. chats) is attributed to that account.

    Prefer the modern Fetch Metadata signal (Sec-Fetch-Site, sent by all
    current browsers and NOT spoofable by page JS) when present; fall back to
    comparing Origin/Referer's host against our own Host header. If neither
    header is present at all, this check can't decide and does not block —
    it is a hardening layer, not the only defense.
    """
    sec_fetch_site = request.headers.get("sec-fetch-site")
    if sec_fetch_site is not None:
        if sec_fetch_site not in ("same-origin", "none"):
            raise OriginMismatchError()
        return

    source = request.headers.get("origin") or request.headers.get("referer")
    if not source:
        return
    from urllib.parse import urlsplit

    source_host = urlsplit(source).netloc
    host = request.headers.get("host", "")
    if source_host and host and source_host != host:
        raise OriginMismatchError()


@functools.lru_cache(maxsize=1)
def _dummy_password_hash() -> str:
    """Argon2 해시 1개를 만들어 두고 '없는 계정' 검증에 쓴다 (import 시점 비용 회피).

    존재하지 않는 계정이라고 검증을 건너뛰면 응답 시간만으로 계정 존재가 드러난다.
    """
    from app.core.security import generate_temp_password

    return hash_password(generate_temp_password())


def _password_matches(user, password: str) -> bool:
    """계정 유무와 무관하게 항상 Argon2 검증 1회를 수행한다 (타이밍 동일화)."""
    if user is None:
        verify_password(_dummy_password_hash(), password)
        return False
    return verify_password(user.password_hash, password)


# 서버 렌더 no-JS 폴백(_is_login_form_fallback, app/core/errors.py)이 /login?error=<code>로
# 돌아왔을 때 login_page()가 #login-error에 채울 문구. login.js의 KNOWN_ERROR_CODES와
# 같은 코드 집합을 다루되, 실제 raise 시점 메시지(예: 계정 잠금의 남은 분 수)는 담을 수
# 없으므로 각 에러 클래스의 default_message(혹은 그와 동등한 문구)로 근사한다 — 서버가
# 최종 권한이라는 사실은 그대로다, 이건 no-JS 사용자를 위한 안내일 뿐.
_LOGIN_ERROR_MESSAGES: dict[str, str] = {
    InvalidCredentialsError.code: InvalidCredentialsError.default_message,
    AccountLockedError.code: AccountLockedError.default_message,
    AccountDisabledError.code: AccountDisabledError.default_message,
    AccountArchivedError.code: AccountArchivedError.default_message,
    "rate_limited": "로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요.",
    "validation_error": "이메일과 비밀번호를 입력하세요.",
    OriginMismatchError.code: OriginMismatchError.default_message,
    # no-JS 폴백이 예기치 못한 500을 만났을 때(app/core/errors.py _unhandled) 이 화면으로
    # 돌아온다 — 원시 JSON('Internal server error') 대신 한국어 안내를 보이게 한다.
    "internal_error": "일시적인 서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
}


def _is_json_request(request: Request) -> bool:
    """True for login.js's fetch() submission; False for the no-JS
    ``<form method=post action=/login novalidate>`` native fallback (which the
    browser always sends as application/x-www-form-urlencoded, never JSON).
    Used to decide whether POST /login should answer with JSON (for the
    fetch/XHR caller to parse) or a full-page RedirectResponse (for a real
    browser navigation, which can't consume a bare JSON body)."""
    return request.headers.get("content-type", "").startswith("application/json")


async def _extract_credentials(request: Request) -> tuple[str, str]:
    try:
        if _is_json_request(request):
            data = await request.json()
        else:
            form = await request.form()
            data = dict(form)
    except Exception:
        raise ValidationAppError("요청 형식이 올바르지 않습니다.") from None
    # JSON body가 문법적으로는 유효해도 객체가 아닐 수 있다(예: [1,2,3], "x", 42) — 이 경우
    # data.get()이 AttributeError로 죽어 인증 없이도 500을 낼 수 있었다.
    if not isinstance(data, dict):
        raise ValidationAppError("요청 형식이 올바르지 않습니다.")
    email = normalize_email(str(data.get("email", "")))
    password = str(data.get("password", ""))
    if not email or not password:
        raise ValidationAppError("이메일과 비밀번호를 입력하세요.")
    return email, password


async def _extract_next(request: Request) -> str | None:
    """로그인 성공 후 돌아갈 원래 페이지. app/main.py의 PageAuthRequired 리다이렉트가
    ?next=<path>로 붙이고, login.html이 그 값을 hidden input(no-JS 폴백)에 실어 돌려주거나
    login.js가 JSON 본문에 실어 보낸다. request.json()/form()은 _extract_credentials가 이미
    한 번 읽었더라도 Starlette가 캐시하므로 스트림을 다시 소비하지 않는다."""
    try:
        if _is_json_request(request):
            data = await request.json()
        else:
            form = await request.form()
            data = dict(form)
    except Exception:
        return None
    return safe_next_path(str(data.get("next", "")))


class ChangePasswordRequest(BaseModel):
    """POST /change-password 본문. 이전엔 `_json_body`(자유 dict)로 받아
    `data.get(...)`로 읽었다 — 유효-JSON이지만 객체가 아닌 본문(예: `[1,2]`, `"x"`, `42`)이
    오면 `.get`이 `AttributeError`를 던져 잡히지 않는 500으로 샜다(포괄 예외 핸들러가
    받아 로그만 남기고 사용자에겐 'Internal server error'). Pydantic 모델로 받으면
    FastAPI가 그런 형태 불일치를 정상적인 422 RequestValidationError 경로로 돌린다
    (프런트가 이미 다루는 형태)."""

    current_password: str = Field(default="")
    new_password: str = Field(default="")


def _subject_particle(word: str) -> str:
    """받침 유무에 따른 한국어 주격 조사(이/가)를 계산한다.

    login.html의 히어로 문구는 {{ app_name }}에 조사 '가'를 하드코딩해 붙였다(
    "{{ app_name }}가 Notion과 연결된..."). app_name(product_name)은 브랜딩 설정
    (app/settings/registry.py ui_branding)에서 관리자가 자유롭게 바꿀 수 있는 문자열이라,
    받침 있는 이름(예: '사내 업무봇')으로 바꾸면 '사내 업무봇가'처럼 문법이 깨진다.
    완전한 한글 음절로 끝나는 이름만 정확히 판정하고, 그 외(영문/숫자 등으로 끝나는
    이름)는 기존 하드코딩과 동일한 안전 기본값 '가'를 그대로 낸다.
    """
    word = (word or "").strip()
    if not word:
        return "가"
    code = ord(word[-1])
    if 0xAC00 <= code <= 0xD7A3:
        # 완성형 한글 음절 = (초성*21 + 중성)*28 + 종성 + 0xAC00. 종성(받침) 인덱스가
        # 0이면 받침이 없다 → '가', 그 외(받침 있음) → '이'.
        return "가" if (code - 0xAC00) % 28 == 0 else "이"
    return "가"


def _display_year(request: Request) -> int:
    """저작권 연도는 서버 렌더 시점의 Asia/Seoul 연도로 낸다 — 템플릿에 연도를 박아 두면
    해가 바뀔 때마다 낡는다(§불변 9: 표시는 Asia/Seoul)."""
    settings = request.app.state.settings
    now = request.app.state.clock.now()  # naive UTC
    try:
        return now.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.timezone)).year
    except Exception:  # pragma: no cover - defensive: 잘못된 tz 설정이어도 연도는 낸다
        return now.year


@router.get("/login")
def login_page(request: Request, db: Session = Depends(get_db)):
    from app.core.deps import _load_auth

    next_path = safe_next_path(request.query_params.get("next", ""))
    if _load_auth(request, db) is not None:
        return RedirectResponse(next_path or "/", status_code=303)
    branding = request.app.state.settings_cache.current_value("ui_branding") or {}
    app_name = branding.get("product_name", "ClovirONE 업무 도우미")
    # 이메일 필드의 placeholder는 이 회사(goodmit.co.kr)를 하드코딩했었다 — 관리자가
    # settings 화면에서 allowed_email_domains를 다른 값으로 바꿔도 placeholder만 낡은
    # 예시를 계속 보여줬다(round28 감사 E). 실제 허용 도메인 목록의 첫 값을 예시로 쓴다.
    allowed_domains = (
        request.app.state.settings_cache.current_value("allowed_email_domains") or []
    )
    email_placeholder = (
        f"name@{allowed_domains[0]}" if allowed_domains else "name@example.com"
    )
    error_code = request.query_params.get("error")
    # app/main.py의 PageAuthRequired 핸들러가 세션 쿠키가 있었는데도 인증에 실패했을 때만
    # (진짜 만료/폐기 — 처음부터 미인증 방문과 구분) 이 플래그를 단다.
    session_expired = request.query_params.get("expired") == "1"
    # no-JS 폴백 실패 후 되돌아온 재렌더에서만 채워진다(app/core/errors.py의 _app_error가
    # 실패한 no-JS 제출의 email 필드를 그대로 얹어 리다이렉트한다). 값 자체는 사용자가
    # 방금 자기 폼에 직접 타이핑한 문자열이라 별도 검증 없이 그대로 표시해도 안전하지만,
    # 렌더는 반드시 Jinja auto-escape로만 한다(§2 규칙 6 — innerHTML 아님).
    submitted_email = request.query_params.get("email", "")
    return request.app.state.templates.TemplateResponse(
        request,
        "login.html",
        {
            "app_name": app_name,
            # app_name 뒤에 붙는 주격 조사(이/가) — 받침 유무에 따라 서버가 계산한다.
            "app_name_particle": _subject_particle(app_name),
            # 비밀번호 재발급 요청 연락처(브랜딩 설정에 있으면 mailto로 노출).
            "support_email": branding.get("support_email"),
            "mailto_subject_account": _MAILTO_SUBJECT_ACCOUNT,
            "mailto_subject_reset": _MAILTO_SUBJECT_RESET,
            "current_year": _display_year(request),
            "email_placeholder": email_placeholder,
            # no-JS <form> 폴백 실패 경로(app/core/errors.py의 _is_login_form_fallback)가
            # /login?error=<code>로 돌아왔을 때만 채워진다 — JS가 정상 동작하는 사용자는
            # fetch()가 페이지를 새로 로드하지 않으므로 이 파라미터를 절대 겪지 않는다.
            "login_error": _LOGIN_ERROR_MESSAGES.get(error_code) if error_code else None,
            "submitted_email": submitted_email,
            # login.html의 안내 문구(비밀번호 재발급 vs 계정 문의) 선택에 쓰인다 — no-JS 폴백
            # 재렌더에서만 채워진다. JS 경로는 login.js가 같은 판단을 동적으로 한다.
            "error_code": error_code,
            # 세션 만료/미인증 리다이렉트가 얹은 원래 목적지(app/main.py). hidden input으로
            # 폼에 실어 no-JS 제출·login.js JSON 제출 양쪽이 로그인 성공 후 그리로 돌아가게 한다.
            "next_path": next_path,
            "session_expired": session_expired,
        },
    )


@router.post("/login", dependencies=[Depends(_verify_login_origin)])
def login(
    request: Request,
    credentials: tuple[str, str] = Depends(_extract_credentials),
    next_target: str | None = Depends(_extract_next),
    db: Session = Depends(get_db),
):
    # sync 핸들러(§2 불변 규칙 1): FastAPI가 이 함수를 threadpool에서 실행하므로 Argon2
    # 검증과 동기 SQLAlchemy가 이벤트 루프를 막지 않는다. 본문 파싱은 async 의존성
    # `_extract_credentials`가 루프에서 먼저 처리한다.
    settings = request.app.state.settings
    clock = request.app.state.clock
    limiter = request.app.state.login_ratelimiter
    session_service = request.app.state.session_service

    client_ip = get_client_ip(request)
    login_limit_key = f"login:{client_ip}"
    if not limiter.allow(login_limit_key):
        raise RateLimitedError(
            "로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요.",
            retry_after_seconds=limiter.retry_after_seconds(login_limit_key),
        )

    email, password = credentials
    user = get_user_by_email(db, email)
    now = clock.now()

    # 인증 실패 응답은 계정 존재 여부를 드러내면 안 된다: 잠금 여부와 상관없이 먼저
    # 비밀번호를 검증하고(없는 계정도 더미 해시로 동일 비용), 잠금 사실은 자격 증명이
    # 맞는 사람에게만 알린다. 잠금 검사를 앞에 두면 403/401 차이로 계정이 열거된다.
    locked = user is not None and user.locked_until is not None and user.locked_until > now

    if not _password_matches(user, password):
        # '누가 언제 로그인/실패했나'는 감사 로그의 핵심 도메인인데 지금까지 이 라우터는
        # 한 번도 record_audit를 부르지 않았다(감사 화면의 존재 목적과 어긋난다). 계정이
        # 존재할 때만 남긴다 — 없는 계정에 대한 시도는 object_id가 없어 계정 열거에
        # 쓰일 수 있는 신호를 남기지 않는다(§인증 실패 응답은 계정 존재를 드러내지 않음).
        if user is not None:
            record_audit(
                db, actor_id=user.id, action="user.login_failed", object_type="user",
                object_id=user.id, result="failure", client_ip=client_ip,
                request_id=getattr(request.state, "request_id", None),
            )
            if not locked:
                user.failed_login_count += 1
                if user.failed_login_count >= settings.login_max_failures:
                    user.locked_until = now + timedelta(seconds=settings.login_lock_seconds)
                    user.failed_login_count = 0
                    # 계정 잠금 알림 (spec §13.5) — 본인 + 관리자.
                    from app.notifications.service import notify_admins, notify_user

                    notify_user(
                        db, user.id, type_="account_locked",
                        title="로그인 실패 누적으로 계정이 잠겼습니다",
                        body="잠금 시간이 지나면 자동 해제됩니다. 즉시 해제는 관리자에게 문의하세요.",
                        now=now,
                    )
                    notify_admins(
                        db, type_="account_locked",
                        title=f"계정 잠금 발생: {user.email}",
                        related=("user", user.id), now=now,
                    )
            # get_db의 자동 commit은 이 함수가 끝에서 항상 예외를 던지므로 절대 실행되지
            # 않는다(예외 시 db.rollback() 경로를 탄다) — 위에서 남긴 감사 로그(+잠금
            # 상태 변경)를 실제로 저장하려면 여기서 명시적으로 커밋해야 한다.
            db.commit()
        raise InvalidCredentialsError()

    # 여기부터는 자격 증명이 확인된 본인이다 — 이제서야 계정 상태를 알려도 된다.
    if locked:
        # '잠시 후'는 1분인지 1시간인지 알 수 없어 사용자가 언제 재시도할지 판단하지
        # 못한다. 남은 잠금 시간을 분 단위(올림)로 알려준다. 자격 증명이 맞은 본인에게만
        # 나가므로 계정 열거에 쓰이지 않는다.
        remaining_seconds = int((user.locked_until - now).total_seconds())
        minutes = max(1, -(-remaining_seconds // 60))  # ceil division
        raise AccountLockedError(
            f"계정이 잠겨 있습니다. 약 {minutes}분 후 다시 시도하거나 관리자에게 문의하세요."
        )

    if user.archived_at is not None:
        raise AccountArchivedError()

    if not user.active:
        raise AccountDisabledError()

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    record, token = session_service.create(
        db,
        user,
        client_ip=client_ip,
        user_agent=request.headers.get("user-agent"),
    )
    record_audit(
        db, actor_id=user.id, action="user.login", object_type="user",
        object_id=user.id, client_ip=client_ip,
        request_id=getattr(request.state, "request_id", None),
    )
    # 사용 통계(0026). 로그인은 세션당 한 번뿐인 전형적인 저빈도 지점이다 —
    # 채팅 전송·폴링 경로에는 절대 걸지 않는다(app/observability/service.py 규칙).
    # 감사 로그와 목적이 다르다: 감사는 '누가 무엇을 바꿨나', 이건 '얼마나 쓰이나'다.
    record_usage(db, event=EVENT_LOGIN, user_id=user.id,
                 org_id=getattr(user, "org_id", None), now=now)
    db.commit()

    if _is_json_request(request):
        # login.js does NOT read csrf_token/user from this body before navigating away
        # (window.location.href) — the destination page (React SPA's auth.jsx, or this
        # app's own change-password template) independently re-fetches identity/CSRF
        # after landing. Both fields stay in the contract anyway: they're the natural
        # place a future no-redirect JS client (or a test) would read them from, and
        # dropping them wouldn't shrink attack surface (both are already served via
        # /api/me and the session cookie). Keep this comment in sync if that assumption
        # changes.
        response = JSONResponse(
            {
                "ok": True,
                "must_change_password": user.must_change_password,
                # 세션 만료로 튕겨나왔던 원래 목적지(app/main.py PageAuthRequired 핸들러 →
                # login.html hidden input → 여기). must_change_password가 여전히 우선한다 —
                # 강제 변경 화면을 next로 우회할 수 없다. login.js가 이 값을 읽어 리다이렉트한다.
                "next": None if user.must_change_password else next_target,
                "csrf_token": record.csrf_token,
                "user": {
                    "email": user.email,
                    "display_name": user.display_name,
                    "role": user.role,
                },
            }
        )
    else:
        # login.html's <form method=post action=/login novalidate> is a
        # documented no-JS fallback for when login.js fails to load/execute
        # (CSP block, extension interference, slow network) — but this
        # handler used to unconditionally return raw JSON even for that path.
        # A real browser navigation can't do anything useful with a bare JSON
        # body (it just renders as text), so a no-JS user who submits the
        # native form saw a blank JSON dump instead of ever reaching the app.
        # Issue a real page redirect for that case instead, carrying the same
        # session cookie the JS path gets.
        response = RedirectResponse(
            "/change-password" if user.must_change_password else (next_target or "/"),
            status_code=303,
        )
    set_session_cookie(response, token, settings, max_age=session_service.absolute_ttl())
    return response


@router.post("/logout", dependencies=[Depends(require_csrf)])
def logout(
    request: Request,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth),
):
    session_service = request.app.state.session_service
    session_service.revoke(db, auth.session)
    record_audit_from_request(
        request, db, action="user.logout", object_type="user", object_id=auth.user.id,
    )
    db.commit()
    response = JSONResponse({"ok": True})
    clear_session_cookie(response, request.app.state.settings)
    return response


@router.get("/change-password")
def change_password_page(request: Request, auth: AuthContext = Depends(get_page_auth)):
    # 실제 정책값을 화면 안내에 반영한다 — 관리자가 정책을 바꿔도 안내 문구가 어긋나지 않게.
    policy = request.app.state.settings_cache.current_value("password_policy") or {}
    branding = request.app.state.settings_cache.current_value("ui_branding") or {}
    return request.app.state.templates.TemplateResponse(
        request,
        "change_password.html",
        {
            # 로그인(login_page)과 같은 브랜딩 제품명을 넘겨, 로그인 → 비밀번호 변경으로
            # 넘어갈 때 탭 제목·화면 문구의 브랜드가 어긋나지 않게 한다(관리자가
            # ui_branding.product_name을 바꿔도 두 화면이 함께 따라간다).
            "app_name": branding.get("product_name", "ClovirONE 업무 도우미"),
            "must_change": auth.user.must_change_password,
            "display_name": auth.user.display_name,
            # 비밀번호 관리자가 저장된 자격 증명을 갱신하려면 폼에 username(이메일)이 있어야
            # 한다 — 숨김 입력으로 넘긴다(change_password.html).
            "email": auth.user.email,
            # CSRF 토큰은 렌더 시점에 서버가 이미 쥐고 있다 — 폼에 실어 내려 준다.
            # 이걸 안 넘기면 change_password.js가 /api/me를 한 번 더 왕복해 토큰을 받아야
            # 하고, 그 왕복이 실패하면(일시적 5xx/네트워크) 제출·탈출 버튼이 영영 잠긴
            # 채로 강제-변경 사용자가 이 화면에 갇힌다. 서버 렌더로 그 실패 모드를 없앤다.
            "csrf_token": auth.session.csrf_token,
            "min_length": policy.get("min_length", 12),
            "min_classes": policy.get("min_classes", 3),
            # 강제 변경 사용자가 임시 비밀번호를 잊으면 이 화면에 갇힌다 — 로그인 화면처럼
            # 재발급 연락처를 넘겨 탈출로를 준다(설정에 있을 때만 mailto로 노출).
            "support_email": branding.get("support_email"),
            "mailto_subject_reset": _MAILTO_SUBJECT_RESET,
            # 로그인 화면과 같은 저작권 footer를 이 화면에도 준다(round28 감사 E) —
            # 없으면 로그인 바로 다음에 오는 화면이 갑자기 별개의 유틸리티 페이지처럼
            # 보인다.
            "current_year": _display_year(request),
        },
    )


@router.post("/change-password", dependencies=[Depends(require_csrf)])
def change_password(
    request: Request,
    data: ChangePasswordRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth),
):
    # sync 핸들러(§2 불변 규칙 1): Argon2 verify+hash가 threadpool에서 돈다. 본문 파싱·
    # 검증은 FastAPI가 ChangePasswordRequest로 이벤트 루프에서 먼저 처리한다.
    settings = request.app.state.settings
    session_service = request.app.state.session_service

    # 무차별 대입 방지 (spec §25.2): /login과 달리 이 엔드포인트는 세션이 이미 있는
    # 상태에서 호출된다 — 탈취/고정된 세션 쿠키 + CSRF 토큰만 있으면 계정 비밀번호
    # 자체는 몰라도 새 비밀번호로 덮어쓸 수 있는지 무제한으로 시도할 수 있었다.
    # /login과 같은 in-process limiter를 재사용하되 키를 분리해(사용자 단위) 로그인
    # 시도 예산과 섞이지 않게 한다.
    limiter = request.app.state.login_ratelimiter
    change_pw_limit_key = f"change_password:{auth.user.id}"
    if not limiter.allow(change_pw_limit_key):
        raise RateLimitedError(
            "비밀번호 변경 시도가 너무 많습니다. 잠시 후 다시 시도하세요.",
            retry_after_seconds=limiter.retry_after_seconds(change_pw_limit_key),
        )

    current_password = data.current_password
    new_password = data.new_password

    user = auth.user
    if not verify_password(user.password_hash, current_password):
        # 반복된 '현재 비밀번호 틀림' 시도는 지금까지 감사 로그에 전혀 남지 않았다 —
        # /login 실패 경로(위 login())는 record_audit + 잠금 카운터를 쓰는데, 이미
        # 세션이 있는 이 엔드포인트(탈취/고정된 쿠키+CSRF만 있으면 본인 비밀번호를
        # 몰라도 새 비밀번호로 덮어쓸 수 있는지 시도할 수 있다)는 in-process 리미터
        # 말고는 방어·기록이 없었다. '누가 언제 실패했나'는 감사 화면의 존재 목적과
        # 일치하는 사건이다.
        record_audit(
            db, actor_id=user.id, action="user.password_change_failed",
            object_type="user", object_id=user.id, result="failure",
            client_ip=get_client_ip(request),
            request_id=getattr(request.state, "request_id", None),
        )
        db.commit()
        raise WrongCurrentPasswordError()
    policy = request.app.state.settings_cache.current_value("password_policy") or {}
    problems = validate_password_policy(
        new_password,
        min_length=policy.get("min_length", 12),
        min_classes=policy.get("min_classes", 3),
    )
    if new_password == current_password:
        problems.append("새 비밀번호는 기존 비밀번호와 달라야 합니다.")
    if problems:
        raise ValidationAppError("비밀번호 정책 위반", details=problems)

    user.password_hash = hash_password(new_password)
    user.must_change_password = False

    # Spec §11.3: 비밀번호 변경 시 모든 다른 세션 폐기 + 세션 회전.
    session_service.revoke_all_for_user(db, user.id)
    record, token = session_service.create(
        db,
        user,
        client_ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    # 자기 자신의 비밀번호 변경은 지금까지 감사 로그에 전혀 남지 않았다 — login()/logout()은
    # 이 파일에서 이미 record_audit를 부르는데(위 참조) change_password()만 빠져 있었다.
    # '언제 누가 비밀번호를 바꿨나'는 감사 화면의 존재 목적과 정확히 일치하는 사건이다.
    record_audit(
        db, actor_id=user.id, action="user.password_change_self", object_type="user",
        object_id=user.id, result="success", client_ip=get_client_ip(request),
        request_id=getattr(request.state, "request_id", None),
    )
    db.commit()

    response = JSONResponse({"ok": True, "csrf_token": record.csrf_token})
    set_session_cookie(response, token, settings, max_age=session_service.absolute_ttl())
    return response
