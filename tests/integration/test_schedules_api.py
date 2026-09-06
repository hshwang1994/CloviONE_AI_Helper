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


# ─────────────────────────────────────────────────────────────────────────────
# 정의를 지키는 규칙 — 저장되면 안 되는 값은 저장 시점에 막는다
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "bad", ["abc", [1], 3.5, 0, -1, 999, True, None, "3"]
)
def test_retry_policy_max_attempts_must_be_an_int_in_range(
    client, admin_csrf, workflow_id, bad
):
    """읽을 수 없는 재시도 횟수는 **저장 시점에** 막는다.

    예전에는 그대로 저장돼 활성화까지 됐고, 실행할 때마다 `int("abc")` 가 터졌다 —
    수동 실행은 500, 자동 실행은 로그 한 줄. 폼 도움말이 이미 약속한 범위(1~10)를
    서버가 같은 자리에서 지킨다.
    """
    r = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(
            workflow_id, name=f"나쁜 재시도 {bad!r}", retry_policy={"max_attempts": bad}
        ),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422, r.text


@pytest.mark.parametrize("good", [1, 3, 10])
def test_retry_policy_in_range_is_still_accepted(client, admin_csrf, workflow_id, good):
    """반례 — 규칙 안의 값은 그대로 통과해야 한다(검증이 문을 잠가 버리면 안 된다)."""
    r = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(
            workflow_id, name=f"좋은 재시도 {good}", retry_policy={"max_attempts": good}
        ),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 201, r.text
    assert r.json()["schedule"]["retry_policy"] == {"max_attempts": good}


def test_retry_policy_without_max_attempts_is_still_accepted(
    client, admin_csrf, workflow_id
):
    """반례 — 재시도 정책은 선택 입력이다. 빈 객체와 다른 키는 그대로 저장된다."""
    r = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(workflow_id, name="빈 재시도 정책", retry_policy={}),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 201, r.text
    assert r.json()["schedule"]["retry_policy"] == {}


def test_blank_name_is_rejected(client, admin_csrf, workflow_id):
    """공백만의 이름은 422 다. `min_length=1` 은 공백도 한 자로 세어 통과시켰고, 그렇게
    만들어진 행은 목록에서도 검색에서도 지목할 수 없었다(스케줄에는 삭제가 없다)."""
    r = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(workflow_id, name="   "),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422, r.text


def test_name_keeps_its_text_and_loses_only_the_padding(client, admin_csrf, workflow_id):
    """반례 — 앞뒤 공백만 떼고 이름 자체는 그대로 저장된다."""
    r = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(workflow_id, name="  여백 있는 이름  "),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 201, r.text
    assert r.json()["schedule"]["name"] == "여백 있는 이름"


def test_past_end_at_is_rejected_at_create(client, admin_csrf, workflow_id):
    """유효 기간이 이미 끝난 일정은 만들 수 없다.

    예전에는 201 이었고 활성화까지 돼 목록이 영영 오지 않을 '다음 실행'을 약속했다.
    """
    r = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(
            workflow_id, name="지난 기간",
            start_at="2020-01-01T00:00:00", end_at="2020-02-01T00:00:00",
        ),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422, r.text
    assert "종료" in r.json()["error"]["message"]


def test_future_end_at_is_still_accepted(client, admin_csrf, workflow_id):
    """반례 — 앞으로 끝나는 유효 기간은 그대로 만들 수 있다(FakeClock 기준 2026-07-14)."""
    r = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(
            workflow_id, name="살아 있는 기간", end_at="2026-12-31T23:59:59"
        ),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 201, r.text


def test_an_already_expired_row_stays_editable_but_cannot_be_enabled(
    client, admin_csrf, db, workflow_id
):
    """이미 지난 종료 시각을 들고 있는 행은 **고칠 수 있어야** 한다 — 그 값을 고치는
    유일한 길이 수정이기 때문이다. 다만 그 상태로 활성화는 거절한다."""
    from datetime import datetime

    from app.schedules.models import Schedule

    row = Schedule(
        name="기간 끝난 일정", schedule_type="cron", cron_expression="0 * * * *",
        timezone="UTC", target_type="system", target_ref="noop",
        payload_template_json="{}", enabled=False,
        end_at=datetime(2020, 2, 1, 0, 0, 0),
    )
    db.add(row)
    db.commit()
    row_id = row.id

    keep = _schedule_payload(
        workflow_id, name="기간 끝난 일정", timezone="UTC",
        description="설명만 고친다", end_at="2020-02-01T00:00:00",
        payload_template={},
    )
    r = client.put(
        f"/api/admin/schedules/{row_id}", json=keep, headers=_headers(admin_csrf)
    )
    assert r.status_code == 200, r.text
    assert r.json()["schedule"]["description"] == "설명만 고친다"

    enabled = client.post(
        f"/api/admin/schedules/{row_id}/enable", headers=_headers(admin_csrf)
    )
    assert enabled.status_code == 409, enabled.text

    db.expire_all()
    assert db.get(Schedule, row_id).enabled is False


