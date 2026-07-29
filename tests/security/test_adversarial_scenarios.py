"""Adversarial scenarios from spec §32.8 walked item by item."""

import pytest

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.security


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


def test_admin_invalid_runner_url_rejected(client, login_as):
    # "관리자가 잘못된 Runner URL을 넣으면?" → allowlist rejects at save time.
    csrf = login_as("admin")
    r = client.post(
        "/api/admin/runners",
        json={"name": "bad", "base_url": "http://169.254.169.254/latest"},
        headers=_headers(csrf),
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "url_not_allowed"


def test_user_putting_another_id_in_url_is_blocked(app, make_user):
    # "사용자가 다른 사람 ID를 URL에 넣으면?" → ownership check (covered by IDOR too).
    from fastapi.testclient import TestClient

    make_user("victim-c@goodmit.co.kr")
    make_user("thief-c@goodmit.co.kr")
    with TestClient(app, raise_server_exceptions=False) as victim:
        victim.post("/login", json={"email": "victim-c@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD})
        vcsrf = victim.get("/api/me").json()["csrf_token"]
        conv = victim.post("/api/conversations", json={}, headers=_headers(vcsrf)).json()["conversation"]
    with TestClient(app, raise_server_exceptions=False) as thief:
        thief.post("/login", json={"email": "thief-c@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD})
        assert thief.get(f"/api/conversations/{conv['id']}/messages").status_code == 403


def test_schedule_double_fire_prevented(app, login_as, client, fake_clock):
    # "Schedule이 두 번 실행되면?" → UNIQUE idempotency key.
    from app.schedules.models import Schedule, ScheduleRun
    from app.schedules.scheduler import create_run_and_enqueue

    csrf = login_as("system_admin")
    wf = client.post(
        "/api/admin/workflows",
        json={"name": "dbl", "webhook_url": "http://127.0.0.1:5678/webhook/dbl"},
        headers=_headers(csrf),
    ).json()["workflow"]
    with app.state.session_factory() as db:
        sched = Schedule(
            name="중복방지", schedule_type="cron", cron_expression="0 * * * *",
            timezone="UTC", target_type="workflow", target_ref=wf["id"],
            enabled=True,
        )
        db.add(sched); db.commit()
        when = fake_clock.now()
        a = create_run_and_enqueue(db, sched, scheduled_at=when, now=when)
        b = create_run_and_enqueue(db, sched, scheduled_at=when, now=when)
        db.commit()
        assert a is not None and b is None
        assert db.query(ScheduleRun).filter(ScheduleRun.schedule_id == sched.id).count() == 1


def test_temp_password_never_logged(client, login_as, db):
    # "임시 비밀번호가 로그에 남으면?" → audit rows never contain it.
    csrf = login_as("admin")
    resp = client.post(
        "/api/admin/users",
        json={"email": "temp-pw@goodmit.co.kr", "display_name": "임시"},
        headers=_headers(csrf),
    ).json()
    temp = resp["temp_password"]
    from app.audit.models import AuditLog

    for row in db.query(AuditLog).all():
        assert temp not in ((row.before_json or "") + (row.after_json or ""))


def test_last_system_admin_cannot_be_removed(client, login_as, db):
    # "마지막 system_admin을 제거하려 하면?"
    csrf = login_as("system_admin")
    from app.users.models import User

    me = db.query(User).filter(User.role == "system_admin").one()
    assert client.post(f"/api/admin/users/{me.id}/disable", headers=_headers(csrf)).status_code == 409


def test_browser_refresh_does_not_duplicate_ticket(client, login_as):
    # "Browser를 새로고침하면 중복 Ticket이 생성되는가?" → client_message_id idempotency.
    csrf = login_as("user")
    conv = client.post("/api/conversations", json={}, headers=_headers(csrf)).json()["conversation"]
    mid = "refresh0123456789abcdef01234567"
    for _ in range(3):  # simulate repeated submits of the same message id
        client.post(
            f"/api/conversations/{conv['id']}/messages",
            json={"content": "새 티켓 만들어줘", "client_message_id": mid},
            headers=_headers(csrf),
        )
    msgs = client.get(f"/api/conversations/{conv['id']}/messages").json()["items"]
    assert len([m for m in msgs if m["role"] == "user"]) == 1


def test_runner_bad_json_response_handled(app, login_as, client, fake_http, fake_clock, settings):
    # "Runner가 잘못된 JSON을 보내면?"
    from app.runners.provider_http import RunnerHttpProvider, RunnerUnavailableError
    from app.runners.schemas import RunnerConfig
    from app.runners.service import create_runner

    with app.state.session_factory() as db:
        runner = create_runner(
            db, RunnerConfig(name="badjson", base_url="http://127.0.0.1:8787", enabled=True),
            allowlists=app.state.allowlists, created_by=None,
        )
        runner.enabled = True
        db.commit()
        rid = runner.id
    fake_http.on_invalid_json("http://127.0.0.1:8787")
    provider = RunnerHttpProvider(app.state.outbound_client)
    with app.state.session_factory() as db:
        from app.runners.models import Runner

        runner = db.get(Runner, rid)
        with pytest.raises(RunnerUnavailableError):
            provider.invoke(db, runner, {"x": 1}, now=fake_clock.now())
