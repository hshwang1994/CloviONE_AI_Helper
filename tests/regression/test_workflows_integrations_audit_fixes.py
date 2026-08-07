"""Regression tests for the backend-workflows-integrations audit findings.

Each test reproduces the defect statement itself (not just the fixed code path),
matching the convention in test_review3_fixes.py / test_review4_fixes.py.

Findings covered (see the audit report for file/line detail):
  1. N8nWorkflowProvider.invoke() silently dropped payload for http_method=GET.
  2. IntegrationConfig.capabilities: null on PATCH was not normalized (unlike
     the identical workflows.tags case), so "clear capabilities" 500/422'd.
  3. schedule_run / document_generate did not classify invoke() failures into
     transient (retry) vs permanent (fail fast), unlike notion_mapping_sync.
  5. Integration health check graded a 3xx redirect response as "up" even
     though OutboundClient never follows redirects.
  6. Workflow/Integration name-uniqueness was a plain SELECT pre-check, not
     race-safe against a concurrent insert (IntegrityError could leak as 500).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

pytestmark = pytest.mark.regression


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


# --------------------------------------------------------------------------- #
# 1. provider_n8n.invoke(): GET + non-empty payload
# --------------------------------------------------------------------------- #
def test_get_workflow_with_payload_fails_fast_instead_of_silently_dropping_it(
    db, app, login_as, client
):
    from app.core.errors import ValidationAppError
    from app.workflows.provider_n8n import N8nWorkflowProvider
    from app.workflows.service import get_workflow_or_404

    csrf = login_as("system_admin", email="audit-get-payload@goodmit.co.kr")
    wf = client.post(
        "/api/admin/workflows",
        json={
            "name": "audit GET workflow",
            "webhook_url": "http://127.0.0.1:5678/webhook/audit-get",
            "http_method": "GET",
            "operation_mode": "read",
        },
        headers=_headers(csrf),
    ).json()["workflow"]

    row = get_workflow_or_404(db, wf["id"])
    db.refresh(row)
    provider = N8nWorkflowProvider(app.state.outbound_client)
    # Before the fix: OutboundClient.request() sends json=None for a GET, so this
    # payload was silently discarded and n8n received an empty GET that looked
    # like a legitimate (if empty) response instead of a configuration error.
    with pytest.raises(ValidationAppError):
        provider.invoke(row, {"action": "lookup_user", "email": "x@example.com"}, timeout=5.0)


def test_get_workflow_with_empty_payload_is_unaffected(db, app, login_as, client, fake_http):
    from app.workflows.provider_n8n import N8nWorkflowProvider
    from app.workflows.service import get_workflow_or_404

    csrf = login_as("system_admin", email="audit-get-empty@goodmit.co.kr")
    url = "http://127.0.0.1:5678/webhook/audit-get-empty"
    wf = client.post(
        "/api/admin/workflows",
        json={
            "name": "audit GET workflow (no payload)",
            "webhook_url": url,
            "http_method": "GET",
            "operation_mode": "read",
        },
        headers=_headers(csrf),
    ).json()["workflow"]
    fake_http.on(url, json_body={"ok": True})

    row = get_workflow_or_404(db, wf["id"])
    db.refresh(row)
    provider = N8nWorkflowProvider(app.state.outbound_client)
    # A genuinely payload-less GET (the reachability-only shape) must still work.
    result = provider.invoke(row, {}, timeout=5.0)
    assert result == {"ok": True}
    assert fake_http.requests[0].method == "GET"


# --------------------------------------------------------------------------- #
# 2. integrations PATCH capabilities:null
# --------------------------------------------------------------------------- #
def test_clearing_integration_capabilities_does_not_break_like_workflow_tags(
    client, login_as
):
    csrf = login_as("system_admin", email="audit-caps@goodmit.co.kr")
    created = client.post(
        "/api/admin/integrations",
        json={
            "name": "audit-capabilities",
            "provider_type": "http_service",
            "base_url": "http://127.0.0.1:8787",
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


# --------------------------------------------------------------------------- #
# 3. schedule_run / document_generate: transient vs permanent invoke() failure
# --------------------------------------------------------------------------- #
def test_schedule_run_deterministic_failure_fails_on_first_attempt(
    client, login_as, app, settings, fake_clock, fake_http, db
):
    from app.jobs.handlers.schedule_run import handle_schedule_run
    from app.jobs.models import Job
    from app.jobs.worker import Worker, WorkerContext

    csrf = login_as("system_admin", email="audit-sched-fail@goodmit.co.kr")
    url = "http://127.0.0.1:5678/webhook/audit-sched-fail"
    workflow_id = client.post(
        "/api/admin/workflows",
        json={"name": "audit 스케줄 결정적 오류", "webhook_url": url, "operation_mode": "read"},
        headers=_headers(csrf),
    ).json()["workflow"]["id"]
    schedule = client.post(
        "/api/admin/schedules",
        json={
            "name": "audit 스케줄 결정적 오류",
            "schedule_type": "cron",
            "cron_expression": "0 * * * *",
            "timezone": "UTC",
            "target_type": "workflow",
            "target_ref": workflow_id,
            "payload_template": {"scope": "all"},
        },
        headers=_headers(csrf),
    ).json()["schedule"]
    client.post(f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(csrf))

    # 404 -> httpx.HTTPStatusError: deterministic (bad webhook path), not transient.
    fake_http.on(url, status=404)
    client.post(
        f"/api/admin/schedules/{schedule['id']}/run-now", json={}, headers=_headers(csrf)
    )

    ctx = WorkerContext(
        settings=settings, clock=fake_clock, outbound_client=app.state.outbound_client
    )
    worker = Worker(
        app.state.session_factory, fake_clock, {"schedule_run": handle_schedule_run}, ctx
    )
    assert worker.run_once() is True

    runs = client.get(
        f"/api/admin/schedules/{schedule['id']}/runs", headers=_headers(csrf)
    ).json()["items"]
    assert runs[0]["status"] == "failed"

    job = (
        db.query(Job)
        .filter(Job.job_type == "schedule_run")
        .order_by(Job.created_at.desc())
        .first()
    )
    db.refresh(job)
    # Before the fix: a deterministic 404 was treated as a retryable failure by
    # worker.py's default path and would still be "queued" after one attempt
    # (max_attempts defaults to 3) instead of failing fast.
    assert job.status == "failed"
    assert job.attempt_count == 1, (
        "결정적 404 오류가 여전히 재시도 대상으로 분류되어 첫 시도만에 실패로 확정되지 않았다"
    )


def test_schedule_run_transient_failure_still_retries(
    client, login_as, app, settings, fake_clock, fake_http, db
):
    """Sanity check: the classification must not turn timeouts into permanent
    failures — only genuinely deterministic errors fail fast."""
    from app.jobs.handlers.schedule_run import handle_schedule_run
    from app.jobs.models import Job
    from app.jobs.worker import Worker, WorkerContext

    csrf = login_as("system_admin", email="audit-sched-transient@goodmit.co.kr")
    url = "http://127.0.0.1:5678/webhook/audit-sched-transient"
    workflow_id = client.post(
        "/api/admin/workflows",
        json={"name": "audit 스케줄 일시 오류", "webhook_url": url, "operation_mode": "read"},
        headers=_headers(csrf),
    ).json()["workflow"]["id"]
    schedule = client.post(
        "/api/admin/schedules",
        json={
            "name": "audit 스케줄 일시 오류",
            "schedule_type": "cron",
            "cron_expression": "0 * * * *",
            "timezone": "UTC",
            "target_type": "workflow",
            "target_ref": workflow_id,
            "payload_template": {"scope": "all"},
        },
        headers=_headers(csrf),
    ).json()["schedule"]
    client.post(f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(csrf))

    fake_http.on_timeout(url)
    client.post(
        f"/api/admin/schedules/{schedule['id']}/run-now", json={}, headers=_headers(csrf)
    )

    ctx = WorkerContext(
        settings=settings, clock=fake_clock, outbound_client=app.state.outbound_client
    )
    worker = Worker(
        app.state.session_factory, fake_clock, {"schedule_run": handle_schedule_run}, ctx
    )
    assert worker.run_once() is True

    job = (
        db.query(Job)
        .filter(Job.job_type == "schedule_run")
        .order_by(Job.created_at.desc())
        .first()
    )
    db.refresh(job)
    assert job.status == "queued", "타임아웃(일시적 오류)이 재시도 대상에서 빠졌다"
    assert job.attempt_count == 1


def test_document_generate_deterministic_response_failure_fails_on_first_attempt(
    client, login_as, app, settings, fake_clock, fake_http, db
):
    from app.jobs.handlers.document_generate import handle_document_generate
    from app.jobs.models import Job
    from app.jobs.worker import Worker, WorkerContext

    csrf = login_as("admin", email="audit-doc-fail@goodmit.co.kr")
    url = "http://127.0.0.1:5678/webhook/audit-doc-fail"
    workflow_id = client.post(
        "/api/admin/workflows",
        json={"name": "audit 문서 결정적 오류", "webhook_url": url, "operation_mode": "write"},
        headers=_headers(csrf),
    ).json()["workflow"]["id"]

    # n8n returns a non-JSON body: deterministic malformed response, not transient.
    fake_http.on_invalid_json(url)
    client.post(
        "/api/admin/documents/generate",
        json={
            "workflow_id": workflow_id,
            "mode": "preview_only",
            "period": "2026-W41",
            "config": {"target_parent_page": "audit-page", "template_version": 1},
        },
        headers=_headers(csrf),
    )

    ctx = WorkerContext(
        settings=settings, clock=fake_clock, outbound_client=app.state.outbound_client
    )
    worker = Worker(
        app.state.session_factory, fake_clock,
        {"document_generate": handle_document_generate}, ctx,
    )
    assert worker.run_once() is True

    job = (
        db.query(Job)
        .filter(Job.job_type == "document_generate")
        .order_by(Job.created_at.desc())
        .first()
    )
    db.refresh(job)
    assert job.status == "failed"
    assert job.attempt_count == 1, (
        "n8n의 비-JSON 응답(확정적 오류)이 재시도 대상으로 분류되어 첫 시도만에 "
        "실패로 확정되지 않았다"
    )


# --------------------------------------------------------------------------- #
# 5. integration health check: 3xx must not be "up"
# --------------------------------------------------------------------------- #
def test_health_check_redirect_is_not_reported_as_healthy(client, login_as, fake_http):
    csrf = login_as("system_admin", email="audit-health-redirect@goodmit.co.kr")
    created = client.post(
        "/api/admin/integrations",
        json={
            "name": "audit-redirect-service",
            "provider_type": "http_service",
            "base_url": "http://127.0.0.1:8787",
            "auth_type": "none",
        },
        headers=_headers(csrf),
    ).json()["integration"]

    # OutboundClient is built with follow_redirects=False (SSRF safety) — this 302
    # IS the response actually received, not a stand-in for the redirect target.
    fake_http.on("http://127.0.0.1:8787", status=302)
    r = client.post(
        f"/api/admin/integrations/{created['id']}/health", headers=_headers(csrf)
    )
    assert r.status_code == 200
    assert r.json()["status"] == "down", "3xx 리다이렉트 응답이 여전히 up으로 보고된다"
    assert r.json()["detail"] == "HTTP 302"


# --------------------------------------------------------------------------- #
# 6. name-uniqueness race: concurrent creates must yield ConflictError, never
#    an unhandled IntegrityError/500. Real concurrency (separate engine/session
#    per thread against the same db file), matching this repo's own convention
#    in tests/integration/test_job_claim_race.py.
# --------------------------------------------------------------------------- #
def test_concurrent_workflow_creates_with_same_name_never_leak_a_500(db_path, settings):
    from app.core.allowlist import AllowlistRegistry
    from app.core.db import make_engine, make_session_factory
    from app.core.errors import ConflictError
    from app.workflows import service as workflows_service
    from app.workflows.schemas import WorkflowConfig

    url = f"sqlite:///{db_path.as_posix()}"
    allowlists = AllowlistRegistry(settings.config_dir)

    # Prime the file into WAL mode via a single connection first — mirrors
    # test_job_claim_race.py's seed_engine. Without this, several threads racing
    # to flip a fresh (non-WAL) file into WAL mode at once can trip a spurious
    # "database is locked" on the PRAGMA itself, before busy_timeout is even set
    # — a SQLite setup artifact, not the race this test is actually about.
    warm_engine = make_engine(url)
    with warm_engine.connect():
        pass
    warm_engine.dispose()

    def attempt(_i: int) -> str:
        engine = make_engine(url)
        factory = make_session_factory(engine)
        try:
            with factory() as db:
                config = WorkflowConfig(
                    name="race-workflow",
                    webhook_url="http://127.0.0.1:5678/webhook/race",
                )
                try:
                    workflows_service.create_workflow(
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


def test_concurrent_integration_creates_with_same_name_never_leak_a_500(db_path, settings):
    from app.core.allowlist import AllowlistRegistry
    from app.core.db import make_engine, make_session_factory
    from app.core.errors import ConflictError
    from app.integrations import service as integrations_service
    from app.integrations.schemas import IntegrationConfig

    url = f"sqlite:///{db_path.as_posix()}"
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
                    base_url="http://127.0.0.1:8787",
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
