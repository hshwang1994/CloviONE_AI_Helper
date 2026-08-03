"""End-to-end chat pipeline: POST message → worker → fake n8n → assistant reply.
Covers spec §31.4: timeout, n8n error, invalid JSON, retry, unsupported request."""

import pytest

from app.jobs.handlers.chat_message import handle_chat_message
from app.jobs.worker import Worker, WorkerContext

pytestmark = pytest.mark.integration

N8N_URL = "http://127.0.0.1:5678/webhook/clovirone-work-assistant"
MSG_ID = "h0123456789abcdef0123456789abcdef"


@pytest.fixture()
def chat_worker(app, settings, fake_clock):
    ctx = WorkerContext(
        settings=settings,
        clock=fake_clock,
        outbound_client=app.state.outbound_client,
    )
    return Worker(
        app.state.session_factory,
        fake_clock,
        {"chat_message": handle_chat_message},
        ctx,
        poll_interval=0.01,
    )


@pytest.fixture()
def posted_message(client, login_as, make_user, db):
    # The message below is first-person ("내 할당 티켓"), so the user must be a
    # verified Notion mapping to reach n8n — otherwise the safe-block refuses it.
    from datetime import datetime

    from app.notion_mapping.service import manual_map

    user = make_user("chatter@goodmit.co.kr")
    manual_map(db, user, notion_user_id="chatter1234", notion_email="c@x",
               now=datetime(2026, 7, 14))
    db.commit()
    csrf = login_as("user", email="chatter@goodmit.co.kr")
    conv = client.post("/api/conversations", json={}, headers={"X-CSRF-Token": csrf}).json()[
        "conversation"
    ]
    r = client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={"content": "내 할당 티켓 보여줘", "client_message_id": MSG_ID},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 202
    return {"conversation_id": conv["id"], "csrf": csrf}


def _messages(client, conversation_id):
    return client.get(f"/api/conversations/{conversation_id}/messages").json()["items"]


def test_success_creates_assistant_reply(client, chat_worker, fake_http, posted_message):
    fake_http.on(
        N8N_URL,
        json_body={
            "reply": "할당된 티켓 2건입니다.",
            "conversation_id": "backend-ctx-123",
            "tickets": [
                {"title": "서버 점검", "status": "진행", "url": "https://www.notion.so/abc"}
            ],
        },
    )
    assert chat_worker.run_once() is True

    items = _messages(client, posted_message["conversation_id"])
    assert len(items) == 2
    user_msg, assistant = items
    assert user_msg["processing_status"] == "done"
    assert assistant["role"] == "assistant"
    assert assistant["content"] == "할당된 티켓 2건입니다."
    assert assistant["structured"]["tickets"][0]["title"] == "서버 점검"

    # n8n received the requester built from the session (spec §11.2).
    import json as _json

    sent = _json.loads(fake_http.requests[0].content)
    assert sent["requester"]["email"] == "chatter@goodmit.co.kr"
    assert sent["message"] == "내 할당 티켓 보여줘"


def test_backend_conversation_id_persisted_for_context(
    client, chat_worker, fake_http, posted_message, db
):
    fake_http.on(N8N_URL, json_body={"reply": "ok", "conversation_id": "ctx-777"})
    chat_worker.run_once()

    from app.conversations.models import Conversation

    conv = db.get(Conversation, posted_message["conversation_id"])
    assert conv.backend_conversation_id == "ctx-777"


def test_timeout_retries_then_marks_message_failed(
    client, chat_worker, fake_http, fake_clock, posted_message
):
    fake_http.on_timeout(N8N_URL)
    # 3 attempts (max_attempts default) with backoff between.
    for _ in range(3):
        assert chat_worker.run_once() is True
        fake_clock.advance(60)

    items = _messages(client, posted_message["conversation_id"])
    # Final failure now posts a guidance reply (원인+다음 행동) alongside the
    # failed user message — the '실패' badge alone told the user nothing.
    assert len(items) == 2
    assert items[1]["role"] == "assistant"
    assert "다시 시도" in items[1]["content"]
    assert items[0]["processing_status"] == "failed"
    # Timeout is a distinct diagnostic bucket from the generic transient
    # error_code (round22: on_failure used to collapse every terminal failure
    # into the same "assistant_error" code, losing this distinction).
    assert items[0]["error_code"] == "assistant_timeout"


