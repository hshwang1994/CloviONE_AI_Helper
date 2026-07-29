"""Regression tests pinned to the iteration-3 review findings.

Each test reproduces the concrete defect statement, not just the fixed code path.
"""

import json

import pytest

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.regression

SECRET_TEXT = "사장님께만 보고할 3분기 구조조정 대상자 명단입니다"
MSG_ID = "r3abcdef0123456789abcdef01234567"


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


def _post_private_message(client, login_as, *, email, content=SECRET_TEXT, msg_id=MSG_ID):
    """Have a regular user say something private, and return their conversation id."""
    csrf = login_as("user", email=email)
    conv = client.post(
        "/api/conversations", json={}, headers=_headers(csrf)
    ).json()["conversation"]
    r = client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={"content": content, "client_message_id": msg_id},
        headers=_headers(csrf),
    )
    assert r.status_code == 202, r.text
    return conv["id"]


# --- 1. Job queue must not expose other people's chat content ---------------


def test_operator_cannot_read_other_users_chat_body_through_job_queue(
    client, login_as
):
    """High: 큐 조회가 타인의 채팅 원문/첨부/요청자 이메일을 노출하면 안 된다.

    같은 내용을 대화 API로 읽으면 403인데 큐 화면이 우회로가 되던 결함.
    """
    _post_private_message(client, login_as, email="private-writer@goodmit.co.kr")

    operator_csrf = login_as("operator", email="nosy-operator@goodmit.co.kr")
    listing = client.get("/api/admin/jobs", headers=_headers(operator_csrf))
    assert listing.status_code == 200
    body = listing.text
    assert SECRET_TEXT not in body
    assert "private-writer@goodmit.co.kr" not in body

    job = listing.json()["items"][0]
    assert "payload" not in job
    # 운영에 필요한 메타데이터는 그대로 남는다.
    assert job["job_type"] == "chat_message"
    assert job["status"] == "queued"
    assert job["attempt_count"] == 0
    assert "duration_ms" in job

    detail = client.get(
        f"/api/admin/jobs/{job['id']}", headers=_headers(operator_csrf)
    )
    assert detail.status_code == 200
    assert SECRET_TEXT not in detail.text
    assert "payload" not in detail.json()["job"]


def test_job_queue_does_not_leak_attachment_bytes(client, login_as):
    """High: 첨부 이미지 base64가 큐 응답에 실려 나가면 안 된다."""
    import base64

    # 1x1 PNG.
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
        "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    )
    data = base64.b64encode(png).decode()
    csrf = login_as("user", email="uploader@goodmit.co.kr")
    conv = client.post(
        "/api/conversations", json={}, headers=_headers(csrf)
    ).json()["conversation"]
    r = client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={
            "content": "이 이미지 봐줘",
            "client_message_id": "r3img0123456789abcdef0123456789a",
            "attachments": [
                {"filename": "shot.png", "media_type": "image/png", "data": data}
            ],
        },
        headers=_headers(csrf),
    )
    assert r.status_code == 202, r.text

    operator_csrf = login_as("operator", email="attach-operator@goodmit.co.kr")
    listing = client.get("/api/admin/jobs", headers=_headers(operator_csrf))
    assert data not in listing.text


# --- 2. run_now must respect the enable (approval) gate ---------------------


@pytest.fixture()
def sched_workflow_id(client, login_as):
    csrf = login_as("system_admin", email="r3-sched-owner@goodmit.co.kr")
    return client.post(
        "/api/admin/workflows",
        json={
            "name": "r3 쓰기 워크플로",
            "webhook_url": "http://127.0.0.1:5678/webhook/r3-write",
            "operation_mode": "write",
        },
        headers=_headers(csrf),
    ).json()["workflow"]["id"]


def _make_schedule(client, csrf, workflow_id, name):
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
        },
        headers=_headers(csrf),
    ).json()["schedule"]


