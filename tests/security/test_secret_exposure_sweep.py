"""Sweep every admin GET endpoint as system_admin with a seeded secret and
assert the plaintext value never appears in any response (spec §25.4, §31.10)."""

import pytest

pytestmark = pytest.mark.security

SECRET_VALUE = "TOP-SECRET-PLAINTEXT-VALUE-DO-NOT-LEAK-9271"


@pytest.fixture()
def seeded(client, login_as, settings):
    csrf = login_as("system_admin")
    (settings.secrets_dir / "sweep-secret").write_text(SECRET_VALUE, encoding="utf-8")
    h = {"X-CSRF-Token": csrf}
    # Integration + runner referencing the secret.
    client.post(
        "/api/admin/integrations",
        json={"name": "sweep-int", "provider_type": "http_service",
              "base_url": "https://api.notion.com", "auth_type": "bearer",
              "secret_ref": "sweep-secret"},
        headers=h,
    )
    return h


ADMIN_GET_ENDPOINTS = [
    "/api/admin/users",
    "/api/admin/integrations",
    "/api/admin/prompts",
    "/api/admin/policies",
    "/api/admin/schedules",
    "/api/admin/approvals",
    "/api/admin/audit",
    "/api/admin/settings",
    "/api/admin/backups",
    "/api/admin/notion-mapping",
    "/api/admin/dashboard",
    "/api/admin/diagnostics/bundle",
    "/api/admin/jobs",
    "/api/notifications",
]


def test_no_endpoint_leaks_secret_plaintext(client, seeded):
    leaks = []
    for path in ADMIN_GET_ENDPOINTS:
        r = client.get(path, headers=seeded)
        assert r.status_code == 200, f"{path} -> {r.status_code}"
        if SECRET_VALUE in r.text:
            leaks.append(path)
    assert leaks == [], f"secret leaked in: {leaks}"


def test_integration_detail_shows_status_not_value(client, seeded):
    listing = client.get("/api/admin/integrations", headers=seeded).json()["items"]
    sweep = next(i for i in listing if i["name"] == "sweep-int")
    assert sweep["secret_status"] == "configured"
    detail = client.get(f"/api/admin/integrations/{sweep['id']}", headers=seeded)
    assert SECRET_VALUE not in detail.text
    assert detail.json()["integration"]["secret_status"] == "configured"


def test_config_version_snapshots_store_ref_not_value(client, seeded, db):
    from app.core.versioning import ConfigVersion

    rows = db.query(ConfigVersion).all()
    for row in rows:
        assert SECRET_VALUE not in row.snapshot_json


def test_audit_never_stores_secret(client, seeded, db):
    from app.audit.models import AuditLog

    for row in db.query(AuditLog).all():
        blob = (row.before_json or "") + (row.after_json or "")
        assert SECRET_VALUE not in blob
