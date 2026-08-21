"""worker_main.py의 레인 조립 — 대화형(D-118)과 스케줄러(S4 · D-225).

`main()` 자신은 시그널 핸들러+무한 루프라 기존 관례대로(test_health_snapshot_job.py 등)
소스 인용으로만 배선을 확인하고, 여기서는 실제로 부를 수 있는 조립 로직을 실행해 결과
Worker의 모양을 확인한다.

qa-contract-change: 스케줄러 평가가 배치 워커의 tick 하나에서 별도 프로세스(clovirassist-scheduler.service)로 나갔다
(S4 · D-225 — 3600초짜리 schedule_run 하나가 도는 동안 워커 루프가 그 잡 안에 있어 스케줄
발화가 통째로 밀렸다). 그래서 «배치 워커가 scheduler_tick 을 등록한다» 는 단언은 더 이상
기본값의 사실이 아니다. 약해진 것이 아니라 **강해졌다**: 예전에는 그 한 줄이 있는지만
봤는데, 이제는 설정값 양쪽에서 «정확히 한 쪽만 그 tick 을 갖는다» 를 확인한다 — 둘 다
등록되거나 둘 다 빠지는 상태가 시험에서 걸린다.
"""

import threading

import pytest

from app import worker_main
from app.jobs.lanes import (
    CONVERSATIONAL_JOB_TYPES,
    LANE_BATCH,
    LANE_CONVERSATIONAL,
    LANE_SCHEDULER,
    liveness_component,
    lock_filename,
)

pytestmark = pytest.mark.integration

#: `build_scheduler_ticks` 가 만드는 콜백 이름. 두 곳(스케줄러 레인 / 배치 워커) 중
#: 정확히 한 곳에만 있어야 한다.
SCHEDULER_TICK_NAMES = {"scheduler_tick", "zombie_run_tick"}


def _batch_tick_names(settings, fake_clock):
    session_factory, ctx, settings_cache, outbound = worker_main._bootstrap(settings, fake_clock)
    try:
        worker = worker_main.build_batch_worker(
            session_factory, fake_clock, ctx, settings, settings_cache, outbound
        )
        return {cb.__name__ for cb in worker.tick_callbacks}
    finally:
        outbound.close()


def test_build_conversational_worker_only_has_conversational_handlers(app, settings, fake_clock):
    session_factory, ctx, settings_cache, outbound = worker_main._bootstrap(settings, fake_clock)
    try:
        worker = worker_main.build_conversational_worker(session_factory, fake_clock, ctx, settings)
        assert set(worker._handlers.keys()) == set(CONVERSATIONAL_JOB_TYPES)
        assert worker._include_types == CONVERSATIONAL_JOB_TYPES
        assert worker._exclude_types == ()
        # 대화형 레인은 tick을 하나도 등록 안 한다 — D-118 §2의 1차 방어.
        assert worker.tick_callbacks == []
        # Phase 3 실측 결함(D-118) — 배치 레인의 3900초(65분) 기본값을 물려받으면 SQLite
        # 쓰기 경합으로 멈춘 채팅 잡이 65분 동안 안 회수된다. 설정값(기본 840초)을 쓴다.
        assert worker._running_timeout_seconds == settings.worker_conversational_running_timeout_seconds
        assert worker._running_timeout_seconds != 3900
    finally:
        outbound.close()


def test_build_conversational_worker_running_timeout_is_configurable(app, settings, fake_clock):
    settings.worker_conversational_running_timeout_seconds = 111
    session_factory, ctx, settings_cache, outbound = worker_main._bootstrap(settings, fake_clock)
    try:
        worker = worker_main.build_conversational_worker(session_factory, fake_clock, ctx, settings)
        assert worker._running_timeout_seconds == 111
    finally:
        outbound.close()


