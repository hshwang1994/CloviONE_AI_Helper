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


# ── S5: 완료 커밋이 실패해도 핸들러를 두 번 실행하지 않는다 ─────────────────────

def test_a_failed_completion_commit_does_not_re_execute_the_handler(
    worker_env, fake_clock, monkeypatch
):
    """핸들러는 성공했는데 **완료 기록만** 실패한 경우 (S5).

    예전에는 `repository.finish()` + `db.commit()` 이 `try` **밖**에 있었다. 그래서 커밋만
    실패하면(SQLite 잠금) 잡이 `running` 인 채로 남고, `sweep` 이 타임아웃 뒤 재큐잉해
    **핸들러가 다시 실행됐다** — n8n·Notion 쓰기가 최대 3회 나가는 경로가 이것이다.
    되돌릴 수 없는 외부 쓰기를 한 번 더 내는 것보다, 성공을 못 적었다는 사실을 남기는 편이 낫다.

    사용자가 겪는 일: 예약 워크플로가 한 번 눌렸는데 n8n 이 세 번 돌아 결재가 3건 생긴다.
    """
    worker, factory, executed = worker_env
    job_id = _enqueue(factory, fake_clock, "ok", {"n": 1})

    calls = {"n": 0}
    real_finish = repository.finish

    def finish_that_fails_once(db, job, *, now):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("database is locked")
        return real_finish(db, job, now=now)

    monkeypatch.setattr(repository, "finish", finish_that_fails_once)

    assert worker.run_once() is True
    assert len(executed) == 1, "핸들러가 첫 회에 실행되지 않았다 — 전제가 깨졌다"

    # 대역외 복구가 완료를 적었어야 한다. `running` 으로 남으면 스윕이 재큐잉한다.
    assert _job_status(factory, job_id) == "succeeded", (
        f"완료가 기록되지 않았다({_job_status(factory, job_id)}) — 스윕이 재실행한다"
    )

    # 그리고 스윕·다음 폴링이 이 잡을 다시 집지 않아야 한다.
    monkeypatch.undo()
    fake_clock.advance(60 * 90)          # running 타임아웃을 훌쩍 넘겨서
    worker.sweep(fake_clock.now())
    assert worker.run_once(fake_clock.now()) is False
    assert len(executed) == 1, f"핸들러가 {len(executed)}회 실행됐다 — 외부 쓰기가 중복됐다"


def test_a_completion_that_cannot_be_recorded_at_all_is_not_silent(
    worker_env, fake_clock, monkeypatch, caplog
):
    """두 번 다 실패하면 **중복 실행 가능성을 로그로 말한다**.

    DB 를 아예 못 쓰는 상황은 여기서 고칠 수 없다. 고칠 수 없는 것을 조용히 두면 나중에
    중복 실행의 원인을 영원히 못 찾는다 — 그 한 줄이 유일한 단서다.
    """
    import logging

    worker, factory, executed = worker_env
    _enqueue(factory, fake_clock, "ok", {"n": 2})

    def always_fails(db, job, *, now):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(repository, "finish", always_fails)

    with caplog.at_level(logging.WARNING, logger="app.worker"):
        assert worker.run_once() is True

    assert len(executed) == 1
    assert any("중복 실행" in r.getMessage() for r in caplog.records), (
        f"중복 실행 위험이 로그에 없다: {[r.getMessage() for r in caplog.records]}"
    )
