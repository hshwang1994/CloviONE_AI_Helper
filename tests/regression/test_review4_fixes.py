"""Regression tests pinned to the iteration-4 review findings.

각 테스트는 고쳐진 코드 경로가 아니라 결함 진술 그 자체를 재현한다.
"""

import json

import pytest

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.regression


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


# --- 1 & 5. retry_run: 실행 게이트와 소요시간 ---------------------------------

SCHED_URL = "http://127.0.0.1:5678/webhook/r4-sched"


@pytest.fixture()
def sched_workflow_id(client, login_as):
    csrf = login_as("system_admin", email="r4-sched-owner@goodmit.co.kr")
    return client.post(
        "/api/admin/workflows",
        json={
            "name": "r4 스케줄 워크플로",
            "webhook_url": SCHED_URL,
            "operation_mode": "read",
        },
        headers=_headers(csrf),
    ).json()["workflow"]["id"]


@pytest.fixture()
def sched_worker(app, settings, fake_clock):
    from app.jobs.handlers.schedule_run import handle_schedule_run
    from app.jobs.worker import Worker, WorkerContext

    ctx = WorkerContext(
        settings=settings, clock=fake_clock, outbound_client=app.state.outbound_client
    )
    return Worker(
        app.state.session_factory, fake_clock, {"schedule_run": handle_schedule_run}, ctx
    )


def _make_schedule(client, csrf, workflow_id, name, **overrides):
    return client.post(
        "/api/admin/schedules",
        json={
            "name": name,
            "schedule_type": "cron",
            "cron_expression": "0 * * * *",
            "timezone": "UTC",
            "target_type": "workflow",
            "target_ref": workflow_id,
            "payload_template": {"scope": "all"},
            **overrides,
        },
        headers=_headers(csrf),
    ).json()["schedule"]


def _failed_run(client, csrf, schedule, worker, fake_clock, fake_http):
    """실행 게이트를 통과한 스케줄을 한 번 돌려 실패한 run을 만든다."""
    fake_http.on(SCHED_URL, status=500)
    run_id = client.post(
        f"/api/admin/schedules/{schedule['id']}/run-now", json={}, headers=_headers(csrf)
    ).json()["run"]["id"]
    for _ in range(4):
        worker.run_once()
        fake_clock.advance(120)
    runs = client.get(
        f"/api/admin/schedules/{schedule['id']}/runs", headers=_headers(csrf)
    ).json()["items"]
    assert runs[0]["status"] == "failed"
    return run_id


def test_operator_cannot_retry_a_run_of_a_disabled_schedule(
    client, login_as, sched_workflow_id, sched_worker, fake_clock, fake_http, db
):
    """High: retry_run이 run-now의 승인 게이트를 통째로 우회하던 결함.

    운영자가 비활성(=승인받지 않은) 정의를 재시도로 그대로 실행할 수 있었다.
    """
    sys_csrf = login_as("system_admin", email="r4-retry-gate@goodmit.co.kr")
    schedule = _make_schedule(client, sys_csrf, sched_workflow_id, "재시도 게이트")
    client.post(
        f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(sys_csrf)
    )
    run_id = _failed_run(client, sys_csrf, schedule, sched_worker, fake_clock, fake_http)

    # 스케줄이 비활성으로 내려간다 — 이 정의는 더 이상 승인된 상태가 아니다.
    client.post(
        f"/api/admin/schedules/{schedule['id']}/disable", headers=_headers(sys_csrf)
    )

    operator_csrf = login_as("operator", email="r4-operator@goodmit.co.kr")
    from app.jobs.models import Job

    jobs_before = db.query(Job).count()

    r = client.post(
        f"/api/admin/schedules/runs/{run_id}/retry", headers=_headers(operator_csrf)
    )
    assert r.status_code == 409

    db.expire_all()
    assert db.query(Job).count() == jobs_before  # 재시도 job이 큐에 들어가지 않았다.
    runs = client.get(
        f"/api/admin/schedules/{schedule['id']}/runs", headers=_headers(operator_csrf)
    ).json()["items"]
    assert runs[0]["status"] == "failed"  # 실패한 채로 남는다 (queued로 되살아나지 않음).