def test_put_keeps_a_target_ref_that_is_no_longer_offered(client, admin_csrf, db):
    """대상 어휘가 좁아지기 전에 만들어진 행도 **설명 한 줄은 고칠 수 있어야** 한다.

    예전에는 create 와 같은 화이트리스트를 update 에도 걸어, 저장된 값을 그대로 실어
    보내는 수정이 언제나 422 였다 — 유일하게 저장 가능한 선택이 '이 일정이 하는 일
    바꾸기'였다.
    """
    from app.schedules.models import Schedule

    row = Schedule(
        name="옛 대상 일정", schedule_type="cron", cron_expression="0 2 * * *",
        timezone="UTC", target_type="system", target_ref="ai.summarize",
        payload_template_json="{}", enabled=False,
    )
    db.add(row)
    db.commit()
    row_id = row.id

    body = _schedule_payload(
        "ai.summarize", name="옛 대상 일정", cron_expression="0 2 * * *",
        timezone="UTC", description="오타를 고쳤다", payload_template={},
    )
    r = client.put(
        f"/api/admin/schedules/{row_id}", json=body, headers=_headers(admin_csrf)
    )
    assert r.status_code == 200, r.text
    assert r.json()["schedule"]["description"] == "오타를 고쳤다"
    assert r.json()["schedule"]["target_ref"] == "ai.summarize"


def test_put_still_refuses_a_new_unknown_target(client, admin_csrf, db):
    """반례 — 저장된 값을 봐준다고 해서 **새 값**으로 옮겨 갈 수 있는 것은 아니다."""
    from app.schedules.models import Schedule

    row = Schedule(
        name="옛 대상 일정 2", schedule_type="cron", cron_expression="0 2 * * *",
        timezone="UTC", target_type="system", target_ref="ai.summarize",
        payload_template_json="{}", enabled=False,
    )
    db.add(row)
    db.commit()

    body = _schedule_payload(
        "ai.rewrite", name="옛 대상 일정 2", cron_expression="0 2 * * *",
        timezone="UTC", payload_template={},
    )
    r = client.put(
        f"/api/admin/schedules/{row.id}", json=body, headers=_headers(admin_csrf)
    )
    assert r.status_code == 422, r.text
    # 오류 문구에 파이썬 리스트 표기가 새지 않는다.
    assert "[" not in r.json()["error"]["message"]


@pytest.mark.parametrize(
    "field, value",
    [
        ("enabled", True),
        ("owner_user_id", "00000000-0000-0000-0000-000000000000"),
        ("next_run_at", "2030-01-01T00:00:00"),
        ("last_run_at", "2030-01-01T00:00:00"),
        ("id", "hijacked"),
    ],
)
def test_put_rejects_column_named_unknown_fields(
    client, admin_csrf, workflow_id, field, value
):
    """컬럼 이름과 같은 미지 필드를 조용히 버리지 않는다.

    보낸 쪽은 200 을 받고 그 값이 반영됐다고 믿는다 — 반영되지 않았다는 것을 알 방법이
    응답 어디에도 없었다.
    """
    created = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(workflow_id, name=f"미지 필드 {field}"),
        headers=_headers(admin_csrf),
    ).json()["schedule"]

    body = _schedule_payload(workflow_id, name=f"미지 필드 {field}")
    body[field] = value
    r = client.put(
        f"/api/admin/schedules/{created['id']}", json=body, headers=_headers(admin_csrf)
    )
    assert r.status_code == 422, r.text


