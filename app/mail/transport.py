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

`verify` 는 DNS 조회 · 연결 · EHLO · 보안 연결 · 로그인 · 봉투 시험(MAIL FROM · RCPT TO · RSET) · QUIT 까지만 한다. 본문(DATA)을
보내지 않으므로 메일이 한 통도 만들어지지 않는다 — 설정을 확인하려고 누군가의 받은 편지함을 쓰지 않는다. 지난 단계와 실패한
단계를 줄로 준다(D-546).

## 단계를 나눈다 (D-546)

발송도 단계로 간다: DNS 조회 → 서버 연결 → 인사 → 보안 연결 → 인증 → 보내는 사람(MAIL FROM) → 받는 사람(RCPT TO) → 본문(DATA).
`smtplib.sendmail` 한 번으로 보내면 어느 단계에서 막혔는지와 본문을 받은 서버의 응답(`250 … queued as …`)을 잃는다. 응답 한 줄은
발송 기록에 남고(`relay_response`), 그것은 「다음 서버가 받았다」이지 「받은 편지함에 들어갔다」가 아니다(D-555).
"""

from __future__ import annotations

import email.generator
import io
import logging
import re
import smtplib
import socket
import ssl
from dataclasses import dataclass
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

STAGE_DNS = "dns"
STAGE_CONNECT = "connect"
STAGE_GREETING = "greeting"
STAGE_TLS = "tls"
STAGE_AUTH = "auth"
STAGE_SENDER = "sender"
STAGE_RECIPIENT = "recipient"
STAGE_DATA = "data"

STAGE_OK = "ok"
STAGE_FAILED = "failed"
STAGE_SKIPPED = "skipped"
STAGE_NOT_REACHED = "not_reached"

# 서버 응답은 한 줄로 접어 이만큼만 남긴다(`mail_deliveries.relay_response`).
RESPONSE_MAX = 300


class MailTransportError(Exception):
    """발송 실패. 원인 문자열에 비밀이 섞이지 않게 호출부가 그대로 기록한다.

    `kind` 는 실패의 종류(`app/mail/models.py::FAILURE_*`), `permanent` 는 다시 보내도 같은 결과인가다.
    """

    def __init__(
        self, message: str, *, kind: str = FAILURE_UNKNOWN, permanent: bool = False, stage: str | None = None,
        response: str | None = None, stages: list[dict] | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.permanent = permanent
        self.stage = stage
        # 서버가 준 마지막 응답 한 줄(있을 때만). 화면에서는 기술 정보 안에만 보인다.
        self.response = response
        # 연결 확인의 단계 줄(`stage_rows`). 발송 실패에는 없다.
        self.stages = stages or []


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


def relay_tls_context(secret_provider) -> ssl.SSLContext:
    """로컬 릴레이로 가는 보안 연결(D-551). 서버 인증서는 릴레이가 켤 때 만든 그것 하나만 믿고(고정), 앱만 가진 클라이언트 열쇠를
    내민다 - 릴레이는 그 열쇠의 지문 하나만 중계를 허가한다. 사람이 고치는 칸이 없다."""
    from app.core.secret_slots import SLOT_SMTP_RELAY_CLIENT
    from app.mail.config import relay_server_cert

    pem = relay_server_cert()
    if not pem:
        raise ssl.SSLError("로컬 릴레이의 서버 인증서가 없습니다.")
    context = ssl.create_default_context(cadata=pem)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile=str(secret_provider.path(SLOT_SMTP_RELAY_CLIENT)))
    return context


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


def build_message(
    config: MailConfig, *, to_email: str, subject: str, body: str, html: str | None = None,
) -> EmailMessage:
    """보낼 메일 한 통. 받는 서버와 사람이 기대하는 머리를 갖춘다.

    - `From` 은 `formataddr` 가 만든다 - 이름에 한글이나 쉼표가 있어도 주소가 깨지지 않는다.
    - `Date` 와 `Message-ID` 가 없으면 받는 서버가 스팸 점수를 올리고, 반송이나 문의가 왔을 때 이 메일을 찾을
      단서가 없다. `Message-ID` 는 발송 기록에 남는다.
    - `Auto-Submitted` · `X-Auto-Response-Suppress` 는 자동 응답(부재 중 회신)이 이 발송함으로 돌아오지 않게 한다.
    - `html` 이 있으면 평문 다음에 HTML 을 붙인 `multipart/alternative` 다(D-549). 메일 앱은 마지막(가장 풍부한) 부분을
      고르고, HTML 을 못 그리는 앱과 사람이 읽는 원문은 평문을 본다. 둘 다 utf-8 이다.
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
    if html:
        message.add_alternative(html, subtype="html")
    return message


