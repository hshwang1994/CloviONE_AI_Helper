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
from app.health.service import _cert_days_remaining, _component_status
from app.worker_main import (
    LIVENESS_COMPONENTS,
    beat_liveness,
    run_heartbeat_loop,
)
from tests.fakes.clock import FakeClock

pytestmark = pytest.mark.integration


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