def test_build_batch_worker_with_lane_disabled_excludes_nothing(app, settings, fake_clock):
    """기본값(꺼짐)에서는 배치 워커가 예전처럼 전 job_type을 그대로 클레임한다 — 대화형
    레인이 실제로 뜨지 않는 한 채팅 잡의 지연을 1ms도 늘리면 안 된다."""
    assert settings.worker_conversational_lane_enabled is False
    session_factory, ctx, settings_cache, outbound = worker_main._bootstrap(settings, fake_clock)
    try:
        worker = worker_main.build_batch_worker(session_factory, fake_clock, ctx, settings, settings_cache, outbound)
        assert worker._exclude_types == ()
        assert worker._include_types is None
        assert worker._takeover_after_seconds is None
        # 배치 레인은 예전과 동일하게 잡 핸들러 전부를 갖는다(대화형 job_type 포함).
        assert set(CONVERSATIONAL_JOB_TYPES).issubset(worker._handlers.keys())
        # 기존 15개 tick이 그대로 배선돼 있다(개수 하드코딩 대신 알려진 대표 이름 몇 개로
        # 확인 — tick 함수가 클로저라 이름이 __name__에 남는다).
        names = {cb.__name__ for cb in worker.tick_callbacks}
        for expected in ("settings_cache_tick", "retention_tick", "search_index_tick"):
            assert expected in names
        # 스케줄 평가는 이제 여기 없다 — 별도 프로세스가 갖는다(D-225). 그 성질은
        # 아래 `test_exactly_one_owner_of_the_scheduler_tick` 이 양방향으로 지킨다.
        assert not (SCHEDULER_TICK_NAMES & names)
    finally:
        outbound.close()


def test_build_batch_worker_with_lane_enabled_excludes_conversational_types(app, settings, fake_clock):
    settings.worker_conversational_lane_enabled = True
    settings.worker_conversational_takeover_seconds = 45.0
    session_factory, ctx, settings_cache, outbound = worker_main._bootstrap(settings, fake_clock)
    try:
        worker = worker_main.build_batch_worker(session_factory, fake_clock, ctx, settings, settings_cache, outbound)
        assert worker._exclude_types == CONVERSATIONAL_JOB_TYPES
        assert worker._takeover_after_seconds == 45.0
    finally:
        outbound.close()


