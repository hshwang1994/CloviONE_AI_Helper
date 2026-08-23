"""qa-contract-change: 발행 승인이 「승인자가 본 그 문서」를 발행한다는 절 넷이 S11 과 함께 사라졌다. 재시도 게이트 쪽 셋은 그대로이고, 실패한 run 을 만드는 방법만 바꿨다 — system 대상은 아웃바운드가 없어 언제나 성공하므로 상태를 직접 만든다. 그 절이 지키는 것은 실패 방식이 아니라 누가 어떤 조건에서 재시도할 수 있는가다."""

"""Regression tests pinned to the iteration-4 review findings.

각 테스트는 고쳐진 코드 경로가 아니라 결함 진술 그 자체를 재현한다.
"""


import pytest


pytestmark = pytest.mark.regression


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


# --- 1 & 5. retry_run: 실행 게이트와 소요시간 ---------------------------------

# S11 이후 스케줄 대상은 `system` 하나다(D-267). 이 절이 지키는 것은 대상 종류가 아니라
# **재시도 게이트와 소요시간 계산**이므로 대상만 바꾼다.
@pytest.fixture()
def sched_target():
    return "noop"


@pytest.fixture()
def sched_worker(app, settings, fake_clock):
    from app.jobs.handlers.schedule_run import handle_schedule_run
    from app.jobs.worker import Worker, WorkerContext

    ctx = WorkerContext(
        settings=settings, clock=fake_clock, outbound_client=app.state.outbound_client
    )
    return Worker(
        app.state.session_factory, fake_clock, {"schedule_run": handle_schedule_run}, ctx
    )


def _make_schedule(client, csrf, target_ref, name, **overrides):
    return client.post(
        "/api/admin/schedules",
        json={
            "name": name,
            "schedule_type": "cron",
            "cron_expression": "0 * * * *",
            "timezone": "UTC",
            "target_type": "system",
            "target_ref": target_ref,
            "payload_template": {"scope": "all"},
            **overrides,
        },
        headers=_headers(csrf),
    ).json()["schedule"]


def _failed_run(client, csrf, schedule, app, fake_clock):
    """실행 게이트를 통과한 스케줄에 **실패한 run** 을 하나 만든다.

    예전에는 가짜 웹훅이 500 을 주게 해서 실제로 실패시켰다. S11 이후 `system` 대상은
    아웃바운드가 없어 언제나 성공하므로, 실패 상태를 직접 만든다 — 이 절이 지키는 것은
    **어떻게 실패했는가**가 아니라 «실패한 run 을 누가 어떤 조건에서 재시도할 수
    있는가»다. 실패 경로 자체는 `schedule_run` 핸들러 시험이 따로 본다.
    """
    from app.jobs.models import STATUS_FAILED as JOB_FAILED
    from app.jobs.models import Job
    from app.schedules.models import RUN_FAILED, ScheduleRun

    run_id = client.post(
        f"/api/admin/schedules/{schedule['id']}/run-now", json={}, headers=_headers(csrf)
    ).json()["run"]["id"]
    with app.state.session_factory() as s:
        run = s.get(ScheduleRun, run_id)
        run.status = RUN_FAILED
        run.started_at = fake_clock.now()
        run.finished_at = fake_clock.now()
        run.error_message = "테스트가 만든 실패"
        job = s.execute(
            Job.__table__.select().where(
                Job.payload_json["schedule_run_id"].astext == run_id
            )
        ).mappings().first()
        if job is not None:
            s.execute(
                Job.__table__.update().where(Job.id == job["id"]).values(
                    status=JOB_FAILED, finished_at=fake_clock.now(), last_error="테스트가 만든 실패"
                )
            )
        s.commit()
    runs = client.get(
        f"/api/admin/schedules/{schedule['id']}/runs", headers=_headers(csrf)
    ).json()["items"]
    assert runs[0]["status"] == "failed"
    return run_id


def test_operator_cannot_retry_a_run_of_a_disabled_schedule(
    client, login_as, sched_target, sched_worker, app, fake_clock, db
):
    """High: retry_run이 run-now의 승인 게이트를 통째로 우회하던 결함.

    운영자가 비활성(=승인받지 않은) 정의를 재시도로 그대로 실행할 수 있었다.
    """
    sys_csrf = login_as("system_admin", email="r4-retry-gate@goodmit.co.kr")
    schedule = _make_schedule(client, sys_csrf, sched_target, "재시도 게이트")
    client.post(
        f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(sys_csrf)
    )
    run_id = _failed_run(client, sys_csrf, schedule, app, fake_clock)

    # 스케줄이 비활성으로 내려간다 — 이 정의는 더 이상 승인된 상태가 아니다.
    client.post(
        f"/api/admin/schedules/{schedule['id']}/disable", headers=_headers(sys_csrf)
    )

    operator_csrf = login_as("operator", email="r4-operator@goodmit.co.kr")
    from app.jobs.models import Job

    jobs_before = db.query(Job).count()

    r = client.post(
        f"/api/admin/schedules/runs/{run_id}/retry", headers=_headers(operator_csrf)
    )
    assert r.status_code == 409

    db.expire_all()
    assert db.query(Job).count() == jobs_before  # 재시도 job이 큐에 들어가지 않았다.
    runs = client.get(
        f"/api/admin/schedules/{schedule['id']}/runs", headers=_headers(operator_csrf)
    ).json()["items"]
    assert runs[0]["status"] == "failed"  # 실패한 채로 남는다 (queued로 되살아나지 않음).


