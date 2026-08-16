"""Background worker: claims jobs and dispatches to registered handlers (spec §22).

Deterministic core: ``run_once(now)`` processes at most one job and never
sleeps — tests drive it with a FakeClock. ``run_forever`` adds the polling
loop, periodic stuck-job sweeps, and graceful shutdown.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Protocol

from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import Clock
from app.core.config import Settings
from app.jobs import repository
from app.jobs.exceptions import PermanentJobError
from app.jobs.models import Job

logger = logging.getLogger("app.worker")


class JobHandler(Protocol):
    def __call__(self, db: Session, job: Job, ctx: "WorkerContext") -> None: ...


@dataclass
class WorkerContext:
    settings: Settings
    clock: Clock
    outbound_client: object | None = None
    extras: dict = field(default_factory=dict)


class Worker:
    def __init__(
        self,
        session_factory: sessionmaker,
        clock: Clock,
        handlers: dict[str, JobHandler],
        ctx: WorkerContext,
        *,
        poll_interval: float = 0.5,
        running_timeout_seconds: int = repository.DEFAULT_RUNNING_TIMEOUT_SECONDS,
        sweep_every: int = 60,
        include_types: tuple[str, ...] | None = None,
        exclude_types: tuple[str, ...] = (),
        takeover_after_seconds: float | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._handlers = handlers
        self._ctx = ctx
        self._poll_interval = poll_interval
        self._running_timeout_seconds = running_timeout_seconds
        self._sweep_every = sweep_every
        # 레인 필터(D-118) — 기본값(둘 다 비었음)은 이전과 똑같이 전 job_type을 클레임/sweep한다.
        # 대화형 레인 워커는 include_types=lanes.CONVERSATIONAL_JOB_TYPES를, 배치 레인 워커는
        # exclude_types=lanes.CONVERSATIONAL_JOB_TYPES(+ takeover_after_seconds)를 받는다.
        self._include_types = include_types
        self._exclude_types = exclude_types
        self._takeover_after_seconds = takeover_after_seconds
        # Hooks run every loop iteration (M8 plugs the scheduler tick in here).
        self.tick_callbacks: list[Callable[[datetime], None]] = []

    def run_once(self, now: datetime | None = None) -> bool:
        """Claim and execute at most one job. Returns True if one was processed."""
        now = now or self._clock.now()
        with self._session_factory() as db:
            job = repository.claim_next(
                db, now,
                include_types=self._include_types,
                exclude_types=self._exclude_types,
                takeover_after_seconds=self._takeover_after_seconds,
            )
            if job is None:
                return False
            job_id = job.id
            job_type = job.job_type

        with self._session_factory() as db:
            job = db.get(Job, job_id)
            handler = self._handlers.get(job_type)
            finish_now = self._clock.now()
            if handler is None:
                repository.fail(
                    db, job,
                    error=f"등록되지 않은 job_type: {job_type}",
                    now=finish_now, permanent=True,
                )
                db.commit()
                logger.error("job %s failed: unknown type %s", job_id, job_type)
                return True
            # DBTX: 핸들러를 부르기 직전 커밋한다. 위 db.get(Job, ...) 읽기가 이미 이
            # 세션의 스냅샷을 고정했다 — 어떤 핸들러는(예: llm_connection_test) 그 자체로는
            # 더 안 읽고 곧장 느린 아웃바운드 호출을 걸 수 있는데, 그러면 이 스냅샷이 호출이
            # 도는 내내 낡아 가다가 응답을 받은 뒤의 쓰기가 "database is locked"로 거부될 수
            # 있다(app/core/db.py의 "begin" 이벤트 주석 참고). 각 핸들러도 자신의 마지막
            # 아웃바운드 호출 바로 앞에서 같은 이유로 커밋한다(chat_message.py 등) — 여기는
            # 그 규율이 없는 핸들러를 위한 보험이다. 아직 아무 것도 안 썼으니(위에서 읽기만
            # 했다) 커밋해도 잃을 것이 없다.
            db.commit()
            try:
                handler(db, job, self._ctx)
            except PermanentJobError as exc:
                db.rollback()
                job = db.get(Job, job_id)
                repository.fail(db, job, error=str(exc), now=self._clock.now(), permanent=True)
                db.commit()
                logger.warning("job %s permanently failed: %s", job_id, exc)
                self._notify_failure(handler, job_id, str(exc))
                return True
            except Exception as exc:
                db.rollback()
                job = db.get(Job, job_id)
                repository.fail(db, job, error=f"{type(exc).__name__}: {exc}", now=self._clock.now())
                db.commit()
                logger.warning(
                    "job %s attempt %s failed (%s), status=%s",
                    job_id, job.attempt_count, type(exc).__name__, job.status,
                )
                if job.status == "failed":
                    self._notify_failure(handler, job_id, str(exc))
                return True
            # 커밋을 `try` 안에 둔다 (S5). 예전에는 밖에 있어서, **핸들러는 성공했는데
            # 커밋만 실패하면**(SQLite 잠금 등) 잡이 `running` 인 채로 남았다. 그러면
            # `sweep` 이 타임아웃 뒤 재큐잉하고 핸들러가 **다시 실행된다** — n8n·Notion
            # 쓰기가 최대 3회 나가는 것이 이 경로였다.
            #
            # 어느 쪽으로 옮길지: **1회 실행 + 실패 기록**이다. 이미 벌어진 외부 부작용을
            # 한 번 더 내는 것보다, 성공을 못 적었다는 사실을 남기는 편이 낫다.
            try:
                repository.finish(db, job, now=self._clock.now())
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("job %s: 처리는 끝났는데 완료 기록에 실패했다", job_id)
                self._finish_out_of_band(job_id)
                return True
            logger.info("job %s (%s) succeeded", job_id, job_type)
            return True

    def _finish_out_of_band(self, job_id: str) -> None:
        """완료 기록만 실패한 잡을 **새 세션에서** failed로 확정한다 (S5).

        예전에는 여기서도 `repository.finish()`로 succeeded 확정을 다시 시도했다. 그런데
        그 시도가 쓰는 것은 **새 세션**이다 — 핸들러가 원래 세션에서 `db.flush()`만 하고
        (커밋은 여기 바깥 `run_once`가 한 번에 한다는 전제로) 커밋이 실패해 롤백된
        메시지/문서/실행 결과 쓰기는 이 새 세션에 없다. 그 상태에서 job 행만 succeeded로
        적으면, 핸들러가 실제로 만든 산출물(assistant 메시지, 문서 발행 상태, schedule_run
        결과)은 롤백된 채로 사라졌는데 job은 '성공'이라 아무도 재시도하지 않고 실패 알림도
        가지 않는다 — 사용자 입장에서는 요청이 조용히 증발한 것과 같다.

        그래서 여기서는 **성공을 재시도하지 않고 실패로 확정**한다(재시도는 하지 않는다 —
        핸들러의 외부 쓰기가 이미 나갔을 수 있어 한 번 더 실행하면 중복 부작용이 난다,
        `run_once`의 커밋-내부화 이유와 같다). 핸들러의 `on_failure` 훅을 불러(있으면)
        막혀 있던 도메인 객체(메시지/생성/실행)를 각자의 실패 상태로 옮기고, `run_once`의
        `PermanentJobError` 분기와 같은 모양으로 소유자에게도 알린다 — '조용히 틀린 성공'
        보다 '눈에 보이는, 복구 가능한 실패'가 낫다는 이 저장소의 기존 fail-closed 원칙
        (예: schedule.enable의 staleness 검사, document.publish의 '미리보기 없음 → 실패'
        검사)과 같은 판단이다.
        """
        error = "완료 기록 실패: 처리 결과가 저장되지 않았을 수 있습니다"
        try:
            with self._session_factory() as db:
                job = db.get(Job, job_id)
                if job is None or job.status != "running":
                    return
                repository.fail(db, job, error=error, now=self._clock.now(), permanent=True)
                db.commit()
                job_type = job.job_type
                logger.warning(
                    "job %s: 완료 기록 실패, 성공 재시도 대신 실패로 확정했다", job_id
                )
        except Exception:
            # failed로도 못 적으면 job은 `running`에 그대로 남는다 — 이 실패 경로는 예전과
            # 같다(둘 다 실패하면 sweep의 타임아웃 복구에 맡긴다). "중복 실행" 문구를 그대로
            # 남긴다: 그 경우 sweep이 재큐잉해 핸들러가 다시 실행될 수 있다는 경고다.
            logger.exception(
                "job %s: 완료 기록에 두 번 실패했다. 스윕이 재큐잉하면 중복 실행된다",
                job_id,
            )
            return
        handler = self._handlers.get(job_type)
        if handler is not None:
            self._notify_failure(handler, job_id, error)

    def _notify_failure(self, handler: JobHandler, job_id: str, error: str) -> None:
        """Invoke the handler's on_failure hook (if any) and notify the job
        owner — in a fresh transaction AFTER the final failure is committed."""
        try:
            with self._session_factory() as db:
                job = db.get(Job, job_id)
                on_failure = getattr(handler, "on_failure", None)
                if on_failure is not None:
                    on_failure(db, job, self._ctx, error)
                if job.user_id:
                    from app.notifications.service import notify_user

                    notify_user(
                        db,
                        job.user_id,
                        type_="job_failed",
                        title="요청 처리에 실패했습니다",
                        body="요청을 다시 시도하거나 관리자에게 문의하세요.",
                        related=("job", job.id),
                        now=self._clock.now(),
                    )
                db.commit()
        except Exception:
            logger.exception("on_failure hook for job %s crashed", job_id)

    def sweep(self, now: datetime | None = None) -> int:
        now = now or self._clock.now()
        with self._session_factory() as db:
            recovered = repository.recover_stuck(
                db, now=now, running_timeout_seconds=self._running_timeout_seconds,
                include_types=self._include_types, exclude_types=self._exclude_types,
            )
            db.commit()
            finally_failed = [
                (job.id, job.job_type) for job in recovered if job.status == "failed"
            ]
        if recovered:
            logger.warning("recovered %d stuck job(s)", len(recovered))
        for job_id, job_type in finally_failed:
            handler = self._handlers.get(job_type)
            if handler is not None:
                self._notify_failure(handler, job_id, "worker timeout: stuck job recovered")
        return len(recovered)

    def run_forever(self, stop_event: threading.Event) -> None:
        """Polling loop with graceful shutdown: finishes the in-flight job,
        then exits."""
        self.sweep()  # crash recovery on startup (spec §22 Worker 재시작 복구)
        iterations = 0
        while not stop_event.is_set():
            now = self._clock.now()
            for callback in self.tick_callbacks:
                try:
                    callback(now)
                except Exception:
                    logger.exception("tick callback failed")
            processed = False
            try:
                processed = self.run_once(now)
            except Exception:
                logger.exception("worker iteration failed")
            iterations += 1
            if iterations % self._sweep_every == 0:
                self.sweep()
            if not processed:
                stop_event.wait(self._poll_interval)
        logger.info("worker stopped gracefully")

    def run_forever_pooled(self, stop_event: threading.Event, *, max_concurrency: int) -> None:
        """대화형 레인 전용 폴링 루프(D-118) — `run_once`를 스레드 풀에서 최대
        `max_concurrency`개 동시에 돈다. `run_once` 자신은 한 글자도 안 바뀐다: 각 호출은
        자기 세션(`with self._session_factory() as db`)을 여니 스레드 사이에 공유되는
        상태가 없다.

        `tick_callbacks`는 절대 안 부른다 — 대화형 레인이 스케줄러/보존/백업 같은 배치
        tick을 대신 실행하면 안 된다(그중 상당수가 유니크 제약 없는 outbound 쓰기라 두
        군데서 돌면 실제로 중복 실행된다, D-118 §2). 배선 자체를 안 하는 것이 1차
        방어(`worker_main.py::build_conversational_worker`가 이 메서드를 쓰는 워커에
        `tick_callbacks.append`를 아예 안 부른다)이고, 이 assertion이 2차 방어다 — 나중에
        실수로 하나가 등록되면 "조용히 두 번 실행"이 아니라 "기동 즉시 실패"가 되게 한다.
        """
        if self.tick_callbacks:
            raise RuntimeError(
                "run_forever_pooled은 tick_callbacks가 비어 있어야 한다. 대화형 레인은 "
                f"배치 tick을 실행하면 안 된다(D-118). 등록된 콜백 {len(self.tick_callbacks)}개."
            )
        self.sweep()  # crash recovery on startup — run_forever와 같은 이유
        from concurrent.futures import ThreadPoolExecutor

        def run_once_safely(now: datetime) -> bool:
            try:
                return self.run_once(now)
            except Exception:
                logger.exception("conversational worker iteration failed")
                return False

        in_flight: set = set()
        iterations = 0
        with ThreadPoolExecutor(max_workers=max_concurrency, thread_name_prefix="conv-worker") as pool:
            while not stop_event.is_set():
                in_flight = {f for f in in_flight if not f.done()}
                while len(in_flight) < max_concurrency and not stop_event.is_set():
                    in_flight.add(pool.submit(run_once_safely, self._clock.now()))
                iterations += 1
                if iterations % self._sweep_every == 0:
                    self.sweep()
                stop_event.wait(self._poll_interval)
            if in_flight:
                logger.info("conversational worker draining %d in-flight job(s)", len(in_flight))
            # `with` 블록을 벗어나면 ThreadPoolExecutor.__exit__가 shutdown(wait=True)를
            # 불러 in_flight의 모든 future가 끝난 뒤에야 아래 줄로 진행한다 — run_forever의
            # "진행 중인 잡은 끝내고 종료" 규약과 같다.
        logger.info("conversational worker stopped gracefully")


def parse_payload(job: Job) -> dict:
    try:
        return json.loads(job.payload_json)
    except json.JSONDecodeError as exc:
        raise PermanentJobError(f"payload JSON이 손상되었습니다: {exc}") from exc
