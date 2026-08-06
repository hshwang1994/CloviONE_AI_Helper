"""비밀번호 재설정 토큰의 발급과 소비 (9-9 P4).

## 원문은 이 함수의 반환값으로만 존재한다

``mint_token`` 은 원문을 **돌려주기만** 하고 DB 에는 SHA-256 해시만 남긴다. 그래서 원문을
아는 곳은 (1) 이 함수를 부른 워커의 메모리, (2) 메일 본문, (3) 사용자의 메일함 뿐이다.
세션 토큰(app/core/sessions.py)과 정확히 같은 규약이고, 이유도 같다: DB 백업 파일 하나가
전 계정 접근 권한이 되면 안 된다.

## 발급을 워커에서 하는 이유

웹에서 만들어 잡 payload 에 실으면 그 원문이 ``jobs.payload_json`` 에 평문으로 앉는다.
"평문 미저장" 을 한 곳(토큰 표)에서만 지키고 옆문으로 새게 하는 전형적인 실패다.
그래서 웹은 "누구에게 보낼지" 만 큐에 넣고, 원문은 발송 직전에 워커가 만든다
(app/mail/renderers.py). 덤으로 만료 시계가 **발송 시점**부터 도는 이점도 있다 - 큐가
밀렸다고 도착하자마자 만료된 링크를 받는 일이 없다.

## 소비는 한 번뿐

``consume_token`` 은 찾자마자 ``used_at`` 을 찍는다. 비밀번호 정책 검증보다 **먼저**
찍지 않는다 - 정책에 걸려 실패한 시도까지 토큰을 태우면, 오타 한 번에 메일을 다시 받아야
한다. 대신 비밀번호가 실제로 바뀌는 순간에 태운다(호출부가 순서를 지킨다).
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import RESET_PURPOSE_RESET, PasswordResetToken
from app.core.errors import AppError
from app.core.security import hash_token
from app.users.models import User

# 1시간. 짧으면 메일이 늦게 도착한 사람이 못 쓰고, 길면 메일함을 본 사람의 창이 넓어진다.
# 초대 메일은 사람이 며칠 뒤 열 수 있으므로 따로 길게 준다.
RESET_TOKEN_TTL_SECONDS = 3600
INVITE_TOKEN_TTL_SECONDS = 7 * 24 * 3600


class InvalidResetTokenError(AppError):
    """만료, 재사용, 존재하지 않음을 **하나의 답**으로 뭉친다.

    구별해서 알려 주면 "이 토큰은 이미 쓰였다" 가 곧 "그 주소에 계정이 있다" 는 뜻이 된다.
    사용자가 할 행동은 어느 경우든 같다: 다시 요청한다.
    """

    status_code = 400
    code = "invalid_reset_token"
    default_message = (
        "재설정 링크가 만료되었거나 이미 사용되었습니다. 다시 요청해 주세요."
    )


def new_reset_token() -> str:
    return secrets.token_urlsafe(32)  # 256 bits


def mint_token(
    db: Session,
    user: User,
    *,
    now: datetime,
    purpose: str = RESET_PURPOSE_RESET,
    ttl_seconds: int | None = None,
    client_ip: str | None = None,
) -> str:
    """새 토큰을 발급하고 **원문**을 돌려준다. DB 에는 해시만 들어간다.

    같은 사용자의 기존 미사용 토큰은 전부 태운다. 여러 장이 동시에 살아 있으면 "다시
    보내기" 를 누를 때마다 열린 창이 하나씩 늘어난다.
    """
    invalidate_open_tokens(db, user.id, now=now)
    ttl = ttl_seconds if ttl_seconds is not None else RESET_TOKEN_TTL_SECONDS
    raw = new_reset_token()
    row = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_token(raw),
        purpose=purpose,
        expires_at=now + timedelta(seconds=ttl),
        created_at=now,
        created_ip=client_ip,
    )
    db.add(row)
    db.flush()
    return raw


def invalidate_open_tokens(db: Session, user_id: str, *, now: datetime) -> int:
    rows = (
        db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.used_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        row.used_at = now
    if rows:
        db.flush()
    return len(rows)


def find_open_token(
    db: Session, raw_token: str, *, now: datetime
) -> tuple[PasswordResetToken, User]:
    """살아 있는 토큰과 그 주인을 찾는다. 아니면 InvalidResetTokenError.

    **조회 자체에 조건을 붙인다.** 먼저 꺼내 놓고 나중에 판정하면, 판정을 빠뜨린 새 경로가
    조용히 열린다(app/jobs/repository.py::get_in_scope 와 같은 원칙).
    """
    if not raw_token or not isinstance(raw_token, str):
        raise InvalidResetTokenError()
    row = db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == hash_token(raw_token),
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
    ).scalar_one_or_none()
    if row is None:
        raise InvalidResetTokenError()
    user = db.get(User, row.user_id)
    # 토큰이 나간 뒤 계정이 잠기거나 보관됐을 수 있다. 그 계정으로 다시 들어오게 하면
    # 관리자가 닫은 문을 메일 한 통이 다시 여는 셈이다.
    if user is None or not user.active or user.archived_at is not None:
        raise InvalidResetTokenError()
    return row, user


def burn(db: Session, row: PasswordResetToken, *, now: datetime) -> None:
    """실제로 비밀번호가 바뀌는 순간에만 부른다(모듈 docstring 참조)."""
    row.used_at = now
    db.flush()


def purge_expired(db: Session, *, now: datetime, keep_days: int = 30) -> int:
    """만료된 지 오래된 행을 지운다. 워커의 보존 정리가 부른다."""
    cutoff = now - timedelta(days=keep_days)
    rows = (
        db.execute(
            select(PasswordResetToken).where(PasswordResetToken.expires_at < cutoff)
        )
        .scalars()
        .all()
    )
    for row in rows:
        db.delete(row)
    if rows:
        db.flush()
    return len(rows)
