"""SMTP 단일 관문 (9-9 P4). **이 저장소에서 smtplib 를 import 하는 유일한 파일이다.**

## 왜 한 곳으로 모으는가

아웃바운드 HTTP 를 `app/core/http_client.py` 하나로 모은 것과 같은 이유다(불변 §2 규칙 2).
여기저기서 SMTP 를 열면 (1) 타임아웃, TLS 정책이 파일마다 달라지고 (2) 언젠가 웹 요청
안에서 보내게 되며 (3) 비밀번호를 secret 파일이 아닌 곳에서 읽는 경로가 생긴다.
`tests/integration/test_mail_delivery.py` 가 이 경계를 못박는다.

## 비밀번호는 고정 칸에서, 값은 SecretValue 로

DB 에는 비밀번호도 그 이름도 없다. 값은 언제나 고정 칸 ``SECRETS_DIR/smtp.password`` 파일이다(불변 §3, D-545) -
설정이 다른 비밀의 이름을 가리켜 그 비밀로 남의 서버에 로그인하게 만드는 길을 막는다(`app/mail/config.py`).
``SecretValue`` 는 repr/str 이 ``***`` 라 로그나 예외 메시지에 실수로 섞여도 새지 않는다.
그래서 ``.reveal()`` 은 ``login()`` 인자로 넘기는 그 한 줄에서만 부른다.

## 실패를 종류로 나눈다 (계획 3.3)

다시 보내면 될 실패(연결 실패, 시간 초과, 4xx 임시 거절, 연결 끊김)와 다시 보내도 같은 결과인 실패(로그인
거부, 보안 연결, 보내는 사람과 받는 사람 거부, 그 밖의 5xx)는 처리가 다르다. 앞의 것은 큐가 재시도 일정대로
다시 보내고, 뒤의 것은 즉시 끝내고 사람이 고친다. 그 판정은 SMTP 응답 코드와 예외를 아는 이 파일만 할 수 있다.

## 서버 인증서를 확인한다 (계획 3.3)

예전에는 `starttls()` 와 `SMTP_SSL` 에 문맥을 주지 않아 서버 인증서도 호스트 이름도 보지 않았다(파이썬 기본값).
이제 기본 문맥(`ssl.create_default_context`)이 둘 다 본다. 사설 CA 는 설정의 `ca_pem` 이 더하고, 확인을 끄는
것은 설정에서 명시적으로 고를 때만이다(`tls_verify=false`). 업그레이드 뒤 자체 서명 릴레이가 실패하기 시작하면
상태 화면이 그 사실을 보이고, 고치는 길은 CA 붙여 넣기나 명시적 끄기다 — 몰래 끄지 않는다.

## 연결 확인은 보내지 않는다

`verify` 는 연결 · EHLO · 보안 연결 · 로그인 · NOOP · QUIT 까지만 한다. 메일을 한 통도 만들지 않는다 — 설정을
확인하려고 누군가의 받은 편지함을 쓰지 않는다. 어느 단계에서 실패했는지(`stage`)를 함께 준다.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from app.mail.config import PASSWORD_SLOT, SECURITY_SSL, SECURITY_STARTTLS, MailConfig
from app.mail.models import (
    FAILURE_AUTH,
    FAILURE_CONNECT,
    FAILURE_DISCONNECTED,
    FAILURE_RECIPIENT,
    FAILURE_REJECTED,
    FAILURE_SENDER,
    FAILURE_TEMPORARY,
    FAILURE_TLS,
    FAILURE_UNKNOWN,
)

logger = logging.getLogger("app.mail.transport")


class MailTransportError(Exception):
    """발송 실패. 원인 문자열에 비밀이 섞이지 않게 호출부가 그대로 기록한다.

    `kind` 는 실패의 종류(`app/mail/models.py::FAILURE_*`), `permanent` 는 다시 보내도 같은 결과인가다.
    """

    def __init__(
        self, message: str, *, kind: str = FAILURE_UNKNOWN, permanent: bool = False, stage: str | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.permanent = permanent
        self.stage = stage


def _by_code(code, kind: str) -> tuple[str, bool]:
    """SMTP 응답 코드로 영구와 일시를 가른다. 4xx 는 임시 거절이라 같은 종류여도 다시 보낸다."""
    try:
        value = int(code)
    except (TypeError, ValueError):
        return kind, True
    if 400 <= value < 500:
        return FAILURE_TEMPORARY, False
    return kind, True


def classify(exc: BaseException) -> tuple[str, bool]:
    """예외 하나를 `(종류, 영구인가)` 로 나눈다. 모르는 것은 일시 실패로 본다 - 한 번 더 보내 보는 쪽이
    조용히 버리는 쪽보다 낫고, 재시도 횟수에 끝이 있다."""
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return _by_code(exc.smtp_code, FAILURE_AUTH)
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return _by_code(exc.smtp_code, FAILURE_SENDER)
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        codes = [c for c, _msg in (exc.recipients or {}).values()]
        if codes and all(400 <= int(c) < 500 for c in codes):
            return FAILURE_TEMPORARY, False
        return FAILURE_RECIPIENT, True
    if isinstance(exc, smtplib.SMTPNotSupportedError):
        # STARTTLS 나 AUTH 를 서버가 모른다 - 설정(보안 방식, 포트)을 고쳐야 한다.
        return FAILURE_TLS, True
    if isinstance(exc, smtplib.SMTPServerDisconnected):
        return FAILURE_DISCONNECTED, False
    if isinstance(exc, smtplib.SMTPConnectError):
        return _by_code(exc.smtp_code, FAILURE_CONNECT) if exc.smtp_code >= 500 else (FAILURE_CONNECT, False)
    if isinstance(exc, smtplib.SMTPResponseException):
        return _by_code(exc.smtp_code, FAILURE_REJECTED)
    if isinstance(exc, ssl.SSLError):
        return FAILURE_TLS, True
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return FAILURE_CONNECT, False
    return FAILURE_UNKNOWN, False


def tls_context(config: MailConfig) -> ssl.SSLContext:
    """보안 연결 문맥. 기본은 인증서와 호스트 이름을 모두 확인한다(모듈 머리말)."""
    context = ssl.create_default_context(cadata=config.ca_pem or None)
    if not config.tls_verify:
        # 설정에서 명시적으로 끈 경우만이다. 이름 확인을 먼저 꺼야 확인 모드를 내릴 수 있다(ssl 모듈 규칙).
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


def _domain_of(address: str) -> str | None:
    return address.rsplit("@", 1)[1] if "@" in (address or "") else None


def build_message(config: MailConfig, *, to_email: str, subject: str, body: str) -> EmailMessage:
    """보낼 메일 한 통. 받는 서버와 사람이 기대하는 머리를 갖춘다.

    - `From` 은 `formataddr` 가 만든다 - 이름에 한글이나 쉼표가 있어도 주소가 깨지지 않는다.
    - `Date` 와 `Message-ID` 가 없으면 받는 서버가 스팸 점수를 올리고, 반송이나 문의가 왔을 때 이 메일을 찾을
      단서가 없다. `Message-ID` 는 발송 기록에 남는다.
    - `Auto-Submitted` · `X-Auto-Response-Suppress` 는 자동 응답(부재 중 회신)이 이 발송함으로 돌아오지 않게 한다.
    """
    message = EmailMessage()
    message["From"] = formataddr((config.from_name, config.from_address)) if config.from_name else config.from_address
    message["To"] = to_email
    message["Subject"] = subject
    message["Date"] = formatdate(usegmt=True)
    message["Message-ID"] = make_msgid(domain=_domain_of(config.from_address))
    message["Auto-Submitted"] = "auto-generated"
    message["X-Auto-Response-Suppress"] = "All"
    message.set_content(body)
    return message


class SmtpTransport:
    """실제 발송기. 워커에서만 인스턴스가 만들어진다(app/worker_main.py).

    테스트와 진단은 같은 모양의 다른 객체를 끼운다 - 그래서 ``send`` 시그니처가 계약이다.
    """

    def _open(self, config: MailConfig, secret_provider, stages: list[str]):
        """연결하고 인사하고 보안 연결을 맺고 로그인한다. 지나간 단계를 `stages` 에 적는다."""
        timeout = max(1, int(config.timeout_seconds or 20))
        stages.append("connect")
        if config.security == SECURITY_SSL:
            server = smtplib.SMTP_SSL(config.host, config.port, timeout=timeout, context=tls_context(config))
        else:
            server = smtplib.SMTP(config.host, config.port, timeout=timeout)
        try:
            stages.append("ehlo")
            server.ehlo()
            if config.security == SECURITY_STARTTLS:
                stages.append("tls")
                server.starttls(context=tls_context(config))
                server.ehlo()
            if config.username:
                stages.append("auth")
                secret = secret_provider.require(PASSWORD_SLOT)
                # reveal() 은 여기 한 줄에서만. 위로도 아래로도 새지 않는다.
                server.login(config.username, secret.reveal())
        except BaseException:
            server.close()
            raise
        return server

    def send(
        self,
        config: MailConfig,
        secret_provider,
        *,
        to_email: str,
        subject: str,
        body: str,
    ) -> str:
        """보낸다. 보낸 메일의 `Message-ID` 를 돌려준다."""
        message = build_message(config, to_email=to_email, subject=subject, body=body)
        stages: list[str] = []
        try:
            server = self._open(config, secret_provider, stages)
            with server:
                stages.append("send")
                server.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            # 연결 거부, DNS 실패, 타임아웃, 인증서 오류는 SMTPException 이 아니라 OSError 로 온다.
            kind, permanent = classify(exc)
            raise MailTransportError(
                f"{type(exc).__name__}: {exc}", kind=kind, permanent=permanent,
                stage=stages[-1] if stages else None,
            ) from exc
        return str(message["Message-ID"])

    def verify(self, config: MailConfig, secret_provider) -> dict:
        """연결을 확인한다 — **메일은 보내지 않는다**(모듈 머리말). 지나간 단계를 돌려준다."""
        stages: list[str] = []
        try:
            server = self._open(config, secret_provider, stages)
            with server:
                stages.append("noop")
                server.noop()
        except (smtplib.SMTPException, OSError) as exc:
            kind, permanent = classify(exc)
            raise MailTransportError(
                f"{type(exc).__name__}: {exc}", kind=kind, permanent=permanent,
                stage=stages[-1] if stages else None,
            ) from exc
        return {"ok": True, "stages": stages}
