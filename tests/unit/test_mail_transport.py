"""메일 전송기 — 보안 연결 확인, 메일 머리, 연결 확인, 실패 분류 (계획 3.3, D-511).

못박는 것:
  * 기본 문맥은 서버 인증서와 호스트 이름을 확인한다. 끄는 것은 설정에서 명시적으로 고를 때만이다.
  * 사설 CA 원문(`ca_pem`)이 문맥에 들어간다. 저장할 때 못 읽는 원문과 보안 연결 없는 CA 는 거절한다.
  * 메일에는 Date · Message-ID · 자동 발송 표시가 붙고, 한글 이름이 든 보내는 사람도 주소가 깨지지 않는다.
  * 연결 확인은 메일을 보내지 않는다(본문 DATA 가 없다). 실패는 어느 단계였는지와 함께 종류로 나뉜다.
  * 발송은 단계로 간다(DNS → 연결 → 인사 → 보안 연결 → 인증 → 보내는 사람 → 받는 사람 → 본문)이고, 다음 서버가 본문을 받고
    준 응답 한 줄을 영수증으로 돌려준다. HTML 이 있으면 평문 다음에 붙인 multipart/alternative 다.

qa-contract-change: 연결 확인이 NOOP 대신 봉투 시험(MAIL FROM · RCPT TO · RSET)을 하고 단계 줄을 돌려주며(D-546), 발송이
Message-ID 문자열 대신 영수증(`SendReceipt`: Message-ID · 다음 서버의 응답)을 돌려준다. 가짜 서버가 새 단계를 받도록 바꿨고
(DNS 조회는 바꿔 끼운다), NOOP 단언은 「본문을 보내지 않는다」와 단계 줄 단언으로 옮겼다.

아래 인증서는 이 시험을 위해 만든 자체 서명 공개 인증서다(개인 키는 만든 자리에서 지웠다).
"""

from __future__ import annotations

import smtplib
import ssl

import pytest

from app.core.errors import ValidationAppError
from app.mail import transport
from app.mail.config import configuration_problems, smtp_config
from app.mail.transport import (
    MailTransportError,
    SendReceipt,
    SmtpTransport,
    build_message,
    classify,
    tls_context,
)

pytestmark = pytest.mark.unit

TEST_CA = """-----BEGIN CERTIFICATE-----
MIIDITCCAgmgAwIBAgIUMiG+62aFQ8kVVoCvRdbXPDA6vNwwDQYJKoZIhvcNAQEL
BQAwHzEdMBsGA1UEAwwUQ2xvdmlyQXNzaXN0IFRlc3QgQ0EwIBcNMjYwOTMwMDUy
MTAyWhgPMjEyNjA5MDYwNTIxMDJaMB8xHTAbBgNVBAMMFENsb3ZpckFzc2lzdCBU
ZXN0IENBMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAqSoBW0U2NM6B
nMJtVAbTQmPQnCOzelx+bmkrQ1zEMat9z/5DKlSRMnueuIO+HMtTa2DNDl/TsqwC
FsNWCiKLxHDg9AjoslQWHXHHoTu+Jw5t5KW3tjW5HFPZ27Ed2rMbIMCIkWhw6m1A
LXKqmxtTVmrTU9TXwQzWEW0wTy9sIkqzVVo8d61sKc4+20koTqT5LRnh4OPeEzx/
IP6ciejC6+WpuL/gb8Ocves3RgVljNHv7JN9Lu3aXZxllbgKelXWmoTPc2OLqTc8
Fo9AokND5LaugPyfD5XBpTeUBeUnnyYdXuQ8iqakwQD+Rcoee8yE+Xz57R6dRbLa
Hqo/rQyN2wIDAQABo1MwUTAdBgNVHQ4EFgQUSbrt1feoIo2NM75mFGaHIpScXcow
HwYDVR0jBBgwFoAUSbrt1feoIo2NM75mFGaHIpScXcowDwYDVR0TAQH/BAUwAwEB
/zANBgkqhkiG9w0BAQsFAAOCAQEAVhNVsOiiaNsLxUHkSopeKMmJUBGSJZQwfqkR
pr2kMLncXMfN/cnQWXE4kZuhf2DsWWLcleQl2PUTmP9g4n3OzI/t3bfJK9oBH4Iu
MBWr6awzm5LPgY28FWXwcJqK1NfdKc/E0cf1RToXdVobNs0ds0L46gStErwWL2Xa
h439YlWa/qOUS0cokIwB6m68d4SzK289xvxusVBQDXwXLEH/pW3ZBwnqmgdNHmbz
6MHs464DFfsdQvSdqoI3Ck6xYJkXj4hZOD3SHmQbM6lQXP+OpXX73ArwsCc/ayHu
IFKOroLOMQy4h/Gxd1nls1nEw6luAyJg0sn+knaAGb0wSe3e8A==
-----END CERTIFICATE-----"""


