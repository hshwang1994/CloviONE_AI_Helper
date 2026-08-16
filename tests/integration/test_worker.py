import threading

import pytest

from app.jobs import repository
from app.jobs.exceptions import PermanentJobError
from app.jobs.models import Job
from app.jobs.worker import Worker, WorkerContext, parse_payload

pytestmark = pytest.mark.integration


@pytest.fixture()
def worker_env(app, settings, fake_clock):
    factory = app.state.session_factory
    executed = []

    def ok_handler(db, job, ctx):
        executed.append(("ok", parse_payload(job)))

    def flaky_handler(db, job, ctx):
        raise RuntimeError("transient failure")

    def fatal_handler(db, job, ctx):
        raise PermanentJobError("입력이 유효하지 않습니다")

    ctx = WorkerContext(settings=settings, clock=fake_clock)
    worker = Worker(
        factory,
        fake_clock,
        {"ok": ok_handler, "flaky": flaky_handler, "fatal": fatal_handler},
        ctx,
        poll_interval=0.01,
    )
    return worker, factory, executed


def _enqueue(factory, clock, job_type, payload=None, **kwargs):
    with factory() as db:
        job = repository.enqueue(
            db, job_type=job_type, payload=payload or {}, now=clock.now(), **kwargs
        )
        db.commit()
        return job.id


def _job_status(factory, job_id):
    with factory() as db:
        return db.get(Job, job_id).status


def test_worker_processes_success(worker_env, fake_clock):
    worker, factory, executed = worker_env
    job_id = _enqueue(factory, fake_clock, "ok", {"hello": "world"})
    assert worker.run_once() is True
    assert executed == [("ok", {"hello": "world"})]
    assert _job_status(factory, job_id) == "succeeded"
    assert worker.run_once() is False  # queue empty


def test_worker_transient_failure_requeues_with_backoff(worker_env, fake_clock):
    worker, factory, _ = worker_env
    job_id = _enqueue(factory, fake_clock, "flaky")
    assert worker.run_once() is True
    assert _job_status(factory, job_id) == "queued"

    # Before backoff elapses nothing to do; after, it retries again.
    assert worker.run_once() is False
    fake_clock.advance(6)
    assert worker.run_once() is True
    assert _job_status(factory, job_id) == "queued"  # attempt 2 also failed

    with factory() as db:
        job = db.get(Job, job_id)
        assert job.attempt_count == 2
        assert "transient failure" in job.last_error

    # Third (final) attempt exhausts max_attempts=3 → failed.
    fake_clock.advance(11)
    assert worker.run_once() is True
    assert _job_status(factory, job_id) == "failed"


def test_worker_permanent_error_fails_immediately(worker_env, fake_clock):
    worker, factory, _ = worker_env
    job_id = _enqueue(factory, fake_clock, "fatal")
    worker.run_once()
    assert _job_status(factory, job_id) == "failed"
    with factory() as db:
        assert "유효하지 않습니다" in db.get(Job, job_id).last_error


def test_worker_unknown_job_type_fails_permanently(worker_env, fake_clock):
    worker, factory, _ = worker_env
    job_id = _enqueue(factory, fake_clock, "no_such_handler")
    worker.run_once()
    assert _job_status(factory, job_id) == "failed"


def test_worker_corrupt_payload_is_permanent(worker_env, fake_clock):
    worker, factory, executed = worker_env
    job_id = _enqueue(factory, fake_clock, "ok")
    with factory() as db:
        db.get(Job, job_id).payload_json = "{corrupt"
        db.commit()
    worker.run_once()
    assert _job_status(factory, job_id) == "failed"
    assert executed == []


def test_worker_startup_sweep_recovers_stuck_jobs(worker_env, fake_clock):
    worker, factory, executed = worker_env
    job_id = _enqueue(factory, fake_clock, "ok")
    # Simulate a crash: job claimed but never finished.
    with factory() as db:
        repository.claim_next(db, fake_clock.now())
    assert _job_status(factory, job_id) == "running"

    fake_clock.advance(4000)  # past DEFAULT_RUNNING_TIMEOUT_SECONDS (3900)
    worker.sweep()
    assert _job_status(factory, job_id) == "queued"
    # Recovery reuses the retry path, so the requeued job carries a backoff.
    fake_clock.advance(10)
    worker.run_once()
    assert _job_status(factory, job_id) == "succeeded"


