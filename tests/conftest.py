"""Shared pytest fixtures.

DB strategy: run alembic once per session into a template file, then copy the
file per test — migrations are exercised on every run but tests stay fast.
File-based SQLite only (never :memory:) so WAL and multi-connection behavior
match production.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def migrated_db_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    template_dir = tmp_path_factory.mktemp("db-template")
    db_path = template_dir / "template.sqlite3"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path.as_posix()}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"
    assert db_path.exists()
    return db_path


@pytest.fixture()
def db_path(migrated_db_template: Path, tmp_path: Path) -> Path:
    target = tmp_path / "web.sqlite3"
    shutil.copy(migrated_db_template, target)
    return target


@pytest.fixture()
def settings(db_path: Path, tmp_path: Path) -> Settings:
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir(exist_ok=True)
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite:///{db_path.as_posix()}",
        session_secret="test-session-secret",
        cookie_secure=False,
        config_dir=PROJECT_ROOT / "config",
        secrets_dir=secrets_dir,
        data_dir=tmp_path,
    )


@pytest.fixture()
def fake_clock():
    from tests.fakes.clock import FakeClock

    return FakeClock()


@pytest.fixture()
def fake_http():
    from tests.fakes.http import FakeHTTP

    return FakeHTTP()


@pytest.fixture()
def app(settings: Settings, fake_clock, fake_http):
    return create_app(
        settings, clock=fake_clock, outbound_transport=fake_http.transport()
    )


@pytest.fixture()
def client(app):
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture()
def db(app):
    factory = app.state.session_factory
    session = factory()
    try:
        yield session
    finally:
        session.close()


DEFAULT_TEST_PASSWORD = "Str0ng-Passw0rd!"


@pytest.fixture()
def make_user(db, settings):
    from app.users.service import create_user

    def _make(
        email: str = "user@goodmit.co.kr",
        *,
        password: str = DEFAULT_TEST_PASSWORD,
        role: str = "user",
        active: bool = True,
        must_change_password: bool = False,
        display_name: str = "테스트 사용자",
    ):
        user = create_user(
            db,
            email=email,
            display_name=display_name,
            password=password,
            settings=settings,
            role=role,
            active=active,
            must_change_password=must_change_password,
        )
        db.commit()
        return user

    return _make


@pytest.fixture()
def login_as(client, make_user):
    """Create a user for the given role, log in, and return the CSRF token.

    The client keeps the session cookie automatically.
    """

    def _login(role: str = "user", *, email: str | None = None):
        from app.users.service import get_user_by_email

        email = email or f"{role.replace('_', '-')}@goodmit.co.kr"
        # Tolerate a pre-created user (tests that call make_user then login_as).
        with client.app.state.session_factory() as db:
            existing = get_user_by_email(db, email)
        if existing is None:
            make_user(email=email, role=role)
        response = client.post(
            "/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD}
        )
        assert response.status_code == 200, response.text
        return response.json()["csrf_token"]

    return _login