class _Secret:
    def reveal(self):
        return "not-a-real-password"


class _Secrets:
    def require(self, name):
        assert name == "smtp.password", "관리 화면이 저장한 슬롯을 쓰지 않았다"
        return _Secret()


class FakeServer:
    """smtplib.SMTP 자리에 끼우는 가짜. 부른 순서를 적는다."""

    last = None
    fail_at = None
    # 단계마다 서버가 돌려줄 (코드, 응답). 거절을 흉내 내려면 시험이 바꾼다.
    replies = {}
    does_esmtp = True

    def __init__(self, host, port, timeout=None, context=None, local_hostname=None):
        self.calls = [("connect", host, port)]
        # 인사(EHLO)에 쓸 이름(D-572) - 전송기가 설정의 서버 이름을 넘기는지 본다.
        self.local_hostname = local_hostname
        FakeServer.last = self

    def _step(self, name, *rest):
        self.calls.append((name, *rest))
        if FakeServer.fail_at == name:
            raise smtplib.SMTPAuthenticationError(535, b"5.7.8 bad credentials")

    def has_extn(self, name):
        return False

    def mail(self, sender, options=()):
        self.calls.append(("mail", sender))
        return FakeServer.replies.get("mail", (250, b"2.1.0 Ok"))

    def rcpt(self, recipient, options=()):
        self.calls.append(("rcpt", recipient))
        return FakeServer.replies.get("rcpt", (250, b"2.1.5 Ok"))

    def data(self, message):
        self.calls.append(("data", message))
        return FakeServer.replies.get("data", (250, b"2.0.0 Ok: queued as ABC123"))

    def rset(self):
        self.calls.append(("rset",))
        return (250, b"2.0.0 Ok")

    def ehlo(self):
        self._step("ehlo")

    def starttls(self, context=None):
        self._step("starttls", context)

    def login(self, user, password):
        self._step("login", user)

    def noop(self):
        self._step("noop")

    def send_message(self, message):
        self._step("send")

    def close(self):
        self.calls.append(("close",))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.calls.append(("quit",))
        return False


@pytest.fixture()
def fake_smtp(monkeypatch):
    FakeServer.fail_at = None
    FakeServer.replies = {}
    monkeypatch.setattr(transport.smtplib, "SMTP", FakeServer)
    # 가짜 서버 주소로 바깥 DNS 를 묻지 않는다 - DNS 단계는 이 함수 하나다.
    monkeypatch.setattr(transport, "_resolve", lambda host, port: [(None, None, None, "", (host, port))])
    return FakeServer


CONFIG = {
    "enabled": True, "host": "smtp.example.com", "port": 587, "security": "starttls",
    "from_address": "noreply@example.com", "from_name": "클로비어시스트, 알림", "username": "mailer",
}


def test_the_default_context_checks_the_certificate_and_the_host():
    ctx = tls_context(smtp_config(CONFIG))
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname is True
    # 모르는 값은 확인하는 쪽으로 떨어진다.
    assert tls_context(smtp_config({**CONFIG, "tls_verify": "no"})).verify_mode == ssl.CERT_REQUIRED


def test_turning_the_check_off_is_explicit():
    ctx = tls_context(smtp_config({**CONFIG, "tls_verify": False}))
    assert ctx.verify_mode == ssl.CERT_NONE and ctx.check_hostname is False


