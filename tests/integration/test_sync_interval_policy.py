"""동기화 주기를 관리 콘솔에서 정한다 (지시 1 · 29).

예전에는 네 주기가 전부 env 기본값 상수였고, 워커 틱이 **등록 시점에 한 번만** 읽어
상수로 굳혔다. 그래서 두 가지 결함이 함께 있었다.

1. 관리자 화면에 그 값이 아예 없었다 — 바꾸려면 서버 파일을 고치고 워커를 재시작해야 했다.
   그 공백을 사용자 목록 화면의 "지금 동기화" 버튼이 메우고 있었다(지시 29 가 없애라고 한
   바로 그 버튼).
2. 정책을 바꿔도 **재시작 전까지 반영되지 않았다** — 화면은 "저장했습니다"라고 말하는데
   실제 동작은 옛 값이었다.

여기서 증명하는 것:
  - 레지스트리가 네 키를 갖고, 검증이 위험한 값을 막는다.
  - 틱이 **매번** 캐시를 다시 읽는다(등록 시점 상수가 아니다).
  - `0` 은 "서버 기본값을 따른다" 센티널이라 env 로 정해 둔 설치가 조용히 안 바뀐다.
"""

from datetime import timedelta

import pytest

from app import worker_main
from app.core.errors import ValidationAppError
from app.settings.registry import REGISTRY

pytestmark = pytest.mark.integration

INTERVAL_KEYS = (
    "notion_docs_sync_interval_seconds",
    "notion_tickets_sync_interval_seconds",
    "notion_projects_sync_interval_seconds",
    "search_index_interval_seconds",
)


def test_registry_exposes_every_sync_interval():
    for key in INTERVAL_KEYS:
        spec = REGISTRY[key]
        assert spec.value_type == "int"
        # 기본값 0 = "서버 기본값을 따른다". 실제 숫자를 박아 두면 env 로 주기를 정해 둔
        # 기존 설치가 업그레이드하는 순간 조용히 다른 값으로 바뀐다.
        assert spec.default == 0
        # 틱이 매 회차 값을 다시 읽으므로 재시작이 필요 없다.
        assert spec.restart_required is False


@pytest.mark.parametrize("bad", [1, 59, 86401, -1, True, "600", 1.5])
def test_registry_rejects_dangerous_intervals(bad):
    spec = REGISTRY["notion_tickets_sync_interval_seconds"]
    with pytest.raises(ValidationAppError):
        spec.validate(bad)


@pytest.mark.parametrize("ok", [0, 60, 600, 86400])
def test_registry_accepts_sane_intervals(ok):
    REGISTRY["notion_tickets_sync_interval_seconds"].validate(ok)


def _tick(worker, name):
    for cb in worker.tick_callbacks:
        if cb.__name__ == name:
            return cb
    raise AssertionError(f"{name} 을 찾지 못했다")


def test_ticks_reread_the_interval_every_time(app, settings, fake_clock, monkeypatch):
    """정책을 바꾸면 **재시작 없이** 다음 틱부터 그 주기로 돈다."""
    session_factory, ctx, settings_cache, outbound = worker_main._bootstrap(settings, fake_clock)
    try:
        worker = worker_main.build_batch_worker(
            session_factory, fake_clock, ctx, settings, settings_cache, outbound)

        # 실제 Notion 호출까지 갈 필요가 없다 — 여기서 보려는 것은 "몇 초마다 부르는가"다.
        monkeypatch.setattr("app.tickets.sync.sync_tickets", lambda *a, **k: None, raising=False)

        tick = _tick(worker, "tickets_sync_tick")
        now = fake_clock.now()

        # 첫 회차는 언제나 즉시 돈다(워커 기동 직후 미러가 비어 있지 않게).
        tick(now)
        assert _last_run_at(worker, "tickets") == now

        # 기본값(0) → 서버 기본값 180초. 60초 뒤에는 아직 안 돈다.
        tick(now + timedelta(seconds=60))
        assert _last_run_at(worker, "tickets") == now

        # 관리자가 주기를 60초로 줄인다. **재시작하지 않는다.**
        settings_cache._values = dict(settings_cache.current())
        settings_cache._values["notion_tickets_sync_interval_seconds"] = 60

        later = now + timedelta(seconds=120)
        tick(later)
        assert _last_run_at(worker, "tickets") == later, (
            "정책을 바꿨는데 틱이 옛 주기로 돌았다 — 등록 시점 상수를 다시 읽지 않는다")
    finally:
        outbound.close()


def _last_run_at(worker, which):
    """틱 클로저가 들고 있는 마지막 실행 시각을 꺼낸다."""
    name = {"tickets": "tickets_sync_tick"}[which]
    cb = _tick(worker, name)
    for cell in cb.__closure__ or ():
        v = cell.cell_contents
        if isinstance(v, list) and len(v) == 1:
            return v[0]
    raise AssertionError("마지막 실행 시각을 못 찾았다")


def test_zero_means_follow_the_server_default(app, settings, fake_clock):
    """`0` 은 "안 정함"이다 — env 로 주기를 정해 둔 설치가 조용히 안 바뀐다."""
    settings.notion_tickets_sync_interval_seconds = 999
    session_factory, ctx, settings_cache, outbound = worker_main._bootstrap(settings, fake_clock)
    try:
        worker = worker_main.build_batch_worker(
            session_factory, fake_clock, ctx, settings, settings_cache, outbound)
        tick = _tick(worker, "tickets_sync_tick")
        now = fake_clock.now()
        tick(now)
        # 레지스트리 기본값 0 이므로 env 의 999초가 그대로 쓰인다 — 998초에는 안 돈다.
        tick(now + timedelta(seconds=998))
        assert _last_run_at(worker, "tickets") == now
        tick(now + timedelta(seconds=1000))
        assert _last_run_at(worker, "tickets") == now + timedelta(seconds=1000)
    finally:
        outbound.close()
