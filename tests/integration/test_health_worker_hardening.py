"""Hardening tests for cert-expiry parsing and worker liveness heartbeats.

Covers two independent fixes:
  * app.health.service._cert_days_remaining — stdlib ``ssl`` parse (no openssl
    subprocess, no third-party dep), timezone-aware, never raises.
  * app.worker_main heartbeat helpers — a dedicated liveness beat that uses its
    own short-lived session and never crashes the worker, so it keeps beating
    during long-running jobs.
"""

from __future__ import annotations

import threading
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.core.db import make_engine, make_session_factory
from app.health.models import Heartbeat
from app.health.service import _cert_days_remaining, _component_status, is_self_signed_cert
from app.worker_main import (
    LIVENESS_COMPONENTS,
    beat_liveness,
    run_heartbeat_loop,
)
from tests.fakes.clock import FakeClock

# 이 파일의 시험 일부는 **전용 DB** 가 필요하다(D-190) — CLI·워커처럼 `DATABASE_URL` 로
# **따로 붙는** 코드가 이 시험이 만든 행을 봐야 하기 때문이다. 공유 DB + 트랜잭션
# 되감기 계층에서는 그 행이 트랜잭션 밖으로 안 나가서 「사용자를 찾을 수 없습니다」가 된다.
pytestmark = [pytest.mark.integration, pytest.mark.real_db]


# A real self-signed certificate, notAfter = Jul 16 01:25:28 2036 GMT.
_TEST_CERT_PEM = """\
-----BEGIN CERTIFICATE-----
MIIDEzCCAfugAwIBAgIUZmU3PFcPOuS8QsqtRWebTljpLRAwDQYJKoZIhvcNAQEL
BQAwGTEXMBUGA1UEAwwOY2xvdmlyb25lLXRlc3QwHhcNMjYwNzE5MDEyNTI4WhcN
MzYwNzE2MDEyNTI4WjAZMRcwFQYDVQQDDA5jbG92aXJvbmUtdGVzdDCCASIwDQYJ
KoZIhvcNAQEBBQADggEPADCCAQoCggEBAKdR6wJfSt6yrsGe/4wjnHuNlCwaoN5o
dxI4Q1Wwa2WQj8zCh56uuooRxqmlEmZFJPNQ5fX4nzVtblOlz2E8qYiZY47tBaW3
xod0nA7A2XqgNlyU78C8p5mTFIfdMg6j0Yc95JTtG0ygfneeOX9zHGD8KftFR82U
+S1tQ82lbJ3maqM4dtBR9Dyyb4CaBmW7H+M/sk4RrqcqPNd7fiQOvv3kx3cGL0QH
nqQc/3KbvuwF+X6sY3lncE2f8dN6vf9stvrmRDi4uW3HCfN9iy2N6/6NfZ36tpAx
fS8Aj4cZqIMT711p+DNsG/HQgxoMqBx2LuQXwo7QnOFbWh+ML7BykMcCAwEAAaNT
MFEwHQYDVR0OBBYEFAhw77LzwN9otxL3MKdM/Bss4uHlMB8GA1UdIwQYMBaAFAhw
77LzwN9otxL3MKdM/Bss4uHlMA8GA1UdEwEB/wQFMAMBAf8wDQYJKoZIhvcNAQEL
BQADggEBAAK0SVDMQJNLKCxoOsVbPpTtGKZqs/R1cY5qwGZgbfiUPhu7QtOdtjdX
xMzr4ykUc5woF0r1ekuxPCl/Re0LiICoPs+6l7GZYT2z1A0d6W4yg5xK73cxU6e/
wQtaeyXsb9l/Udnwfjwuii1iwUDSG+f8HVcv1SJKQtcJ/Cf9u701AEU6/BwV7UwC
8/EIGDMWApbT9bvWDp2/ZcRpvBX9EchDD3HRe7Jt6gOsI3x6tRYWmvxwYvAWMQpa
JRzFyF/6tijUN6adnkAicWiEt5u12vNJh8bJ+WeOurnwYXAtieBnB7th9DZPUvf0
rGNJyF0kIsrT9LPd7V0dGrENffp+RDY=
-----END CERTIFICATE-----
"""


