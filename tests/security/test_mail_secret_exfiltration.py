"""메일 설정으로 다른 비밀을 빼낼 수 없다 (D-545).

## 무엇이 뚫려 있었나

`smtp.password_ref` 는 아무 비밀 이름이나 받았고, `smtp` 키는 시스템 관리자 전용이 아니었다. 그래서 시스템 관리자가
아닌 전역 관리자가 두 길로 진짜 비밀을 자기 서버로 빼낼 수 있었다.

  (a) `password_ref` 를 `ai.openai.api_key` 같은 다른 비밀 칸으로, 서버 주소를 자기 서버로 바꾸고 「연결 확인」을
      누른다 → 워커가 그 비밀을 비밀번호로 그 서버에 로그인한다.
  (b) 서버 주소만 자기 서버로 바꾸고 기본 칸 그대로 「연결 확인」 → 워커가 시스템 관리자가 넣은 SMTP 비밀번호로
      그 서버에 로그인한다.

## 이 파일이 못박는 것

- 시스템 관리자가 아닌 관리자는 `smtp` 를 바꾸지도, 미리 검증하지도, 되돌리지도 못한다(403, 값 그대로).
- 시스템 관리자도 `password_ref` 에 이름을 적을 수 없고(422), 모르는 항목을 넣을 수 없다(422).
- DB 를 억지로 옛 모양(`password_ref` = AI 키 칸 + 남의 서버)으로 바꿔도, 연결 확인과 시험 메일이 로그인에 쓰는 값은
  언제나 고정 칸 `smtp.password` 다 - 다른 비밀(SENTINEL)은 어떤 길로도 나가지 않는다.
- 상태 응답에는 비밀 칸 이름도 값도 없다.
반례: 시스템 관리자는 그대로 설정을 바꿀 수 있다.
"""

from __future__ import annotations

import json

import pytest

from tests.integration.test_password_reset import configure_smtp, drain_worker

pytestmark = pytest.mark.security

PASSWORD = "Str0ng-Passw0rd!"
SENTINEL = "SENTINEL-OPENAI-KEY-MUST-NEVER-LEAVE-7731"
REAL_SMTP_PASSWORD = "real-smtp-password-1234"


class _RecordingSmtp:
    """`smtplib.SMTP` 자리에 끼우는 가짜 서버. 로그인에 쓰인 비밀번호를 모두 적는다."""

    logins: list[tuple[str, str, str]] = []

    def __init__(self, host, port, timeout=None, **_kw):
        self.host = host

    def ehlo(self, *_a):
        return (250, b"ok")

    def starttls(self, **_kw):
        return (220, b"ready")

    def login(self, user, password):
        _RecordingSmtp.logins.append((self.host, user, password))
        return (235, b"ok")

    def noop(self):
        return (250, b"ok")

    def send_message(self, message):
        return {}

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture()
def recording_smtp(monkeypatch):
    _RecordingSmtp.logins = []
    monkeypatch.setattr("app.mail.transport.smtplib.SMTP", _RecordingSmtp)
    return _RecordingSmtp


@pytest.fixture()
def planted(settings):
    """다른 비밀 칸에 진짜처럼 보이는 값을 심고, 고정 칸에는 진짜 SMTP 비밀번호를 둔다."""
    (settings.secrets_dir / "ai.openai.api_key").write_text(SENTINEL, encoding="utf-8")
    (settings.secrets_dir / "smtp.password").write_text(REAL_SMTP_PASSWORD, encoding="utf-8")
    return settings