def _resolve(host: str, port: int):
    """DNS 조회 단계. 시험은 이 함수를 바꿔 끼운다(가짜 서버 주소로 바깥 DNS 를 묻지 않게)."""
    return socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)


def _response_text(code, message) -> str:
    """다음 서버의 응답 한 줄 — `250 2.0.0 Ok: queued as 4ABC` 처럼 코드와 글. 300자까지만 남긴다."""
    if isinstance(message, bytes):
        message = message.decode("utf-8", "replace")
    words = " ".join(str(message or "").split())
    return (f"{code} {words}" if code is not None else words).strip()[:RESPONSE_MAX]


def _exc_response(exc: BaseException) -> str | None:
    """예외가 싣고 온 서버 응답(있을 때만). 받는 사람 거부는 첫 받는 사람의 응답이다."""
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        for code, message in (exc.recipients or {}).values():
            return _response_text(code, message)
        return None
    code = getattr(exc, "smtp_code", None)
    if code is None:
        return None
    return _response_text(code, getattr(exc, "smtp_error", b""))


def _stage_of(trail: list[str], kind: str) -> str:
    """실패한 단계. 마지막으로 들어간 단계가 실패 자리다 — 다만 보안 연결 오류는 연결 단계(SSL 은 연결과 함께 맺는다)에서
    나도 「보안 연결」이고, 인사(EHLO) 실패는 화면에서 「서버 연결」이다."""
    last = trail[-1] if trail else STAGE_CONNECT
    if kind == FAILURE_TLS and last in (STAGE_CONNECT, STAGE_GREETING):
        return STAGE_TLS
    if last == STAGE_GREETING:
        return STAGE_CONNECT
    return last


def stage_rows(trail: list[str], *, failed_at: str | None = None, detail: str | None = None,
               skipped: frozenset[str] | set[str] = frozenset()) -> list[dict]:
    """연결 확인이 지난 단계 → 화면의 줄(`app/mail/labels.py::VERIFY_STAGES` 순서). 상태는 ok · failed · skipped · not_reached.

    보내는 방식이 지나지 않는 단계(보안 연결 없음, 로그인 없음, 받는 사람 확인 없음)는 `skipped` 다 — 「정상」이라고 말하지
    않는다. 실패한 단계 뒤의 단계는 `not_reached` 다.
    """
    from app.mail.labels import VERIFY_STAGES

    reached = {STAGE_CONNECT if key == STAGE_GREETING else key for key in trail}
    failed_index = VERIFY_STAGES.index(failed_at) if failed_at in VERIFY_STAGES else None
    rows: list[dict] = []
    for index, key in enumerate(VERIFY_STAGES):
        if key in skipped:
            state, text = STAGE_SKIPPED, None
        elif failed_index is not None and index == failed_index:
            state, text = STAGE_FAILED, detail
        elif failed_index is not None and index > failed_index:
            state, text = STAGE_NOT_REACHED, None
        elif key in reached:
            state, text = STAGE_OK, None
        else:
            state, text = STAGE_NOT_REACHED, None
        rows.append({"key": key, "state": state, "detail": text})
    return rows


def _reset_quietly(server, code) -> None:
    """거절 뒤 연결을 정리한다(smtplib.sendmail 과 같은 규칙: 421 이면 닫고, 아니면 RSET)."""
    try:
        if code == 421:
            server.close()
        else:
            server.rset()
    except (smtplib.SMTPException, OSError):
        pass


def _flatten(message: EmailMessage, international: bool) -> bytes:
    """`smtplib.SMTP.send_message` 와 같은 방식으로 메일을 바이트로 편다(줄 끝 CRLF, 비ASCII 주소면 utf8 정책)."""
    buffer = io.BytesIO()
    policy = message.policy.clone(utf8=True) if international else None
    generator = email.generator.BytesGenerator(buffer, policy=policy) if policy else email.generator.BytesGenerator(buffer)
    generator.flatten(message, linesep="\r\n")
    return buffer.getvalue()


