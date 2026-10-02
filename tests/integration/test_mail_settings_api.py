"""메일 설정 전용 API (계획 M1, D-545 · D-548).

못박는 것:
  * 설정을 읽고 쓰는 것은 시스템 관리자(`SYSTEM_CONFIGURE`)뿐이다. 전역 · 부서 관리자 · 운영자 · 감사자는 PUT 이 403 이고 상태는 읽는다.
  * 모르는 칸(옛 `password_ref` 포함)은 422 다. 비밀 칸 이름은 사람이 고르지 않는다.
  * 비밀번호는 같은 저장에 실려 고정 칸에 쓰이고, 응답 · 감사 어디에도 값이 없다.
  * 저장하면 보낼 수 있는 설정일 때만 연결 확인을 저절로 시작한다.
  * 범용 설정 API 는 `smtp` 의 저장 · 미리 검증 · 되돌리기를 시스템 관리자라도 거절한다(메일 화면에서 바꾼다).
"""

from __future__ import annotations

import json

import pytest

from app.audit.models import AuditLog
from tests.integration.test_password_reset import configure_smtp

pytestmark = pytest.mark.integration

GOOD = {
    "enabled": True, "host": "smtp.internal", "port": 587, "security": "starttls",
    "from_address": "noreply@example.com", "from_name": "ClovirAssist", "username": "",
    "timeout_seconds": 20, "tls_verify": True, "ca_pem": "",
}
SECRET = "settings-api-password-5521"


def _dept_admin(db, make_user):
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department
    from app.users.models import ADMIN_SCOPE_DEPT

    dept = Department(name="메일 설정 부서", org_id=DEFAULT_ORG_ID)
    db.add(dept)
    db.commit()
    user = make_user(email="mail-settings-dept@goodmit.co.kr", role="admin", display_name="부서 관리자")
    user.department_id = dept.id
    user.membership_kind = "department"
    user.admin_scope = ADMIN_SCOPE_DEPT
    user.scope_dept_id = dept.id
    db.commit()
    return user


@pytest.mark.parametrize("role", ["admin", "operator", "auditor"])
def test_only_a_system_admin_writes_the_mail_settings(client, login_as, role):
    csrf = login_as(role)
    h = {"X-CSRF-Token": csrf}
    assert client.get("/api/admin/mail/status", headers=h).status_code == 200, "상태는 콘솔 역할이 모두 읽는다"
    assert client.get("/api/admin/mail/settings", headers=h).status_code == 403
    assert client.put("/api/admin/mail/settings", json=GOOD, headers=h).status_code == 403


def test_a_department_admin_cannot_write_either(client, db, login_as, make_user):
    _dept_admin(db, make_user)
    csrf = login_as("admin", email="mail-settings-dept@goodmit.co.kr")
    assert client.put("/api/admin/mail/settings", json=GOOD, headers={"X-CSRF-Token": csrf}).status_code == 403


def test_unknown_fields_and_a_secret_name_are_refused(client, login_as):
    h = {"X-CSRF-Token": login_as("system_admin")}
    for extra in ({"password_ref": "ai.openai.api_key"}, {"relay": {}}, {"smtp_password": "x"}):
        r = client.put("/api/admin/mail/settings", json={**GOOD, **extra}, headers=h)
        assert r.status_code == 422, (extra, r.text)
    r = client.put("/api/admin/mail/settings", json={**GOOD, "host": "smtp://bad host"}, headers=h)
    assert r.status_code == 422, r.text


def test_saving_writes_the_password_in_the_same_save_and_starts_a_check(client, app, db, settings, login_as):
    h = {"X-CSRF-Token": login_as("system_admin")}
    r = client.put("/api/admin/mail/settings", json={**GOOD, "username": "mailer", "password": SECRET}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["settings"]["host"] == "smtp.internal"
    assert body["password"]["stored"] is True
    assert body["verify"] and body["verify"]["job_id"], "보낼 수 있는 설정인데 연결 확인을 시작하지 않았다"
    assert (settings.secrets_dir / "smtp.password").read_text(encoding="utf-8") == SECRET
    # 값은 응답에도 감사에도 없다.
    assert SECRET not in r.text
    for row in db.query(AuditLog).all():
        assert SECRET not in (row.after_json or "") and SECRET not in (row.before_json or "")
    actions = {row.action for row in db.query(AuditLog).all()}
    assert {"secret.write", "mail.settings.update"} <= actions


def test_no_check_starts_while_the_setting_cannot_send(client, login_as):
    h = {"X-CSRF-Token": login_as("system_admin")}
    r = client.put("/api/admin/mail/settings", json={**GOOD, "enabled": False}, headers=h)
    assert r.status_code == 200 and r.json()["verify"] is None
    # 로그인 계정이 있는데 비밀번호가 없다 - 보낼 수 없다.
    r = client.put("/api/admin/mail/settings", json={**GOOD, "username": "mailer"}, headers=h)
    assert r.status_code == 200 and r.json()["verify"] is None
    assert r.json()["health"]["state"] == "unconfigured"


def test_the_ca_text_is_shortened_in_the_audit(client, app, db, login_as):
    from tests.unit.test_mail_transport import TEST_CA

    h = {"X-CSRF-Token": login_as("system_admin")}
    r = client.put("/api/admin/mail/settings", json={**GOOD, "ca_pem": TEST_CA}, headers=h)
    assert r.status_code == 200, r.text
    row = db.query(AuditLog).filter(AuditLog.action == "mail.settings.update").one()
    after = json.loads(row.after_json)
    assert after["ca_pem"]["length"] == len(TEST_CA.strip()) and "BEGIN CERTIFICATE" not in row.after_json


def test_the_generic_settings_api_refuses_smtp_even_for_a_system_admin(client, app, login_as):
    configure_smtp(app)
    h = {"X-CSRF-Token": login_as("system_admin")}
    for method, path, body in (
        ("put", "/api/admin/settings/smtp", {"value": GOOD}),
        ("post", "/api/admin/settings/smtp/dry-run", {"value": GOOD}),
        ("post", "/api/admin/settings/smtp/rollback", {"version": 1}),
    ):
        r = getattr(client, method)(path, json=body, headers=h)
        assert r.status_code == 422 and "메일 화면에서 바꿉니다" in r.text, (path, r.text)


def test_the_status_says_what_the_screen_needs(client, app, login_as):
    configure_smtp(app)
    body = client.get("/api/admin/mail/status", headers={"X-CSRF-Token": login_as("system_admin")}).json()
    assert body["capabilities"] == {"can_configure": True, "can_operate": True}
    assert body["backlog"]["window_days"] == 7
    assert body["summary"]["host"] == "smtp.internal" and "password" in body["summary"]
    assert "password_ref" not in json.dumps(body)
    body = client.get("/api/admin/mail/status", headers={"X-CSRF-Token": login_as("operator")}).json()
    assert body["capabilities"]["can_configure"] is False