def test_retry_cannot_run_a_definition_that_lost_its_approval(
    client, login_as, sched_workflow_id, sched_worker, fake_clock, fake_http, db
):
    """High: 승인 후 PUT으로 정의를 갈아끼우면 enabled가 내려가는데(이전 라운드 수정),
    retry는 그 게이트를 보지 않아 승인받은 적 없는 정의로 실행할 수 있었다."""
    admin_csrf = login_as("admin", email="r4-retry-put@goodmit.co.kr")
    schedule = _make_schedule(client, admin_csrf, sched_workflow_id, "정의 교체 재시도")

    # 승인 없이 활성화된 상태를 만들기 위해 system_admin이 활성화해 준다.
    sys_csrf = login_as("system_admin", email="r4-retry-put-sys@goodmit.co.kr")
    client.post(
        f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(sys_csrf)
    )
    run_id = _failed_run(client, sys_csrf, schedule, sched_worker, fake_clock, fake_http)

    # 요청자(admin)가 정의를 바꾸면 승인 게이트가 활성 상태를 내린다.
    admin_csrf = login_as("admin", email="r4-retry-put@goodmit.co.kr")
    put = client.put(
        f"/api/admin/schedules/{schedule['id']}",
        json={
            "name": "정의 교체 재시도",
            "schedule_type": "cron",
            "cron_expression": "* * * * *",
            "timezone": "UTC",
            "target_type": "workflow",
            "target_ref": sched_workflow_id,
            "payload_template": {"scope": "everything", "delete": True},
        },
        headers=_headers(admin_csrf),
    )
    assert put.status_code == 200
    assert put.json()["schedule"]["enabled"] is False

    r = client.post(
        f"/api/admin/schedules/runs/{run_id}/retry", headers=_headers(admin_csrf)
    )
    assert r.status_code == 409


def test_retry_resets_the_duration_of_the_previous_failed_attempt(
    client, login_as, sched_workflow_id, sched_worker, fake_clock, fake_http
):
    """Low: 재시도가 started_at을 초기화하지 않아 소요시간에 이전 실패 시도가
    포함돼 표시되던 결함."""
    sys_csrf = login_as("system_admin", email="r4-duration@goodmit.co.kr")
    schedule = _make_schedule(client, sys_csrf, sched_workflow_id, "소요시간")
    client.post(
        f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(sys_csrf)
    )
    run_id = _failed_run(client, sys_csrf, schedule, sched_worker, fake_clock, fake_http)

    runs = client.get(
        f"/api/admin/schedules/{schedule['id']}/runs", headers=_headers(sys_csrf)
    ).json()["items"]
    first_started_at = runs[0]["started_at"]
    assert first_started_at is not None

    # 한참 뒤에 재시도한다 (세션 유휴 만료 시간을 넘기므로 다시 로그인한다).
    fake_clock.advance(3600)
    sys_csrf = login_as("system_admin", email="r4-duration@goodmit.co.kr")
    r = client.post(
        f"/api/admin/schedules/runs/{run_id}/retry", headers=_headers(sys_csrf)
    )
    assert r.status_code == 200
    # 아직 시작하지 않은 실행 — 이전 시도의 시작 시각을 물려받지 않는다.
    assert r.json()["run"]["started_at"] is None

    fake_http.on(SCHED_URL, json_body={"ok": True})
    sched_worker.run_once()

    runs = client.get(
        f"/api/admin/schedules/{schedule['id']}/runs", headers=_headers(sys_csrf)
    ).json()["items"]
    assert runs[0]["status"] == "succeeded"
    # 소요시간은 이번 시도만 센다 — 1시간 전 실패 시도부터 재지 않는다.
    assert runs[0]["started_at"] > first_started_at


# --- 2. 발행 승인은 '승인자가 본 그 문서'를 발행한다 --------------------------

DOC_URL = "http://127.0.0.1:5678/webhook/r4-doc"
APPROVED_TITLE = "승인자가 검토한 주간 보고서"
APPROVED_BODY = "승인자가 읽은 본문입니다. 내용이 충분히 깁니다. " * 2
RERENDER_TITLE = "승인 뒤 몰래 바뀐 보고서"


@pytest.fixture()
def doc_worker(app, settings, fake_clock):
    from app.jobs.handlers.document_generate import handle_document_generate
    from app.jobs.worker import Worker, WorkerContext

    ctx = WorkerContext(
        settings=settings, clock=fake_clock, outbound_client=app.state.outbound_client
    )
    return Worker(
        app.state.session_factory, fake_clock,
        {"document_generate": handle_document_generate}, ctx,
    )


@pytest.fixture()
def doc_workflow_id(client, login_as):
    csrf = login_as("admin", email="r4-doc-requester@goodmit.co.kr")
    return client.post(
        "/api/admin/workflows",
        json={
            "name": "r4 문서 워크플로",
            "webhook_url": DOC_URL,
            "operation_mode": "write",
            "approval_required": True,
        },
        headers=_headers(csrf),
    ).json()["workflow"]["id"]


