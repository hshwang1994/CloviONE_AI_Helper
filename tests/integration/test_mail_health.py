"""메일 건강 상태 · 연결 확인 · 복구 재큐 · 발송 기록 (계획 3.3 · M2, D-512 · D-546).

qa-contract-change: 상태가 넷에서 다섯이 됐다(D-546) — 꺼진 설치는 「설정 덜 됨」이 아니라 「사용 안 함」이다. 그래서 첫 단언은
`disabled` 이고, 켰는데 채우지 않은 설정이 `unconfigured` 다. 지문에 비밀번호 파일의 표지가 들어가고, 복구 재큐는 「같은 지문의 발송
실패 → 정상」이 아니라 「지금 지문으로 정상이 아니던 상태 → 성공」에서 돈다. 창은 최대 나이 설정을 따른다.

못박는 것:
  * 상태는 다섯이다 — 사용 안 함 · 설정 덜 됨 · 확인 전 · 정상 · 발송 실패. 설정이나 비밀번호를 바꾸면 옛 기록은 「확인 전」이다.
  * 연결 확인은 잡이고 메일을 보내지 않으며, 결과가 상태에 적힌다. 받는 사람 거부는 상태를 바꾸지 않는다.
  * 「발송 실패」에서 「정상」이 되면 최근 7일의 서버 탓 실패 중 **아직 의미가 있는 것만** 다시 보낸다.
  * 보내기 직전에 의미를 잃은 메일(이미 처리된 승인 요청 등)은 보내지 않고 까닭과 함께 끝낸다.
  * 발송 기록 목록은 상태 · 종류 · 검색 · 기간 · 정렬 · 페이지를 받는다. 쓰기는 전역 관리 범위만 한다.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.audit.models import AuditLog
from app.mail.models import (
    FAILURE_AUTH,
    FAILURE_RECIPIENT,
    MAIL_FAILED,
    MAIL_SENT,
    MAIL_SUPERSEDED,
    MailDelivery,
)
from app.mail.transport import MailTransportError
from tests.integration.test_password_reset import FakeSmtp, configure_smtp, drain_worker

pytestmark = pytest.mark.integration


class FakeServer(FakeSmtp):
    """보내기와 연결 확인을 둘 다 흉내 낸다. `fail` 에 예외를 주면 둘 다 그 예외로 실패한다."""

    def __init__(self, fail_with=None):
        super().__init__()
        self.fail_with = fail_with
        self.verified = 0

    def send(self, config, secret_provider, *, to_email, subject, body, html=None):
        if self.fail_with is not None:
            raise self.fail_with
        self.sent.append({"to": to_email, "subject": subject, "body": body, "html": html})
        return "<test@example.com>"

    def verify(self, config, secret_provider, *, probe_recipient=None):
        self.verified += 1
        self.probe_recipient = probe_recipient
        if self.fail_with is not None:
            raise self.fail_with
        return {"ok": True, "stages": [
            {"key": "dns", "state": "ok", "detail": None}, {"key": "connect", "state": "ok", "detail": None},
            {"key": "tls", "state": "ok", "detail": None}, {"key": "auth", "state": "skipped", "detail": None},
            {"key": "sender", "state": "ok", "detail": None},
            {"key": "recipient", "state": "ok" if probe_recipient else "skipped", "detail": None},
        ]}


AUTH_FAIL = MailTransportError("SMTPAuthenticationError: (535, b'bad')", kind=FAILURE_AUTH, permanent=True, stage="auth")
RECIPIENT_FAIL = MailTransportError("SMTPRecipientsRefused", kind=FAILURE_RECIPIENT, permanent=True, stage="send")


def _health(client, csrf):
    return client.get("/api/admin/mail/status", headers={"X-CSRF-Token": csrf}).json()["health"]


def _verify(client, csrf, app, settings, fake_clock, server):
    r = client.post("/api/admin/mail/verify", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    drain_worker(app, settings, fake_clock, server)
    return client.get(f"/api/admin/mail/verify/{r.json()['job_id']}", headers={"X-CSRF-Token": csrf}).json()


def _invite(app, email, *, user_id="u-x", created=None):
    from app.mail.service import queue_mail

    with app.state.session_factory() as db:
        row = queue_mail(db, kind="invite", to_email=email, subject="초대", params={"user_id": user_id},
                         recipient_user_id=None, now=app.state.clock.now())
        if created is not None:
            row.created_at = created
        db.commit()
        return row.id


def _row(app, delivery_id):
    with app.state.session_factory() as db:
        row = db.get(MailDelivery, delivery_id)
        db.expunge(row)
        return row


# ── 상태 넷 ───────────────────────────────────────────────────────────────────


def test_the_five_states(client, app, settings, fake_clock, login_as):
    csrf = login_as("system_admin")
    assert _health(client, csrf)["state"] == "disabled", "꺼 둔 설치를 고장처럼 말했다"
    # 켰는데 덜 채웠다 - 로그인 계정은 있는데 비밀번호가 저장되지 않았다(빈 주소는 저장 단계가 이미 거절한다).
    configure_smtp(app, username="mailer")
    health = _health(client, csrf)
    assert health["state"] == "unconfigured" and health["problems"], "켰는데 덜 채운 설정의 문제를 말하지 않았다"
    configure_smtp(app)
    assert _health(client, csrf)["state"] == "unverified", "값이 있다는 것만으로 정상이라고 했다"

    server = FakeServer()
    body = _verify(client, csrf, app, settings, fake_clock, server)
    assert body["result"]["ok"] is True and body["pending"] is False
    assert body["health"]["state"] == "ok"
    # 봉투 시험의 받는 사람은 확인을 누른 사람이고, 지난 단계가 상태 면에 줄로 선다(D-546).
    assert server.probe_recipient and server.probe_recipient.endswith("@goodmit.co.kr")
    stages = {row["key"]: (row["label"], row["state"]) for row in body["health"]["stages"]}
    assert stages["dns"] == ("DNS 조회", "ok") and stages["recipient"][1] == "ok"

    body = _verify(client, csrf, app, settings, fake_clock, FakeServer(fail_with=AUTH_FAIL))
    assert body["result"]["ok"] is False
    assert "로그인" in body["result"]["message"], body
    health = _health(client, csrf)
    assert health["state"] == "failing" and health["failure_kind"] == FAILURE_AUTH and health["stage"] == "auth"

    configure_smtp(app, host="smtp.other")
    assert _health(client, csrf)["state"] == "unverified", "설정을 바꿨는데 옛 기록이 지금 설정을 말했다"


def test_verify_never_sends_a_mail(client, app, settings, fake_clock, login_as):
    csrf = login_as("system_admin")
    configure_smtp(app)
    server = FakeServer()
    _verify(client, csrf, app, settings, fake_clock, server)
    assert server.verified == 1 and server.sent == []


def test_a_recipient_rejection_does_not_change_the_state(client, app, settings, fake_clock, login_as, make_user):
    csrf = login_as("system_admin")
    configure_smtp(app)
    _verify(client, csrf, app, settings, fake_clock, FakeServer())
    user = make_user("nobody-there@goodmit.co.kr")
    _invite(app, "nobody-there@goodmit.co.kr", user_id=user.id)
    drain_worker(app, settings, fake_clock, FakeServer(fail_with=RECIPIENT_FAIL))
    assert _health(client, csrf)["state"] == "ok", "받는 사람 주소 하나가 틀렸다고 메일 서버가 고장이라고 했다"


# ── 복구 재큐 ─────────────────────────────────────────────────────────────────


def test_recovery_requeues_only_what_still_means_something(client, app, db, settings, fake_clock, login_as, make_user):
    csrf = login_as("system_admin")
    configure_smtp(app)
    waiting = make_user("waiting@goodmit.co.kr")
    joined = make_user("joined@goodmit.co.kr")
    typo = make_user("typo@goodmit.co.kr")
    old = make_user("old@goodmit.co.kr")
    ids = {
        "waiting": _invite(app, "waiting@goodmit.co.kr", user_id=waiting.id),
        "joined": _invite(app, "joined@goodmit.co.kr", user_id=joined.id),
        "old": _invite(app, "old@goodmit.co.kr", user_id=old.id),
    }
    # 서버가 로그인을 거부하는 동안 셋이 실패한다.
    drain_worker(app, settings, fake_clock, FakeServer(fail_with=AUTH_FAIL))
    ids["typo"] = _invite(app, "typo@goodmit.co.kr", user_id=typo.id)
    drain_worker(app, settings, fake_clock, FakeServer(fail_with=RECIPIENT_FAIL))
    assert _health(client, csrf)["state"] == "failing"
    with app.state.session_factory() as s:
        s.get(MailDelivery, ids["old"]).created_at = fake_clock.now() - timedelta(days=9)
        from app.users.models import User

        s.get(User, joined.id).last_login_at = fake_clock.now()
        s.commit()

    body = _verify(client, csrf, app, settings, fake_clock, FakeServer())
    assert body["health"]["state"] == "ok"
    # 다시 큐에 들어간 초대는 같은 워커 차례에 실제로 나간다.
    assert _row(app, ids["waiting"]).status == MAIL_SENT, "복구됐는데 밀린 초대를 다시 안 보냈다"
    joined_row = _row(app, ids["joined"])
    assert (joined_row.status, joined_row.skip_reason) == (MAIL_SUPERSEDED, "already_active")
    assert _row(app, ids["typo"]).status == MAIL_FAILED, "받는 사람 거부를 다시 보냈다"
    assert _row(app, ids["old"]).status == MAIL_FAILED, "7일 넘은 메일을 뒤늦게 보냈다"
    audit = db.query(AuditLog).filter(AuditLog.action == "mail.requeue_on_recovery").one()
    assert '"requeued": 1' in audit.after_json and '"superseded": 1' in audit.after_json


def test_an_approval_already_decided_is_not_mailed(app, settings, fake_clock, make_user):
    from app.mail.service import queue_mail

    configure_smtp(app)
    # 받는 사람은 아직 결재할 수 있는 관리자다(받는 사람 재검사를 지난다) - 이 시험은 그 다음의 의미 판정을 본다.
    boss = make_user("boss@goodmit.co.kr", role="admin")
    with app.state.session_factory() as db:
        row = queue_mail(db, kind="approval_requested", to_email="boss@goodmit.co.kr", subject="승인 요청",
                         recipient_user_id=boss.id, params={"approval_id": "gone-approval"},
                         now=app.state.clock.now())
        db.commit()
        delivery_id = row.id
    server = FakeServer()
    drain_worker(app, settings, fake_clock, server)
    row = _row(app, delivery_id)
    assert server.sent == []
    assert (row.status, row.skip_reason) == (MAIL_SUPERSEDED, "approval_gone")


def test_every_mailable_kind_has_a_relevance_rule():
    from app.mail.relevance import ALWAYS_RELEVANT_KINDS, RULES
    from app.mail.renderers import MAIL_KINDS

    missing = sorted(set(MAIL_KINDS) - set(RULES) - ALWAYS_RELEVANT_KINDS)
    assert missing == [], f"보내기 직전 판정이 없는 종류: {missing}"


# ── 발송 기록 목록 ────────────────────────────────────────────────────────────


def test_the_delivery_list_filters_searches_and_pages(client, app, settings, fake_clock, login_as, make_user):
    csrf = login_as("system_admin")
    configure_smtp(app)
    for n in range(3):
        user = make_user(f"list{n}@goodmit.co.kr")
        _invite(app, f"list{n}@goodmit.co.kr", user_id=user.id)
    drain_worker(app, settings, fake_clock, FakeServer())
    h = {"X-CSRF-Token": csrf}
    page = client.get("/api/admin/mail/deliveries", params={"page_size": 2}, headers=h).json()
    assert page["total"] == 3 and len(page["items"]) == 2
    sent = client.get("/api/admin/mail/deliveries", params={"status": MAIL_SENT, "kind": "invite"}, headers=h).json()
    assert sent["total"] == 3 and sent["items"][0]["message_id"] == "<test@example.com>"
    found = client.get("/api/admin/mail/deliveries", params={"q": "LIST1@"}, headers=h).json()
    assert [i["to_email"] for i in found["items"]] == ["list1@goodmit.co.kr"], "검색이 대소문자를 접지 않는다"
    ordered = client.get("/api/admin/mail/deliveries", params={"sort": "to_email", "order": "asc"}, headers=h).json()
    assert [i["to_email"] for i in ordered["items"]] == sorted(i["to_email"] for i in ordered["items"])
    today = fake_clock.now().date().isoformat()
    assert client.get("/api/admin/mail/deliveries", params={"since": "2099-01-01"}, headers=h).json()["total"] == 0
    assert client.get("/api/admin/mail/deliveries", params={"until": "2000-01-01"}, headers=h).json()["total"] == 0
    assert client.get("/api/admin/mail/deliveries", params={"since": today}, headers=h).status_code == 200
    assert client.get("/api/admin/mail/deliveries", params={"status": "lost"}, headers=h).status_code == 422


def test_an_auditor_reads_and_only_a_global_admin_verifies(client, app, db, login_as, make_user):
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department
    from app.users.models import ADMIN_SCOPE_DEPT

    configure_smtp(app)
    login_as("auditor")
    assert client.get("/api/admin/mail/deliveries").status_code == 200
    csrf = login_as("operator")
    assert client.post("/api/admin/mail/verify", headers={"X-CSRF-Token": csrf}).status_code == 403

    dept = Department(name="메일 확인 부서", org_id=DEFAULT_ORG_ID)
    db.add(dept)
    db.commit()
    scoped = make_user(email="verify-scoped@goodmit.co.kr", role="admin", display_name="부서 관리자")
    scoped.department_id = dept.id
    scoped.membership_kind = "department"
    scoped.admin_scope = ADMIN_SCOPE_DEPT
    scoped.scope_dept_id = dept.id
    db.commit()
    csrf = login_as("admin", email="verify-scoped@goodmit.co.kr")
    assert client.post("/api/admin/mail/verify", headers={"X-CSRF-Token": csrf}).status_code == 403


# ── 지문의 비밀 표지 · 복구 · 수동 재발송 · 창 (D-546) ──────────────────────────


def _write_password(settings, value: str) -> None:
    from app.core.secret_refs import FileSecretReferenceProvider

    FileSecretReferenceProvider(settings.secrets_dir).write("smtp.password", value)


def test_changing_only_the_password_returns_to_unverified(client, app, settings, fake_clock, login_as):
    """비밀번호 파일만 바꿔도 옛 「정상」이 지금 비밀번호를 말하지 않는다(지문에 표지가 들어간다)."""
    import os
    import time

    csrf = login_as("system_admin")
    configure_smtp(app, username="mailer")
    _write_password(settings, "first-password")
    _verify(client, csrf, app, settings, fake_clock, FakeServer())
    assert _health(client, csrf)["state"] == "ok"
    _write_password(settings, "second-password-longer")
    path = os.path.join(str(settings.secrets_dir), "smtp.password")
    later = time.time() + 5
    os.utime(path, (later, later))
    assert _health(client, csrf)["state"] == "unverified", "비밀번호를 바꿨는데 옛 확인이 정상이라고 했다"


def test_fixing_the_setting_and_verifying_requeues_failed_mail(client, app, settings, fake_clock, login_as, make_user):
    """실패 → 호스트를 고침 → 확인 성공이면 복구다(예전에는 같은 지문의 「발송 실패 → 정상」만 복구로 봐서 고친 뒤에도
    실패한 메일이 다시 나가지 않았다). 옛 `failed/config` 행도 다시 보낸다."""
    from app.mail.models import FAILURE_CONFIG

    csrf = login_as("system_admin")
    configure_smtp(app, host="smtp.wrong")
    waiting = make_user("fixme@goodmit.co.kr")
    first = _invite(app, "fixme@goodmit.co.kr", user_id=waiting.id)
    drain_worker(app, settings, fake_clock, FakeServer(fail_with=AUTH_FAIL))
    assert _row(app, first).status == MAIL_FAILED
    legacy_user = make_user("legacy-config@goodmit.co.kr")
    legacy = _invite(app, "legacy-config@goodmit.co.kr", user_id=legacy_user.id)
    with app.state.session_factory() as db:
        row = db.get(MailDelivery, legacy)
        row.status, row.failure_kind = MAIL_FAILED, FAILURE_CONFIG
        db.commit()
    configure_smtp(app, host="smtp.right")
    assert _health(client, csrf)["state"] == "unverified"
    body = _verify(client, csrf, app, settings, fake_clock, FakeServer())
    assert body["health"]["state"] == "ok"
    assert _row(app, first).status == MAIL_SENT, "설정을 고치고 확인했는데 실패한 메일이 다시 나가지 않았다"
    assert _row(app, legacy).status == MAIL_SENT, "옛 설정 실패 행을 다시 보내지 않았다"


def test_a_manual_resend_of_an_old_mail_really_goes_out(client, app, settings, fake_clock, login_as, make_user):
    """열흘 된 실패 메일을 사람이 다시 보내면 나이를 그 시각부터 센다 - 예전에는 나이 규칙이 곧바로 버렸다."""
    csrf = login_as("system_admin")
    configure_smtp(app)
    old_user = make_user("ten-days@goodmit.co.kr")
    delivery_id = _invite(app, "ten-days@goodmit.co.kr", user_id=old_user.id,
                          created=fake_clock.now() - timedelta(days=10))
    with app.state.session_factory() as db:
        row = db.get(MailDelivery, delivery_id)
        row.status, row.failure_kind = MAIL_FAILED, FAILURE_AUTH
        db.commit()
    r = client.post(f"/api/admin/mail/deliveries/{delivery_id}/resend", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    drain_worker(app, settings, fake_clock, FakeServer())
    row = _row(app, delivery_id)
    assert row.status == MAIL_SENT, (row.status, row.skip_reason)
    assert '"manual_resend_at"' in row.params_json


def test_the_backlog_window_follows_the_max_age_setting(client, app, settings, fake_clock, login_as, make_user):
    """설정 전에 쌓인 메일의 창은 관리자가 정한 최대 나이다 - 7일 고정이 아니다."""
    from app.mail.models import MAIL_UNCONFIGURED
    from app.settings.service import apply_setting

    csrf = login_as("system_admin")
    configure_smtp(app, enabled=False)
    user = make_user("window@goodmit.co.kr")
    delivery_id = _invite(app, "window@goodmit.co.kr", user_id=user.id,
                          created=fake_clock.now() - timedelta(days=10))
    assert _row(app, delivery_id).status == MAIL_UNCONFIGURED
    status = client.get("/api/admin/mail/status", headers={"X-CSRF-Token": csrf}).json()
    assert status["backlog"] == {"count": 0, "window_days": 7}
    with app.state.session_factory() as db:
        apply_setting(db, app.state.settings_cache, key="mail_notification_max_age_days", value=14,
                      updated_by=None, now=fake_clock.now())
        db.commit()
    status = client.get("/api/admin/mail/status", headers={"X-CSRF-Token": csrf}).json()
    assert status["backlog"] == {"count": 1, "window_days": 14}


def test_a_send_time_configuration_problem_is_unconfigured_not_failed(app, settings, fake_clock, make_user):
    """큐에 넣은 뒤 발송을 껐으면 그 메일은 「설정이 끝나지 않아 보내지 못함」이다 - 쌓인 메일로 다시 보낼 수 있다."""
    from app.jobs.models import Job
    from app.mail.models import MAIL_UNCONFIGURED

    configure_smtp(app)
    user = make_user("turned-off@goodmit.co.kr")
    delivery_id = _invite(app, "turned-off@goodmit.co.kr", user_id=user.id)
    configure_smtp(app, enabled=False)
    server = FakeServer()
    drain_worker(app, settings, fake_clock, server)
    row = _row(app, delivery_id)
    assert server.sent == []
    assert row.status == MAIL_UNCONFIGURED and row.failure_kind is None and row.last_error
    with app.state.session_factory() as db:
        assert db.get(Job, row.job_id).status != "failed", "설정 문제를 잡 실패로 적었다"