def test_put_without_unknown_fields_still_saves(client, admin_csrf, workflow_id):
    """반례 — 스키마가 아는 필드만 담은 수정은 그대로 200 이고 값이 실제로 바뀐다."""
    created = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(
            workflow_id, name="정상 수정", retry_policy={"max_attempts": 5},
            timeout_seconds=120,
        ),
        headers=_headers(admin_csrf),
    ).json()["schedule"]

    r = client.put(
        f"/api/admin/schedules/{created['id']}",
        json=_schedule_payload(
            workflow_id, name="정상 수정", description="바뀐 설명",
            retry_policy={"max_attempts": 5}, timeout_seconds=120,
        ),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200, r.text
    body = r.json()["schedule"]
    assert body["description"] == "바뀐 설명"
    assert body["retry_policy"] == {"max_attempts": 5}
    assert body["timeout_seconds"] == 120


# ─────────────────────────────────────────────────────────────────────────────
# 낙관적 잠금 — 나중 저장이 앞 저장을 조용히 덮지 않는다
# ─────────────────────────────────────────────────────────────────────────────


def test_stale_base_version_is_refused(client, admin_csrf, workflow_id):
    created = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(workflow_id, name="두 탭"),
        headers=_headers(admin_csrf),
    ).json()["schedule"]
    opened_at = created["base_version"]
    assert opened_at

    first = client.put(
        f"/api/admin/schedules/{created['id']}",
        json=_schedule_payload(
            workflow_id, name="두 탭", description="탭 A", base_version=opened_at
        ),
        headers=_headers(admin_csrf),
    )
    assert first.status_code == 200, first.text

    # 탭 B 는 열었을 때의 낡은 판을 들고 있다 — 앞 저장을 덮지 않는다.
    second = client.put(
        f"/api/admin/schedules/{created['id']}",
        json=_schedule_payload(
            workflow_id, name="두 탭", description="탭 B", base_version=opened_at
        ),
        headers=_headers(admin_csrf),
    )
    assert second.status_code == 409, second.text

    current = client.get(f"/api/admin/schedules/{created['id']}").json()["schedule"]
    assert current["description"] == "탭 A"


def test_fresh_base_version_saves_and_no_base_version_still_saves(
    client, admin_csrf, workflow_id
):
    """반례 둘 — 최신 판을 실으면 저장되고, 아예 안 보내면 예전대로 저장된다
    (새 계약을 강제해 기존 클라이언트를 깨뜨리지 않는다)."""
    created = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(workflow_id, name="최신 판"),
        headers=_headers(admin_csrf),
    ).json()["schedule"]

    r = client.put(
        f"/api/admin/schedules/{created['id']}",
        json=_schedule_payload(
            workflow_id, name="최신 판", description="첫 저장",
            base_version=created["base_version"],
        ),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200, r.text
    assert r.json()["schedule"]["base_version"] != created["base_version"]

    r2 = client.put(
        f"/api/admin/schedules/{created['id']}",
        json=_schedule_payload(workflow_id, name="최신 판", description="판 없이 저장"),
        headers=_headers(admin_csrf),
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["schedule"]["description"] == "판 없이 저장"


def test_create_refuses_a_base_version(client, admin_csrf, workflow_id):
    """만들 것에는 앞 판이 없다 — 조용히 버리면 보낸 쪽은 잠금이 걸렸다고 믿는다."""
    r = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(workflow_id, name="판 실은 생성", base_version="2026-01-01T00:00:00"),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422, r.text


# ─────────────────────────────────────────────────────────────────────────────
# 범위 — 전사 실행 일정은 전체 범위 관리자만 바꾼다
# ─────────────────────────────────────────────────────────────────────────────


def _dept_scoped_admin(app, db, email="dept-admin-sched@goodmit.co.kr"):
    """부서 범위 관리자를 만든다(role=admin, admin_scope=dept)."""
    from app.org.models import Department
    from app.users.models import ADMIN_SCOPE_DEPT, User
    from app.users.service import create_user
    from tests.conftest import DEFAULT_TEST_PASSWORD

    dept = Department(name="일정 범위 시험 부서", active=True)
    db.add(dept)
    db.commit()
    user = create_user(
        db, email=email, display_name="부서 관리자",
        password=DEFAULT_TEST_PASSWORD, settings=app.state.settings,
        actor_role="system_admin", role="admin", must_change_password=False,
    )
    row = db.get(User, user.id)
    row.admin_scope = ADMIN_SCOPE_DEPT
    row.scope_dept_id = dept.id
    row.department_id = dept.id
    db.commit()
    return email


def test_department_scoped_admin_cannot_write_global_schedules(
    app, client, db, admin_csrf, workflow_id
):
    """부서 범위 관리자는 전사 실행 일정을 만들지도 끄지도 못한다.

    역할 게이트(CONSOLE_WRITE_ROLES)만으로는 그대로 지나갔다 — 부서로 나눌 수 없는
    자원을 부서 관리자가 승인 없이 껐다.
    """
    from tests.conftest import DEFAULT_TEST_PASSWORD

    existing = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(workflow_id, name="전사 야간 배치"),
        headers=_headers(admin_csrf),
    ).json()["schedule"]

    email = _dept_scoped_admin(app, db)
    relogin = client.post(
        "/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD}
    )
    assert relogin.status_code == 200, relogin.text
    dept_csrf = relogin.json()["csrf_token"]

    created = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(workflow_id, name="부서 관리자가 만든 일정"),
        headers=_headers(dept_csrf),
    )
    assert created.status_code == 403, created.text

    disabled = client.post(
        f"/api/admin/schedules/{existing['id']}/disable", headers=_headers(dept_csrf)
    )
    assert disabled.status_code == 403, disabled.text

    updated = client.put(
        f"/api/admin/schedules/{existing['id']}",
        json=_schedule_payload(workflow_id, name="전사 야간 배치", description="남의 일정"),
        headers=_headers(dept_csrf),
    )
    assert updated.status_code == 403, updated.text

    enabled = client.post(
        f"/api/admin/schedules/{existing['id']}/enable", headers=_headers(dept_csrf)
    )
    assert enabled.status_code == 403, enabled.text

    # 거절된 **쓰기** 시도는 감사 원장에 남는다(읽기 거절은 남기지 않는다).
    from app.audit.models import AuditLog

    db.expire_all()
    refusals = (
        db.query(AuditLog)
        .filter(AuditLog.object_type == "schedule", AuditLog.result == "failure")
        .all()
    )
    assert {r.action for r in refusals} == {
        "schedule.create", "schedule.update", "schedule.enable", "schedule.disable",
    }

    # 읽기는 그대로 열린다 — 범위 판정은 쓰기에만 건다.
    assert client.get("/api/admin/schedules").status_code == 200


