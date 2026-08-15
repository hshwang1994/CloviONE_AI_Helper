"""FastAPI dependencies: DB session, authentication, RBAC, CSRF, client IP.

Server-side RBAC is authoritative — UI hiding is never the control (spec §25.5).
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.auth.models import UserSession
from app.core.db import is_write_conflict
from app.core.errors import AppError, ForbiddenError, UnauthorizedError, WriteUnavailableError
from app.core.sessions import SESSION_COOKIE_NAME, SessionService
from app.users.models import User

logger = logging.getLogger("app.deps")

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class PasswordChangeRequiredError(AppError):
    status_code = 403
    code = "password_change_required"
    default_message = "비밀번호를 변경해야 계속 사용할 수 있습니다."


class CSRFError(AppError):
    status_code = 403
    code = "csrf_failed"
    default_message = "CSRF 토큰이 없거나 올바르지 않습니다."


class ImpersonationReadOnlyError(AppError):
    """임퍼소네이션 세션이 상태를 바꾸려 했다 (0033, PLAN Phase 6).

    **읽기 전용은 화면에서 버튼을 숨겨서 지키는 것이 아니다.** 숨긴 버튼은 fetch 한 줄이면
    되살아나고, 그 순간 감사 로그에는 대상 사용자가 한 것처럼 보이는 쓰기가 남는다.
    그래서 서버 한 곳(`get_current_auth`)에서 **모든 안전하지 않은 메서드**를 막는다.
    """

    status_code = 403
    code = "impersonation_read_only"
    default_message = "임퍼소네이션 중에는 읽기만 할 수 있습니다."


class PageAuthRequired(Exception):
    """Raised by HTML page routes; handled with a redirect to /login."""


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: UserSession
    # 임퍼소네이션 중이면 '실제로 요청을 낸 사람'(관리자). 평소에는 None 이고,
    # 그때 actor == user 다. 감사 로그의 행위자는 **언제나 actor** 여야 한다.
    actor: User | None = None

    @property
    def impersonating(self) -> bool:
        return self.actor is not None

    @property
    def audit_actor(self) -> User:
        """감사·권한 판단의 주체. 임퍼소네이션 중에도 관리자 자신이다."""
        return self.actor or self.user


def get_db(request: Request) -> Iterator[Session]:
    """D-75: the route handler's own writes already go through the SAVEPOINT
    retry layer (`app/core/db.py`) at call sites that use it — this function's
    own commit, after the handler has already returned successfully, has no
    retry of its own. A busy/locked failure *here* can't be safely retried by
    just calling `db.commit()` again (SQLAlchemy rolls back on a failed
    commit, so whatever was flushed is already gone) — a real retry would mean
    re-running the whole request, which this dependency doesn't do. So this
    only classifies the failure into a clean, retryable-by-the-user response
    instead of leaking a raw 500 (`docs/DECISIONS.md` D-75).

    The `except (IntegrityError, OperationalError)` below only wraps the
    commit itself (via the `else` clause, which runs only when `yield db`
    raised nothing) — an exception raised by the handler's own business logic
    still hits the plain `except Exception` below unchanged, so a genuine
    (non-transient) `IntegrityError` from inside a route still surfaces as
    whatever that route already turns it into, not as a 503.
    """
    factory = request.app.state.session_factory
    db = factory()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    else:
        try:
            db.commit()
        except (IntegrityError, OperationalError) as exc:
            db.rollback()
            if not is_write_conflict(exc):
                raise
            logger.exception(
                "get_db outer commit hit write conflict request_id=%s",
                getattr(request.state, "request_id", None),
            )
            raise WriteUnavailableError() from exc
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
    # 조직 정지(X5)도 같은 자리에서 막는다. 정지 시 세션을 폐기하지만, 그 폐기 하나에
    # 차단 전부를 걸어 두면 세션이 다른 경로로 만들어지는 순간 정지가 무력해진다 —
    # 바로 위 보관 계정과 똑같은 이유다.
    from app.org.service import is_blocked_by_org_suspension

    if is_blocked_by_org_suspension(db, user):
        return None
    if record.impersonated_user_id:
        return _impersonated_auth(request, db, record, user)
    return AuthContext(user=user, session=record)


# 임퍼소네이션 중에도 통과해야 하는 쓰기 경로. 이 둘까지 막으면 관리자가 임퍼소네이션에서
# **빠져나올 수 없다**(로그아웃도 POST 다).
#
# 두 가지를 테스트가 못박는다(tests/security/test_impersonation.py):
#   1. 이 집합이 늘어나지 않았는가 — 하나 더 넣는 것은 곧 예외를 하나 더 뚫는 것이다.
#   2. 여기 적힌 경로가 **실제로 존재하는 라우트인가** — 없어진 경로가 남아 있으면, 나중에
#      누가 그 경로를 다시 만드는 날 아무도 모르게 열린 채로 태어난다.
IMPERSONATION_ALLOWED_WRITES = frozenset(
    {"/api/admin/impersonation/stop", "/logout"}
)


def _impersonated_auth(
    request: Request, db: Session, record: UserSession, actor: User
) -> AuthContext | None:
    """임퍼소네이션 세션의 인증 문맥 — 대상의 눈으로 읽되, 행위자는 관리자다.

    대상이 그 사이에 비활성/보관됐거나 최대 지속 시간을 넘었으면 **임퍼소네이션만 끝내고**
    관리자 자신의 세션으로 되돌린다. 여기서 `None`(=401)을 돌려주면 관리자가 자기 세션까지
    잃는다 — 남의 계정이 잠겼다는 이유로 내가 로그아웃되는 것은 말이 안 된다.
    """
    from app.impersonation import service as imp_service
    from app.impersonation.models import ImpersonationSession

    now = request.app.state.clock.now()
    row = (
        db.get(ImpersonationSession, record.impersonation_id)
        if record.impersonation_id
        else None
    )
    if row is None:
        # CORE-09: `record.impersonation_id`가 비어 있거나 낡았으면(그 자체가 이미
        # `imp_service.end()`가 이 폴백을 두는 이유다) `row is not None and expired(...)`가
        # 통째로 건너뛰어져 **최대 지속 시간(30분) 검사가 무력화**된다 — 세션의 절대 TTL
        # (8시간)까지 임퍼소네이션이 그대로 이어질 수 있었다. `end()`와 같은 방식으로
        # session_id 기준 조회를 한 번 더 시도한다.
        row = imp_service.active_for_session(db, record.id)
    target = db.get(User, record.impersonated_user_id)
    unavailable = (
        target is None or not target.active or target.archived_at is not None
    )
    if unavailable or (row is not None and imp_service.expired(row, now)):
        # UB-17: 수동 종료(impersonation/router.py::stop_impersonation)·로그아웃 종료
        # (auth/router.py::logout, UB-03)는 이미 감사에 남는데 이 자동 종료 경로만
        # 빠져 있었다 — service.py 모듈 docstring 규칙 2("감사 필수")가 이 경로에도
        # 그대로 적용된다. request.state.actor 는 아직 안 채워진 시점(_load_auth 가
        # 이 함수를 부르는 도중)이라 record_audit_from_request 대신 이 함수의 실제
        # actor 인자를 직접 쓴다.
        from app.core.audit import record_audit

        ended = imp_service.end(
            db,
            session=record,
            now=now,
            reason=imp_service.END_TARGET_UNAVAILABLE if unavailable else imp_service.END_EXPIRED,
        )
        if ended is not None:
            record_audit(
                db,
                actor_id=actor.id,
                action="impersonation.stop",
                object_type="user",
                object_id=ended.target_user_id,
                after={
                    "impersonation_id": ended.id,
                    "ended_reason": ended.ended_reason,
                    "duration_seconds": int(
                        (ended.ended_at - ended.started_at).total_seconds()
                    ),
                    "blocked_write_count": ended.blocked_write_count,
                },
                client_ip=client_ip_from_request(request),
            )
        return AuthContext(user=actor, session=record)
    return AuthContext(user=target, session=record, actor=actor)


def get_current_auth(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    """Authenticated context. Allowed even when must_change_password is set —
    use ``get_current_user`` for everything except login/logout/change-password/me.

    **임퍼소네이션 쓰기 차단이 여기에 있는 이유**: 모든 인증 라우트가 이 의존성을 지난다
    (`get_current_user`·`require_roles`·`require_csrf`·`get_principal` 이 전부 여기서
    파생된다). 라우터마다 걸면 새 라우터에서 빠뜨리고, 그 라우터만 조용히 뚫린다 —
    CSRF 커버리지 테스트가 잡아낸 것과 정확히 같은 종류의 결함이다.
    """
    auth = _load_auth(request, db)
    if auth is None:
        raise UnauthorizedError()
    request.state.user = auth.user
    request.state.session = auth.session
    request.state.actor = auth.audit_actor
    if auth.impersonating:
        _guard_impersonation_write(request, db, auth)
    return auth


def _guard_impersonation_write(request: Request, db: Session, auth: AuthContext) -> None:
    if request.method in SAFE_METHODS:
        return
    if request.url.path in IMPERSONATION_ALLOWED_WRITES:
        return
    # 막힌 시도는 세어 둔다. 0이 아니면 그 관리자는 읽기 전용 세션에서 쓰기를 시도했고,
    # 그 사실은 감사가 알아야 한다(실수든 아니든).
    #
    # **별도 세션을 쓰는 이유**: 바로 아래에서 예외를 던지면 `get_db` 가 요청 세션을
    # 롤백한다 — 같은 세션에 세어 두면 그 숫자도 함께 사라져 언제나 0이 된다(실제로
    # 그렇게 만들었다가 테스트에서 잡혔다). 기록 실패가 차단을 막아서도 안 되므로
    # 예외는 전부 삼킨다: 세지 못한 것이 뚫린 것보다는 낫다.
    if auth.session.impersonation_id:
        _count_blocked_write(request, auth.session.impersonation_id)
    raise ImpersonationReadOnlyError()


def _count_blocked_write(request: Request, impersonation_id: str) -> None:
    from app.impersonation.models import ImpersonationSession

    try:
        factory = request.app.state.session_factory
        with factory() as side:
            row = side.get(ImpersonationSession, impersonation_id)
            if row is not None:
                row.blocked_write_count = (row.blocked_write_count or 0) + 1
                side.commit()
    except Exception:  # noqa: BLE001 — 세지 못한 것이 차단을 무르게 하면 안 된다
        pass


def get_current_user(auth: AuthContext = Depends(get_current_auth)) -> User:
    # 임퍼소네이션 중에는 대상의 must_change_password 로 막지 않는다. 읽기만 가능하므로
    # 위험이 없고, 막으면 "비밀번호를 못 바꾼 계정은 지원할 수 없다"는 이상한 구멍이 생긴다.
    if auth.user.must_change_password and not auth.impersonating:
        raise PasswordChangeRequiredError()
    return auth.user


def get_page_auth(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    """Like get_current_auth but for HTML pages: unauthenticated → /login redirect.

    CORE-08: `get_current_auth`'s own docstring explains exactly why the
    impersonation write-guard and `request.state.actor` live in one shared
    place instead of on each router — a new call site that skips this
    function silently reopens the write bypass. This one did: it duplicated
    the auth-loading logic but left both out. Harmless today only because
    every current caller is a GET page route; the first POST page route
    built on this dependency would let an impersonated session write with
    the audit trail attributed to the *target*, not the actor.
    """
    auth = _load_auth(request, db)
    if auth is None:
        raise PageAuthRequired()
    request.state.user = auth.user
    request.state.session = auth.session
    request.state.actor = auth.audit_actor
    if auth.impersonating:
        _guard_impersonation_write(request, db, auth)
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
