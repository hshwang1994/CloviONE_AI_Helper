import pytest

pytestmark = pytest.mark.integration


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "ticket_source": "notion_cache"}


def test_healthz_reports_configured_ticket_source(settings, fake_clock, fake_http):
    # ticket_source는 SSH 없이 확인할 방법이 없던 운영 킬 스위치였다(app/core/config.py:136-
    # 164). 기본값 하나만 보면 "그냥 필드가 있다"만 확인되고 실제로 settings 값을 읽어 오는지는
    # 확인되지 않는다 - 기본값과 다른 값을 주입해 healthz가 하드코딩된 문자열이 아니라
    # request.app.state.settings를 실제로 읽는지 증명한다.
    from fastapi.testclient import TestClient

    from app.core.config import Settings
    from app.main import create_app

    # _env_file=None을 다시 주지 않으면 pydantic-settings가 기본 env_file(".env")을
    # 다시 읽어 들여 이 오버라이드가 로컬 .env 내용에 좌우될 수 있다 - settings 픽스처와
    # 똑같이 순수 명시값만으로 구성한다.
    overridden = Settings(
        **{**settings.model_dump(), "ticket_source": "notion"}, _env_file=None
    )
    app = create_app(
        overridden, clock=fake_clock, outbound_transport=fake_http.transport()
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "ticket_source": "notion"}


def test_readyz_with_working_db(client):
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}


# OPS-03: uploads 디렉터리가 쓰기 불가(소유권/권한 드리프트, OPS-01 실사고와 같은 유형)여도
# 예전엔 이를 관측할 방법이 전혀 없었다 — 디스크 용량 확인(_disk_usage)만으로는 안 보인다.
def test_readyz_reports_unready_when_uploads_not_writable(client, monkeypatch):
    from pathlib import Path

    def _boom(self, *a, **k):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "mkdir", _boom)
    r = client.get("/readyz")
    assert r.status_code == 503
    assert r.json() == {"status": "unready", "reason": "uploads_not_writable"}


def test_dashboard_reports_uploads_writable(client, login_as):
    csrf = login_as("system_admin")
    r = client.get("/api/admin/dashboard", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    assert r.json()["uploads_writable"] is True


def test_dashboard_reports_uploads_not_writable(client, login_as, monkeypatch):
    from pathlib import Path

    csrf = login_as("system_admin")

    def _boom(self, *a, **k):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "mkdir", _boom)
    r = client.get("/api/admin/dashboard", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    assert r.json()["uploads_writable"] is False


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
