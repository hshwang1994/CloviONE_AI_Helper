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


def test_non_numeric_template_version_rejected_with_422_not_500(client, admin_csrf, workflow_id):
    # UA-29: config는 자유형 dict라 template_version에 타입 검증이 없었다 - int(config
    # .get("template_version", 1))이 처리 안 된 ValueError로 500이 났다. 사용자 입력
    # 오류는 422여야 한다.
    r = client.post(
        "/api/admin/documents/generate",
        json={
            "workflow_id": workflow_id,
            "mode": "preview_only",
            "period": "2026-W31",
            "config": {"target_parent_page": "page-123", "template_version": "v2"},
        },
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422, r.text


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


def test_preview_then_approve_approval_has_due_at_and_notifies_delegate(
    client, admin_csrf, workflow_id, doc_worker, fake_http, db, app, fake_clock
):
    """Regression (backend-approvals-jobs 감사 #2): `document.publish` 승인은
    `Approval`을 손으로 만드는 유일한 경로였다 — `due_at`(SLA)이 계속 NULL로 남아
    이 요청 유형만 절대 '기한 초과'로 표시되지 않았고, `notify_admins`만 불러 활성
    `ApprovalDelegation`을 받은 비관리자가 결재할 수 있는데도 알림을 받지 못했다(X7과
    같은 결함).
    """
    from datetime import timedelta

    from app.approvals import delegation as delegation_service
    from app.approvals.models import DEFAULT_SLA_HOURS, Approval
    from app.notifications.models import Notification
    from app.users.service import create_user, get_user_by_email

    delegate = create_user(
        db, email="doc-delegate@goodmit.co.kr", display_name="위임받은 운영자",
        password="Str0ng-Passw0rd!", settings=app.state.settings, actor_role="system_admin",
        role="operator", must_change_password=False,
    )
    db.commit()
    delegator = get_user_by_email(db, "admin@goodmit.co.kr")  # admin_csrf fixture's user
    now = fake_clock.now()
    delegation_service.create(
        db, delegator=delegator, delegate=delegate,
        starts_at=now, ends_at=now + timedelta(days=1),
        reason="휴가 대비", created_by=delegator.id, now=now,
    )
    db.commit()

    fake_http.on(
        DOC_URL,
        json_body={"title": "승인용 보고서", "body": "본문 내용 충분히 깁니다 " * 3,
                   "source_row_count": 3},
    )
    r = _generate(client, admin_csrf, workflow_id, "preview_then_approve")
    assert r.status_code == 202
    doc_worker.run_once()

    approval = db.query(Approval).filter(Approval.request_type == "document.publish").one()
    assert approval.due_at is not None
    assert approval.due_at == approval.requested_at + timedelta(hours=DEFAULT_SLA_HOURS)

    delegate_notes = (
        db.query(Notification)
        .filter(Notification.user_id == delegate.id, Notification.type == "approval_requested")
        .all()
    )
    assert delegate_notes, "위임받은 비관리자가 document.publish 승인 알림을 받아야 한다 (X7)"


def test_document_generation_rbac(client, login_as, workflow_id):
    csrf = login_as("operator")
    r = client.post(
        "/api/admin/documents/generate",
        json={"workflow_id": workflow_id, "mode": "preview_only", "period": "x", "config": {}},
        headers=_headers(csrf),
    )
    assert r.status_code == 403