def test_a_private_ca_goes_into_the_context():
    ctx = tls_context(smtp_config({**CONFIG, "ca_pem": TEST_CA}))
    subjects = [dict(x[0] for x in c["subject"]) for c in ctx.get_ca_certs()]
    assert {"commonName": "ClovirAssist Test CA"} in subjects


def test_the_message_carries_the_headers_receivers_expect():
    msg = build_message(smtp_config(CONFIG), to_email="user@example.com", subject="제목", body="본문")
    sender = msg["From"].addresses[0]
    assert (sender.display_name, sender.addr_spec) == ("클로비어시스트, 알림", "noreply@example.com")
    assert msg["Date"]
    assert msg["Message-ID"].endswith("@example.com>")
    assert msg["Auto-Submitted"] == "auto-generated"
    assert msg["X-Auto-Response-Suppress"] == "All"


def _states(rows):
    return {row["key"]: row["state"] for row in rows}


def test_verify_never_sends_a_mail(fake_smtp):
    result = SmtpTransport().verify(smtp_config(CONFIG), _Secrets(), probe_recipient="admin@example.com")
    names = [c[0] for c in fake_smtp.last.calls]
    assert "data" not in names, "연결 확인이 본문을 보냈다"
    assert names[:5] == ["connect", "ehlo", "starttls", "ehlo", "login"]
    # 봉투 시험: 보내는 주소로 MAIL FROM, 확인을 누른 사람으로 RCPT TO, 그리고 RSET 으로 되돌린다.
    assert ("mail", "noreply@example.com") in fake_smtp.last.calls
    assert ("rcpt", "admin@example.com") in fake_smtp.last.calls
    assert names[-2:] == ["rset", "quit"]
    starttls = next(c for c in fake_smtp.last.calls if c[0] == "starttls")
    assert isinstance(starttls[1], ssl.SSLContext), "보안 연결에 확인 문맥을 주지 않았다"
    assert _states(result["stages"]) == {
        "dns": "ok", "connect": "ok", "tls": "ok", "auth": "ok", "sender": "ok", "recipient": "ok",
    }


def test_verify_skips_the_stages_the_setting_does_not_use(fake_smtp):
    """보안 연결 없이 · 로그인 없이 · 받는 사람 없이 확인하면 그 단계는 「정상」이 아니라 「건너뜀」이다."""
    plain = smtp_config({**CONFIG, "security": "none", "username": ""})
    result = SmtpTransport().verify(plain, _Secrets())
    states = _states(result["stages"])
    assert (states["tls"], states["auth"], states["recipient"]) == ("skipped", "skipped", "skipped")
    assert ("rcpt",) not in [c[:1] for c in fake_smtp.last.calls]


def test_send_returns_a_receipt_with_the_next_servers_reply(fake_smtp):
    receipt = SmtpTransport().send(smtp_config(CONFIG), _Secrets(), to_email="a@example.com", subject="s", body="b")
    assert isinstance(receipt, SendReceipt)
    assert receipt.message_id.startswith("<") and receipt.message_id.endswith("@example.com>")
    # 다음 서버의 응답 한 줄이다 - 「받은 편지함」이 아니라 「접수」의 증거다(D-555).
    assert receipt.response == "250 2.0.0 Ok: queued as ABC123"
    names = [c[0] for c in fake_smtp.last.calls]
    assert names.index("mail") < names.index("rcpt") < names.index("data")


def test_a_failure_says_which_stage_failed(fake_smtp):
    fake_smtp.fail_at = "login"
    with pytest.raises(MailTransportError) as caught:
        SmtpTransport().verify(smtp_config(CONFIG), _Secrets())
    assert (caught.value.kind, caught.value.permanent, caught.value.stage) == ("auth", True, "auth")
    assert ("close",) in fake_smtp.last.calls, "실패한 연결을 닫지 않았다"
    states = _states(caught.value.stages)
    assert (states["connect"], states["auth"], states["sender"]) == ("ok", "failed", "not_reached")
    assert caught.value.response == "535 5.7.8 bad credentials"


