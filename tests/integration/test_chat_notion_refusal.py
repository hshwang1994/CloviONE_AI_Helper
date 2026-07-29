"""First-person requests are FORWARDED even for unmapped users.

The runner matches the requester by name/email against the live Notion people
directory, so the platform never gates on admin-verified mapping (매핑은 정확도
보조 기능이지 관문이 아니다). The old platform-side refusal blocked users the
runner could resolve fine — user report: '나한테 할당된 티켓 보여줘' was refused.
"""

import pytest

from app.jobs.handlers.chat_message import handle_chat_message
from app.jobs.worker import Worker, WorkerContext

pytestmark = pytest.mark.integration

N8N_URL = "http://127.0.0.1:5678/webhook/clovirone-work-assistant"


@pytest.fixture()
def chat_worker(app, settings, fake_clock):
    ctx = WorkerContext(
        settings=settings, clock=fake_clock, outbound_client=app.state.outbound_client
    )
    return Worker(
        app.state.session_factory, fake_clock, {"chat_message": handle_chat_message}, ctx
    )


def _post(client, csrf, conv_id, content, mid):
    return client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": content, "client_message_id": mid},
        headers={"X-CSRF-Token": csrf},
    )


def _messages(client, conv_id):
    return client.get(f"/api/conversations/{conv_id}/messages").json()["items"]


@pytest.mark.parametrize("phrase", ["내 티켓 보여줘", "내 할당 티켓 보기", "내 담당 프로젝트", "my tickets"])
def test_unmapped_user_first_person_request_reaches_n8n(
    client, login_as, chat_worker, fake_http, phrase
):
    csrf = login_as("user", email="unmapped@goodmit.co.kr")
    conv = client.post("/api/conversations", json={}, headers={"X-CSRF-Token": csrf}).json()[
        "conversation"
    ]
    fake_http.on(N8N_URL, json_body={"response_text": "황형섭 담당 티켓 3건입니다."})
    _post(client, csrf, conv["id"], phrase, "u" + "0" * 31)
    chat_worker.run_once()

    items = _messages(client, conv["id"])
    assert items[0]["processing_status"] == "done"
    assert items[1]["role"] == "assistant"
    assert items[1]["content"] == "황형섭 담당 티켓 3건입니다."
    assert len(fake_http.requests) == 1  # forwarded, not refused


def test_requester_identity_still_comes_from_session(client, login_as, chat_worker, fake_http):
    """Forwarding unmapped users must not weaken the no-forgery invariant — the
    requester identity still comes only from the server-side session (spec §11.2)."""
    import json as _json

    csrf = login_as("user", email="identity@goodmit.co.kr")
    conv = client.post("/api/conversations", json={}, headers={"X-CSRF-Token": csrf}).json()[
        "conversation"
    ]
    fake_http.on(N8N_URL, json_body={"response_text": "확인"})
    _post(client, csrf, conv["id"], "내 티켓 보여줘", "i" + "0" * 31)
    chat_worker.run_once()

    sent = _json.loads(fake_http.requests[-1].content)
    assert sent["requester"]["email"] == "identity@goodmit.co.kr"
