"""메일 본문을 **발송 직전에** 만든다 (9-9 P4).

## 왜 본문을 미리 만들지 않는가

비밀번호 재설정과 초대 메일에는 1회용 토큰이 들어간다. 본문을 웹에서 만들어 잡 payload
(또는 아웃박스 행)에 실으면 그 토큰 원문이 DB 에 평문으로 앉는다 - 토큰 표에서 해시만
저장하며 지킨 규칙을 옆문으로 무너뜨리는 것이다. 그래서 아웃박스에는 ``kind`` 와
비밀 아닌 ``params`` 만 두고, 원문은 이 파일이 워커 안에서 만든다.

## 링크가 가리키는 화면은 실제로 있다

`/reset-password` 는 app/auth/reset_router.py 가 서버 렌더로 내는 진짜 페이지다.
없는 주소를 메일에 적는 것은 "없는 것을 있는 척 그리는" 것과 같다.
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.auth.models import RESET_PURPOSE_INVITE, RESET_PURPOSE_RESET
from app.auth.reset_service import (
    INVITE_TOKEN_TTL_SECONDS,
    RESET_TOKEN_TTL_SECONDS,
    mint_token,
)
from app.jobs.exceptions import PermanentJobError
from app.mail.models import MailDelivery
from app.users.models import User

KIND_PASSWORD_RESET = "password_reset"
KIND_INVITE = "invite"
KIND_BACKUP_FAILED = "backup_failed"
KIND_APPROVAL_REQUESTED = "approval_requested"
KIND_TEST = "test"


def _params(delivery: MailDelivery) -> dict:
    try:
        value = json.loads(delivery.params_json or "{}")
    except ValueError as exc:
        raise PermanentJobError(f"메일 파라미터가 손상되었습니다: {exc}") from exc
    return value if isinstance(value, dict) else {}


def _base_url(ctx) -> str:
    return str(getattr(ctx.settings, "app_base_url", "") or "").rstrip("/")


def _reset_link(ctx, token: str) -> str:
    return f"{_base_url(ctx)}/reset-password?token={token}"


def _hours(seconds: int) -> int:
    return max(1, seconds // 3600)


def _require_user(db: Session, params: dict) -> User:
    user = db.get(User, params.get("user_id") or "")
    if user is None:
        # 계정이 사라진 뒤 큐에 남은 잡이다. 재시도해도 낫지 않는다.
        raise PermanentJobError("메일 대상 계정을 찾을 수 없습니다.")
    return user


def _render_password_reset(db: Session, delivery: MailDelivery, ctx) -> str:
    user = _require_user(db, _params(delivery))
    now: datetime = ctx.clock.now()
    token = mint_token(db, user, now=now, purpose=RESET_PURPOSE_RESET)
    return (
        f"{user.display_name}님, 비밀번호 재설정을 요청하셨습니다.\n\n"
        f"아래 주소에서 새 비밀번호를 설정하세요.\n"
        f"{_reset_link(ctx, token)}\n\n"
        f"이 링크는 {_hours(RESET_TOKEN_TTL_SECONDS)}시간 뒤에 만료되며 한 번만 사용할 수 있습니다.\n"
        "본인이 요청하지 않았다면 이 메일을 무시하세요. 비밀번호는 바뀌지 않습니다.\n"
    )


def _render_invite(db: Session, delivery: MailDelivery, ctx) -> str:
    user = _require_user(db, _params(delivery))
    now: datetime = ctx.clock.now()
    token = mint_token(
        db,
        user,
        now=now,
        purpose=RESET_PURPOSE_INVITE,
        ttl_seconds=INVITE_TOKEN_TTL_SECONDS,
    )
    days = max(1, INVITE_TOKEN_TTL_SECONDS // 86400)
    return (
        f"{user.display_name}님, 업무 포털 계정이 만들어졌습니다.\n\n"
        f"아래 주소에서 비밀번호를 직접 설정하신 뒤 로그인하세요.\n"
        f"{_reset_link(ctx, token)}\n\n"
        f"로그인 주소: {_base_url(ctx)}/login\n"
        f"계정(이메일): {user.email}\n\n"
        f"이 링크는 {days}일 뒤에 만료되며 한 번만 사용할 수 있습니다.\n"
        # 임시 비밀번호를 메일로 보내지 않는다는 사실을 사용자에게도 알린다 -
        # "비밀번호가 안 적혀 있다" 를 오류로 오해하지 않게.
        "임시 비밀번호는 메일로 보내지 않습니다.\n"
    )


def _render_backup_failed(db: Session, delivery: MailDelivery, ctx) -> str:
    params = _params(delivery)
    reason = str(params.get("reason") or "원인이 기록되지 않았습니다.")
    at = str(params.get("at") or "")
    return (
        "예약 백업이 실패했습니다.\n\n"
        f"발생 시각(UTC): {at}\n"
        f"내용: {reason}\n\n"
        "관리 콘솔의 백업 화면에서 상태를 확인하고, 디스크 용량과 권한을 점검하세요.\n"
        f"{_base_url(ctx)}/admin\n"
    )


def _render_approval_requested(db: Session, delivery: MailDelivery, ctx) -> str:
    params = _params(delivery)
    return (
        "결재할 승인 요청이 도착했습니다.\n\n"
        f"요청 유형: {params.get('request_type') or '알 수 없음'}\n"
        f"요청자: {params.get('requested_by') or '알 수 없음'}\n"
        f"대상: {params.get('object_type') or '알 수 없음'}\n\n"
        "관리 콘솔의 승인 화면에서 검토하세요.\n"
        f"{_base_url(ctx)}/admin\n"
    )


def _render_test(db: Session, delivery: MailDelivery, ctx) -> str:
    return (
        "메일 발송 설정이 정상입니다.\n\n"
        "이 메일은 관리 콘솔에서 보낸 시험 발송입니다. 받으셨다면 SMTP 설정이 "
        "실제로 동작한다는 뜻입니다.\n"
        f"{_base_url(ctx)}/admin\n"
    )


# kind 하나에 렌더러 하나. 여기 없는 kind 는 발송 자체가 거부된다 - 오타 난 kind 가
# 조용히 빈 메일로 나가는 것보다, 잡이 영구 실패로 남아 눈에 띄는 편이 낫다.
RENDERERS = {
    KIND_PASSWORD_RESET: _render_password_reset,
    KIND_INVITE: _render_invite,
    KIND_BACKUP_FAILED: _render_backup_failed,
    KIND_APPROVAL_REQUESTED: _render_approval_requested,
    KIND_TEST: _render_test,
}

MAIL_KINDS = frozenset(RENDERERS)


def render_body(db: Session, delivery: MailDelivery, ctx) -> str:
    renderer = RENDERERS.get(delivery.kind)
    if renderer is None:
        raise PermanentJobError(f"등록되지 않은 메일 유형입니다: {delivery.kind}")
    return renderer(db, delivery, ctx)
