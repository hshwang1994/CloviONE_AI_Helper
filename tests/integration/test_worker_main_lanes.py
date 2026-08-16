"""D-118 Phase 1 — worker_main.py의 레인 조립 함수(`build_batch_worker`/
`build_conversational_worker`). `main()` 자신은 시그널 핸들러+무한 루프라 기존
관례대로(test_health_snapshot_job.py 등) 소스 인용으로만 배선을 확인하고, 여기서는
실제로 부를 수 있는 조립 로직을 실행해 결과 Worker의 모양을 확인한다.
"""

import pytest

from app import worker_main
from app.jobs.lanes import CONVERSATIONAL_JOB_TYPES

pytestmark = pytest.mark.integration


def test_build_conversational_worker_only_has_conversational_handlers(app, settings, fake_clock):
    session_factory, ctx, settings_cache, outbound = worker_main._bootstrap(settings, fake_clock)
    try:
        worker = worker_main.build_conversational_worker(session_factory, fake_clock, ctx, settings)
        assert set(worker._handlers.keys()) == set(CONVERSATIONAL_JOB_TYPES)
        assert worker._include_types == CONVERSATIONAL_JOB_TYPES
        assert worker._exclude_types == ()
        # 대화형 레인은 tick을 하나도 등록 안 한다 — D-118 §2의 1차 방어.
        assert worker.tick_callbacks == []
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
        for expected in ("settings_cache_tick", "scheduler_tick", "retention_tick", "search_index_tick"):
            assert expected in names
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