def test_n8n_500_is_transient(client, chat_worker, fake_http, fake_clock, posted_message):
    fake_http.on(N8N_URL, status=500, json_body={"error": "boom"})
    chat_worker.run_once()
    items = _messages(client, posted_message["conversation_id"])
    # Still processing (queued for retry) — not failed yet.
    assert items[0]["processing_status"] == "processing"

    # Now n8n recovers.
    fake_http.on(N8N_URL, json_body={"reply": "복구됨"})
    fake_clock.advance(60)
    chat_worker.run_once()
    items = _messages(client, posted_message["conversation_id"])
    assert items[0]["processing_status"] == "done"
    assert items[1]["content"] == "복구됨"


def test_n8n_400_is_permanent(client, chat_worker, fake_http, posted_message):
    fake_http.on(N8N_URL, status=400, json_body={"error": "bad request"})
    chat_worker.run_once()
    items = _messages(client, posted_message["conversation_id"])
    assert items[0]["processing_status"] == "failed"


def test_invalid_json_is_transient_then_fails(
    client, chat_worker, fake_http, fake_clock, posted_message
):
    fake_http.on_invalid_json(N8N_URL)
    for _ in range(3):
        chat_worker.run_once()
        fake_clock.advance(60)
    items = _messages(client, posted_message["conversation_id"])
    assert items[0]["processing_status"] == "failed"


def test_user_retry_after_failure_succeeds(
    client, chat_worker, fake_http, fake_clock, posted_message
):
    fake_http.on(N8N_URL, status=400, json_body={})
    chat_worker.run_once()
    failed = _messages(client, posted_message["conversation_id"])[0]
    assert failed["processing_status"] == "failed"

    fake_http.on(N8N_URL, json_body={"reply": "재시도 성공"})
    r = client.post(
        f"/api/messages/{failed['id']}/retry",
        headers={"X-CSRF-Token": posted_message["csrf"]},
    )
    assert r.status_code == 200
    fake_clock.advance(1)
    chat_worker.run_once()

    items = _messages(client, posted_message["conversation_id"])
    assert items[0]["processing_status"] == "done"
    assert items[-1]["content"] == "재시도 성공"


def test_unsupported_response_shape_gets_default_text(
    client, chat_worker, fake_http, posted_message
):
    fake_http.on(N8N_URL, json_body={"unknown_key": 42})
    processed = chat_worker.run_once()
    items = _messages(client, posted_message["conversation_id"])
    detail = {
        "processed": processed,
        "items": [
            (m["role"], m["processing_status"], m["content"][:60]) for m in items
        ],
    }
    assert len(items) == 2, detail
    # 알아볼 수 있는 답이 없는 응답은 '처리되었습니다'로 뭉개지 않는다 — 워크플로가 중간에
    # 끊겨도 사용자가 성공한 줄 알던 문제를 고치면서 바뀐 계약이다(2026-08-03).
    assert "답을 돌려주지 않았습니다" in items[1]["content"], detail


