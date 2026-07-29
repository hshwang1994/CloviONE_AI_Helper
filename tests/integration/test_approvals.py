"""Approval workflow (spec §20): gates, decisions, self-approval ban, expiry,
exactly-once payload replay."""

import pytest

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


@pytest.fixture()
def workflow_id(client, login_as):
    csrf = login_as("system_admin", email="boot-sysadmin@goodmit.co.kr")
    r = client.post(
        "/api/admin/workflows",
        json={
            "name": "승인 테스트 workflow",
            "webhook_url": "http://127.0.0.1:5678/webhook/approve-test",
        },
        headers=_headers(csrf),
    )
    return r.json()["workflow"]["id"]


def _make_schedule(client, csrf, workflow_id, name="승인 스케줄"):
    return client.post(
        "/api/admin/schedules",
        json={
            "name": name,
            "schedule_type": "cron",
            "cron_expression": "0 * * * *",
            "timezone": "UTC",
            "target_type": "workflow",
            "target_ref": workflow_id,
        },
        headers=_headers(csrf),
    ).json()["schedule"]


def test_system_admin_enables_schedule_directly(client, login_as, workflow_id):
    csrf = login_as("system_admin", email="direct@goodmit.co.kr")
    schedule = _make_schedule(client, csrf, workflow_id, name="직접 활성화")
    r = client.post(f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(csrf))
    assert r.status_code == 200
    assert r.json()["schedule"]["enabled"] is True


def test_admin_enable_creates_pending_approval(client, login_as, workflow_id, db):
    csrf = login_as("admin", email="requester@goodmit.co.kr")
    schedule = _make_schedule(client, csrf, workflow_id, name="승인 대기 활성화")
    r = client.post(f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(csrf))
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "approval_pending"
    approval_id = body["approval"]["id"]

    # 스케줄은 아직 비활성.
    detail = client.get(f"/api/admin/schedules/{schedule['id']}").json()["schedule"]
    assert detail["enabled"] is False

    # 관리자들에게 알림 발송됨.
    from app.notifications.models import Notification

    notes = db.query(Notification).filter(Notification.type == "approval_requested").all()
    assert notes


def test_self_approval_banned(client, login_as, workflow_id):
    csrf = login_as("admin", email="selfish@goodmit.co.kr")
    schedule = _make_schedule(client, csrf, workflow_id, name="자기승인 시도")
    approval = client.post(
        f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(csrf)
    ).json()["approval"]

    r = client.post(
        f"/api/admin/approvals/{approval['id']}/approve", headers=_headers(csrf)
    )
    assert r.status_code == 403


