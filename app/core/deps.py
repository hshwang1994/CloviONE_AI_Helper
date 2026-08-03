"""FastAPI dependencies: DB session, authentication, RBAC, CSRF, client IP.

Server-side RBAC is authoritative — UI hiding is never the control (spec §25.5).
"""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.auth.models import UserSession
from app.core.errors import AppError, ForbiddenError, UnauthorizedError
from app.core.sessions import SESSION_COOKIE_NAME, SessionService
from app.users.models import User

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class PasswordChangeRequiredError(AppError):
    status_code = 403
    code = "password_change_required"
    default_message = "비밀번호를 변경해야 계속 사용할 수 있습니다."


class CSRFError(AppError):
    status_code = 403
    code = "csrf_failed"
    default_message = "CSRF 토큰이 없거나 올바르지 않습니다."


class PageAuthRequired(Exception):
    """Raised by HTML page routes; handled with a redirect to /login."""


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: UserSession


def get_db(request: Request) -> Iterator[Session]:
    factory = request.app.state.session_factory
    db = factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _load_auth(request: Request, db: Session) -> AuthContext | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    service: SessionService = request.app.state.session_service
    record = service.validate(db, token)
    if record is None:
        return None
    user = db.get(User, record.user_id)
    # 보관된 계정은 비활성 계정과 똑같이 세션이 통하지 않아야 한다. archive_user가 이미
    # 세션을 폐기하지만, 그 폐기 하나에 계정 차단 전부를 걸어 두면 세션이 다른 경로로
    # 만들어지는 순간(또는 폐기가 한 번 실패하는 순간) 보관이 무력해진다 — 여기서도 막는다.
    if user is None or not user.active or user.archived_at is not None:
        return None
    return AuthContext(user=user, session=record)


def get_current_auth(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    """Authenticated context. Allowed even when must_change_password is set —
    use ``get_current_user`` for everything except login/logout/change-password/me."""
    auth = _load_auth(request, db)
    if auth is None:
        raise UnauthorizedError()
    request.state.user = auth.user
    request.state.session = auth.session
    return auth


def get_current_user(auth: AuthContext = Depends(get_current_auth)) -> User:
    if auth.user.must_change_password:
        raise PasswordChangeRequiredError()
    return auth.user


def get_page_auth(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    """Like get_current_auth but for HTML pages: unauthenticated → /login redirect."""
    auth = _load_auth(request, db)
    if auth is None:
        raise PageAuthRequired()
    request.state.user = auth.user
    request.state.session = auth.session
    return auth


def require_roles(*roles: str):
    allowed = frozenset(roles)

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise ForbiddenError()
        return user

    return dependency


def get_principal(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """요청 주체 + 그 주체의 **범위**(app/core/scope.py).

    역할 게이트(`require_roles`)와 짝을 이룬다: 역할은 '무엇을 할 수 있는가', 범위는
    '누구에게 할 수 있는가'. 부서 트리를 한 번 전개해야 하므로 요청당 한 번만 만들고
    `request.state.principal` 에 남겨 둔다(감사·로깅이 다시 계산하지 않게).
    """
    from app.core.scope import principal_from_user

    principal = principal_from_user(db, user)
    request.state.principal = principal
    return principal


def require_csrf(request: Request, auth: AuthContext = Depends(get_current_auth)) -> None:
    if request.method in SAFE_METHODS:
        return
    supplied = request.headers.get("X-CSRF-Token", "")
    if not supplied or not secrets.compare_digest(supplied, auth.session.csrf_token):
        raise CSRFError()


def client_ip_from_request(request: Request) -> str:
    """Real client IP. Only trust proxy headers when the immediate peer IS the
    trusted proxy, and then take the RIGHTMOST X-Forwarded-For entry (the one
    the trusted proxy itself appended) — the leftmost entries are client-supplied
    and spoofable. Prefer X-Real-IP (nginx sets it to $remote_addr)."""
    settings = request.app.state.settings
    client_host = request.client.host if request.client else ""
    if client_host == settings.trusted_proxy:
        real_ip = request.headers.get("X-Real-IP", "").strip()
        if real_ip:
            return real_ip
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            # Rightmost = appended by the trusted proxy; unspoofable.
            return forwarded.split(",")[-1].strip()
    return client_host


# Backwards-compatible alias used across routers.
def get_client_ip(request: Request) -> str:
    return client_ip_from_request(request)
