"""Schedule API + end-to-end execution through worker and fake n8n."""

import pytest

from app.jobs.handlers.schedule_run import handle_schedule_run
from app.jobs.worker import Worker, WorkerContext
from app.schedules.scheduler import SchedulerService

pytestmark = pytest.mark.integration


@pytest.fixture()
def admin_csrf(login_as):
    # system_admin: schedule enable은 승인 게이트(M9)를 우회해 직접 적용된다.
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


def _schedule_payload(workflow_id, **overrides):
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


def test_create_validates_cron(client, admin_csrf, workflow_id):
    r = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(workflow_id, cron_expression="bad cron"),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422


def test_create_validates_timezone(client, admin_csrf, workflow_id):
    r = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(workflow_id, timezone="Mars/Olympus"),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422


def test_create_validates_target(client, admin_csrf):
    r = client.post(
        "/api/admin/schedules",
        json=_schedule_payload("no-such-workflow"),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422


def test_create_accepts_null_misfire_and_concurrency_policy(
    client, admin_csrf, workflow_id
):
    # 관리자 콘솔 select가 미선택 상태를 명시적 null로 보낼 수 있다 — 기본값(skip)으로
    # 처리되어야 하며 422로 거부되면 안 된다 (round16 발견사항, 스케줄 생성 크래시).
    r = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(
            workflow_id, misfire_policy=None, concurrency_policy=None
        ),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 201
    body = r.json()["schedule"]
    assert body["misfire_policy"] == "skip"
    assert body["concurrency_policy"] == "skip"


def test_create_still_rejects_invalid_misfire_policy(client, admin_csrf, workflow_id):
    r = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(workflow_id, misfire_policy="bogus"),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422


def test_preset_expands_to_cron(client, admin_csrf, workflow_id):
    r = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(
            workflow_id, name="주간 프리셋", cron_expression=None, preset="weekly"
        ),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 201
    assert r.json()["schedule"]["cron_expression"] == "0 9 * * 1"


def test_created_disabled_enable_computes_next_run(client, admin_csrf, workflow_id):
    created = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(workflow_id),
        headers=_headers(admin_csrf),
    ).json()["schedule"]
    assert created["enabled"] is False
    assert created["next_run_at"] is None

    r = client.post(
        f"/api/admin/schedules/{created['id']}/enable", headers=_headers(admin_csrf)
    )
    assert r.status_code == 200
    body = r.json()["schedule"]
    assert body["enabled"] is True
    assert body["next_run_at"] == "2026-07-14T01:00:00"  # FakeClock 기준 다음 정각


def test_once_schedule_requires_future_run_at(client, admin_csrf, workflow_id):
    r = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(
            workflow_id, name="일회성", schedule_type="once",
            cron_expression=None, run_at="2020-01-01T00:00:00",
        ),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422


def test_dry_run_previews_without_executing(client, admin_csrf, workflow_id, db):
    created = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(workflow_id),
        headers=_headers(admin_csrf),
    ).json()["schedule"]
    r = client.post(
        f"/api/admin/schedules/{created['id']}/dry-run", headers=_headers(admin_csrf)
    )
    assert r.status_code == 200
    body = r.json()
    assert body["payload_preview"] == {"scope": "weekly"}
    assert len(body["next_fire_times_utc"]) == 3

    from app.schedules.models import ScheduleRun

    assert db.query(ScheduleRun).count() == 0


