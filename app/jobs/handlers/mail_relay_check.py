"""mail_relay_check 잡 핸들러 — 로컬 릴레이 준비 점검 (계획 M7, D-551).

메일 화면의 「점검 다시 하기」가 이 잡을 넣고 결과를 폴링한다(`GET /api/admin/mail/relay/check/{job_id}`). 점검은 DNS 를 여러 번 묻고
받는 쪽 메일 서버의 25번에 붙어 보므로 웹 요청 안에서 하지 않는다. 화면 앞에서 기다리는 일이라 대화형 레인에서 돈다(`app/jobs/lanes.py`).

결과는 `sync_status["mail_relay"]` 에 남는다(`app/mail/relay_readiness.py`). **메일은 보내지 않는다** - 앱 → 릴레이와 상위 SMTP 는 봉투
시험(RSET)까지, 바깥 25번은 인사(EHLO)까지다. 다시 시도하지 않는다(`max_attempts=1`).
"""

from __future__ import annotations

import dataclasses
import json
import logging

from sqlalchemy.orm import Session

from app.jobs.exceptions import PermanentJobError
from app.jobs.models import Job
from app.jobs.worker import WorkerContext
from app.mail import relay_readiness
from app.mail.config import (
    MODE_EXTERNAL,
    PASSWORD_SLOT,
    config_from_db,
)

logger = logging.getLogger("app.handlers.mail_relay_check")

MAIL_RELAY_CHECK_JOB_TYPE = "mail_relay_check"
CHECK_TIMEOUT_SECONDS = 20


class _SlotAlias:
    """상위 SMTP 확인용 — 전송기가 읽는 로그인 비밀번호 칸을 상위 SMTP 비밀번호 칸으로 돌린다. 값을 다루지 않는다."""

    def __init__(self, provider, target: str) -> None:
        self._provider = provider
        self._target = target

    def _name(self, name: str) -> str:
        return self._target if name == PASSWORD_SLOT else name

    def require(self, name: str):
        return self._provider.require(self._name(name))

    def status(self, name: str) -> str:
        return self._provider.status(self._name(name))


def _extras(ctx: WorkerContext) -> dict:
    return ctx.extras or {}


def _client(ctx: WorkerContext):
    injected = _extras(ctx).get("sysops_client")
    if injected is not None:
        return injected
    from app.sysops.client import SysopsClient

    return SysopsClient()


def _transport(ctx: WorkerContext):
    injected = _extras(ctx).get("mail_transport")
    if injected is not None:
        return injected
    from app.mail.transport import SmtpTransport

    return SmtpTransport()


def _probe_domain(db: Session, job: Job, config) -> tuple[str, str | None]:
    """시험할 받는 도메인 — 넣은 값, 아니면 점검을 시작한 관리자의 메일 도메인, 아니면 보내는 도메인."""
    from app.users.models import User

    try:
        payload = json.loads(job.payload_json or "{}")
    except ValueError:
        payload = {}
    payload = payload if isinstance(payload, dict) else {}
    user = db.get(User, job.user_id) if job.user_id else None
    email = (user.email or "").strip().lower() if user is not None else ""
    chosen = str(payload.get("probe_domain") or "").strip().lower()
    domain = chosen or (email.rsplit("@", 1)[-1] if "@" in email else "") or config.sender_domain
    return domain, (email if email and email.isascii() else None)


def handle_mail_relay_check(db: Session, job: Job, ctx: WorkerContext) -> None:
    config = config_from_db(db)
    if not config.local_relay:
        raise PermanentJobError("로컬 릴레이를 쓰는 설정이 아니어서 점검하지 않았습니다.")
    secret_provider = _extras(ctx).get("secret_provider")
    capped = dataclasses.replace(config, timeout_seconds=min(int(config.timeout_seconds or 20), CHECK_TIMEOUT_SECONDS))
    probe_domain, probe_recipient = _probe_domain(db, job, config)
    db.commit()

    client = _client(ctx)
    status_params = {}
    if config.relay.dkim_selector and config.sender_domain:
        status_params = {"dkim": {"domain": config.sender_domain, "selector": config.relay.dkim_selector}}
    reply = client.call("mailrelay.status", status_params)
    helper_status = reply.data if reply.available and reply.ok else None
    transport = _transport(ctx)

    def app_verify() -> dict:
        return transport.verify(capped, secret_provider, probe_recipient=probe_recipient)

    def smarthost_verify() -> dict:
        from app.core.secret_slots import SLOT_SMTP_RELAY_PASSWORD

        sh = config.relay.smarthost
        upstream = dataclasses.replace(
            capped, mode=MODE_EXTERNAL, host=sh.host, port=sh.port, security=sh.security, username=sh.username,
            tls_verify=True, ca_pem="",
        )
        return transport.verify(upstream, _SlotAlias(secret_provider, SLOT_SMTP_RELAY_PASSWORD),
                                probe_recipient=probe_recipient)

    dns_factory = _extras(ctx).get("mail_dns_factory")
    if dns_factory is None:
        from app.mail.dns import MailDns

        dns_factory = MailDns
    mx_probe = _extras(ctx).get("mx_probe")
    if mx_probe is None:
        from app.mail.transport import probe_mx

        def mx_probe(host: str, helo: str) -> dict:
            return probe_mx(host, helo, timeout=CHECK_TIMEOUT_SECONDS)

    result = relay_readiness.run_checks(
        config, helper_status=helper_status, app_verify=app_verify, smarthost_verify=smarthost_verify,
        system_dns=dns_factory(), compare_dns=[dns_factory([ip]) for ip in config.relay.compare_resolvers],
        probe_domain=probe_domain, mx_probe=mx_probe,
    )
    relay_readiness.save(db, result, now=ctx.clock.now())
    db.commit()
    logger.info("로컬 릴레이 준비 점검: %s (%d줄)", result["state"], len(result["checks"]))
