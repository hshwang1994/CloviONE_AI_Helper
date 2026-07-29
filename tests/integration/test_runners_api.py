import pytest

pytestmark = pytest.mark.integration

VALID = {
    "name": "test-runner",
    "provider_type": "local_http",
    "base_url": "http://127.0.0.1:8787",
    "timeout_seconds": 30,
}


@pytest.fixture()
def admin_csrf(login_as):
    return login_as("admin")


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


def _create(client, csrf, **overrides):
    return client.post(
        "/api/admin/runners", json={**VALID, **overrides}, headers=_headers(csrf)
    )


def test_new_runner_created_disabled_regardless_of_request(client, admin_csrf):
    r = _create(client, admin_csrf, enabled=True)
    assert r.status_code == 201
    assert r.json()["runner"]["enabled"] is False  # spec §15.5


def test_runner_url_allowlist_enforced(client, admin_csrf):
    r = _create(client, admin_csrf, name="evil", base_url="http://8.8.8.8:80")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "url_not_allowed"


def test_enable_disable_flow(client, admin_csrf):
    runner = _create(client, admin_csrf).json()["runner"]
    r = client.post(f"/api/admin/runners/{runner['id']}/enable", headers=_headers(admin_csrf))
    assert r.status_code == 200
    detail = client.get(f"/api/admin/runners/{runner['id']}", headers=_headers(admin_csrf))
    assert detail.json()["runner"]["enabled"] is True


def test_clone_creates_disabled_copy(client, admin_csrf):
    runner = _create(client, admin_csrf).json()["runner"]
    r = client.post(
        f"/api/admin/runners/{runner['id']}/clone",
        json={"name": "test-runner-copy"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200
    copy = r.json()["runner"]
    assert copy["name"] == "test-runner-copy"
    assert copy["base_url"] == runner["base_url"]
    assert copy["enabled"] is False
    assert copy["id"] != runner["id"]


def test_health_check_updates_status_and_breaker(client, admin_csrf, fake_http):
    runner = _create(client, admin_csrf).json()["runner"]
    fake_http.on("http://127.0.0.1:8787", json_body={"ok": True})
    r = client.post(f"/api/admin/runners/{runner['id']}/health", headers=_headers(admin_csrf))
    assert r.json()["status"] == "up"

    fake_http.on_connect_error("http://127.0.0.1:8787")
    r = client.post(f"/api/admin/runners/{runner['id']}/health", headers=_headers(admin_csrf))
    assert r.json()["status"] == "down"
    detail = client.get(f"/api/admin/runners/{runner['id']}", headers=_headers(admin_csrf))
    assert detail.json()["runner"]["consecutive_failures"] == 1


def test_test_request_endpoint(client, admin_csrf, fake_http):
    runner = _create(client, admin_csrf).json()["runner"]
    fake_http.on("http://127.0.0.1:8787", json_body={"pong": True})
    r = client.post(f"/api/admin/runners/{runner['id']}/test", headers=_headers(admin_csrf))
    assert r.status_code == 200
    assert r.json()["ok"] is True

    fake_http.on_connect_error("http://127.0.0.1:8787")
    r = client.post(f"/api/admin/runners/{runner['id']}/test", headers=_headers(admin_csrf))
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "runner_unavailable"


def test_update_and_rollback(client, admin_csrf):
    runner = _create(client, admin_csrf).json()["runner"]
    client.patch(
        f"/api/admin/runners/{runner['id']}",
        json={"timeout_seconds": 120},
        headers=_headers(admin_csrf),
    )
    r = client.post(
        f"/api/admin/runners/{runner['id']}/rollback",
        json={"version": 1},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200
    rolled = r.json()["runner"]
    assert rolled["timeout_seconds"] == 30
    assert rolled["config_version"] == 3


def test_operator_reads_but_cannot_mutate(client, login_as, admin_csrf):
    runner = _create(client, admin_csrf).json()["runner"]
    operator_csrf = login_as("operator")
    assert client.get("/api/admin/runners").status_code == 200
    r = client.patch(
        f"/api/admin/runners/{runner['id']}",
        json={"timeout_seconds": 5},
        headers=_headers(operator_csrf),
    )
    assert r.status_code == 403


def test_provider_blocks_disabled_runner_invoke(db, app, fake_clock, fake_http, settings):
    from app.runners.provider_http import RunnerHttpProvider, RunnerUnavailableError
    from app.runners.schemas import RunnerConfig
    from app.runners.service import create_runner

    row = create_runner(
        db,
        RunnerConfig(name="disabled-runner", base_url="http://127.0.0.1:8787"),
        allowlists=app.state.allowlists,
        created_by=None,
    )
    db.commit()
    provider = RunnerHttpProvider(app.state.outbound_client)
    with pytest.raises(RunnerUnavailableError):
        provider.invoke(db, row, {"x": 1}, now=fake_clock.now())
    assert fake_http.requests == []
