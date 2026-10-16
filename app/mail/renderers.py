"""메일 본문을 **발송 직전에** 만든다 (9-9 P4).

## 왜 본문을 미리 만들지 않는가

비밀번호 재설정과 초대 메일에는 1회용 토큰이 들어간다. 본문을 웹에서 만들어 잡 payload
(또는 아웃박스 행)에 실으면 그 토큰 원문이 DB 에 평문으로 앉는다 - 토큰 표에서 해시만
저장하며 지킨 규칙을 옆문으로 무너뜨리는 것이다. 그래서 아웃박스에는 ``kind`` 와
비밀 아닌 ``params`` 만 두고, 원문은 이 파일이 워커 안에서 만든다.

## 링크가 가리키는 화면은 실제로 있다

`/reset-password` 는 app/auth/reset_router.py 가 서버 렌더로 내는 진짜 페이지다.
없는 주소를 메일에 적는 것은 "없는 것을 있는 척 그리는" 것과 같다.

## 내용과 모양 (D-549)

여기서는 종류마다 **재료**(사람 이름 · 토큰 링크 · 시각)를 모아 `app/mail/content.py` 의 내용 함수에 넘기고, 틀 두 벌이
평문과 HTML 을 그린다(`render_mail`). 미리 보기(`app/mail/samples.py`)도 같은 내용 함수를 쓴다.
"""

from __future__ import annotations

import json
import re
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
# 화면 알림을 메일로도 보낸 것(계획 3.4, D-514). 본문은 그 알림의 제목과 내용, 그리고 바로 가는 주소다.
KIND_NOTIFICATION = "notification"
# 알림 받을 주소의 확인 코드(M4 · D-550). 코드는 워커가 그릴 때 만든다 - DB · 잡 · params 에 평문이 없다.
KIND_NOTIFY_EMAIL_VERIFICATION = "notify_email_verification"

# 화면이 `backup_failed` 를 그대로 보여 주면 그건 메일 종류의 이름이 아니라 우리 내부
# 코드다(지시 36 · 40). 상태값을 서버가 이름 지어 주는 것과 같은 이유로 종류도 여기서
# 이름을 준다 - 화면이 스스로 사전을 들면 종류가 하나 늘 때마다 raw 키가 샌다
# (app/mail/models.py 의 MAIL_STATUS_LABELS 주석 참조).
# 계정 보안 메일(D-562) - 사용자 선택과 무관하게 본인에게 간다. 종류 키는 알림 유형과 같다(사건 하나에 이름 하나).
KIND_ACCOUNT_LOCKED = "account_locked"
KIND_PASSWORD_CHANGE_REQUIRED = "password_change_required"
SECURITY_KINDS = frozenset({KIND_ACCOUNT_LOCKED, KIND_PASSWORD_CHANGE_REQUIRED})

MAIL_KIND_LABELS: dict[str, str] = {
    KIND_PASSWORD_RESET: "비밀번호 재설정",
    KIND_INVITE: "계정 초대",
    KIND_BACKUP_FAILED: "백업 실패 알림",
    KIND_APPROVAL_REQUESTED: "승인 요청 알림",
    KIND_TEST: "시험 메일",
    KIND_NOTIFICATION: "알림 메일",
    KIND_NOTIFY_EMAIL_VERIFICATION: "주소 확인 코드",
    KIND_ACCOUNT_LOCKED: "계정 잠금 안내",
    KIND_PASSWORD_CHANGE_REQUIRED: "비밀번호 변경 안내",
}


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


def _product(db: Session) -> str:
    from app.mail.content import product_name

    return product_name(db)


def _content_password_reset(db: Session, delivery: MailDelivery, ctx):
    from app.mail.content import password_reset_content

    user = _require_user(db, _params(delivery))
    now: datetime = ctx.clock.now()
    token = mint_token(db, user, now=now, purpose=RESET_PURPOSE_RESET)
    return password_reset_content(
        product=_product(db), base_url=_base_url(ctx), subject=delivery.subject, name=user.display_name,
        link=_reset_link(ctx, token), hours=_hours(RESET_TOKEN_TTL_SECONDS),
    )


