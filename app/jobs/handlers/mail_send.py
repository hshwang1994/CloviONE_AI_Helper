"""mail_send 잡 핸들러 (9-9 P4). **메일이 실제로 나가는 유일한 자리다.**

## 실패를 두 곳에 남긴다

잡 큐(`jobs.last_error`)와 아웃박스(`mail_deliveries.last_error`) 둘 다에 남긴다.
겹쳐 보이지만 답하는 질문이 다르다:

  * 잡 - "이 작업이 재시도 중인가, 포기했는가"
  * 아웃박스 - "그 사람에게 메일이 갔는가" (잡이 성공으로 덮여도 이력이 남는다)

**아웃박스 기록을 먼저 커밋하고 나서 예외를 다시 던진다.** 순서가 뒤집히면 워커의
`db.rollback()` 이 실패 기록을 함께 지워, 큐에는 실패가 보이는데 "왜 안 왔나" 를 묻는
화면에는 아무것도 없는 상태가 된다. 실제로 이 저장소가 여러 번 겪은 모양이다
(app/core/deps.py::_count_blocked_write 의 별도 세션 주석과 같은 종류의 함정).

## 다시 보낼지는 실패의 종류가 정한다 (계획 3.3)

전송기가 실패를 종류로 나눠 준다(`app/mail/transport.py::classify`). 일시 실패는 행을 `retrying` 으로 두고
잡이 종류별 재시도 일정(`retry_delay`)대로 다시 돈다. 영구 실패와 마지막 시도의 실패만 `failed` 다. 워커가
죽어 잡이 회수된 뒤 끝나거나 사람이 잡을 취소하면 `on_failure` 와 잡 화면의 취소가 행도 끝낸다 - 행이
`queued` 로 영원히 남지 않게.

## 본문은 여기서 만든다

토큰과 초대 링크가 DB 에 평문으로 앉지 않게 하려는 것이다 - 이유는
app/mail/renderers.py 모듈 docstring 에 적어 뒀다.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.jobs.exceptions import PermanentJobError
from app.jobs.models import Job
from app.jobs.worker import WorkerContext, parse_payload
from app.mail.config import config_from_db, configuration_problems
from app.mail.models import (
    FAILURE_CONFIG,
    FAILURE_RENDER,
    FAILURE_UNKNOWN,
    MAIL_CANCELLED,
    MAIL_SENT,
    MAIL_SUPERSEDED,
    PENDING_MAIL_STATUSES,
    MailDelivery,
)
from app.mail.renderers import render_body
from app.mail.service import record_failure, record_sent, retry_delay_for

logger = logging.getLogger("app.handlers.mail_send")


def _transport(ctx: WorkerContext):
    """워커가 끼워 준 발송기. 없으면 진짜 SMTP 를 쓴다.

    지연 import 인 이유: `app/mail/transport.py` 만 smtplib 를 import 한다는 경계를
    지키면서, 테스트가 가짜를 끼우면 smtplib 를 아예 건드리지 않게 하려는 것이다.
    """
    injected = (ctx.extras or {}).get("mail_transport")
    if injected is not None:
        return injected
    from app.mail.transport import SmtpTransport

    return SmtpTransport()


def handle_mail_send(db: Session, job: Job, ctx: WorkerContext) -> None:
    payload = parse_payload(job)
    delivery_id = payload.get("delivery_id")
    delivery = db.get(MailDelivery, delivery_id) if delivery_id else None
    if delivery is None:
        raise PermanentJobError(f"메일 발송 기록을 찾을 수 없습니다: {delivery_id}")
    if delivery.status == MAIL_SENT:
        # 완료 기록만 실패해 재큐잉된 경우(app/jobs/worker.py::_finish_out_of_band 참조).
        # 같은 메일을 두 번 보내지 않는다.
        logger.info("mail %s 는 이미 발송됐다. 건너뛴다", delivery.id)
        return
    if delivery.status in (MAIL_CANCELLED, MAIL_SUPERSEDED):
        # 잡이 집힌 뒤 사람이 취소했거나 보낼 의미가 없어졌다. 보내지 않고 끝낸다.
        logger.info("mail %s 는 %s 상태라 보내지 않는다", delivery.id, delivery.status)
        return

    now = ctx.clock.now()
    config = config_from_db(db)
    secret_provider = (ctx.extras or {}).get("secret_provider")
    problems = configuration_problems(config, secret_provider)
    if problems:
        # 큐에 넣은 뒤 설정이 지워졌거나 secret 파일이 사라진 경우다. 재시도해도 낫지
        # 않으므로 영구 실패로 끊되, **왜인지는 아웃박스에 남긴다.**
        record_failure(
            db, delivery, error=" / ".join(problems), now=now, terminal=True, failure_kind=FAILURE_CONFIG,
        )
        db.commit()
        raise PermanentJobError("메일 발송 설정이 없어 보낼 수 없습니다: " + "; ".join(problems))

    try:
        body = render_body(db, delivery, ctx)
        _transport(ctx).send(
            config,
            secret_provider,
            to_email=delivery.to_email,
            subject=delivery.subject,
            body=body,
        )
    except Exception as exc:
        # 렌더 실패도 발송 실패와 같은 자리에서 잡는다 - 렌더가 만든 토큰 행은 이 롤백과
        # 함께 사라져야 한다. render_body 가 밖에서 raise 하면 아웃박스 기록 없이 잡만
        # 영구 실패로 남는다 (파일 docstring 의 그 함정).
        db.rollback()
        fresh = db.get(MailDelivery, delivery_id)
        if isinstance(exc, PermanentJobError):
            kind, permanent = FAILURE_RENDER, True
        else:
            kind = getattr(exc, "kind", FAILURE_UNKNOWN)
            permanent = bool(getattr(exc, "permanent", False))
        # 잡은 집힐 때 시도 수를 올린다. 이번이 마지막 시도였으면 재시도가 남지 않았다.
        terminal = permanent or job.attempt_count >= job.max_attempts
        record_failure(
            db, fresh, error=f"{type(exc).__name__}: {exc}", now=now, terminal=terminal, failure_kind=kind,
        )
        db.commit()
        logger.warning("메일 발송 실패 (kind=%s, 종류=%s, 끝=%s): %s", fresh.kind, kind, terminal, exc)
        if permanent and not isinstance(exc, PermanentJobError):
            # 다시 보내도 같은 결과다. 잡도 즉시 끝낸다(재시도 일정을 태우지 않는다).
            raise PermanentJobError(f"{type(exc).__name__}: {exc}") from exc
        raise

    record_sent(db, delivery, now=now)
    logger.info("메일 발송 완료 (kind=%s, delivery=%s)", delivery.kind, delivery.id)


def _retry_delay(job: Job) -> float | None:
    """다음 시도까지의 간격 - 메일 종류의 재시도 일정(`app/mail/service.py::retry_delay_for`).

    종류는 잡 payload 에 있다. 업그레이드 전에 들어간 옛 잡에는 없어서 기본 백오프로 돈다.
    """
    try:
        kind = json.loads(job.payload_json or "{}").get("kind")
    except ValueError:
        return None
    if not kind:
        return None
    return retry_delay_for(kind, job.attempt_count)


def _on_failure(db: Session, job: Job, ctx: WorkerContext, error: str) -> None:
    """잡이 핸들러 밖에서 끝났을 때(워커가 죽어 회수된 뒤 시도가 다 됨, 완료 기록 실패) 행도 끝낸다.

    핸들러가 이미 `failed` 로 적은 행은 건드리지 않는다 - 그 기록이 더 정확하다.
    """
    try:
        delivery_id = json.loads(job.payload_json or "{}").get("delivery_id")
    except ValueError:
        return
    delivery = db.get(MailDelivery, delivery_id) if delivery_id else None
    if delivery is None or delivery.status not in PENDING_MAIL_STATUSES:
        return
    record_failure(db, delivery, error=error, now=ctx.clock.now(), terminal=True, failure_kind=FAILURE_UNKNOWN)


handle_mail_send.retry_delay = _retry_delay
handle_mail_send.on_failure = _on_failure