def test_end_to_end_schedule_execution(
    client, admin_csrf, workflow_id, app, settings, fake_clock, fake_http, db
):
    created = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(workflow_id),
        headers=_headers(admin_csrf),
    ).json()["schedule"]
    client.post(f"/api/admin/schedules/{created['id']}/enable", headers=_headers(admin_csrf))

    fake_http.on(
        "http://127.0.0.1:5678/webhook/report", json_body={"report": "생성 완료"}
    )

    scheduler = SchedulerService(app.state.session_factory, fake_clock)
    ctx = WorkerContext(
        settings=settings, clock=fake_clock, outbound_client=app.state.outbound_client
    )
    worker = Worker(
        app.state.session_factory, fake_clock, {"schedule_run": handle_schedule_run}, ctx
    )

    fake_clock.advance(3600)  # 01:00 도달
    assert scheduler.tick() == 1
    assert worker.run_once() is True

    import json as _json

    sent = _json.loads(fake_http.requests[0].content)
    assert sent == {"scope": "weekly"}

    # 1시간 경과로 관리자 세션이 idle 만료(30분) — 재로그인.
    from tests.conftest import DEFAULT_TEST_PASSWORD

    relogin = client.post(
        "/login",
        json={"email": "system-admin@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD},
    )
    admin_csrf = relogin.json()["csrf_token"]

    runs = client.get(
        f"/api/admin/schedules/{created['id']}/runs", headers=_headers(admin_csrf)
    ).json()
    assert runs["total"] == 1
    assert runs["items"][0]["status"] == "succeeded"
    assert "생성 완료" in runs["items"][0]["response_summary"]


def test_run_now_and_retry_failed_run(
    client, admin_csrf, workflow_id, app, settings, fake_clock, fake_http
):
    created = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(workflow_id, name="수동 실행"),
        headers=_headers(admin_csrf),
    ).json()["schedule"]
    # run-now도 활성화(승인) 게이트를 통과한 정의에만 허용된다.
    client.post(f"/api/admin/schedules/{created['id']}/enable", headers=_headers(admin_csrf))

    ctx = WorkerContext(
        settings=settings, clock=fake_clock, outbound_client=app.state.outbound_client
    )
    worker = Worker(
        app.state.session_factory, fake_clock, {"schedule_run": handle_schedule_run}, ctx
    )

    # Run-now against a failing webhook → run ends failed after retries.
    fake_http.on("http://127.0.0.1:5678/webhook/report", status=404)
    r = client.post(
        f"/api/admin/schedules/{created['id']}/run-now",
        json={},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200
    run_id = r.json()["run"]["id"]

    worker.run_once()  # 404 → HTTPStatusError → 재시도 소진까지
    for _ in range(3):
        fake_clock.advance(120)
        worker.run_once()

    runs = client.get(
        f"/api/admin/schedules/{created['id']}/runs", headers=_headers(admin_csrf)
    ).json()
    assert runs["items"][0]["status"] == "failed"

    # Operator retries the failed run — now the webhook works.
    fake_http.on("http://127.0.0.1:5678/webhook/report", json_body={"ok": True})
    operator_csrf = login = None
    r = client.post(
        f"/api/admin/schedules/runs/{run_id}/retry", headers=_headers(admin_csrf)
    )
    assert r.status_code == 200
    fake_clock.advance(1)
    worker.run_once()

    runs = client.get(
        f"/api/admin/schedules/{created['id']}/runs", headers=_headers(admin_csrf)
    ).json()
    assert runs["items"][0]["status"] == "succeeded"


def test_retry_run_respects_schedule_max_attempts(
    client, admin_csrf, workflow_id, app, settings, fake_clock, fake_http
):
    """운영자의 '재시도'가 스케줄의 retry_policy.max_attempts를 무시하면 안 된다.

    scheduler.create_run_and_enqueue는 _max_attempts(schedule)을 잡에 실어 보내는데,
    schedules/router.py::retry_run은 잡을 새로 enqueue하면서 이 값을 빼먹고
    jobs_repo.enqueue의 기본값(3)을 쓴다. max_attempts=1로 "재시도 없음"을 설정한
    스케줄이라도, 운영자가 '재시도'를 누른 순간부터는 조용히 최대 3회까지 자동
    재시도하게 된다 — 스케줄 정의가 명시한 정책과 어긋난다.
    """
    created = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(
            workflow_id, name="재시도 정책 확인", retry_policy={"max_attempts": 1}
        ),
        headers=_headers(admin_csrf),
    ).json()["schedule"]
    client.post(f"/api/admin/schedules/{created['id']}/enable", headers=_headers(admin_csrf))

    ctx = WorkerContext(
        settings=settings, clock=fake_clock, outbound_client=app.state.outbound_client
    )
    worker = Worker(
        app.state.session_factory, fake_clock, {"schedule_run": handle_schedule_run}, ctx
    )

    fake_http.on("http://127.0.0.1:5678/webhook/report", status=404)
    r = client.post(
        f"/api/admin/schedules/{created['id']}/run-now",
        json={},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200
    run_id = r.json()["run"]["id"]

    # max_attempts=1이므로 첫 시도 실패 즉시 영구 실패(추가 백오프 재시도 없음).
    worker.run_once()
    runs = client.get(
        f"/api/admin/schedules/{created['id']}/runs", headers=_headers(admin_csrf)
    ).json()
    assert runs["items"][0]["status"] == "failed"

    # 운영자가 재시도 — 새로 만들어지는 잡도 같은 스케줄의 max_attempts=1을 지켜야 한다.
    r = client.post(
        f"/api/admin/schedules/runs/{run_id}/retry", headers=_headers(admin_csrf)
    )
    assert r.status_code == 200

    fake_clock.advance(1)
    worker.run_once()  # 웹훅은 여전히 404 — max_attempts=1을 지켰다면 이 한 번으로 영구 실패해야 한다.

    runs = client.get(
        f"/api/admin/schedules/{created['id']}/runs", headers=_headers(admin_csrf)
    ).json()
    assert runs["items"][0]["status"] == "failed", (
        "재시도로 만든 잡이 스케줄의 max_attempts=1을 무시하고 기본값(3)으로 "
        "백오프 재시도에 들어갔다 — run이 'running'에 머물러 있다."
    )


def test_cancel_queued_run(client, admin_csrf, workflow_id, app, settings, fake_clock, fake_http):
    """M9 — 실행 상세(달력)는 run_id 만 갖고 있어 취소할 방법이 없었다.

    job_id 기준 취소(app/jobs/router.py)만 있고 ScheduleRun→job_id 매핑 경로가 없어
    '해결 불가'로 보고됐던 항목. run_id 로 직접 취소하는 엔드포인트를 신설했다.
    """
    created = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(workflow_id, name="취소 테스트"),
        headers=_headers(admin_csrf),
    ).json()["schedule"]
    client.post(f"/api/admin/schedules/{created['id']}/enable", headers=_headers(admin_csrf))

    r = client.post(
        f"/api/admin/schedules/{created['id']}/run-now",
        json={},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200
    run_id = r.json()["run"]["id"]

    # Worker 가 아직 안 돌았으니 대기(queued) 상태다 — 지금 취소한다.
    r = client.post(
        f"/api/admin/schedules/runs/{run_id}/cancel", headers=_headers(admin_csrf)
    )
    assert r.status_code == 200
    assert r.json()["run"]["status"] == "skipped"

    runs = client.get(
        f"/api/admin/schedules/{created['id']}/runs", headers=_headers(admin_csrf)
    ).json()
    assert runs["items"][0]["status"] == "skipped"

    # 연결된 잡도 함께 취소돼, 워커가 나중에 돌아도 이 run 을 다시 처리하지 않는다.
    ctx = WorkerContext(
        settings=settings, clock=fake_clock, outbound_client=app.state.outbound_client
    )
    worker = Worker(
        app.state.session_factory, fake_clock, {"schedule_run": handle_schedule_run}, ctx
    )
    fake_clock.advance(1)
    processed = worker.run_once()
    assert processed is False  # 취소된 잡은 더 이상 대기 상태가 아니라 워커가 집을 게 없다

    # 이미 끝난(skipped) 실행을 또 취소하면 거부된다.
    r = client.post(
        f"/api/admin/schedules/runs/{run_id}/cancel", headers=_headers(admin_csrf)
    )
    assert r.status_code == 409


def test_cancel_run_rejects_unknown_run(client, admin_csrf):
    r = client.post(
        "/api/admin/schedules/runs/does-not-exist/cancel", headers=_headers(admin_csrf)
    )
    assert r.status_code == 404


def test_write_workflow_with_approval_rejected_at_create(client, admin_csrf):
    # 승인이 필요한 write workflow를 스케줄로 자동 실행하면 매번 반드시 실패한다(스케줄 실행에는
    # payload.approved를 채울 사람이 없다) — 절대 성공할 수 없는 조합이므로 예전처럼 생성을 허용해
    # 런타임에 조용히 실패시키지 않고, 정의 시점(create)에 명확히 거부한다.
    wf = client.post(
        "/api/admin/workflows",
        json={
            "name": "승인 필요 write",
            "webhook_url": "http://127.0.0.1:5678/webhook/write-op",
            "operation_mode": "write",
            "approval_required": True,
        },
        headers=_headers(admin_csrf),
    ).json()["workflow"]

    r = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(wf["id"], name="승인 필요 스케줄"),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422
    assert "승인" in r.json()["error"]["message"]


def test_write_workflow_with_approval_rejected_at_edit(client, admin_csrf, workflow_id):
    # 정상 워크플로로 생성한 스케줄을 이후 승인 필요 write workflow로 수정하려는 시도도 같은 이유로 막는다.
    created = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(workflow_id, name="정상 스케줄"),
        headers=_headers(admin_csrf),
    ).json()["schedule"]

    wf = client.post(
        "/api/admin/workflows",
        json={
            "name": "승인 필요 write 2",
            "webhook_url": "http://127.0.0.1:5678/webhook/write-op-2",
            "operation_mode": "write",
            "approval_required": True,
        },
        headers=_headers(admin_csrf),
    ).json()["workflow"]

    r = client.put(
        f"/api/admin/schedules/{created['id']}",
        json=_schedule_payload(wf["id"], name="정상 스케줄"),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422
    assert "승인" in r.json()["error"]["message"]


def test_schedule_rbac(client, login_as):
    login_as("user")
    assert client.get("/api/admin/schedules").status_code == 403
