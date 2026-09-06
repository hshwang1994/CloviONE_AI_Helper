"""실행(run) 경로가 **정의된 방식으로** 실패한다 — 500 도, 침묵도 아니다.

이미 저장된 잘못된 재시도 정책(스키마가 막기 전에 들어온 행)을 화면에서 실행하면 어떤
답을 주는가에 대한 계약이다. 채널마다 답이 다른 것이 의도다:

  * **자동 실행**(스케줄러 tick)은 보는 사람이 없다 → 실행 이력에 **실패 행**을 남긴다.
  * **사람이 누른 실행**(지금 실행 / 재시도)은 지금 읽을 수 있는 답을 준다 →
    '지금 실행'은 그 실패 행을 그대로 돌려주고, '재시도'는 무엇을 고치라고 422 로 답한다.

예전에는 셋 다 `int("abc")` 하나로 끝났다 — 수동은 500, 자동은 로그 한 줄, 이력은 빈 채.
"""

import pytest

from app.schedules.models import RUN_FAILED, Schedule, ScheduleRun
from app.schedules.scheduler import UNREADABLE_RETRY_POLICY_MESSAGE

pytestmark = pytest.mark.integration


@pytest.fixture()
def admin_csrf(login_as):
    # system_admin: 활성화가 승인 게이트를 우회해 즉시 적용된다.
    return login_as("system_admin")


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


def _schedule(db, *, name, retry_policy_json):
    """스키마를 지나지 않고 행을 만든다 — 지금은 이 값을 API 로 저장할 수 없기 때문이다
    (그것이 이 결함의 절반이고, 나머지 절반이 이미 저장된 행의 실행이다)."""
    row = Schedule(
        name=name,
        schedule_type="cron",
        cron_expression="0 * * * *",
        timezone="UTC",
        target_type="system",
        target_ref="noop",
        payload_template_json="{}",
        retry_policy_json=retry_policy_json,
        enabled=True,
    )
    db.add(row)
    db.commit()
    return row


def test_run_now_on_an_unreadable_policy_answers_with_a_failed_run(
    client, admin_csrf, db
):
    row = _schedule(db, name="못 읽는 정책 수동", retry_policy_json='{"max_attempts": "abc"}')

    r = client.post(
        f"/api/admin/schedules/{row.id}/run-now", json={}, headers=_headers(admin_csrf)
    )
    assert r.status_code == 200, r.text
    assert r.json()["run"]["status"] == RUN_FAILED
    assert r.json()["run"]["error_message"] == UNREADABLE_RETRY_POLICY_MESSAGE

    # 실행 이력에 그 실패가 남는다 — '아직 시간이 안 됐다' 와 구별된다.
    runs = client.get(
        f"/api/admin/schedules/{row.id}/runs", headers=_headers(admin_csrf)
    ).json()
    assert runs["total"] == 1
    assert runs["items"][0]["status"] == RUN_FAILED


def test_run_now_on_a_readable_policy_still_queues(client, admin_csrf, db):
    """반례 — 읽을 수 있는 정책은 예전 그대로 대기(queued) 실행을 만든다."""
    row = _schedule(db, name="읽히는 정책 수동", retry_policy_json='{"max_attempts": 2}')

    r = client.post(
        f"/api/admin/schedules/{row.id}/run-now", json={}, headers=_headers(admin_csrf)
    )
    assert r.status_code == 200, r.text
    assert r.json()["run"]["status"] == "queued"
    assert r.json()["run"]["error_message"] is None


def test_retry_run_on_an_unreadable_policy_says_what_to_fix(client, admin_csrf, db):
    row = _schedule(db, name="못 읽는 정책 재시도", retry_policy_json='{"max_attempts": [1]}')
    run = ScheduleRun(
        schedule_id=row.id,
        scheduled_at=row.created_at,
        idempotency_key=f"manual:{row.id}:20260714000000",
        status=RUN_FAILED,
        request_payload_json="{}",
        created_at=row.created_at,
        finished_at=row.created_at,
        error_message="앞선 실패",
    )
    db.add(run)
    db.commit()

    r = client.post(
        f"/api/admin/schedules/runs/{run.id}/retry", headers=_headers(admin_csrf)
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["message"] == UNREADABLE_RETRY_POLICY_MESSAGE

    # 거절했으면 상태도 그대로다 — 반쯤 큐에 들어간 실행을 남기지 않는다.
    db.expire_all()
    assert db.get(ScheduleRun, run.id).status == RUN_FAILED
    assert db.get(ScheduleRun, run.id).error_message == "앞선 실패"


def test_retry_run_on_a_readable_policy_requeues(client, admin_csrf, db):
    """반례 — 읽을 수 있는 정책의 실패한 실행은 그대로 다시 큐에 들어간다."""
    row = _schedule(db, name="읽히는 정책 재시도", retry_policy_json='{"max_attempts": 1}')
    run = ScheduleRun(
        schedule_id=row.id,
        scheduled_at=row.created_at,
        idempotency_key=f"manual:{row.id}:20260714000001",
        status=RUN_FAILED,
        request_payload_json="{}",
        created_at=row.created_at,
        finished_at=row.created_at,
        error_message="앞선 실패",
    )
    db.add(run)
    db.commit()

    r = client.post(
        f"/api/admin/schedules/runs/{run.id}/retry", headers=_headers(admin_csrf)
    )
    assert r.status_code == 200, r.text
    assert r.json()["run"]["status"] == "queued"
    assert r.json()["run"]["error_message"] is None


def test_run_now_does_not_call_a_run_that_never_started_the_last_run(
    client, admin_csrf, db
):
    """시작도 못 한 실행은 '마지막 실행'이 아니고, 응답도 시작했다고 말하지 않는다.

    `create_run_and_enqueue` 는 재시도 정책을 읽을 수 없으면 예외 대신 실패 행을 남긴다 —
    그래야 실행 이력이 침묵하지 않는다. 그 행까지 `last_run_at` 으로 찍으면 목록의 '마지막
    실행' 칸이 "이 시각에 돌았다"고 거짓말을 한다. 스케줄러 tick 이 세는 기준과 같은
    기준으로 본다(scheduler.py 의 "시작도 못 한 실행을 세지 않는다").
    """
    from app.schedules.models import Schedule

    row = _schedule(db, name="시작 못 한 실행", retry_policy_json='{"max_attempts": "abc"}')

    r = client.post(
        f"/api/admin/schedules/{row.id}/run-now", json={}, headers=_headers(admin_csrf)
    )
    assert r.status_code == 200, r.text
    assert r.json()["run"]["status"] == RUN_FAILED
    assert r.json()["ok"] is False, "시작하지 못한 실행을 ok 로 답하면 부르는 쪽이 알 방법이 없다"

    db.expire_all()
    assert db.get(Schedule, row.id).last_run_at is None


def test_run_now_that_actually_queues_still_stamps_the_last_run(client, admin_csrf, db):
    """반례 — 실제로 큐에 들어간 실행은 예전 그대로 '마지막 실행'을 찍고 ok 로 답한다."""
    from app.schedules.models import Schedule

    row = _schedule(db, name="시작한 실행", retry_policy_json='{"max_attempts": 2}')

    r = client.post(
        f"/api/admin/schedules/{row.id}/run-now", json={}, headers=_headers(admin_csrf)
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert r.json()["run"]["status"] == "queued"

    db.expire_all()
    assert db.get(Schedule, row.id).last_run_at is not None
