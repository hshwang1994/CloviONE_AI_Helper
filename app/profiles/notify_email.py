"""알림 받을 메일 주소 — 계정 주소가 기본이고, 다른 주소는 그 주소로 보낸 6자리 코드를 넣어야 쓴다 (계획 M4, D-550).

## 무엇을 지키는가

- 확인이 끝나기 전에는 새 주소로 업무 알림을 보내지 않는다. 그동안 알림은 계정 주소로 간다.
- 회사가 「허용 이메일 도메인」을 정했으면 그 도메인의 주소만 받는다. 확인한 주소가 나중에 허용 밖이 되면 그 주소로 보내지 않고
  계정 주소로 돌아간다(보내는 순간 다시 본다 - `resolve_address`).
- 코드는 **워커가 메일을 그릴 때** 만든다(재설정 토큰과 같은 원리, `app/mail/renderers.py`) - DB · 잡 payload · 발송 행 params 에
  평문이 없다. 저장하는 것은 `session_secret` HMAC 뿐이다. 코드는 그린 때부터 15분 동안 쓸 수 있다.
- 틀린 코드는 확인 한 건당 다섯 번까지다 - 자기 세션의 리미터(`RateLimiter`)가 세어 실패한 요청과 함께 되감기지 않는다. 확인 메일은
  사람당 15분에 3통이다.
- 링크가 아니라 코드다 - 회사 메일의 링크 검사기가 링크를 미리 열어 확인을 써 버리지 못한다. 공개 엔드포인트가 없다(로그인한 본인만).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, RateLimitedError, ValidationAppError

PURPOSE_NOTIFY = "notify_email"
CODE_TTL = timedelta(minutes=15)
RESEND_AFTER = timedelta(seconds=60)
MAX_ATTEMPTS = 5
SENDS_PER_WINDOW = 3
SEND_WINDOW_SECONDS = 15 * 60
CODE_DIGITS = 6
CODE_MINUTES = int(CODE_TTL.total_seconds() // 60)

INACTIVE_DOMAIN = "허용 도메인이 바뀌어 이 주소로는 보내지 않습니다. 지금은 계정 이메일로 보냅니다."

_ADDRESS = re.compile(
    r"^[a-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$"
)
_CODE = re.compile(r"^\d{6}$")


def normalize_address(raw: str) -> str:
    """알림 주소 하나 — ASCII · 254자 · 줄바꿈 · 쉼표 · 공백 없음 · 소문자."""
    text = (raw or "").strip()
    bad = not text or len(text) > 254 or not text.isascii() or any(ch in text for ch in ",;<>\r\n\t ")
    text = text.lower()
    if bad or not _ADDRESS.match(text):
        raise ValidationAppError("알림 받을 주소는 name@example.com 모양의 주소 하나여야 합니다.")
    return text


def current_domains(db: Session) -> list[str]:
    """회사가 허용한 이메일 도메인(설정 `allowed_email_domains`). 빈 목록이면 아무 도메인이나 받는다 - 계정 만들기와 같은 판정이다
    (`app/users/service.py::create_user` 가 쓰는 유효 설정의 기본값도 빈 목록이다)."""
    from app.settings.models import AppSetting

    row = db.get(AppSetting, "allowed_email_domains")
    if row is None:
        return []
    try:
        value = json.loads(row.value_json)
    except (TypeError, ValueError):
        return []
    return [str(d).strip().lower() for d in (value or []) if str(d).strip()] if isinstance(value, list) else []


def domain_allowed(email: str, domains: list[str]) -> bool:
    return not domains or email.rsplit("@", 1)[-1] in domains


def code_hash(secret: str, verification_id: str, code: str) -> str:
    return hmac.new((secret or "").encode("utf-8"), f"{verification_id}:{code}".encode("utf-8"), hashlib.sha256).hexdigest()


def new_code() -> str:
    return f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"


def _model():
    from app.profiles.models import MailAddressVerification

    return MailAddressVerification


def open_verification(db: Session, user_id: str):
    model = _model()
    return db.execute(
        select(model).where(
            model.user_id == user_id, model.purpose == PURPOSE_NOTIFY,
            model.consumed_at.is_(None), model.cancelled_at.is_(None),
        )
    ).scalar_one_or_none()


def cancel_open(db: Session, user_id: str, *, now: datetime) -> bool:
    row = open_verification(db, user_id)
    if row is None:
        return False
    row.cancelled_at = now
    row.updated_at = now
    db.flush()
    return True


def resolve_address(db: Session, user, pref, *, domains: list[str] | None = None) -> str:
    """보낼 주소 — 확인한 다른 주소가 지금 허용 도메인 안이면 그 주소, 아니면 계정 주소."""
    account = (getattr(user, "email", "") or "").strip()
    custom = (getattr(pref, "notify_email", None) or "").strip() if pref is not None else ""
    if not custom or pref.notify_email_verified_at is None:
        return account
    allowed = current_domains(db) if domains is None else domains
    return custom if domain_allowed(custom, allowed) else account


def address_view(db: Session, user, pref, *, now: datetime) -> dict:
    """화면의 받는 주소 한 벌 — 계정 주소 · 지금 보내는 주소 · 확인한 주소와 그 상태 · 확인 중인 주소 · 허용 도메인."""
    domains = current_domains(db)
    custom = None
    if pref is not None and pref.notify_email and pref.notify_email_verified_at is not None:
        active = domain_allowed(pref.notify_email, domains)
        custom = {
            "email": pref.notify_email,
            "verified_at": pref.notify_email_verified_at.isoformat(),
            "active": active,
            "inactive_reason": None if active else INACTIVE_DOMAIN,
        }
    pending = None
    row = open_verification(db, user.id)
    if row is not None:
        sent = row.code_sent_at or row.created_at
        pending = {
            "email": row.email,
            "sent_at": sent.isoformat() if sent else None,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "resend_after": (sent + RESEND_AFTER).isoformat() if sent else None,
        }
    return {
        "account_email": user.email,
        "effective": resolve_address(db, user, pref, domains=domains),
        "custom": custom,
        "pending": pending,
        "allowed_domains": domains,
    }


def request_address(db: Session, user, raw_email: str, *, now: datetime, secret_provider, limiter) -> str:
    """다른 주소로 받기를 시작한다 — 확인 메일을 큐에 넣는다. 계정 주소를 넣으면 다른 주소를 지운다.

    돌려주는 값: `"requested"` · `"cleared"`.
    """
    from app.mail.config import config_from_db, configuration_problems
    from app.mail.renderers import KIND_NOTIFY_EMAIL_VERIFICATION
    from app.mail.service import mail_subject, queue_mail
    from app.profiles.service import ensure_preference

    email = normalize_address(raw_email)
    pref = ensure_preference(db, user.id, now=now)
    if email == (user.email or "").strip().lower():
        cancel_open(db, user.id, now=now)
        pref.notify_email = None
        pref.notify_email_verified_at = None
        pref.updated_at = now
        db.flush()
        return "cleared"
    domains = current_domains(db)
    if not domain_allowed(email, domains):
        raise ValidationAppError(f"회사가 허용한 도메인({', '.join(domains)})의 주소만 쓸 수 있습니다.")
    config = config_from_db(db)
    if configuration_problems(config, secret_provider):
        raise ConflictError("관리자가 메일 발송을 설정하지 않아 확인 메일을 보낼 수 없습니다.")
    existing = open_verification(db, user.id)
    if existing is not None:
        sent = existing.code_sent_at or existing.created_at
        wait = (sent + RESEND_AFTER - now).total_seconds() if sent else 0
        if wait > 0:
            raise RateLimitedError("확인 코드를 다시 받으려면 잠시 기다리세요.", retry_after_seconds=wait)
    key = f"notify_email:send:{user.id}"
    if not limiter.allow(key):
        raise RateLimitedError("확인 메일은 15분에 3통까지 보낼 수 있습니다.", retry_after_seconds=limiter.retry_after_seconds(key))
    cancel_open(db, user.id, now=now)
    model = _model()
    row = model(user_id=user.id, purpose=PURPOSE_NOTIFY, email=email, attempts=0, created_at=now, updated_at=now)
    db.add(row)
    db.flush()
    delivery = queue_mail(
        db, kind=KIND_NOTIFY_EMAIL_VERIFICATION, to_email=email, subject=mail_subject(db, "알림 받을 주소 확인 코드"),
        recipient_user_id=user.id, params={"verification_id": row.id, "user_id": user.id}, now=now, config=config,
        secret_provider=secret_provider,
    )
    row.delivery_id = delivery.id
    db.flush()
    return "requested"


def verify_code(db: Session, user, raw_code: str, *, now: datetime, secret: str, limiter) -> str:
    """코드를 맞추면 그 주소를 알림 주소로 쓴다. 돌려주는 값은 확인한 주소다."""
    from app.profiles.service import ensure_preference

    code = (raw_code or "").strip()
    row = open_verification(db, user.id)
    if row is None:
        raise ValidationAppError("확인할 주소가 없습니다. 확인 코드를 먼저 받으세요.")
    if not _CODE.match(code):
        raise ValidationAppError("확인 코드는 숫자 6자리입니다.")
    key = f"notify_email:verify:{row.id}"
    if not limiter.allow(key):
        raise RateLimitedError("코드를 너무 많이 틀렸습니다. 코드를 다시 받으세요.", retry_after_seconds=limiter.retry_after_seconds(key))
    if row.code_hash is None:
        raise ValidationAppError("확인 메일이 아직 나가지 않았습니다. 잠시 뒤 다시 시도하세요.")
    if row.expires_at is not None and now > row.expires_at:
        raise ValidationAppError("코드가 만료됐습니다. 코드를 다시 받으세요.")
    if not hmac.compare_digest(row.code_hash, code_hash(secret, row.id, code)):
        raise ValidationAppError("코드가 맞지 않습니다. 메일의 6자리 코드를 다시 확인하세요.")
    pref = ensure_preference(db, user.id, now=now)
    row.consumed_at = now
    row.updated_at = now
    pref.notify_email = row.email
    pref.notify_email_verified_at = now
    pref.updated_at = now
    db.flush()
    return row.email


def clear(db: Session, user, *, now: datetime, pending_only: bool = False) -> None:
    """확인 중인 주소를 취소한다. `pending_only` 가 아니면 확인한 다른 주소도 지워 계정 주소로 돌아간다."""
    from app.profiles.service import get_preference

    cancel_open(db, user.id, now=now)
    if pending_only:
        return
    pref = get_preference(db, user.id)
    if pref is not None:
        pref.notify_email = None
        pref.notify_email_verified_at = None
        pref.updated_at = now
        db.flush()


def mint_for_mail(db: Session, verification_id: str, *, now: datetime, secret: str) -> tuple[str, str]:
    """워커가 확인 메일을 그리는 순간 코드를 만든다 - 평문은 메일 본문에만 산다. `(주소, 코드)` 를 돌려준다."""
    row = db.get(_model(), verification_id)
    if row is None or row.consumed_at is not None or row.cancelled_at is not None:
        from app.jobs.exceptions import PermanentJobError

        raise PermanentJobError("주소 확인이 이미 끝났거나 취소됐습니다.")
    code = new_code()
    row.code_hash = code_hash(secret, row.id, code)
    row.code_sent_at = now
    row.expires_at = now + CODE_TTL
    row.updated_at = now
    db.flush()
    return row.email, code


def is_open(db: Session, verification_id: str | None) -> bool:
    if not verification_id:
        return False
    row = db.get(_model(), verification_id)
    return row is not None and row.consumed_at is None and row.cancelled_at is None
