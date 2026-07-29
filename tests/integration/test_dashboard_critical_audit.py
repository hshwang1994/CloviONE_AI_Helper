"""Dashboard '최근 주요 변경' (recent_critical_audit) role gating + maintenance flag.

recent_critical_audit is a sensitive audit slice (누가 역할 변경/롤백/승인했나) — it
must only reach roles that can read the audit log (admin/system_admin/auditor).
operator sees the dashboard but NOT the audit log (app/audit/router.py), so the
dashboard must withhold the slice from operator to avoid a bypass leak
(app/health/router.py:dashboard, app/health/service.py:build_dashboard).

The dashboard also surfaces the current maintenance_mode state so the UI can raise
a danger banner — assert it tracks the setting both on and off.
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


def test_operator_dashboard_hides_critical_audit(client, login_as, db):
    _seed_critical_audit(db)
    login_as("operator")
    body = client.get("/api/admin/dashboard").json()
    # operator has no audit-read authority → the whole slice is withheld.
    assert body["recent_critical_audit"] == []


def test_admin_dashboard_shows_critical_audit(client, login_as, db):
    _seed_critical_audit(db)
    login_as("admin")
    body = client.get("/api/admin/dashboard").json()
    actions = [row["action"] for row in body["recent_critical_audit"]]
    assert "user.role_change" in actions


def test_auditor_dashboard_shows_critical_audit(client, login_as, db):
    _seed_critical_audit(db)
    login_as("auditor")
    body = client.get("/api/admin/dashboard").json()
    actions = [row["action"] for row in body["recent_critical_audit"]]
    assert "user.role_change" in actions


def test_dashboard_maintenance_flag_reflects_setting(client, login_as):
    csrf = login_as("system_admin")

    # Default: maintenance off.
    body = client.get("/api/admin/dashboard").json()
    assert body["maintenance"] is False

    # Turn it on → flag flips to True.
    r = client.put(
        "/api/admin/settings/maintenance_mode",
        json={"value": True},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200
    body = client.get("/api/admin/dashboard").json()
    assert body["maintenance"] is True

    # Turn it back off → flag returns to False.
    r = client.put(
        "/api/admin/settings/maintenance_mode",
        json={"value": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200
    body = client.get("/api/admin/dashboard").json()
    assert body["maintenance"] is False
