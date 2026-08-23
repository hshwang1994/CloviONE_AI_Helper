"""Integration의 health_url 변경도 승인 대상이다.

health_url은 헬스체크 때 secret과 함께 호출되는 주소다(service.py run_health_check:
`url = row.health_url or row.base_url` → OutboundClient가 secret_ref를 Authorization에 실어
보낸다). 그래서 이 값을 바꾸는 것은 **secret을 다른 대상에게 보내는 일**이다.

base_url·secret_ref는 승인 게이트를 지나는데 health_url만 빠져 있었다. 그래서 일반 admin이
승인 없이 health_url을 다른 allowlist 호스트로 돌리고 헬스체크를 눌러 토큰을 그쪽으로
보낼 수 있었다. allowlist는 '외부로 못 나간다'만 보장한다 — '어느 내부 서비스로 가느냐'는
승인 게이트가 지켜야 한다.

같은 판정이 러너 라우터에는 이유 주석까지 달고 이미 있었다(runners/router.py:80-86).
복붙이 갈라진 자리다.
"""

import pytest

pytestmark = pytest.mark.security


def _integration(client, csrf):
    r = client.post(
        "/api/admin/integrations",
        json={
            "name": "health-url-gate-test",
            "provider_type": "http_service",
            "base_url": "https://api.notion.com",
            "health_url": "https://api.notion.com/healthz",
            "auth_type": "none",
            "enabled": True,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    return (body.get("integration") or body)["id"]


def test_health_url_change_is_approval_gated_for_admin(client, login_as):
    """admin이 health_url만 바꿔도 승인을 거쳐야 한다 — secret이 그쪽으로 나가기 때문이다."""
    csrf = login_as("system_admin")
    integration_id = _integration(client, csrf)

    csrf = login_as("admin")   # system_admin이 아닌 admin
    r = client.patch(
        f"/api/admin/integrations/{integration_id}",
        json={"health_url": "https://api.notion.com/collect"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 202, (
        "health_url 변경이 승인 없이 즉시 적용됐다. 이 주소로 secret이 나간다. "
        f"응답: {r.status_code} {r.text[:300]}"
    )


def test_health_url_rollback_is_approval_gated_for_admin(client, login_as):
    """롤백으로도 같은 일을 할 수 있으면 PATCH만 막는 것은 의미가 없다."""
    csrf = login_as("system_admin")
    integration_id = _integration(client, csrf)

    # system_admin이 health_url을 바꿔 새 버전을 만든다(v2).
    r = client.patch(
        f"/api/admin/integrations/{integration_id}",
        json={"health_url": "https://api.notion.com/collect"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text

    versions = client.get(f"/api/admin/integrations/{integration_id}/versions").json()
    items = versions.get("items") or versions.get("versions") or []
    assert items, f"버전 목록을 읽지 못했다: {versions}"
    first = min(int(v["version"]) for v in items)

    csrf = login_as("admin")
    r = client.post(
        f"/api/admin/integrations/{integration_id}/rollback",
        json={"version": first},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 202, (
        "health_url을 되돌리는 롤백이 승인 없이 적용됐다 — PATCH 게이트를 우회하는 경로다. "
        f"응답: {r.status_code} {r.text[:300]}"
    )