def test_other_admin_approves_and_action_applies_once(
    app, client, login_as, workflow_id, db
):
    from fastapi.testclient import TestClient

    requester_csrf = login_as("admin", email="asker@goodmit.co.kr")
    schedule = _make_schedule(client, requester_csrf, workflow_id, name="승인 후 적용")
    approval = client.post(
        f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(requester_csrf)
    ).json()["approval"]

    # 다른 admin이 승인.
    from app.users.service import create_user

    create_user(
        db, email="approver@goodmit.co.kr", display_name="승인자",
        password=DEFAULT_TEST_PASSWORD, settings=app.state.settings,
        role="admin", must_change_password=False,
    )
    db.commit()
    with TestClient(app, raise_server_exceptions=False) as approver:
        login = approver.post(
            "/login",
            json={"email": "approver@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD},
        )
        approver_csrf = login.json()["csrf_token"]
        r = approver.post(
            f"/api/admin/approvals/{approval['id']}/approve",
            json={"comment": "확인했습니다"},
            headers=_headers(approver_csrf),
        )
        assert r.status_code == 200, r.text
        assert r.json()["approval"]["status"] == "approved"

        # 실행됨: 스케줄 활성화.
        detail = approver.get(f"/api/admin/schedules/{schedule['id']}").json()["schedule"]
        assert detail["enabled"] is True
        assert detail["next_run_at"] is not None

        # 두 번째 승인 시도 → 이미 처리됨.
        r = approver.post(
            f"/api/admin/approvals/{approval['id']}/approve", headers=_headers(approver_csrf)
        )
        assert r.status_code == 409

    # 요청자에게 결정 알림.
    from app.notifications.models import Notification

    decided = db.query(Notification).filter(Notification.type == "approval_decided").all()
    assert decided


def test_reject_does_not_apply(app, client, login_as, workflow_id, db):
    from fastapi.testclient import TestClient

    requester_csrf = login_as("admin", email="rejected@goodmit.co.kr")
    schedule = _make_schedule(client, requester_csrf, workflow_id, name="거절 케이스")
    approval = client.post(
        f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(requester_csrf)
    ).json()["approval"]

    from app.users.service import create_user

    create_user(
        db, email="rejecter@goodmit.co.kr", display_name="거절자",
        password=DEFAULT_TEST_PASSWORD, settings=app.state.settings,
        role="admin", must_change_password=False,
    )
    db.commit()
    with TestClient(app, raise_server_exceptions=False) as rejecter:
        csrf = rejecter.post(
            "/login",
            json={"email": "rejecter@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD},
        ).json()["csrf_token"]
        r = rejecter.post(
            f"/api/admin/approvals/{approval['id']}/reject",
            json={"comment": "지금은 안 됩니다"},
            headers=_headers(csrf),
        )
        assert r.status_code == 200
        detail = rejecter.get(f"/api/admin/schedules/{schedule['id']}").json()["schedule"]
        assert detail["enabled"] is False


def test_expiry_sweep(db, app, client, login_as, workflow_id, fake_clock):
    csrf = login_as("admin", email="expiring@goodmit.co.kr")
    schedule = _make_schedule(client, csrf, workflow_id, name="만료 케이스")
    approval = client.post(
        f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(csrf)
    ).json()["approval"]

    from app.approvals.service import expire_pending

    fake_clock.advance(73 * 3600)  # 72h 기본 만료 초과
    count = expire_pending(db, now=fake_clock.now())
    db.commit()
    assert count == 1

    row = client.get(f"/api/admin/approvals/{approval['id']}")
    # 세션도 만료됐으므로 재로그인.
    relogin = client.post(
        "/login", json={"email": "expiring@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
    )
    row = client.get(f"/api/admin/approvals/{approval['id']}")
    assert row.json()["approval"]["status"] == "expired"


def test_pending_past_expiry_lists_as_expired(client, login_as, workflow_id, fake_clock):
    # Regression: a pending approval past its expiry must DISPLAY as 'expired' in
    # the list even before the background sweep persists it (it showed 'pending').
    csrf = login_as("admin", email="expdisplay@goodmit.co.kr")
    schedule = _make_schedule(client, csrf, workflow_id, name="만료 표시 테스트")
    r = client.post(f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(csrf))
    approval_id = r.json()["approval"]["id"]

    fake_clock.advance(73 * 3600)  # past the 72h expiry — no sweep run
    # The session also expired at 73h, so re-login before reading the list.
    csrf = login_as("admin", email="expdisplay@goodmit.co.kr")
    items = client.get("/api/admin/approvals", headers=_headers(csrf)).json()["items"]
    match = [a for a in items if a["id"] == approval_id][0]
    assert match["status"] == "expired"


def test_runner_endpoint_change_gated_for_admin(client, login_as):
    sys_csrf = login_as("system_admin", email="runner-owner@goodmit.co.kr")
    runner = client.post(
        "/api/admin/runners",
        json={"name": "게이트 러너", "base_url": "http://127.0.0.1:8787"},
        headers=_headers(sys_csrf),
    ).json()["runner"]

    admin_csrf = login_as("admin", email="runner-editor@goodmit.co.kr")
    r = client.patch(
        f"/api/admin/runners/{runner['id']}",
        json={"base_url": "http://127.0.0.1:8788"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 202
    assert r.json()["status"] == "approval_pending"

    # 민감하지 않은 변경(설명)은 즉시 적용.
    r = client.patch(
        f"/api/admin/runners/{runner['id']}",
        json={"description": "설명만 변경"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200


def test_role_change_to_admin_gated(client, login_as, make_user):
    target = make_user("promotee@goodmit.co.kr")
    admin_csrf = login_as("admin", email="promoter@goodmit.co.kr")
    r = client.patch(
        f"/api/admin/users/{target.id}",
        json={"role": "admin"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 202
    assert r.json()["status"] == "approval_pending"

    # operator로의 변경은 게이트 없음.
    r = client.patch(
        f"/api/admin/users/{target.id}",
        json={"role": "operator"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200
