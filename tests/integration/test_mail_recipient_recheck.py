"""보내기 직전에 받는 사람을 다시 본다 — 모든 메일 종류, 판정이 터지면 보내지 않는다 (D-547).

못박는 것:
  * 강등된 관리자에게 백업 실패 메일이 가지 않는다(`no_longer_admin`). 다른 관리자는 그대로 받는다.
  * 결재 권한을 잃은 사람에게 승인 요청 메일이 가지 않는다(`no_longer_decider`).
  * 보관된 사람에게 초대 · 비밀번호 재설정이 가지 않는다(`archived`). 요청 뒤 계정 주소가 바뀌면 예전 주소로 재설정
    메일이 가지 않는다(`address_changed`).
  * 수동 재발송과 복구 재큐도 같은 자리를 지난다 - 다시 큐에 넣어도 보내기 직전에 또 멈춘다.
  * 판정이 터지거나 판정이 없는 종류는 보내지 않는다(`check_failed`).
"""

from __future__ import annotations

import pytest

from app.mail.models import FAILURE_CONNECT, MAIL_CANCELLED, MAIL_FAILED, MAIL_SENT, MailDelivery
from tests.integration.test_password_reset import FakeSmtp, configure_smtp, drain_worker

pytestmark = pytest.mark.integration


def _rows(app) -> list[MailDelivery]:
    with app.state.session_factory() as db:
        rows = list(db.query(MailDelivery).order_by(MailDelivery.created_at, MailDelivery.to_email))
        db.expunge_all()
    return rows


def _set_user(app, user_id, **fields):
    from app.users.models import User

    with app.state.session_factory() as db:
        user = db.get(User, user_id)
        for key, value in fields.items():
            setattr(user, key, value)
        db.commit()


def test_a_demoted_admin_gets_no_backup_failure_mail(app, settings, fake_clock, make_user):
    from app.mail.service import queue_mail_to_admins

    configure_smtp(app)
    stays = make_user("stays-admin@goodmit.co.kr", role="admin")
    demoted = make_user("demoted-admin@goodmit.co.kr", role="admin")
    with app.state.session_factory() as db:
        queue_mail_to_admins(db, kind="backup_failed", subject="백업 실패", params={"reason": "x"},
                             now=app.state.clock.now())
        db.commit()
    _set_user(app, demoted.id, role="user")
    server = FakeSmtp()
    drain_worker(app, settings, fake_clock, server)
    by_to = {r.to_email: r for r in _rows(app)}
    assert (by_to[demoted.email].status, by_to[demoted.email].skip_reason) == (MAIL_CANCELLED, "no_longer_admin")
    assert by_to[stays.email].status == MAIL_SENT
    assert [m["to"] for m in server.sent] == [stays.email]


def test_someone_who_can_no_longer_decide_gets_no_approval_mail(app, settings, fake_clock, make_user):
    from app.mail.service import queue_mail_to_users

    configure_smtp(app)
    decider = make_user("decider@goodmit.co.kr", role="admin")
    with app.state.session_factory() as db:
        # 승인 id 를 싣기 전의 옛 모양이다 - 그래도 결재할 역할은 지금 있어야 한다.
        queue_mail_to_users(db, [decider.id], kind="approval_requested", subject="승인 요청",
                            params={"request_type": "role_change"}, now=app.state.clock.now())
        db.commit()
    _set_user(app, decider.id, role="user")
    server = FakeSmtp()
    drain_worker(app, settings, fake_clock, server)
    (row,) = _rows(app)
    assert (row.status, row.skip_reason) == (MAIL_CANCELLED, "no_longer_decider")
    assert server.sent == []


def test_archived_people_get_no_invite_or_reset(client, app, settings, fake_clock, make_user):
    from datetime import timedelta

    from app.mail.service import queue_mail

    configure_smtp(app)
    invited = make_user("archived-invite@goodmit.co.kr")
    resetter = make_user("archived-reset@goodmit.co.kr")
    with app.state.session_factory() as db:
        queue_mail(db, kind="invite", to_email=invited.email, recipient_user_id=invited.id, subject="초대",
                   params={"user_id": invited.id}, now=app.state.clock.now())
        db.commit()
    assert client.post("/forgot-password", json={"email": resetter.email}).status_code in (200, 202)
    archived_at = app.state.clock.now() - timedelta(minutes=1)
    _set_user(app, invited.id, archived_at=archived_at)
    _set_user(app, resetter.id, archived_at=archived_at)
    server = FakeSmtp()
    drain_worker(app, settings, fake_clock, server)
    reasons = {(r.kind, r.status, r.skip_reason) for r in _rows(app)}
    assert ("invite", MAIL_CANCELLED, "archived") in reasons
    assert ("password_reset", MAIL_CANCELLED, "archived") in reasons
    assert server.sent == []