def _awaiting_approval_doc(client, csrf, workflow_id, doc_worker, fake_http, period):
    """미리보기까지 끝내 '승인자가 본 내용'이 확정된 문서를 만든다."""
    fake_http.on(
        DOC_URL,
        json_body={
            "title": APPROVED_TITLE,
            "body": APPROVED_BODY,
            "source_row_count": 7,
        },
    )
    gen_id = client.post(
        "/api/admin/documents/generate",
        json={
            "workflow_id": workflow_id,
            "mode": "preview_then_approve",
            "period": period,
            "config": {"target_parent_page": "r4-page", "template_version": 1},
        },
        headers=_headers(csrf),
    ).json()["generation"]["id"]
    doc_worker.run_once()
    detail = client.get(f"/api/admin/documents/{gen_id}").json()["generation"]
    assert detail["status"] == "awaiting_approval"
    assert detail["preview"]["title"] == APPROVED_TITLE
    return gen_id


def _approve_as_other_admin(app, db, approval_id, email):
    from fastapi.testclient import TestClient

    from app.users.service import create_user

    create_user(
        db, email=email, display_name="승인자", password=DEFAULT_TEST_PASSWORD,
        settings=app.state.settings, role="admin", must_change_password=False,
    )
    db.commit()
    with TestClient(app, raise_server_exceptions=False) as approver:
        csrf = approver.post(
            "/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD}
        ).json()["csrf_token"]
        return approver.post(
            f"/api/admin/approvals/{approval_id}/approve", headers=_headers(csrf)
        )


def _publish_approval_id(db, gen_id):
    from app.approvals.models import Approval

    return (
        db.query(Approval)
        .filter(Approval.request_type == "document.publish", Approval.object_id == gen_id)
        .one()
        .id
    )


def test_publish_sends_the_approved_document_not_a_fresh_render(
    app, client, login_as, doc_workflow_id, doc_worker, fake_http, db
):
    """High: 승인 시점에 문서를 새로 렌더해 발행하던 결함.

    승인자가 검토한 내용과 실제 발행물이 달라질 수 있었다.
    """
    csrf = login_as("admin", email="r4-doc-requester@goodmit.co.kr")
    gen_id = _awaiting_approval_doc(
        client, csrf, doc_workflow_id, doc_worker, fake_http, "2026-W41"
    )

    # 승인 뒤 소스가 바뀌어 재렌더하면 다른 문서가 나오는 상황.
    fake_http.on(
        DOC_URL,
        json_body={
            "title": RERENDER_TITLE,
            "body": "승인자가 본 적 없는 본문입니다. " * 3,
            "source_row_count": 99,
            "published_ref": "https://www.notion.so/r4-published",
        },
    )
    approval_id = _publish_approval_id(db, gen_id)
    assert (
        _approve_as_other_admin(
            app, db, approval_id, "r4-doc-approver@goodmit.co.kr"
        ).status_code
        == 200
    )
    doc_worker.run_once()

    # 발행은 딱 한 번, 재렌더(preview 재호출) 없이 이뤄진다.
    actions = [json.loads(r.content)["action"] for r in fake_http.requests]
    assert actions == ["preview", "publish"]

    published = json.loads(fake_http.requests[-1].content)
    # 워크플로에 실려 나간 것은 '승인자가 본 그 문서'다.
    assert published["content"]["title"] == APPROVED_TITLE
    assert published["content"]["body"] == APPROVED_BODY
    assert RERENDER_TITLE not in fake_http.requests[-1].content.decode()

    detail = client.get(f"/api/admin/documents/{gen_id}").json()["generation"]
    assert detail["status"] == "published"
    assert detail["published_ref"] == "https://www.notion.so/r4-published"
    # 승인된 미리보기가 재렌더 결과로 덮이지 않는다.
    assert detail["preview"]["title"] == APPROVED_TITLE


def test_approved_publish_is_not_silently_dropped_by_a_rerender_quality_gate(
    app, client, login_as, doc_workflow_id, doc_worker, fake_http, db
):
    """High(침묵 실패): 재렌더가 품질 게이트에 걸리면 승인은 완료인데 발행만 조용히
    사라지던 결함 — 승인자도 요청자도 알 수 없었다."""
    csrf = login_as("admin", email="r4-doc-requester@goodmit.co.kr")
    gen_id = _awaiting_approval_doc(
        client, csrf, doc_workflow_id, doc_worker, fake_http, "2026-W42"
    )

    # 재렌더했다면 품질 게이트에 걸렸을 응답(빈 제목·빈 소스).
    fake_http.on(
        DOC_URL,
        json_body={
            "title": "",
            "body": "짧",
            "source_row_count": 0,
            "published_ref": "https://www.notion.so/r4-quality",
        },
    )
    _approve_as_other_admin(
        app, db, _publish_approval_id(db, gen_id), "r4-quality-approver@goodmit.co.kr"
    )
    doc_worker.run_once()

    detail = client.get(f"/api/admin/documents/{gen_id}").json()["generation"]
    # 이미 게이트를 통과해 승인된 내용이 그대로 발행된다.
    assert detail["status"] == "published"
    assert detail["quality_problems"] is None
    assert json.loads(fake_http.requests[-1].content)["content"]["title"] == APPROVED_TITLE


