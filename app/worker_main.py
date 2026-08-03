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
from app.core.worker_lock import WorkerLock, default_lock_path
from app.jobs.worker import Worker, WorkerContext
from app.observability.models import COMPONENT_DOCUMENTS, COMPONENT_TICKETS

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
    lock=None,
) -> None:
    """Beat immediately, then every ``interval`` seconds until ``stop_event``.

    Runs on a daemon thread (see main). Beating first means the dashboard shows
    'up' as soon as the worker starts rather than after the first interval.

    워커 싱글턴 리스(``lock``)도 여기서 갱신한다 — 이미 30초마다 도는 스레드가 있는데
    두 번째 타이머 스레드를 만들 이유가 없다. 갱신에 실패하면(= 리스를 남이 가져갔다)
    **즉시 멈춘다**: 워커가 둘 도는 것보다 하나도 안 도는 편이 안전하다(잡이 두 번
    실행되면 워크플로가 두 번 호출되고 스케줄이 두 번 발화한다).
    """
    while not stop_event.is_set():
        beat_liveness(session_factory, clock, components)
        if lock is not None and not lock.renew():
            logger.error("워커 리스를 잃었다 — 다른 워커가 인수했다. 중단한다.")
            stop_event.set()
            break
        stop_event.wait(interval)


def mirror_sync_status(db, component: str, state, now) -> None:
    """미러 동기화 상태를 `sync_status` 공통 표에도 남긴다(0026).

    왜 표를 하나 더 두는가: `document_sync_state` / `ticket_sync_state` 는 각자 다른 컬럼을
    가진 **구현 상태**다. 화면이 "동기화 컴포넌트 목록"을 그리려면 컴포넌트마다 다른 표와
    다른 컬럼 이름을 알아야 하고, 그러면 컴포넌트가 늘 때마다 화면을 고쳐야 한다.
    워커가 여기서 공통 모양으로 옮겨 적고, 화면은 이 표만 읽는다.

    실패해도 동기화 tick 을 죽이지 않는다 — 상태 표시가 본 작업보다 강하면 안 된다.
    """
    from app.observability.service import upsert_sync_status

    try:
        upsert_sync_status(
            db, component,
            status=state.status,
            now=now,
            item_count=(
                getattr(state, "ticket_count", None)
                or getattr(state, "doc_count", None)
                or getattr(state, "item_count", 0)
            ),
            truncated=bool(getattr(state, "truncated", False)),
            error=state.error,
        )
    except Exception:
        logger.exception("sync_status 미러링 실패 (무시하고 계속한다): %s", component)


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

    # 싱글턴 리스(§ 스케일 심). 워커가 둘 돌면 잡이 두 번 실행되고 스케줄이 두 번 발화한다.
    # systemd 재시작 중첩, 운영자가 진단하려고 손으로 띄운 워커, 배포 스크립트의 중복
    # start — 셋 다 실제로 있는 경로다. 잡지 못하면 **뜨지 않는다**(조용히 둘째로 돌지 않는다).
    lock = WorkerLock(default_lock_path(settings.data_dir))
    if not lock.acquire():
        holder = (lock.read() or {}).get("owner", "?")
        logger.error(
            "다른 워커가 이미 돌고 있다(owner=%s, lock=%s) — 중복 실행을 막기 위해 종료한다. "
            "정말 이전 워커가 죽었다면 리스가 만료된 뒤(기본 120초) 다시 시도하면 인수한다.",
            holder, lock.path,
        )
        return 1
    logger.info("워커 리스 획득: %s", lock.owner)

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
                    state = sync_documents(db, outbound=outbound, settings=settings, now=now)
                    mirror_sync_status(db, COMPONENT_DOCUMENTS, state, now)
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
                    state = sync_tickets(db, outbound=outbound, settings=settings, now=now)
                    mirror_sync_status(db, COMPONENT_TICKETS, state, now)
                    db.commit()
            except Exception:
                logger.exception("tickets sync tick failed")

    worker.tick_callbacks.append(tickets_sync_tick)

    # 통합 검색 인덱스 재구축 (PLAN Phase 5) — search_index_interval_seconds 간격.
    #
    # **인덱싱 훅은 여기 한 곳뿐이다.** 티켓/문서/게시판/사용자를 저장하는 경로마다 인덱스를
    # 같이 쓰게 하면, 이 앱에서 가장 뜨거운 쓰기(채팅 전송)와 폴링 읽기에 INSERT 가 얹힌다
    # (PLAN C9: 진짜 병목은 _append_message 다). 검색 결과가 최대 한 틱 늦는 대신 뜨거운
    # 경로는 한 글자도 안 바뀐다.
    #
    # 티켓 미러 뒤에 등록하는 이유: 첫 틱에서 tickets_sync 가 먼저 돌아 미러를 채우므로,
    # 워커 기동 직후 첫 인덱싱이 빈 티켓 목록을 보지 않는다.
    from app.core.source_registry import build_repositories
    from app.observability.models import COMPONENT_SEARCH
    from app.search.indexer import reindex_all

    _last_search_index: list = [None]
    SEARCH_INDEX_INTERVAL_SECONDS = float(settings.search_index_interval_seconds)
    repositories = build_repositories(settings, outbound)

    def search_index_tick(now):
        if _last_search_index[0] is None or (now - _last_search_index[0]).total_seconds() >= SEARCH_INDEX_INTERVAL_SECONDS:
            _last_search_index[0] = now
            try:
                with session_factory() as db:
                    result = reindex_all(
                        db, tickets=repositories.tickets,
                        documents=repositories.documents, now=now,
                    )
                    mirror_sync_status(db, COMPONENT_SEARCH, result, now)
                    db.commit()
            except Exception:
                logger.exception("search index tick failed")

    worker.tick_callbacks.append(search_index_tick)

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
        kwargs={"lock": lock},
        name="liveness-heartbeat",
        daemon=True,
    )
    heartbeat_thread.start()

    try:
        worker.run_forever(stop_event)
        heartbeat_thread.join(timeout=5.0)
    finally:
        # 리스는 반드시 놓는다. 안 놓으면 다음 워커가 만료(120초)까지 기다려야 하고,
        # 배포 때 재시작이 2분 멈춘 것처럼 보인다.
        lock.release()
        outbound.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
