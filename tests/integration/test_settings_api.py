import pytest

pytestmark = pytest.mark.integration


@pytest.fixture()
def admin_csrf(login_as):
    return login_as("admin")


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


def test_list_settings_shows_registry_defaults(client, admin_csrf):
    r = client.get("/api/admin/settings")
    assert r.status_code == 200
    settings = r.json()["settings"]
    assert settings["notification_retention_days"]["value"] == 90
    assert settings["maintenance_mode"]["value"] is False
    # session_policy now applies to new sessions immediately — no restart needed.
    assert settings["session_policy"]["restart_required"] is False
    # Removed keys (env/per-object only) must not appear as dead switches.
    assert "page_size" not in settings
    assert "timezone" not in settings


def test_unknown_key_rejected(client, admin_csrf):
    r = client.put(
        "/api/admin/settings/arbitrary_system_file",
        json={"value": "/etc/passwd"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422  # not in allowlist


def test_dry_run_validates_without_applying(client, admin_csrf):
    ok = client.post(
        "/api/admin/settings/notification_retention_days/dry-run",
        json={"value": 50},
        headers=_headers(admin_csrf),
    )
    assert ok.status_code == 200
    assert ok.json()["ok"] is True

    bad = client.post(
        "/api/admin/settings/notification_retention_days/dry-run",
        json={"value": 99999},  # exceeds max 3650
        headers=_headers(admin_csrf),
    )
    assert bad.status_code == 422

    # Nothing changed.
    assert (
        client.get("/api/admin/settings").json()["settings"]["notification_retention_days"]["value"]
        == 90
    )


def test_update_and_rollback(client, admin_csrf):
    key = "notification_retention_days"
    r = client.put(f"/api/admin/settings/{key}", json={"value": 50}, headers=_headers(admin_csrf))
    assert r.status_code == 200
    assert r.json()["after"] == 50
    assert client.get("/api/admin/settings").json()["settings"][key]["value"] == 50

    client.put(f"/api/admin/settings/{key}", json={"value": 30}, headers=_headers(admin_csrf))
    versions = client.get(f"/api/admin/settings/{key}/versions").json()["items"]
    assert len(versions) == 2
    r = client.post(
        f"/api/admin/settings/{key}/rollback",
        json={"version": 1},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200
    assert client.get("/api/admin/settings").json()["settings"][key]["value"] == 90


def test_invalid_value_rejected_on_apply(client, admin_csrf):
    r = client.put(
        "/api/admin/settings/notification_retention_days",
        json={"value": -5},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422


def test_password_policy_takes_effect_immediately(client, admin_csrf):
    # Wiring proof: tightening password_policy blocks a now-too-short password.
    client.put(
        "/api/admin/settings/password_policy",
        json={"value": {"min_length": 20, "min_classes": 3}},
        headers=_headers(admin_csrf),
    )
    r = client.post(
        "/api/admin/users",
        json={"email": "shortpw@goodmit.co.kr", "display_name": "짧은비번",
              "password": "Only-12-Chars!"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422  # 14 chars < new min 20


def test_session_policy_object_validation(client, admin_csrf):
    r = client.put(
        "/api/admin/settings/session_policy",
        json={"value": {"idle_timeout_seconds": 10, "absolute_timeout_seconds": 100}},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422  # idle < 60

    r = client.put(
        "/api/admin/settings/session_policy",
        json={"value": {"idle_timeout_seconds": 1800, "absolute_timeout_seconds": 28800}},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200


def test_operator_cannot_change_settings(client, login_as):
    csrf = login_as("operator")
    r = client.put(
        "/api/admin/settings/notification_retention_days",
        json={"value": 40},
        headers=_headers(csrf),
    )
    assert r.status_code == 403
    assert client.get("/api/admin/settings").status_code == 200  # read OK