# --------------------------------------------------------------------------- #
# _cert_days_remaining
# --------------------------------------------------------------------------- #


def test_cert_days_remaining_none_when_no_path():
    settings = SimpleNamespace()  # no tls_cert_path attribute at all
    assert _cert_days_remaining(settings) is None

    settings = SimpleNamespace(tls_cert_path=None)
    assert _cert_days_remaining(settings) is None

    settings = SimpleNamespace(tls_cert_path="")
    assert _cert_days_remaining(settings) is None


def test_cert_days_remaining_none_when_file_missing(tmp_path):
    missing = tmp_path / "does-not-exist.pem"
    settings = SimpleNamespace(tls_cert_path=str(missing))
    assert _cert_days_remaining(settings) is None


def test_cert_days_remaining_none_on_garbage_file(tmp_path):
    junk = tmp_path / "not-a-cert.pem"
    junk.write_text("this is definitely not a PEM certificate")
    settings = SimpleNamespace(tls_cert_path=str(junk))
    # Must swallow the parse error rather than raise.
    assert _cert_days_remaining(settings) is None


def test_cert_days_remaining_parses_real_cert(tmp_path):
    cert = tmp_path / "cert.pem"
    cert.write_text(_TEST_CERT_PEM)
    settings = SimpleNamespace(tls_cert_path=str(cert))

    days = _cert_days_remaining(settings)
    assert isinstance(days, int)
    # notAfter is Jul 16 2036; from any realistic "now" that is many years out.
    assert days > 3000

    # Cross-check against an independent computation from the same source of
    # truth so we know the arithmetic (not just the sign) is right.
    import ssl
    from datetime import timezone

    expiry = datetime.fromtimestamp(
        ssl.cert_time_to_seconds("Jul 16 01:25:28 2036 GMT"), tz=timezone.utc
    )
    expected = (expiry - datetime.now(timezone.utc)).days
    assert days == expected


def test_is_self_signed_cert_true_for_the_real_self_signed_test_cert(tmp_path):
    """SYS-05: `_TEST_CERT_PEM`은 자체서명(issuer==subject, 위 주석에 명시)이다 —
    `is_self_signed_cert`가 실제 파싱으로 그것을 그대로 확인한다."""
    from app.health.service import is_self_signed_cert

    cert = tmp_path / "cert.pem"
    cert.write_text(_TEST_CERT_PEM)
    settings = SimpleNamespace(tls_cert_path=str(cert))

    assert is_self_signed_cert(settings) is True


def test_is_self_signed_cert_false_when_issuer_differs_from_subject(tmp_path, monkeypatch):
    """진짜 CA 서명 인증서 체인을 새로 만들지 않고, ssl 파싱 결과(issuer != subject)만
    흉내 낸다 — 비교 로직 자체를 잠근다(subject==issuer가 아니면 자체서명이 아니다)."""
    import app.health.service as health_service

    cert = tmp_path / "cert.pem"
    cert.write_text("placeholder, 아래 monkeypatch가 실제 파싱을 대신한다", encoding="utf-8")
    settings = SimpleNamespace(tls_cert_path=str(cert))

    fake_cert = {
        "subject": ((("commonName", "clovirassist.gooddi.lab"),),),
        "issuer": ((("commonName", "Some Trusted CA"),),),
    }
    monkeypatch.setattr(health_service.ssl._ssl, "_test_decode_cert", lambda path: fake_cert)

    assert health_service.is_self_signed_cert(settings) is False


def test_is_self_signed_cert_none_when_no_path():
    assert is_self_signed_cert(SimpleNamespace(tls_cert_path=None)) is None


