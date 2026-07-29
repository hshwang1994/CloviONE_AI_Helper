import pytest

from app.core.middleware import CSP_POLICY

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
