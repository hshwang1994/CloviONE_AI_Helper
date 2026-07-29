import pytest
from fastapi.testclient import TestClient

from app.core.errors import NotFoundError
from app.main import create_app

pytestmark = pytest.mark.integration


def test_unhandled_exception_returns_opaque_envelope(settings):
    app = create_app(settings)

    @app.get("/boom")
    def boom():
        raise RuntimeError("sensitive internal detail")

    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert body["error"]["code"] == "internal_error"
    assert "sensitive internal detail" not in r.text
    assert "Traceback" not in r.text


def test_app_error_renders_envelope(settings):
    app = create_app(settings)

    @app.get("/missing")
    def missing():
        raise NotFoundError("Ticket not found")

    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.get("/missing")
    assert r.status_code == 404
    assert r.json()["error"] == {
        "code": "not_found",
        "message": "Ticket not found",
        "request_id": r.headers["X-Request-ID"],
    }


def test_validation_error_does_not_echo_input(settings):
    from pydantic import BaseModel

    app = create_app(settings)

    class Payload(BaseModel):
        count: int

    @app.post("/typed")
    def typed(payload: Payload):
        return {"ok": True}

    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post("/typed", json={"count": "secret-string-value"})
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "validation_error"
    assert "secret-string-value" not in r.text
