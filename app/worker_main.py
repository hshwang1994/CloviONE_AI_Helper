"""Worker entry point — systemd clovirone-web-worker.service (spec §26.2).

Run: python -m app.worker_main
Handles SIGTERM/SIGINT for graceful shutdown. The scheduler tick (M8) is
registered as a tick callback so a separate scheduler service remains possible
without code changes (spec §2.3).
"""

from __future__ import annotations

import logging
import signal
import threading

from app.core.allowlist import AllowlistRegistry
from app.core.clock import Clock, SystemClock
from app.core.config import Settings
from app.core.db import make_engine, make_session_factory
from app.core.http_client import OutboundClient
from app.core.secret_refs import FileSecretReferenceProvider
from app.jobs.worker import Worker, WorkerContext

logger = logging.getLogger("app.worker")

# Liveness heartbeat: written from a dedicated thread so it keeps beating even
# while the worker loop is blocked inside a long run_once (schedule workflows up
# to 3600s, notion sync up to 90s). HEARTBEAT_STALE_SECONDS is 90 on the health
# side, so ~30s cadence leaves comfortable margin (spec §14.1).
HEARTBEAT_INTERVAL_SECONDS = 30.0
# Both liveness components are beaten by the thread. The scheduler still *ticks*
# in the worker loop; only its liveness signal moves here so a long-running job
# can't make the dashboard read the scheduler as 'down'.
LIVENESS_COMPONENTS = ("worker", "scheduler")


def beat_liveness(
    session_factory,
    clock: Clock,
    components: tuple[str, ...] = LIVENESS_COMPONENTS,
) -> bool:
    """Write one round of liveness heartbeats using a short-lived session.

    Returns True on success, False on any failure. Never raises — a heartbeat
    hiccup (e.g. a transient DB lock) must not crash the worker process.
    """
    from app.health.service import write_heartbeat

    try:
        now = clock.now()
        with session_factory() as db:
            for component in components:
                write_heartbeat(db, component, now)
            db.commit()
        return True
    except Exception:
        logger.exception("liveness heartbeat write failed")
        return False


def run_heartbeat_loop(
    session_factory,
    clock: Clock,
    stop_event: threading.Event,
    *,
    interval: float = HEARTBEAT_INTERVAL_SECONDS,
    components: tuple[str, ...] = LIVENESS_COMPONENTS,
) -> None:
    """Beat immediately, then every ``interval`` seconds until ``stop_event``.

    Runs on a daemon thread (see main). Beating first means the dashboard shows
    'up' as soon as the worker starts rather than after the first interval.
    """
    while not stop_event.is_set():
        beat_liveness(session_factory, clock, components)
        stop_event.wait(interval)


