import json

import pytest

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.security

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
