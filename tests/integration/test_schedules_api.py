"""qa-contract-change: 스케줄 대상이 workflow·system 둘에서 system 하나가 됐다(D-267). 워크플로 전용 가드 셋(승인 필요 write 거부·채팅 전용 워크플로 거부 세 갈래)은 그 대상 종류와 함께 사라졌다. 대신 end-to-end 시험이 「이 레인은 아무 데도 HTTP 를 안 보낸다」를 새로 못 박고, max_attempts 시험은 잡을 간접적으로 실패시키는 대신 잡 행의 max_attempts 를 직접 본다."""

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


def _fail_the_run(app, run_id, now):
    """실행 행 하나를 실패 상태로 만든다.

    예전에는 가짜 웹훅이 404 를 주게 해서 실제로 실패시켰다. S11 이후 `system` 대상은
    아웃바운드가 없어 언제나 성공하므로 상태를 직접 만든다 — 아래 시험들이 지키는 것은
    **어떻게 실패했는가**가 아니라 재시도·취소·정책이 그 실패를 어떻게 다루는가다.
    """
    from app.jobs.models import STATUS_FAILED as JOB_FAILED
    from app.jobs.models import Job
    from app.schedules.models import RUN_FAILED, ScheduleRun

    with app.state.session_factory() as s:
        run = s.get(ScheduleRun, run_id)
        run.status = RUN_FAILED
        run.started_at = run.started_at or now
        run.finished_at = now
        run.error_message = "테스트가 만든 실패"
        s.execute(
            Job.__table__.update()
            .where(Job.payload_json["schedule_run_id"].astext == run_id)
            .values(status=JOB_FAILED, finished_at=now, last_error="테스트가 만든 실패")
        )
        s.commit()


# S11 이후 스케줄 대상은 `system` 하나다(D-267). 이름은 그대로 두어 diff 가 「대상이
# 바뀌었다」만 말하게 한다.
@pytest.fixture()
def workflow_id():
    return "noop"


def _schedule_payload(workflow_id, **overrides):
    return {
        "name": "매시 보고서",
        "schedule_type": "cron",
        "cron_expression": "0 * * * *",
        "timezone": "UTC",
        "target_type": "system",
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


def test_create_accepts_null_timezone_and_timeout_seconds(client, admin_csrf, workflow_id):
    """UX-41: misfire_policy/concurrency_policy는 이미 null 코어싱이 있는데(위 시험),
    같은 폼의 timezone/timeout_seconds 두 칸은 빠져 있었다 — 콘솔이 지워진 선택 칸을
    명시적 null로 보내면 스키마 기본값(Asia/Seoul, 180초) 대신 422가 났다."""
    r = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(workflow_id, timezone=None, timeout_seconds=None),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 201, r.text
    body = r.json()["schedule"]
    assert body["timezone"] == "Asia/Seoul"
    assert body["timeout_seconds"] == 180


def test_create_still_rejects_invalid_misfire_policy(client, admin_csrf, workflow_id):
    r = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(workflow_id, misfire_policy="bogus"),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422


def test_list_target_name_is_null_for_system_target(client, admin_csrf):
    client.post(
        "/api/admin/schedules",
        json=_schedule_payload(None, name="시스템 대상", target_type="system", target_ref="noop"),
        headers=_headers(admin_csrf),
    )
    r = client.get("/api/admin/schedules")
    row = next(i for i in r.json()["items"] if i["name"] == "시스템 대상")
    assert row["target_type"] == "system"
    assert row["target_name"] is None


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

    # S11 이후 이 레인은 **아무 데도 HTTP 를 안 보낸다** — 그것 자체를 못 박는다.
    assert fake_http.requests == []

    from app.schedules.models import ScheduleRun

    db.query(ScheduleRun).filter(ScheduleRun.schedule_id == created["id"]).one()

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
    assert "noop" in runs["items"][0]["response_summary"]


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

    r = client.post(
        f"/api/admin/schedules/{created['id']}/run-now",
        json={},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200
    run_id = r.json()["run"]["id"]
    _fail_the_run(app, run_id, fake_clock.now())

    runs = client.get(
        f"/api/admin/schedules/{created['id']}/runs", headers=_headers(admin_csrf)
    ).json()
    assert runs["items"][0]["status"] == "failed"

    # 운영자가 실패한 run 을 재시도한다 — 이번에는 성공한다.
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
    client, admin_csrf, workflow_id, app, fake_clock
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

    r = client.post(
        f"/api/admin/schedules/{created['id']}/run-now",
        json={},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200
    run_id = r.json()["run"]["id"]
    _fail_the_run(app, run_id, fake_clock.now())
    runs = client.get(
        f"/api/admin/schedules/{created['id']}/runs", headers=_headers(admin_csrf)
    ).json()
    assert runs["items"][0]["status"] == "failed"

    # 운영자가 재시도 — 새로 만들어지는 잡도 같은 스케줄의 max_attempts=1을 지켜야 한다.
    r = client.post(
        f"/api/admin/schedules/runs/{run_id}/retry", headers=_headers(admin_csrf)
    )
    assert r.status_code == 200

    # 재시도로 만들어진 **잡**이 스케줄의 max_attempts=1 을 물려받았는가. 이것이 이
    # 시험의 전부다 — 예전에는 잡을 실제로 실패시켜 간접적으로 봤는데, 그 방법은 실행
    # 경로가 바뀌면 같이 깨진다. 잡 행을 직접 본다.
    from app.jobs.models import Job

    with app.state.session_factory() as s:
        job = s.execute(
            Job.__table__.select().where(
                Job.payload_json["schedule_run_id"].astext == run_id,
                Job.status.in_(("queued", "running")),
            )
        ).mappings().one()
    assert job["max_attempts"] == 1, (
        "재시도로 만든 잡이 스케줄의 max_attempts=1을 무시하고 기본값(3)을 썼다."
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


# 워크플로 대상 전용 가드(승인 필요 write 거부 · 채팅 전용 워크플로 거부)는 S11 이
# 워크플로 대상 자체를 걷어내면서 함께 사라졌다. 지금 남은 방어는 더 단순하다:
# **아는 system 대상이 아니면 정의 시점에 거부한다** — `test_create_validates_target`
# 가 그것을 본다.
