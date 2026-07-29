"""Regression tests for defects found by the §32 review loop (iteration 1)."""

import pytest

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.regression


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


def test_session_policy_setting_actually_shortens_idle(client, login_as, fake_clock):
    """H1: session_policy was a placebo. Now tightening idle timeout takes
    effect on new sessions."""
    csrf = login_as("system_admin")
    client.put(
        "/api/admin/settings/session_policy",
        json={"value": {"idle_timeout_seconds": 60, "absolute_timeout_seconds": 3600}},
        headers=_headers(csrf),
    )
    # A brand-new session must now die after 61s idle, not the env default 1800s.
    client.post("/login", json={"email": "system-admin@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD})
    assert client.get("/api/me").status_code == 200
    fake_clock.advance(61)
    assert client.get("/api/me").status_code == 401


def test_removed_settings_not_present(client, login_as):
    """H1: dead knobs removed from the registry."""
    login_as("admin")
    settings = client.get("/api/admin/settings").json()["settings"]
    for dead in ["page_size", "timezone", "app_base_url", "default_timeout_seconds",
                 "retry_policy", "schedule_misfire_policy"]:
        assert dead not in settings


def test_xff_leftmost_not_trusted_for_rate_limit(client, make_user):
    """H2: get_client_ip must not trust the spoofable leftmost X-Forwarded-For.
    From a non-proxy peer the header is ignored entirely."""
    from app.core.deps import client_ip_from_request

    class FakeReq:
        def __init__(self, host, headers):
            self.client = type("C", (), {"host": host})()
            self.headers = headers
            self.app = client.app

    # Peer is not the trusted proxy → header ignored, real peer used.
    req = FakeReq("203.0.113.9", {"X-Forwarded-For": "1.2.3.4, 5.6.7.8"})
    assert client_ip_from_request(req) == "203.0.113.9"
    # Peer IS the trusted proxy → rightmost XFF (proxy-appended), not leftmost.
    req2 = FakeReq("127.0.0.1", {"X-Forwarded-For": "1.2.3.4, 9.9.9.9"})
    assert client_ip_from_request(req2) == "9.9.9.9"
    # X-Real-IP preferred when present.
    req3 = FakeReq("127.0.0.1", {"X-Real-IP": "8.8.8.8", "X-Forwarded-For": "1.2.3.4"})
    assert client_ip_from_request(req3) == "8.8.8.8"


def test_admin_cannot_create_system_admin(client, login_as):
    """H5: creating admin+ accounts requires system_admin."""
    csrf = login_as("admin")
    r = client.post(
        "/api/admin/users",
        json={"email": "sneak-admin@goodmit.co.kr", "display_name": "몰래관리자", "role": "admin"},
        headers=_headers(csrf),
    )
    assert r.status_code == 403


def test_system_admin_can_create_admin(client, login_as):
    csrf = login_as("system_admin")
    r = client.post(
        "/api/admin/users",
        json={"email": "legit-admin@goodmit.co.kr", "display_name": "정식관리자", "role": "admin"},
        headers=_headers(csrf),
    )
    assert r.status_code == 201


def test_runner_rollback_sensitive_change_gated(client, login_as):
    """#2: rollback that changes base_url/secret_ref goes through the approval gate."""
    sys_csrf = login_as("system_admin", email="runner-rb-owner@goodmit.co.kr")
    runner = client.post(
        "/api/admin/runners",
        json={"name": "rb-runner", "base_url": "http://127.0.0.1:8787"},
        headers=_headers(sys_csrf),
    ).json()["runner"]
    # system_admin changes the URL (creates version 2 with a different base_url).
    client.patch(
        f"/api/admin/runners/{runner['id']}",
        json={"base_url": "http://127.0.0.1:8788"},
        headers=_headers(sys_csrf),
    )
    # A plain admin rolling back to v1 (different base_url) must be gated.
    admin_csrf = login_as("admin", email="runner-rb-admin@goodmit.co.kr")
    r = client.post(
        f"/api/admin/runners/{runner['id']}/rollback",
        json={"version": 1},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 202
    assert r.json()["status"] == "approval_pending"


def test_integration_secret_change_gated(client, login_as, settings):
    """#2: integration secret_ref change is approval-gated for non-sysadmin."""
    (settings.secrets_dir / "int-sec").write_text("v", encoding="utf-8")
    sys_csrf = login_as("system_admin", email="int-owner@goodmit.co.kr")
    integ = client.post(
        "/api/admin/integrations",
        json={"name": "gated-int", "provider_type": "http_service",
              "base_url": "http://127.0.0.1:8787"},
        headers=_headers(sys_csrf),
    ).json()["integration"]
    admin_csrf = login_as("admin", email="int-editor@goodmit.co.kr")
    r = client.patch(
        f"/api/admin/integrations/{integ['id']}",
        json={"secret_ref": "int-sec"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 202
    assert r.json()["status"] == "approval_pending"


def test_cancelling_schedule_run_job_terminalizes_run(client, login_as, app, fake_clock, db):
    """H4: cancelling a schedule_run job must not wedge the schedule."""
    from app.jobs import repository
    from app.schedules.models import Schedule, ScheduleRun
    from app.schedules.scheduler import create_run_and_enqueue

    csrf = login_as("system_admin")
    wf = client.post(
        "/api/admin/workflows",
        json={"name": "wedge", "webhook_url": "http://127.0.0.1:5678/webhook/w"},
        headers=_headers(csrf),
    ).json()["workflow"]
    with app.state.session_factory() as s:
        sched = Schedule(name="wedge-sched", schedule_type="cron", cron_expression="0 * * * *",
                         timezone="UTC", target_type="workflow", target_ref=wf["id"], enabled=True)
        s.add(sched); s.commit()
        run = create_run_and_enqueue(s, sched, scheduled_at=fake_clock.now(), now=fake_clock.now())
        s.commit()
        run_id, sched_id = run.id, sched.id
        job = repository.get_by_idempotency_key(s, f"schedrun:{run.idempotency_key}")
        job_id = job.id

    r = client.post(f"/api/admin/jobs/{job_id}/cancel", headers=_headers(csrf))
    assert r.status_code == 200
    with app.state.session_factory() as s:
        assert s.get(ScheduleRun, run_id).status == "skipped"  # terminal, not stuck 'queued'


def test_deactivating_user_disables_their_schedules(client, login_as, make_user, app):
    """§11.5: a deactivated user's schedules stop firing."""
    from app.schedules.models import Schedule

    owner = make_user("sched-owner@goodmit.co.kr", role="operator")
    csrf = login_as("system_admin")
    with app.state.session_factory() as s:
        sched = Schedule(name="owned", schedule_type="cron", cron_expression="0 * * * *",
                         timezone="UTC", target_type="system", target_ref="noop",
                         owner_user_id=owner.id, enabled=True,
                         next_run_at=None)
        from datetime import datetime
        sched.next_run_at = datetime(2026, 7, 15)
        s.add(sched); s.commit()
        sched_id = sched.id

    client.post(f"/api/admin/users/{owner.id}/disable", headers=_headers(csrf))
    with app.state.session_factory() as s:
        row = s.get(Schedule, sched_id)
        assert row.enabled is False
        assert row.next_run_at is None
