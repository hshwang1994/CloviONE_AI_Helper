"""Worker entry point — 레인 셋을 한 진입점이 연다 (spec §26.2).

    python -m app.worker_main --lane batch          # clovirassist-worker.service
    python -m app.worker_main --lane conversational # clovirassist-worker-conversational.service
    python -m app.worker_main --lane scheduler      # clovirassist-scheduler.service
    python -m app.worker_main --lane index          # clovirassist-index.service

SIGTERM/SIGINT 을 받아 진행 중인 일을 마치고 내려간다.

스케줄러가 별도 레인이 된 것은 S4(D-225)다. 예전 주석은 "a separate scheduler service
remains possible without code changes" 라고 적어 뒀는데, 실제로 꺼내 보니 **코드 변경이
필요했다** — 배치 워커가 그 tick 을 계속 등록하고 하트비트까지 함께 찍고 있었기 때문이다.
둘 다 도는 상태를 만들지 않으려면 한 설정값이 양쪽을 반대로 가르게 해야 한다.
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
from app.core.logging_setup import configure_logging
from app.core.secret_refs import FileSecretReferenceProvider
from app.core.worker_lock import WorkerLock, WorkerLockError, default_lock_path
from app.jobs.worker import Worker, WorkerContext
from app.observability.models import COMPONENT_DOCUMENTS, COMPONENT_TICKETS

logger = logging.getLogger("app.worker")

# Liveness heartbeat: written from a dedicated thread so it keeps beating even
# while the worker loop is blocked inside a long run_once (schedule workflows up
# to 3600s, notion sync up to 90s). HEARTBEAT_STALE_SECONDS is 90 on the health
# side, so ~30s cadence leaves comfortable margin (spec §14.1).
HEARTBEAT_INTERVAL_SECONDS = 30.0
# 배치 워커가 **스케줄러까지 안고 돌 때** 찍는 컴포넌트 둘. 스케줄러 레인이 켜져 있으면
# (기본값) 배치 워커는 `worker` 만 찍고 `scheduler` 는 그 프로세스가 직접 찍는다 — 여기서도
# 찍으면 스케줄러가 죽어도 대시보드가 계속 «정상» 이라고 말한다(D-225).
# 하트비트를 이 스레드로 옮긴 이유는 그대로다: 긴 잡이 루프를 막아도 계속 뛰어야 한다.
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
        # OPS-11: beat_liveness()는 예외를 전부 가두는데(위 함수 docstring), renew()는
        # 무방비였다 - renew() 안의 _write()가 OSError(디스크 가득 참·권한 어긋남 등)를
        # 던지면 이 데몬 스레드가 그 예외로 조용히 죽고, stop_event 는 끝내 안 켜진다.
        # 그러면 대시보드는 하트비트가 끊겨 "워커 중단"으로 보이는데, 본 루프
        # (worker.run_forever)는 이 스레드가 죽은 줄 모른 채 잡을 계속 처리한다 - 상태
        # 표시와 실제 동작이 어긋난 좀비 상태다. 리스를 남이 가져간 경우(정상적인 False
        # 반환)와 같은 대응(멈춘다)으로 통일한다.
        lease_lost = False
        if lock is not None:
            try:
                lease_lost = not lock.renew()
            except OSError:
                logger.exception("워커 리스 갱신 중 오류 - 리스를 잃은 것으로 간주하고 중단한다.")
                lease_lost = True
        if lease_lost:
            logger.error("워커 리스를 잃었다. 다른 워커가 인수했다. 중단한다.")
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
                or getattr(state, "project_count", None)
                or getattr(state, "item_count", 0)
            ),
            truncated=bool(getattr(state, "truncated", False)),
            error=state.error,
            # 드리프트 지표 — 이번 회차가 몇 건을 지웠나. 지금까지는 어디에도 안 남아서
            # 캐시가 2000 → 0 이 되어도 {status:"ok", item_count:0} 만 보였다.
            detail={"pruned": int(getattr(state, "pruned_count", 0) or 0)},
        )
    except Exception:
        logger.exception("sync_status 미러링 실패 (무시하고 계속한다): %s", component)


# ── 주간 프로젝트 헬스 스냅샷 ─────────────────────────────────────────────────
#
# 헬스 규칙(app/projects/health.py)과 저장(service.record_health_snapshot)은 이미 있었는데
# **부르는 사람이 없었다**: `POST /{project_id}/health/snapshot` 을 손으로 누를 때만 이력이
# 쌓였고, 그래서 추세선은 사실상 영원히 비어 있었다. 여기가 그 구멍이다.
#
# 모양은 `retention_tick` 과 같다: 주기를 설정에서 읽고, 워커에서만 돌고, 실패가 워커 루프
# 밖으로 새어 나가지 않는다. 다른 점은 하나뿐이다 - **결과를 남긴다.** 이 잡은 조용히
# 성공해도 조용히 실패해도 화면이 똑같아서(추세선에 점이 하나 덜 찍힐 뿐), 자국을 안 남기면
# "이게 도는가?" 에 아무도 답할 수 없다.


def _record_sweep_status(session_factory, now, sweep, error: str | None = None) -> None:
    """회차 결과를 `sync_status` 에 남긴다. **실패해도 여기서 끝난다**(잡을 죽이지 않는다).

    새 세션을 여는 이유: 본 작업이 통째로 터진 경우에도 불리기 때문이다. 그때 원래 세션은
    쓸 수 없는 상태일 수 있고, 그 세션을 다시 쓰려다 두 번째 예외를 내면 **실패 사실 자체가
    사라진다** - 그게 이 함수가 막으려는 일이다.
    """
    from app.observability.models import (
        COMPONENT_PROJECT_HEALTH,
        SYNC_ERROR,
        SYNC_OK,
    )
    from app.observability.service import upsert_sync_status

    if sweep is None:
        # 회차가 통째로 실패했다. 건수는 **덮지 않는다**(None) - 마지막 정상 회차가 몇 건을
        # 적었는지는 여전히 사실이고, 0으로 덮으면 "이번에 못 쟀다" 가 "0건이었다" 로 바뀐다.
        fields = dict(
            status=SYNC_ERROR, item_count=None, truncated=None,
            error=error, detail={"aborted": True},
        )
    else:
        fields = dict(
            status=SYNC_ERROR if sweep.failed else SYNC_OK,
            # '이력에 적은 건수' 다. 건너뛴 것은 여기 안 센다 - 둘을 합치면 "잴 것이 없어서
            # 안 적었다" 와 "적었다" 가 화면에서 같은 숫자가 된다.
            item_count=sweep.recorded,
            truncated=sweep.truncated,
            error=sweep.error_summary(),
            detail=sweep.as_dict(),
        )
    try:
        with session_factory() as db:
            upsert_sync_status(db, COMPONENT_PROJECT_HEALTH, now=now, **fields)
            db.commit()
    except Exception:
        logger.exception("헬스 스냅샷 상태 기록 실패 (더 할 수 있는 일이 없다)")


def run_health_snapshot_sweep(session_factory, settings, now):
    """한 회차: 전 프로젝트의 그 주 헬스를 이력에 남기고 결과를 남긴다.

    예외를 **밖으로 내보내지 않는다** - 이 잡의 실패가 스케줄러 틱이나 다른 스윕을 죽이면
    안 된다. 다만 삼키지도 않는다: 스택은 로그에, 사실은 `sync_status` 에 남는다.
    실패했는데 마지막 성공 시각이 안 움직이는 것이 화면에서 "이 잡이 멈췄다" 로 읽힌다.

    돌려주는 값은 결과 객체(실패로 아무것도 못 했으면 None)다. 테스트와 호출부가 이 회차가
    무엇을 했는지 물어볼 수 있어야 한다.
    """
    from app.home.service import local_today
    from app.projects.service import record_health_snapshots

    today = local_today(settings, now).isoformat()
    try:
        with session_factory() as db:
            sweep = record_health_snapshots(db, today=today, now=now)
            db.commit()
    except Exception as exc:
        logger.exception("주간 헬스 스냅샷 회차가 통째로 실패했다 (today=%s)", today)
        _record_sweep_status(
            session_factory, now, None, error=f"{type(exc).__name__}: {exc}",
        )
        return None

    _record_sweep_status(session_factory, now, sweep)
    # 성공 회차도 한 줄 남긴다. 로그가 조용하면 "안 도는 것" 과 "돌았는데 적을 게 없던 것" 이
    # 구별되지 않는다(이 저장소가 0 과 '없음' 을 다르게 다루는 것과 같은 이유).
    log = logger.error if sweep.failed else logger.info
    log(
        "주간 헬스 스냅샷(%s): 기록 %d건, 건너뜀 %d건, 실패 %d건%s",
        today, sweep.recorded, sweep.skipped, sweep.failed,
        f" [{sweep.error_summary()}]" if sweep.failed else "",
    )
    return sweep


def register_health_snapshot_tick(worker, session_factory, settings, *, interval=None):
    """스냅샷 스윕을 워커 틱으로 등록한다. `main()` 이 부르는 유일한 배선 지점이다.

    함수로 뽑아 둔 이유: `main()` 은 리스를 잡고 시그널을 걸고 무한 루프를 도는 함수라
    테스트에서 부를 수 없다. 배선을 그 안에 인라인으로 두면 "주기 실행이 이력을 만든다" 를
    **증명할 방법이 없어지고**, 그러면 이 과제가 고친 결함(아무도 안 부른다)이 다음 번엔
    조용히 되돌아온다.
    """
    if interval is None:
        interval = float(settings.project_health_snapshot_interval_seconds)
    last: list = [None]

    def health_snapshot_tick(now):
        if last[0] is not None and (now - last[0]).total_seconds() < interval:
            return
        # 시각을 **먼저** 찍는다. 나중에 찍으면 회차가 오래 걸릴 때 그 시간만큼 다음 회차가
        # 당겨지고, 통째로 실패하는 상황에서는 매 틱마다 재시도해 루프를 잡아먹는다.
        last[0] = now
        try:
            run_health_snapshot_sweep(session_factory, settings, now)
        except Exception:
            # 여기까지 오면 안 되지만(위 함수가 이미 가둔다), 워커 루프는 어떤 경우에도
            # 살아 있어야 한다. 한 겹 더 두는 비용이 워커가 죽는 비용보다 훨씬 싸다.
            logger.exception("헬스 스냅샷 틱 실패 (워커 루프는 계속한다)")

    worker.tick_callbacks.append(health_snapshot_tick)
    return health_snapshot_tick


def build_handlers() -> dict:
    """Job handler registry."""
    from app.jobs.handlers.chat_message import handle_chat_message
    from app.jobs.handlers.document_generate import handle_document_generate
    from app.jobs.handlers.llm_connection_test import handle_llm_connection_test
    from app.jobs.handlers.mail_send import handle_mail_send
    from app.jobs.handlers.notion_mapping_sync import handle_notion_mapping_sync
    from app.jobs.handlers.project_weekly_summary import handle_project_weekly_summary
    from app.jobs.handlers.schedule_run import handle_schedule_run
    from app.llm_console.service import JOB_TYPE_TEST

    return {
        "chat_message": handle_chat_message,
        "schedule_run": handle_schedule_run,
        "document_generate": handle_document_generate,
        "notion_mapping_sync": handle_notion_mapping_sync,
        # 메일은 **여기서만** 나간다(9-9 P4). 새 큐를 만들지 않는 이유: 재시도, 백오프,
        # 좀비 회수, 실패 알림이 이미 이 큐에 있다.
        "mail_send": handle_mail_send,
        # AI 연결 테스트(9-5). 웹 요청에서 기다리면 처리 칸이 수십 초 잠긴다 -
        # 이유는 핸들러 파일 맨 위에 적어 뒀다.
        JOB_TYPE_TEST: handle_llm_connection_test,
        # 주간 리포트 AI 요약(§L 소비처). 같은 이유로 웹에서 안 부르고 잡 큐를 지난다.
        "project_weekly_summary": handle_project_weekly_summary,
    }


def _bootstrap(settings: Settings, clock: Clock):
    """레인과 무관한 공용 배선. 리스 획득(레인마다 경로가 다르다)과 `Worker` 생성(레인마다
    핸들러·필터가 다르다)은 여기 없다 — `main()`이 레인을 안 뒤에 한다(D-118 Phase 1)."""
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    allowlists = AllowlistRegistry(settings.config_dir)
    secrets = FileSecretReferenceProvider(settings.secrets_dir)
    outbound = OutboundClient(allowlists, secrets)

    from app.settings.service import SettingsCache

    # 웹과 같은 이유로 `settings` 를 넘긴다(app/main.py 의 같은 줄 참조).
    settings_cache = SettingsCache(settings)
    with session_factory() as db:
        settings_cache.load(db)

    ctx = WorkerContext(
        settings=settings, clock=clock, outbound_client=outbound,
        # secret_provider 는 메일 발송(SMTP 비밀번호)이 쓴다. OutboundClient 가 이미 같은
        # 제공자를 쥐고 있지만 그 안에 갇혀 있어 잡 핸들러가 꺼내 쓸 수 없었다.
        extras={"settings_cache": settings_cache, "secret_provider": secrets},
    )
    return session_factory, ctx, settings_cache, outbound


def build_conversational_worker(session_factory, clock: Clock, ctx: WorkerContext, settings: Settings) -> Worker:
    """대화형 레인(D-118) — `chat_message`·`llm_connection_test`만, tick 0개.

    tick을 등록하지 않는 것 자체가 1차 방어다(2차는 `Worker.run_forever_pooled`의
    assertion) — 이 함수가 `worker.tick_callbacks.append`를 한 번도 안 부르므로, 배치
    레인의 15개 tick(스케줄러·보존·백업·동기화 등) 중 어느 것도 이 프로세스에서 돌 수
    없다.

    Phase 3 실측(D-118)에서 발견: 배치 레인의 기본 `running_timeout_seconds`(3900초,
    3600초짜리 schedule_run 기준)를 그대로 두면, SQLite 쓰기 경합으로 잡이 멈춰도
    최대 65분 동안 sweep이 회수하지 않는다 — 채팅은 수십 초 안에 끝나는 레인이라 그
    격차가 훨씬 크게 느껴진다. n8n 타임아웃(180초) 기준의 훨씬 짧은 값을 쓴다."""
    from app.jobs.lanes import CONVERSATIONAL_JOB_TYPES

    handlers = {k: v for k, v in build_handlers().items() if k in CONVERSATIONAL_JOB_TYPES}
    return Worker(
        session_factory, clock, handlers, ctx,
        include_types=CONVERSATIONAL_JOB_TYPES,
        running_timeout_seconds=settings.worker_conversational_running_timeout_seconds,
    )


ZOMBIE_SWEEP_INTERVAL_SECONDS = 300.0


def build_scheduler_ticks(session_factory, clock: Clock, *, tick_seconds: float = 1.0) -> list:
    """스케줄러가 하는 일 전부를 tick 콜백 두 개로 만든다 (S4 · D-225).

    **한 곳에서 만드는 것이 요점이다.** 이 둘은 스케줄러 레인 프로세스(`--lane=scheduler`)와
    배치 워커(레인을 껐을 때) 양쪽에서 돌 수 있는데, 두 자리에 각자 적어 두면 한쪽만
    고치는 날이 온다 — 이 저장소가 이미 여러 번 겪은 패턴이다(D-22).

    콜백은 `now` 하나를 받는다. `Worker.tick_callbacks` 의 계약과 같은 모양이라 배치
    워커에 그대로 얹을 수 있고, 스케줄러 루프는 같은 것을 직접 부른다.
    """
    from app.schedules.scheduler import SchedulerService, sweep_zombie_runs

    scheduler = SchedulerService(session_factory, clock)
    _last_tick: list = [None]
    _last_zombie: list = [None]

    def scheduler_tick(now):
        # 루프가 이보다 빨리 돌 수 있으므로 간격을 여기서 정한다.
        # NOTE: 스케줄러 LIVENESS 하트비트는 여기서 안 쓴다 — 긴 잡이 루프를 막아도 계속
        # 뛰도록 전용 하트비트 스레드(run_heartbeat_loop)로 옮겼다. 이 콜백은 실제
        # 스케줄링 작업만 한다.
        if _last_tick[0] is None or (now - _last_tick[0]).total_seconds() >= tick_seconds:
            _last_tick[0] = now
            scheduler.tick(now)

    def zombie_run_tick(now):
        # 좀비 실행 스윕 (S8) — 5분 간격. `Worker.sweep` 은 `Job` 만 보므로 `on_failure` 가
        # 실패해 `running` 으로 남은 `ScheduleRun` 을 치우는 경로가 저장소에 없었다. 그 한 행이
        # `concurrency=skip` 스케줄의 **모든 미래 실행을 영구히 skip** 시킨다.
        if (_last_zombie[0] is not None
                and (now - _last_zombie[0]).total_seconds() < ZOMBIE_SWEEP_INTERVAL_SECONDS):
            return
        _last_zombie[0] = now
        try:
            with session_factory() as db:
                if sweep_zombie_runs(db, now=now):
                    db.commit()
        except Exception:
            logger.exception("zombie schedule-run sweep failed")

    return [scheduler_tick, zombie_run_tick]


def run_scheduler_loop(
    session_factory,
    clock: Clock,
    stop_event: threading.Event,
    *,
    tick_seconds: float = 1.0,
) -> None:
    """스케줄러 레인의 루프 (S4 · D-225). **잡을 하나도 클레임하지 않는다.**

    `Worker` 를 쓰지 않는 것이 의도다. `Worker.run_forever` 는 큐에서 잡을 집어 실행하는데,
    이 프로세스가 그걸 하면 스케줄 발화가 다시 잡 실행 뒤로 밀린다 — 분리한 이유가 사라진다.
    핸들러가 아예 없으니 실수로도 잡을 못 집는다.

    한 tick 이 예외로 죽어도 루프는 계속 돈다. 스케줄러가 조용히 멈추는 것이 이 레인의
    가장 나쁜 실패다 — 아무 오류도 안 나고 그냥 아무 일도 안 일어난다.
    """
    callbacks = build_scheduler_ticks(session_factory, clock, tick_seconds=tick_seconds)
    logger.info("스케줄러 레인 시작(tick=%.1fs)", tick_seconds)
    while not stop_event.is_set():
        now = clock.now()
        for callback in callbacks:
            try:
                callback(now)
            except Exception:
                logger.exception("scheduler tick failed")
        stop_event.wait(tick_seconds)
    logger.info("스케줄러 레인 정상 종료")


#: 색인 레인이 한 판 돌고 다음 판까지 쉬는 시간. 스케줄러(1초)보다 훨씬 길다 —
#: 색인은 사람이 화면 앞에서 기다리는 일이 아니고, 매초 훑기 질의를 던질 이유가 없다.
INDEX_IDLE_SECONDS = 10.0
#: 할 일이 있었으면 곧바로 다음 판을 돈다. 밀린 문서 백 건을 10초 간격으로 처리하면
#: 「색인이 안 된다」로 보인다.
INDEX_BUSY_SECONDS = 0.5


def run_index_loop(
    session_factory,
    clock: Clock,
    stop_event: threading.Event,
    settings: Settings,
    *,
    idle_seconds: float = INDEX_IDLE_SECONDS,
) -> None:
    """색인 레인의 루프 (S9 · D-203). **잡을 하나도 클레임하지 않는다.**

    스케줄러 레인과 같은 모양이다. `Worker` 를 쓰지 않는 것이 의도다 — 이 프로세스가
    잡을 집으면 색인이 다시 잡 실행 뒤로 밀리고, 분리한 이유가 사라진다. 핸들러가 아예
    없으니 실수로도 잡을 못 집는다.

    Gateway 는 **한 번만** 만든다. ONNX 세션 로드가 2.3초라(D-211) 매 tick 마다 만들면
    그 시간이 곧 색인 시간이 된다.

    한 판이 예외로 죽어도 루프는 계속 돈다. 색인이 조용히 멈추는 것이 이 레인의 가장
    나쁜 실패다 — 아무 오류도 안 나고 그냥 검색 결과가 낡는다.
    """
    from app.ai.gateway.registry import build_gateway
    from app.ai.index import service as index_service

    gateway = build_gateway(settings)
    caps = gateway.capabilities()
    logger.info(
        "색인 레인 시작(embed=%s status=%s)", caps.embed.available, caps.embed.status
    )
    while not stop_event.is_set():
        processed = 0
        try:
            now = clock.now()
            with session_factory() as db:
                processed = index_service.run_once(
                    db, gateway=gateway, now=now, limit=settings.index_batch_documents
                )
                db.commit()
        except Exception:
            logger.exception("색인 tick 이 실패했다")
        stop_event.wait(INDEX_BUSY_SECONDS if processed else idle_seconds)
    logger.info("색인 레인 정상 종료")


def build_batch_worker(session_factory, clock: Clock, ctx: WorkerContext, settings: Settings, settings_cache, outbound) -> Worker:
    """배치 레인 — 기존 워커 전체(잡 핸들러 전부 + tick 15개)를 그대로 옮긴 것이다.

    `worker_conversational_lane_enabled`가 꺼져 있으면(기본값) `exclude_types`를 전혀
    안 줘 이 워커가 예전처럼 전 job_type을 그대로 클레임한다 — 대화형 레인이 실제로 뜨지
    않는 한 채팅 잡의 지연을 단 1ms도 늘리지 않는다. 켜져 있을 때만 대화형 job_type을
    제외하고(`takeover_after_seconds` 유예 포함) 별도 프로세스에 그 몫을 넘긴다."""
    from app.jobs.lanes import CONVERSATIONAL_JOB_TYPES

    lane_kwargs: dict = {}
    if settings.worker_conversational_lane_enabled:
        lane_kwargs = {
            "exclude_types": CONVERSATIONAL_JOB_TYPES,
            "takeover_after_seconds": settings.worker_conversational_takeover_seconds,
        }
    worker = Worker(session_factory, clock, build_handlers(), ctx, **lane_kwargs)

    # 동기화 주기는 **매 틱마다** 다시 읽는다 (지시 1 · 29).
    #
    # 예전에는 아래 네 틱이 등록 시점에 `float(settings.<key>)` 를 한 번만 읽어 상수로
    # 굳혔다. 그래서 관리자가 주기를 바꿔도 워커를 재시작하기 전까지는 옛 값으로 돌았다 —
    # 화면은 "저장했습니다" 라고 말하는데 실제 동작은 안 바뀌는, 이 저장소가 가장 싫어하는
    # 종류의 거짓말이다. 캐시 재적재 틱이 60초마다 돌고 그 콜백이 맨 앞에 등록돼 있으므로,
    # 같은 반복 안에서 이미 새로 고친 값을 읽는다.
    #
    # 레지스트리 값 `0` 은 "서버 기본값을 따른다" 센티널이다(app/settings/registry.py).
    def _sync_interval(key: str, fallback: float) -> float:
        try:
            raw = settings_cache.current_value(key)
        except Exception:  # 캐시가 아직 안 떴거나 비정상이면 기본값으로 돈다.
            return fallback
        if raw is None or isinstance(raw, bool):
            return fallback
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return fallback
        return value if value > 0 else fallback

    # 설정 캐시 재적재 — 60초 간격. 이 콜백을 **맨 먼저** 등록한다: 같은 반복(iteration)
    # 안에서 다른 콜백(스케줄러, 백업, 보존, 티켓/문서/프로젝트 미러 동기화)보다 먼저 돌아야
    # 그 콜백들이 이번 반복에서 이미 새로 고친 값을 읽는다.
    #
    # 예전엔 `SettingsCache.load` 를 부르는 곳이 부팅·백업 틱(600초)·보존 틱(3600초)
    # 셋뿐이었다 - 관리자가 Notion 작업 DB id 를 바꿔도 티켓 미러 동기화(180초 간격)는
    # 최대 600초 동안 옛 DB 를 읽어 그 결과를 같은 미러에 계속 써 넣었다(두 소스가 섞인
    # 미러). 60초는 가장 짧은 소비 주기(티켓 동기화 180초)보다 확실히 촘촘해, 그 다음 동기화
    # 틱은 항상 최근 값을 본다.
    _last_settings_reload: list = [None]
    SETTINGS_RELOAD_INTERVAL_SECONDS = 60.0

    def settings_cache_tick(now):
        if (_last_settings_reload[0] is not None
                and (now - _last_settings_reload[0]).total_seconds() < SETTINGS_RELOAD_INTERVAL_SECONDS):
            return
        _last_settings_reload[0] = now
        try:
            with session_factory() as db:
                settings_cache.load(db)
        except Exception:
            logger.exception("settings cache reload tick failed")

    worker.tick_callbacks.append(settings_cache_tick)

    # 스케줄 평가와 좀비 실행 스윕 (S4 · D-225).
    #
    # 이 둘은 이제 **기본적으로 이 프로세스에서 돌지 않는다** — `clovirassist-scheduler.service`
    # 가 별도 프로세스로 돈다(`--lane=scheduler`). 배치 워커의 tick 이던 시절에는 3600초짜리
    # schedule_run 하나가 도는 동안 워커 루프가 그 잡 안에 있어 스케줄 발화가 통째로 밀렸다.
    #
    # `worker_scheduler_lane_enabled` 를 끄면 여기로 되돌아온다. **같은 값이 양쪽을 반대로
    # 가르므로**(스케줄러 프로세스는 꺼져 있으면 리스를 잡기 전에 exit(0) 한다) 둘 다 도는
    # 상태는 만들어지지 않는다.
    if not settings.worker_scheduler_lane_enabled:
        for callback in build_scheduler_ticks(session_factory, clock):
            worker.tick_callbacks.append(callback)

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

    # 임퍼소네이션 만료 스윕 (UB-27) — 1분 간격, approval_expiry_tick과 같은 이유(요청 없이
    # 만료된 상태를 방치하면 "진행 중" 목록이 거짓말을 한다).
    from app.impersonation.service import sweep_expired as sweep_expired_impersonations

    _last_impersonation_sweep: list = [None]

    def impersonation_expiry_tick(now):
        if (
            _last_impersonation_sweep[0] is None
            or (now - _last_impersonation_sweep[0]).total_seconds() >= 60.0
        ):
            _last_impersonation_sweep[0] = now
            try:
                with session_factory() as db:
                    sweep_expired_impersonations(db, now=now)
                    db.commit()
            except Exception:
                logger.exception("impersonation expiry sweep failed")

    worker.tick_callbacks.append(impersonation_expiry_tick)

    # 승인 SLA 스윕 (0033, PLAN Phase 6) — 5분 간격. 만료 스윕과 나눈 이유: 만료는 요청을
    # 죽이는 상태 변경이라 1분마다 돌아야 정확하고, 기한 초과 알림은 사람에게 보내는 것이라
    # 그렇게 자주 볼 필요가 없다(그리고 같은 틱에 묶으면 알림 폭주가 만료 처리를 지연시킨다).
    from app.approvals.delegation import notify_overdue

    _last_sla: list = [None]

    def approval_sla_tick(now):
        if _last_sla[0] is None or (now - _last_sla[0]).total_seconds() >= 300.0:
            _last_sla[0] = now
            try:
                with session_factory() as db:
                    notify_overdue(db, now=now)
                    db.commit()
            except Exception:
                logger.exception("approval SLA sweep failed")

    worker.tick_callbacks.append(approval_sla_tick)

    # 예약 백업 (0033, PLAN Phase 6) — 10분 간격으로 '지금 돌 차례인가'만 확인한다.
    # 판정이 멱등이라(직전 예정 시각 이후 성공한 백업이 있는가) 워커가 재시작해도 두 번
    # 돌지 않고, 확인 주기가 실행 주기가 아니다.
    from app.backups.service import (
        backup_schedule_config,
        check_backup_health,
        due_for_scheduled_backup,
        reap_stuck_running,
        run_scheduled_backup,
    )

    _last_backup_check: list = [None]

    def backup_schedule_tick(now):
        if _last_backup_check[0] is not None and (now - _last_backup_check[0]).total_seconds() < 600.0:
            return
        _last_backup_check[0] = now
        try:
            with session_factory() as db:
                settings_cache.load(db)
                config = backup_schedule_config(settings_cache)
                if due_for_scheduled_backup(db, config, now=now):
                    row = run_scheduled_backup(db, settings, config, now=now)
                    if row is not None:
                        logger.info("예약 백업 완료: %s (%s)", row.id, row.status)
                # RSTR-03: 백업이 실패하면 위 run_scheduled_backup이 이미 알린다 — 이 검사는
                # "실패"가 아니라 "꺼져 있음"·"너무 오래 안 돎"을 잡는다(하루 최대 1회).
                check_backup_health(db, config, now=now)
                # UA-18: 예전엔 이 정리가 GET /api/admin/backups 를 열 때만 돌아서, 아무도
                # 화면을 안 보면 죽은 채 'running'으로 멈춘 백업이 계속 남았다(그 GET 은
                # require_csrf 가 안전 메서드로 통과시켜 CSRF 로부터도 무방비였다). 여기
                # 10분 틱으로 옮겨 "사람이 봐야만 청소된다"를 없앤다 — 목록 화면은 더는
                # 이 정리를 트리거하지 않고 순수 읽기가 된다(router.py 쪽 호출 제거).
                reap_stuck_running(db, now=now)
                db.commit()
        except Exception:
            logger.exception("backup schedule tick failed")

    worker.tick_callbacks.append(backup_schedule_tick)

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

    # 연동(Integration) 헬스 자동 점검 — 러너와 같은 이유·같은 90초 간격(WF1 감사: 수동
    # POST /{id}/health만 있어 25일 전 점검 결과가 지금 상태처럼 초록 「정상」으로 보였다).
    # 러너 스윕과 별도 tick으로 두는 이유: 한쪽이 느려지거나 실패해도(outbound 호출이라
    # 잠깐 걸릴 수 있다) 다른 쪽 스윕 주기에 영향을 주지 않는다.
    from app.integrations.service import run_all_integration_health_checks

    _last_integration_health: list = [None]
    INTEGRATION_HEALTH_INTERVAL_SECONDS = 90.0

    def integration_health_tick(now):
        if _last_integration_health[0] is None or (now - _last_integration_health[0]).total_seconds() >= INTEGRATION_HEALTH_INTERVAL_SECONDS:
            _last_integration_health[0] = now
            try:
                with session_factory() as db:
                    run_all_integration_health_checks(db, outbound=outbound, now=now)
                    db.commit()
            except Exception:
                logger.exception("integration health sweep failed")

    worker.tick_callbacks.append(integration_health_tick)

    # 문서 캐시 주기 동기화 (spec §17.2/§17.4) — notion_docs_sync_interval_seconds 간격.
    # 첫 tick 즉시 실행 → 워커 기동 직후 문서 목록이 채워진다. Notion 장애/미설정이면 sync
    # 상태에만 기록되고 캐시(마지막 정상 동기화)는 유지된다 — sync_documents 내부에서 예외를
    # 가두므로 티켓 등 다른 기능엔 무영향.
    from app.team_docs.sync import sync_documents

    _last_docs_sync: list = [None]
    DOCS_SYNC_FALLBACK_SECONDS = float(settings.notion_docs_sync_interval_seconds)

    def docs_sync_tick(now):
        interval = _sync_interval("notion_docs_sync_interval_seconds", DOCS_SYNC_FALLBACK_SECONDS)
        if _last_docs_sync[0] is None or (now - _last_docs_sync[0]).total_seconds() >= interval:
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
    TICKETS_SYNC_FALLBACK_SECONDS = float(settings.notion_tickets_sync_interval_seconds)

    def tickets_sync_tick(now):
        interval = _sync_interval("notion_tickets_sync_interval_seconds", TICKETS_SYNC_FALLBACK_SECONDS)
        if _last_tickets_sync[0] is None or (now - _last_tickets_sync[0]).total_seconds() >= interval:
            _last_tickets_sync[0] = now
            try:
                with session_factory() as db:
                    state = sync_tickets(db, outbound=outbound, settings=settings, now=now)
                    mirror_sync_status(db, COMPONENT_TICKETS, state, now)
                    db.commit()
            except Exception:
                logger.exception("tickets sync tick failed")

    worker.tick_callbacks.append(tickets_sync_tick)

    # 프로젝트 미러 주기 동기화 (0045) — notion_projects_sync_interval_seconds 간격.
    # 티켓 미러 **뒤에** 등록한다: 프로젝트 진행률은 `ticket_cache` 를 세므로, 첫 틱에서
    # 티켓이 먼저 채워져야 새로 들어온 프로젝트가 "작업 0건"으로 보이지 않는다.
    # sync_projects 가 내부에서 예외를 가두므로 이 tick 도 루프 밖으로 아무것도 던지지 않는다.
    from app.observability.models import COMPONENT_PROJECTS
    from app.projects.sync import sync_projects

    _last_projects_sync: list = [None]
    PROJECTS_SYNC_FALLBACK_SECONDS = float(settings.notion_projects_sync_interval_seconds)

    def projects_sync_tick(now):
        interval = _sync_interval("notion_projects_sync_interval_seconds", PROJECTS_SYNC_FALLBACK_SECONDS)
        if _last_projects_sync[0] is None or (now - _last_projects_sync[0]).total_seconds() >= interval:
            _last_projects_sync[0] = now
            try:
                with session_factory() as db:
                    state = sync_projects(db, outbound=outbound, settings=settings, now=now)
                    mirror_sync_status(db, COMPONENT_PROJECTS, state, now)
                    db.commit()
            except Exception:
                logger.exception("projects sync tick failed")

    worker.tick_callbacks.append(projects_sync_tick)

    # 주간 프로젝트 헬스 스냅샷 — project_health_snapshot_interval_seconds 간격.
    #
    # **프로젝트 미러 뒤에 등록한다.** 헬스 규칙은 `ticket_cache` 와 프로젝트 행을 세므로,
    # 첫 틱에서 티켓 미러와 프로젝트 미러가 먼저 채워져야 한다. 앞에 두면 워커 기동 직후
    # 첫 회차가 빈 표본으로 점수를 매기고, 그 점수가 **그 주의 이력으로 남는다** - 이력은
    # 나중에 덮이더라도 그 주의 첫 판단이 거짓이었다는 사실은 화면에 안 보인다.
    #
    # 배선을 함수로 뽑아 둔 이유는 `register_health_snapshot_tick` 의 docstring 에 있다:
    # 여기 인라인으로 두면 "주기 실행이 이력을 만든다" 를 테스트가 증명할 방법이 없다.
    register_health_snapshot_tick(worker, session_factory, settings)

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
    SEARCH_INDEX_FALLBACK_SECONDS = float(settings.search_index_interval_seconds)
    repositories = build_repositories(settings, outbound)

    def search_index_tick(now):
        interval = _sync_interval("search_index_interval_seconds", SEARCH_INDEX_FALLBACK_SECONDS)
        if _last_search_index[0] is None or (now - _last_search_index[0]).total_seconds() >= interval:
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
    return worker


def main(argv: list[str] | None = None) -> int:
    """워커 진입점.
    `--lane batch`(기본)|`conversational`(D-118)|`scheduler`(D-225)|`index`(D-203).

    인자 없이 부르면 `argparse`의 `default=LANE_BATCH`가 배치 레인으로 떨어진다 — 옛
    유닛처럼 `--lane`을 안 주는 호출도 그대로 배치 워커가 된다.

    레인마다 리스 파일이 다르고(`app/jobs/lanes.py::lock_filename`) liveness 컴포넌트
    이름도 다르다. 리스를 못 잡으면 **뜨지 않는다** — 같은 레인이 둘 도는 것보다 하나도
    안 도는 편이 안전하다.
    """
    import argparse

    from app.jobs.lanes import (
        LANE_BATCH,
        LANE_CONVERSATIONAL,
        LANE_INDEX,
        LANE_SCHEDULER,
        liveness_component,
    )

    parser = argparse.ArgumentParser(prog="app.worker_main")
    parser.add_argument(
        "--lane",
        default=LANE_BATCH,
        choices=(LANE_BATCH, LANE_CONVERSATIONAL, LANE_INDEX, LANE_SCHEDULER),
    )
    args = parser.parse_args(argv)
    lane = args.lane

    # 웹(`create_app`)과 같은 설정을 쓴다. 예전에는 여기만 설정이 있어서 **워커 로그는 보이고
    # 웹 로그는 안 보이는** 비대칭이 있었다 — RUNBOOK 의 journalctl 안내가 반만 맞았던 이유다.
    configure_logging()
    settings = Settings()
    clock = SystemClock()

    # D-118: `--lane=conversational`은 설정 플래그와 별개로 systemd 유닛이 존재/활성화만
    # 되면 항상 실행될 수 있다 — 유닛 파일이 설치돼 있는 것과 그 레인이 실제로 운영 중인
    # 것은 다른 결정이어야 한다(설치는 배포 스크립트가, 실제로 켜는 것은 이 설정값이
    # 판단해야 한다). 이 검사가 없으면 유닛만 깔려 있어도(플래그는 꺼진 채) 대화형 워커가
    # 곧바로 chat_message/llm_connection_test를 채가기 시작해, "플래그가 꺼지면 배치
    # 레인만 처리한다"는 D-119의 전제가 깨진다. 리스를 잡기 **전에** 확인해 불필요한 리스
    # 파일 churn도 없앤다. `Restart=on-failure`라 exit(0)은 재시작 루프를 만들지 않는다 —
    # 플래그를 나중에 켜면 운영자가 이 유닛을 다시 시작해야 한다(설정 변경 후 재시작은
    # 이 저장소의 기존 관례와 같다).
    if lane == LANE_CONVERSATIONAL and not settings.worker_conversational_lane_enabled:
        logger.info(
            "lane=conversational이지만 worker_conversational_lane_enabled가 꺼져 있다. "
            "리스를 잡지 않고 정상 종료한다(D-118). 켜려면 설정을 바꾼 뒤 이 유닛을 재시작하라."
        )
        return 0

    # 스케줄러 레인도 같은 모양이다(S4 · D-225). 다만 **기본이 켜짐**이라 이 문은 되돌릴
    # 때만 열린다. 꺼져 있으면 여기서 정상 종료하고 배치 워커가 스케줄러 tick 을 다시
    # 등록한다 — 둘 다 도는 상태는 만들어지지 않는다.
    if lane == LANE_SCHEDULER and not settings.worker_scheduler_lane_enabled:
        logger.info(
            "lane=scheduler이지만 worker_scheduler_lane_enabled가 꺼져 있다. "
            "리스를 잡지 않고 정상 종료한다(D-225) — 스케줄은 배치 워커가 계속 평가한다."
        )
        return 0

    # 색인 레인도 같은 모양이다(S9 · D-203). 기본이 켜짐이라 이 문도 되돌릴 때만 열린다.
    # **꺼도 배치 워커가 대신 색인하지 않는다** — 스케줄러와 다른 점이 이것이다. 색인을
    # 배치 레인에 되돌리면 임베딩이 배치 틱을 굶기는 상태로 돌아가는데, 그것이 이 레인을
    # 만든 이유다. 끄면 색인이 **멈춘다**: `ai_index_state` 가 `pending` 으로 쌓이고
    # `ai_cli status` 와 대시보드가 그 숫자를 그대로 말한다.
    if lane == LANE_INDEX and not settings.worker_index_lane_enabled:
        logger.info(
            "lane=index이지만 worker_index_lane_enabled가 꺼져 있다. "
            "리스를 잡지 않고 정상 종료한다(D-203). 이 상태에서는 색인이 멈춘다."
        )
        return 0

    # 싱글턴 리스(§ 스케일 심, D-118로 레인마다 별도 파일). 워커가 둘 돌면 잡이 두 번
    # 실행되고 스케줄이 두 번 발화한다. systemd 재시작 중첩, 운영자가 진단하려고 손으로
    # 띄운 워커, 배포 스크립트의 중복 start — 셋 다 실제로 있는 경로다. 잡지 못하면
    # **뜨지 않는다**(조용히 둘째로 돌지 않는다).
    lock = WorkerLock(default_lock_path(settings.data_dir, lane=lane))
    try:
        acquired = lock.acquire()
    except WorkerLockError:
        # OPS-10: 리스 경쟁(다른 워커가 있다)이 아니라 파일시스템이 리스 자체를 못 쓰게
        # 한다(권한 어긋남·디스크 가득 참 등) - 여기서 잡지 않으면 트레이스백과 함께
        # 죽고 systemd 가 RestartSec=3 로 계속 재시도하며 같은 이유로 또 죽는다(재시작
        # 루프). 명확한 원인과 함께 조용히 종료해, 유닛의 완화된 재시작 정책
        # (deploy/systemd/clovirassist-worker.service - RestartSec 10, StartLimitBurst)이
        # 감당하게 한다.
        logger.exception(
            "워커 리스 파일을 쓸 수 없다(lock=%s) - 디렉터리 권한이나 디스크 공간을 확인하라.",
            lock.path,
        )
        return 1
    if not acquired:
        holder = (lock.read() or {}).get("owner", "?")
        logger.error(
            "다른 워커가 이미 돌고 있다(lane=%s, owner=%s, lock=%s). 중복 실행을 막기 위해 종료한다. "
            "정말 이전 워커가 죽었다면 리스가 만료된 뒤(기본 120초) 다시 시도하면 인수한다.",
            lane, holder, lock.path,
        )
        return 1
    logger.info("워커 리스 획득(lane=%s): %s", lane, lock.owner)

    session_factory, ctx, settings_cache, outbound = _bootstrap(settings, clock)
    worker = None
    if lane == LANE_CONVERSATIONAL:
        worker = build_conversational_worker(session_factory, clock, ctx, settings)
        components = (liveness_component(LANE_CONVERSATIONAL),)
    elif lane == LANE_SCHEDULER:
        components = (liveness_component(LANE_SCHEDULER),)
    elif lane == LANE_INDEX:
        components = (liveness_component(LANE_INDEX),)
    else:
        worker = build_batch_worker(session_factory, clock, ctx, settings, settings_cache, outbound)
        # 스케줄러를 별도 프로세스로 꺼냈으면 그 하트비트도 그쪽이 찍는다. 여기서도 찍으면
        # 스케줄러 프로세스가 죽어도 대시보드가 계속 «정상» 이라고 말한다 — 감시가 아니라
        # 위장이 된다.
        components = (
            ("worker",) if settings.worker_scheduler_lane_enabled else LIVENESS_COMPONENTS
        )

    stop_event = threading.Event()

    def _shutdown(signum, _frame):
        logger.info("signal %s: graceful shutdown", signum)
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
        kwargs={"lock": lock, "components": components},
        name="liveness-heartbeat",
        daemon=True,
    )
    heartbeat_thread.start()

    try:
        if lane == LANE_CONVERSATIONAL:
            worker.run_forever_pooled(stop_event, max_concurrency=settings.worker_conversational_concurrency)
        elif lane == LANE_SCHEDULER:
            run_scheduler_loop(
                session_factory, clock, stop_event,
                tick_seconds=settings.worker_scheduler_tick_seconds,
            )
        elif lane == LANE_INDEX:
            run_index_loop(session_factory, clock, stop_event, settings)
        else:
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
