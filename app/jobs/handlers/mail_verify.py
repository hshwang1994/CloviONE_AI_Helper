"""mail_verify 잡 핸들러 — 메일 서버 연결 확인 (계획 3.3, D-512).

관리 화면의 「연결 확인」이 이 잡을 넣고 결과를 폴링한다(`GET /api/admin/mail/verify/{job_id}`). 웹 요청 안에서
메일 서버에 붙지 않는 이유는 발송과 같다 — 느린 서버는 수십 초를 문다.

확인은 연결 · 보안 연결 · 로그인까지이고 **메일을 보내지 않는다**(`app/mail/transport.py::SmtpTransport.verify`).
결과는 건강 상태에 적힌다(`app/mail/health.py`). 실패는 사람이 읽는 한 문장으로 잡의 오류에 남아 폴링 응답이
그대로 보여 준다. 다시 시도하지 않는다(`max_attempts=1`) — 틀린 비밀번호는 몇 초 뒤에도 틀리다.
"""

from __future__ import annotations

import dataclasses
import logging

from sqlalchemy.orm import Session

from app.jobs.exceptions import PermanentJobError
from app.jobs.models import Job
from app.jobs.worker import WorkerContext
from app.mail import health
from app.mail.config import config_from_db, configuration_problems
from app.mail.models import FAILURE_UNKNOWN
from app.mail.service import summarize_failure

logger = logging.getLogger("app.handlers.mail_verify")

MAIL_VERIFY_JOB_TYPE = "mail_verify"
# 화면이 기다리는 확인이라 설정의 응답 대기 시간(최대 300초)보다 짧게 끊는다.
VERIFY_TIMEOUT_SECONDS = 30


def _transport(ctx: WorkerContext):
    injected = (ctx.extras or {}).get("mail_transport")
    if injected is not None:
        return injected
    from app.mail.transport import SmtpTransport

    return SmtpTransport()


def handle_mail_verify(db: Session, job: Job, ctx: WorkerContext) -> None:
    config = config_from_db(db)
    secret_provider = (ctx.extras or {}).get("secret_provider")
    problems = configuration_problems(config, secret_provider)
    if problems:
        raise PermanentJobError(problems[0])
    capped = dataclasses.replace(
        config, timeout_seconds=min(int(config.timeout_seconds or 20), VERIFY_TIMEOUT_SECONDS),
    )
    # 느린 바깥 호출 앞에서 스냅샷을 놓는다(워커의 DBTX 규율 - app/jobs/worker.py).
    db.commit()
    try:
        _transport(ctx).verify(capped, secret_provider)
    except Exception as exc:  # noqa: BLE001 - 어떤 실패든 상태와 잡에 사람의 말로 남긴다
        summary = summarize_failure(f"{type(exc).__name__}: {exc}") or "메일 서버 연결을 확인하지 못했습니다."
        health.record_result(
            db, config, ok=False, now=ctx.clock.now(), source="verify",
            failure_kind=getattr(exc, "kind", FAILURE_UNKNOWN), stage=getattr(exc, "stage", None),
            summary=summary, counts_any_failure=True,
        )
        db.commit()
        logger.warning("메일 연결 확인 실패: %s", exc)
        raise PermanentJobError(summary) from exc
    health.record_result(db, config, ok=True, now=ctx.clock.now(), source="verify")
