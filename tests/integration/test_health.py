import pytest

pytestmark = pytest.mark.integration


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz_with_working_db(client):
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}


def test_readyz_reports_unready_when_db_is_broken(settings):
    from fastapi.testclient import TestClient

    from app.core.db import make_engine, make_session_factory
    from app.main import create_app

    app = create_app(settings)
    # Point the app at a database path that cannot exist.
    broken = make_engine("sqlite:///Z:/nonexistent/definitely/missing.sqlite3")
    app.state.session_factory = make_session_factory(broken)

    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.get("/readyz")
    assert r.status_code == 503
    assert r.json() == {"status": "unready"}
