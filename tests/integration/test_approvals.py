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
        password=DEFAULT_TEST_PASSWORD, settings=app.state.settings, actor_role="system_admin",
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
        password=DEFAULT_TEST_PASSWORD, settings=app.state.settings, actor_role="system_admin",
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


def test_admin_cancelling_someone_elses_request_notifies_the_requester(
    app, client, login_as, workflow_id, db
):
    """decide()·expire_pending()은 이미 요청자에게 알리는데 cancel()만 빠져 있었다 —
    admin이 남의 대기 요청을 대신 취소하면 요청자는 벨도 /notifications도 신호가 없었다."""
    from fastapi.testclient import TestClient

    requester_csrf = login_as("admin", email="cancel-target@goodmit.co.kr")
    schedule = _make_schedule(client, requester_csrf, workflow_id, name="취소 알림 케이스")
    approval = client.post(
        f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(requester_csrf)
    ).json()["approval"]

    from app.users.service import create_user

    create_user(
        db, email="canceller@goodmit.co.kr", display_name="취소자",
        password=DEFAULT_TEST_PASSWORD, settings=app.state.settings, actor_role="system_admin",
        role="admin", must_change_password=False,
    )
    db.commit()
    with TestClient(app, raise_server_exceptions=False) as canceller:
        csrf = canceller.post(
            "/login",
            json={"email": "canceller@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD},
        ).json()["csrf_token"]
        r = canceller.post(
            f"/api/admin/approvals/{approval['id']}/cancel", headers=_headers(csrf)
        )
        assert r.status_code == 200, r.text
        assert r.json()["approval"]["status"] == "cancelled"

    from app.notifications.models import Notification
    from app.users.service import get_user_by_email

    requester = get_user_by_email(db, "cancel-target@goodmit.co.kr")
    cancelled = db.query(Notification).filter(
        Notification.type == "approval_cancelled", Notification.user_id == requester.id
    ).all()
    assert cancelled, "남이 취소했는데 요청자에게 approval_cancelled 알림이 안 갔다"


def test_self_cancel_does_not_notify_self(client, login_as, workflow_id, db):
    """본인이 취소했으면 이미 알고 있다 — 자기 자신에게 알림을 만들지 않는다."""
    csrf = login_as("admin", email="self-canceller@goodmit.co.kr")
    schedule = _make_schedule(client, csrf, workflow_id, name="자기 취소 케이스")
    approval = client.post(
        f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(csrf)
    ).json()["approval"]

    r = client.post(f"/api/admin/approvals/{approval['id']}/cancel", headers=_headers(csrf))
    assert r.status_code == 200, r.text

    from app.notifications.models import Notification

    assert not db.query(Notification).filter(Notification.type == "approval_cancelled").all()


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


def test_notification_title_uses_korean_label_not_raw_request_type(
    client, login_as, workflow_id, db
):
    """APPR-02: 알림·메일 제목이 "승인 요청: user.role_change" 같은 내부 코드 상수를
    그대로 노출했다 — 요청/결정 알림 둘 다 request_type을 사람이 읽는 한국어 라벨로
    바꾼다."""
    from app.notifications.models import Notification

    csrf = login_as("admin", email="ko-title-requester@goodmit.co.kr")
    schedule = _make_schedule(client, csrf, workflow_id, name="한글 제목 확인")
    r = client.post(f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(csrf))
    assert r.status_code == 202

    requested = (
        db.query(Notification).filter(Notification.type == "approval_requested").all()
    )
    assert requested
    for n in requested:
        assert "schedule.enable" not in n.title, n.title
        assert "스케줄 활성화" in n.title, n.title


def test_list_rejects_unknown_status_instead_of_silently_returning_zero(client, login_as):
    """APPR-03: `status=all`(또는 다른 알 수 없는 값)이 조용히 0건을 주면 API를 직접
    두드리는 쪽(스크립트·연동)이 "승인이 하나도 없다"로 오해한다 — 422로 원인을 말한다.
    화면 자체는 안전하다(필터 기본값 pending, 선택지 5개 실제 상태뿐이라 'all'을 안 보낸다)."""
    csrf = login_as("admin", email="unknown-status@goodmit.co.kr")
    r = client.get("/api/admin/approvals?status=all", headers=_headers(csrf))
    assert r.status_code == 422


def test_list_accepts_all_five_known_statuses(client, login_as):
    csrf = login_as("admin", email="known-status@goodmit.co.kr")
    for status in ["pending", "approved", "rejected", "expired", "cancelled"]:
        r = client.get(f"/api/admin/approvals?status={status}", headers=_headers(csrf))
        assert r.status_code == 200, (status, r.text)


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


# ── backend-approvals-jobs 감사 #1: 중복 PENDING 승인이 향후 요청을 500으로 막지 않는다ㅡ

def test_create_approval_does_not_crash_on_preexisting_duplicate_pending_rows(
    client, login_as, workflow_id, db, fake_clock
):
    """Regression: 같은 (request_type, object_id)에 payload가 다른 pending 요청이 둘
    이상 있는 것은 의도된 정상 상태다(재요청 허용, `create_approval`의 주석 참고). 예전
    코드는 이 정상 상태에서도, 또 더블클릭 경합이 만들어 낸 우연한 중복에서도
    `scalar_one_or_none()`이 `MultipleResultsFound`를 던져 그 대상에 대한 **모든** 향후
    승인 요청을 500으로 막았다.
    """
    from app.approvals.service import create_approval
    from app.users.service import get_user_by_email

    csrf = login_as("admin", email="dupe-requester@goodmit.co.kr")
    schedule = _make_schedule(client, csrf, workflow_id, name="중복 방지 테스트")
    now = fake_clock.now()
    requester = get_user_by_email(db, "dupe-requester@goodmit.co.kr")

    payload_a = {"definition": {"cron_expression": "0 * * * *"}}
    payload_b = {"definition": {"cron_expression": "*/5 * * * *"}}

    a1 = create_approval(
        db, request_type="schedule.enable", object_type="schedule",
        object_id=schedule["id"], requested_by=requester, payload=payload_a, now=now,
    )
    b1 = create_approval(
        db, request_type="schedule.enable", object_type="schedule",
        object_id=schedule["id"], requested_by=requester, payload=payload_b, now=now,
    )
    db.commit()
    # payload가 다르므로 둘 다 살아 있는 pending 행 — 이 자체가 의도된 정상 상태다.
    assert a1.id != b1.id

    # 이 시점에 이 객체에 대해 pending 행이 2개다. 예전 코드라면 다음 호출이
    # scalar_one_or_none()에서 MultipleResultsFound로 500이 났다.
    a2 = create_approval(
        db, request_type="schedule.enable", object_type="schedule",
        object_id=schedule["id"], requested_by=requester, payload=payload_a, now=now,
    )
    assert a2.id == a1.id  # 같은 payload → 기존 행 재사용, 새로 안 만든다

    c1 = create_approval(
        db, request_type="schedule.enable", object_type="schedule",
        object_id=schedule["id"], requested_by=requester,
        payload={"definition": {"cron_expression": "*/10 * * * *"}}, now=now,
    )
    assert c1.id not in {a1.id, b1.id}  # 세 번째 다른 payload → 새 pending 셋째 행


def test_deciding_expired_approval_does_not_persist_status_change(
    client, login_as, workflow_id, db, fake_clock
):
    """Regression (감사 #6): `_ensure_decidable`가 만료를 발견해 `ConflictError`를 던지는
    경로는 `row.status = EXPIRED` 대입을 절대 커밋하지 못한다 — `get_db`가 예외 시 요청
    트랜잭션 전체를 롤백한다. 저장된 만료 전이는 오직 백그라운드 스윕(`expire_pending`)만
    한다는 것을 못박아 둔다 — 이 대입이 실제로 저장되는 것처럼 보이는 리그레션(예: 실수로
    끼워 넣은 flush)이 생기면 이 테스트가 잡는다.
    """
    from app.approvals.models import APPROVAL_PENDING, Approval

    csrf = login_as("admin", email="deadwrite@goodmit.co.kr")
    schedule = _make_schedule(client, csrf, workflow_id, name="죽은 대입 테스트")
    approval_id = client.post(
        f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(csrf)
    ).json()["approval"]["id"]

    fake_clock.advance(73 * 3600)  # 72h 기본 만료 초과, 세션도 함께 만료된다
    csrf = login_as("admin", email="deadwrite@goodmit.co.kr")
    r = client.post(f"/api/admin/approvals/{approval_id}/approve", headers=_headers(csrf))
    assert r.status_code == 409

    row = db.get(Approval, approval_id)
    db.refresh(row)
    assert row.status == APPROVAL_PENDING  # 스윕 전에는 저장된 상태가 그대로다