def test_run_forever_graceful_shutdown(worker_env, fake_clock):
    worker, factory, executed = worker_env
    _enqueue(factory, fake_clock, "ok")
    stop = threading.Event()
    thread = threading.Thread(target=worker.run_forever, args=(stop,), daemon=True)
    thread.start()
    # Give the loop a moment to process, then stop.
    for _ in range(200):
        if executed:
            break
        threading.Event().wait(0.01)
    stop.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert executed


# ── D-118 Phase 1: run_forever_pooled (대화형 레인) ───────────────────────────


def test_run_forever_pooled_rejects_a_worker_with_tick_callbacks(worker_env):
    """2차 방어(D-118 §2) — 대화형 레인에 실수로 tick이 하나라도 등록돼 있으면 조용히
    두 번 실행되는 대신 기동 자체를 거부한다."""
    worker, factory, executed = worker_env
    worker.tick_callbacks.append(lambda now: None)
    with pytest.raises(RuntimeError, match="tick_callbacks"):
        worker.run_forever_pooled(threading.Event(), max_concurrency=2)


def test_run_forever_pooled_runs_jobs_concurrently_up_to_max_concurrency(app, settings, fake_clock):
    """순차 실행이면 이 시험은 배리어 타임아웃으로 실패한다 — 통과 자체가 동시성의 증거다."""
    factory = app.state.session_factory
    barrier = threading.Barrier(3, timeout=5)
    executed = []

    def slow_handler(db, job, ctx):
        barrier.wait()  # 셋이 동시에 여기 도달해야 통과한다
        executed.append(parse_payload(job))

    ctx = WorkerContext(settings=settings, clock=fake_clock)
    worker = Worker(factory, fake_clock, {"slow": slow_handler}, ctx, poll_interval=0.01)
    for i in range(3):
        _enqueue(factory, fake_clock, "slow", payload={"i": i})

    stop = threading.Event()
    thread = threading.Thread(
        target=worker.run_forever_pooled, kwargs={"stop_event": stop, "max_concurrency": 3}, daemon=True,
    )
    thread.start()
    for _ in range(500):
        if len(executed) >= 3:
            break
        threading.Event().wait(0.02)
    stop.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert len(executed) == 3


def test_run_forever_pooled_graceful_shutdown_drains_in_flight_job(app, settings, fake_clock):
    """정지 신호가 와도 이미 시작한 잡은 끝까지 기다린 뒤 스레드가 종료돼야 한다
    (run_forever의 '진행 중인 잡은 끝내고 종료' 규약과 같다)."""
    factory = app.state.session_factory
    started = threading.Event()
    release = threading.Event()
    executed = []

    def blocking_handler(db, job, ctx):
        started.set()
        release.wait(timeout=5)
        executed.append(parse_payload(job))

    ctx = WorkerContext(settings=settings, clock=fake_clock)
    worker = Worker(factory, fake_clock, {"blocking": blocking_handler}, ctx, poll_interval=0.01)
    _enqueue(factory, fake_clock, "blocking")

    stop = threading.Event()
    thread = threading.Thread(
        target=worker.run_forever_pooled, kwargs={"stop_event": stop, "max_concurrency": 1}, daemon=True,
    )
    thread.start()
    assert started.wait(timeout=5), "핸들러가 시작하지 않았다"
    stop.set()  # 잡이 아직 실행 중인 채로 정지 신호를 보낸다
    release.set()  # 이제 핸들러가 끝나게 둔다
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert executed, "정지 신호가 in-flight 잡을 중간에 끊었다 — drain이 안 된다"


# ── S5: 완료 커밋이 실패해도 핸들러를 두 번 실행하지 않는다 ─────────────────────