def test_a_dns_failure_is_the_dns_stage(fake_smtp, monkeypatch):
    import socket

    def no_such_host(host, port):
        raise socket.gaierror(11001, "getaddrinfo failed")

    monkeypatch.setattr(transport, "_resolve", no_such_host)
    with pytest.raises(MailTransportError) as caught:
        SmtpTransport().verify(smtp_config(CONFIG), _Secrets())
    assert (caught.value.kind, caught.value.stage) == ("connect", "dns")
    assert _states(caught.value.stages)["dns"] == "failed"
    assert _states(caught.value.stages)["connect"] == "not_reached"


@pytest.mark.parametrize("step, reply, stage, kind", [
    ("mail", (550, b"5.7.60 SMTP; Client does not have permissions to send as this sender"), "sender", "sender"),
    ("rcpt", (550, b"5.1.1 User unknown"), "recipient", "recipient"),
    ("data", (554, b"5.7.1 Message rejected as spam"), "data", "rejected"),
])
def test_a_refusal_names_its_stage_and_keeps_the_reply(fake_smtp, step, reply, stage, kind):
    fake_smtp.replies = {step: reply}
    with pytest.raises(MailTransportError) as caught:
        SmtpTransport().send(smtp_config(CONFIG), _Secrets(), to_email="a@example.com", subject="s", body="b")
    assert (caught.value.stage, caught.value.kind) == (stage, kind)
    assert caught.value.response.startswith(str(reply[0]))


def test_html_goes_after_the_text_as_an_alternative():
    msg = build_message(smtp_config(CONFIG), to_email="a@example.com", subject="제목", body="평문", html="<p>본문</p>")
    assert msg.get_content_type() == "multipart/alternative"
    parts = list(msg.iter_parts())
    assert [part.get_content_type() for part in parts] == ["text/plain", "text/html"]
    assert all(part.get_content_charset() == "utf-8" for part in parts)


@pytest.mark.parametrize("exc, expected", [
    (smtplib.SMTPAuthenticationError(535, b"bad"), ("auth", True)),
    (smtplib.SMTPAuthenticationError(454, b"try later"), ("temporary", False)),
    (smtplib.SMTPSenderRefused(550, b"no", "a@b"), ("sender", True)),
    (smtplib.SMTPRecipientsRefused({"a@b": (550, b"no such user")}), ("recipient", True)),
    (smtplib.SMTPRecipientsRefused({"a@b": (450, b"greylisted")}), ("temporary", False)),
    (smtplib.SMTPDataError(554, b"rejected"), ("rejected", True)),
    (smtplib.SMTPDataError(451, b"later"), ("temporary", False)),
    (smtplib.SMTPServerDisconnected("gone"), ("disconnected", False)),
    (ssl.SSLCertVerificationError("certificate verify failed"), ("tls", True)),
    (ConnectionRefusedError(), ("connect", False)),
    (TimeoutError(), ("connect", False)),
    (RuntimeError("?"), ("unknown", False)),
])
def test_failures_are_classified(exc, expected):
    assert classify(exc) == expected


def test_an_empty_password_name_means_the_saved_slot(tmp_path):
    from app.core.secret_refs import FileSecretReferenceProvider

    provider = FileSecretReferenceProvider(tmp_path)
    config = smtp_config(CONFIG)
    assert any("비밀번호" in p for p in configuration_problems(config, provider))
    (tmp_path / "smtp.password").write_text("x", encoding="utf-8")
    assert configuration_problems(config, provider) == []
    # 옛 설치가 적어 둔 이름은 더 이상 이기지 않는다(D-545) - 비밀번호는 언제나 고정 칸에서 읽는다.
    (tmp_path / "smtp.password").unlink()
    (tmp_path / "legacy_file").write_text("x", encoding="utf-8")
    legacy = smtp_config({**CONFIG, "password_ref": "legacy_file"})
    assert any("비밀번호" in p for p in configuration_problems(legacy, provider)), "옛 이름이 가리키는 파일로 로그인한다"