def build_handlers() -> dict:
    """Job handler registry."""
    from app.jobs.handlers.chat_message import handle_chat_message
    from app.jobs.handlers.document_generate import handle_document_generate
    from app.jobs.handlers.notion_mapping_sync import handle_notion_mapping_sync
    from app.jobs.handlers.schedule_run import handle_schedule_run

    return {
        "chat_message": handle_chat_message,
        "schedule_run": handle_schedule_run,
        "document_generate": handle_document_generate,
        "notion_mapping_sync": handle_notion_mapping_sync,
    }


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = Settings()
    clock = SystemClock()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    allowlists = AllowlistRegistry(settings.config_dir)
    secrets = FileSecretReferenceProvider(settings.secrets_dir)
    outbound = OutboundClient(allowlists, secrets)

    from app.settings.service import SettingsCache

    settings_cache = SettingsCache()
    with session_factory() as db:
        settings_cache.load(db)

    ctx = WorkerContext(
        settings=settings, clock=clock, outbound_client=outbound,
        extras={"settings_cache": settings_cache},
    )
    worker = Worker(session_factory, clock, build_handlers(), ctx)

    # Scheduler runs inside the worker loop (spec §2.3 — Worker 내부 Scheduler).
    # A dedicated clovirone-web-scheduler.service can host this instead later.
    from app.schedules.scheduler import SchedulerService

    scheduler = SchedulerService(session_factory, clock)
    _last_tick: list = [None]

    def scheduler_tick(now):
        # Tick at most once per second — the worker loop can spin faster.
        # NOTE: the scheduler LIVENESS heartbeat is no longer written here — it
        # moved to the dedicated heartbeat thread (run_heartbeat_loop) so it
        # keeps beating while a long job blocks this loop. This callback only
        # performs the actual scheduling work now.
        if _last_tick[0] is None or (now - _last_tick[0]).total_seconds() >= 1.0:
            _last_tick[0] = now
            scheduler.tick(now)

    worker.tick_callbacks.append(scheduler_tick)

    # 승인 만료 스윕 (spec §20) — 1분 간격.
    from app.approvals.service import expire_pending

    _last_expiry: list = [None]

    def approval_expiry_tick(now):
        if _last_expiry[0] is None or (now - _last_expiry[0]).total_seconds() >= 60.0:
            _last_expiry[0] = now
            with session_factory() as db:
                expire_pending(db, now=now)
                db.commit()

    worker.tick_callbacks.append(approval_expiry_tick)

    # Retention purge (spec §14.4) — hourly.
    from app.core.retention import run_retention

    _last_retention: list = [None]

    def retention_tick(now):
        if _last_retention[0] is None or (now - _last_retention[0]).total_seconds() >= 3600.0:
            _last_retention[0] = now
            # Refresh the cache so admin edits to retention take effect.
            with session_factory() as db:
                settings_cache.load(db)
                # outbound/settings 전달 → 휴지통 만료분을 노션에서 보관처리하고 정리한다.
                run_retention(db, now=now, settings_cache=settings_cache, outbound=outbound, settings=settings)
                db.commit()

    worker.tick_callbacks.append(retention_tick)

    # Runner 헬스 자동 점검 (spec §15) — 90초 간격. 수동 점검이 없으면 last_health_status 가
    # 영원히 'unknown'이라 대시보드/러너 목록이 실제 상태를 못 보였다. 워커가 주기적으로 전 러너를
    # 점검해 채운다(첫 tick은 즉시 실행 → 워커 기동 직후 상태가 뜬다). 스윕이 아웃바운드 호출로
    # 잠깐 루프를 잡을 수 있으나 liveness는 별도 스레드라 영향 없다.
    from app.runners.service import run_all_runner_health_checks

    _last_runner_health: list = [None]
    RUNNER_HEALTH_INTERVAL_SECONDS = 90.0

    def runner_health_tick(now):
        if _last_runner_health[0] is None or (now - _last_runner_health[0]).total_seconds() >= RUNNER_HEALTH_INTERVAL_SECONDS:
            _last_runner_health[0] = now
            try:
                with session_factory() as db:
                    run_all_runner_health_checks(db, outbound=outbound, now=now)
                    db.commit()
            except Exception:
                logger.exception("runner health sweep failed")

    worker.tick_callbacks.append(runner_health_tick)

    # 문서 캐시 주기 동기화 (spec §17.2/§17.4) — notion_docs_sync_interval_seconds 간격.
    # 첫 tick 즉시 실행 → 워커 기동 직후 문서 목록이 채워진다. Notion 장애/미설정이면 sync
    # 상태에만 기록되고 캐시(마지막 정상 동기화)는 유지된다 — sync_documents 내부에서 예외를
    # 가두므로 티켓 등 다른 기능엔 무영향.
    from app.team_docs.sync import sync_documents

    _last_docs_sync: list = [None]
    DOCS_SYNC_INTERVAL_SECONDS = float(settings.notion_docs_sync_interval_seconds)

    def docs_sync_tick(now):
        if _last_docs_sync[0] is None or (now - _last_docs_sync[0]).total_seconds() >= DOCS_SYNC_INTERVAL_SECONDS:
            _last_docs_sync[0] = now
            try:
                with session_factory() as db:
                    sync_documents(db, outbound=outbound, settings=settings, now=now)
                    db.commit()
            except Exception:
                logger.exception("docs sync tick failed")

    worker.tick_callbacks.append(docs_sync_tick)

    # 티켓 캐시 주기 동기화 (PLAN §A) — notion_tickets_sync_interval_seconds 간격.
    # 문서 동기화와 완전히 같은 모양이다: 첫 tick 즉시 실행 → 워커 기동 직후 티켓 목록이 채워지고,
    # Notion 장애/미설정이면 sync 상태에만 기록되고 캐시(마지막 정상 동기화)는 유지된다.
    # sync_tickets 가 내부에서 예외를 가두므로 이 tick 은 워커 루프 밖으로 아무것도 던지지 않는다.
    from app.tickets.sync import sync_tickets

    _last_tickets_sync: list = [None]
    TICKETS_SYNC_INTERVAL_SECONDS = float(settings.notion_tickets_sync_interval_seconds)

    def tickets_sync_tick(now):
        if _last_tickets_sync[0] is None or (now - _last_tickets_sync[0]).total_seconds() >= TICKETS_SYNC_INTERVAL_SECONDS:
            _last_tickets_sync[0] = now
            try:
                with session_factory() as db:
                    sync_tickets(db, outbound=outbound, settings=settings, now=now)
                    db.commit()
            except Exception:
                logger.exception("tickets sync tick failed")

    worker.tick_callbacks.append(tickets_sync_tick)

    stop_event = threading.Event()

    def _shutdown(signum, _frame):
        logger.info("signal %s — graceful shutdown", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # Dedicated liveness heartbeat thread (spec §14.1). Daemon so it can never
    # block process exit; it also watches stop_event for prompt shutdown. Its
    # own short-lived sessions keep it independent of the worker loop, so it
    # keeps beating 'worker'/'scheduler' during long-running jobs.
    heartbeat_thread = threading.Thread(
        target=run_heartbeat_loop,
        args=(session_factory, clock, stop_event),
        name="liveness-heartbeat",
        daemon=True,
    )
    heartbeat_thread.start()

    worker.run_forever(stop_event)
    heartbeat_thread.join(timeout=5.0)
    outbound.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
