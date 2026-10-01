"""메일 큐 — 한 통을 보고, 다시 보내고, 취소한다 (계획 3.3, D-509).

못박는 것:
  * 한 통의 상세가 잡의 다음 시도 시각을 준다(시험 메일을 기다리는 화면이 읽는다).
  * 다시 보내기는 실패 · 설정 없음 · 취소로 끝난 메일만 되고, 재설정과 시험 메일은 409 다.
  * 취소는 기다리는 메일만 되고, 잡도 함께 취소된다. 잡 화면에서 잡을 취소해도 메일 행이 끝난다.
  * 워커가 죽어 회수된 잡이 시도를 다 쓰면 메일 행도 `failed` 로 끝난다(`queued` 로 남지 않는다).
  * 설정 전에 쌓인 초대 메일은 사람이 누를 때만, 최근 7일 것만 다시 나간다.
  * 보존 정리는 다시 보내는 중인 메일을 지우지 않는다.
  * 쓰기는 전역 관리 범위만 한다(운영자 403, 부서 범위 관리자 403).
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.audit.models import AuditLog
from app.jobs.models import Job
from app.mail.models import (
    MAIL_CANCELLED,
    MAIL_FAILED,
    MAIL_QUEUED,
    MAIL_RETRYING,
    MAIL_SENT,
    MAIL_UNCONFIGURED,
    MailDelivery,
)
from app.mail.service import queue_mail
from tests.integration.test_password_reset import FakeSmtp, configure_smtp, drain_worker

pytestmark = pytest.mark.integration


def _hdr(csrf):
    return {"X-CSRF-Token": csrf}


def _queue(app, kind="invite", email="someone@goodmit.co.kr", **extra):
    with app.state.session_factory() as db:
        row = queue_mail(db, kind=kind, to_email=email, subject=f"{kind} 메일", params=extra.pop("params", {}),
                         recipient_user_id=extra.pop("recipient_user_id", None), now=app.state.clock.now(), **extra)
        db.commit()
        return row.id


def _row(app, delivery_id):
    with app.state.session_factory() as db:
        row = db.get(MailDelivery, delivery_id)
        db.expunge(row)
        return row


def _set_status(app, delivery_id, status):
    with app.state.session_factory() as db:
        db.get(MailDelivery, delivery_id).status = status
        db.commit()


def test_the_detail_carries_the_next_attempt(client, app, settings, fake_clock, login_as, make_user):
    configure_smtp(app)
    make_user("wait@goodmit.co.kr")
    client.post("/forgot-password", json={"email": "wait@goodmit.co.kr"})
    drain_worker(app, settings, fake_clock, FakeSmtp(fail=True))
    csrf = login_as("system_admin")
    with app.state.session_factory() as db:
        delivery_id = db.query(MailDelivery).one().id
    body = client.get(f"/api/admin/mail/deliveries/{delivery_id}", headers=_hdr(csrf)).json()["delivery"]
    assert body["status"] == MAIL_RETRYING
    assert body["job"]["status"] == "queued"
    assert body["job"]["next_attempt_at"], "다음 시도 시각이 없다"
    assert body["cancellable"] is True and body["resendable"] is False


def test_resend_takes_only_finished_failures_and_not_resets_or_tests(client, app, login_as):
    configure_smtp(app)
    csrf = login_as("system_admin")
    invite = _queue(app, "invite")
    reset = _queue(app, "password_reset", params={"user_id": "x"})
    _set_status(app, invite, MAIL_FAILED)
    _set_status(app, reset, MAIL_FAILED)

    r = client.post(f"/api/admin/mail/deliveries/{reset}/resend", headers=_hdr(csrf))
    assert r.status_code == 409, "재설정 메일을 다시 보내면 오래된 요청이 되살아난다"

    before_job = _row(app, invite).job_id
    r = client.post(f"/api/admin/mail/deliveries/{invite}/resend", headers=_hdr(csrf))
    assert r.status_code == 200, r.text
    row = _row(app, invite)
    assert row.status == MAIL_QUEUED and row.job_id and row.job_id != before_job
    r = client.post(f"/api/admin/mail/deliveries/{invite}/resend", headers=_hdr(csrf))
    assert r.status_code == 409, "대기 중인 메일을 또 큐에 넣었다"
    with app.state.session_factory() as db:
        assert db.query(AuditLog).filter(AuditLog.action == "mail.resend").count() == 1


def test_cancel_stops_a_waiting_mail_and_its_job(client, app, settings, fake_clock, login_as):
    configure_smtp(app)
    csrf = login_as("system_admin")
    delivery_id = _queue(app, "invite")
    r = client.post(f"/api/admin/mail/deliveries/{delivery_id}/cancel", headers=_hdr(csrf))
    assert r.status_code == 200, r.text
    row = _row(app, delivery_id)
    assert row.status == MAIL_CANCELLED and row.skip_reason == "cancelled_by_operator"
    with app.state.session_factory() as db:
        assert db.get(Job, row.job_id).status == "cancelled"
    sender = FakeSmtp()
    drain_worker(app, settings, fake_clock, sender)
    assert sender.sent == [], "취소한 메일이 나갔다"
    r = client.post(f"/api/admin/mail/deliveries/{delivery_id}/cancel", headers=_hdr(csrf))
    assert r.status_code == 409


def test_cancelling_the_job_from_the_job_queue_ends_the_mail_too(client, app, login_as):
    configure_smtp(app)
    csrf = login_as("system_admin")
    delivery_id = _queue(app, "invite")
    job_id = _row(app, delivery_id).job_id
    r = client.post(f"/api/admin/jobs/{job_id}/cancel", headers=_hdr(csrf))
    assert r.status_code == 200, r.text
    assert _row(app, delivery_id).status == MAIL_CANCELLED, "잡은 취소됐는데 메일은 영원히 대기 중이다"


def test_a_row_cancelled_after_the_claim_is_not_sent(app, settings, fake_clock):
    configure_smtp(app)
    delivery_id = _queue(app, "invite")
    _set_status(app, delivery_id, MAIL_CANCELLED)
    sender = FakeSmtp()
    drain_worker(app, settings, fake_clock, sender)
    assert sender.sent == []
    assert _row(app, delivery_id).status == MAIL_CANCELLED


def test_a_recovered_zombie_that_used_every_attempt_ends_the_mail(app, settings, fake_clock):
    from app.core.secret_refs import FileSecretReferenceProvider
    from app.jobs.worker import Worker, WorkerContext
    from app.worker_main import build_handlers

    configure_smtp(app)
    delivery_id = _queue(app, "test")  # 한 번만 보내는 종류다
    with app.state.session_factory() as db:
        job = db.get(Job, db.get(MailDelivery, delivery_id).job_id)
        job.status = "running"
        job.attempt_count = job.max_attempts
        job.started_at = fake_clock.now() - timedelta(hours=3)
        db.commit()
    ctx = WorkerContext(settings=settings, clock=fake_clock, extras={
        "mail_transport": FakeSmtp(),
        "secret_provider": FileSecretReferenceProvider(settings.secrets_dir),
    })
    Worker(app.state.session_factory, fake_clock, build_handlers(), ctx).sweep()
    row = _row(app, delivery_id)
    assert row.status == MAIL_FAILED, "워커가 죽은 뒤 메일 행이 대기 중으로 남았다"


def test_unconfigured_invites_go_out_only_when_asked_and_only_recent(client, app, login_as):
    csrf = login_as("system_admin")
    configure_smtp(app, enabled=False)
    fresh = _queue(app, "invite", email="fresh@goodmit.co.kr")
    old = _queue(app, "invite", email="old@goodmit.co.kr")
    reset = _queue(app, "password_reset", email="reset@goodmit.co.kr", params={"user_id": "x"})
    with app.state.session_factory() as db:
        db.get(MailDelivery, old).created_at = app.state.clock.now() - timedelta(days=8)
        db.commit()
    assert _row(app, fresh).status == MAIL_UNCONFIGURED

    r = client.post("/api/admin/mail/resend-unconfigured", headers=_hdr(csrf))
    assert r.status_code == 409, "설정이 없는데 다시 보내려 했다"

    configure_smtp(app)
    status = client.get("/api/admin/mail/status", headers=_hdr(csrf)).json()
    assert status["pending_unconfigured_count"] == 1
    r = client.post("/api/admin/mail/resend-unconfigured", headers=_hdr(csrf))
    assert r.status_code == 200 and r.json()["queued"] == 1, r.text
    assert _row(app, fresh).status == MAIL_QUEUED
    assert _row(app, old).status == MAIL_UNCONFIGURED, "7일 넘은 초대를 뒤늦게 보냈다"
    assert _row(app, reset).status == MAIL_UNCONFIGURED, "재설정 메일을 뒤늦게 보냈다"


def test_retention_never_deletes_a_mail_that_is_still_retrying(app, db):
    from app.core.retention import run_retention

    now = app.state.clock.now()
    old = now - timedelta(days=400)
    for status in (MAIL_RETRYING, MAIL_CANCELLED, MAIL_SENT):
        db.add(MailDelivery(kind="invite", to_email="x@goodmit.co.kr", subject=status, status=status,
                            params_json="{}", created_at=old, updated_at=old))
    db.commit()
    run_retention(db, now=now, settings_cache=app.state.settings_cache)
    db.commit()
    assert [r.status for r in db.query(MailDelivery).all()] == [MAIL_RETRYING]


@pytest.mark.parametrize("path", ["resend", "cancel"])
def test_only_a_global_admin_can_touch_a_mail(client, app, db, login_as, make_user, path):
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department
    from app.users.models import ADMIN_SCOPE_DEPT

    configure_smtp(app)
    delivery_id = _queue(app, "invite")
    if path == "resend":
        _set_status(app, delivery_id, MAIL_FAILED)

    csrf = login_as("operator")
    assert client.post(f"/api/admin/mail/deliveries/{delivery_id}/{path}", headers=_hdr(csrf)).status_code == 403

    dept = Department(name="메일 부서", org_id=DEFAULT_ORG_ID)
    db.add(dept)
    db.commit()
    scoped = make_user(email="mail-scoped@goodmit.co.kr", role="admin", display_name="부서 관리자")
    scoped.department_id = dept.id
    scoped.membership_kind = "department"
    scoped.admin_scope = ADMIN_SCOPE_DEPT
    scoped.scope_dept_id = dept.id
    db.commit()
    csrf = login_as("admin", email="mail-scoped@goodmit.co.kr")
    assert client.post(f"/api/admin/mail/deliveries/{delivery_id}/{path}", headers=_hdr(csrf)).status_code == 403
    assert client.post("/api/admin/mail/resend-unconfigured", headers=_hdr(csrf)).status_code == 403