@pytest.mark.parametrize("patch, ok", [
    ({"ca_pem": TEST_CA}, True),
    ({"ca_pem": "\n".join(["-----BEGIN CERTIFICATE-----", "not a cert", "-----END CERTIFICATE-----"])}, False),
    ({"ca_pem": "hello"}, False),
    ({"ca_pem": TEST_CA, "security": "none"}, False),
    ({"tls_verify": "no"}, False),
    ({"tls_verify": False}, True),
    # D-545: 비밀번호 칸의 이름은 고를 수 없다. 빈 값(옛 모양)만 받는다.
    ({"password_ref": ""}, True),
    ({"password_ref": "ai.openai.api_key"}, False),
    ({"password_ref": "smtp.password"}, False),
    ({"relay_secret": "x"}, False),
    # 칸의 모양: 서버 주소는 이름이나 IP 만, 보내는 사람은 주소 모양, 이름 · 계정에는 줄바꿈이 없다.
    ({"host": "smtp.example.com"}, True),
    ({"host": "10.0.0.5"}, True),
    ({"host": "smtp://evil.example"}, False),
    ({"host": "smtp.example.com /x"}, False),
    ({"host": "user@evil.example"}, False),
    ({"from_address": "noreply@example.com"}, True),
    ({"from_address": "not-an-address"}, False),
    ({"from_address": "a@b.com\r\nBcc: x@y.com"}, False),
    ({"from_name": "알림\r\nBcc: x@y.com"}, False),
    ({"from_name": "가" * 101}, False),
    ({"username": "mailer\n"}, False),
])
def test_the_smtp_setting_validates_the_new_fields(patch, ok):
    from app.settings.registry import _smtp

    value = {"enabled": False, "port": 587, "security": "starttls", **patch}
    if ok:
        _smtp(value)
    else:
        with pytest.raises(ValidationAppError):
            _smtp(value)


def test_external_smtp_greets_with_the_configured_server_name(fake_smtp, monkeypatch):
    """D-572: 외부 SMTP 의 인사(EHLO) 이름은 설정의 서버 이름(HELO)이다 - 도메인 모양일 때만. 아니면 smtplib 기본값(None → 이 서버의 FQDN)."""
    named = {**CONFIG, "relay": {"helo_name": "clovirassist-mail.example.com"}}
    SmtpTransport().verify(smtp_config(named), _Secrets())
    assert fake_smtp.last.local_hostname == "clovirassist-mail.example.com"
    SmtpTransport().verify(smtp_config({**CONFIG, "relay": {"helo_name": "not a host name"}}), _Secrets())
    assert fake_smtp.last.local_hostname is None
    SmtpTransport().verify(smtp_config(CONFIG), _Secrets())
    assert fake_smtp.last.local_hostname is None
    # SSL 도 같다(연결과 함께 인사한다).
    monkeypatch.setattr(transport.smtplib, "SMTP_SSL", FakeServer)
    SmtpTransport().send(smtp_config({**named, "security": "ssl", "port": 465}), _Secrets(), to_email="u@example.com",
                         subject="s", body="b")
    assert fake_smtp.last.local_hostname == "clovirassist-mail.example.com"


def test_send_carries_only_the_known_extra_headers(fake_smtp):
    """D-571: 더할 머리는 이름을 골라 싣는다 - `Reply-To` · `List-Unsubscribe` 밖의 이름은 버린다(머리 주입의 문을 열지 않는다)."""
    import email

    SmtpTransport().send(smtp_config(CONFIG), _Secrets(), to_email="u@example.com", subject="s", body="b",
                         headers={"Reply-To": "help@example.com", "List-Unsubscribe": "<https://x.example.com/#/profile>",
                                  "Bcc": "evil@example.com"})
    raw = next(c[1] for c in fake_smtp.last.calls if c[0] == "data")
    message = email.message_from_bytes(raw)
    assert message["Reply-To"] == "help@example.com"
    assert message["List-Unsubscribe"] == "<https://x.example.com/#/profile>"
    assert message["Bcc"] is None and message["List-Unsubscribe-Post"] is None