@dataclass(frozen=True)
class SendReceipt:
    """보낸 결과. `response` 는 다음 서버가 본문을 받고 준 응답 한 줄이다(로컬 릴레이면 `queued as <큐 id>` 가 든다).

    이것은 「다음 서버가 받았다」이지 「받은 편지함에 들어갔다」가 아니다(D-555).
    """

    message_id: str
    response: str | None = None


_BRACKET_IP = re.compile(r"\[(\d{1,3}(?:\.\d{1,3}){3})\]")


def probe_mx(host: str, helo: str | None = None, *, port: int = 25, timeout: int = 10) -> dict:
    """받는 쪽 메일 서버의 25번에 붙어 인사(EHLO)만 하고 끊는다 — **메일은 보내지 않는다**(MAIL 명령이 없다).

    로컬 릴레이의 「인터넷으로 직접 전달」 준비 점검이 쓴다(D-551): 바깥 25번이 열려 있는지, 받는 쪽이 이 서버를 어떤 주소로 보는지
    (인사말의 `Hello [x.x.x.x]`)를 잰다. 실패는 예외가 아니라 결과의 `error` 다.
    """
    result: dict = {"host": host, "connected": False, "banner": None, "ehlo": None, "egress_ip": None, "error": None}
    server = None
    try:
        server = smtplib.SMTP(timeout=timeout, local_hostname=helo or None)
        code, banner = server.connect(host, port)
        result["connected"] = True
        result["banner"] = _response_text(code, banner)
        code, reply = server.ehlo()
        text = reply.decode("utf-8", "replace") if isinstance(reply, bytes) else str(reply or "")
        result["ehlo"] = _response_text(code, text.splitlines()[0] if text else "")
        found = _BRACKET_IP.search(text)
        if found:
            result["egress_ip"] = found.group(1)
        server.quit()
    except (smtplib.SMTPException, OSError) as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"[:RESPONSE_MAX]
        if server is not None:
            try:
                server.close()
            except OSError:
                pass
    return result


