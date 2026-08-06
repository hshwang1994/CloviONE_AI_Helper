"""사용자 스스로 하는 비밀번호 재설정 (9-9 P4).

## 왜 별도 파일인가

`app/auth/router.py` 는 로그인, 로그아웃, 비밀번호 변경이 들어 있는 이 저장소에서 가장
깨뜨리면 안 되는 파일이다(깨지면 아무도 못 들어온다). 새 기능을 그 안에 밀어 넣는 대신
옆에 둔다 - 저장소 규칙(작은 파일 다수)과도 맞고, 로그인 경로를 건드릴 일이 없다.

## 세 가지 규칙

1. **계정 열거 금지.** `POST /forgot-password` 는 계정이 있든 없든, 활성이든 아니든
   **똑같은 응답**을 준다. 사내망이라도 문제다: 누가 이 회사에 다니는지가 로그인 화면
   앞에서 새어 나간다. 실제 차이는 "메일이 나가는가" 뿐이고, 그건 응답에 안 보인다.
2. **설정이 없으면 없다고 한다.** SMTP 가 없으면 200 이 아니라 503 이다. 이 판정은
   계정 조회보다 **먼저** 한다 - 순서가 반대면 "설정 없음" 응답이 계정 존재 여부에
   따라 갈려서 1번이 무너진다.
3. **토큰은 1회용, 만료, 해시 저장.** 판정은 app/auth/reset_service.py 한 곳이다.

## JSON 과 no-JS 폼을 둘 다 받는 이유

로그인 화면과 같은 관용이다(app/auth/router.py::_is_json_request). 재설정 페이지는
비밀번호를 잃은 사람이 마지막으로 기대는 화면이라, JS 가 막히거나 실패해도 동작해야 한다.
그래서 페이지는 순수 서버 렌더 `<form>` 이고 스크립트가 하나도 없다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth.reset_service import InvalidResetTokenError, burn, find_open_token
from app.auth.router import _verify_login_origin
from app.core.audit import record_audit
from app.core.deps import get_client_ip, get_db
from app.core.errors import AppError, RateLimitedError, ValidationAppError
from app.core.security import hash_password, validate_password_policy
from app.mail.config import config_from_cache, configuration_problems
from app.mail.renderers import KIND_PASSWORD_RESET
from app.mail.service import queue_mail
from app.users.service import get_user_by_email, normalize_email

router = APIRouter(tags=["auth-reset"])

# 있든 없든 같은 답. 이 문자열이 계정 존재 여부와 무관하다는 사실이 규칙 1의 전부다.
NEUTRAL_REQUEST_MESSAGE = (
    "요청을 접수했습니다. 등록된 계정이라면 비밀번호 재설정 안내 메일이 발송됩니다. "
    "메일이 오지 않으면 스팸함을 확인하시고, 그래도 없으면 관리자에게 문의하세요."
)
RESET_DONE_MESSAGE = "비밀번호가 변경되었습니다. 새 비밀번호로 로그인하세요."


class MailNotConfiguredError(AppError):
    """이 서버는 메일을 보낼 수 없다.

    조용히 성공한 척하면 사용자는 오지 않을 메일을 며칠 기다린다. 계정 존재와 무관한
    **서버 상태**라 알려 줘도 열거에 쓰이지 않는다.
    """

    status_code = 503
    code = "mail_not_configured"
    default_message = (
        "이 서버는 메일 발송이 설정되어 있지 않아 재설정 메일을 보낼 수 없습니다. "
        "관리자에게 비밀번호 재발급을 요청하세요."
    )


def _is_json_request(request: Request) -> bool:
    return request.headers.get("content-type", "").startswith("application/json")


async def extract_body(request: Request) -> dict:
    """JSON 이든 form 이든 dict 로. 모양이 아니면 422.

    **의존성으로 두는 것이 계약이다.** 라우트 핸들러 자체는 반드시 sync `def` 여야 한다
    (불변 §1) - 여기서 `async def` 핸들러를 쓰면 Argon2 해싱과 sync SQLAlchemy 가
    이벤트 루프 위에서 돌아 앱 전체가 멈춘다. 본문 파싱만 루프에서 먼저 하고 핸들러는
    스레드풀에서 돈다. `app/auth/router.py::_extract_credentials` 와 같은 구조다.

    같은 파일의 `_extract_credentials` 와 같은 이유로 dict 여부를 확인한다 - 유효
    JSON 이지만 객체가 아닌 본문(`[1,2]`, `"x"`)에 `.get` 을 부르면 인증 없이도 500 을
    낼 수 있었다.
    """
    try:
        data = await request.json() if _is_json_request(request) else dict(await request.form())
    except Exception:
        raise ValidationAppError("요청 형식이 올바르지 않습니다.") from None
    if not isinstance(data, dict):
        raise ValidationAppError("요청 형식이 올바르지 않습니다.")
    return data


def _guard_rate(request: Request, bucket: str) -> None:
    """로그인과 같은 리미터, 다른 예산. 재설정 요청은 메일 폭탄의 도구가 될 수 있다."""
    limiter = request.app.state.login_ratelimiter
    key = f"{bucket}:{get_client_ip(request)}"
    if not limiter.allow(key):
        raise RateLimitedError(
            "요청이 너무 많습니다. 잠시 후 다시 시도하세요.",
            retry_after_seconds=limiter.retry_after_seconds(key),
        )


def mail_is_sendable(request: Request) -> bool:
    return not configuration_problems(
        config_from_cache(getattr(request.app.state, "settings_cache", None)),
        getattr(request.app.state, "secret_provider", None),
    )


def _page(request: Request, template: str, context: dict):
    branding = request.app.state.settings_cache.current_value("ui_branding") or {}
    return request.app.state.templates.TemplateResponse(
        request,
        template,
        {
            "app_name": branding.get("product_name", "ClovirAssist"),
            "support_email": branding.get("support_email"),
            **context,
        },
    )


@router.get("/forgot-password")
def forgot_password_page(request: Request):
    return _page(
        request,
        "forgot_password.html",
        {
            # 못 보내는 서버에서 폼만 그려 두면 사용자는 보내지도 못할 요청을 반복한다.
            "mail_available": mail_is_sendable(request),
            "notice": None,
            "error": None,
            "submitted_email": "",
        },
    )


@router.post("/forgot-password", dependencies=[Depends(_verify_login_origin)])
def request_password_reset(
    request: Request,
    data: dict = Depends(extract_body),
    db: Session = Depends(get_db),
):
    _guard_rate(request, "password_reset_request")

    # 규칙 2: 계정 조회보다 **먼저** 설정을 본다(모듈 docstring).
    if not mail_is_sendable(request):
        if _is_json_request(request):
            raise MailNotConfiguredError()
        return _page(
            request,
            "forgot_password.html",
            {
                "mail_available": False,
                "notice": None,
                "error": MailNotConfiguredError.default_message,
                "submitted_email": "",
            },
        )

    email = normalize_email(str(data.get("email", "")))
    now = request.app.state.clock.now()
    if email:
        user = get_user_by_email(db, email)
        # 비활성, 보관 계정에는 보내지 않는다 - 관리자가 닫은 문을 메일이 다시 열면 안 된다.
        # 그 사실은 응답에 드러나지 않는다(규칙 1).
        if user is not None and user.active and user.archived_at is None:
            queue_mail(
                db,
                kind=KIND_PASSWORD_RESET,
                to_email=user.email,
                subject="[ClovirAssist] 비밀번호 재설정 안내",
                params={"user_id": user.id},
                now=now,
                secret_provider=getattr(request.app.state, "secret_provider", None),
            )
            record_audit(
                db,
                actor_id=user.id,
                action="user.password_reset_requested",
                object_type="user",
                object_id=user.id,
                client_ip=get_client_ip(request),
                request_id=getattr(request.state, "request_id", None),
            )

    if _is_json_request(request):
        return JSONResponse({"ok": True, "message": NEUTRAL_REQUEST_MESSAGE})
    return _page(
        request,
        "forgot_password.html",
        {
            "mail_available": True,
            "notice": NEUTRAL_REQUEST_MESSAGE,
            "error": None,
            "submitted_email": "",
        },
    )


@router.get("/reset-password")
def reset_password_page(request: Request):
    token = str(request.query_params.get("token", ""))
    return _page(
        request,
        "reset_password.html",
        {
            "token": token,
            "error": None,
            "policy": request.app.state.settings_cache.current_value("password_policy") or {},
        },
    )


@router.post("/reset-password", dependencies=[Depends(_verify_login_origin)])
def confirm_password_reset(
    request: Request,
    data: dict = Depends(extract_body),
    db: Session = Depends(get_db),
):
    # sync 핸들러(불변 §1): Argon2 해싱이 스레드풀에서 돈다. 본문 파싱은 async 의존성
    # `extract_body` 가 이벤트 루프에서 먼저 처리한다.
    _guard_rate(request, "password_reset_confirm")

    token = str(data.get("token", ""))
    new_password = str(data.get("new_password", ""))
    policy = request.app.state.settings_cache.current_value("password_policy") or {}
    now = request.app.state.clock.now()

    try:
        row, user = find_open_token(db, token, now=now)
    except InvalidResetTokenError:
        if _is_json_request(request):
            raise
        return _page(
            request,
            "reset_password.html",
            {
                "token": token,
                "error": InvalidResetTokenError.default_message,
                "policy": policy,
            },
        )

    problems = validate_password_policy(
        new_password,
        min_length=policy.get("min_length", 12),
        min_classes=policy.get("min_classes", 3),
    )
    if problems:
        # 토큰은 태우지 않는다 - 오타 한 번에 메일을 다시 받아야 하면 아무도 못 쓴다.
        if _is_json_request(request):
            raise ValidationAppError("비밀번호 정책 위반", details=problems)
        return _page(
            request,
            "reset_password.html",
            {"token": token, "error": " ".join(problems), "policy": policy},
        )

    user.password_hash = hash_password(new_password)
    # 임시 비밀번호로 들어온 사람이 재설정을 끝냈으면 강제 변경 화면에 다시 가둘 이유가 없다.
    user.must_change_password = False
    user.failed_login_count = 0
    user.locked_until = None
    burn(db, row, now=now)

    # 비밀번호를 잃어버린 이유가 '털렸기 때문' 일 수 있다. 기존 세션을 전부 끊는다
    # (app/auth/router.py::change_password 와 같은 규칙, spec §11.3).
    request.app.state.session_service.revoke_all_for_user(db, user.id)
    record_audit(
        db,
        actor_id=user.id,
        action="user.password_reset",
        object_type="user",
        object_id=user.id,
        client_ip=get_client_ip(request),
        request_id=getattr(request.state, "request_id", None),
    )
    db.commit()

    if _is_json_request(request):
        return JSONResponse({"ok": True, "message": RESET_DONE_MESSAGE})
    return RedirectResponse("/login?reset=1", status_code=303)
