"""시험 메일의 받는 주소 (계획 M1, D-554).

못박는 것:
  * 받는 주소를 비우면 내 계정 주소다. 다른 주소는 메일 설정 권한(`SYSTEM_CONFIGURE`)이 있어야 하고, 없으면 403 이다.
  * 주소는 하나다 - 잘못된 모양 · 여러 주소 · 줄바꿈은 422 다.
  * 사람당 10분에 5통, 설치 전체 1시간에 20통 - 넘으면 429 다.
  * 감사에는 가린 주소와 도메인만 남는다. 내용은 고정 틀이라 요청 값이 본문에 섞이지 않는다.
  * 계정이 아닌 주소로 간 시험 메일은 받는 사람 축이 비어 전역 관리자만 본다.
"""

from __future__ import annotations

import pytest

from app.audit.models import AuditLog
from app.mail.models import MailDelivery
from tests.integration.test_password_reset import FakeSmtp, configure_smtp, drain_worker

pytestmark = pytest.mark.integration

OTHER = "outside.tester@example.org"


def _send(client, csrf, to=None):
    body = {} if to is None else {"to": to}
    return client.post("/api/admin/mail/test", json=body, headers={"X-CSRF-Token": csrf})


def test_without_an_address_it_goes_to_my_account(client, app, login_as):
    configure_smtp(app)
    # 전역 관리자(메일 설정 권한은 없다)는 자기 주소로 보낸다.
    csrf = login_as("admin")
    r = _send(client, csrf)
    assert r.status_code == 200, r.text
    assert r.json()["delivery"]["to_email"].endswith("@goodmit.co.kr")
    assert "접수했습니다" in r.json()["sentence"] and "도착" not in r.json()["sentence"]


def test_another_address_needs_the_mail_settings_permission(client, app, db, login_as):
    configure_smtp(app)
    csrf = login_as("admin")
    r = _send(client, csrf, OTHER)
    assert r.status_code == 403 and "시스템 관리자 권한" in r.text, r.text
    csrf = login_as("system_admin")
    r = _send(client, csrf, OTHER)
    assert r.status_code == 200, r.text
    row = db.get(MailDelivery, r.json()["delivery"]["id"])
    assert row.to_email == OTHER and row.recipient_user_id is None


@pytest.mark.parametrize("bad", [
    "not-an-address", "a@b", "one@example.com, two@example.com", "one@example.com;two@example.com",
    "line@example.com\r\nBcc: x@example.com", "한글@example.com", "x" * 250 + "@example.com",
])
def test_a_bad_address_is_refused(client, app, login_as, bad):
    configure_smtp(app)
    assert _send(client, login_as("system_admin"), bad).status_code == 422


def test_the_audit_keeps_only_a_masked_address(client, app, db, login_as):
    configure_smtp(app)
    _send(client, login_as("system_admin"), OTHER)
    row = db.query(AuditLog).filter(AuditLog.action == "mail.test_send").one()
    assert OTHER not in (row.after_json or "")
    assert "o****r@example.org" in row.after_json and '"to_domain": "example.org"' in row.after_json


def test_the_body_is_the_fixed_template(client, app, settings, fake_clock, login_as):
    configure_smtp(app)
    csrf = login_as("system_admin")
    _send(client, csrf, OTHER)
    server = FakeSmtp()
    drain_worker(app, settings, fake_clock, server)
    assert [m["to"] for m in server.sent] == [OTHER]
    text = server.sent[0]["body"]
    assert "시험 메일입니다." in text and "smtp.internal:587" in text
    assert OTHER not in text, "요청 값이 본문에 섞였다"
    assert server.sent[0]["subject"] == "[ClovirAssist] 메일 발송 시험"


def test_the_per_person_limit(client, app, login_as):
    configure_smtp(app)
    csrf = login_as("system_admin")
    codes = [_send(client, csrf).status_code for _ in range(6)]
    assert codes[:5] == [200] * 5 and codes[5] == 429


def test_the_install_wide_limit(client, app, login_as):
    from app.core.ratelimit import RateLimiter

    configure_smtp(app)
    # 설치 전체 리미터를 작게 끼워 넣는다(스무 통을 실제로 보내지 않고 같은 길을 잰다).
    app.state.mail_test_all_ratelimiter = RateLimiter(
        capacity=2, refill_per_second=2 / 3600, clock=app.state.clock, session_factory=app.state.session_factory,
    )
    first = login_as("system_admin")
    assert _send(client, first).status_code == 200
    assert _send(client, first).status_code == 200
    r = _send(client, first)
    assert r.status_code == 429 and "설치 전체" in r.text


def test_a_mail_to_a_non_user_is_visible_only_to_global_admins(client, app, db, login_as, make_user):
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department
    from app.users.models import ADMIN_SCOPE_DEPT

    configure_smtp(app)
    _send(client, login_as("system_admin"), OTHER)
    dept = Department(name="시험 메일 부서", org_id=DEFAULT_ORG_ID)
    db.add(dept)
    db.commit()
    scoped = make_user(email="test-mail-dept@goodmit.co.kr", role="admin", display_name="부서 관리자")
    scoped.department_id = dept.id
    scoped.membership_kind = "department"
    scoped.admin_scope = ADMIN_SCOPE_DEPT
    scoped.scope_dept_id = dept.id
    db.commit()
    csrf = login_as("admin", email="test-mail-dept@goodmit.co.kr")
    listed = client.get("/api/admin/mail/deliveries", headers={"X-CSRF-Token": csrf}).json()
    assert OTHER not in [item["to_email"] for item in listed["items"]]