def test_failed_publish_is_reported_not_silent(
    app, client, login_as, doc_workflow_id, doc_worker, fake_http, db
):
    """발행이 실패하면 문서 상태와 요청자 알림으로 드러나야 한다 (조용한 중단 금지)."""
    csrf = login_as("admin", email="r4-doc-requester@goodmit.co.kr")
    gen_id = _awaiting_approval_doc(
        client, csrf, doc_workflow_id, doc_worker, fake_http, "2026-W43"
    )

    # 발행 응답에 published_ref가 없다 — 발행됐다는 증거가 없다 (spec §19.5).
    fake_http.on(DOC_URL, json_body={"title": APPROVED_TITLE})
    _approve_as_other_admin(
        app, db, _publish_approval_id(db, gen_id), "r4-fail-approver@goodmit.co.kr"
    )
    doc_worker.run_once()

    detail = client.get(f"/api/admin/documents/{gen_id}").json()["generation"]
    assert detail["status"] == "failed"
    assert detail["published_ref"] is None
    assert "published_ref" in detail["error_message"]

    from app.notifications.models import Notification
    from app.users.service import get_user_by_email

    requester = get_user_by_email(db, "r4-doc-requester@goodmit.co.kr")
    notifications = (
        db.query(Notification).filter(Notification.user_id == requester.id).all()
    )
    assert [n for n in notifications if n.type == "job_failed"]


# --- 3. 승인된 발행 job을 취소해도 문서가 고착되지 않는다 ---------------------


def test_cancelling_an_approved_publish_job_terminalizes_the_document(
    app, client, login_as, doc_workflow_id, doc_worker, fake_http, db
):
    """Medium: 승인된 발행 job을 취소하면 문서가 awaiting_approval로 영구 고착돼
    어느 화면에서도 되살릴 수 없던 결함."""
    csrf = login_as("admin", email="r4-doc-requester@goodmit.co.kr")
    gen_id = _awaiting_approval_doc(
        client, csrf, doc_workflow_id, doc_worker, fake_http, "2026-W44"
    )
    _approve_as_other_admin(
        app, db, _publish_approval_id(db, gen_id), "r4-cancel-approver@goodmit.co.kr"
    )

    from app.jobs.models import Job

    db.expire_all()
    publish_job = (
        db.query(Job).filter(Job.idempotency_key == f"docpublish:{gen_id}").one()
    )
    assert publish_job.status == "queued"

    operator_csrf = login_as("operator", email="r4-cancel-operator@goodmit.co.kr")
    r = client.post(
        f"/api/admin/jobs/{publish_job.id}/cancel", headers=_headers(operator_csrf)
    )
    assert r.status_code == 200

    detail = client.get(f"/api/admin/documents/{gen_id}").json()["generation"]
    assert detail["status"] != "awaiting_approval"
    assert detail["status"] == "failed"
    assert detail["error_message"] == "job cancelled by operator"


# --- 4. 만료 판정은 목록과 상세가 같아야 한다 --------------------------------


def test_expired_approval_reads_the_same_in_the_list_and_the_detail(
    client, login_as, sched_workflow_id, fake_clock
):
    """Low: 같은 승인이 목록에서는 expired, 상세에서는 pending으로 보이던 결함."""
    csrf = login_as("admin", email="r4-expiry@goodmit.co.kr")
    schedule = _make_schedule(client, csrf, sched_workflow_id, "만료 표시")
    approval = client.post(
        f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(csrf)
    ).json()["approval"]

    from app.approvals.models import DEFAULT_EXPIRY_HOURS

    fake_clock.advance(DEFAULT_EXPIRY_HOURS * 3600 + 1)
    csrf = login_as("admin", email="r4-expiry@goodmit.co.kr")  # 세션 유휴 만료 → 재로그인

    listed = client.get("/api/admin/approvals", headers=_headers(csrf)).json()["items"]
    listed_row = [row for row in listed if row["id"] == approval["id"]][0]
    detail = client.get(
        f"/api/admin/approvals/{approval['id']}", headers=_headers(csrf)
    ).json()["approval"]

    assert listed_row["status"] == "expired"
    assert detail["status"] == listed_row["status"]


def test_pending_approval_still_reads_as_pending_in_the_detail(
    client, login_as, sched_workflow_id
):
    """만료 전에는 그대로 pending — 만료 판정이 과하게 적용되지 않는다."""
    csrf = login_as("admin", email="r4-pending@goodmit.co.kr")
    schedule = _make_schedule(client, csrf, sched_workflow_id, "대기 표시")
    approval = client.post(
        f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(csrf)
    ).json()["approval"]

    detail = client.get(
        f"/api/admin/approvals/{approval['id']}", headers=_headers(csrf)
    ).json()["approval"]
    assert detail["status"] == "pending"
