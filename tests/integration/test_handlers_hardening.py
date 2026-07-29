"""Retry-hardening for job handlers and the Notion-sync enqueue key.

Covers three idempotency/retry defects:
  1. document_generate: on retry, an already-published doc (published_ref set) must
     short-circuit to succeeded instead of re-running preview+quality (which can
     diverge and flip a live doc to quality_failed).
  2. chat_message: the n8n POST carries a stable idempotency_key so a lost-response
     retry lets n8n dedupe a WRITE instead of performing it twice.
  3. notion_mapping /sync: a fresh sync click in the same minute must NOT be deduped
     into a stale pre-existing job.
"""

import json

import pytest

from app.jobs.handlers.chat_message import handle_chat_message
from app.jobs.handlers.document_generate import handle_document_generate
from app.jobs.worker import Worker, WorkerContext

pytestmark = pytest.mark.integration

DOC_URL = "http://127.0.0.1:5678/webhook/doc-gen"
N8N_URL = "http://127.0.0.1:5678/webhook/clovirone-work-assistant"


# --------------------------------------------------------------------------- #
# 1. document_generate short-circuit when already published
# --------------------------------------------------------------------------- #
@pytest.fixture()
def doc_worker(app, settings, fake_clock):
    ctx = WorkerContext(
        settings=settings, clock=fake_clock, outbound_client=app.state.outbound_client
    )
    return Worker(
        app.state.session_factory, fake_clock,
        {"document_generate": handle_document_generate}, ctx,
    )


def _seed_published_generation(db, fake_clock, *, status, published_ref):
    """Create a workflow + a generation that is already published in Notion."""
    from app.documents.models import DocumentGeneration, MODE_AUTO_PUBLISH
    from app.workflows.models import MODE_WRITE, Workflow

    now = fake_clock.now()
    wf = Workflow(
        name="문서 생성(단락 테스트)",
        webhook_url=DOC_URL,
        operation_mode=MODE_WRITE,
        approval_required=False,
        created_at=now,
        updated_at=now,
    )
    db.add(wf)
    db.flush()
    gen = DocumentGeneration(
        workflow_id=wf.id,
        mode=MODE_AUTO_PUBLISH,
        idempotency_key=f"docgen-test:{published_ref}",
        status=status,
        config_json=json.dumps({"target_parent_page": "page-1", "template_version": 1}),
        published_ref=published_ref,
        created_at=now,
    )
    db.add(gen)
    db.commit()
    return gen.id


def test_retry_short_circuits_when_already_published(db, doc_worker, fake_http, fake_clock):
    """gen.published_ref set + a spurious retry → succeeded, n8n never re-called.

    Simulates §32.8: the publish succeeded on n8n (published_ref recorded) but the
    response was lost and the job requeued. Re-running preview here would call n8n
    again and could record quality_failed on a doc that is actually live.
    """
    from app.documents.models import DocumentGeneration, STATUS_QUALITY_FAILED
    from app.jobs import repository as jobs_repo

    gen_id = _seed_published_generation(
        db, fake_clock,
        status=STATUS_QUALITY_FAILED,  # a diverged/incorrect prior state
        published_ref="https://www.notion.so/live-doc-123",
    )
    # A route exists; the point is the handler must NOT touch it.
    fake_http.on(DOC_URL, json_body={"title": "x", "body": "y", "source_row_count": 0})

    with doc_worker._session_factory() as s:
        jobs_repo.enqueue(
            s, job_type="document_generate", payload={"generation_id": gen_id},
            now=fake_clock.now(),
        )
        s.commit()

    assert doc_worker.run_once() is True

    detail = db.get(DocumentGeneration, gen_id)
    db.refresh(detail)
    assert detail.status == "published"          # flipped back to the truth
    assert detail.published_ref == "https://www.notion.so/live-doc-123"
    assert fake_http.requests == []              # n8n never called on the retry


