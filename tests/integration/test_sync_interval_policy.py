"""주기를 관리 콘솔에서 정한다 (지시 1 · 29).

예전에는 주기가 전부 env 기본값 상수였고, 워커 틱이 **등록 시점에 한 번만** 읽어 상수로
굳혔다. 그래서 두 가지 결함이 함께 있었다.

1. 관리자 화면에 그 값이 아예 없었다 — 바꾸려면 서버 파일을 고치고 워커를 재시작해야 했다.
2. 정책을 바꿔도 **재시작 전까지 반영되지 않았다** — 화면은 "저장했습니다"라고 말하는데
   실제 동작은 옛 값이었다.

## 남은 주기가 하나뿐인 이유

예전에는 문서·티켓·프로젝트 미러 동기화 주기가 여기 함께 있었다. 세 미러가 사라지면서
그 키들도 레지스트리에서 없어졌다 — 돌지 않는 동기화의 주기를 관리자가 고를 수 있게 두면
값을 바꾼 사람이 무언가 달라졌다고 믿는 거짓 스위치가 된다. 지금 이 규약을 지나는 주기는
검색 색인 재구축 하나이고, 규약 자체는 그대로다.

여기서 증명하는 것:
  - 레지스트리가 그 키를 갖고, 검증이 위험한 값을 막는다.
  - 틱이 **매번** 캐시를 다시 읽는다(등록 시점 상수가 아니다).
  - `0` 은 "서버 기본값을 따른다" 센티널이라 env 로 정해 둔 설치가 조용히 안 바뀐다.
"""

from datetime import timedelta

import pytest

from app import worker_main
from app.core.errors import ValidationAppError
from app.settings.registry import REGISTRY

# 이 파일의 시험 둘은 **전용 DB** 가 필요하다(D-190). `worker_main._bootstrap` 이
# `settings.database_url` 로 **자기 엔진**을 만들기 때문이다 — 하네스가 열어 둔 바깥
# 트랜잭션 밖의 커넥션이라, 워커가 커밋한 것은 시험이 끝나도 되감기지 않는다.
#
# 그대로 두면 이 파일이 **공유 DB 를 오염시킨다**: 워커 틱이 관측 상태 행을 커밋하고, 같은
# 프로세스에서 나중에 도는 시험이 그 행을 처음 상태로 기대하다 실패한다. 파일을 혼자 돌리면
# 통과하고 청크로 돌리면 실패하는 모양이라, 원인을 파일 안에서 찾으면 안 보인다.
pytestmark = [pytest.mark.integration, pytest.mark.real_db]

INTERVAL_KEY = "search_index_interval_seconds"


def test_registry_exposes_the_interval():
    spec = REGISTRY[INTERVAL_KEY]
    assert spec.value_type == "int"
    # 기본값 0 = "서버 기본값을 따른다". 실제 숫자를 박아 두면 env 로 주기를 정해 둔
    # 기존 설치가 업그레이드하는 순간 조용히 다른 값으로 바뀐다.
    assert spec.default == 0
    # 틱이 매 회차 값을 다시 읽으므로 재시작이 필요 없다.
    assert spec.restart_required is False


def test_the_removed_mirror_intervals_are_gone_from_the_registry():
    """돌지 않는 동기화의 주기가 관리 콘솔에 남아 있으면 **거짓 스위치**다.

    관리자는 값을 바꾸고 저장 성공을 보지만 아무 동작도 안 바뀐다. 그 거짓말은 다음에
    진짜로 안 도는 것을 조사할 때 시간을 통째로 태운다.
    """
    for key in (
        "notion_docs_sync_interval_seconds",
        "notion_tickets_sync_interval_seconds",
        "notion_projects_sync_interval_seconds",
    ):
        assert key not in REGISTRY, f"사라진 미러의 주기가 관리 콘솔에 남아 있다: {key}"


@pytest.mark.parametrize("bad", [1, 59, 86401, -1, True, "600", 1.5])
def test_registry_rejects_dangerous_intervals(bad):
    spec = REGISTRY[INTERVAL_KEY]
    with pytest.raises(ValidationAppError):
        spec.validate(bad)


@pytest.mark.parametrize("ok", [0, 60, 600, 86400])
def test_registry_accepts_sane_intervals(ok):
    REGISTRY[INTERVAL_KEY].validate(ok)


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

        # 실제 색인 작업까지 갈 필요가 없다 — 여기서 보려는 것은 "몇 초마다 부르는가"다.
        monkeypatch.setattr(
            "app.search.indexer.reindex_all", lambda *a, **k: None, raising=False)

        tick = _tick(worker, "search_index_tick")
        now = fake_clock.now()

        # 첫 회차는 언제나 즉시 돈다(워커 기동 직후 색인이 비어 있지 않게).
        tick(now)
        assert _last_run_at(worker) == now

        # 기본값(0) → 서버 기본값 300초. 60초 뒤에는 아직 안 돈다.
        tick(now + timedelta(seconds=60))
        assert _last_run_at(worker) == now

        # 관리자가 주기를 60초로 줄인다. **재시작하지 않는다.**
        settings_cache._values = dict(settings_cache.current())
        settings_cache._values[INTERVAL_KEY] = 60

        later = now + timedelta(seconds=120)
        tick(later)
        assert _last_run_at(worker) == later, (
            "정책을 바꿨는데 틱이 옛 주기로 돌았다 — 등록 시점 상수를 다시 읽지 않는다")
    finally:
        outbound.close()


def _last_run_at(worker):
    """틱 클로저가 들고 있는 마지막 실행 시각을 꺼낸다."""
    cb = _tick(worker, "search_index_tick")
    for cell in cb.__closure__ or ():
        v = cell.cell_contents
        if isinstance(v, list) and len(v) == 1:
            return v[0]
    raise AssertionError("마지막 실행 시각을 못 찾았다")


def test_zero_means_follow_the_server_default(app, settings, fake_clock, monkeypatch):
    """`0` 은 "안 정함"이다 — env 로 주기를 정해 둔 설치가 조용히 안 바뀐다."""
    settings.search_index_interval_seconds = 999
    session_factory, ctx, settings_cache, outbound = worker_main._bootstrap(settings, fake_clock)
    try:
        worker = worker_main.build_batch_worker(
            session_factory, fake_clock, ctx, settings, settings_cache, outbound)
        monkeypatch.setattr(
            "app.search.indexer.reindex_all", lambda *a, **k: None, raising=False)
        tick = _tick(worker, "search_index_tick")
        now = fake_clock.now()
        tick(now)
        # 레지스트리 기본값 0 이므로 env 의 999초가 그대로 쓰인다 — 998초에는 안 돈다.
        tick(now + timedelta(seconds=998))
        assert _last_run_at(worker) == now
        tick(now + timedelta(seconds=1000))
        assert _last_run_at(worker) == now + timedelta(seconds=1000)
    finally:
        outbound.close()
