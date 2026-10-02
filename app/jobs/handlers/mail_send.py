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
app/mail/renderers.py 모듈 docstring 에 적어 뒀다. 평문과 HTML 두 부분을 함께 만든다(D-549).

## 보내려는 순간 설정이 없으면 「설정이 끝나지 않아 보내지 못함」이다 (D-546)

큐에 넣은 뒤 설정이 꺼졌거나 비밀번호 파일이 사라졌으면 큐에 넣을 때와 같은 `unconfigured` 로 적고 잡을 끝낸다.
예전에는 `failed/config` 로 적어 「설정 전에 쌓인 메일」과 갈라졌고, 설정을 마친 뒤 한꺼번에 다시 보낼 수 없었다.

## 다음 서버의 응답을 남긴다 (D-546 · D-555)

발송이 끝나면 다음 서버가 본문을 받고 준 응답 한 줄(`250 … queued as …`)을 행에 남기고, 실패면 실패한 단계와 그 응답을
남긴다. 접수는 「받은 편지함에 들어갔다」가 아니다 - 화면의 낱말이 그 차이를 지킨다(`app/mail/labels.py`).
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
    FAILURE_RENDER,
    FAILURE_UNKNOWN,
    MAIL_CANCELLED,
    MAIL_SENT,
    MAIL_SUPERSEDED,
    PENDING_MAIL_STATUSES,
    MailDelivery,
)
from app.mail import health
from app.mail.recipients import access_block, recipient_block
from app.mail.relevance import still_relevant
from app.mail.renderers import render_mail
from app.mail.service import (
    record_failure,
    record_sent,
    record_skipped,
    record_unconfigured,
    retry_delay_for,
    summarize_failure,
)

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
    # 1) 받는 사람이 아직 이 종류의 메일을 받아도 되는가(D-547) - 모든 종류다. 큐에 들어간 뒤 강등 · 보관되거나 결재
    #    권한을 잃었으면 보내지 않는다. 판정이 터지면 보내지 않는다(fail-closed, `app/mail/recipients.py`). 재시도 ·
    #    복구 재큐 · 수동 재발송도 전부 이 자리를 지난다.
    blocked = recipient_block(db, delivery, now)
    if blocked:
        record_skipped(db, delivery, status=MAIL_CANCELLED, reason=blocked, now=now)
        logger.info("mail %s 는 받는 사람 사정으로 보내지 않는다 (%s)", delivery.id, blocked)
        return
    # 2) 보내기 직전에 아직 의미가 있는가(계획 3.3 · 3.4). 장애가 길었으면 그 사이 초대받은 사람이 로그인했거나 승인이
    #    끝났을 수 있다 - 그런 메일은 보내지 않고 까닭과 함께 끝낸다. 재시도할 때마다 다시 본다. 이 판정은 터지면 보낸다.
    relevant, reason = still_relevant(db, delivery, now)
    if not relevant:
        record_skipped(db, delivery, status=MAIL_SUPERSEDED, reason=reason or "", now=now)
        logger.info("mail %s 는 의미가 없어져 보내지 않는다 (%s)", delivery.id, reason)
        return
    # 3) 알림 메일이면 받는 사람이 그 내용(티켓 · 문서 · 채팅방 · 승인)을 지금도 볼 수 있는가(D-547). 의미 판정과 달리
    #    판정이 터지면 보내지 않는다 - 볼 수 없는 사람에게 티켓 제목이 가는 것은 되돌릴 수 없다.
    blocked = access_block(db, delivery, now)
    if blocked:
        record_skipped(db, delivery, status=MAIL_CANCELLED, reason=blocked, now=now)
        logger.info("mail %s 는 받는 사람의 열람 권한 때문에 보내지 않는다 (%s)", delivery.id, blocked)
        return
    config = config_from_db(db)
    secret_provider = (ctx.extras or {}).get("secret_provider")
    problems = configuration_problems(config, secret_provider)
    if problems:
        # 큐에 넣은 뒤 설정이 꺼졌거나 지워졌거나 secret 파일이 사라진 경우다(머리말). 재시도해도 낫지 않으므로 잡은
        # 여기서 끝내되, 행은 큐에 넣을 때와 같은 `unconfigured` 로 두고 **왜인지는 아웃박스에 남긴다** - 설정을 마친 뒤
        # 「쌓인 메일 보내기」가 이 행을 다시 보낸다.
        record_unconfigured(db, delivery, problems=problems, now=now)
        logger.warning("메일 발송 설정이 끝나지 않아 보내지 않았다 (kind=%s): %s", delivery.kind, "; ".join(problems))
        return

    try:
        rendered = render_mail(db, delivery, ctx)
        receipt = _transport(ctx).send(
            config,
            secret_provider,
            to_email=delivery.to_email,
            subject=rendered.subject,
            body=rendered.text,
            html=rendered.html,
        )
    except Exception as exc:
        # 렌더 실패도 발송 실패와 같은 자리에서 잡는다 - 렌더가 만든 토큰 행은 이 롤백과
        # 함께 사라져야 한다. render_mail 이 밖에서 raise 하면 아웃박스 기록 없이 잡만
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
            stage=getattr(exc, "stage", None), response=getattr(exc, "response", None),
        )
        # 메일 서버 탓인 실패만 건강 상태를 바꾼다(`app/mail/health.py`) - 받는 사람 거부는 서버가 멀쩡하다는 뜻이다.
        health.record_result(
            db, config, ok=False, now=now, source="send", failure_kind=kind,
            stage=getattr(exc, "stage", None), summary=summarize_failure(f"{type(exc).__name__}: {exc}"),
            secret_provider=secret_provider,
        )
        db.commit()
        logger.warning("메일 발송 실패 (kind=%s, 종류=%s, 끝=%s): %s", fresh.kind, kind, terminal, exc)
        if permanent and not isinstance(exc, PermanentJobError):
            # 다시 보내도 같은 결과다. 잡도 즉시 끝낸다(재시도 일정을 태우지 않는다).
            raise PermanentJobError(f"{type(exc).__name__}: {exc}") from exc
        raise

    # 진짜 전송기는 영수증(`SendReceipt`: Message-ID · 다음 서버의 응답)을 돌려준다. 시험의 가짜 전송기는 문자열 하나나
    # 아무것도 안 돌려줄 수 있다.
    message_id = getattr(receipt, "message_id", None) or (receipt if isinstance(receipt, str) else None)
    record_sent(db, delivery, now=now, message_id=message_id, response=getattr(receipt, "response", None))
    health.record_result(db, config, ok=True, now=now, source="send", secret_provider=secret_provider)
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
