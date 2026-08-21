import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.core.deps import require_roles
from app.main import create_app
from tests.conftest import DEFAULT_TEST_PASSWORD

# 이 파일은 `create_app(settings, …)` 을 **직접** 부른다 — 시험 하네스의 바인드를
# 안 받으므로 `settings.database_url` 로 자기 엔진을 만들고 **진짜로 커밋한다**.
# 공유 DB 계층에서는 그 커밋이 되감기 밖에 있어 다음 시험으로 샌다(실제로 같은
# 이메일로 두 번째 `create_user` 가 유니크 위반으로 죽었다). 그래서 전용 DB 를 받는다.
pytestmark = [pytest.mark.security, pytest.mark.real_db]


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
