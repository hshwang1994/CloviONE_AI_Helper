"""Document automation end-to-end (spec §19)."""

import pytest

from app.jobs.handlers.document_generate import handle_document_generate
from app.jobs.worker import Worker, WorkerContext

pytestmark = pytest.mark.integration

DOC_URL = "http://127.0.0.1:5678/webhook/doc-gen"


@pytest.fixture()
def admin_csrf(login_as):
    return login_as("admin")


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


@pytest.fixture()
def workflow_id(client, admin_csrf):
    return client.post(
        "/api/admin/workflows",
        json={
            "name": "문서 생성",
            "webhook_url": DOC_URL,
            "operation_mode": "write",
            "approval_required": True,
        },
        headers=_headers(admin_csrf),
    ).json()["workflow"]["id"]


@pytest.fixture()
def open_workflow_id(client, admin_csrf):
    """발행에 승인이 필요 없는 workflow — auto_publish가 실제로 발행되는 경우용."""
    return client.post(
        "/api/admin/workflows",
        json={
            "name": "문서 생성 (무승인)",
            "webhook_url": DOC_URL,
            "operation_mode": "write",
            "approval_required": False,
        },
        headers=_headers(admin_csrf),
    ).json()["workflow"]["id"]


@pytest.fixture()
def doc_worker(app, settings, fake_clock):
    ctx = WorkerContext(
        settings=settings, clock=fake_clock, outbound_client=app.state.outbound_client
    )
    return Worker(
        app.state.session_factory, fake_clock,
        {"document_generate": handle_document_generate}, ctx,
    )


def _generate(client, csrf, workflow_id, mode, period="2026-W28"):
    return client.post(
        "/api/admin/documents/generate",
        json={
            "workflow_id": workflow_id,
            "mode": mode,
            "period": period,
            "config": {"target_parent_page": "page-123", "template_version": 1,
                       "prompt_template": "weekly"},
        },
        headers=_headers(csrf),
    )


def test_preview_only_stops_at_preview(client, admin_csrf, workflow_id, doc_worker, fake_http):
    fake_http.on(
        DOC_URL,
        json_body={"title": "주간 보고서", "body": "완료된 작업 요약입니다. " * 3,
                   "source_row_count": 4},
    )
    r = _generate(client, admin_csrf, workflow_id, "preview_only")
    assert r.status_code == 202
    gen_id = r.json()["generation"]["id"]

    doc_worker.run_once()
    detail = client.get(f"/api/admin/documents/{gen_id}").json()["generation"]
    assert detail["status"] == "preview_ready"
    assert detail["preview"]["title"] == "주간 보고서"
    # Preview only → workflow called once with action=preview, never publish.
    import json as _json

    assert _json.loads(fake_http.requests[0].content)["action"] == "preview"
    assert len(fake_http.requests) == 1


def test_quality_gate_failure_blocks_publish(client, admin_csrf, workflow_id, doc_worker, fake_http):
    fake_http.on(DOC_URL, json_body={"title": "", "body": "짧", "source_row_count": 0})
    r = _generate(client, admin_csrf, workflow_id, "auto_publish")
    gen_id = r.json()["generation"]["id"]
    doc_worker.run_once()
    detail = client.get(f"/api/admin/documents/{gen_id}").json()["generation"]
    assert detail["status"] == "quality_failed"
    assert detail["quality_problems"]
    assert len(fake_http.requests) == 1  # only preview attempted, no publish


def test_auto_publish_flow(client, admin_csrf, open_workflow_id, doc_worker, fake_http):
    fake_http.on(
        DOC_URL,
        json_body={
            "title": "주간 보고서", "body": "완료된 작업 요약입니다. " * 3,
            "source_row_count": 4, "published_ref": "https://www.notion.so/pub123",
        },
    )
    r = _generate(client, admin_csrf, open_workflow_id, "auto_publish")
    gen_id = r.json()["generation"]["id"]
    doc_worker.run_once()
    detail = client.get(f"/api/admin/documents/{gen_id}").json()["generation"]
    assert detail["status"] == "published"
    assert detail["published_ref"] == "https://www.notion.so/pub123"
    # preview + publish calls.
    actions = [__import__("json").loads(r.content)["action"] for r in fake_http.requests]
    assert actions == ["preview", "publish"]


def test_duplicate_period_target_blocked(client, admin_csrf, workflow_id, doc_worker, fake_http):
    fake_http.on(
        DOC_URL,
        json_body={"title": "T", "body": "본문 내용 충분히 깁니다 " * 3, "source_row_count": 2},
    )
    r1 = _generate(client, admin_csrf, workflow_id, "preview_only", period="2026-W30")
    assert r1.status_code == 202
    r2 = _generate(client, admin_csrf, workflow_id, "preview_only", period="2026-W30")
    assert r2.status_code == 409  # same period+target+version


def test_preview_then_approve_creates_approval(client, admin_csrf, workflow_id, doc_worker, fake_http, db):
    fake_http.on(
        DOC_URL,
        json_body={"title": "승인용 보고서", "body": "본문 내용 충분히 깁니다 " * 3,
                   "source_row_count": 3},
    )
    r = _generate(client, admin_csrf, workflow_id, "preview_then_approve")
    gen_id = r.json()["generation"]["id"]
    doc_worker.run_once()
    detail = client.get(f"/api/admin/documents/{gen_id}").json()["generation"]
    assert detail["status"] == "awaiting_approval"

    from app.approvals.models import Approval

    approval = db.query(Approval).filter(Approval.request_type == "document.publish").one()
    assert approval.object_id == gen_id


def test_document_generation_rbac(client, login_as, workflow_id):
    csrf = login_as("operator")
    r = client.post(
        "/api/admin/documents/generate",
        json={"workflow_id": workflow_id, "mode": "preview_only", "period": "x", "config": {}},
        headers=_headers(csrf),
    )
    assert r.status_code == 403
