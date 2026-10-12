"""받은 편지함 확인 기록과 메일 상태 응답의 일곱 단계 (기능 개선 회차 P4, D-560).

못박는 성질:
1. `GET /api/admin/mail/status` 가 `progress{steps[7], next}` 와 `latest_test` · `inbox` 를 싣는다.
2. 접수된 시험 메일만 「받았습니다」로 기록할 수 있다 - 시험 메일이 아니면 422, 아직 접수되지 않았으면 409, 범위 밖이면 404.
3. 기록은 전역 관리 범위가 한다(부서 범위 관리자 · 일반 사용자 403). 감사에 메일 id 와 결과가 남고 주소는 가린다.
4. 기록한 뒤 일곱째 단계가 끝나고 다음 할 일이 없다. 「못 받았다」는 막힌 단계다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.audit.models import AuditLog
from app.mail.models import MAIL_SENT
from tests.integration.test_mail_health import FakeServer
from tests.integration.test_password_reset import configure_smtp, drain_worker

pytestmark = pytest.mark.integration


def _status(client, csrf) -> dict:
    return client.get("/api/admin/mail/status", headers={"X-CSRF-Token": csrf}).json()


def _send_test(client, csrf, app, settings, fake_clock, server) -> dict:
    sent = client.post("/api/admin/mail/test", json={}, headers={"X-CSRF-Token": csrf})
    assert sent.status_code == 200, sent.text
    drain_worker(app, settings, fake_clock, server)
    return client.get(f"/api/admin/mail/deliveries/{sent.json()['delivery']['id']}",
                      headers={"X-CSRF-Token": csrf}).json()["delivery"]


def test_the_status_carries_seven_steps_and_the_test_mail_is_acceptance_not_arrival(client, login_as, app, settings,
                                                                                     fake_clock):
    csrf = login_as("system_admin")
    configure_smtp(app)
    body = _status(client, csrf)
    assert [s["key"] for s in body["progress"]["steps"]] == [
        "enable", "method", "inputs", "applied", "verified", "test_sent", "inbox_confirmed",
    ]
    assert body["progress"]["next"]["key"] == "verified"
    assert body["latest_test"] is None and body["inbox"] is None

    server = FakeServer()
    verify = client.post("/api/admin/mail/verify", headers={"X-CSRF-Token": csrf})
    assert verify.status_code == 200
    drain_worker(app, settings, fake_clock, server)
    assert _status(client, csrf)["progress"]["next"]["key"] == "test_sent"

    delivery = _send_test(client, csrf, app, settings, fake_clock, server)
    assert delivery["status"] == MAIL_SENT
    body = _status(client, csrf)
    assert body["latest_test"]["id"] == delivery["id"]
    assert body["progress"]["next"]["key"] == "inbox_confirmed", "접수는 도착이 아니다 - 사람이 확인할 일이 남는다"
    assert body["progress"]["done_count"] == 6


def test_only_an_accepted_test_mail_can_be_confirmed_and_the_record_closes_the_last_step(client, login_as, app,
                                                                                         settings, fake_clock, db):
    csrf = login_as("system_admin")
    configure_smtp(app)
    server = FakeServer()
    queued = client.post("/api/admin/mail/test", json={}, headers={"X-CSRF-Token": csrf}).json()["delivery"]
    early = client.post("/api/admin/mail/inbox-confirm", json={"delivery_id": queued["id"]}, headers={"X-CSRF-Token": csrf})
    assert early.status_code == 409, "아직 접수되지 않은 메일을 받았다고 할 수 없다"
    drain_worker(app, settings, fake_clock, server)

    missing = client.post("/api/admin/mail/inbox-confirm", json={"delivery_id": "no-such"}, headers={"X-CSRF-Token": csrf})
    assert missing.status_code == 404
    bad = client.post("/api/admin/mail/inbox-confirm", json={"delivery_id": queued["id"], "extra": 1},
                      headers={"X-CSRF-Token": csrf})
    assert bad.status_code == 422

    ok = client.post("/api/admin/mail/inbox-confirm", json={"delivery_id": queued["id"]}, headers={"X-CSRF-Token": csrf})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["inbox"]["delivery_id"] == queued["id"] and body["inbox"]["received"] is True
    assert body["status"]["progress"]["complete"] is True and body["status"]["progress"]["next"] is None
    assert _status(client, csrf)["inbox"]["received"] is True

    audit = db.execute(select(AuditLog).where(AuditLog.action == "mail.inbox_confirm")).scalars().all()
    assert len(audit) == 1 and audit[0].object_id == queued["id"]
    assert queued["to_email"] not in (audit[0].after_json or ""), "감사에 받는 주소가 그대로 남았다"

    not_received = client.post("/api/admin/mail/inbox-confirm", json={"delivery_id": queued["id"], "received": False},
                               headers={"X-CSRF-Token": csrf})
    assert not_received.status_code == 200
    step = not_received.json()["status"]["progress"]["next"]
    assert step["key"] == "inbox_confirmed" and step["state"] == "blocked"


def test_a_non_test_mail_is_refused_and_scope_is_enforced(client, login_as, app, settings, fake_clock, make_user):
    from app.mail.service import queue_mail

    csrf = login_as("system_admin")
    configure_smtp(app)
    server = FakeServer()
    other = make_user(email="colleague@goodmit.co.kr", role="user")
    with app.state.session_factory() as s:
        row = queue_mail(s, kind="invite", to_email=other.email, subject="초대", recipient_user_id=other.id,
                         params={"user_id": other.id}, now=fake_clock.now())
        s.commit()
        invite_id = row.id
    drain_worker(app, settings, fake_clock, server)
    refused = client.post("/api/admin/mail/inbox-confirm", json={"delivery_id": invite_id}, headers={"X-CSRF-Token": csrf})
    assert refused.status_code == 422, "시험 메일만 기록한다"

    csrf_user = login_as("user", email="colleague@goodmit.co.kr")
    assert client.post("/api/admin/mail/inbox-confirm", json={"delivery_id": invite_id},
                       headers={"X-CSRF-Token": csrf_user}).status_code == 403
