"""Regression tests for the backend-integrations audit findings.

qa-contract-replaced-by: tests/regression/test_workflows_integrations_audit_fixes.py

Each test reproduces the defect statement itself (not just the fixed code path),
matching the convention in test_review3_fixes.py / test_review4_fixes.py.

Findings covered (see the audit report for file/line detail):
  2. IntegrationConfig.capabilities: null on PATCH was not normalized, so
     "clear capabilities" 500/422'd.
  5. Integration health check graded a 3xx redirect response as "up" even
     though OutboundClient never follows redirects.
  6. Integration name-uniqueness was a plain SELECT pre-check, not race-safe
     against a concurrent insert (IntegrityError could leak as 500).

S11 이 n8n·러너를 걷어내면서 워크플로·문서 생성 쪽 findings(1·3, 그리고 6의 워크플로
절반)는 그 기능과 함께 사라졌다. 남은 셋은 연동 레지스트리 소유라 그대로다.
주소도 함께 옮겼다 — 내부 러너 포트가 허용 목록에서 빠져 저장 자체가 안 된다.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

# 이 파일의 시험은 **전용 DB** 가 필요하다(D-190) — 두 번째 커넥션이나 별도
# 프로세스가 이 시험의 데이터를 봐야 하기 때문이다. 공유 DB + 트랜잭션 되감기
# 계층에서는 그 데이터가 트랜잭션 밖으로 안 나가서 아무것도 증명하지 못한다.
pytestmark = [pytest.mark.regression, pytest.mark.real_db]


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


def test_clearing_integration_capabilities_is_normalized_not_rejected(
    client, login_as
):
    csrf = login_as("system_admin", email="audit-caps@goodmit.co.kr")
    created = client.post(
        "/api/admin/integrations",
        json={
            "name": "audit-capabilities",
            "provider_type": "http_service",
            "base_url": "https://api.notion.com",
            "auth_type": "none",
            "capabilities": {"foo": "bar"},
        },
        headers=_headers(csrf),
    ).json()["integration"]
    assert created["capabilities"] == {"foo": "bar"}

    # Reproduces the bug: IntegrationConfig.capabilities is dict (no None branch),
    # so merging an explicit null used to raise a bare pydantic.ValidationError,
    # caught globally as a generic 422 instead of clearing the field.
    r = client.patch(
        f"/api/admin/integrations/{created['id']}",
        json={"capabilities": None},
        headers=_headers(csrf),
    )
    assert r.status_code == 200, r.text
    assert r.json()["integration"]["capabilities"] == {}


def test_health_check_redirect_is_not_reported_as_healthy(client, login_as, fake_http):
    csrf = login_as("system_admin", email="audit-health-redirect@goodmit.co.kr")
    created = client.post(
        "/api/admin/integrations",
        json={
            "name": "audit-redirect-service",
            "provider_type": "http_service",
            "base_url": "https://api.notion.com",
            "auth_type": "none",
        },
        headers=_headers(csrf),
    ).json()["integration"]

    # OutboundClient is built with follow_redirects=False (SSRF safety) — this 302
    # IS the response actually received, not a stand-in for the redirect target.
    fake_http.on("https://api.notion.com", status=302)
    r = client.post(
        f"/api/admin/integrations/{created['id']}/health", headers=_headers(csrf)
    )
    assert r.status_code == 200
    assert r.json()["status"] == "down", "3xx 리다이렉트 응답이 여전히 up으로 보고된다"
    assert r.json()["detail"] == "HTTP 302"


def test_concurrent_integration_creates_with_same_name_never_leak_a_500(db_url, settings):
    from app.core.allowlist import AllowlistRegistry
    from app.core.db import make_engine, make_session_factory
    from app.core.errors import ConflictError
    from app.integrations import service as integrations_service
    from app.integrations.schemas import IntegrationConfig

    url = db_url
    allowlists = AllowlistRegistry(settings.config_dir)

    # Prime the file into WAL mode via a single connection first — see the
    # matching comment in test_concurrent_workflow_creates_with_same_name_never_leak_a_500.
    warm_engine = make_engine(url)
    with warm_engine.connect():
        pass
    warm_engine.dispose()

    def attempt(_i: int) -> str:
        engine = make_engine(url)
        factory = make_session_factory(engine)
        try:
            with factory() as db:
                config = IntegrationConfig(
                    name="race-integration",
                    provider_type="http_service",
                    base_url="https://api.notion.com",
                )
                try:
                    integrations_service.create_integration(
                        db, config, allowlists=allowlists, created_by=None,
                    )
                    db.commit()
                    return "created"
                except ConflictError:
                    db.rollback()
                    return "conflict"
        finally:
            engine.dispose()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))

    assert results.count("created") == 1, f"동시에 이름이 중복 생성됐다: {results}"
    assert results.count("conflict") == 7, (
        f"IntegrityError가 ConflictError로 흡수되지 않고 다른 예외(=500)로 샜다: {results}"
    )
