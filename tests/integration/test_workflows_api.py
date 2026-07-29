import pytest

pytestmark = pytest.mark.integration

VALID = {
    "name": "문서 생성 workflow",
    "webhook_url": "http://127.0.0.1:5678/webhook/doc-gen",
    "operation_mode": "write",
    "approval_required": True,
}


@pytest.fixture()
def admin_csrf(login_as):
    return login_as("admin")


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


def test_create_and_view_workflow(client, admin_csrf):
    r = client.post("/api/admin/workflows", json=VALID, headers=_headers(admin_csrf))
    assert r.status_code == 201, r.text
    wf = r.json()["workflow"]
    assert wf["operation_mode"] == "write"
    assert wf["approval_required"] is True


def test_webhook_url_allowlist_enforced(client, admin_csrf):
    r = client.post(
        "/api/admin/workflows",
        json={**VALID, "name": "evil", "webhook_url": "http://evil.example.com/hook"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 400


def test_invalid_operation_mode_rejected(client, admin_csrf):
    r = client.post(
        "/api/admin/workflows",
        json={**VALID, "name": "badmode", "operation_mode": "execute"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422


def test_clearing_tags_does_not_crash(client, admin_csrf):
    # Reproduced live: PATCH {"tags": null} (exactly what the edit form sends when a
    # previously-populated tags field is emptied) 500'd — WorkflowConfig.tags is
    # list[str] with no None branch, so the merged-dict revalidation raised a bare
    # pydantic.ValidationError that fell through to the generic 500 handler.
    r = client.post(
        "/api/admin/workflows",
        json={**VALID, "name": "tagged", "tags": ["report", "weekly"]},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 201, r.text
    wf_id = r.json()["workflow"]["id"]
    r = client.patch(
        f"/api/admin/workflows/{wf_id}", json={"tags": None}, headers=_headers(admin_csrf)
    )
    assert r.status_code == 200, r.text
    assert r.json()["workflow"]["tags"] == []


def test_workflow_test_is_reachability_only_never_post(client, admin_csrf, fake_http):
    wf = client.post("/api/admin/workflows", json=VALID, headers=_headers(admin_csrf)).json()[
        "workflow"
    ]
    fake_http.on("http://127.0.0.1:5678/webhook/doc-gen", status=404)  # n8n GET on POST hook
    r = client.post(f"/api/admin/workflows/{wf['id']}/test", headers=_headers(admin_csrf))
    assert r.json()["status"] == "reachable"
    assert fake_http.requests[0].method == "GET"  # write workflow NOT executed

    fake_http.on_connect_error("http://127.0.0.1:5678/webhook/doc-gen")
    r = client.post(f"/api/admin/workflows/{wf['id']}/test", headers=_headers(admin_csrf))
    assert r.json()["status"] == "unreachable"


def test_disabled_workflow_invoke_blocked(db, app, fake_http, admin_csrf, client):
    from app.workflows.provider_n8n import N8nWorkflowProvider, WorkflowDisabledError
    from app.workflows.service import get_workflow_or_404

    wf = client.post("/api/admin/workflows", json=VALID, headers=_headers(admin_csrf)).json()[
        "workflow"
    ]
    client.post(f"/api/admin/workflows/{wf['id']}/disable", headers=_headers(admin_csrf))

    row = get_workflow_or_404(db, wf["id"])
    db.refresh(row)
    provider = N8nWorkflowProvider(app.state.outbound_client)
    with pytest.raises(WorkflowDisabledError):
        provider.invoke(row, {"x": 1}, timeout=5.0)
    assert fake_http.requests == []


def test_update_rollback_and_versions(client, admin_csrf):
    wf = client.post("/api/admin/workflows", json=VALID, headers=_headers(admin_csrf)).json()[
        "workflow"
    ]
    client.patch(
        f"/api/admin/workflows/{wf['id']}",
        json={"purpose": "업데이트된 목적"},
        headers=_headers(admin_csrf),
    )
    versions = client.get(
        f"/api/admin/workflows/{wf['id']}/versions", headers=_headers(admin_csrf)
    ).json()["items"]
    assert [v["version"] for v in versions] == [2, 1]

    r = client.post(
        f"/api/admin/workflows/{wf['id']}/rollback",
        json={"version": 1},
        headers=_headers(admin_csrf),
    )
    assert r.json()["workflow"]["purpose"] is None


def test_seed_known_workflows_idempotent(db, app):
    from app.workflows.service import seed_known_workflows

    first = seed_known_workflows(db, allowlists=app.state.allowlists)
    db.commit()
    # 이름을 여기 다시 적지 않고 seed 정의에서 읽는다 — 시드에 워크플로가 하나 늘 때마다
    # 이 줄이 깨지던 것을 반복하지 않기 위해서다(실제로 그렇게 깨져 있었다).
    # 이 테스트가 보는 것은 목록의 내용이 아니라 '두 번 돌려도 또 만들지 않는다'는 것이다.
    assert first, "시드가 아무것도 만들지 않았다"
    assert seed_known_workflows(db, allowlists=app.state.allowlists) == []


def test_auditor_can_read_workflows(client, login_as):
    login_as("auditor")
    assert client.get("/api/admin/workflows").status_code == 200


def test_user_cannot_read_workflows(client, login_as):
    login_as("user")
    assert client.get("/api/admin/workflows").status_code == 403
