"""Session lifecycle: create, validate (idle + absolute timeout), rotate, revoke.

Spec §11.3, §25.1: Secure/HttpOnly/SameSite=Strict cookie, rotation on login
and password change, idle timeout 30m, absolute timeout 8h.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Callable

from fastapi import Response
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.auth.models import UserSession
from app.core.clock import Clock
from app.core.config import Settings
from app.core.db import is_write_conflict
from app.core.security import hash_token, new_csrf_token, new_session_token
from app.users.models import User

SESSION_COOKIE_NAME = "clovirone_session"

# last_seen_at writes are throttled to limit write amplification on SQLite.
_LAST_SEEN_WRITE_INTERVAL_SECONDS = 60

# validate() 안의 세 커밋(만료 revoke ×2, last_seen_at 스로틀 갱신)은 전부 인증 판단
# 자체가 아니라 부수 효과다 — record/None을 뭘 돌려줄지는 이미 메모리 위에서 결정이
# 끝나 있다. 이 커밋이 동시 요청의 다른 세션 쓰기와 SQLite 쓰기 충돌을 일으키면, 예전
# 코드는 그 OperationalError("database is locked")를 그대로 올려 get_db(deps.py)의
# 마지막 커밋까지 번지게 했다 — 그 결과 인증만 확인하면 끝인 순수 조회 API(예:
# GET /api/notifications/unread-count, GET /api/team-chat/rooms — 사실상 인증이 걸린
# 모든 API)까지 500이 났다(실측: QA 하네스 동시 접속 중 두 API 모두 이 UPDATE에서
# "database is locked", request_id a2666aa6/5fbacfb3, 2026-08-11 23:58:48). 기존
# `is_write_conflict()` 재시도 관용(app/core/versioning.py 등 13곳)을 그대로 쓰되,
# 여기서는 다 실패해도 예외를 올리지 않고 그냥 넘어간다 — revoke는 이미 만료로 판단해
# None을 돌려줄 참이었고, last_seen_at은 60초 스로틀 창이 이미 지연을 허용한다. 무관한
# OperationalError(디스크 오류 등)는 여전히 그대로 올린다(is_write_conflict 문서 참고).
_SIDE_EFFECT_COMMIT_ATTEMPTS = 2


def _commit_best_effort(db: Session, apply: Callable[[], None]) -> None:
    for attempt in range(_SIDE_EFFECT_COMMIT_ATTEMPTS):
        apply()
        try:
            db.commit()
            return
        except (IntegrityError, OperationalError) as exc:
            db.rollback()
            if not is_write_conflict(exc):
                raise
            if attempt == _SIDE_EFFECT_COMMIT_ATTEMPTS - 1:
                return


class SessionService:
    def __init__(self, settings: Settings, clock: Clock, settings_cache=None) -> None:
        self._settings = settings
        self._clock = clock
        # Optional effective-settings cache: session_policy overrides env values.
        self._cache = settings_cache

    def absolute_ttl(self) -> int:
        """Effective absolute session TTL (session_policy override or env default)."""
        if self._cache is not None:
            policy = self._cache.current_value("session_policy") or {}
            v = policy.get("absolute_timeout_seconds")
            if isinstance(v, int) and v >= 60:
                return v
        return self._settings.session_ttl_seconds

    # Backwards-compatible internal alias.
    _absolute_ttl = absolute_ttl

    def _idle_timeout(self) -> int:
        if self._cache is not None:
            policy = self._cache.current_value("session_policy") or {}
            v = policy.get("idle_timeout_seconds")
            if isinstance(v, int) and v >= 60:
                return v
        return self._settings.session_idle_timeout_seconds

    def create(
        self,
        db: Session,
        user: User,
        *,
        client_ip: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[UserSession, str]:
        token = new_session_token()
        now = self._clock.now()
        record = UserSession(
            token_hash=hash_token(token),
            user_id=user.id,
            csrf_token=new_csrf_token(),
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(seconds=self._absolute_ttl()),
            client_ip=client_ip,
            user_agent=(user_agent or "")[:255] or None,
        )
        db.add(record)
        db.flush()
        return record, token

    def validate(self, db: Session, token: str) -> UserSession | None:
        record = db.execute(
            select(UserSession).where(
                UserSession.token_hash == hash_token(token),
                UserSession.revoked_at.is_(None),
            )
        ).scalar_one_or_none()
        if record is None:
            return None

        now = self._clock.now()
        if record.expires_at <= now:
            # CORE-02: 이 뒤 호출자는 None을 UnauthorizedError로 바꿔 던지고,
            # get_db(deps.py)의 except 절이 그 요청 세션 전체를 롤백한다 — 커밋
            # 안 된 이 쓰기도 함께 사라져 만료된 세션이 profiles 화면에
            # 영원히 "활성"으로 남았다(retention도 정리 대상에서 빠뜨렸다).
            # 예외로 번지기 전에 여기서 직접 커밋해 그 롤백을 피한다.
            _commit_best_effort(db, lambda: setattr(record, "revoked_at", now))
            return None
        idle_deadline = record.last_seen_at + timedelta(seconds=self._idle_timeout())
        if idle_deadline <= now:
            _commit_best_effort(db, lambda: setattr(record, "revoked_at", now))
            return None

        if now - record.last_seen_at > timedelta(seconds=_LAST_SEEN_WRITE_INTERVAL_SECONDS):
            _commit_best_effort(db, lambda: setattr(record, "last_seen_at", now))
        return record

    def rotate(
        self,
        db: Session,
        current: UserSession,
        user: User,
        *,
        client_ip: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[UserSession, str]:
        self.revoke(db, current)
        return self.create(db, user, client_ip=client_ip, user_agent=user_agent)

    def revoke(self, db: Session, record: UserSession) -> None:
        if record.revoked_at is None:
            record.revoked_at = self._clock.now()

    def revoke_all_for_user(
        self, db: Session, user_id: str, *, except_session_id: str | None = None
    ) -> int:
        stmt = (
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=self._clock.now())
        )
        if except_session_id is not None:
            stmt = stmt.where(UserSession.id != except_session_id)
        result = db.execute(stmt)
        return result.rowcount or 0


def set_session_cookie(
    response: Response, token: str, settings: Settings, *, max_age: int | None = None
) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=max_age if max_age is not None else settings.session_ttl_seconds,
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
