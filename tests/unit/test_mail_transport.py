"""메일 전송기 — 보안 연결 확인, 메일 머리, 연결 확인, 실패 분류 (계획 3.3, D-511).

못박는 것:
  * 기본 문맥은 서버 인증서와 호스트 이름을 확인한다. 끄는 것은 설정에서 명시적으로 고를 때만이다.
  * 사설 CA 원문(`ca_pem`)이 문맥에 들어간다. 저장할 때 못 읽는 원문과 보안 연결 없는 CA 는 거절한다.
  * 메일에는 Date · Message-ID · 자동 발송 표시가 붙고, 한글 이름이 든 보내는 사람도 주소가 깨지지 않는다.
  * 연결 확인은 메일을 보내지 않는다. 실패는 어느 단계였는지와 함께 종류로 나뉜다.

아래 인증서는 이 시험을 위해 만든 자체 서명 공개 인증서다(개인 키는 만든 자리에서 지웠다).
"""

from __future__ import annotations

import smtplib
import ssl

import pytest

from app.core.errors import ValidationAppError
from app.mail import transport
from app.mail.config import configuration_problems, smtp_config
from app.mail.transport import MailTransportError, SmtpTransport, build_message, classify, tls_context

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

    def __init__(self, host, port, timeout=None, context=None):
        self.calls = [("connect", host, port)]
        FakeServer.last = self

    def _step(self, name, *rest):
        self.calls.append((name, *rest))
        if FakeServer.fail_at == name:
            raise smtplib.SMTPAuthenticationError(535, b"5.7.8 bad credentials")

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
    monkeypatch.setattr(transport.smtplib, "SMTP", FakeServer)
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


def test_verify_never_sends_a_mail(fake_smtp):
    result = SmtpTransport().verify(smtp_config(CONFIG), _Secrets())
    names = [c[0] for c in fake_smtp.last.calls]
    assert "send" not in names, "연결 확인이 메일을 보냈다"
    assert names[:5] == ["connect", "ehlo", "starttls", "ehlo", "login"]
    assert "noop" in names and names[-1] == "quit"
    starttls = next(c for c in fake_smtp.last.calls if c[0] == "starttls")
    assert isinstance(starttls[1], ssl.SSLContext), "보안 연결에 확인 문맥을 주지 않았다"
    assert result["stages"][-1] == "noop"


def test_send_returns_the_message_id(fake_smtp):
    sent = SmtpTransport().send(smtp_config(CONFIG), _Secrets(), to_email="a@example.com", subject="s", body="b")
    assert sent.startswith("<") and sent.endswith("@example.com>")
    assert ("send",) in fake_smtp.last.calls


def test_a_failure_says_which_stage_failed(fake_smtp):
    fake_smtp.fail_at = "login"
    with pytest.raises(MailTransportError) as caught:
        SmtpTransport().verify(smtp_config(CONFIG), _Secrets())
    assert (caught.value.kind, caught.value.permanent, caught.value.stage) == ("auth", True, "auth")
    assert ("close",) in fake_smtp.last.calls, "실패한 연결을 닫지 않았다"


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
    # 옛 설치가 적어 둔 이름은 그대로 이긴다.
    legacy = smtp_config({**CONFIG, "password_ref": "legacy_file"})
    assert legacy.effective_password_ref == "legacy_file"


@pytest.mark.parametrize("patch, ok", [
    ({"ca_pem": TEST_CA}, True),
    ({"ca_pem": "\n".join(["-----BEGIN CERTIFICATE-----", "not a cert", "-----END CERTIFICATE-----"])}, False),
    ({"ca_pem": "hello"}, False),
    ({"ca_pem": TEST_CA, "security": "none"}, False),
    ({"tls_verify": "no"}, False),
    ({"tls_verify": False}, True),
])
def test_the_smtp_setting_validates_the_new_fields(patch, ok):
    from app.settings.registry import _smtp

    value = {"enabled": False, "port": 587, "security": "starttls", **patch}
    if ok:
        _smtp(value)
    else:
        with pytest.raises(ValidationAppError):
            _smtp(value)
