import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.core.deps import require_roles
from app.main import create_app
from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.security


@pytest.fixture()
def rbac_app(settings, fake_clock):
    app = create_app(settings, clock=fake_clock)

    @app.get("/api/_test/admin-only", dependencies=[Depends(require_roles("admin", "system_admin"))])
    def admin_only():
        return {"ok": True}

    @app.get(
        "/api/_test/audit-read",
        dependencies=[Depends(require_roles("admin", "system_admin", "auditor"))],
    )
    def audit_read():
        return {"ok": True}

    return app


def _client_for(rbac_app, settings, role):
    from app.core.db import make_engine, make_session_factory
    from app.users.service import create_user

    client = TestClient(rbac_app, raise_server_exceptions=False)
    engine = rbac_app.state.engine
    factory = make_session_factory(engine)
    email = f"{role.replace('_', '-')}-rbac@goodmit.co.kr"
    with factory() as db:
        create_user(
            db,
            email=email,
            display_name=f"{role} 계정",
            password=DEFAULT_TEST_PASSWORD,
            settings=settings,
            actor_role="system_admin",
            role=role,
            must_change_password=False,
        )
        db.commit()
    r = client.post("/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD})
    assert r.status_code == 200
    return client


@pytest.mark.parametrize(
    ("role", "expected"),
    [("user", 403), ("operator", 403), ("auditor", 403), ("admin", 200), ("system_admin", 200)],
)
def test_admin_only_endpoint_role_matrix(rbac_app, settings, role, expected):
    client = _client_for(rbac_app, settings, role)
    assert client.get("/api/_test/admin-only").status_code == expected


@pytest.mark.parametrize(
    ("role", "expected"),
    [("user", 403), ("operator", 403), ("auditor", 200), ("admin", 200), ("system_admin", 200)],
)
def test_auditor_branch_gets_read_access_where_listed(rbac_app, settings, role, expected):
    client = _client_for(rbac_app, settings, role)
    assert client.get("/api/_test/audit-read").status_code == expected