def _login(client, make_user, email, role):
    make_user(email=email, role=role, password=PASSWORD)
    r = client.post("/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def _smtp_value(app) -> dict:
    from app.settings.models import AppSetting

    with app.state.session_factory() as db:
        row = db.get(AppSetting, "smtp")
        if row is None:
            return {}
        raw = row.value_json
        return json.loads(raw) if isinstance(raw, str) else raw


ATTACK = {
    "enabled": True, "host": "attacker.example", "port": 587, "security": "starttls",
    "from_address": "noreply@example.com", "from_name": "ClovirAssist", "username": "mailer",
    "timeout_seconds": 10,
}


def test_a_global_admin_cannot_touch_the_smtp_setting(client, app, make_user, planted):
    configure_smtp(app, username="mailer")
    before = _smtp_value(app)
    h = _login(client, make_user, "exfil-ga@goodmit.co.kr", "admin")
    for body in (ATTACK, {**ATTACK, "password_ref": "ai.openai.api_key"}):
        r = client.put("/api/admin/settings/smtp", json={"value": body}, headers=h)
        assert r.status_code == 403, r.text
        r = client.post("/api/admin/settings/smtp/dry-run", json={"value": body}, headers=h)
        assert r.status_code == 403, r.text
    r = client.post("/api/admin/settings/smtp/rollback", json={"version": 1}, headers=h)
    assert r.status_code == 403, r.text
    assert _smtp_value(app) == before, "막았다면서 값이 바뀌었다"


def test_even_a_system_admin_cannot_name_another_secret(client, app, make_user, planted):
    h = _login(client, make_user, "exfil-sa@goodmit.co.kr", "system_admin")
    r = client.put("/api/admin/settings/smtp", json={"value": {**ATTACK, "password_ref": "ai.openai.api_key"}}, headers=h)
    assert r.status_code == 422, r.text
    r = client.put("/api/admin/settings/smtp", json={"value": {**ATTACK, "relay_secret": "x"}}, headers=h)
    assert r.status_code == 422, r.text
    # 반례: 이름 없는 정상 설정은 시스템 관리자가 그대로 저장한다.
    ok = {**ATTACK, "host": "smtp.internal"}
    r = client.put("/api/admin/settings/smtp", json={"value": ok}, headers=h)
    assert r.status_code == 200, r.text
    assert "password_ref" not in _smtp_value(app)


def test_a_tampered_row_still_logs_in_with_the_fixed_slot_only(
    client, app, make_user, planted, settings, fake_clock, recording_smtp,
):
    """옛 모양으로 DB 를 억지로 바꿔도 다른 비밀은 로그인에 쓰이지 않는다(연결 확인 · 시험 메일 둘 다)."""
    from app.mail.transport import SmtpTransport
    from app.settings.models import AppSetting

    configure_smtp(app, username="mailer")
    with app.state.session_factory() as db:
        row = db.get(AppSetting, "smtp")
        row.value_json = json.dumps({**ATTACK, "password_ref": "ai.openai.api_key"})
        db.commit()
    with app.state.session_factory() as db:
        app.state.settings_cache.load(db)

    h = _login(client, make_user, "exfil-sa2@goodmit.co.kr", "system_admin")
    assert client.post("/api/admin/mail/verify", headers=h).status_code == 200
    assert client.post("/api/admin/mail/test", headers=h).status_code == 200
    drain_worker(app, settings, fake_clock, SmtpTransport())

    passwords = [password for _host, _user, password in recording_smtp.logins]
    assert passwords, "연결 확인과 시험 메일이 로그인까지 가지 않았다 - 시험이 아무것도 재지 않았다"
    assert SENTINEL not in passwords, "다른 비밀 칸의 값으로 로그인했다"
    assert set(passwords) == {REAL_SMTP_PASSWORD}


def test_the_status_carries_no_secret_name_or_value(client, app, make_user, planted):
    configure_smtp(app, username="mailer")
    h = _login(client, make_user, "exfil-sa3@goodmit.co.kr", "system_admin")
    text = client.get("/api/admin/mail/status", headers=h).text
    for leaked in (SENTINEL, REAL_SMTP_PASSWORD, "ai.openai.api_key", "password_ref"):
        assert leaked not in text, f"상태 응답에 {leaked!r} 가 있다"