def test_global_admin_still_writes_schedules(client, admin_csrf, workflow_id):
    """반례 — 전체 범위 관리자에게는 아무것도 달라지지 않는다."""
    created = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(workflow_id, name="전역 관리자 일정"),
        headers=_headers(admin_csrf),
    )
    assert created.status_code == 201, created.text
    sid = created.json()["schedule"]["id"]
    assert client.post(
        f"/api/admin/schedules/{sid}/enable", headers=_headers(admin_csrf)
    ).status_code == 200
    assert client.post(
        f"/api/admin/schedules/{sid}/disable", headers=_headers(admin_csrf)
    ).status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 활성화 게이트는 승인 경로에도 걸린다 (R3-01)
# ─────────────────────────────────────────────────────────────────────────────


def _expired_window_row(db, name="기간 끝난 전사 배치"):
    """유효 기간이 이미 끝난 행 — API 로는 만들 수 없어서 직접 넣는다."""
    from datetime import datetime

    from app.schedules.models import Schedule

    row = Schedule(
        name=name, schedule_type="cron", cron_expression="0 * * * *",
        timezone="UTC", target_type="system", target_ref="noop",
        payload_template_json="{}", enabled=False,
        end_at=datetime(2020, 2, 1, 0, 0, 0),
    )
    db.add(row)
    db.commit()
    return row.id


