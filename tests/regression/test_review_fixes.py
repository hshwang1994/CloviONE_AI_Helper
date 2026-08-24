"""qa-contract-change: 러너 롤백 승인 게이트 시험이 그 화면과 함께 사라졌다 — 같은 규칙(민감 필드 변경은 승인 대상)은 연동 쪽 시험 둘이 그대로 지고 있고 test_review2_fixes 도 같은 것을 본다. 스케줄 실행 취소 시험은 대상만 system 으로 바꿨다(지키는 것은 「잡을 취소하면 실행 행이 terminal 이 된다」이지 대상 종류가 아니다)."""

"""Regression tests for defects found by the §32 review loop (iteration 1)."""

import pytest

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.regression


# 주소는 **런타임 허용 목록(config/allowed-services.json)에 있는 호스트**여야 한다. 예전에는
# 여기가 api.notion.com 이었는데, S14 가 그 호스트를 목록에서 뺐다(D-284). 목록 밖 주소로는
# 연동을 만들 수 없으므로(400), 그대로 두면 아래 시험들이 **행이 하나도 없는 세계**를 훑는다.

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


def test_integration_secret_change_gated(client, login_as, settings):
    """#2: integration secret_ref change is approval-gated for non-sysadmin."""
    (settings.secrets_dir / "int-sec").write_text("v", encoding="utf-8")
    sys_csrf = login_as("system_admin", email="int-owner@goodmit.co.kr")
    integ = client.post(
        "/api/admin/integrations",
        json={"name": "gated-int", "provider_type": "http_service",
              "base_url": "https://api.anthropic.com"},
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
    with app.state.session_factory() as s:
        # S11 이후 스케줄 대상은 `system` 하나다. 이 시험이 지키는 것은 대상 종류가 아니라
        # 「잡을 취소하면 실행 행이 terminal 이 된다」이므로 대상만 바꾼다.
        sched = Schedule(name="wedge-sched", schedule_type="cron", cron_expression="0 * * * *",
                         timezone="UTC", target_type="system", target_ref="noop", enabled=True)
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
