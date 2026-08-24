import pytest

pytestmark = pytest.mark.integration

VALID = {
    "name": "test-service",
    "provider_type": "http_service",
    "base_url": "https://api.anthropic.com",
    "health_url": "https://api.anthropic.com",
    "auth_type": "none",
    "enabled": True,
}


@pytest.fixture()
def admin_csrf(login_as):
    # system_admin: base_url/secret_ref changes apply directly (bypass the
    # §20 approval gate that a plain admin would trigger).
    return login_as("system_admin")


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


def test_create_and_get_integration(client, admin_csrf):
    r = client.post("/api/admin/integrations", json=VALID, headers=_headers(admin_csrf))
    assert r.status_code == 201, r.text
    integration = r.json()["integration"]
    assert integration["name"] == "test-service"
    assert integration["config_version"] == 1
    assert integration["secret_status"] is None

    r = client.get(f"/api/admin/integrations/{integration['id']}", headers=_headers(admin_csrf))
    assert r.status_code == 200


def test_create_rejects_url_not_in_allowlist(client, admin_csrf):
    payload = {**VALID, "name": "evil", "base_url": "http://10.0.0.99:8080"}
    r = client.post("/api/admin/integrations", json=payload, headers=_headers(admin_csrf))
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "url_not_allowed"


def test_create_duplicate_name_conflict(client, admin_csrf):
    client.post("/api/admin/integrations", json=VALID, headers=_headers(admin_csrf))
    r = client.post("/api/admin/integrations", json=VALID, headers=_headers(admin_csrf))
    assert r.status_code == 409