def test_an_expired_window_is_refused_before_an_approval_is_ever_created(
    client, login_as, db, workflow_id
):
    """활성화 판정이 승인 분기 **뒤**에 있으면 사실상 아무도 그 판정을 지나지 않는다.

    승인이 필요한 사람은 `system_admin` 이 아닌 **모든** 관리자다. 판정이 직접 적용 쪽에만
    있으면 전역 관리자가 누른 활성화는 202 로 승인 대기가 되고, 승인 실행기는 같은 판정을
    갖고 있지 않아 결국 켠다 — 같은 일정을 system_admin 이 켜면 409 인데 관리자가 켜면
    켜지는, 답이 둘인 상태가 된다.
    """
    from app.approvals.models import Approval
    from app.schedules.models import Schedule

    row_id = _expired_window_row(db)
    csrf = login_as("admin", email="window-asker@goodmit.co.kr")

    r = client.post(f"/api/admin/schedules/{row_id}/enable", headers=_headers(csrf))
    assert r.status_code == 409, r.text
    assert "유효 기간" in r.json()["error"]["message"]

    # 승인 요청 자체가 만들어지지 않는다 — 승인자에게 적용될 수 없는 결재를 보내지 않는다.
    db.expire_all()
    assert (
        db.query(Approval).filter(Approval.object_id == row_id).count() == 0
    ), "적용될 수 없는 활성화로 승인 요청이 만들어졌다"
    assert db.get(Schedule, row_id).enabled is False


def test_a_live_window_still_walks_the_whole_approval_path(
    app, client, login_as, db, workflow_id
):
    """반례 — 유효 기간이 살아 있는 일정은 예전 그대로 승인 요청이 되고, 승인되면 켜진다.

    R3-01 의 수정이 승인 경로 자체를 막아 버리지 않았다는 것을 끝까지 걸어서 확인한다.
    """
    from fastapi.testclient import TestClient

    from app.schedules.models import Schedule
    from app.users.service import create_user
    from tests.conftest import DEFAULT_TEST_PASSWORD

    requester_csrf = login_as("admin", email="live-window-asker@goodmit.co.kr")
    created = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(
            workflow_id, name="살아 있는 전사 배치", end_at="2026-12-31T23:59:59"
        ),
        headers=_headers(requester_csrf),
    )
    assert created.status_code == 201, created.text
    schedule_id = created.json()["schedule"]["id"]

    pending = client.post(
        f"/api/admin/schedules/{schedule_id}/enable", headers=_headers(requester_csrf)
    )
    assert pending.status_code == 202, pending.text
    approval_id = pending.json()["approval"]["id"]

    create_user(
        db, email="window-approver@goodmit.co.kr", display_name="승인자",
        password=DEFAULT_TEST_PASSWORD, settings=app.state.settings,
        actor_role="system_admin", role="admin", must_change_password=False,
    )
    db.commit()
    with TestClient(app, raise_server_exceptions=False) as approver:
        login = approver.post(
            "/login",
            json={
                "email": "window-approver@goodmit.co.kr",
                "password": DEFAULT_TEST_PASSWORD,
            },
        )
        approver_csrf = login.json()["csrf_token"]
        decided = approver.post(
            f"/api/admin/approvals/{approval_id}/approve",
            headers=_headers(approver_csrf),
        )
        assert decided.status_code == 200, decided.text

    db.expire_all()
    row = db.get(Schedule, schedule_id)
    assert row.enabled is True
    assert row.next_run_at is not None
    assert row.next_run_at <= row.end_at


# ─────────────────────────────────────────────────────────────────────────────
# 편집 잠금은 **정의**의 판을 본다 (R3-02)
# ─────────────────────────────────────────────────────────────────────────────


