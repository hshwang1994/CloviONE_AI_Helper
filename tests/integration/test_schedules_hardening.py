"""Schedule hardening: run_at/start_at coherence, run-now dedup, once-misfire
catch-up + owner notification.

These pin three previously-silent failure modes (see scheduler.py / router.py):
  1. run_at < start_at on a once schedule → rejected at create AND enable, instead
     of busy re-evaluating every tick then misfiring.
  2. Manual run-now double-click → one run, not duplicates (second-granularity
     idempotency key + active-run guard).
  3. A once schedule that misfired within a catch-up window still runs; beyond it,
     it is dropped but the owner is notified rather than losing it silently.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.notifications.models import Notification
from app.schedules.models import Schedule, ScheduleRun
from app.schedules.scheduler import SchedulerService

pytestmark = pytest.mark.integration

# FakeClock's default epoch — see tests/fakes/clock.py.
BASE = datetime(2026, 7, 14, 0, 0, 0)


@pytest.fixture()
def admin_csrf(login_as):
    # system_admin: enable은 승인 게이트를 우회해 직접 적용된다.
    return login_as("system_admin")


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


@pytest.fixture()
def workflow_id(client, admin_csrf):
    r = client.post(
        "/api/admin/workflows",
        json={
            "name": "보고서 생성",
            "webhook_url": "http://127.0.0.1:5678/webhook/report",
            "operation_mode": "read",
        },
        headers=_headers(admin_csrf),
    )
    return r.json()["workflow"]["id"]


def _once_payload(workflow_id, **overrides):
    return {
        "name": "일회성",
        "schedule_type": "once",
        "cron_expression": None,
        "run_at": "2026-07-14T05:00:00",
        "timezone": "UTC",
        "target_type": "workflow",
        "target_ref": workflow_id,
        "payload_template": {"scope": "weekly"},
        **overrides,
    }


def _cron_payload(workflow_id, **overrides):
    return {
        "name": "매시 보고서",
        "schedule_type": "cron",
        "cron_expression": "0 * * * *",
        "timezone": "UTC",
        "target_type": "workflow",
        "target_ref": workflow_id,
        "payload_template": {"scope": "weekly"},
        **overrides,
    }


# --------------------------------------------------------------------------- #
# Fix 1: run_at < start_at is rejected at create and at enable.
# --------------------------------------------------------------------------- #


def test_create_once_rejects_run_at_before_start_at(client, admin_csrf, workflow_id):
    r = client.post(
        "/api/admin/schedules",
        json=_once_payload(
            workflow_id,
            name="역전 스케줄",
            run_at="2026-07-14T01:00:00",
            start_at="2026-07-14T02:00:00",
        ),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422
    assert "run_at" in r.json()["error"]["message"]


def test_create_once_allows_run_at_after_start_at(client, admin_csrf, workflow_id):
    r = client.post(
        "/api/admin/schedules",
        json=_once_payload(
            workflow_id,
            name="정상 순서",
            run_at="2026-07-14T03:00:00",
            start_at="2026-07-14T02:00:00",
        ),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 201


def test_enable_once_rejects_run_at_before_start_at(
    client, admin_csrf, workflow_id, db
):
    created = client.post(
        "/api/admin/schedules",
        json=_once_payload(workflow_id, name="활성화 역전", run_at="2026-07-14T05:00:00"),
        headers=_headers(admin_csrf),
    ).json()["schedule"]

    # start_at을 run_at 뒤로 밀어 어긋난 상태를 만든다(create 검증을 우회한 드리프트 모사).
    row = db.get(Schedule, created["id"])
    row.start_at = datetime(2026, 7, 14, 6, 0, 0)
    db.commit()

    r = client.post(
        f"/api/admin/schedules/{created['id']}/enable", headers=_headers(admin_csrf)
    )
    assert r.status_code == 422
    assert "run_at" in r.json()["error"]["message"]

    db.expire_all()
    row = db.get(Schedule, created["id"])
    assert row.enabled is False  # 거부됐으므로 활성화되지 않음


# --------------------------------------------------------------------------- #
# Fix 2: run-now double-click does not duplicate.
# --------------------------------------------------------------------------- #


def test_run_now_double_click_does_not_duplicate(client, admin_csrf, workflow_id):
    created = client.post(
        "/api/admin/schedules",
        json=_cron_payload(workflow_id, name="수동 연타"),
        headers=_headers(admin_csrf),
    ).json()["schedule"]
    client.post(
        f"/api/admin/schedules/{created['id']}/enable", headers=_headers(admin_csrf)
    )

    r1 = client.post(
        f"/api/admin/schedules/{created['id']}/run-now",
        json={},
        headers=_headers(admin_csrf),
    )
    assert r1.status_code == 200
    run1_id = r1.json()["run"]["id"]

    # 첫 run이 아직 queued인 상태에서 즉시 재요청 — 새 run을 만들지 않고 그 run을 돌려준다.
    r2 = client.post(
        f"/api/admin/schedules/{created['id']}/run-now",
        json={},
        headers=_headers(admin_csrf),
    )
    assert r2.status_code == 200
    assert r2.json().get("deduplicated") is True
    assert r2.json()["run"]["id"] == run1_id

    runs = client.get(
        f"/api/admin/schedules/{created['id']}/runs", headers=_headers(admin_csrf)
    ).json()
    assert runs["total"] == 1


def test_run_now_uses_second_granularity_idempotency_key(
    client, admin_csrf, workflow_id, db
):
    created = client.post(
        "/api/admin/schedules",
        json=_cron_payload(workflow_id, name="초단위 키"),
        headers=_headers(admin_csrf),
    ).json()["schedule"]
    client.post(
        f"/api/admin/schedules/{created['id']}/enable", headers=_headers(admin_csrf)
    )
    client.post(
        f"/api/admin/schedules/{created['id']}/run-now",
        json={},
        headers=_headers(admin_csrf),
    )

    db.expire_all()
    run = db.execute(
        select(ScheduleRun).where(ScheduleRun.schedule_id == created["id"])
    ).scalar_one()
    # 마이크로초(%f)가 아니라 초 단위 — manual:<id>:YYYYMMDDHHMMSS (14자리)로 끝난다.
    assert run.idempotency_key.startswith(f"manual:{created['id']}:")
    tail = run.idempotency_key.rsplit(":", 1)[-1]
    assert len(tail) == 14 and tail.isdigit()


# --------------------------------------------------------------------------- #
# Fix 3: once-schedule misfire — catch-up within window, notify when dropped.
# --------------------------------------------------------------------------- #


def _make_once(db, owner_id, *, next_run_at):
    row = Schedule(
        name=f"일회성-{len(db.query(Schedule).all())}",
        schedule_type="once",
        cron_expression=None,
        timezone="UTC",
        owner_user_id=owner_id,
        target_type="system",
        target_ref="noop",
        payload_template_json="{}",
        misfire_policy="skip",
        concurrency_policy="allow",
        enabled=True,
        next_run_at=next_run_at,
    )
    db.add(row)
    db.commit()
    return row


def test_once_misfire_within_catchup_runs(db, app, fake_clock, make_user):
    owner = make_user(email="owner-catchup@goodmit.co.kr")
    sched = _make_once(db, owner.id, next_run_at=BASE + timedelta(hours=1))

    scheduler = SchedulerService(app.state.session_factory, fake_clock)
    # scheduled at +1h; now = +1h20m → 1200s late (>300s grace, <=3600s catch-up).
    fake_clock.advance(3600 + 1200)
    assert scheduler.tick() == 1  # 따라잡기 실행

    db.expire_all()
    runs = (
        db.execute(select(ScheduleRun).where(ScheduleRun.schedule_id == sched.id))
        .scalars()
        .all()
    )
    assert len(runs) == 1
    assert runs[0].status == "queued"

    # 실행됐으므로 소유자에게 실패 알림이 가지 않는다.
    notes = (
        db.execute(select(Notification).where(Notification.user_id == owner.id))
        .scalars()
        .all()
    )
    assert notes == []

    db.refresh(sched)
    assert sched.enabled is False  # once 소진
    assert sched.next_run_at is None


def test_once_misfire_beyond_catchup_notifies_owner(db, app, fake_clock, make_user):
    owner = make_user(email="owner-dropped@goodmit.co.kr")
    sched = _make_once(db, owner.id, next_run_at=BASE + timedelta(hours=1))

    scheduler = SchedulerService(app.state.session_factory, fake_clock)
    # scheduled at +1h; now = +5h → 4h late, well beyond the 3600s catch-up window.
    fake_clock.advance(3600 * 5)
    assert scheduler.tick() == 0  # 실행되지 않고 버려짐

    db.expire_all()
    runs = (
        db.execute(select(ScheduleRun).where(ScheduleRun.schedule_id == sched.id))
        .scalars()
        .all()
    )
    assert len(runs) == 1
    assert runs[0].status == "skipped"
    assert runs[0].error_message == "misfire_skip"

    # 조용히 사라지지 않고 소유자에게 알림이 남는다.
    notes = (
        db.execute(select(Notification).where(Notification.user_id == owner.id))
        .scalars()
        .all()
    )
    assert len(notes) == 1
    assert notes[0].type == "schedule_failed"
    assert notes[0].related_object_type == "schedule"
    assert notes[0].related_object_id == sched.id

    db.refresh(sched)
    assert sched.enabled is False
    assert sched.next_run_at is None


def test_cron_misfire_skip_unchanged_no_notification(db, app, fake_clock, make_user):
    """cron은 다음 발생이 있으므로 기존대로 건너뛰고 알림도 만들지 않는다(회귀 방지)."""
    owner = make_user(email="owner-cron@goodmit.co.kr")
    sched = Schedule(
        name="크론 미스파이어",
        schedule_type="cron",
        cron_expression="0 * * * *",
        timezone="UTC",
        owner_user_id=owner.id,
        target_type="system",
        target_ref="noop",
        payload_template_json="{}",
        misfire_policy="skip",
        enabled=True,
        next_run_at=BASE + timedelta(hours=1),
    )
    db.add(sched)
    db.commit()

    scheduler = SchedulerService(app.state.session_factory, fake_clock)
    fake_clock.advance(3600 * 5)  # 4h 지연 — grace 초과
    assert scheduler.tick() == 0

    db.expire_all()
    runs = (
        db.execute(select(ScheduleRun).where(ScheduleRun.schedule_id == sched.id))
        .scalars()
        .all()
    )
    assert len(runs) == 1
    assert runs[0].status == "skipped"

    notes = (
        db.execute(select(Notification).where(Notification.user_id == owner.id))
        .scalars()
        .all()
    )
    assert notes == []  # cron은 알림 없음

    db.refresh(sched)
    assert sched.enabled is True  # cron은 계속 산다
    assert sched.next_run_at > fake_clock.now()
