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
