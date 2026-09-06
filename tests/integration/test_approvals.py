"""Approval workflow (spec §20): gates, decisions, self-approval ban, expiry,
exactly-once payload replay."""

from datetime import timedelta

import pytest

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


# S11 이후 스케줄 대상은 `system` 하나다(D-267). 이 파일이 지키는 것은 승인 게이트이므로
# 대상만 바꾼다.
@pytest.fixture()
def workflow_id():
    return "noop"


def _make_schedule(client, csrf, workflow_id, name="승인 스케줄"):
    return client.post(
        "/api/admin/schedules",
        json={
            "name": name,
            "schedule_type": "cron",
            "cron_expression": "0 * * * *",
            "timezone": "UTC",
            "target_type": "system",
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


def test_integration_endpoint_change_gated_for_admin(client, login_as):
    """목적지를 바꾸는 것은 승인 대상이고 설명을 바꾸는 것은 아니다.

    S11 이전에는 러너로도 같은 것을 봤다 — 그 화면이 사라져 연동 하나가 남았고,
    규칙(민감 필드만 게이트)은 그대로다.
    """
    sys_csrf = login_as("system_admin", email="integ-owner@goodmit.co.kr")
    integ = client.post(
        "/api/admin/integrations",
        json={"name": "게이트 연동", "provider_type": "http_service",
              "base_url": "https://api.anthropic.com/v1"},
        headers=_headers(sys_csrf),
    ).json()["integration"]

    admin_csrf = login_as("admin", email="integ-editor@goodmit.co.kr")
    # 허용 목록은 host:port 만 보므로 **경로로** 가른다 — 값이 실제로 달라져야 민감 필드
    # 변경으로 잡힌다(같은 값이면 바뀐 것이 없어 게이트에 닿지도 않는다).
    r = client.patch(
        f"/api/admin/integrations/{integ['id']}",
        json={"base_url": "https://api.anthropic.com/v2"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 202
    assert r.json()["status"] == "approval_pending"

    # 민감하지 않은 변경(설명)은 즉시 적용.
    r = client.patch(
        f"/api/admin/integrations/{integ['id']}",
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


# ── 결재 표면이 사람에게 하는 말 (perm-13 · perm-16 · perm-21 · perm-03) ─────


def test_redeciding_says_the_status_in_korean(client, login_as, workflow_id):
    """409 문구가 내부 열거값(`status=rejected`)을 그대로 노출했다 — 이 문구는 토스트로
    관리자에게 그대로 보이고, 목록·배지는 같은 상태를 「거절됨」이라고 부른다."""
    admin_csrf = login_as("admin", email="status-ko-asker@goodmit.co.kr")
    schedule = _make_schedule(client, admin_csrf, workflow_id, name="상태 문구 확인")
    approval = client.post(
        f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(admin_csrf)
    ).json()["approval"]

    csrf = login_as("system_admin", email="status-ko@goodmit.co.kr")
    assert client.post(
        f"/api/admin/approvals/{approval['id']}/reject", headers=_headers(csrf)
    ).status_code == 200
    again = client.post(
        f"/api/admin/approvals/{approval['id']}/approve", headers=_headers(csrf)
    )
    assert again.status_code == 409
    message = again.json()["error"]["message"]
    assert "거절된" in message, message
    assert "status=" not in message, f"내부 상태 코드가 화면 문구로 샌다: {message}"


def test_delegation_list_rejects_an_unknown_state(client, login_as):
    """형제 목록(`/api/admin/approvals?status=`)은 이미 422 인데 위임 목록만 조용히 0건이었다."""
    csrf = login_as("admin", email="deleg-state@goodmit.co.kr")
    bogus = client.get("/api/admin/approval-delegations?state=bogus", headers=_headers(csrf))
    assert bogus.status_code == 422, bogus.text
    assert "active" in bogus.json()["error"]["message"]

    ok = client.get("/api/admin/approval-delegations?state=active", headers=_headers(csrf))
    assert ok.status_code == 200, ok.text
    assert ok.json()["items"] == []


def test_request_notification_body_uses_the_korean_object_label(
    client, login_as, workflow_id, db
):
    """제목만 한국어로 바꾸고 본문에는 `object_type` 원문을 넣고 있었다 — 한 알림 안에서
    제목은 「승인 요청: 스케줄 활성화」, 본문은 「… schedule 변경 승인을 요청했습니다」였다."""
    from app.notifications.models import Notification

    csrf = login_as("admin", email="ko-body-requester@goodmit.co.kr")
    schedule = _make_schedule(client, csrf, workflow_id, name="한글 본문 확인")
    assert client.post(
        f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(csrf)
    ).status_code == 202

    bodies = [
        n.body
        for n in db.query(Notification).filter(Notification.type == "approval_requested").all()
    ]
    assert bodies
    for body in bodies:
        assert "schedule" not in body, f"내부 object_type 이 알림 본문에 그대로 있다: {body}"
        assert "스케줄 변경 승인을 요청했습니다" in body, body


def test_on_behalf_of_shows_the_delegators_name(client, login_as, db, make_user, fake_clock):
    """「누구의 위임으로 결재했는가」가 상세에서 UUID 로 나왔다 — 그 줄의 존재 이유가
    「운영자가 왜 승인할 수 있었지?」에 답하는 것인데 정작 답이 원시 id 였다."""
    from app.approvals import delegation

    boss = make_user("ob-boss@goodmit.co.kr", role="admin", display_name="위임한관리자")
    stand_in = make_user("ob-standin@goodmit.co.kr", role="operator", display_name="대리결재자")
    target = make_user("ob-target@goodmit.co.kr", role="user", display_name="대상")
    db.commit()

    now = fake_clock.now()
    delegation.create(
        db, delegator=boss, delegate=stand_in,
        starts_at=now - timedelta(hours=1), ends_at=now + timedelta(days=3),
        reason="휴가", created_by=boss.id, now=now, visible=None,
    )
    db.commit()

    asker_csrf = login_as("admin", email="ob-asker@goodmit.co.kr")
    approval = client.patch(
        f"/api/admin/users/{target.id}", json={"role": "admin"}, headers=_headers(asker_csrf)
    ).json()["approval"]

    op_csrf = login_as("operator", email="ob-standin@goodmit.co.kr")
    decided = client.post(
        f"/api/admin/approvals/{approval['id']}/approve", headers=_headers(op_csrf)
    )
    assert decided.status_code == 200, decided.text

    csrf = login_as("system_admin", email="ob-reader@goodmit.co.kr")
    detail = client.get(f"/api/admin/approvals/{approval['id']}", headers=_headers(csrf))
    assert detail.status_code == 200, detail.text
    row = detail.json()["approval"]
    assert row["decided_on_behalf_of"] == boss.id
    assert row["decided_on_behalf_of_name"] == "위임한관리자", row


# ── 거부된 결재 시도는 감사에 남는다 (perm-15) ───────────────────────────────


def _audit_rows(client, csrf, approval_id, **params):
    r = client.get(
        "/api/admin/audit",
        params={"object_type": "approval", "object_id": approval_id, **params},
        headers=_headers(csrf),
    )
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_a_refused_decision_leaves_a_failure_row_in_the_audit_log(
    client, login_as, workflow_id
):
    """승인은 권한 부여 실행이라 「누가 결재하려다 막혔는가」는 남아야 하는 사실이다.
    감사 기록이 성공 뒤에만 있어서 자기 승인 403 도, 권한 없는 사용자의 시도도 흔적이 없었다."""
    csrf = login_as("admin", email="fail-audit-asker@goodmit.co.kr")
    schedule = _make_schedule(client, csrf, workflow_id, name="실패 감사 케이스")
    approval = client.post(
        f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(csrf)
    ).json()["approval"]

    # 요청자 자신의 승인 — 403.
    denied = client.post(
        f"/api/admin/approvals/{approval['id']}/approve", headers=_headers(csrf)
    )
    assert denied.status_code == 403, denied.text

    # 권한이 아예 없는 사람의 시도 — 403.
    user_csrf = login_as("user", email="fail-audit-nobody@goodmit.co.kr")
    assert client.post(
        f"/api/admin/approvals/{approval['id']}/approve", headers=_headers(user_csrf)
    ).status_code == 403

    reader = login_as("system_admin", email="fail-audit-reader@goodmit.co.kr")
    failures = _audit_rows(client, reader, approval["id"], result="failure")
    assert len(failures) == 2, f"거부된 결재 시도가 감사에 안 남는다: {failures}"
    assert {row["action"] for row in failures} == {"approval.approve"}
    assert _audit_rows(client, reader, approval["id"], result="success") == []


def test_a_successful_decision_is_still_recorded_as_success(client, login_as, workflow_id):
    """오탐 방지 — 실패 기록을 넣다가 성공 기록이 실패로 뒤집히면 안 된다."""
    asker = login_as("admin", email="ok-audit-asker@goodmit.co.kr")
    schedule = _make_schedule(client, asker, workflow_id, name="성공 감사 케이스")
    approval = client.post(
        f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(asker)
    ).json()["approval"]

    csrf = login_as("system_admin", email="ok-audit-decider@goodmit.co.kr")
    assert client.post(
        f"/api/admin/approvals/{approval['id']}/approve", headers=_headers(csrf)
    ).status_code == 200

    rows = _audit_rows(client, csrf, approval["id"])
    assert [(r["action"], r["result"]) for r in rows] == [("approval.approve", "success")]


# ── 대상 계정이 닫힌 뒤의 역할 승격 (xc-15) ──────────────────────────────────


def test_role_change_approval_is_stale_once_the_target_is_archived(
    client, login_as, db, make_user
):
    """보관은 「이 사람의 접근을 끊는다」는 관리 행위다. 큐에 남아 있던 승격이 그 뒤에
    적용되면 닫힌 계정이 admin 이 되고, 복구 단추 한 번에 관리자 권한으로 되살아난다."""
    from app.users.models import User

    target = make_user("stale-target@goodmit.co.kr", role="user", display_name="보관대상")
    db.commit()

    asker = login_as("admin", email="stale-asker@goodmit.co.kr")
    approval = client.patch(
        f"/api/admin/users/{target.id}", json={"role": "admin"}, headers=_headers(asker)
    ).json()["approval"]

    csrf = login_as("system_admin", email="stale-root@goodmit.co.kr")
    assert client.post(
        f"/api/admin/users/{target.id}/archive", headers=_headers(csrf)
    ).status_code == 200

    r = client.post(f"/api/admin/approvals/{approval['id']}/approve", headers=_headers(csrf))
    assert r.status_code == 409, f"보관된 계정이 승인으로 승격됐다: {r.status_code} {r.text}"
    db.expire_all()
    assert db.get(User, target.id).role == "user", "409 인데 실제로는 역할이 올라갔다"


def test_a_live_target_is_still_promoted_by_the_same_approval_path(
    client, login_as, db, make_user
):
    """오탐 방지 — 살아 있는 계정의 승격까지 막히면 승인 기능 자체가 고장난 것이다."""
    from app.users.models import User

    target = make_user("live-target@goodmit.co.kr", role="user", display_name="정상대상")
    db.commit()

    asker = login_as("admin", email="live-asker@goodmit.co.kr")
    approval = client.patch(
        f"/api/admin/users/{target.id}", json={"role": "admin"}, headers=_headers(asker)
    ).json()["approval"]

    csrf = login_as("system_admin", email="live-root@goodmit.co.kr")
    r = client.post(f"/api/admin/approvals/{approval['id']}/approve", headers=_headers(csrf))
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(User, target.id).role == "admin"


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


# ── 잠금 대기 초과 판정은 **문구가 아니라 SQLSTATE** 다 ──────────────────────
#
# 두 행 잠금 경로(결재 잠금·위임자 잠금)가 예외 문구에 영어 "lock" 이 들어 있는지로 잠금
# 대기 초과를 가렸다. PostgreSQL 은 오류 문구를 서버 로캘(`lc_messages`)로 렌더링한다 —
# 이 배포는 한국어라 그 문구에 "lock" 이 없고, 그러면 깨끗한 409 대신 날 500 이 나간다.
# 결재 경로에서는 그 500 이 「거절된 쓰기」 감사 행을 이미 커밋한 뒤에 떨어져, 원장에는
# 결재 시도가 남고 사용자는 서버 오류를 본다. 반대 방향도 틀린다: 문구에 우연히 그 네
# 글자가 든 다른 오류(테이블 이름에 lock 이 든 경우 등)가 경합으로 둔갑한다.


class _FakeOrig(Exception):
    """psycopg 예외 흉내 — `sqlstate` 를 들고 있는 원본 예외."""

    def __init__(self, message: str, sqlstate: str) -> None:
        super().__init__(message)
        self.sqlstate = sqlstate


def _pg_error(message: str, sqlstate: str):
    from sqlalchemy.exc import OperationalError

    return OperationalError("SELECT 1", {}, _FakeOrig(message, sqlstate))


class _RaisingSession:
    """첫 `execute`(SET LOCAL)는 통과하고 두 번째(잠금 시도)에서 던진다."""

    def __init__(self, exc):
        self._exc = exc
        self.calls = 0

    def execute(self, *args, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return None
        raise self._exc


# 한국어 로캘의 PostgreSQL 이 실제로 내는 모양 — ASCII "lock" 이 한 글자도 없다.
_KO_LOCK_TIMEOUT = "잠금 대기 시간이 초과되어 명령을 취소합니다"
_EN_LOCK_TIMEOUT = "canceling statement due to lock timeout"


@pytest.mark.parametrize("message", [_KO_LOCK_TIMEOUT, _EN_LOCK_TIMEOUT])
def test_decision_lock_timeout_is_a_conflict_in_any_server_locale(message):
    """55P03 이면 로캘과 무관하게 409 다."""
    from app.approvals.models import Approval
    from app.approvals.service import lock_for_decision
    from app.core.errors import ConflictError

    session = _RaisingSession(_pg_error(message, "55P03"))
    with pytest.raises(ConflictError) as caught:
        lock_for_decision(session, Approval(id="appr-locale-1"))
    assert "다른 관리자가 이 요청을 결재하고 있습니다" in str(caught.value.message)


def test_a_non_conflict_error_whose_text_contains_lock_is_not_swallowed():
    """반례 — 문구에 lock 이 들어 있어도 경합이 아니면 그대로 올라간다. 이것이 없으면
    「무조건 409」로도 위 시험이 통과하고, 진짜 스키마 오류가 경합으로 위장한다."""
    from sqlalchemy.exc import OperationalError

    from app.approvals.models import Approval
    from app.approvals.service import lock_for_decision

    session = _RaisingSession(
        _pg_error('relation "advisory_locks" does not exist', "42P01")
    )
    with pytest.raises(OperationalError):
        lock_for_decision(session, Approval(id="appr-locale-2"))


@pytest.mark.parametrize("message", [_KO_LOCK_TIMEOUT, _EN_LOCK_TIMEOUT])
def test_delegator_lock_timeout_is_a_conflict_in_any_server_locale(message):
    from app.approvals.delegation import _lock_delegator
    from app.core.errors import ConflictError

    session = _RaisingSession(_pg_error(message, "55P03"))
    with pytest.raises(ConflictError) as caught:
        _lock_delegator(session, "user-locale-1")
    assert "같은 사람의 위임이 동시에 등록되고 있습니다" in str(caught.value.message)


def test_delegator_lock_does_not_swallow_a_schema_error_that_mentions_lock():
    """반례 — 위임자 잠금도 같은 규칙이다."""
    from sqlalchemy.exc import OperationalError

    from app.approvals.delegation import _lock_delegator

    session = _RaisingSession(
        _pg_error('relation "advisory_locks" does not exist', "42P01")
    )
    with pytest.raises(OperationalError):
        _lock_delegator(session, "user-locale-2")
