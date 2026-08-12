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


def test_lockout_policy_object_validation(client, admin_csrf):
    r = client.put(
        "/api/admin/settings/lockout_policy",
        json={"value": {"max_failures": 0, "lock_seconds": 900}},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422  # max_failures < 1

    r = client.put(
        "/api/admin/settings/lockout_policy",
        json={"value": {"max_failures": 5, "lock_seconds": 30}},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422  # lock_seconds < 60

    r = client.put(
        "/api/admin/settings/lockout_policy",
        json={"value": {"max_failures": 5, "lock_seconds": 900}},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200


def test_rollback_to_maintenance_true_notifies_active_users(client, admin_csrf, db):
    """A rollback that flips maintenance_mode False→True must send the same
    'maintenance_announcement' notify as a direct PUT does — both are the same
    kind of blast-radius change to users (spec §13.5), and app/settings/gate.py
    still blocks regular users' writes either way, so skipping the notify would
    leave them getting 503s with no warning banner explaining why.
    """
    from app.notifications.models import Notification

    key = "maintenance_mode"

    # version 1: False -> True (direct PUT notifies — sanity check baseline).
    r = client.put(f"/api/admin/settings/{key}", json={"value": True}, headers=_headers(admin_csrf))
    assert r.status_code == 200
    db.commit()  # 스냅샷을 새로 뜬다 — client 호출은 이 세션과 다른 세션에서 커밋한다
    count_after_first_on = (
        db.query(Notification).filter(Notification.type == "maintenance_announcement").count()
    )
    assert count_after_first_on >= 1

    # version 2: True -> False (turning off must NOT notify again).
    r = client.put(f"/api/admin/settings/{key}", json={"value": False}, headers=_headers(admin_csrf))
    assert r.status_code == 200
    db.commit()
    count_after_off = (
        db.query(Notification).filter(Notification.type == "maintenance_announcement").count()
    )
    assert count_after_off == count_after_first_on

    # Rollback to version 2's snapshot (the value it replaced, i.e. True) —
    # this reapplies maintenance_mode=True exactly like SettingVersions.jsx
    # intends, and must notify just like the original direct PUT did.
    r = client.post(
        f"/api/admin/settings/{key}/rollback",
        json={"version": 2},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200
    assert r.json()["after"] is True
    assert client.get("/api/admin/settings").json()["settings"][key]["value"] is True

    db.commit()  # 스냅샷을 새로 뜬다
    count_after_rollback = (
        db.query(Notification).filter(Notification.type == "maintenance_announcement").count()
    )
    assert count_after_rollback == count_after_first_on + 1, (
        "rollback flipping maintenance_mode False->True must notify active users, "
        "same as a direct PUT does"
    )


def test_operator_cannot_change_settings(client, login_as):
    csrf = login_as("operator")
    r = client.put(
        "/api/admin/settings/notification_retention_days",
        json={"value": 40},
        headers=_headers(csrf),
    )
    assert r.status_code == 403
    assert client.get("/api/admin/settings").status_code == 200  # read OK


def test_string_setting_is_trimmed_on_save(client, login_as):
    """공백 낀 값을 저장해도 실제 저장되는 값엔 공백이 없다.

    관리 화면(NotionConsole.jsx)은 이미 `.trim()` 하지만, 그 화면을 거치지 않는 raw API
    PUT(system_admin)이나 DB 직접 수정으로 공백 섞인 값이 들어오면 - 검증기(`_non_empty_str`)는
    `strip()` 해서 모양만 보고 원문은 그대로 통과시키므로 - 조회 URL 에 `%20` 이 그대로
    붙는다. `notion_tasks_database_id` 는 SYSTEM_ADMIN_ONLY_KEYS 라 system_admin 으로 문다.
    """
    csrf = login_as("system_admin")
    db_id = "a1b2c3d4e5f60718293a4b5c6d7e8f90"  # 32자리 16진수(유효한 모양)
    r = client.put(
        "/api/admin/settings/notion_tasks_database_id",
        json={"value": f" {db_id}\n"},
        headers=_headers(csrf),
    )
    assert r.status_code == 200, r.text
    assert r.json()["after"] == db_id, "저장 응답에 공백이 그대로 남아 있다"

    fetched = client.get("/api/admin/settings").json()["settings"]["notion_tasks_database_id"]
    assert fetched["value"] == db_id, f"저장된 값에 공백이 남았다: {fetched['value']!r}"
