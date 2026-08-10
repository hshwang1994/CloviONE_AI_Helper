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


def test_schedule_and_generation_id_filters_find_the_triggering_job(client, login_as, db, fake_clock):
    # FN-13/IA-02 반대 방향 — 스케줄/문서 생성이 자신을 실행한 작업으로 역추적한다.
    now = fake_clock.now()
    schedule_run = repository.enqueue(
        db, job_type="schedule_run",
        payload={"schedule_id": "sched-abc", "schedule_run_id": "run-xyz"}, now=now,
    )
    doc_gen = repository.enqueue(
        db, job_type="document_generate", payload={"generation_id": "gen-123"}, now=now,
    )
    unrelated = repository.enqueue(db, job_type="chat_message", payload={"q": 1}, now=now)
    db.commit()

    login_as("operator")

    r = client.get("/api/admin/jobs", params={"schedule_id": "sched-abc"})
    assert r.status_code == 200
    assert [it["id"] for it in r.json()["items"]] == [schedule_run.id]

    r = client.get("/api/admin/jobs", params={"schedule_run_id": "run-xyz"})
    assert [it["id"] for it in r.json()["items"]] == [schedule_run.id]

    r = client.get("/api/admin/jobs", params={"generation_id": "gen-123"})
    assert [it["id"] for it in r.json()["items"]] == [doc_gen.id]

    # 매칭 없는 값은 빈 목록이지 다른 작업이 새지 않는다.
    r = client.get("/api/admin/jobs", params={"schedule_id": "no-such-schedule"})
    assert r.json()["items"] == []
    assert unrelated.id not in [it["id"] for it in r.json()["items"]]