def test_update_bumps_version_and_versions_listed(client, admin_csrf):
    created = client.post(
        "/api/admin/integrations", json=VALID, headers=_headers(admin_csrf)
    ).json()["integration"]

    r = client.patch(
        f"/api/admin/integrations/{created['id']}",
        json={"description": "설명 추가"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200
    assert r.json()["integration"]["config_version"] == 2

    versions = client.get(
        f"/api/admin/integrations/{created['id']}/versions", headers=_headers(admin_csrf)
    ).json()["items"]
    assert [v["version"] for v in versions] == [2, 1]


def test_rollback_restores_previous_config(client, admin_csrf):
    created = client.post(
        "/api/admin/integrations", json=VALID, headers=_headers(admin_csrf)
    ).json()["integration"]
    client.patch(
        f"/api/admin/integrations/{created['id']}",
        json={"base_url": "https://api.anthropic.com"},
        headers=_headers(admin_csrf),
    )

    r = client.post(
        f"/api/admin/integrations/{created['id']}/rollback",
        json={"version": 1},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200
    rolled = r.json()["integration"]
    assert rolled["base_url"] == "https://api.anthropic.com"
    assert rolled["config_version"] == 3  # rollback = new version, append-only


def test_integration_config_approval_rejects_stale_config(client, login_as, admin_csrf):
    """Regression (backend-approvals-jobs 감사 #7): 승인 대기 중 integration 설정이 직접
    수정되면, 그 승인을 나중에 그대로 적용하는 것은 승인자가 검토한 적 없는 옛 설정으로
    현재 설정을 조용히 되돌리는 일이 된다 — `schedule.enable`과 같은 staleness 가드가
    `integration.change_config`에도 있어야 한다.
    """
    created = client.post(
        "/api/admin/integrations", json=VALID, headers=_headers(admin_csrf)
    ).json()["integration"]  # base_url = VALID 의 값

    # 세 주소가 서로 달라야 staleness 를 볼 수 있다 — 허용 목록은 host:port 만 보므로
    # 경로로 가른다(S11 이 내부 러너 호스트를 목록에서 걷어냈다).

    requester_csrf = login_as("admin", email="int-requester@goodmit.co.kr")
    r = client.patch(
        f"/api/admin/integrations/{created['id']}",
        json={"base_url": "https://api.anthropic.com/v1"},
        headers=_headers(requester_csrf),
    )
    assert r.status_code == 202
    approval_id = r.json()["approval"]["id"]

    # client는 세션 쿠키를 하나만 들고 있다 — 위 login_as가 요청자로 세션을 바꿔치기했으므로
    # system_admin으로 다시 로그인해 새 csrf 토큰을 받아야 그 세션으로 계속 조작할 수 있다.
    admin_csrf = login_as("system_admin")

    # 승인 대기 중 system_admin이 직접 설정을 바꾼다 — 즉시 적용된다.
    r2 = client.patch(
        f"/api/admin/integrations/{created['id']}",
        json={"base_url": "https://api.anthropic.com/v2"},
        headers=_headers(admin_csrf),
    )
    assert r2.status_code == 200

    approve = client.post(
        f"/api/admin/approvals/{approval_id}/approve", headers=_headers(admin_csrf)
    )
    assert approve.status_code == 409
    assert "stale" in approve.json()["error"]["message"]

    detail = client.get(
        f"/api/admin/integrations/{created['id']}", headers=_headers(admin_csrf)
    ).json()["integration"]
    assert detail["base_url"] == "https://api.anthropic.com/v2"  # 옛 설정으로 되돌아가지 않는다


def test_rollback_to_unknown_version_404(client, admin_csrf):
    created = client.post(
        "/api/admin/integrations", json=VALID, headers=_headers(admin_csrf)
    ).json()["integration"]
    r = client.post(
        f"/api/admin/integrations/{created['id']}/rollback",
        json={"version": 99},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 404


def test_enable_disable(client, admin_csrf):
    created = client.post(
        "/api/admin/integrations", json=VALID, headers=_headers(admin_csrf)
    ).json()["integration"]
    r = client.post(
        f"/api/admin/integrations/{created['id']}/disable", headers=_headers(admin_csrf)
    )
    assert r.status_code == 200
    detail = client.get(
        f"/api/admin/integrations/{created['id']}", headers=_headers(admin_csrf)
    ).json()["integration"]
    assert detail["enabled"] is False


def test_health_check_up_and_down(client, admin_csrf, fake_http, fake_clock):
    created = client.post(
        "/api/admin/integrations", json=VALID, headers=_headers(admin_csrf)
    ).json()["integration"]

    fake_http.on("https://api.anthropic.com", json_body={"status": "ok"})
    r = client.post(
        f"/api/admin/integrations/{created['id']}/health", headers=_headers(admin_csrf)
    )
    assert r.status_code == 200
    assert r.json()["status"] == "up"

    fake_http.on_connect_error("https://api.anthropic.com")
    r = client.post(
        f"/api/admin/integrations/{created['id']}/health", headers=_headers(admin_csrf)
    )
    assert r.json()["status"] == "down"
    assert r.json()["detail"] == "connection_error"

    detail = client.get(
        f"/api/admin/integrations/{created['id']}", headers=_headers(admin_csrf)
    ).json()["integration"]
    assert detail["last_health_status"] == "down"
    assert detail["last_health_at"] is not None


def test_health_check_timeout(client, admin_csrf, fake_http):
    created = client.post(
        "/api/admin/integrations", json=VALID, headers=_headers(admin_csrf)
    ).json()["integration"]
    fake_http.on_timeout("https://api.anthropic.com")
    r = client.post(
        f"/api/admin/integrations/{created['id']}/health", headers=_headers(admin_csrf)
    )
    assert r.json()["status"] == "down"
    assert r.json()["detail"] == "timeout"


def test_secret_status_shown_never_value(client, admin_csrf, settings):
    (settings.secrets_dir / "svc-secret").write_text("PLAINTEXT-VALUE", encoding="utf-8")
    payload = {
        **VALID,
        "name": "with-secret",
        "auth_type": "bearer",
        "secret_ref": "svc-secret",
    }
    r = client.post("/api/admin/integrations", json=payload, headers=_headers(admin_csrf))
    assert r.status_code == 201
    assert r.json()["integration"]["secret_status"] == "configured"
    assert "PLAINTEXT-VALUE" not in r.text

    listing = client.get("/api/admin/integrations", headers=_headers(admin_csrf))
    assert "PLAINTEXT-VALUE" not in listing.text


def test_operator_can_read_and_health_but_not_mutate(client, login_as, make_user, fake_http):
    # Admin creates one first.
    admin_client_csrf = login_as("admin")
    created = client.post(
        "/api/admin/integrations", json=VALID, headers=_headers(admin_client_csrf)
    ).json()["integration"]

    operator_csrf = login_as("operator")
    assert client.get("/api/admin/integrations").status_code == 200

    fake_http.on("https://api.anthropic.com", json_body={})
    r = client.post(
        f"/api/admin/integrations/{created['id']}/health", headers=_headers(operator_csrf)
    )
    assert r.status_code == 200

    r = client.post(
        "/api/admin/integrations",
        json={**VALID, "name": "op-made"},
        headers=_headers(operator_csrf),
    )
    assert r.status_code == 403


def test_user_role_cannot_read_integrations(client, login_as):
    login_as("user")
    assert client.get("/api/admin/integrations").status_code == 403


def test_nothing_is_seeded_by_default(db, settings):
    """기본 시드가 **비어 있다.**

    S11 이 n8n·러너 셋을 걷어냈고 마지막 하나였던 Notion 은 Notion 런타임과 함께 사라졌다.
    설치 직후 연동이 하나 놓여 있으면 그것이 무엇을 부르는지 아무도 안 본 채로 살아 있게
    된다 — 지금은 그런 항목이 없어야 한다.
    """
    from app.core.allowlist import AllowlistRegistry
    from app.integrations.discovery import KNOWN_INTEGRATIONS, seed_known_integrations

    allowlists = AllowlistRegistry(settings.config_dir)
    assert KNOWN_INTEGRATIONS == [], f"기본 시드가 다시 생겼다: {KNOWN_INTEGRATIONS}"
    assert seed_known_integrations(db, allowlists=allowlists) == []


def test_discovery_seed_is_idempotent(db, settings, monkeypatch):
    """시드가 비었다고 **두 번 돌려도 되는가**를 안 보면, 다음 항목이 들어오는 날 그 성질이
    한 번도 검증된 적 없는 상태가 된다. 그래서 표본을 하나 꽂아 두고 두 번 돌린다.
    """
    from app.core.allowlist import AllowlistRegistry
    from app.integrations import discovery

    sample = [{
        "name": "seed-sample",
        "provider_type": "http_service",
        # 호스트는 런타임 허용 목록에 있어야 한다 — 없으면 저장 시점에 거절당해서
        # 이 시험이 「두 번째가 안 만든다」가 아니라 「한 번도 못 만든다」를 보게 된다.
        "base_url": "https://api.anthropic.com",
        "health_url": "https://api.anthropic.com/v1/models",
        "capabilities": {},
        "enabled": True,
    }]
    monkeypatch.setattr(discovery, "KNOWN_INTEGRATIONS", sample)

    allowlists = AllowlistRegistry(settings.config_dir)
    first = discovery.seed_known_integrations(db, allowlists=allowlists)
    db.commit()
    assert first == ["seed-sample"], f"표본을 한 번도 안 만들었다: {first}"
    assert discovery.seed_known_integrations(db, allowlists=allowlists) == []
