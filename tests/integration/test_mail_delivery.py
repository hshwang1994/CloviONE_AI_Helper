"""메일 발송 경로 (9-9 P4).

이 저장소에는 메일을 보내는 코드가 **한 줄도 없었다**(`smtplib` / `EmailMessage` /
`send_mail` 전부 0건). 그래서 SMTP 설정 화면만 먼저 만들면 소비자 없는 스위치가 된다.

이 파일이 못박는 것은 셋이다.

  1. **설정이 없으면 없다고 한다.** 조용히 성공한 척하면 사용자는 오지 않을 메일을 기다린다.
     진단(`/api/admin/diagnostics/bundle`)과 관리 화면이 그 사실을 말해야 한다.
  2. **웹이 아니라 워커에서 보낸다.** SMTP 는 느릴 때 수십 초를 잡아먹는다. 웹 요청 안에서
     보내면 그 시간 동안 요청이 잡혀 있고, sync 핸들러라 스레드풀 슬롯을 통째로 문다.
  3. **실패가 남는다.** 메일 실패가 본 작업을 막지 않는 것은 이 저장소의 기존 규칙이지만
     (알림 실패와 같다), 조용히 삼키면 "왜 안 왔지" 에 아무도 답할 수 없다.
     남는 자리는 `mail_deliveries` 표다 - status/last_error/attempt_count.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from tests.integration.test_password_reset import (
    FakeSmtp,
    configure_smtp,
    drain_worker,
)

pytestmark = pytest.mark.integration

APP_DIR = pathlib.Path(__file__).resolve().parents[2] / "app"


# ── 1. 설정이 없으면 없다고 한다 ─────────────────────────────────────────────


def test_status_endpoint_says_mail_is_not_configured(client, login_as):
    csrf = login_as("admin")
    response = client.get("/api/admin/mail/status", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200, response.text
    body = response.json()["mail"]
    assert body["configured"] is False
    assert body["problems"], "설정이 왜 안 됐는지 한 줄도 말하지 않는다"


def test_status_endpoint_flips_once_configured(client, app, login_as):
    csrf = login_as("admin")
    configure_smtp(app)
    body = client.get(
        "/api/admin/mail/status", headers={"X-CSRF-Token": csrf}
    ).json()["mail"]
    assert body["configured"] is True
    assert body["problems"] == []


def test_diagnostics_bundle_carries_the_same_fact(client, login_as):
    csrf = login_as("system_admin")
    bundle = client.get(
        "/api/admin/diagnostics/bundle", headers={"X-CSRF-Token": csrf}
    ).json()
    assert "mail" in bundle, "진단 번들이 메일 상태를 말하지 않는다"
    assert bundle["mail"]["configured"] is False


def test_status_never_leaks_the_smtp_password(client, app, login_as, settings):
    secret = "SMTP-PLAINTEXT-MUST-NOT-LEAK-4471"
    (settings.secrets_dir / "smtp_password").write_text(secret, encoding="utf-8")
    csrf = login_as("system_admin")
    configure_smtp(app, username="mailer", password_ref="smtp_password")
    response = client.get("/api/admin/mail/status", headers={"X-CSRF-Token": csrf})
    assert secret not in response.text


def test_a_missing_secret_file_is_named_as_the_problem(client, app, login_as):
    csrf = login_as("admin")
    configure_smtp(app, username="mailer", password_ref="smtp_password")
    body = client.get(
        "/api/admin/mail/status", headers={"X-CSRF-Token": csrf}
    ).json()["mail"]
    assert body["configured"] is False
    assert any("smtp_password" in p for p in body["problems"])


def test_unconfigured_consumer_leaves_a_trace_instead_of_vanishing(app, make_user):
    """관리자에게 알려야 할 일이 생겼는데 메일이 없다 - 그 사실이 남아야 한다."""
    from app.mail.models import MAIL_UNCONFIGURED, MailDelivery
    from app.mail.service import queue_mail_to_admins

    make_user("boss@goodmit.co.kr", role="admin")
    with app.state.session_factory() as db:
        queue_mail_to_admins(
            db,
            kind="backup_failed",
            subject="자동 백업이 실패했습니다",
            params={"reason": "디스크 없음"},
            now=app.state.clock.now(),
        )
        db.commit()
        rows = db.query(MailDelivery).all()
        assert rows, "보낼 수 없다는 사실 자체가 아무 데도 안 남았다"
        assert all(r.status == MAIL_UNCONFIGURED for r in rows)
        assert all(r.last_error for r in rows)


# ── 2. 워커에서 보낸다 ───────────────────────────────────────────────────────


def test_only_the_transport_module_imports_smtplib():
    """웹 코드가 smtplib 를 직접 import 하면 언젠가 요청 안에서 보내게 된다.

    `import httpx` 를 단일 관문으로 묶은 것과 같은 발상이다(불변 §2 규칙 2).
    """
    offenders = []
    for path in sorted(APP_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            if any(n.split(".")[0] in ("smtplib", "email") for n in names):
                offenders.append(path.relative_to(APP_DIR.parent).as_posix())
    assert set(offenders) <= {"app/mail/transport.py"}, (
        "SMTP 를 보내는 코드가 단일 관문 밖에 있다: " + ", ".join(sorted(set(offenders)))
    )


def test_web_request_queues_and_the_worker_sends(client, app, settings, fake_clock, make_user):
    from app.jobs.models import Job
    from app.mail.models import MAIL_QUEUED, MAIL_SENT, MailDelivery

    configure_smtp(app)
    make_user("queued@goodmit.co.kr")
    transport = FakeSmtp()

    assert client.post(
        "/forgot-password", json={"email": "queued@goodmit.co.kr"}
    ).status_code == 200

    # 웹 요청은 SMTP 를 건드리지 않는다.
    assert transport.sent == []
    with app.state.session_factory() as db:
        delivery = db.query(MailDelivery).one()
        assert delivery.status == MAIL_QUEUED
        assert delivery.job_id is not None
        job = db.get(Job, delivery.job_id)
        assert job is not None and job.job_type == "mail_send"

    assert drain_worker(app, settings, fake_clock, transport) >= 1
    assert len(transport.sent) == 1
    assert transport.sent[0]["to"] == "queued@goodmit.co.kr"
    with app.state.session_factory() as db:
        assert db.query(MailDelivery).one().status == MAIL_SENT


def test_the_mail_handler_is_registered_on_the_worker():
    from app.worker_main import build_handlers

    assert "mail_send" in build_handlers(), (
        "새 큐를 만들지 말고 기존 잡 큐에 등록해야 한다"
    )


# ── 3. 실패가 남는다 ─────────────────────────────────────────────────────────


def test_a_failed_send_is_recorded_not_swallowed(client, app, settings, fake_clock, make_user):
    from app.mail.models import MAIL_FAILED, MailDelivery

    configure_smtp(app)
    make_user("doomed@goodmit.co.kr")
    client.post("/forgot-password", json={"email": "doomed@goodmit.co.kr"})

    transport = FakeSmtp(fail=True)
    drain_worker(app, settings, fake_clock, transport)

    with app.state.session_factory() as db:
        delivery = db.query(MailDelivery).one()
        assert delivery.status == MAIL_FAILED
        assert delivery.attempt_count >= 1
        assert delivery.last_error, "왜 실패했는지 아무 데도 안 남았다"


def test_a_render_failure_is_recorded_not_left_queued_forever(app, settings, fake_clock):
    """계정이 큐잉과 워커 처리 사이에 사라지면 render_body 가 발송 전에 실패한다.

    handle_mail_send 가 그 실패를 try/except 밖에서 일으키면 잡은 영구 실패로 끊기지만
    아웃박스 행은 MAIL_QUEUED 에 멈춰 영원히 '대기 중'으로 보인다 - mail_send.py 파일
    docstring 이 명시적으로 막으려는 상태다.
    """
    from app.mail.models import MAIL_FAILED, MAIL_QUEUED, MailDelivery
    from app.mail.renderers import KIND_PASSWORD_RESET
    from app.mail.service import queue_mail

    configure_smtp(app)
    with app.state.session_factory() as db:
        queue_mail(
            db,
            kind=KIND_PASSWORD_RESET,
            to_email="ghost@goodmit.co.kr",
            subject="[ClovirAssist] 비밀번호 재설정 안내",
            # 실제 계정이 없는 user_id - 큐잉 뒤 계정이 삭제/보관된 경우를 흉내낸다.
            params={"user_id": "does-not-exist"},
            now=app.state.clock.now(),
        )
        db.commit()

    drain_worker(app, settings, fake_clock, FakeSmtp())

    with app.state.session_factory() as db:
        delivery = db.query(MailDelivery).one()
        assert delivery.status != MAIL_QUEUED, (
            "렌더 실패가 아웃박스에 안 남고 MAIL_QUEUED 에 영원히 멈춰 있다"
        )
        assert delivery.status == MAIL_FAILED
        assert delivery.last_error, "왜 실패했는지 아무 데도 안 남았다"


def test_failures_surface_on_the_admin_status_screen(
    client, app, settings, fake_clock, login_as, make_user
):
    csrf = login_as("admin")
    configure_smtp(app)
    make_user("doomed2@goodmit.co.kr")
    client.post("/forgot-password", json={"email": "doomed2@goodmit.co.kr"})
    drain_worker(app, settings, fake_clock, FakeSmtp(fail=True))

    body = client.get("/api/admin/mail/status", headers={"X-CSRF-Token": csrf}).json()
    assert body["counts"]["failed"] >= 1
    assert body["recent_failures"], "실패가 화면에 안 보이면 삼킨 것과 같다"


def test_mail_failure_does_not_break_the_work_itself(app, settings, fake_clock, make_user):
    """메일이 실패해도 본 작업(백업 기록)은 남는다 - 기존 알림 규칙과 같다."""
    from app.backups.models import Backup
    from app.backups.service import run_scheduled_backup

    configure_smtp(app)
    make_user("ops@goodmit.co.kr", role="admin")

    import app.backups.service as backups_service

    def boom(*_args, **_kwargs):
        raise OSError("디스크에 공간이 없습니다")

    original = backups_service.backup_database
    backups_service.backup_database = boom
    try:
        with app.state.session_factory() as db:
            row = run_scheduled_backup(
                db, settings, {"keep": 3}, now=app.state.clock.now()
            )
            db.commit()
            assert row is not None
            assert db.query(Backup).count() == 1
    finally:
        backups_service.backup_database = original


# ── 4. 소비처가 넷 붙어 있다 ─────────────────────────────────────────────────


def test_backup_failure_sends_mail(app, settings, make_user):
    from app.mail.models import MailDelivery
    from app.mail.renderers import KIND_BACKUP_FAILED

    configure_smtp(app)
    make_user("ops2@goodmit.co.kr", role="admin")

    import app.backups.service as backups_service

    def boom(*_args, **_kwargs):
        raise OSError("디스크에 공간이 없습니다")

    original = backups_service.backup_database
    backups_service.backup_database = boom
    try:
        with app.state.session_factory() as db:
            run = backups_service.run_scheduled_backup
            run(db, settings, {"keep": 3}, now=app.state.clock.now())
            db.commit()
            kinds = [r.kind for r in db.query(MailDelivery).all()]
            assert KIND_BACKUP_FAILED in kinds, (
                "§E-6: 백업 실패가 여전히 로그로만 사라진다"
            )
    finally:
        backups_service.backup_database = original


def test_approval_request_sends_mail(app, db, make_user):
    from app.approvals.service import APPROVAL_EXECUTORS, create_approval
    from app.mail.models import MailDelivery
    from app.mail.renderers import KIND_APPROVAL_REQUESTED

    configure_smtp(app)
    make_user("approver@goodmit.co.kr", role="admin")
    requester = make_user("asker@goodmit.co.kr", role="operator")

    APPROVAL_EXECUTORS["test.request"] = lambda *a, **k: None
    try:
        create_approval(
            db,
            request_type="test.request",
            object_type="user",
            object_id=requester.id,
            requested_by=requester,
            payload={"x": 1},
            now=app.state.clock.now(),
        )
        db.commit()
        rows = [r for r in db.query(MailDelivery).all() if r.kind == KIND_APPROVAL_REQUESTED]
        assert rows
        assert "approver@goodmit.co.kr" in {r.to_email for r in rows}
    finally:
        APPROVAL_EXECUTORS.pop("test.request", None)


def test_approval_mail_reaches_delegates_not_just_admins(app, db, make_user):
    """결재하라고 권한을 준 사람이 메일을 못 받으면 위임 기능이 반쯤 장식이 된다 (X7)."""
    from datetime import timedelta

    from app.approvals.models import ApprovalDelegation
    from app.approvals.service import APPROVAL_EXECUTORS, create_approval
    from app.mail.models import MailDelivery
    from app.mail.renderers import KIND_APPROVAL_REQUESTED

    configure_smtp(app)
    make_user("boss3@goodmit.co.kr", role="admin")
    delegate = make_user("delegate@goodmit.co.kr", role="operator")
    requester = make_user("asker3@goodmit.co.kr", role="operator")

    now = app.state.clock.now()
    db.add(
        ApprovalDelegation(
            delegator_user_id=requester.id,
            delegate_user_id=delegate.id,
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=1),
        )
    )
    db.flush()

    APPROVAL_EXECUTORS["test.delegated"] = lambda *a, **k: None
    try:
        create_approval(
            db,
            request_type="test.delegated",
            object_type="user",
            object_id=requester.id,
            requested_by=requester,
            payload={"y": 2},
            now=now,
        )
        db.commit()
        recipients = {
            r.to_email
            for r in db.query(MailDelivery).all()
            if r.kind == KIND_APPROVAL_REQUESTED
        }
        assert "delegate@goodmit.co.kr" in recipients, (
            "피위임자가 메일을 못 받는다 - notify_approvers 가 이미 고친 결함을 되풀이한다"
        )
        assert "boss3@goodmit.co.kr" in recipients
    finally:
        APPROVAL_EXECUTORS.pop("test.delegated", None)


def test_new_account_gets_an_invite_mail(client, app, login_as):
    from app.mail.models import MailDelivery
    from app.mail.renderers import KIND_INVITE

    csrf = login_as("system_admin")
    configure_smtp(app)
    response = client.post(
        "/api/admin/users",
        json={"email": "invited@goodmit.co.kr", "display_name": "초대된 사람", "role": "user"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201, response.text
    assert response.json()["invite_mail"]["queued"] is True

    with app.state.session_factory() as db:
        rows = db.query(MailDelivery).filter(MailDelivery.kind == KIND_INVITE).all()
        assert [r.to_email for r in rows] == ["invited@goodmit.co.kr"]


def test_retention_cleans_the_outbox_but_never_a_queued_mail(app, db):
    """아웃박스와 토큰 표가 무한히 자라면 안 된다. 다만 **대기 중인 메일은 못 지운다.**"""
    from datetime import timedelta

    from app.core.retention import run_retention
    from app.mail.models import MAIL_QUEUED, MAIL_SENT, MailDelivery

    now = app.state.clock.now()
    old = now - timedelta(days=400)
    db.add(MailDelivery(kind="test", to_email="a@b.co", subject="옛 발송",
                        status=MAIL_SENT, params_json="{}", created_at=old, updated_at=old))
    db.add(MailDelivery(kind="test", to_email="c@d.co", subject="옛 대기",
                        status=MAIL_QUEUED, params_json="{}", created_at=old, updated_at=old))
    db.commit()

    result = run_retention(db, now=now, settings_cache=app.state.settings_cache)
    db.commit()

    assert result["mail_history"] == 1
    assert "reset_tokens" in result
    remaining = db.query(MailDelivery).all()
    assert [r.status for r in remaining] == [MAIL_QUEUED]


def test_create_user_says_when_the_invite_cannot_be_sent(client, login_as):
    """메일이 안 되는 설치에서 관리자가 '초대가 나갔겠지' 라고 믿으면 안 된다."""
    csrf = login_as("system_admin")
    response = client.post(
        "/api/admin/users",
        json={"email": "noinvite@goodmit.co.kr", "display_name": "초대 못 함", "role": "user"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201, response.text
    invite = response.json()["invite_mail"]
    assert invite["queued"] is False
    assert invite["reason"], "왜 못 보냈는지 말하지 않는다"
