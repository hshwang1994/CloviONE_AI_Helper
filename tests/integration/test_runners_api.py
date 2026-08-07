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


def test_health_check_without_health_url_treats_4xx_as_up(client, admin_csrf, fake_http):
    """수동 '상태 확인'도 자동 스윕(run_all_runner_health_checks)과 같은 '거짓 down 방지'
    규칙을 따라야 한다: 전용 health_url이 없는 러너는 base_url 도달 가능성만 본다 — 인증된
    POST만 받는 러너가 GET에 404를 줘도 프로세스는 살아있으므로 'up'이다
    (app/runners/service.py::run_all_runner_health_checks 문서 참조, round36 감사).

    수정 전에는 단건 점검(run_runner_health_check)이 항상 `< 400` 엄격 기준을 써서 같은
    404 응답을 'down'으로 오판했다 — 그 오판이 record_runner_result(success=False)로
    이어져, 운영자가 '상태 확인' 버튼을 5번 누르면 정상 러너가 서킷 브레이커에 의해
    실제로 degraded/circuit_open 상태로 떨어진다.
    """
    runner = _create(client, admin_csrf).json()["runner"]
    fake_http.on("http://127.0.0.1:8787", status=404)
    r = client.post(f"/api/admin/runners/{runner['id']}/health", headers=_headers(admin_csrf))
    assert r.json()["status"] == "up"
    detail = client.get(f"/api/admin/runners/{runner['id']}", headers=_headers(admin_csrf))
    assert detail.json()["runner"]["consecutive_failures"] == 0


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


def test_runner_config_approval_rejects_stale_config(client, login_as, admin_csrf):
    """Regression (backend-approvals-jobs 감사 #7): 승인 대기 중 runner 설정이 직접
    수정되면, 그 승인을 나중에 그대로 적용하는 것은 승인자가 검토한 적 없는 옛 설정으로
    현재 설정을 조용히 되돌리는 일이 된다 — `schedule.enable`과 같은 staleness 가드가
    `runner.change_config`에도 있어야 한다.
    """
    runner = _create(client, admin_csrf).json()["runner"]  # base_url = 127.0.0.1:8787

    r = client.patch(
        f"/api/admin/runners/{runner['id']}",
        json={"base_url": "http://127.0.0.1:8788"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 202
    approval_id = r.json()["approval"]["id"]

    # 승인 대기 중 다른 사람(system_admin)이 직접 설정을 바꾼다 — 승인은 즉시 적용된다.
    sys_csrf = login_as("system_admin", email="runner-sys@goodmit.co.kr")
    r2 = client.patch(
        f"/api/admin/runners/{runner['id']}",
        json={"base_url": "http://127.0.0.1:8789"},
        headers=_headers(sys_csrf),
    )
    assert r2.status_code == 200

    approve = client.post(
        f"/api/admin/approvals/{approval_id}/approve", headers=_headers(sys_csrf)
    )
    assert approve.status_code == 409
    assert "stale" in approve.json()["error"]["message"]

    detail = client.get(
        f"/api/admin/runners/{runner['id']}", headers=_headers(sys_csrf)
    ).json()["runner"]
    assert detail["base_url"] == "http://127.0.0.1:8789"  # 옛 설정으로 되돌아가지 않는다


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
