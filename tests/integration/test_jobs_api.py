"""qa-contract-change: 작업 큐의 역추적 필터가 셋에서 둘로 줄었다 — generation_id 는 그 화면(문서 자동 생성)이 S11 과 함께 사라져 만들 수 있는 잡 자체가 없다. schedule_id·schedule_run_id 쪽 단언과 「매칭 없는 값은 빈 목록이고 다른 작업이 안 샌다」는 반례는 그대로다."""

import pytest

from app.jobs import repository

pytestmark = pytest.mark.integration


@pytest.fixture()
def seeded_jobs(db, fake_clock):
    now = fake_clock.now()
    ok = repository.enqueue(db, job_type="chat_message", payload={"q": 1}, now=now)
    failed = repository.enqueue(db, job_type="chat_message", payload={"q": 2}, now=now)
    failed.status = "failed"
    failed.last_error = "n8n timeout"
    db.commit()
    return {"queued": ok.id, "failed": failed.id}


def test_operator_can_list_and_filter_jobs(client, login_as, seeded_jobs):
    login_as("operator")
    r = client.get("/api/admin/jobs")
    assert r.status_code == 200
    assert r.json()["total"] == 2

    r = client.get("/api/admin/jobs", params={"status": "failed"})
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["last_error"] == "n8n timeout"


def test_stats_endpoint(client, login_as, seeded_jobs):
    login_as("operator")
    r = client.get("/api/admin/jobs/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["queued"] == 1
    assert body["failed"] == 1


def test_stats_endpoint_honors_dept_admin_scope(db, client, login_as, make_user, fake_clock):
    """SEC-02: 형제인 목록·상세·재시도·취소는 apply_scope를 지나는데 요약(stats)만
    빠져 있었다 — 부서 범위 admin이 전역 큐 깊이·실패 수를 그대로 봤다."""
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.flush()

    mine_user = make_user("j-mine@goodmit.co.kr", role="user", display_name="우리팀사람")
    theirs_user = make_user("j-theirs@goodmit.co.kr", role="user", display_name="남의팀사람")
    mine_user.department_id = mine.id
    theirs_user.department_id = theirs.id

    dept_admin = make_user("j-dept-admin@goodmit.co.kr", role="admin", display_name="부서관리자")
    dept_admin.department_id = mine.id
    dept_admin.admin_scope = "dept"
    dept_admin.scope_dept_id = mine.id
    db.commit()

    now = fake_clock.now()
    repository.enqueue(db, job_type="chat_message", payload={}, now=now, user_id=mine_user.id)
    failed = repository.enqueue(db, job_type="chat_message", payload={}, now=now, user_id=theirs_user.id)
    failed.status = "failed"
    db.commit()

    login_as("admin", email="j-dept-admin@goodmit.co.kr")
    body = client.get("/api/admin/jobs/stats").json()
    assert body["queued"] == 1, "우리팀 잡만 보여야 한다"
    assert body["failed"] == 0, "남의팀 잡의 실패가 부서 admin에게 새면 안 된다"


def test_operator_can_retry_failed_job(client, login_as, seeded_jobs):
    csrf = login_as("operator")
    r = client.post(
        f"/api/admin/jobs/{seeded_jobs['failed']}/retry", headers={"X-CSRF-Token": csrf}
    )
    assert r.status_code == 200
    assert r.json()["job"]["status"] == "queued"


def test_retry_non_failed_job_conflict(client, login_as, seeded_jobs):
    csrf = login_as("operator")
    r = client.post(
        f"/api/admin/jobs/{seeded_jobs['queued']}/retry", headers={"X-CSRF-Token": csrf}
    )
    assert r.status_code == 409


def test_cancel_queued_job(client, login_as, seeded_jobs):
    csrf = login_as("operator")
    r = client.post(
        f"/api/admin/jobs/{seeded_jobs['queued']}/cancel", headers={"X-CSRF-Token": csrf}
    )
    assert r.status_code == 200
    assert r.json()["job"]["status"] == "cancelled"


def test_regular_user_cannot_access_jobs_admin(client, login_as, seeded_jobs):
    login_as("user")
    assert client.get("/api/admin/jobs").status_code == 403


def test_unknown_status_filter_rejected(client, login_as):
    login_as("operator")
    r = client.get("/api/admin/jobs", params={"status": "exploded"})
    assert r.status_code == 422


def test_schedule_id_filters_find_the_triggering_job(client, login_as, db, fake_clock):
    # FN-13/IA-02 반대 방향 — 스케줄이 자신을 실행한 작업으로 역추적한다.
    # (문서 생성 쪽 절반은 S11 이 그 화면과 함께 걷어냈다.)
    now = fake_clock.now()
    schedule_run = repository.enqueue(
        db, job_type="schedule_run",
        payload={"schedule_id": "sched-abc", "schedule_run_id": "run-xyz"}, now=now,
    )
    unrelated = repository.enqueue(db, job_type="chat_message", payload={"q": 1}, now=now)
    db.commit()

    login_as("operator")

    r = client.get("/api/admin/jobs", params={"schedule_id": "sched-abc"})
    assert r.status_code == 200
    assert [it["id"] for it in r.json()["items"]] == [schedule_run.id]

    r = client.get("/api/admin/jobs", params={"schedule_run_id": "run-xyz"})
    assert [it["id"] for it in r.json()["items"]] == [schedule_run.id]

    # 매칭 없는 값은 빈 목록이지 다른 작업이 새지 않는다.
    r = client.get("/api/admin/jobs", params={"schedule_id": "no-such-schedule"})
    assert r.json()["items"] == []
    assert unrelated.id not in [it["id"] for it in r.json()["items"]]