def test_a_scheduler_tick_does_not_invalidate_an_open_edit_form(
    client, admin_csrf, workflow_id, app, fake_clock, db
):
    """스케줄러가 한 번 돌았다는 이유로 "다른 사람이 먼저 저장했습니다" 가 되면 안 된다.

    판을 `updated_at` 에서 뽑으면 그렇게 된다 — tick 이 `last_run_at`·`next_run_at` 을 쓰는
    순간 `TimestampMixin` 의 `onupdate` 가 그 값을 올리기 때문이다. 매분 도는 일정이면 편집
    폼을 연 관리자가 저장할 수 있는 창이 1분이고, 놓치면 그가 고쳐서 통과할 수 있는 것이
    아무것도 없다.
    """
    from app.schedules.models import Schedule

    created = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(workflow_id, name="매분 도는 일정", cron_expression="* * * * *"),
        headers=_headers(admin_csrf),
    ).json()["schedule"]
    client.post(
        f"/api/admin/schedules/{created['id']}/enable", headers=_headers(admin_csrf)
    )

    # 관리자가 편집 폼을 연 시점의 판.
    opened = client.get(f"/api/admin/schedules/{created['id']}").json()["schedule"]
    opened_at = opened["base_version"]
    assert opened_at
    db.expire_all()
    updated_at_before = db.get(Schedule, created["id"]).updated_at

    # 그 사이 스케줄러가 한 번 돈다 — 사람은 아무것도 저장하지 않았다.
    scheduler = SchedulerService(app.state.session_factory, fake_clock)
    fake_clock.advance(61)
    assert scheduler.tick() == 1

    db.expire_all()
    row = db.get(Schedule, created["id"])
    assert row.last_run_at is not None
    assert row.updated_at > updated_at_before, "tick 이 updated_at 을 올리지 않았다면 이 시험은 아무것도 증명하지 않는다"

    saved = client.put(
        f"/api/admin/schedules/{created['id']}",
        json=_schedule_payload(
            workflow_id, name="매분 도는 일정", cron_expression="* * * * *",
            description="설명 한 줄", base_version=opened_at,
        ),
        headers=_headers(admin_csrf),
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["schedule"]["description"] == "설명 한 줄"


def test_saving_the_same_definition_twice_keeps_the_same_version(
    client, admin_csrf, workflow_id
):
    """반례 둘 — 값이 그대로면 판도 그대로이고, 값이 바뀌면 판도 바뀐다."""
    created = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(workflow_id, name="판 비교"),
        headers=_headers(admin_csrf),
    ).json()["schedule"]

    same = client.put(
        f"/api/admin/schedules/{created['id']}",
        json=_schedule_payload(workflow_id, name="판 비교"),
        headers=_headers(admin_csrf),
    )
    assert same.status_code == 200, same.text
    assert same.json()["schedule"]["base_version"] == created["base_version"]

    changed = client.put(
        f"/api/admin/schedules/{created['id']}",
        json=_schedule_payload(workflow_id, name="판 비교", description="바뀐 설명"),
        headers=_headers(admin_csrf),
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["schedule"]["base_version"] != created["base_version"]


# ─────────────────────────────────────────────────────────────────────────────
# 정의는 전역, 실행은 운영 (R3-03)
# ─────────────────────────────────────────────────────────────────────────────


def test_execution_stays_at_ops_scope_while_the_definition_stays_global(
    app, client, db, admin_csrf, workflow_id
):
    """부서 범위 관리자는 전사 일정을 **끄지는 못해도 한 번 돌릴 수는 있다.**

    두 축을 갈라 놓은 결정을 시험으로도 적어 둔다(근거는
    `app/schedules/router.py::_require_global_schedule_write` 의 설명에 있다). 실행 셋에
    같은 문을 걸면 운영자가 전부 걸린다 — 운영자는 조직 관리자가 아니라서 관리 범위가
    전역이 되지 않는데(`app/core/scope.py`), 실행·재시도·취소는 원래 그 사람들 일이다.
    """
    from tests.conftest import DEFAULT_TEST_PASSWORD

    existing = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(workflow_id, name="전사 야간 배치(실행 축)"),
        headers=_headers(admin_csrf),
    ).json()["schedule"]
    assert client.post(
        f"/api/admin/schedules/{existing['id']}/enable", headers=_headers(admin_csrf)
    ).status_code == 200

    email = _dept_scoped_admin(app, db, email="dept-admin-ops@goodmit.co.kr")
    relogin = client.post(
        "/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD}
    )
    assert relogin.status_code == 200, relogin.text
    dept_csrf = relogin.json()["csrf_token"]

    # 정의를 바꾸는 것은 막힌다.
    assert client.post(
        f"/api/admin/schedules/{existing['id']}/disable", headers=_headers(dept_csrf)
    ).status_code == 403

    # 실행은 막지 않는다 — 승인을 지난 정의를 한 번 앞당기는 것이다.
    fired = client.post(
        f"/api/admin/schedules/{existing['id']}/run-now",
        json={},
        headers=_headers(dept_csrf),
    )
    assert fired.status_code == 200, fired.text
    run_id = fired.json()["run"]["id"]

    # 실행 취소도 같은 축이다.
    cancelled = client.post(
        f"/api/admin/schedules/runs/{run_id}/cancel", headers=_headers(dept_csrf)
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["run"]["status"] == "skipped"


def test_an_operator_can_still_run_and_cancel(client, login_as, admin_csrf, workflow_id):
    """반례 — 운영자에게 실행·취소가 그대로 열려 있다.

    `console.ops` 가 화면의 RBAC 매트릭스에 그렇게 적혀 있다(`app/core/authz.py`). 실행 셋에
    전역 관리 범위를 요구하면 이 시험이 빨간불이 되고, 그 빨간불이 곧 매트릭스가 거짓이
    됐다는 신호다.
    """
    created = client.post(
        "/api/admin/schedules",
        json=_schedule_payload(workflow_id, name="운영자가 돌리는 일정"),
        headers=_headers(admin_csrf),
    ).json()["schedule"]
    assert client.post(
        f"/api/admin/schedules/{created['id']}/enable", headers=_headers(admin_csrf)
    ).status_code == 200

    op_csrf = login_as("operator", email="sched-operator@goodmit.co.kr")
    fired = client.post(
        f"/api/admin/schedules/{created['id']}/run-now",
        json={},
        headers=_headers(op_csrf),
    )
    assert fired.status_code == 200, fired.text
    cancelled = client.post(
        f"/api/admin/schedules/runs/{fired.json()['run']['id']}/cancel",
        headers=_headers(op_csrf),
    )
    assert cancelled.status_code == 200, cancelled.text


# ─────────────────────────────────────────────────────────────────────────────
# 이미 저장된 재시도 횟수는 그대로 다시 저장할 수 있다 (R3-04)
# ─────────────────────────────────────────────────────────────────────────────


def test_a_stored_out_of_range_retry_count_does_not_block_an_unrelated_edit(
    client, admin_csrf, db, workflow_id
):
    """`max_attempts` 가 999 로 저장된 행도 설명 한 줄은 고칠 수 있어야 한다.

    실행 경계(`scheduler._max_attempts`)는 그 값을 예전부터 10 으로 잘라 왔다 — 그 일정은
    지금도 멀쩡히 돈다. 저장 경계가 그 값을 거절하면 관리자가 오타 하나를 고치려고 그
    일정의 재시도 정책부터 바꿔야 한다(target_ref·end_at 이 이미 봐주는 그 상황이다).
    """
    from app.schedules.models import Schedule

    row = Schedule(
        name="옛 재시도 정책", schedule_type="cron", cron_expression="0 * * * *",
        timezone="UTC", target_type="system", target_ref="noop",
        payload_template_json="{}", retry_policy_json='{"max_attempts": 999}',
        enabled=False,
    )
    db.add(row)
    db.commit()
    row_id = row.id

    keep = _schedule_payload(
        workflow_id, name="옛 재시도 정책", timezone="UTC",
        description="오타를 고쳤다", retry_policy={"max_attempts": 999},
        payload_template={},
    )
    r = client.put(
        f"/api/admin/schedules/{row_id}", json=keep, headers=_headers(admin_csrf)
    )
    assert r.status_code == 200, r.text
    assert r.json()["schedule"]["description"] == "오타를 고쳤다"
    assert r.json()["schedule"]["retry_policy"] == {"max_attempts": 999}


def test_moving_a_retry_count_to_another_out_of_range_value_is_still_refused(
    client, admin_csrf, db, workflow_id
):
    """반례 — 저장된 값을 봐준다고 해서 **새** 범위 밖 값으로 옮겨 갈 수 있는 것은 아니다."""
    from app.schedules.models import Schedule

    row = Schedule(
        name="옛 재시도 정책 이동", schedule_type="cron", cron_expression="0 * * * *",
        timezone="UTC", target_type="system", target_ref="noop",
        payload_template_json="{}", retry_policy_json='{"max_attempts": 999}',
        enabled=False,
    )
    db.add(row)
    db.commit()

    moved = _schedule_payload(
        workflow_id, name="옛 재시도 정책 이동", timezone="UTC",
        retry_policy={"max_attempts": 50}, payload_template={},
    )
    r = client.put(
        f"/api/admin/schedules/{row.id}", json=moved, headers=_headers(admin_csrf)
    )
    assert r.status_code == 422, r.text
    assert "재시도 횟수" in r.text

    # 형이 틀린 값은 저장된 값이라도 봐주지 않는다 — 그 값으로는 어느 경로로도 못 돈다.
    typed = _schedule_payload(
        workflow_id, name="옛 재시도 정책 이동", timezone="UTC",
        retry_policy={"max_attempts": "999"}, payload_template={},
    )
    assert client.put(
        f"/api/admin/schedules/{row.id}", json=typed, headers=_headers(admin_csrf)
    ).status_code == 422
