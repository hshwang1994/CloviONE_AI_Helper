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
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.mail.config import (
    MailConfig,
    config_from_db,
    configuration_problems,
)
from app.mail.models import (
    MAIL_FAILED,
    MAIL_QUEUED,
    MAIL_SENT,
    MAIL_STATUS_LABELS,
    MAIL_UNCONFIGURED,
    MailDelivery,
)

logger = logging.getLogger("app.mail")

MAIL_JOB_TYPE = "mail_send"
# 메일은 상대 서버 사정으로 자주 일시 실패한다. 채팅 잡(3회)보다 넉넉히 준다.
MAIL_MAX_ATTEMPTS = 5


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
) -> MailDelivery:
    """메일 한 통을 큐에 넣는다. 보낼 수 없으면 그 사실을 행에 적고 잡은 만들지 않는다.

    ``params`` 에는 **비밀이 아닌 재료만** 넣는다(사용자 id, 실패 사유 문장 등).
    본문은 워커가 발송 직전에 만든다 - 토큰과 임시 비밀번호가 DB 에 앉지 않게.
    """
    from app.jobs import repository as jobs_repository

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
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()

    if problems:
        # 로그에도 남긴다. 화면을 안 보는 운영자가 journalctl 로 먼저 발견하는 경로다.
        logger.warning(
            "메일을 보낼 수 없어 큐에 넣지 않았다 (kind=%s): %s", kind, "; ".join(problems)
        )
        return row

    job = jobs_repository.enqueue(
        db,
        job_type=MAIL_JOB_TYPE,
        payload={"delivery_id": row.id},
        now=now,
        max_attempts=MAIL_MAX_ATTEMPTS,
    )
    row.job_id = job.id
    db.flush()
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


def record_sent(db: Session, row: MailDelivery, *, now: datetime) -> None:
    row.status = MAIL_SENT
    row.sent_at = now
    row.last_error = None
    row.updated_at = now
    db.flush()


def record_failure(db: Session, row: MailDelivery, *, error: str, now: datetime) -> None:
    """실패를 행에 적는다. **잡의 재시도와 별개로** 남는 기록이다.

    잡은 성공하면 흔적이 사라지지만(succeeded 로 덮인다) 이 행의 ``attempt_count`` 와
    ``last_error`` 는 "그동안 몇 번 실패했나" 를 계속 말한다.
    """
    row.status = MAIL_FAILED
    row.attempt_count = (row.attempt_count or 0) + 1
    row.last_error = (error or "")[:2000]
    row.updated_at = now
    db.flush()


def delivery_view(row: MailDelivery) -> dict:
    return {
        "id": row.id,
        "kind": row.kind,
        "to_email": row.to_email,
        "subject": row.subject,
        "status": row.status,
        "status_label": MAIL_STATUS_LABELS.get(row.status, row.status),
        "attempt_count": row.attempt_count,
        "last_error": row.last_error,
        "created_at": row.created_at.isoformat(),
        "sent_at": row.sent_at.isoformat() if row.sent_at else None,
    }


def queue_counts(db: Session) -> dict:
    counts = dict(
        db.execute(
            select(MailDelivery.status, func.count()).group_by(MailDelivery.status)
        ).all()
    )
    return {
        "queued": int(counts.get(MAIL_QUEUED, 0)),
        "sent": int(counts.get(MAIL_SENT, 0)),
        "failed": int(counts.get(MAIL_FAILED, 0)),
        "unconfigured": int(counts.get(MAIL_UNCONFIGURED, 0)),
    }


def recent_failures(db: Session, *, limit: int = 10) -> list[MailDelivery]:
    """실패와 '보낼 수 없었음' 을 함께 본다 - 사용자에게는 둘 다 '안 온 메일' 이다."""
    return list(
        db.execute(
            select(MailDelivery)
            .where(MailDelivery.status.in_([MAIL_FAILED, MAIL_UNCONFIGURED]))
            .order_by(MailDelivery.created_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
