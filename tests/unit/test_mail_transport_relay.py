"""앱 → 로컬 릴레이 전송 (계획 M7, D-551).

못박는 것:
  * 로컬 릴레이 방식이면 이름 찾기 없이 127.0.0.1:2525 에 붙고, 언제나 STARTTLS 를 맺으며 로그인하지 않는다.
  * 보안 연결은 릴레이의 서버 인증서 하나만 믿고(고정 - 다른 인증서는 거절), 앱의 클라이언트 열쇠를 내민다.
  * 서버 인증서가 없으면(릴레이가 켜진 적이 없으면) 보안 연결 단계의 실패다.
  * 연결 확인의 단계 줄은 DNS 조회 · 인증을 건너뜀으로 보인다(「정상」이라고 말하지 않는다).
  * MX 25번 시험은 인사만 하고 끊으며(MAIL 없음) 받는 쪽이 보는 바깥 IP 를 인사말에서 읽는다.

실제 Postfix 와의 연결은 `scripts/ui_qa/relay_systemd_e2e.py` 가 잰다.
"""

from __future__ import annotations

import smtplib
import ssl

import pytest

from app.mail import relay_certs, relay_files, transport
from app.mail.config import smtp_config


class FakeSmtp:
    instances: list = []

    def __init__(self, host=None, port=None, timeout=None, local_hostname=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.calls: list = []
        self.context = None
        FakeSmtp.instances.append(self)

    def ehlo(self, name=None):
        self.calls.append("ehlo")
        return 250, b"relay"

    def starttls(self, context=None):
        self.calls.append("starttls")
        self.context = context
        return 220, b"ready"

    def login(self, *args):
        self.calls.append("login")

    def mail(self, sender, options=()):
        self.calls.append("mail")
        return 250, b"ok"

    def rcpt(self, recipient):
        self.calls.append("rcpt")
        return 250, b"ok"

    def rset(self):
        self.calls.append("rset")

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Provider:
    def __init__(self, path):
        self._path = path

    def path(self, name):
        assert name == "smtp.relay_client"
        return self._path

    def status(self, name):
        return "configured"


@pytest.fixture()
def relay(monkeypatch, tmp_path):
    crt, _key = relay_certs.make_server_cert()
    cert = tmp_path / "server.crt"
    cert.write_text(crt, encoding="ascii")
    bundle = tmp_path / "client.pem"
    bundle.write_text(relay_certs.make_client_bundle(), encoding="ascii")
    monkeypatch.setattr(relay_files, "SERVER_CERT", str(cert))
    monkeypatch.setattr(transport.smtplib, "SMTP", FakeSmtp)
    resolved = []
    monkeypatch.setattr(transport, "_resolve", lambda host, port: resolved.append((host, port)))
    FakeSmtp.instances = []
    return {"provider": Provider(bundle), "resolved": resolved, "server_pem": crt}


CFG = smtp_config({"enabled": True, "from_address": "noreply@goodmit.co.kr", "mode": "local_relay", "username": "ignored",
                   "relay": {"delivery": "direct", "helo_name": "mail.goodmit.co.kr"}})


def test_local_relay_connects_to_loopback_with_tls_and_no_login(relay):
    result = transport.SmtpTransport().verify(CFG, relay["provider"], probe_recipient="someone@goodmit.co.kr")
    server = FakeSmtp.instances[-1]
    assert (server.host, server.port) == ("127.0.0.1", 2525)
    assert server.calls[:3] == ["ehlo", "starttls", "ehlo"] and "login" not in server.calls
    assert relay["resolved"] == [], "고정 주소라 이름을 찾지 않는다"
    stages = {row["key"]: row["state"] for row in result["stages"]}
    assert stages["dns"] == "skipped" and stages["auth"] == "skipped"
    assert stages["tls"] == "ok" and stages["recipient"] == "ok"


def test_the_tls_context_pins_the_relay_certificate_and_carries_the_client_key(relay):
    transport.SmtpTransport().verify(CFG, relay["provider"])
    context = FakeSmtp.instances[-1].context
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2
    trusted = context.get_ca_certs()
    assert len(trusted) == 1 and trusted[0]["subject"] == ((("commonName", relay_certs.SERVER_NAME),),)


def test_without_the_relay_certificate_it_is_a_tls_failure(relay, monkeypatch, tmp_path):
    monkeypatch.setattr(relay_files, "SERVER_CERT", str(tmp_path / "missing.crt"))
    with pytest.raises(transport.MailTransportError) as caught:
        transport.SmtpTransport().verify(CFG, relay["provider"])
    assert caught.value.stage == "tls"


def test_mx_probe_greets_and_reads_the_egress_ip(monkeypatch):
    class Mx:
        def __init__(self, timeout=None, local_hostname=None):
            self.helo = local_hostname
            self.sent: list = []

        def connect(self, host, port):
            self.sent.append(("connect", host, port))
            return 220, b"mx.example.com ESMTP"

        def ehlo(self):
            self.sent.append("ehlo")
            return 250, b"mx.example.com Hello [221.147.80.10]\nSIZE 1000\nSTARTTLS"

        def quit(self):
            self.sent.append("quit")

        def close(self):
            pass

        def mail(self, *a):  # pragma: no cover - 불리면 시험이 실패한다
            raise AssertionError("MX 시험은 메일을 보내지 않는다")

    made = []
    monkeypatch.setattr(transport.smtplib, "SMTP", lambda **kw: made.append(Mx(**kw)) or made[-1])
    got = transport.probe_mx("mx.example.com", "mail.goodmit.co.kr")
    assert got["connected"] and got["egress_ip"] == "221.147.80.10"
    assert made[0].helo == "mail.goodmit.co.kr" and made[0].sent == [("connect", "mx.example.com", 25), "ehlo", "quit"]


def test_mx_probe_failure_is_a_result_not_an_exception(monkeypatch):
    class Down:
        def __init__(self, **kw):
            pass

        def connect(self, host, port):
            raise TimeoutError("timed out")

        def close(self):
            pass

    monkeypatch.setattr(transport.smtplib, "SMTP", lambda **kw: Down(**kw))
    got = transport.probe_mx("mx.example.com")
    assert got["connected"] is False and "TimeoutError" in got["error"]


_ = smtplib  # 시험 대상이 smtplib 를 바꿔 끼우는 자리를 쓴다