def test_is_self_signed_cert_none_when_file_missing(tmp_path):
    assert is_self_signed_cert(
        SimpleNamespace(tls_cert_path=str(tmp_path / "missing.crt"))
    ) is None


# --------------------------------------------------------------------------- #
# worker liveness heartbeat
# --------------------------------------------------------------------------- #


def _session_factory(settings):
    engine = make_engine(settings.database_url)
    return make_session_factory(engine)


def test_beat_liveness_writes_all_components(settings):
    session_factory = _session_factory(settings)
    clock = FakeClock(datetime(2026, 7, 19, 12, 0, 0))

    assert beat_liveness(session_factory, clock) is True

    now = clock.now()
    with session_factory() as db:
        for component in LIVENESS_COMPONENTS:
            row = db.get(Heartbeat, component)
            assert row is not None, component
            assert row.last_beat_at == now
            # And the dashboard reads them as 'up' right after the beat.
            assert _component_status(db, component, now) == "up"


def test_beat_liveness_never_raises_and_reports_failure():
    def exploding_factory():
        raise RuntimeError("db is unavailable")

    clock = FakeClock(datetime(2026, 7, 19, 12, 0, 0))
    # Must not propagate — the worker process must survive a heartbeat failure.
    assert beat_liveness(exploding_factory, clock) is False


def test_run_heartbeat_loop_beats_then_stops(settings):
    real_factory = _session_factory(settings)
    clock = FakeClock(datetime(2026, 7, 19, 12, 0, 0))
    stop_event = threading.Event()
    calls: list[int] = []

    def counting_factory():
        calls.append(1)
        # Stop after the first round so the loop terminates deterministically.
        stop_event.set()
        return real_factory()

    run_heartbeat_loop(counting_factory, clock, stop_event, interval=0.01)

    assert len(calls) == 1  # exactly one round before the stop took effect
    now = clock.now()
    with real_factory() as db:
        for component in LIVENESS_COMPONENTS:
            assert db.get(Heartbeat, component).last_beat_at == now


def test_run_heartbeat_loop_stops_when_lock_renew_raises(settings):
    """OPS-11: `beat_liveness` 는 예외를 전부 가두는데 `lock.renew()` 는 무방비였다 -
    `renew()` 가 (반환값이 아니라) 예외로 실패하면 이 데몬 스레드가 조용히 죽고
    `stop_event` 는 끝내 안 켜져서, 대시보드는 하트비트 단절로 "워커 중단"을 보여 주는데
    본 루프(`worker.run_forever`)는 그 사실을 모른 채 잡을 계속 처리하는 좀비 상태가 됐다.
    이 테스트는 `run_heartbeat_loop` 자신이 그 예외를 잡아 `stop_event` 를 켜고 돌아오는지
    본다(그래야 본 루프가 그 신호를 보고 같이 멈춘다)."""
    session_factory = _session_factory(settings)
    clock = FakeClock(datetime(2026, 7, 19, 12, 0, 0))
    stop_event = threading.Event()

    class ExplodingLock:
        def renew(self):
            raise OSError("ENOSPC")

    # 데몬 스레드가 조용히 죽지 않고 정상적으로 리턴해야 이 호출 자체가 끝난다 -
    # 예전 코드라면 여기서 OSError 가 그대로 튀어나와 테스트가 실패(에러)했을 것이다.
    run_heartbeat_loop(session_factory, clock, stop_event, interval=0.01, lock=ExplodingLock())

    assert stop_event.is_set(), "renew() 예외 뒤에도 stop_event 가 안 켜지면 본 루프가 계속 돈다"


def test_run_heartbeat_loop_exits_when_already_stopped(settings):
    session_factory = _session_factory(settings)
    clock = FakeClock()
    stop_event = threading.Event()
    stop_event.set()  # already stopped before we start

    calls: list[int] = []

    def counting_factory():
        calls.append(1)
        return session_factory()

    run_heartbeat_loop(counting_factory, clock, stop_event, interval=0.01)
    assert calls == []  # no beats when stopped up front