def test_already_published_status_left_untouched(db, doc_worker, fake_http, fake_clock):
    """If status is already 'published', the short-circuit is a clean no-op."""
    from app.documents.models import DocumentGeneration, STATUS_PUBLISHED
    from app.jobs import repository as jobs_repo

    gen_id = _seed_published_generation(
        db, fake_clock, status=STATUS_PUBLISHED,
        published_ref="https://www.notion.so/already",
    )
    fake_http.on(DOC_URL, json_body={"title": "x", "body": "y", "source_row_count": 0})
    with doc_worker._session_factory() as s:
        jobs_repo.enqueue(
            s, job_type="document_generate", payload={"generation_id": gen_id},
            now=fake_clock.now(),
        )
        s.commit()

    assert doc_worker.run_once() is True
    gen = db.get(DocumentGeneration, gen_id)
    db.refresh(gen)
    assert gen.status == "published"
    assert fake_http.requests == []


# --------------------------------------------------------------------------- #
# 2. chat_message carries a stable idempotency key to n8n
# --------------------------------------------------------------------------- #
@pytest.fixture()
def chat_worker(app, settings, fake_clock):
    ctx = WorkerContext(
        settings=settings, clock=fake_clock, outbound_client=app.state.outbound_client
    )
    return Worker(
        app.state.session_factory, fake_clock,
        {"chat_message": handle_chat_message}, ctx, poll_interval=0.01,
    )


def _post_message(client, login_as, make_user, db, *, content, client_message_id):
    from datetime import datetime

    from app.notion_mapping.service import manual_map

    user = make_user("idem-chatter@goodmit.co.kr")
    manual_map(db, user, notion_user_id="idemchat1234", notion_email="i@x",
               now=datetime(2026, 7, 14))
    db.commit()
    csrf = login_as("user", email="idem-chatter@goodmit.co.kr")
    conv = client.post("/api/conversations", json={},
                       headers={"X-CSRF-Token": csrf}).json()["conversation"]
    r = client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={"content": content, "client_message_id": client_message_id},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 202, r.text
    return client_message_id


def test_chat_request_carries_stable_idempotency_key(
    client, chat_worker, fake_http, login_as, make_user, db
):
    msg_id = "hidem0123456789abcdef0123456789ab"
    _post_message(client, login_as, make_user, db,
                  content="내 할당 티켓 보여줘", client_message_id=msg_id)
    fake_http.on(N8N_URL, json_body={"reply": "ok"})
    assert chat_worker.run_once() is True

    sent = json.loads(fake_http.requests[-1].content)
    # Present, stable, and derived from the message id (survives requeue/retry).
    assert sent["idempotency_key"] == f"chatmsg:{msg_id}"


# --------------------------------------------------------------------------- #
# 3. notion_mapping /sync: active-dedup — double-click reuses the in-flight job,
#    but a fresh click after it completes runs again (fixes the stale-pre-add-user bug).
# --------------------------------------------------------------------------- #
def test_sync_dedups_active_but_allows_fresh_after_completion(client, login_as, fake_clock, db):
    csrf = login_as("admin")
    headers = {"X-CSRF-Token": csrf}

    r1 = client.post("/api/admin/notion-mapping/sync", headers=headers)
    r2 = client.post("/api/admin/notion-mapping/sync", headers=headers)
    assert r1.status_code == 202 and r2.status_code == 202
    # 진행 중(queued) 잡이 있으므로 신경질적 더블클릭은 같은 잡 → 중복 조회 안 함.
    assert r1.json()["job_id"] == r2.json()["job_id"]

    # 첫 잡을 완료 처리하면 새 클릭은 새 잡을 만든다(사용자 추가 후 재동기화가 막히지 않음).
    from app.jobs.models import STATUS_SUCCEEDED, Job

    job = db.get(Job, r1.json()["job_id"])
    job.status = STATUS_SUCCEEDED
    db.commit()
    r3 = client.post("/api/admin/notion-mapping/sync", headers=headers)
    assert r3.status_code == 202
    assert r3.json()["job_id"] != r1.json()["job_id"]