def test_retry_cannot_run_a_definition_that_lost_its_approval(
    client, login_as, sched_target, sched_worker, app, fake_clock, db
):
    """High: 승인 후 PUT으로 정의를 갈아끼우면 enabled가 내려가는데(이전 라운드 수정),
    retry는 그 게이트를 보지 않아 승인받은 적 없는 정의로 실행할 수 있었다."""
    admin_csrf = login_as("admin", email="r4-retry-put@goodmit.co.kr")
    schedule = _make_schedule(client, admin_csrf, sched_target, "정의 교체 재시도")

    # 승인 없이 활성화된 상태를 만들기 위해 system_admin이 활성화해 준다.
    sys_csrf = login_as("system_admin", email="r4-retry-put-sys@goodmit.co.kr")
    client.post(
        f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(sys_csrf)
    )
    run_id = _failed_run(client, sys_csrf, schedule, app, fake_clock)

    # 요청자(admin)가 정의를 바꾸면 승인 게이트가 활성 상태를 내린다.
    admin_csrf = login_as("admin", email="r4-retry-put@goodmit.co.kr")
    put = client.put(
        f"/api/admin/schedules/{schedule['id']}",
        json={
            "name": "정의 교체 재시도",
            "schedule_type": "cron",
            "cron_expression": "* * * * *",
            "timezone": "UTC",
            "target_type": "system",
            "target_ref": sched_target,
            "payload_template": {"scope": "everything", "delete": True},
        },
        headers=_headers(admin_csrf),
    )
    assert put.status_code == 200
    assert put.json()["schedule"]["enabled"] is False

    r = client.post(
        f"/api/admin/schedules/runs/{run_id}/retry", headers=_headers(admin_csrf)
    )
    assert r.status_code == 409


def test_retry_resets_the_duration_of_the_previous_failed_attempt(
    client, login_as, sched_target, sched_worker, app, fake_clock
):
    """Low: 재시도가 started_at을 초기화하지 않아 소요시간에 이전 실패 시도가
    포함돼 표시되던 결함."""
    sys_csrf = login_as("system_admin", email="r4-duration@goodmit.co.kr")
    schedule = _make_schedule(client, sys_csrf, sched_target, "소요시간")
    client.post(
        f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(sys_csrf)
    )
    run_id = _failed_run(client, sys_csrf, schedule, app, fake_clock)

    runs = client.get(
        f"/api/admin/schedules/{schedule['id']}/runs", headers=_headers(sys_csrf)
    ).json()["items"]
    first_started_at = runs[0]["started_at"]
    assert first_started_at is not None

    # 한참 뒤에 재시도한다 (세션 유휴 만료 시간을 넘기므로 다시 로그인한다).
    fake_clock.advance(3600)
    sys_csrf = login_as("system_admin", email="r4-duration@goodmit.co.kr")
    r = client.post(
        f"/api/admin/schedules/runs/{run_id}/retry", headers=_headers(sys_csrf)
    )
    assert r.status_code == 200
    # 아직 시작하지 않은 실행 — 이전 시도의 시작 시각을 물려받지 않는다.
    assert r.json()["run"]["started_at"] is None

    sched_worker.run_once()

    runs = client.get(
        f"/api/admin/schedules/{schedule['id']}/runs", headers=_headers(sys_csrf)
    ).json()["items"]
    assert runs[0]["status"] == "succeeded"
    # 소요시간은 이번 시도만 센다 — 1시간 전 실패 시도부터 재지 않는다.
    assert runs[0]["started_at"] > first_started_at


# --- 4. 만료 판정은 목록과 상세가 같아야 한다 --------------------------------


def test_expired_approval_reads_the_same_in_the_list_and_the_detail(
    client, login_as, sched_target, fake_clock
):
    """Low: 같은 승인이 목록에서는 expired, 상세에서는 pending으로 보이던 결함."""
    csrf = login_as("admin", email="r4-expiry@goodmit.co.kr")
    schedule = _make_schedule(client, csrf, sched_target, "만료 표시")
    approval = client.post(
        f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(csrf)
    ).json()["approval"]

    from app.approvals.models import DEFAULT_EXPIRY_HOURS

    fake_clock.advance(DEFAULT_EXPIRY_HOURS * 3600 + 1)
    csrf = login_as("admin", email="r4-expiry@goodmit.co.kr")  # 세션 유휴 만료 → 재로그인

    listed = client.get("/api/admin/approvals", headers=_headers(csrf)).json()["items"]
    listed_row = [row for row in listed if row["id"] == approval["id"]][0]
    detail = client.get(
        f"/api/admin/approvals/{approval['id']}", headers=_headers(csrf)
    ).json()["approval"]

    assert listed_row["status"] == "expired"
    assert detail["status"] == listed_row["status"]


def test_pending_approval_still_reads_as_pending_in_the_detail(
    client, login_as, sched_target
):
    """만료 전에는 그대로 pending — 만료 판정이 과하게 적용되지 않는다."""
    csrf = login_as("admin", email="r4-pending@goodmit.co.kr")
    schedule = _make_schedule(client, csrf, sched_target, "대기 표시")
    approval = client.post(
        f"/api/admin/schedules/{schedule['id']}/enable", headers=_headers(csrf)
    ).json()["approval"]

    detail = client.get(
        f"/api/admin/approvals/{approval['id']}", headers=_headers(csrf)
    ).json()["approval"]
    assert detail["status"] == "pending"
