import pytest
from fastapi.testclient import TestClient

from app.core.middleware import CSP_POLICY
from app.main import create_app

pytestmark = pytest.mark.integration


def test_request_id_generated_when_absent(client):
    r = client.get("/healthz")
    request_id = r.headers["X-Request-ID"]
    assert len(request_id) == 32  # uuid4 hex


def test_safe_incoming_request_id_is_echoed(client):
    r = client.get("/healthz", headers={"X-Request-ID": "abc-123-def"})
    assert r.headers["X-Request-ID"] == "abc-123-def"


def test_unsafe_incoming_request_id_is_replaced(client):
    r = client.get("/healthz", headers={"X-Request-ID": "bad<script>id"})
    assert r.headers["X-Request-ID"] != "bad<script>id"


# CORE-12: str.isalnum() is Unicode-aware, so a non-ASCII "alphanumeric" value
# (e.g. Hangul) used to pass the safety check, then blow up when Starlette
# tried to latin-1-encode it as a response header value. Going through the
# real ASGI/httpx transport can't reproduce this directly: incoming header
# *bytes* get latin-1-decoded before reaching our code, so raw UTF-8 bytes
# for Hangul turn into C1-control mojibake that already fails isalnum() for
# an unrelated reason and would mask a regression here. Test the function
# (and the header-encoding failure it exists to prevent) directly instead.
def test_non_ascii_alnum_value_is_rejected_as_unsafe():
    from app.core.middleware import _is_safe_request_id

    assert _is_safe_request_id("한글한글한글") is False


def test_ascii_alnum_value_is_still_accepted():
    from app.core.middleware import _is_safe_request_id

    assert _is_safe_request_id("abc-123-def") is True


def test_a_value_isalnum_would_wrongly_accept_cannot_be_a_response_header():
    """Documents *why* the check must stay ASCII-only, independent of our own
    fix: if it accepted this string, building the response would crash."""
    with pytest.raises(UnicodeEncodeError):
        "한글한글한글".encode("latin-1")


def test_security_headers_present(client):
    r = client.get("/healthz")
    assert r.headers["Content-Security-Policy"] == CSP_POLICY
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "same-origin"
    assert r.headers["Cache-Control"] == "no-store"


def test_csp_matches_spec_25_6(client):
    csp = client.get("/healthz").headers["Content-Security-Policy"]
    for directive in [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "connect-src 'self'",
        "font-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "frame-ancestors 'none'",
        "form-action 'self'",
    ]:
        assert directive in csp


def test_unknown_route_returns_error_envelope(client):
    r = client.get("/definitely-not-a-route")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["request_id"]


def test_oversized_body_rejected_with_413(client):
    r = client.post("/healthz", content=b"x" * (300 * 1024))
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"


# CORE-04: an unhandled exception is converted to a 500 by Starlette's
# ServerErrorMiddleware, which sits *outside* every app.add_middleware(...)
# layer — so RequestContextMiddleware's post-call_next code (security headers,
# access log) used to never run for that response. Same repro technique as
# tests/integration/test_error_envelope.py: a throwaway route on a fresh app.
def test_500_response_still_gets_security_headers(settings):
    app = create_app(settings)

    @app.get("/boom-headers")
    def boom():
        raise RuntimeError("sensitive internal detail")

    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.get("/boom-headers")

    assert r.status_code == 500
    assert r.headers.get("Content-Security-Policy") == CSP_POLICY
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("Referrer-Policy") == "same-origin"
    assert r.headers.get("Cache-Control") == "no-store"
    assert r.headers.get("X-Request-ID")


def test_500_response_still_gets_an_access_log_line(settings):
    """`app.access`는 중복 출력을 막으려고 `propagate=False`로 둔다(logging_setup.py)
    — 그래서 root에 붙는 pytest 기본 caplog 핸들러로는 이 로거를 못 본다. 직접
    핸들러를 붙인다."""
    import logging

    app = create_app(settings)

    @app.get("/boom-log")
    def boom():
        raise RuntimeError("sensitive internal detail")

    captured: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record):
            captured.append(record)

    access_logger = logging.getLogger("app.access")
    handler = _Collect()
    access_logger.addHandler(handler)
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            client.get("/boom-log")
    finally:
        access_logger.removeHandler(handler)

    assert any("/boom-log" in r.getMessage() and "500" in r.getMessage() for r in captured), (
        "500 응답이 접근 로그에 안 남았다 — request_id로 상관관계를 지을 유일한 줄이다"
    )
