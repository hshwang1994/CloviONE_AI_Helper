"""PA-RC-0026: /api/admin/diagnostics/bundle role gate + embedded critical-audit slice.

The gate was CONSOLE_WRITE_ROLES (admin+) even though the bundle is read-only
(spec §14.7 masked diagnostics) and the product's own capability table
(app/core/authz.py CAPABILITIES) names "헬스체크" under console.ops, which
includes operator. Widened to CONSOLE_OPS_ROLES.

That widening created a real risk this file pins down: the bundle embeds a
full build_dashboard() call, and build_dashboard's own recent_critical_audit
slice defaults to included (see tests/integration/test_dashboard_critical_audit.py
for why operator must never see it via the dashboard route directly). Without
explicitly threading role through, operator would have gained that slice
through the diagnostics side door the moment the outer gate widened.
"""

import pytest

pytestmark = pytest.mark.integration


def _seed_critical_audit(db):
    from app.audit.models import AuditLog

    row = AuditLog(
        action="user.role_change",
        object_type="user",
        object_id="target-user-123",
    )
    db.add(row)
    db.commit()
    return row


@pytest.mark.parametrize(
    ("role", "expected"),
    [("user", 403), ("auditor", 403), ("operator", 200), ("admin", 200), ("system_admin", 200)],
)
def test_diagnostics_bundle_role_matrix(client, login_as, role, expected):
    login_as(role)
    r = client.get("/api/admin/diagnostics/bundle")
    assert r.status_code == expected


def test_unauthenticated_diagnostics_bundle_rejected(client):
    assert client.get("/api/admin/diagnostics/bundle").status_code == 401


def test_operator_diagnostics_bundle_hides_critical_audit(client, login_as, db):
    _seed_critical_audit(db)
    login_as("operator")
    body = client.get("/api/admin/diagnostics/bundle").json()
    # 🔴 revert-to-verify — dropping the include_critical_audit passthrough in
    # app/health/router.py::diagnostics_bundle (i.e. calling build_diagnostic_bundle
    # without it, so build_dashboard's own default of True applies) makes this fail:
    # operator would see the same slice the dashboard route deliberately withholds.
    assert body["dashboard"]["recent_critical_audit"] == []


def test_admin_diagnostics_bundle_shows_critical_audit(client, login_as, db):
    _seed_critical_audit(db)
    login_as("admin")
    body = client.get("/api/admin/diagnostics/bundle").json()
    actions = [row["action"] for row in body["dashboard"]["recent_critical_audit"]]
    assert "user.role_change" in actions


def test_system_admin_diagnostics_bundle_shows_critical_audit(client, login_as, db):
    _seed_critical_audit(db)
    login_as("system_admin")
    body = client.get("/api/admin/diagnostics/bundle").json()
    actions = [row["action"] for row in body["dashboard"]["recent_critical_audit"]]
    assert "user.role_change" in actions


def test_diagnostics_bundle_payload_keeps_fields_pa_rc_0028_stopped_rendering(
    client, login_as, db, stub_pg_dump
):
    """PA-RC-0028 removed the '백업'/'최근 주요 변경' sections from Diagnostics.jsx's
    body (they duplicated /dashboard's own always-visible sections 16/16 and 3/3) but
    acceptance criterion (3) requires the *payload* to stay whole — the bundle is a
    support-team artifact (JSON download) that must still be complete even though the
    screen now renders less of it. This pins the fields the removed sections used to
    read so a future payload-shrink (e.g. "unused, let's drop it from the query") gets
    caught here instead of silently thinning the support artifact.
    """
    _seed_critical_audit(db)
    csrf = login_as("system_admin")
    r = client.post("/api/admin/backups", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 201, r.text

    body = client.get("/api/admin/diagnostics/bundle").json()
    dash = body["dashboard"]
    assert dash["last_backup_at"] is not None
    assert dash["last_backup_status"] == "verified"
    assert any(row["action"] == "user.role_change" for row in dash["recent_critical_audit"])
