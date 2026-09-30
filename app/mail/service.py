"""메일 큐잉 (9-9 P4). **여기서는 절대 보내지 않는다.**

## 왜 웹에서 보내면 안 되는가

SMTP 는 느릴 때 수십 초를 문다(DNS, 연결, STARTTLS 핸드셰이크, 상대 서버 그레이리스팅).
이 저장소의 핸들러는 전부 sync 라(불변 §1) 그 시간 동안 스레드풀 슬롯 하나가 통째로
잡힌다. 티켓을 만들다 메일 때문에 30초를 기다리는 화면은 "느리다" 가 아니라 "고장" 으로
읽힌다.

그래서 이 모듈은 **행 하나와 잡 하나**만 만들고 끝난다. 실제 발송은
`app/jobs/handlers/mail_send.py` 가 워커에서 한다. 새 큐를 만들지 않고 기존 잡 큐를 쓴다 -
재시도, 백오프, 좀비 회수, 실패 알림이 이미 거기 있다.

## 보낼 수 없을 때도 행은 남긴다

`status='unconfigured'` 로 남긴다. 잡은 만들지 않는다. 이유는 app/mail/models.py 의
docstring 에 적어 뒀다 - 요약하면 "영원히 재시도하는 큐" 와 "통째로 증발" 둘 다 피한다.

## 재시도는 종류마다 다르다 (계획 3.3)

일시 실패(연결, 시간 초과, 4xx, 연결 끊김)는 **보낼 때까지 버리지 않는다.** 알림 · 초대 · 승인 · 백업
실패 메일은 1분 · 5분 · 15분 · 1시간 · 4시간 · 8시간 · 12시간 뒤에 다시 보낸다(여덟 번, 약 25시간 - 하루
남짓한 메일 서버 장애를 견딘다). 비밀번호 재설정은 몇 분 안에 세 번이다 - 링크가 한 시간 뒤 만료되고, 사람은
그 사이에 다시 요청한다. 시험 메일은 한 번이다 - 결과를 바로 보려고 보내는 메일이다. 영구 실패(로그인 거부,
보안 연결, 보내는 사람과 받는 사람 거부, 그 밖의 5xx)는 다시 보내도 같아서 즉시 끝낸다.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError

from app.mail.config import (
    MailConfig,
    config_from_db,
    configuration_problems,
)
from app.mail.models import (
    MAIL_CANCELLED,
    MAIL_FAILED,
    MAIL_QUEUED,
    MAIL_RETRYING,
    MAIL_SENT,
    MAIL_STATUS_LABELS,
    MAIL_SUPERSEDED,
    MAIL_UNCONFIGURED,
    PENDING_MAIL_STATUSES,
    MailDelivery,
)
from app.mail.renderers import (
    KIND_INVITE,
    KIND_NOTIFICATION,
    KIND_PASSWORD_RESET,
    KIND_TEST,
    MAIL_KIND_LABELS,
)

logger = logging.getLogger("app.mail")

MAIL_JOB_TYPE = "mail_send"

# 다음 시도까지의 간격(초). 길이 + 1 이 시도 횟수다(모듈 머리말).
DEFAULT_RETRY_DELAYS: tuple[int, ...] = (60, 300, 900, 3600, 4 * 3600, 8 * 3600, 12 * 3600)
RETRY_DELAYS_BY_KIND: dict[str, tuple[int, ...]] = {
    KIND_TEST: (),
    KIND_PASSWORD_RESET: (60, 300),
}
# 사람이 다시 보낼 수 없는 종류. 재설정 메일은 보낼 때 새 토큰을 만들어 오래된 요청을 되살리고, 시험 메일은
# 새로 보내면 된다.
NOT_RESENDABLE_KINDS = frozenset({KIND_PASSWORD_RESET, KIND_TEST})
# 설정 전에 쌓인 메일 중 설정 뒤에 다시 보낼 수 있는 종류와 기간. 사람이 누를 때만 보내고, 보내기 직전에 아직
# 의미가 있는지와 받는 사람이 여전히 원하는지를 다시 본다(계획 3.4).
RESENDABLE_UNCONFIGURED_KINDS = frozenset({KIND_INVITE, KIND_NOTIFICATION})
UNCONFIGURED_RESEND_WINDOW_DAYS = 7


def retry_delays(kind: str) -> tuple[int, ...]:
    return RETRY_DELAYS_BY_KIND.get(kind, DEFAULT_RETRY_DELAYS)


def max_attempts_for(kind: str) -> int:
    return len(retry_delays(kind)) + 1


def retry_delay_for(kind: str, attempt: int) -> int | None:
    """`attempt` 번째 시도가 실패한 뒤 다음 시도까지의 간격. 남은 시도가 없으면 None."""
    delays = retry_delays(kind)
    index = attempt - 1
    return delays[index] if 0 <= index < len(delays) else None


def _enqueue_job(db: Session, row: MailDelivery, *, now: datetime) -> None:
    """이 행을 보낼 잡 하나. 시도 횟수는 종류의 재시도 일정이 정한다."""
    from app.jobs import repository as jobs_repository

    job = jobs_repository.enqueue(
        db,
        job_type=MAIL_JOB_TYPE,
        payload={"delivery_id": row.id, "kind": row.kind},
        now=now,
        max_attempts=max_attempts_for(row.kind),
    )
    row.job_id = job.id
    db.flush()


def queue_mail(
    db: Session,
    *,
    kind: str,
    to_email: str,
    subject: str,
    params: dict | None = None,
    now: datetime,
    config: MailConfig | None = None,
    secret_provider=None,
    idempotency_key: str | None = None,
) -> MailDelivery:
    """메일 한 통을 큐에 넣는다. 보낼 수 없으면 그 사실을 행에 적고 잡은 만들지 않는다.

    ``params`` 에는 **비밀이 아닌 재료만** 넣는다(사용자 id, 실패 사유 문장 등).
    본문은 워커가 발송 직전에 만든다 - 토큰과 임시 비밀번호가 DB 에 앉지 않게.

    ``idempotency_key`` 를 주면 같은 열쇠의 행이 이미 있을 때 **그 행을 돌려주고 아무것도 더 만들지 않는다**
    (같은 알림이 두 번 팬아웃돼도 메일은 한 통이다). 동시에 들어온 두 요청은 유일 제약이 가른다.
    """
    if idempotency_key:
        existing = db.execute(
            select(MailDelivery).where(MailDelivery.idempotency_key == idempotency_key)
        ).scalar_one_or_none()
        if existing is not None:
            return existing

    resolved = config if config is not None else config_from_db(db)
    problems = configuration_problems(resolved, secret_provider)

    row = MailDelivery(
        kind=kind,
        to_email=(to_email or "").strip(),
        subject=subject[:300],
        status=MAIL_UNCONFIGURED if problems else MAIL_QUEUED,
        attempt_count=0,
        params_json=json.dumps(params or {}, ensure_ascii=False),
        last_error=" / ".join(problems) if problems else None,
        idempotency_key=idempotency_key or None,
        created_at=now,
        updated_at=now,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        # 같은 열쇠가 먼저 커밋됐다. 그 행이 이 요청의 결과다.
        existing = db.execute(
            select(MailDelivery).where(MailDelivery.idempotency_key == idempotency_key)
        ).scalar_one_or_none()
        if existing is None:
            raise
        return existing

    if problems:
        # 로그에도 남긴다. 화면을 안 보는 운영자가 journalctl 로 먼저 발견하는 경로다.
        logger.warning(
            "메일을 보낼 수 없어 큐에 넣지 않았다 (kind=%s): %s", kind, "; ".join(problems)
        )
        return row

    _enqueue_job(db, row, now=now)
    return row


def _queue_to_emails(
    db: Session,
    emails,
    *,
    kind: str,
    subject: str,
    params: dict | None,
    now: datetime,
    config: MailConfig | None,
    secret_provider,
) -> list[MailDelivery]:
    resolved = config if config is not None else config_from_db(db)
    return [
        queue_mail(
            db,
            kind=kind,
            to_email=email,
            subject=subject,
            params=params,
            now=now,
            config=resolved,
            secret_provider=secret_provider,
        )
        for email in emails
        if email
    ]


def queue_mail_to_admins(
    db: Session,
    *,
    kind: str,
    subject: str,
    params: dict | None = None,
    now: datetime,
    config: MailConfig | None = None,
    secret_provider=None,
) -> list[MailDelivery]:
    """활성 관리자 전원에게. `notifications.notify_admins` 와 같은 대상 규칙을 쓴다."""
    from app.users.models import ROLE_ADMIN, ROLE_SYSTEM_ADMIN, User

    emails = (
        db.execute(
            select(User.email).where(
                User.role.in_([ROLE_ADMIN, ROLE_SYSTEM_ADMIN]),
                User.active.is_(True),
                User.archived_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    return _queue_to_emails(
        db, emails, kind=kind, subject=subject, params=params, now=now,
        config=config, secret_provider=secret_provider,
    )


def queue_mail_to_users(
    db: Session,
    user_ids,
    *,
    kind: str,
    subject: str,
    params: dict | None = None,
    now: datetime,
    config: MailConfig | None = None,
    secret_provider=None,
) -> list[MailDelivery]:
    """사용자 id 목록을 주소로 바꿔 보낸다.

    **대상 규칙을 여기서 정하지 않는다.** 누가 받아야 하는지는 부르는 쪽 도메인이 안다
    (예: 결재 가능자 = `notifications.approver_user_ids`). 여기서 다시 정하면 화면 알림과
    메일이 서로 다른 사람에게 가는 상태가 만들어진다.
    """
    from app.users.models import User

    ids = [uid for uid in (user_ids or []) if uid]
    if not ids:
        return []
    emails = (
        db.execute(
            select(User.email).where(
                User.id.in_(ids), User.active.is_(True), User.archived_at.is_(None)
            )
        )
        .scalars()
        .all()
    )
    return _queue_to_emails(
        db, emails, kind=kind, subject=subject, params=params, now=now,
        config=config, secret_provider=secret_provider,
    )


def record_sent(db: Session, row: MailDelivery, *, now: datetime, message_id: str | None = None) -> None:
    row.status = MAIL_SENT
    row.sent_at = now
    row.last_error = None
    row.failure_kind = None
    if message_id:
        row.message_id = message_id[:300]
    row.updated_at = now
    db.flush()


def record_failure(
    db: Session, row: MailDelivery, *, error: str, now: datetime,
    terminal: bool = True, failure_kind: str | None = None,
) -> None:
    """실패를 행에 적는다. **잡의 재시도와 별개로** 남는 기록이다.

    잡은 성공하면 흔적이 사라지지만(succeeded 로 덮인다) 이 행의 ``attempt_count`` 와
    ``last_error`` 는 "그동안 몇 번 실패했나" 를 계속 말한다.

    ``terminal`` 이 아니면(재시도가 남았으면) ``retrying`` 이다. 예전에는 첫 실패부터 ``failed`` 로 적어서
    다음 재시도에 나갈 메일도 실패로 세었고, 화면은 「실패」와 「다시 보내는 중」을 가르지 못했다.
    """
    row.status = MAIL_FAILED if terminal else MAIL_RETRYING
    row.attempt_count = (row.attempt_count or 0) + 1
    row.last_error = (error or "")[:2000]
    row.failure_kind = failure_kind
    row.updated_at = now
    db.flush()


def record_skipped(db: Session, row: MailDelivery, *, status: str, reason: str, now: datetime) -> None:
    """보내지 않고 끝낸다(`cancelled` · `superseded`). 까닭은 `skip_reason` 에 남는다."""
    row.status = status
    row.skip_reason = (reason or "")[:64] or None
    row.updated_at = now
    db.flush()


def _require(row: MailDelivery | None) -> MailDelivery:
    from app.core.errors import NotFoundError

    if row is None:
        raise NotFoundError("메일 발송 기록을 찾을 수 없습니다.")
    return row


def cancel_delivery(db: Session, delivery_id: str, *, now: datetime) -> MailDelivery:
    """대기 중이거나 다시 보내는 중인 메일을 취소한다. 워커가 이미 집었으면 409 다(잡 취소와 같은 CAS)."""
    from app.jobs import repository as jobs_repository
    from app.jobs.models import Job

    row = _require(db.get(MailDelivery, delivery_id))
    if row.status not in PENDING_MAIL_STATUSES:
        raise ConflictError("보내기를 기다리는 메일만 취소할 수 있습니다.")
    job = db.get(Job, row.job_id) if row.job_id else None
    if job is not None:
        jobs_repository.cancel_queued(db, job, now=now)
    record_skipped(db, row, status=MAIL_CANCELLED, reason="cancelled_by_operator", now=now)
    return row


def resend_delivery(
    db: Session, delivery_id: str, *, now: datetime, config: MailConfig | None = None, secret_provider=None,
) -> MailDelivery:
    """실패 · 설정 없음 · 취소로 끝난 메일을 다시 보낸다. 새 잡을 만들고 행은 그대로 쓴다(이력이 이어진다)."""
    row = _require(db.get(MailDelivery, delivery_id))
    if row.kind in NOT_RESENDABLE_KINDS:
        raise ConflictError(
            "이 종류의 메일은 다시 보낼 수 없습니다. 비밀번호 재설정은 사용자가 다시 요청하고, 시험 메일은 새로 보내세요."
        )
    if row.status not in (MAIL_FAILED, MAIL_UNCONFIGURED, MAIL_CANCELLED):
        raise ConflictError("실패했거나 보내지 못한 메일만 다시 보낼 수 있습니다.")
    resolved = config if config is not None else config_from_db(db)
    problems = configuration_problems(resolved, secret_provider)
    if problems:
        raise ConflictError("메일 발송 설정이 끝나지 않아 다시 보낼 수 없습니다: " + " ".join(problems))
    row.status = MAIL_QUEUED
    row.failure_kind = None
    row.skip_reason = None
    row.updated_at = now
    _enqueue_job(db, row, now=now)
    return row


def resend_unconfigured(
    db: Session, *, now: datetime, config: MailConfig | None = None, secret_provider=None,
) -> int:
    """설정 전에 쌓인 메일 중 아직 의미가 있을 만한 것(초대 · 알림, 최근 7일)을 다시 큐에 넣는다.

    오래된 알림을 예고 없이 뿌리지 않으려고 이 동작은 **사람이 누를 때만** 돈다(계획 3.4). 보내기 직전의
    유효성 재검사는 렌더러가 한다.
    """
    from datetime import timedelta

    resolved = config if config is not None else config_from_db(db)
    problems = configuration_problems(resolved, secret_provider)
    if problems:
        raise ConflictError("메일 발송 설정이 끝나지 않아 보낼 수 없습니다: " + " ".join(problems))
    since = now - timedelta(days=UNCONFIGURED_RESEND_WINDOW_DAYS)
    rows = list(db.execute(
        select(MailDelivery).where(
            MailDelivery.status == MAIL_UNCONFIGURED,
            MailDelivery.kind.in_(sorted(RESENDABLE_UNCONFIGURED_KINDS)),
            MailDelivery.created_at >= since,
        ).order_by(MailDelivery.created_at)
    ).scalars())
    for row in rows:
        row.status = MAIL_QUEUED
        row.last_error = None
        row.updated_at = now
        _enqueue_job(db, row, now=now)
    return len(rows)


def pending_unconfigured_count(db: Session, *, now: datetime) -> int:
    """`resend_unconfigured` 가 다시 보낼 메일의 수. 화면이 그 단추 옆에 건수를 말한다."""
    from datetime import timedelta

    since = now - timedelta(days=UNCONFIGURED_RESEND_WINDOW_DAYS)
    return int(db.execute(
        select(func.count()).select_from(MailDelivery).where(
            MailDelivery.status == MAIL_UNCONFIGURED,
            MailDelivery.kind.in_(sorted(RESENDABLE_UNCONFIGURED_KINDS)),
            MailDelivery.created_at >= since,
        )
    ).scalar_one())


# 원문 앞머리가 `SMTPAuthenticationError: ...` 처럼 파이썬 예외 이름이면 그건 사람에게
# 보여 줄 문장이 아니다. 설정 문제 경로(configuration_problems)는 이미 한국어 문장을
# 넣으므로 이 표를 타지 않는다 - 아래 summarize_failure 가 둘을 구분한다.
_ERROR_SUMMARIES: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("SMTPAuthenticationError", "authentication", "535", "534"),
        "메일 서버가 로그인을 거부했습니다. 사용자 이름과 비밀번호를 확인하세요.",
    ),
    (
        ("SMTPSenderRefused", "SenderRefused"),
        "메일 서버가 보내는 사람 주소를 거부했습니다. 보내는 사람 주소를 확인하세요.",
    ),
    (
        ("SMTPRecipientsRefused", "RecipientsRefused", "550"),
        "메일 서버가 받는 사람 주소를 거부했습니다. 주소가 맞는지 확인하세요.",
    ),
    (
        ("SSLError", "SMTPNotSupportedError", "STARTTLS", "wrong version number"),
        "보안 연결 방식이 서버와 맞지 않습니다. 보안 방식(STARTTLS/SSL)과 포트를 확인하세요.",
    ),
    (
        ("timed out", "TimeoutError", "timeout"),
        "메일 서버가 제때 응답하지 않았습니다. 서버 주소와 포트, 방화벽을 확인하세요.",
    ),
    (
        (
            "ConnectionRefused",
            "SMTPConnectError",
            "getaddrinfo",
            "gaierror",
            "Name or service not known",
            "Network is unreachable",
        ),
        "메일 서버에 연결하지 못했습니다. 서버 주소와 포트를 확인하세요.",
    ),
    (
        ("SMTPServerDisconnected",),
        "메일 서버와의 연결이 끊겼습니다. 보안 방식과 포트를 확인하세요.",
    ),
    (
        ("PermanentJobError", "메일 파라미터", "대상 계정"),
        "메일 내용을 만들지 못했습니다. 대상 계정이 남아 있는지 확인하세요.",
    ),
    (
        ("CERTIFICATE_VERIFY_FAILED", "certificate verify failed", "SSLCertVerificationError"),
        "메일 서버의 인증서를 확인하지 못했습니다. 사설 인증서라면 CA 인증서를 등록하세요.",
    ),
)

_UNKNOWN_FAILURE = "메일을 보내지 못했습니다. 아래 기술 정보로 원인을 확인하세요."

# `Klass: 메시지` 또는 `module.Klass: 메시지` 모양. 파이썬 예외를 문자열로 만든 자국이다.
_EXCEPTION_HEAD = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*(Error|Exception|Refused|Disconnected)\b")


def summarize_failure(raw: str | None) -> str | None:
    """실패 원문을 **사람에게 보여 줄 한 문장**으로 바꾼다 (지시 36 · 40).

    원문(`f"{type(exc).__name__}: {exc}"`)은 지우지 않는다 - 운영자가 원인을 찾을 때
    그것이 유일한 단서다. 다만 그것이 화면의 **주된 내용**이 되어서는 안 된다. 여기서
    만든 요약이 앞에 서고 원문은 `기술 정보`로 내려간다.

    설정 문제 경로는 `configuration_problems()` 가 이미 한국어 문장을 만들어 넣으므로
    (app/jobs/handlers/mail_send.py) 그대로 통과시킨다. 요약을 한 번 더 씌우면
    "메일 서버 주소가 비어 있습니다" 같은 정확한 안내가 뭉개진다.
    """
    text = (raw or "").strip()
    if not text:
        return None
    for needles, message in _ERROR_SUMMARIES:
        if any(n.lower() in text.lower() for n in needles):
            return message
    # 예외 이름으로 시작하지 않으면 우리가 직접 쓴 한국어 안내다. 그대로 쓴다.
    if not _EXCEPTION_HEAD.match(text):
        return text
    return _UNKNOWN_FAILURE


def _skip_label(reason: str | None) -> str | None:
    from app.mail.relevance import REASON_LABELS

    if not reason:
        return None
    return REASON_LABELS.get(reason, "보내지 않았습니다.")


def delivery_view(row: MailDelivery) -> dict:
    return {
        "id": row.id,
        "kind": row.kind,
        "kind_label": MAIL_KIND_LABELS.get(row.kind, row.kind),
        "to_email": row.to_email,
        "subject": row.subject,
        "status": row.status,
        "status_label": MAIL_STATUS_LABELS.get(row.status, row.status),
        "attempt_count": row.attempt_count,
        "max_attempts": max_attempts_for(row.kind),
        # error_summary 가 화면의 주된 내용이고 last_error 는 `기술 정보` 안에서만 쓴다.
        "error_summary": summarize_failure(row.last_error),
        "last_error": row.last_error,
        "failure_kind": row.failure_kind,
        "skip_reason": row.skip_reason,
        "skip_reason_label": _skip_label(row.skip_reason),
        "message_id": row.message_id,
        "resendable": row.kind not in NOT_RESENDABLE_KINDS
        and row.status in (MAIL_FAILED, MAIL_UNCONFIGURED, MAIL_CANCELLED),
        "cancellable": row.status in PENDING_MAIL_STATUSES,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "sent_at": row.sent_at.isoformat() if row.sent_at else None,
    }


def delivery_detail(db: Session, delivery_id: str) -> dict:
    """한 통의 상세 - 행과 그 잡의 상태, 다음 시도 시각. 시험 메일의 결과를 기다리는 화면이 이것을 읽는다."""
    from app.jobs.models import Job

    row = _require(db.get(MailDelivery, delivery_id))
    job = db.get(Job, row.job_id) if row.job_id else None
    view = delivery_view(row)
    view["job"] = None if job is None else {
        "id": job.id,
        "status": job.status,
        "attempt_count": job.attempt_count,
        "max_attempts": job.max_attempts,
        "next_attempt_at": job.available_at.isoformat() if job.status == "queued" and job.available_at else None,
    }
    try:
        view["params"] = json.loads(row.params_json or "{}")
    except ValueError:
        view["params"] = {}
    return view


def queue_counts(db: Session) -> dict:
    counts = dict(
        db.execute(
            select(MailDelivery.status, func.count()).group_by(MailDelivery.status)
        ).all()
    )
    return {
        "queued": int(counts.get(MAIL_QUEUED, 0)),
        "retrying": int(counts.get(MAIL_RETRYING, 0)),
        "sent": int(counts.get(MAIL_SENT, 0)),
        "failed": int(counts.get(MAIL_FAILED, 0)),
        "unconfigured": int(counts.get(MAIL_UNCONFIGURED, 0)),
        "cancelled": int(counts.get(MAIL_CANCELLED, 0)),
        "superseded": int(counts.get(MAIL_SUPERSEDED, 0)),
    }


def recent_failures(db: Session, *, limit: int = 10) -> list[MailDelivery]:
    """실패, '보낼 수 없었음', 다시 보내는 중을 함께 본다 - 사용자에게는 셋 다 '안 온 메일' 이다.

    다시 보내는 중인 메일은 끝난 실패가 아니지만 한 번 이상 실패했고 그 까닭이 `last_error` 에 있다.
    메일 서버가 몇 시간째 거절하는 동안 이 목록이 비어 있으면 운영자는 문제가 없다고 읽는다.
    """
    return list(
        db.execute(
            select(MailDelivery)
            .where(MailDelivery.status.in_([MAIL_FAILED, MAIL_UNCONFIGURED, MAIL_RETRYING]))
            .order_by(MailDelivery.created_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )


# ── 발송 기록 목록 (계획 3.3) ─────────────────────────────────────────────────

def _list_sort():
    from app.core.sort import SortSpec

    return SortSpec(
        columns={
            "created_at": MailDelivery.created_at,
            "status": MailDelivery.status,
            "kind": MailDelivery.kind,
            "to_email": MailDelivery.to_email,
            "attempt_count": MailDelivery.attempt_count,
        },
        default="created_at",
        tiebreak=MailDelivery.id,
        default_order="desc",
    )


LIST_SORT = _list_sort()


def list_deliveries(
    db: Session, *, status: str | None = None, kind: str | None = None, q: str | None = None,
    since: str | None = None, until: str | None = None, sort=None, offset: int = 0, limit: int = 50,
) -> tuple[list[MailDelivery], int]:
    """발송 기록 한 쪽. 모르는 상태 · 종류는 422 다 - 빈 목록으로 삼키면 「그런 메일이 없다」로 읽힌다."""
    from app.core.dates import parse_kst_boundary
    from app.core.errors import ValidationAppError
    from app.core.search_text import contains_folded
    from app.core.sort import order_by
    from app.mail.models import ALL_MAIL_STATUSES
    from app.mail.renderers import MAIL_KINDS

    stmt = select(MailDelivery)
    if status:
        if status not in ALL_MAIL_STATUSES:
            raise ValidationAppError(f"알 수 없는 발송 상태입니다: {status}")
        stmt = stmt.where(MailDelivery.status == status)
    if kind:
        if kind not in MAIL_KINDS:
            raise ValidationAppError(f"알 수 없는 메일 종류입니다: {kind}")
        stmt = stmt.where(MailDelivery.kind == kind)
    clause = contains_folded((MailDelivery.to_email, MailDelivery.subject), q)
    if clause is not None:
        stmt = stmt.where(clause)
    if since:
        stmt = stmt.where(MailDelivery.created_at >= parse_kst_boundary(since, "since", upper=False))
    if until:
        stmt = stmt.where(MailDelivery.created_at < parse_kst_boundary(until, "until", upper=True))
    total = int(db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
    rows = list(db.execute(stmt.order_by(*order_by(LIST_SORT, sort)).offset(offset).limit(limit)).scalars())
    return rows, total