class SmtpTransport:
    """실제 발송기. 워커에서만 인스턴스가 만들어진다(app/worker_main.py).

    테스트와 진단은 같은 모양의 다른 객체를 끼운다 - 그래서 ``send`` · ``verify`` 시그니처가 계약이다.
    """

    def _open_relay(self, config: MailConfig, secret_provider, trail: list[str]):
        """로컬 릴레이(127.0.0.1:2525)에 붙는다 — 이름 찾기와 로그인이 없고, 보안 연결은 언제나 맺는다(D-551)."""
        from app.mail import relay_files

        timeout = max(1, int(config.timeout_seconds or 20))
        trail.append(STAGE_CONNECT)
        server = smtplib.SMTP(relay_files.RELAY_HOST, relay_files.RELAY_PORT, timeout=timeout)
        try:
            trail.append(STAGE_GREETING)
            server.ehlo()
            trail.append(STAGE_TLS)
            server.starttls(context=relay_tls_context(secret_provider))
            server.ehlo()
        except BaseException:
            server.close()
            raise
        return server

    def _open(self, config: MailConfig, secret_provider, trail: list[str]):
        """이름을 찾고 연결하고 인사하고 보안 연결을 맺고 로그인한다. 들어간 단계를 `trail` 에 적는다."""
        if getattr(config, "local_relay", False):
            return self._open_relay(config, secret_provider, trail)
        timeout = max(1, int(config.timeout_seconds or 20))
        trail.append(STAGE_DNS)
        _resolve(config.host, config.port)
        trail.append(STAGE_CONNECT)
        if config.security == SECURITY_SSL:
            server = smtplib.SMTP_SSL(config.host, config.port, timeout=timeout, context=tls_context(config))
            # SSL 은 연결과 함께 보안 연결을 맺는다 - 여기까지 왔으면 그 단계도 지났다.
            trail.append(STAGE_TLS)
        else:
            server = smtplib.SMTP(config.host, config.port, timeout=timeout)
        try:
            trail.append(STAGE_GREETING)
            server.ehlo()
            if config.security == SECURITY_STARTTLS:
                trail.append(STAGE_TLS)
                server.starttls(context=tls_context(config))
                server.ehlo()
            if config.username:
                trail.append(STAGE_AUTH)
                secret = secret_provider.require(PASSWORD_SLOT)
                # reveal() 은 여기 한 줄에서만. 위로도 아래로도 새지 않는다.
                server.login(config.username, secret.reveal())
        except BaseException:
            server.close()
            raise
        return server

    def _envelope(self, server, sender: str, recipient: str | None, trail: list[str], options=()) -> None:
        """봉투 — 보내는 사람과 받는 사람을 서버에 묻는다. 거절이면 smtplib 의 같은 예외로 올린다."""
        trail.append(STAGE_SENDER)
        code, message = server.mail(sender, options)
        if code != 250:
            _reset_quietly(server, code)
            raise smtplib.SMTPSenderRefused(code, message, sender)
        if recipient:
            trail.append(STAGE_RECIPIENT)
            code, message = server.rcpt(recipient)
            if code not in (250, 251):
                _reset_quietly(server, code)
                raise smtplib.SMTPRecipientsRefused({recipient: (code, message)})

    def send(
        self,
        config: MailConfig,
        secret_provider,
        *,
        to_email: str,
        subject: str,
        body: str,
        html: str | None = None,
    ) -> SendReceipt:
        """보낸다. 보낸 메일의 `Message-ID` 와 다음 서버의 응답 한 줄을 돌려준다."""
        message = build_message(config, to_email=to_email, subject=subject, body=body, html=html)
        trail: list[str] = []
        try:
            server = self._open(config, secret_provider, trail)
            with server:
                international = not (config.from_address.isascii() and to_email.isascii())
                flat = _flatten(message, international)
                options: list[str] = []
                if international:
                    if not server.has_extn("smtputf8"):
                        raise smtplib.SMTPNotSupportedError("이 서버는 ASCII 가 아닌 주소를 받지 않습니다.")
                    options += ["SMTPUTF8", "BODY=8BITMIME"]
                if getattr(server, "does_esmtp", False) and server.has_extn("size"):
                    options.append(f"size={len(flat)}")
                self._envelope(server, config.from_address, to_email, trail, options)
                trail.append(STAGE_DATA)
                code, reply = server.data(flat)
                if code != 250:
                    _reset_quietly(server, code)
                    raise smtplib.SMTPDataError(code, reply)
                response = _response_text(code, reply)
        except (smtplib.SMTPException, OSError) as exc:
            # 연결 거부, DNS 실패, 타임아웃, 인증서 오류는 SMTPException 이 아니라 OSError 로 온다.
            kind, permanent = classify(exc)
            raise MailTransportError(
                f"{type(exc).__name__}: {exc}", kind=kind, permanent=permanent,
                stage=_stage_of(trail, kind), response=_exc_response(exc),
            ) from exc
        return SendReceipt(message_id=str(message["Message-ID"]), response=response)

    def verify(self, config: MailConfig, secret_provider, *, probe_recipient: str | None = None) -> dict:
        """연결을 확인한다 — **메일은 보내지 않는다**(모듈 머리말). 단계 줄을 돌려준다.

        로그인 뒤 봉투 시험을 한다: 보내는 주소로 MAIL FROM, 확인을 누른 사람의 주소로 RCPT TO, 그리고 RSET(본문 없음).
        로그인은 되는데 보내는 주소를 쓸 권한이 없거나(M365 `SendAsDenied`) 중계가 막힌 설정은 여기서 드러난다.
        """
        trail: list[str] = []
        skipped = set()
        if getattr(config, "local_relay", False):
            # 로컬 릴레이는 고정 주소라 이름을 찾지 않고, 계정 대신 클라이언트 인증서로 허가받는다.
            skipped.update({STAGE_DNS, STAGE_AUTH})
        else:
            if config.security not in (SECURITY_STARTTLS, SECURITY_SSL):
                skipped.add(STAGE_TLS)
            if not config.username:
                skipped.add(STAGE_AUTH)
        if not probe_recipient:
            skipped.add(STAGE_RECIPIENT)
        try:
            server = self._open(config, secret_provider, trail)
            with server:
                self._envelope(server, config.from_address, probe_recipient, trail)
                server.rset()
        except (smtplib.SMTPException, OSError) as exc:
            kind, permanent = classify(exc)
            stage = _stage_of(trail, kind)
            raise MailTransportError(
                f"{type(exc).__name__}: {exc}", kind=kind, permanent=permanent, stage=stage,
                response=_exc_response(exc),
                stages=stage_rows(trail, failed_at=stage, skipped=skipped),
            ) from exc
        return {"ok": True, "stages": stage_rows(trail, skipped=skipped)}
