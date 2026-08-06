"""SMTP 단일 관문 (9-9 P4). **이 저장소에서 smtplib 를 import 하는 유일한 파일이다.**

## 왜 한 곳으로 모으는가

아웃바운드 HTTP 를 `app/core/http_client.py` 하나로 모은 것과 같은 이유다(불변 §2 규칙 2).
여기저기서 SMTP 를 열면 (1) 타임아웃, TLS 정책이 파일마다 달라지고 (2) 언젠가 웹 요청
안에서 보내게 되며 (3) 비밀번호를 secret 파일이 아닌 곳에서 읽는 경로가 생긴다.
`tests/integration/test_mail_delivery.py` 가 이 경계를 못박는다.

## 비밀번호는 파일에서, 값은 SecretValue 로

DB 에는 이름(``password_ref``)만 있고 값은 ``SECRETS_DIR/<ref>`` 파일이다(불변 §3).
``SecretValue`` 는 repr/str 이 ``***`` 라 로그나 예외 메시지에 실수로 섞여도 새지 않는다.
그래서 ``.reveal()`` 은 ``login()`` 인자로 넘기는 그 한 줄에서만 부른다.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.mail.config import SECURITY_SSL, SECURITY_STARTTLS, MailConfig

logger = logging.getLogger("app.mail.transport")


class MailTransportError(Exception):
    """발송 실패. 원인 문자열에 비밀이 섞이지 않게 호출부가 그대로 기록한다."""


def build_message(config: MailConfig, *, to_email: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = config.from_header
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    return message


class SmtpTransport:
    """실제 발송기. 워커에서만 인스턴스가 만들어진다(app/worker_main.py).

    테스트와 진단은 같은 모양의 다른 객체를 끼운다 - 그래서 ``send`` 시그니처가 계약이다.
    """

    def send(
        self,
        config: MailConfig,
        secret_provider,
        *,
        to_email: str,
        subject: str,
        body: str,
    ) -> None:
        message = build_message(config, to_email=to_email, subject=subject, body=body)
        timeout = max(1, int(config.timeout_seconds or 20))
        try:
            if config.security == SECURITY_SSL:
                server = smtplib.SMTP_SSL(config.host, config.port, timeout=timeout)
            else:
                server = smtplib.SMTP(config.host, config.port, timeout=timeout)
            with server:
                server.ehlo()
                if config.security == SECURITY_STARTTLS:
                    server.starttls()
                    server.ehlo()
                if config.username:
                    secret = secret_provider.require(config.password_ref)
                    # reveal() 은 여기 한 줄에서만. 위로도 아래로도 새지 않는다.
                    server.login(config.username, secret.reveal())
                server.send_message(message)
        except smtplib.SMTPException as exc:
            raise MailTransportError(f"{type(exc).__name__}: {exc}") from exc
        except OSError as exc:
            # 연결 거부, DNS 실패, 타임아웃. SMTPException 이 아니라 OSError 로 온다.
            raise MailTransportError(f"{type(exc).__name__}: {exc}") from exc
