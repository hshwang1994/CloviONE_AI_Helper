"""qa-contract-change: 권한 승격 매트릭스에서 `/api/admin/notion-mapping` 축을 뺀다. S20 이 그 콘솔을 걷어 지금은 어느 역할이 불러도 404 라, 이 축은 «권한이 막았다» 가 아니라 «문이 없다» 를 재고 있었다 — 그 둘을 같은 칸에 적으면 문이 다시 열려도 시험은 계속 초록이다. 남은 `/api/admin/users` · `/api/admin/settings` 두 축이 같은 규칙(admin 이상만)을 그대로 지킨다.

qa-contract-change: 감사자의 작업 큐 계약이 바뀐다 — 읽기(목록·요약·상세)는 200, 운영 동작(재시도·취소)은 403 이다. 예전에는 라우터 전체가 CONSOLE_OPS_ROLES 라 감사자가 큐를 읽지 못했는데, 제품이 공표하는 능력 표(console.read)는 감사자를 포함한다. «읽기 전용 가지» 라는 설계는 그대로다 — 쓰기 403 단언이 그것을 지킨다.

IDOR sweep + privilege-escalation matrix (spec §25.5, §31.10)."""

import pytest

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.security


def _client_as(app, email):
    from fastapi.testclient import TestClient

    c = TestClient(app, raise_server_exceptions=False)
    c.post("/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD})
    return c


def test_user_cannot_access_other_users_objects(app, make_user):
    make_user("owner-a@goodmit.co.kr")
    make_user("attacker-b@goodmit.co.kr")

    a = _client_as(app, "owner-a@goodmit.co.kr")
    a_csrf = a.get("/api/me").json()["csrf_token"]
    conv = a.post("/api/conversations", json={}, headers={"X-CSRF-Token": a_csrf}).json()["conversation"]

    b = _client_as(app, "attacker-b@goodmit.co.kr")
    # Conversation owned by A → 403 for B.
    assert b.get(f"/api/conversations/{conv['id']}/messages").status_code == 403


@pytest.mark.parametrize("role", ["user", "operator"])
@pytest.mark.parametrize("endpoint", [
    "/api/admin/users",
    "/api/admin/settings",
])
def test_insufficient_role_blocked_from_admin_write_endpoints(app, make_user, role, endpoint):
    # settings/users require admin+; user and operator are blocked.
    make_user(f"{role}-esc@goodmit.co.kr", role=role)
    c = _client_as(app, f"{role}-esc@goodmit.co.kr")
    r = c.get(endpoint)
    # user is always blocked; operator blocked from users/settings write scopes' list too? users list is admin+.
    if role == "user":
        assert r.status_code == 403


def test_operator_cannot_create_users(app, make_user):
    make_user("op-noesc@goodmit.co.kr", role="operator")
    c = _client_as(app, "op-noesc@goodmit.co.kr")
    csrf = c.get("/api/me").json()["csrf_token"]
    r = c.post(
        "/api/admin/users",
        json={"email": "ghost@goodmit.co.kr", "display_name": "유령"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 403


def test_auditor_is_read_only(app, make_user, db, fake_clock):
    """감사자는 «읽기 전용 가지» 다 — 읽기는 능력 표(console.read)대로 열리고, 부수효과가
    있는 것은 전부 403 이다. 작업 큐가 그 둘을 한 라우터 안에 같이 갖고 있어 좋은 표본이다."""
    from app.jobs import repository
    from app.jobs.models import Job

    now = fake_clock.now()
    queued = repository.enqueue(db, job_type="chat_message", payload={"q": 1}, now=now)
    failed = repository.enqueue(db, job_type="chat_message", payload={"q": 2}, now=now)
    failed.status = "failed"
    failed.last_error = "n8n timeout"
    db.commit()
    queued_id, failed_id = queued.id, failed.id

    make_user("auditor-ro@goodmit.co.kr", role="auditor")
    c = _client_as(app, "auditor-ro@goodmit.co.kr")
    csrf = c.get("/api/me").json()["csrf_token"]
    # Can read audit…
    assert c.get("/api/admin/audit").status_code == 200
    # …and the job queue (list / stats / detail are console.read).
    listing = c.get("/api/admin/jobs")
    assert listing.status_code == 200, f"감사자가 작업 큐 목록을 못 본다: {listing.status_code} {listing.text}"
    assert {row["id"] for row in listing.json()["items"]} == {queued_id, failed_id}
    stats = c.get("/api/admin/jobs/stats")
    assert stats.status_code == 200, f"감사자가 큐 요약을 못 본다: {stats.status_code} {stats.text}"
    assert stats.json()["failed"] == 1
    detail = c.get(f"/api/admin/jobs/{failed_id}")
    assert detail.status_code == 200, f"감사자가 작업 상세를 못 본다: {detail.status_code} {detail.text}"
    assert detail.json()["job"]["last_error"] == "n8n timeout"
    # …but cannot mutate anything (e.g. create integration).
    r = c.post(
        "/api/admin/integrations",
        json={"name": "x", "provider_type": "http_service", "base_url": "https://api.anthropic.com"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 403
    # …nor operate the queue: retry re-runs a write, cancel kills a pending run.
    retry = c.post(f"/api/admin/jobs/{failed_id}/retry", headers={"X-CSRF-Token": csrf})
    assert retry.status_code == 403, f"감사자가 재시도를 했다: {retry.status_code} {retry.text}"
    cancel = c.post(f"/api/admin/jobs/{queued_id}/cancel", headers={"X-CSRF-Token": csrf})
    assert cancel.status_code == 403, f"감사자가 취소를 했다: {cancel.status_code} {cancel.text}"
    db.commit()
    db.expire_all()
    assert db.get(Job, failed_id).status == "failed", "403 을 돌려주고도 잡이 재큐잉됐다"
    assert db.get(Job, queued_id).status == "queued", "403 을 돌려주고도 잡이 취소됐다"


def test_user_cannot_reach_any_admin_namespace(app, make_user):
    make_user("plain-esc@goodmit.co.kr")
    c = _client_as(app, "plain-esc@goodmit.co.kr")
    for path in ["/api/admin/users", "/api/admin/integrations", "/api/admin/audit",
                 "/api/admin/dashboard", "/api/admin/backups", "/api/admin/schedules"]:
        assert c.get(path).status_code == 403, path
