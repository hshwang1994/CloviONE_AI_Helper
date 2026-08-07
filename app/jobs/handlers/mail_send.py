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

## 본문은 여기서 만든다

토큰과 초대 링크가 DB 에 평문으로 앉지 않게 하려는 것이다 - 이유는
app/mail/renderers.py 모듈 docstring 에 적어 뒀다.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.jobs.exceptions import PermanentJobError
from app.jobs.models import Job
from app.jobs.worker import WorkerContext, parse_payload
from app.mail.config import config_from_db, configuration_problems
from app.mail.models import MAIL_SENT, MailDelivery
from app.mail.renderers import render_body
from app.mail.service import record_failure, record_sent

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

    now = ctx.clock.now()
    config = config_from_db(db)
    secret_provider = (ctx.extras or {}).get("secret_provider")
    problems = configuration_problems(config, secret_provider)
    if problems:
        # 큐에 넣은 뒤 설정이 지워졌거나 secret 파일이 사라진 경우다. 재시도해도 낫지
        # 않으므로 영구 실패로 끊되, **왜인지는 아웃박스에 남긴다.**
        record_failure(db, delivery, error=" / ".join(problems), now=now)
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
        record_failure(db, fresh, error=f"{type(exc).__name__}: {exc}", now=now)
        db.commit()
        logger.warning("메일 발송 실패 (kind=%s): %s", fresh.kind, exc)
        raise

    record_sent(db, delivery, now=now)
    logger.info("메일 발송 완료 (kind=%s, delivery=%s)", delivery.kind, delivery.id)