def test_a_reset_mail_does_not_follow_an_old_address(client, app, settings, fake_clock, make_user):
    configure_smtp(app)
    user = make_user("old-address@goodmit.co.kr")
    assert client.post("/forgot-password", json={"email": user.email}).status_code in (200, 202)
    _set_user(app, user.id, email="new-address@goodmit.co.kr")
    server = FakeSmtp()
    drain_worker(app, settings, fake_clock, server)
    (row,) = _rows(app)
    assert (row.status, row.skip_reason) == (MAIL_CANCELLED, "address_changed")
    assert server.sent == []


def test_manual_resend_and_recovery_requeue_are_rechecked(client, app, settings, fake_clock, make_user, login_as):
    from app.mail.health import on_recovered
    from app.mail.service import queue_mail, queue_mail_to_admins

    configure_smtp(app)
    invited = make_user("resend-archived@goodmit.co.kr")
    admin = make_user("recover-admin@goodmit.co.kr", role="admin")
    with app.state.session_factory() as db:
        invite = queue_mail(db, kind="invite", to_email=invited.email, recipient_user_id=invited.id, subject="초대",
                            params={"user_id": invited.id}, now=app.state.clock.now())
        db.commit()
        invite_id = invite.id
    _set_user(app, invited.id, archived_at=app.state.clock.now())
    drain_worker(app, settings, fake_clock, FakeSmtp())
    csrf = login_as("system_admin")
    r = client.post(f"/api/admin/mail/deliveries/{invite_id}/resend", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    server = FakeSmtp()
    drain_worker(app, settings, fake_clock, server)
    with app.state.session_factory() as db:
        assert db.get(MailDelivery, invite_id).status == MAIL_CANCELLED, "수동 재발송이 재검사를 건너뛰었다"
    assert server.sent == []

    # 복구 재큐: 서버 탓으로 실패한 백업 메일이 복구 때 다시 큐에 들어가도, 그 사이 강등된 사람에게는 가지 않는다.
    with app.state.session_factory() as db:
        rows = queue_mail_to_admins(db, kind="backup_failed", subject="백업 실패", params={"reason": "x"},
                                    now=app.state.clock.now())
        backup_id = next(row.id for row in rows if row.recipient_user_id == admin.id)
        db.commit()
    drain_worker(app, settings, fake_clock, FakeSmtp())
    with app.state.session_factory() as db:
        # 서버 탓으로 끝난 실패처럼 만든다(큐의 첫 잡은 이미 끝났다).
        row = db.get(MailDelivery, backup_id)
        row.status, row.failure_kind = MAIL_FAILED, FAILURE_CONNECT
        db.commit()
    _set_user(app, admin.id, role="user")
    with app.state.session_factory() as db:
        on_recovered(db, now=app.state.clock.now())
        db.commit()
    server = FakeSmtp()
    drain_worker(app, settings, fake_clock, server)
    with app.state.session_factory() as db:
        row = db.get(MailDelivery, backup_id)
        assert (row.status, row.skip_reason) == (MAIL_CANCELLED, "no_longer_admin"), "복구 재큐가 재검사를 건너뛰었다"
    assert admin.email not in [m["to"] for m in server.sent]


def test_a_crashing_check_or_an_unknown_kind_is_not_sent(app, settings, fake_clock, make_user, monkeypatch):
    from app.mail import recipients
    from app.mail.service import queue_mail

    configure_smtp(app)
    user = make_user("crash-check@goodmit.co.kr")

    def boom(*_a, **_kw):
        raise RuntimeError("판정 중 오류")

    monkeypatch.setitem(recipients.RECIPIENT_RULES, "invite", boom)
    with app.state.session_factory() as db:
        queue_mail(db, kind="invite", to_email=user.email, recipient_user_id=user.id, subject="초대",
                   params={"user_id": user.id}, now=app.state.clock.now())
        queue_mail(db, kind="mystery", to_email=user.email, recipient_user_id=user.id, subject="?",
                   params={}, now=app.state.clock.now())
        db.commit()
    server = FakeSmtp()
    drain_worker(app, settings, fake_clock, server)
    assert {(r.kind, r.status, r.skip_reason) for r in _rows(app)} == {
        ("invite", MAIL_CANCELLED, "check_failed"), ("mystery", MAIL_CANCELLED, "check_failed"),
    }
    assert server.sent == []