def test_main_refuses_to_run_the_conversational_lane_when_the_flag_is_off(tmp_path, monkeypatch):
    """D-118 — installing/enabling the systemd unit must not be enough on its own to
    start actively claiming chat_message/llm_connection_test; only the config flag
    decides that. Calling main() for real (not just source inspection) here is safe
    because this exact path returns before acquiring any lease or touching the DB."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKER_CONVERSATIONAL_LANE_ENABLED", "false")

    rc = worker_main.main(["--lane", "conversational"])

    assert rc == 0
    assert not (tmp_path / "worker-conversational.lock").exists(), (
        "플래그가 꺼져 있는데 대화형 레인 리스를 잡았다 — 유닛만 설치돼도 잡을 채가기 시작한다는 뜻이다"
    )
    assert not (tmp_path / "worker.lock").exists()


def test_main_dispatches_to_the_right_builder_per_lane():
    """소스 인용 — main()이 --lane에 따라 실제로 다른 조립 함수를 부르는지(어느 한쪽만
    있고 분기가 없으면 --lane 인자 자체가 죽은 설정이 된다)."""
    import inspect

    source = inspect.getsource(worker_main.main)
    assert "build_conversational_worker(" in source
    assert "build_batch_worker(" in source
    assert "run_forever_pooled(" in source
    assert "default_lock_path(settings.data_dir, lane=lane)" in source


# ── 스케줄러 레인 (S4 · D-225) ────────────────────────────────────────────────


@pytest.mark.parametrize("lane_on", [True, False])
def test_exactly_one_owner_of_the_scheduler_tick(app, settings, fake_clock, lane_on):
    """**이 시험이 이 레인 분리의 핵심이다.**

    스케줄러가 둘 도는 것과 하나도 안 도는 것은 둘 다 사고다. 앞은 스케줄이 두 번 발화하고
    (idempotency_key 가 막지만 그건 마지막 방어선이다), 뒤는 **아무 오류 없이 아무 일도 안
    일어난다** — 화면상 스케줄은 멀쩡하고 «다음 실행» 만 계속 지나간다.

    설정값 하나가 양쪽을 반대로 가른다. 켜져 있으면 배치 워커가 그 tick 을 등록하지 않고
    (스케줄러 프로세스가 갖는다), 꺼져 있으면 배치 워커가 되찾는다.
    """
    settings.worker_scheduler_lane_enabled = lane_on
    names = _batch_tick_names(settings, fake_clock)
    if lane_on:
        assert not (SCHEDULER_TICK_NAMES & names), (
            "스케줄러 레인이 켜졌는데 배치 워커도 그 tick 을 들고 있다 — 둘 다 평가한다"
        )
    else:
        assert SCHEDULER_TICK_NAMES <= names, (
            "스케줄러 레인을 껐는데 배치 워커가 그 tick 을 안 갖는다 — 스케줄이 아무 데서도 안 돈다"
        )


def test_the_default_is_the_dedicated_process():
    """기본값이 켜짐이라는 것 자체가 계약이다 — 대화형 레인(기본 꺼짐)과 반대다."""
    from app.core.config import Settings

    assert Settings(_env_file=None).worker_scheduler_lane_enabled is True


def test_scheduler_lane_has_its_own_lease_and_liveness_name():
    """레인마다 리스 파일이 달라야 서로를 밀어내지 않는다. liveness 이름은 반대로 **예전 그대로**
    여야 한다 — 대시보드의 `scheduler` 칸이 같은 것을 계속 가리켜야 하기 때문이다."""
    assert lock_filename(LANE_SCHEDULER) == "scheduler.lock"
    assert len({lock_filename(x) for x in (LANE_BATCH, LANE_CONVERSATIONAL, LANE_SCHEDULER)}) == 3
    assert liveness_component(LANE_SCHEDULER) == "scheduler"


def test_scheduler_loop_ticks_until_stopped(app, settings, fake_clock):
    """루프가 실제로 콜백을 부르고, stop_event 에 즉시 응답한다."""
    calls = []

    def fake_ticks(session_factory, clock, *, tick_seconds=1.0):
        def scheduler_tick(now):
            calls.append(now)
            stop.set()

        return [scheduler_tick]

    stop = threading.Event()
    original = worker_main.build_scheduler_ticks
    worker_main.build_scheduler_ticks = fake_ticks
    try:
        worker_main.run_scheduler_loop(None, fake_clock, stop, tick_seconds=0.01)
    finally:
        worker_main.build_scheduler_ticks = original
    assert calls, "루프가 콜백을 한 번도 안 불렀다"


def test_a_failing_tick_does_not_stop_the_loop(app, settings, fake_clock):
    """스케줄러가 조용히 멈추는 것이 이 레인의 가장 나쁜 실패다 — 예외 하나로 죽지 않는다."""
    seen = []

    def fake_ticks(session_factory, clock, *, tick_seconds=1.0):
        def boom(now):
            seen.append(now)
            if len(seen) == 1:
                raise RuntimeError("첫 tick 이 터진다")
            stop.set()

        return [boom]

    stop = threading.Event()
    original = worker_main.build_scheduler_ticks
    worker_main.build_scheduler_ticks = fake_ticks
    try:
        worker_main.run_scheduler_loop(None, fake_clock, stop, tick_seconds=0.01)
    finally:
        worker_main.build_scheduler_ticks = original
    assert len(seen) >= 2, "예외 하나에 루프가 죽었다"


def test_scheduler_lane_exits_cleanly_when_turned_off(monkeypatch):
    """되돌릴 스위치가 실제로 되돌리는지. 꺼진 상태에서 이 유닛이 뜨면 **리스를 잡기 전에**
    정상 종료해야 한다 — 안 그러면 배치 워커와 둘 다 평가한다."""
    monkeypatch.setenv("WORKER_SCHEDULER_LANE_ENABLED", "false")
    assert worker_main.main(["--lane=scheduler"]) == 0


def test_the_batch_worker_stops_beating_the_scheduler_heartbeat(app, settings, fake_clock):
    """하트비트도 소유자를 따라가야 한다.

    배치 워커가 `scheduler` 를 계속 찍으면 스케줄러 프로세스가 죽어도 대시보드는 «정상» 이라고
    말한다 — 감시가 아니라 위장이 된다. `main()` 의 그 분기를 소스로 확인한다(무한 루프라
    실행해 볼 수 없다, 이 파일 머리말의 관례).
    """
    import inspect

    source = inspect.getsource(worker_main.main)
    assert "worker_scheduler_lane_enabled" in source, (
        "main() 이 하트비트 컴포넌트를 레인 설정에 따라 가르지 않는다"
    )
    assert 'LIVENESS_COMPONENTS' in source