def test_attachments_reach_n8n_then_get_stripped(client, chat_worker, fake_http, login_as, make_user, db):
    """#34 Phase 2: image bytes must be forwarded to n8n once, then purged from the
    stored job payload (서버 미보관) while keeping name markers."""
    import json as _json

    PNG_B64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
        "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    make_user("imager@goodmit.co.kr")
    csrf = login_as("user", email="imager@goodmit.co.kr")
    conv = client.post("/api/conversations", json={}, headers={"X-CSRF-Token": csrf}).json()["conversation"]
    r = client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={
            "content": "스크린샷 분석해줘",
            "client_message_id": "hatt0123456789abcdef0123456789ab",
            "attachments": [{"filename": "e.png", "media_type": "image/png", "data": PNG_B64}],
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 202
    job_id = r.json()["job_id"]

    fake_http.on(N8N_URL, json_body={"response_text": "이미지를 확인했습니다."})
    assert chat_worker.run_once() is True

    # 1) n8n request carried the attachment data.
    sent = _json.loads(fake_http.requests[-1].content)
    assert sent["attachments"][0]["data"] == PNG_B64
    # 2) after success the job payload keeps names only.
    from app.jobs.models import Job

    db.expire_all()
    payload = _json.loads(db.get(Job, job_id).payload_json)
    assert payload["attachments"][0]["stripped"] is True
    assert "data" not in payload["attachments"][0]


def test_safe_refusal_also_strips_attachment_bytes(client, chat_worker, fake_http, login_as, make_user, db):
    """Unmapped first-person messages are now FORWARDED (runner resolves by
    name/email); the strip still runs on the success path."""
    import json as _json

    PNG_B64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
        "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    make_user("unmapped-img@goodmit.co.kr")  # no Notion mapping on purpose
    csrf = login_as("user", email="unmapped-img@goodmit.co.kr")
    conv = client.post("/api/conversations", json={}, headers={"X-CSRF-Token": csrf}).json()["conversation"]
    r = client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={
            "content": "내 티켓 진행상황 봐줘",  # first-person → safe-refusal branch
            "client_message_id": "hstr0123456789abcdef0123456789ab",
            "attachments": [{"filename": "e.png", "media_type": "image/png", "data": PNG_B64}],
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    fake_http.on(N8N_URL, json_body={"response_text": "진행 중인 티켓 2건입니다."})
    assert chat_worker.run_once() is True

    from app.jobs.models import Job

    db.expire_all()
    payload = _json.loads(db.get(Job, job_id).payload_json)
    assert payload["attachments"][0].get("stripped") is True
    assert "data" not in payload["attachments"][0]
    assert len(fake_http.requests) == 1  # forwarded to n8n, not refused


def test_retry_recovers_attachments_and_strips_donor(client, chat_worker, fake_http, posted_message, db):
    """Review fix: a user-initiated retry must re-send the image bytes (copied from
    the failed job) instead of silently dropping them."""
    import json as _json

    # Fail the pre-posted message permanently (n8n 400 → PermanentJobError).
    fake_http.on(N8N_URL, status=400, json_body={"error": "bad"})
    assert chat_worker.run_once() is True
    items = _messages(client, posted_message["conversation_id"])
    failed = [m for m in items if m["processing_status"] == "failed"]
    assert failed, "message should be failed after permanent n8n rejection"

    # Post a NEW message with an image and fail it too.
    PNG_B64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
        "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    r = client.post(
        f"/api/conversations/{posted_message['conversation_id']}/messages",
        json={
            "content": "이 스크린샷 봐줘",
            "client_message_id": "hrty0123456789abcdef0123456789ab",
            "attachments": [{"filename": "s.png", "media_type": "image/png", "data": PNG_B64}],
        },
        headers={"X-CSRF-Token": posted_message["csrf"]},
    )
    assert r.status_code == 202
    first_job_id = r.json()["job_id"]
    assert chat_worker.run_once() is True  # fails permanently (400 still active)

    msg_db_id = r.json()["message"]["id"]
    r2 = client.post(
        f"/api/messages/{msg_db_id}/retry",
        json={},
        headers={"X-CSRF-Token": posted_message["csrf"]},
    )
    assert r2.status_code == 200

    from app.jobs.models import Job
    from sqlalchemy import select as _select

    db.expire_all()
    jobs = db.execute(
        _select(Job).where(Job.message_id == "hrty0123456789abcdef0123456789ab")
        .order_by(Job.created_at)
    ).scalars().all()
    assert len(jobs) == 2
    old_payload = _json.loads(jobs[0].payload_json)
    new_payload = _json.loads(jobs[1].payload_json)
    assert new_payload["attachments"][0]["data"] == PNG_B64      # bytes recovered
    assert old_payload["attachments"][0].get("stripped") is True  # donor stripped


# --- on_failure error_code buckets (app/jobs/handlers/chat_message.py) --------
# The '실패' badge alone tells the user nothing; on_failure differentiates at
# least three diagnostic buckets so a UI/DB reader can tell "retrying is
# pointless without admin action" apart from "just retry". timeout →
# assistant_timeout is already pinned by test_timeout_retries_then_marks_message_failed.


def test_n8n_400_bucketed_as_assistant_rejected_with_no_retry_guidance(
    client, chat_worker, fake_http, posted_message
):
    # A permanent 4xx rejection: retrying the identical content will likely fail
    # the same way, so the guidance must NOT imply retry is a reliable fix.
    fake_http.on(N8N_URL, status=400, json_body={"error": "bad request"})
    assert chat_worker.run_once() is True

    items = _messages(client, posted_message["conversation_id"])
    assert items[0]["processing_status"] == "failed"
    assert items[0]["error_code"] == "assistant_rejected"
    # Guidance reply says retrying likely fails the same way (no-retry wording).
    assert items[1]["role"] == "assistant"
    assert "동일하게 실패" in items[1]["content"]


def test_transient_exhausted_bucketed_as_assistant_error(
    client, chat_worker, fake_http, fake_clock, posted_message
):
    # n8n 5xx is transient; after max_attempts are exhausted the terminal failure
    # is the generic connection/server bucket (retry is a reasonable next step).
    fake_http.on(N8N_URL, status=500, json_body={"error": "boom"})
    for _ in range(3):
        assert chat_worker.run_once() is True
        fake_clock.advance(60)

    items = _messages(client, posted_message["conversation_id"])
    assert items[0]["processing_status"] == "failed"
    assert items[0]["error_code"] == "assistant_error"
    assert items[1]["role"] == "assistant"
    assert "다시 시도" in items[1]["content"]


# --- chat Workflow registry wiring (app/jobs/handlers/chat_message.py) ---------
# The admin Workflows screen edits webhook_url / enables-disables the seeded chat
# workflow row. The handler must honor that row (CHAT_WORKFLOW_NAME) or every
# control on that screen for chat would be a dead affordance.


def _seed_chat_workflow(db, app):
    from sqlalchemy import select

    from app.jobs.handlers.chat_message import CHAT_WORKFLOW_NAME
    from app.workflows.models import Workflow
    from app.workflows.service import seed_known_workflows

    seed_known_workflows(db, allowlists=app.state.allowlists)
    db.commit()
    return db.execute(
        select(Workflow).where(Workflow.name == CHAT_WORKFLOW_NAME)
    ).scalar_one()


def test_disabled_chat_workflow_fails_without_calling_n8n(
    app, client, chat_worker, fake_http, posted_message, db
):
    row = _seed_chat_workflow(db, app)
    row.enabled = False
    db.commit()

    # If the handler wrongly fell back to the static URL, this route would answer.
    fake_http.on(N8N_URL, json_body={"reply": "must not be sent"})
    assert chat_worker.run_once() is True

    items = _messages(client, posted_message["conversation_id"])
    assert items[0]["processing_status"] == "failed"
    # Disabled workflow is a permanent, admin-actionable failure → rejected bucket.
    assert items[0]["error_code"] == "assistant_rejected"
    assert items[1]["role"] == "assistant"
    # The outbound client was never called — resolution failed before the request.
    assert fake_http.requests == []


def test_enabled_workflow_uses_edited_webhook_url(
    app, client, chat_worker, fake_http, posted_message, db
):
    row = _seed_chat_workflow(db, app)
    edited_url = "http://127.0.0.1:5678/webhook/edited-chat-endpoint"
    row.webhook_url = edited_url
    db.commit()

    # Route the EDITED url; leave the original static url unrouted (would 502).
    fake_http.on(edited_url, json_body={"reply": "편집된 엔드포인트 응답"})
    assert chat_worker.run_once() is True

    items = _messages(client, posted_message["conversation_id"])
    assert items[0]["processing_status"] == "done"
    assert items[1]["content"] == "편집된 엔드포인트 응답"
    # The request went to the admin-edited URL, not the static settings default.
    assert str(fake_http.requests[-1].url) == edited_url