def test_run_now_refuses_schedule_that_never_passed_the_enable_gate(
    client, login_as, sched_workflow_id, db
):
    """High: 승인 게이트를 통과하지 않은 비활성 스케줄을 run_now로 즉시 실행하던 결함."""
    admin_csrf = login_as("admin", email="r3-runner@goodmit.co.kr")
    schedule = _make_schedule(client, admin_csrf, sched_workflow_id, "게이트 미통과")
    assert schedule["enabled"] is False

    # 활성화 요청은 승인 대기로만 남는다.
    assert (
        client.post(
            f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(admin_csrf)
        ).status_code
        == 202
    )

    r = client.post(
        f"/api/admin/schedules/{schedule['id']}/run-now",
        json={},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 409

    from app.schedules.models import ScheduleRun

    assert db.query(ScheduleRun).count() == 0


def test_run_now_dry_run_still_allowed_while_disabled(
    client, login_as, sched_workflow_id
):
    """dry_run은 실행이 아니라 미리보기 — 게이트 대상이 아니다."""
    admin_csrf = login_as("admin", email="r3-dry@goodmit.co.kr")
    schedule = _make_schedule(client, admin_csrf, sched_workflow_id, "드라이런")
    r = client.post(
        f"/api/admin/schedules/{schedule['id']}/run-now",
        json={"dry_run": True},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200
    assert r.json()["payload_preview"] == {"scope": "all"}


def test_run_now_allowed_once_enabled(client, login_as, sched_workflow_id):
    sys_csrf = login_as("system_admin", email="r3-enabler@goodmit.co.kr")
    schedule = _make_schedule(client, sys_csrf, sched_workflow_id, "활성 후 실행")
    client.post(
        f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(sys_csrf)
    )
    r = client.post(
        f"/api/admin/schedules/{schedule['id']}/run-now",
        json={},
        headers=_headers(sys_csrf),
    )
    assert r.status_code == 200
    assert r.json()["run"]["status"] == "queued"


# --- 3. Publish approval policy is server-enforced, not requester-chosen ----


DOC_URL = "http://127.0.0.1:5678/webhook/r3-doc"


def _doc_workflow(client, csrf, *, name, approval_required):
    return client.post(
        "/api/admin/workflows",
        json={
            "name": name,
            "webhook_url": DOC_URL,
            "operation_mode": "write",
            "approval_required": approval_required,
        },
        headers=_headers(csrf),
    ).json()["workflow"]["id"]


def _generate(client, csrf, workflow_id, mode, *, period="2026-W40", config=None):
    return client.post(
        "/api/admin/documents/generate",
        json={
            "workflow_id": workflow_id,
            "mode": mode,
            "period": period,
            "config": config or {"target_parent_page": "r3-page", "template_version": 1},
        },
        headers=_headers(csrf),
    )


def test_requester_cannot_bypass_workflow_approval_with_auto_publish(
    client, login_as, fake_http, app, settings, fake_clock
):
    """High: approval_required workflow인데 mode=auto_publish면 무승인 발행되던 결함."""
    from app.jobs.handlers.document_generate import handle_document_generate
    from app.jobs.worker import Worker, WorkerContext

    csrf = login_as("admin", email="r3-doc-admin@goodmit.co.kr")
    workflow_id = _doc_workflow(
        client, csrf, name="r3 승인필요 문서", approval_required=True
    )
    fake_http.on(
        DOC_URL,
        json_body={
            "title": "몰래 발행",
            "body": "본문 내용 충분히 깁니다. " * 3,
            "source_row_count": 5,
            "published_ref": "https://www.notion.so/should-not-happen",
        },
    )

    r = _generate(client, csrf, workflow_id, "auto_publish")
    assert r.status_code == 202
    gen = r.json()["generation"]
    # 서버가 mode를 강제로 승인 경로로 바꾼다.
    assert gen["mode"] == "preview_then_approve"

    ctx = WorkerContext(
        settings=settings, clock=fake_clock, outbound_client=app.state.outbound_client
    )
    Worker(
        app.state.session_factory, fake_clock,
        {"document_generate": handle_document_generate}, ctx,
    ).run_once()

    detail = client.get(f"/api/admin/documents/{gen['id']}").json()["generation"]
    assert detail["status"] == "awaiting_approval"
    assert detail["published_ref"] is None
    # preview만 호출됐고 publish는 나가지 않았다.
    actions = [json.loads(req.content)["action"] for req in fake_http.requests]
    assert actions == ["preview"]


def test_template_approval_policy_also_forces_approval(client, login_as, db):
    """Medium: 템플릿 approval_policy.required도 요청자의 mode보다 우선한다."""
    csrf = login_as("admin", email="r3-tmpl-admin@goodmit.co.kr")
    workflow_id = _doc_workflow(
        client, csrf, name="r3 무승인 워크플로", approval_required=False
    )

    from app.templates.models import AutomationTemplate

    template = AutomationTemplate(
        name="r3 승인 템플릿",
        target_type="workflow",
        target_ref=workflow_id,
        approval_policy_json=json.dumps({"required": True}),
        enabled=True,
    )
    db.add(template)
    db.commit()

    r = _generate(
        client, csrf, workflow_id, "auto_publish",
        config={
            "target_parent_page": "r3-tmpl-page",
            "template_version": 1,
            "template_id": template.id,
        },
    )
    assert r.status_code == 202
    assert r.json()["generation"]["mode"] == "preview_then_approve"


# --- 4. schedule.enable approval is bound to the definition it approved -----


def test_schedule_definition_changed_after_request_invalidates_approval(
    app, client, login_as, sched_workflow_id, db
):
    """Medium(TOCTOU): 승인 대기 중 PUT으로 정의를 바꾸면 승인자가 본 적 없는 내용이
    활성화되던 결함."""
    from fastapi.testclient import TestClient

    requester_csrf = login_as("admin", email="r3-toctou@goodmit.co.kr")
    schedule = _make_schedule(client, requester_csrf, sched_workflow_id, "정의 교체")
    approval = client.post(
        f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(requester_csrf)
    ).json()["approval"]

    # 승인 화면에 무엇을 승인하는지 보인다.
    definition = approval["request_payload"]["definition"]
    assert definition["cron_expression"] == "0 * * * *"
    assert definition["payload_template"] == {"scope": "all"}

    # 승인 대기 중 정의를 몰래 바꾼다.
    r = client.put(
        f"/api/admin/schedules/{schedule['id']}",
        json={
            "name": "정의 교체",
            "schedule_type": "cron",
            "cron_expression": "* * * * *",
            "timezone": "UTC",
            "target_type": "workflow",
            "target_ref": sched_workflow_id,
            "payload_template": {"scope": "everything", "delete": True},
        },
        headers=_headers(requester_csrf),
    )
    assert r.status_code == 200

    from app.users.service import create_user

    create_user(
        db, email="r3-approver@goodmit.co.kr", display_name="승인자",
        password=DEFAULT_TEST_PASSWORD, settings=app.state.settings,
        role="admin", must_change_password=False,
    )
    db.commit()
    with TestClient(app, raise_server_exceptions=False) as approver:
        csrf = approver.post(
            "/login",
            json={"email": "r3-approver@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD},
        ).json()["csrf_token"]
        decision = approver.post(
            f"/api/admin/approvals/{approval['id']}/approve", headers=_headers(csrf)
        )
        assert decision.status_code == 409
        assert "stale" in decision.json()["error"]["message"]

        detail = approver.get(
            f"/api/admin/schedules/{schedule['id']}"
        ).json()["schedule"]
        assert detail["enabled"] is False


def test_unchanged_definition_still_approves(app, client, login_as, sched_workflow_id, db):
    """정의가 그대로면 승인은 정상 적용된다 (게이트가 과하게 막지 않는다)."""
    from fastapi.testclient import TestClient
    from app.users.service import create_user

    requester_csrf = login_as("admin", email="r3-stable@goodmit.co.kr")
    schedule = _make_schedule(client, requester_csrf, sched_workflow_id, "정의 유지")
    approval = client.post(
        f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(requester_csrf)
    ).json()["approval"]

    create_user(
        db, email="r3-approver2@goodmit.co.kr", display_name="승인자2",
        password=DEFAULT_TEST_PASSWORD, settings=app.state.settings,
        role="admin", must_change_password=False,
    )
    db.commit()
    with TestClient(app, raise_server_exceptions=False) as approver:
        csrf = approver.post(
            "/login",
            json={"email": "r3-approver2@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD},
        ).json()["csrf_token"]
        r = approver.post(
            f"/api/admin/approvals/{approval['id']}/approve", headers=_headers(csrf)
        )
        assert r.status_code == 200, r.text
        detail = approver.get(
            f"/api/admin/schedules/{schedule['id']}"
        ).json()["schedule"]
        assert detail["enabled"] is True


def _approve_as_second_admin(app, db, approval_id, email):
    """Approve as a different admin and return the decision response."""
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


def _put_definition(client, csrf, schedule_id, workflow_id, *, cron, payload_template):
    return client.put(
        f"/api/admin/schedules/{schedule_id}",
        json={
            "name": "게이트 검증",
            "schedule_type": "cron",
            "cron_expression": cron,
            "timezone": "UTC",
            "target_type": "workflow",
            "target_ref": workflow_id,
            "payload_template": payload_template,
        },
        headers=_headers(csrf),
    )


def test_put_after_approval_cannot_run_an_unapproved_definition(
    app, client, login_as, sched_workflow_id, db
):
    """승인 후 PUT으로 정의를 갈아끼우면 승인받은 적 없는 정의가 실행되던 결함.

    승인 대기 중 변조(stale 검사)만 막고 승인 이후를 열어 두면 게이트는 무의미하다:
    무해한 정의로 승인을 받아 enabled를 얻은 뒤 PUT 한 번이면 그만이다.
    """
    csrf = login_as("admin", email="r3-postput@goodmit.co.kr")
    schedule = _make_schedule(client, csrf, sched_workflow_id, "게이트 검증")
    approval = client.post(
        f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(csrf)
    ).json()["approval"]
    assert (
        _approve_as_second_admin(
            app, db, approval["id"], "r3-postput-approver@goodmit.co.kr"
        ).status_code
        == 200
    )

    r = _put_definition(
        client, csrf, schedule["id"], sched_workflow_id,
        cron="* * * * *", payload_template={"scope": "everything", "delete": True},
    )
    assert r.status_code == 200
    # 승인받지 않은 정의는 활성 상태를 유지할 수 없다 — 다시 승인을 받아야 한다.
    assert r.json()["schedule"]["enabled"] is False
    assert r.json()["schedule"]["next_run_at"] is None

    rn = client.post(
        f"/api/admin/schedules/{schedule['id']}/run-now", json={}, headers=_headers(csrf)
    )
    assert rn.status_code == 409

    from app.schedules.models import ScheduleRun

    assert db.query(ScheduleRun).count() == 0


def test_put_without_definition_change_keeps_schedule_enabled(
    app, client, login_as, sched_workflow_id, db
):
    """정의가 그대로인 PUT은 활성 상태를 건드리지 않는다 (과잉 차단 방지)."""
    csrf = login_as("admin", email="r3-noop-put@goodmit.co.kr")
    schedule = _make_schedule(client, csrf, sched_workflow_id, "게이트 검증")
    approval = client.post(
        f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(csrf)
    ).json()["approval"]
    _approve_as_second_admin(app, db, approval["id"], "r3-noop-approver@goodmit.co.kr")

    r = _put_definition(
        client, csrf, schedule["id"], sched_workflow_id,
        cron="0 * * * *", payload_template={"scope": "all"},
    )
    assert r.status_code == 200
    assert r.json()["schedule"]["enabled"] is True


def test_system_admin_put_keeps_schedule_enabled(client, login_as, sched_workflow_id):
    """system_admin은 승인 대상이 아니다 (직접 활성화 가능) — 재승인을 요구하지 않는다."""
    csrf = login_as("system_admin", email="r3-sysadmin-put@goodmit.co.kr")
    schedule = _make_schedule(client, csrf, sched_workflow_id, "게이트 검증")
    client.post(
        f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(csrf)
    )
    r = _put_definition(
        client, csrf, schedule["id"], sched_workflow_id,
        cron="*/5 * * * *", payload_template={"scope": "some"},
    )
    assert r.status_code == 200
    assert r.json()["schedule"]["enabled"] is True
    assert r.json()["schedule"]["next_run_at"] is not None


# --- 5. Deleting a conversation must remove its text from the queue ---------


def test_deleted_conversation_text_does_not_survive_in_job_queue(client, login_as, db):
    """Medium: 대화 삭제가 Job payload를 남겨 원문이 큐에 영구 잔존하던 결함."""
    from app.jobs.models import Job

    csrf = login_as("user", email="r3-deleter@goodmit.co.kr")
    conv = client.post(
        "/api/conversations", json={}, headers=_headers(csrf)
    ).json()["conversation"]
    client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={"content": SECRET_TEXT, "client_message_id": "r3del0123456789abcdef0123456789a"},
        headers=_headers(csrf),
    )
    assert SECRET_TEXT in db.query(Job).one().payload_json

    r = client.delete(f"/api/conversations/{conv['id']}", headers=_headers(csrf))
    assert r.status_code == 200, r.text

    db.expire_all()
    job = db.query(Job).one()
    assert SECRET_TEXT not in job.payload_json
    assert "r3-deleter@goodmit.co.kr" not in job.payload_json
    payload = json.loads(job.payload_json)
    assert payload["purged"] is True
    # 큐 행 자체(운영 지표)는 남는다.
    assert job.job_type == "chat_message"


def test_retention_expiry_also_purges_job_payloads(client, login_as, db, fake_clock, app):
    """Medium: 보존기간 만료로 지워진 대화의 원문도 큐에 남으면 안 된다."""
    from app.core.retention import purge_old_conversations
    from app.jobs.models import Job

    csrf = login_as("user", email="r3-retention@goodmit.co.kr")
    conv = client.post(
        "/api/conversations", json={}, headers=_headers(csrf)
    ).json()["conversation"]
    client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={"content": SECRET_TEXT, "client_message_id": "r3ret0123456789abcdef0123456789a"},
        headers=_headers(csrf),
    )

    fake_clock.advance(400 * 24 * 3600)
    purged = purge_old_conversations(db, now=fake_clock.now(), retention_days=365)
    db.commit()
    assert purged == 1

    db.expire_all()
    assert SECRET_TEXT not in db.query(Job).one().payload_json


# --- 6. Body cap applies to chunked requests too ----------------------------


def test_chunked_request_without_content_length_is_capped(client):
    """Low: Content-Length가 없는 chunked 요청에는 본문 상한이 없던 결함."""

    def _chunks():
        for _ in range(6):
            yield b"x" * (64 * 1024)  # 총 384KB > 256KB 상한

    r = client.post("/healthz", content=_chunks())
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"


def test_malformed_content_length_rejected(client):
    """음수/비정수 Content-Length는 상한 비교를 무의미하게 만든다 — 형식 오류로 막는다."""
    for bad in ("-1", "abc"):
        r = client.post("/healthz", content=b"x", headers={"Content-Length": bad})
        assert r.status_code == 400, bad
        assert r.json()["error"]["code"] == "bad_request"


def test_chunked_request_within_limit_still_reaches_the_app(client, login_as):
    """상한 이하의 chunked 요청은 본문이 온전히 전달돼야 한다 (캡이 기능을 깨지 않음)."""
    csrf = login_as("user", email="r3-chunk@goodmit.co.kr")
    conv = client.post(
        "/api/conversations", json={}, headers=_headers(csrf)
    ).json()["conversation"]
    body = json.dumps(
        {"content": "청크로 보낸 메시지", "client_message_id": "r3chk0123456789abcdef0123456789a"}
    ).encode()

    def _chunks():
        yield body[: len(body) // 2]
        yield body[len(body) // 2 :]

    r = client.post(
        f"/api/conversations/{conv['id']}/messages",
        content=_chunks(),
        headers={"X-CSRF-Token": csrf, "Content-Type": "application/json"},
    )
    assert r.status_code == 202, r.text
    assert r.json()["message"]["content"] == "청크로 보낸 메시지"


# --- 7. Login must not reveal whether an account exists ---------------------


def test_locked_account_is_not_revealed_to_someone_without_the_password(
    client, make_user, settings
):
    """Low: 잠금 응답(403)이 비밀번호 검증 전에 나와 계정 존재가 드러나던 결함."""
    make_user("r3-locked@goodmit.co.kr")
    for _ in range(settings.login_max_failures):
        client.post(
            "/login",
            json={"email": "r3-locked@goodmit.co.kr", "password": "Wrong-Pass-123"},
        )

    # 잠긴 '기존' 계정에 틀린 비밀번호 → 존재하지 않는 계정과 응답이 같아야 한다.
    locked_existing = client.post(
        "/login", json={"email": "r3-locked@goodmit.co.kr", "password": "Wrong-Pass-123"}
    )
    unknown_account = client.post(
        "/login", json={"email": "r3-ghost@goodmit.co.kr", "password": "Wrong-Pass-123"}
    )
    assert locked_existing.status_code == unknown_account.status_code == 401
    assert (
        locked_existing.json()["error"]["code"]
        == unknown_account.json()["error"]["code"]
        == "invalid_credentials"
    )


def test_lock_is_reported_only_after_correct_password(client, make_user, settings):
    """본인(자격 증명 일치)에게는 잠금 사실을 알려 준다."""
    make_user("r3-owner-locked@goodmit.co.kr")
    for _ in range(settings.login_max_failures):
        client.post(
            "/login",
            json={"email": "r3-owner-locked@goodmit.co.kr", "password": "Wrong-Pass-123"},
        )
    r = client.post(
        "/login",
        json={"email": "r3-owner-locked@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "account_locked"


def test_unknown_account_still_runs_password_verification(client, monkeypatch):
    """없는 계정이 Argon2 검증을 건너뛰면 타이밍으로 계정 존재가 드러난다."""
    import app.auth.router as auth_router

    calls = []
    real_verify = auth_router.verify_password

    def _counting_verify(password_hash, password):
        calls.append(password_hash)
        return real_verify(password_hash, password)

    monkeypatch.setattr(auth_router, "verify_password", _counting_verify)
    r = client.post(
        "/login", json={"email": "r3-nobody@goodmit.co.kr", "password": "Wrong-Pass-123"}
    )
    assert r.status_code == 401
    assert len(calls) == 1  # 더미 해시로라도 검증을 수행했다.
    assert calls[0].startswith("$argon2")
