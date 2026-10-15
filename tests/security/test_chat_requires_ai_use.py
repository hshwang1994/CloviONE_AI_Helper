"""🔴 AI 도우미 채팅은 `AI_USE` 권한을 본다 — 모든 경로, 그리고 실행하는 순간에 한 번 더 (D-538).

예전에는 작업 공간만 이 권한을 보고 채팅은 보지 않아 RBAC 로 좁힐 수 없었다. 이제 채팅 경로 전부가 403 이고, 메시지를 넣은 뒤
실행 전에 권한을 잃으면 워커가 안내 답만 남기고 제공자를 부르지 않는다.
"""

from __future__ import annotations

import pytest

from app.conversations.models import Message
from app.jobs.handlers.chat_message import NO_PERMISSION_TEXT, handle_chat_message
from app.jobs.worker import Worker, WorkerContext
from tests.fakes.ai import ScriptedToolAdapter, install_runtime
from tests.fakes.authz import revoke

pytestmark = pytest.mark.integration

MSG = "u" * 32


def _h(csrf):
    return {"X-CSRF-Token": csrf}


def test_every_chat_route_is_closed_without_ai_use(client, login_as, db, app):
    install_runtime(app, ScriptedToolAdapter(["답"]))
    csrf = login_as("user")
    conversation = client.post("/api/conversations", json={}, headers=_h(csrf)).json()["conversation"]
    sent = client.post(f"/api/conversations/{conversation['id']}/messages",
                       json={"content": "안녕", "client_message_id": MSG}, headers=_h(csrf))
    assert sent.status_code == 202
    message_id = sent.json()["message"]["id"]

    revoke(db, "user", "AI_USE")
    cid = conversation["id"]
    calls = [
        ("get", "/api/conversations", None),
        ("post", "/api/conversations", {}),
        ("get", f"/api/conversations/{cid}/messages", None),
        ("patch", f"/api/conversations/{cid}", {"title": "새 제목"}),
        ("delete", f"/api/conversations/{cid}", None),
        ("post", f"/api/conversations/{cid}/messages", {"content": "안녕", "client_message_id": "v" * 32}),
        ("post", f"/api/messages/{message_id}/retry", {}),
        ("post", f"/api/messages/{message_id}/regenerate", {}),
        ("delete", f"/api/messages/{message_id}", None),
        ("patch", f"/api/messages/{message_id}/feedback", {"feedback": "up"}),
        ("get", "/api/me/ai-quota", None),
        ("post", "/api/conversations/archive-empty", {}),
        ("get", f"/api/messages/{message_id}/results/r1", None),
    ]
    for method, path, body in calls:
        kwargs = {"headers": _h(csrf)}
        if body is not None:
            kwargs["json"] = body
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 403, (method, path, response.status_code)
    assert client.get("/api/me").json()["capabilities"] == {"ai_use": False}


def test_losing_ai_use_after_sending_means_no_provider_call(client, login_as, db, app, settings, fake_clock):
    adapter = ScriptedToolAdapter(["답입니다."])
    runtime = install_runtime(app, adapter)
    csrf = login_as("user")
    conversation = client.post("/api/conversations", json={}, headers=_h(csrf)).json()["conversation"]
    assert client.post(f"/api/conversations/{conversation['id']}/messages",
                       json={"content": "안녕", "client_message_id": MSG}, headers=_h(csrf)).status_code == 202

    revoke(db, "user", "AI_USE")
    ctx = WorkerContext(settings=settings, clock=fake_clock, outbound_client=app.state.outbound_client,
                        extras={"ai_runtime": runtime, "session_factory": app.state.session_factory,
                                "settings_cache": app.state.settings_cache})
    Worker(app.state.session_factory, fake_clock, {"chat_message": handle_chat_message}, ctx,
           poll_interval=0.01).run_once()

    assert adapter.converse_calls == []
    db.expire_all()
    rows = db.query(Message).filter(Message.conversation_id == conversation["id"]).order_by(Message.seq).all()
    assert [r.content for r in rows if r.role == "assistant"] == [NO_PERMISSION_TEXT]
    assert next(r for r in rows if r.role == "user").error_code == "assistant_no_permission"
