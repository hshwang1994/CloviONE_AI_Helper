import pytest

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration


def test_notification_list_and_read_flow(client, login_as, db, fake_clock):
    csrf = login_as("user", email="notified@goodmit.co.kr")
    me = client.get("/api/me").json()["user"]

    from app.notifications.service import notify_user

    notify_user(
        db, me["id"], type_="job_failed", title="요청 처리 실패",
        body="다시 시도하세요.", now=fake_clock.now(),
    )
    db.commit()

    listing = client.get("/api/notifications").json()
    assert listing["total"] == 1
    assert listing["unread"] == 1
    note = listing["items"][0]
    assert note["title"] == "요청 처리 실패"

    r = client.post(f"/api/notifications/{note['id']}/read", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    assert client.get("/api/notifications/unread-count").json()["unread"] == 0


def test_read_all_marks_every_unread(client, login_as, db, fake_clock):
    # '모두 읽음'은 페이지에 로드된 것뿐 아니라 전체 미읽음을 한 번에 처리한다.
    csrf = login_as("user", email="readall@goodmit.co.kr")
    me = client.get("/api/me").json()["user"]

    from app.notifications.service import notify_user

    for i in range(12):  # page_size(8)보다 많게
        notify_user(db, me["id"], type_="system", title=f"알림 {i}", now=fake_clock.now())
    db.commit()

    assert client.get("/api/notifications/unread-count").json()["unread"] == 12
    r = client.post("/api/notifications/read-all", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and r.json()["read_count"] == 12
    assert client.get("/api/notifications/unread-count").json()["unread"] == 0


def test_cannot_read_another_users_notification(app, client, login_as, make_user, db, fake_clock):
    from fastapi.testclient import TestClient

    csrf = login_as("user", email="mine@goodmit.co.kr")
    me = client.get("/api/me").json()["user"]

    from app.notifications.service import notify_user

    note = notify_user(
        db, me["id"], type_="test", title="내 알림", now=fake_clock.now()
    )
    db.commit()

    make_user("other@goodmit.co.kr")
    with TestClient(app, raise_server_exceptions=False) as other:
        other.post(
            "/login", json={"email": "other@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
        )
        other_csrf = other.get("/api/me").json()["csrf_token"]
        # 목록에 안 보이고, 읽음 처리도 불가.
        assert other.get("/api/notifications").json()["total"] == 0
        r = other.post(
            f"/api/notifications/{note.id}/read", headers={"X-CSRF-Token": other_csrf}
        )
        assert r.status_code == 404


def test_job_final_failure_notifies_owner(app, client, login_as, settings, fake_clock, db):
    """worker 최종 실패 → 소유자 알림 (fan-out 경로 검증)."""
    from app.jobs import repository
    from app.jobs.exceptions import PermanentJobError
    from app.jobs.worker import Worker, WorkerContext

    login_as("user", email="jobowner@goodmit.co.kr")
    me = client.get("/api/me").json()["user"]

    def failing_handler(db_, job, ctx):
        raise PermanentJobError("영구 실패")

    with app.state.session_factory() as session:
        repository.enqueue(
            session, job_type="fail_test", payload={}, now=fake_clock.now(),
            user_id=me["id"],
        )
        session.commit()

    worker = Worker(
        app.state.session_factory, fake_clock, {"fail_test": failing_handler},
        WorkerContext(settings=settings, clock=fake_clock),
    )
    worker.run_once()

    listing = client.get("/api/notifications").json()
    assert listing["total"] == 1
    assert listing["items"][0]["type"] == "job_failed"


def test_account_lock_notifies_admins(client, make_user, login_as, settings, db):
    make_user("locktarget@goodmit.co.kr")
    login_as("admin", email="watcher@goodmit.co.kr")

    from fastapi.testclient import TestClient

    for _ in range(settings.login_max_failures):
        client.post(
            "/login", json={"email": "locktarget@goodmit.co.kr", "password": "Wrong-1!"}
        )

    # 관리자 알림 존재 (본인 알림 + 관리자 알림).
    from app.notifications.models import Notification

    notes = db.query(Notification).filter(Notification.type == "account_locked").all()
    assert len(notes) >= 2