def test_a_failed_completion_commit_marks_the_job_failed_not_silently_succeeded(
    worker_env, fake_clock, monkeypatch
):
    """핸들러는 성공했는데 **완료 기록만** 실패한 경우 (S5 + backend-approvals-jobs 감사 #3).

    예전에는 `repository.finish()` + `db.commit()` 이 `try` **밖**에 있었다. 그래서 커밋만
    실패하면(SQLite 잠금) 잡이 `running` 인 채로 남고, `sweep` 이 타임아웃 뒤 재큐잉해
    **핸들러가 다시 실행됐다** — n8n·Notion 쓰기가 최대 3회 나가는 경로가 이것이다.

    그 다음 결함(감사 #3): 커밋을 `try` 안으로 옮긴 뒤에도 `_finish_out_of_band`(대역외
    복구)가 **새 세션에서 succeeded 재확정을 재시도**했다. 그런데 그 새 세션에는 원래
    세션에서 롤백된 핸들러의 산출물 쓰기(예: assistant 메시지, 문서 발행 상태)가 없다 —
    job 행만 성공으로 적히고 실제로 만들어졌어야 할 결과는 사라진 채로 남는다. 이제는
    성공을 재시도하는 대신 **실패로 확정**해 `on_failure` 훅이 돌게 한다 — 도메인 객체가
    실패 상태로 남아 사용자가 재시도할 수 있고, 아무도 재큐잉해서 핸들러를 또 실행하지도
    않는다.
    """
    worker, factory, executed = worker_env
    job_id = _enqueue(factory, fake_clock, "ok", {"n": 1})

    calls = {"n": 0}

    def finish_always_fails(db, job, *, now):
        calls["n"] += 1
        raise RuntimeError("database is locked")

    monkeypatch.setattr(repository, "finish", finish_always_fails)

    assert worker.run_once() is True
    assert len(executed) == 1, "핸들러가 첫 회에 실행되지 않았다 — 전제가 깨졌다"
    assert calls["n"] == 1, "완료 기록 시도(repository.finish)는 주 경로에서 한 번만 나야 한다"

    # 대역외 복구는 이제 succeeded 재시도가 아니라 failed 확정이다 — 핸들러의 실제
    # 산출물 쓰기는 롤백된 채로 job만 succeeded가 되는 '조용히 틀린 성공'을 막는다.
    assert _job_status(factory, job_id) == "failed", (
        f"완료 기록 실패가 succeeded로 둔갑했다({_job_status(factory, job_id)}) — "
        "핸들러의 산출물 쓰기는 사라졌는데 아무도 재시도하지 않는다"
    )
    with factory() as db:
        job = db.get(Job, job_id)
        assert "저장되지 않았을 수 있습니다" in (job.last_error or "")
        assert job.attempt_count == 1  # permanent=True — 백오프 재큐잉하지 않는다

    # failed로 이미 확정됐으니, sweep도 다음 폴링도 이 잡을 다시 실행하지 않는다.
    monkeypatch.undo()
    fake_clock.advance(60 * 90)          # running 타임아웃을 훌쩍 넘겨서
    worker.sweep(fake_clock.now())
    assert worker.run_once(fake_clock.now()) is False
    assert len(executed) == 1, f"핸들러가 {len(executed)}회 실행됐다 — 외부 쓰기가 중복됐다"


def test_a_completion_that_cannot_be_recorded_at_all_is_not_silent(
    worker_env, fake_clock, monkeypatch, caplog
):
    """두 번 다(주 경로 + 대역외 복구) 실패하면 **중복 실행 가능성을 로그로 말한다**.

    DB 를 아예 못 쓰는 상황은 여기서 고칠 수 없다. 고칠 수 없는 것을 조용히 두면 나중에
    중복 실행의 원인을 영원히 못 찾는다 — 그 한 줄이 유일한 단서다.

    대역외 복구는 이제 `repository.finish`가 아니라 `repository.fail`을 쓰므로
    (backend-approvals-jobs 감사 #3), "완전히 못 쓰는 상황"을 재현하려면 둘 다 막아야 한다.
    """
    import logging

    worker, factory, executed = worker_env
    _enqueue(factory, fake_clock, "ok", {"n": 2})

    def always_fails(*args, **kwargs):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(repository, "finish", always_fails)
    monkeypatch.setattr(repository, "fail", always_fails)

    with caplog.at_level(logging.WARNING, logger="app.worker"):
        assert worker.run_once() is True

    assert len(executed) == 1
    assert any("중복 실행" in r.getMessage() for r in caplog.records), (
        f"중복 실행 위험이 로그에 없다: {[r.getMessage() for r in caplog.records]}"
    )
