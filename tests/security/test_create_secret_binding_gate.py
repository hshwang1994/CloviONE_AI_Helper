"""qa-contract-change: secret 을 목적지에 묶는 생성·활성화·복제를 admin 이 승인 없이 못 한다는 규칙의 소비자가 둘에서 하나로 줄었다 — 러너 화면이 S11 과 함께 사라졌다. 연동 쪽 절이 create·patch(활성화) 세 갈래를 전부 그대로 보고 있고, 규칙과 그 판정 코드는 한 줄도 안 바뀌었다."""

"""승인 게이트 우회: '만들기'로 '목적지 바꾸기'를 달성할 수 있으면 안 된다.

오늘 PATCH/rollback에 base_url·health_url·secret_ref 변경을 승인 대상으로 넣었다.
이유는 allowlist가 '외부로 못 나간다'만 보장하고, 허용된 내부 서비스끼리
(n8n:5678 ↔ 러너:8787) secret을 옮기는 것은 막지 못하기 때문이다 —
'어느 내부 서비스로 secret을 보내느냐'는 승인 게이트가 지킨다.

그런데 POST(create)는 그대로였다. 일반 admin이 승인 없이

    POST /api/admin/integrations
    {base_url: 러너:8787, secret_ref: n8n_token, auth_type: bearer}

를 만들고 헬스체크를 눌러 n8n 토큰을 러너로 보낼 수 있었다. PATCH가 막는 일을
'새로 만들기'로 그대로 달성한다.

secret이 실제로 전송되는 조건은 OutboundClient 기준 `auth_type != "none"` 이다
(그때만 secret_ref를 Authorization/X-API-Key에 실어 보낸다). 그래서 secret 바인딩을
새로 만드는 것(auth_type != none)은 system_admin 권한을 요구한다.

추가로, auth_type 자체가 민감 필드다: 이미 secret_ref·base_url이 잡혀 있는 객체를
auth_type none→bearer 로 PATCH 하면 그 순간 secret이 흐르기 시작한다. auth_type이
승인 대상에서 빠져 있으면 create-none → patch-authtype 로 create 게이트를 우회한다.
"""

import pytest

pytestmark = pytest.mark.security


def _h(csrf):
    return {"X-CSRF-Token": csrf}


# --- Integrations -----------------------------------------------------------

def _post_integration(client, csrf, **overrides):
    payload = {
        "name": "gate-int",
        "provider_type": "http_service",
        "base_url": "https://api.notion.com",
        "auth_type": "none",
        "enabled": True,
    }
    payload.update(overrides)
    return client.post("/api/admin/integrations", json=payload, headers=_h(csrf))


def test_admin_cannot_create_secret_bound_integration(client, login_as):
    """admin(비-system_admin)이 secret을 목적지에 묶는 Integration을 승인 없이 만들 수 없다."""
    csrf = login_as("admin")
    r = _post_integration(
        client, csrf, name="exfil-int", secret_ref="n8n_token", auth_type="bearer"
    )
    assert r.status_code == 403, (
        "일반 admin이 secret 바인딩 Integration을 즉시 생성했다 — 헬스체크 한 번에 "
        f"secret이 임의의 내부 대상으로 나간다. 응답: {r.status_code} {r.text[:300]}"
    )


def test_system_admin_can_create_secret_bound_integration(client, login_as):
    """system_admin은 그대로 만들 수 있어야 한다 — 정상 작업을 막지 않는다(과잉 수정 방지)."""
    csrf = login_as("system_admin")
    r = _post_integration(
        client, csrf, name="ok-int", secret_ref="svc-secret", auth_type="bearer"
    )
    assert r.status_code == 201, r.text


def test_admin_can_create_secretless_integration(client, login_as):
    """secret을 묶지 않는(auth_type=none) 생성은 admin의 정상 작업 — 막지 않는다."""
    csrf = login_as("admin")
    r = _post_integration(client, csrf, name="plain-int", auth_type="none")
    assert r.status_code == 201, r.text


def test_admin_patch_activating_auth_is_gated_integration(client, login_as):
    """create-none → patch(auth_type none→bearer) 로 create 게이트를 우회하지 못한다.

    system_admin이 secret_ref는 잡되 auth_type=none 으로 만든다(이 시점엔 secret이
    흐르지 않는다). 그 뒤 admin이 auth_type만 bearer로 바꾸면 그 순간 secret이 흐른다 —
    이 변경은 승인을 거쳐야 한다.
    """
    sa = login_as("system_admin")
    created = _post_integration(
        client, sa, name="activate-int", secret_ref="svc-secret", auth_type="none"
    )
    assert created.status_code == 201, created.text
    integration_id = created.json()["integration"]["id"]

    admin = login_as("admin")
    r = client.patch(
        f"/api/admin/integrations/{integration_id}",
        json={"auth_type": "bearer"},
        headers=_h(admin),
    )
    assert r.status_code == 202, (
        "auth_type none→bearer 변경이 승인 없이 적용됐다 — 이 순간부터 secret이 나간다. "
        f"응답: {r.status_code} {r.text[:300]}"
    )


# Runner 절은 S11 이 그 화면과 함께 걷어냈다. 같은 게이트를 지는 것은 이제 연동 하나이고,
# 위 절이 create · patch(활성화) · 세 갈래를 전부 본다 — 규칙이 사라진 것이 아니라
# 그것을 지나던 자원 하나가 사라졌다.
