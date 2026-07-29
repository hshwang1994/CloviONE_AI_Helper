"""Regression tests for §32 review iteration-2 findings."""

import pytest

pytestmark = pytest.mark.regression


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


def test_integration_rollback_sensitive_change_gated(client, login_as):
    """iter2 medium: integration rollback must go through the approval gate."""
    sys_csrf = login_as("system_admin", email="int-rb-owner@goodmit.co.kr")
    integ = client.post(
        "/api/admin/integrations",
        json={"name": "int-rb", "provider_type": "http_service", "base_url": "http://127.0.0.1:8787"},
        headers=_headers(sys_csrf),
    ).json()["integration"]
    client.patch(
        f"/api/admin/integrations/{integ['id']}",
        json={"base_url": "http://127.0.0.1:8788"},
        headers=_headers(sys_csrf),
    )
    admin_csrf = login_as("admin", email="int-rb-admin@goodmit.co.kr")
    r = client.post(
        f"/api/admin/integrations/{integ['id']}/rollback",
        json={"version": 1},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 202
    assert r.json()["status"] == "approval_pending"


def test_admin_cannot_promote_to_system_admin(client, login_as, make_user):
    """iter2 security: only system_admin may grant system_admin."""
    target = make_user("promote-target@goodmit.co.kr")
    admin_csrf = login_as("admin", email="promoter2@goodmit.co.kr")
    r = client.patch(
        f"/api/admin/users/{target.id}",
        json={"role": "system_admin"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 403


def test_admin_cannot_demote_system_admin(client, login_as, make_user):
    """iter2 medium: revoking system_admin also requires system_admin authority."""
    victim = make_user("sysadmin-victim@goodmit.co.kr", role="system_admin")
    admin_csrf = login_as("admin", email="demoter@goodmit.co.kr")
    r = client.patch(
        f"/api/admin/users/{victim.id}",
        json={"role": "operator"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 403


def test_system_admin_can_manage_system_admin_membership(client, login_as, make_user):
    target = make_user("sa-managed@goodmit.co.kr", role="admin")
    csrf = login_as("system_admin")
    r = client.patch(
        f"/api/admin/users/{target.id}",
        json={"role": "system_admin"},
        headers=_headers(csrf),
    )
    assert r.status_code == 200


def test_password_policy_min_classes_bounded(client, login_as):
    """iter2 medium: impossible min_classes (>4) is rejected, not stored."""
    csrf = login_as("system_admin")
    r = client.put(
        "/api/admin/settings/password_policy",
        json={"value": {"min_length": 12, "min_classes": 5}},
        headers=_headers(csrf),
    )
    assert r.status_code == 422


def test_retention_keeps_last_good_backup_when_recent_fail(db, fake_clock):
    """iter2 medium: apply_retention must not delete the last good backup."""
    from datetime import timedelta

    from app.backups.models import Backup
    from app.backups.service import apply_retention, last_successful_backup

    base = fake_clock.now()
    good = Backup(backup_type="sqlite", path="/tmp/good.sqlite3", status="verified",
                  created_at=base)
    db.add(good)
    # 20 later failed backups.
    for i in range(20):
        db.add(Backup(backup_type="sqlite", path=f"/tmp/f{i}", status="failed",
                      created_at=base + timedelta(minutes=i + 1)))
    db.commit()

    apply_retention(db, keep=14)
    db.commit()
    # The one good backup survives; failed ones are pruned.
    assert last_successful_backup(db) is not None
    assert last_successful_backup(db).path == "/tmp/good.sqlite3"


def test_mark_read_is_idempotent(client, login_as, db, fake_clock):
    """iter2 low: marking an already-read notification returns 200, not 404."""
    login_as("user", email="idempotent-notif@goodmit.co.kr")
    me = client.get("/api/me").json()
    from app.notifications.service import notify_user

    note = notify_user(db, me["user"]["id"], type_="t", title="알림", now=fake_clock.now())
    db.commit()
    csrf = me["csrf_token"]
    assert client.post(f"/api/notifications/{note.id}/read", headers=_headers(csrf)).status_code == 200
    # Second time — still 200 (idempotent), not 404.
    assert client.post(f"/api/notifications/{note.id}/read", headers=_headers(csrf)).status_code == 200
    # A non-existent id is still 404.
    assert client.post("/api/notifications/no-such-id/read", headers=_headers(csrf)).status_code == 404


def test_create_user_temp_password_still_returned(client, login_as):
    """iter2 high (regression fix): the create flow still returns the temp
    password for the persistent modal to display."""
    csrf = login_as("admin")
    r = client.post(
        "/api/admin/users",
        json={"email": "modal-user@goodmit.co.kr", "display_name": "모달사용자"},
        headers=_headers(csrf),
    )
    assert r.status_code == 201
    assert r.json()["temp_password"]
