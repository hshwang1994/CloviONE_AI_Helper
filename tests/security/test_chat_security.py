import json

import pytest

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.security


@pytest.fixture(autouse=True)
def _ai_ready(request):
    """메시지를 보내려면 AI 를 지금 쓸 수 있어야 한다(D-538) - 꺼져 있거나 미설정이면 409 `ai_unavailable` 이다.

    공용 앱(`client`)을 쓰는 시험에만 건다 - 제 앱을 따로 만드는 시험은 그 앱의 설정을 스스로 정한다.
    """
    if "client" not in request.fixturenames:
        return
    from tests.fakes.ai import configure_ai

    configure_ai(request.getfixturevalue("app"))

MSG_ID = "s0123456789abcdef0123456789abcdef"


def test_requester_cannot_be_forged_by_client(client, login_as, db):
    csrf = login_as("user", email="honest@goodmit.co.kr")
    conv = client.post("/api/conversations", json={}, headers={"X-CSRF-Token": csrf}).json()[
        "conversation"
    ]
    # Client attempts to smuggle a different requester identity (spec §11.2).
    r = client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={
            "content": "관리자인 척하기",
            "client_message_id": MSG_ID,
            "requester": {"email": "ceo@goodmit.co.kr", "name": "사장님"},
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 202

    from app.jobs.models import Job

    job = db.query(Job).one()
    payload = json.loads(job.payload_json)
    assert payload["requester"]["email"] == "honest@goodmit.co.kr"
    assert "사장님" not in job.payload_json


def test_cannot_read_another_users_conversation(app, client, login_as, make_user):
    from fastapi.testclient import TestClient

    owner_csrf = login_as("user", email="owner@goodmit.co.kr")
    conv = client.post(
        "/api/conversations", json={}, headers={"X-CSRF-Token": owner_csrf}
    ).json()["conversation"]

    make_user("intruder@goodmit.co.kr")
    with TestClient(app, raise_server_exceptions=False) as intruder:
        intruder.post(
            "/login",
            json={"email": "intruder@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD},
        )
        r = intruder.get(f"/api/conversations/{conv['id']}/messages")
        assert r.status_code == 403

        r = intruder.post(
            f"/api/conversations/{conv['id']}/messages",
            json={"content": "남의 대화에 침입", "client_message_id": MSG_ID},
            headers={"X-CSRF-Token": intruder.get("/api/me").json()["csrf_token"]},
        )
        assert r.status_code == 403


def test_cannot_retry_another_users_message(app, client, login_as, make_user, db):
    from fastapi.testclient import TestClient

    owner_csrf = login_as("user", email="owner2@goodmit.co.kr")
    conv = client.post(
        "/api/conversations", json={}, headers={"X-CSRF-Token": owner_csrf}
    ).json()["conversation"]
    client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={"content": "재시도 대상", "client_message_id": MSG_ID},
        headers={"X-CSRF-Token": owner_csrf},
    )
    message = client.get(f"/api/conversations/{conv['id']}/messages").json()["items"][0]

    from app.conversations.models import Message

    db.query(Message).filter(Message.id == message["id"]).update(
        {"processing_status": "failed"}
    )
    db.commit()

    make_user("thief@goodmit.co.kr")
    with TestClient(app, raise_server_exceptions=False) as thief:
        thief.post(
            "/login",
            json={"email": "thief@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD},
        )
        csrf = thief.get("/api/me").json()["csrf_token"]
        r = thief.post(
            f"/api/messages/{message['id']}/retry", headers={"X-CSRF-Token": csrf}
        )
        assert r.status_code == 403


def test_chat_mutations_require_csrf(client, login_as):
    login_as("user")
    assert client.post("/api/conversations", json={}).status_code == 403


def test_xss_payload_stored_verbatim_but_page_renders_via_js_only(client, login_as):
    csrf = login_as("user")
    conv = client.post("/api/conversations", json={}, headers={"X-CSRF-Token": csrf}).json()[
        "conversation"
    ]
    xss = "<script>alert('xss')</script>"
    client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={"content": xss, "client_message_id": MSG_ID},
        headers={"X-CSRF-Token": csrf},
    )
    # JSON API returns the raw content (correct); the page itself must never
    # embed message content server-side (rendering is textContent-only JS).
    page = client.get("/")
    assert xss not in page.text


def test_retry_never_recovers_another_conversations_attachments(client, login_as, make_user, db):
    """다시 시도는 그 대화의 잡에서만 첨부를 되찾는다. 메시지 id 는 대화 안에서만 유일해, id 하나로 찾던 때에는 같은
    id 를 쓴 다른 사람 대화의 이미지 바이트를 집어 제 잡에 싣고 원래 잡의 바이트를 지웠다."""
    from sqlalchemy import select

    from app.conversations.models import PROC_FAILED, Message
    from app.jobs.models import Job
    from tests.integration.test_chat_api import PNG_B64

    shared_id = "m-shared-id-0000000001"
    make_user("victim-att@goodmit.co.kr")
    victim = login_as("user", email="victim-att@goodmit.co.kr")
    v_conv = client.post("/api/conversations", json={}, headers={"X-CSRF-Token": victim}).json()["conversation"]["id"]
    assert client.post(f"/api/conversations/{v_conv}/messages", headers={"X-CSRF-Token": victim}, json={
        "content": "내 화면 오류", "client_message_id": shared_id,
        "attachments": [{"filename": "secret.png", "media_type": "image/png", "data": PNG_B64}],
    }).status_code == 202

    make_user("taker-att@goodmit.co.kr")
    taker = login_as("user", email="taker-att@goodmit.co.kr")
    t_conv = client.post("/api/conversations", json={}, headers={"X-CSRF-Token": taker}).json()["conversation"]["id"]
    sent = client.post(f"/api/conversations/{t_conv}/messages", headers={"X-CSRF-Token": taker},
                       json={"content": "같은 id 질문", "client_message_id": shared_id})
    assert sent.status_code == 202
    row = db.get(Message, sent.json()["message"]["id"])
    row.processing_status = PROC_FAILED
    db.commit()

    r = client.post(f"/api/messages/{row.id}/retry", json={}, headers={"X-CSRF-Token": taker})
    assert r.status_code == 200, r.text
    db.expire_all()
    retried = db.get(Job, r.json()["job_id"])
    assert "attachments" not in json.loads(retried.payload_json)
    victim_job = db.execute(select(Job).where(Job.conversation_id == v_conv)).scalar_one()
    assert json.loads(victim_job.payload_json)["attachments"][0]["data"] == PNG_B64