def _content_invite(db: Session, delivery: MailDelivery, ctx):
    from app.mail.content import invite_content

    user = _require_user(db, _params(delivery))
    now: datetime = ctx.clock.now()
    token = mint_token(
        db,
        user,
        now=now,
        purpose=RESET_PURPOSE_INVITE,
        ttl_seconds=INVITE_TOKEN_TTL_SECONDS,
    )
    return invite_content(
        product=_product(db), base_url=_base_url(ctx), subject=delivery.subject, name=user.display_name,
        email=user.email, link=_reset_link(ctx, token), days=max(1, INVITE_TOKEN_TTL_SECONDS // 86400),
    )


def _content_backup_failed(db: Session, delivery: MailDelivery, ctx):
    from app.mail.content import backup_failed_content

    params = _params(delivery)
    return backup_failed_content(
        product=_product(db), base_url=_base_url(ctx), subject=delivery.subject, at=params.get("at"),
        reason=params.get("reason"),
    )


_KEY_SHAPE = re.compile(r"^[a-z_]+(\.[a-z_]+)+$")


def approval_type_label(request_type: str | None) -> str:
    """승인 요청 유형의 이름. 이름을 모르는 유형은 유형 키(`approval.ai_document` 같은)를 싣지 않고 「승인 요청」이다."""
    from app.approvals.service import request_type_label

    raw = str(request_type or "")
    label = request_type_label(raw)
    return "승인 요청" if not label or label == raw or _KEY_SHAPE.match(label) else label


def _object_label(object_type: str | None) -> str:
    from app.approvals.service import _object_type_ko

    raw = str(object_type or "")
    label = _object_type_ko(raw)
    return "-" if not label or label == raw or _KEY_SHAPE.match(label) else label


def _content_approval_requested(db: Session, delivery: MailDelivery, ctx):
    from app.mail.content import approval_requested_content

    params = _params(delivery)
    return approval_requested_content(
        product=_product(db), base_url=_base_url(ctx), subject=delivery.subject,
        type_label=approval_type_label(params.get("request_type")),
        requester=str(params.get("requested_by") or "알 수 없음"),
        target=_object_label(params.get("object_type")),
        approval_id=params.get("approval_id"),
    )


SECURITY_LABELS = {"none": "사용 안 함", "starttls": "STARTTLS", "ssl": "SSL"}
MODE_LABELS = {"external": "외부 SMTP 사용", "local_relay": "ClovirAssist 로컬 릴레이"}


def _content_test(db: Session, delivery: MailDelivery, ctx):
    from app.mail.config import config_from_db
    from app.mail.content import test_content

    config = config_from_db(db)
    mode = getattr(config, "mode", "external")
    if getattr(config, "local_relay", False):
        # 로컬 릴레이는 외부 SMTP 값(서버 · 보안 연결)이 없다 - 이 서버의 릴레이와 전달 방식이 사실이다.
        relay = config.relay
        if relay.delivery == "direct":
            delivery_label = "인터넷으로 직접 전달"
        else:
            sh = relay.smarthost
            delivery_label = f"상위 SMTP {sh.host}:{sh.port} 이용" if sh.host else "상위 SMTP 이용"
        return test_content(
            product=_product(db), base_url=_base_url(ctx), subject=delivery.subject, sent_at=ctx.clock.now(),
            server="이 서버의 로컬 릴레이", security_label="", mode_label=MODE_LABELS[mode], delivery_label=delivery_label,
        )
    return test_content(
        product=_product(db), base_url=_base_url(ctx), subject=delivery.subject, sent_at=ctx.clock.now(),
        server=f"{config.host}:{config.port}" if config.host else "-",
        security_label=SECURITY_LABELS.get(config.security, config.security),
        mode_label=MODE_LABELS.get(mode, MODE_LABELS["external"]),
    )


def _notification_link(ctx, params: dict) -> str:
    """알림이 가리키는 화면. 관리자 알림은 관리 콘솔(`/admin`)에서, 나머지는 사용자 콘솔에서 연다."""
    base = _base_url(ctx)
    admin = params.get("audience") == "admin"
    route = str(params.get("route") or "") or ("/admin-notifications" if admin else "/notifications")
    return f"{base}/admin#{route}" if admin else f"{base}/#{route}"


def _content_notification(db: Session, delivery: MailDelivery, ctx):
    """알림 한 건을 메일로 옮긴다. 받는 사람 사정과 사건의 유효성은 보내기 전에 이미 다시 봤다(`mail_send`)."""
    from app.mail.content import notification_content
    from app.profiles.prefs import NOTIFICATION_TYPES

    params = _params(delivery)
    user = _require_user(db, params)
    type_ = str(params.get("type") or "")
    return notification_content(
        product=_product(db), base_url=_base_url(ctx), subject=delivery.subject, name=user.display_name,
        type_=type_, title=str(params.get("title") or ""), body=str(params.get("body") or ""),
        link=_notification_link(ctx, params), type_label=(NOTIFICATION_TYPES.get(type_) or ("알림",))[0],
        first_assignment=bool(params.get("first_assignment")),
    )


def _content_notify_verification(db: Session, delivery: MailDelivery, ctx):
    """알림 받을 주소의 확인 코드(M4 · D-550). 코드는 **지금** 만들어 HMAC 만 남긴다 - 평문은 이 메일 본문에만 산다. 발송이
    실패하면 이 트랜잭션과 함께 되감기고, 다음 시도가 새 코드를 만든다."""
    from app.mail.content import verification_code_content
    from app.profiles.notify_email import CODE_MINUTES, mint_for_mail

    params = _params(delivery)
    user = _require_user(db, params)
    _email, code = mint_for_mail(
        db, str(params.get("verification_id") or ""), now=ctx.clock.now(),
        secret=str(getattr(ctx.settings, "session_secret", "") or ""),
    )
    return verification_code_content(
        product=_product(db), base_url=_base_url(ctx), subject=delivery.subject, name=user.display_name, code=code,
        minutes=CODE_MINUTES,
    )


def _content_security(db: Session, delivery: MailDelivery, ctx):
    """계정 잠금 · 비밀번호 변경 요청(D-562). 임시 비밀번호 · 링크 토큰은 싣지 않는다 - 알림의 제목과 본문 문장만이다."""
    from app.mail.content import security_content

    params = _params(delivery)
    user = _require_user(db, params)
    return security_content(
        product=_product(db), base_url=_base_url(ctx), subject=delivery.subject, name=user.display_name,
        type_=delivery.kind, title=str(params.get("title") or ""), body=str(params.get("body") or ""),
        at=params.get("at") or delivery.created_at,
    )


# kind 하나에 내용 함수 하나. 여기 없는 kind 는 발송 자체가 거부된다 - 오타 난 kind 가
# 조용히 빈 메일로 나가는 것보다, 잡이 영구 실패로 남아 눈에 띄는 편이 낫다.
CONTENT_BUILDERS = {
    KIND_PASSWORD_RESET: _content_password_reset,
    KIND_INVITE: _content_invite,
    KIND_BACKUP_FAILED: _content_backup_failed,
    KIND_APPROVAL_REQUESTED: _content_approval_requested,
    KIND_TEST: _content_test,
    KIND_NOTIFICATION: _content_notification,
    KIND_NOTIFY_EMAIL_VERIFICATION: _content_notify_verification,
    KIND_ACCOUNT_LOCKED: _content_security,
    KIND_PASSWORD_CHANGE_REQUIRED: _content_security,
}

MAIL_KINDS = frozenset(CONTENT_BUILDERS)


def render_mail(db: Session, delivery: MailDelivery, ctx):
    """보낼 메일 한 통 — (제목, 평문, HTML). 토큰은 여기서 만들어져 이 트랜잭션 안에만 산다(머리말)."""
    from app.mail.content import render, support_email

    builder = CONTENT_BUILDERS.get(delivery.kind)
    if builder is None:
        raise PermanentJobError(f"등록되지 않은 메일 유형입니다: {delivery.kind}")
    content = builder(db, delivery, ctx)
    content.support_email = support_email(db)
    return render(content)


def render_body(db: Session, delivery: MailDelivery, ctx) -> str:
    """평문 본문만(옛 호출부 · 시험용). 실제 발송은 `render_mail` 이 두 부분을 함께 만든다."""
    return render_mail(db, delivery, ctx).text
