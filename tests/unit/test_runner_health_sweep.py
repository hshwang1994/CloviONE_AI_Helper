"""자동 러너 헬스 스윕(run_all_runner_health_checks) — 워커가 주기적으로 호출.

거짓 'down' 방지 규칙을 검증한다: 비활성 러너는 건너뛰고, 전용 health_url 이 없으면 도달 가능성만
본다(404 등 4xx 응답=프로세스 살아있음=up), 연결오류/타임아웃만 down. 한 러너의 예외가 스윕을
막지 않는다. Notion 대신 fake outbound(.get)로 HTTP 를 대체한다.
"""

import pytest

from app.runners.schemas import RunnerConfig
from app.runners.service import create_runner, run_all_runner_health_checks

pytestmark = pytest.mark.unit


class _Resp:
    def __init__(self, code):
        self.status_code = code


class _FakeOutbound:
    def __init__(self, code_by_url=None, raise_urls=None, default=200):
        self.code_by_url = code_by_url or {}
        self.raise_urls = set(raise_urls or [])
        self.default = default
        self.calls = []

    def get(self, url, **kw):
        self.calls.append(url)
        if url in self.raise_urls:
            raise RuntimeError("boom")
        return _Resp(self.code_by_url.get(url, self.default))


def _mk(db, app, name, base_url, *, enabled=True, health_url=None):
    cfg = RunnerConfig(name=name, base_url=base_url, health_url=health_url, enabled=enabled)
    row = create_runner(db, cfg, allowlists=app.state.allowlists, created_by=None)
    row.enabled = enabled  # create_runner 는 항상 비활성으로 만든다 — 테스트 의도대로 맞춘다.
    db.commit()
    return row


def test_reachable_marks_up_unreachable_down(db, app, fake_clock):
    # health_url 없음: 200→up, 503(5xx)→down.
    r1 = _mk(db, app, "r-up", "http://127.0.0.1:8787")
    r2 = _mk(db, app, "r-5xx", "http://127.0.0.1:8788")
    ob = _FakeOutbound(code_by_url={
        "http://127.0.0.1:8787": 200,
        "http://127.0.0.1:8788": 503,
    })
    summary = run_all_runner_health_checks(db, outbound=ob, now=fake_clock.now())
    assert summary == {"checked": 2, "up": 1, "down": 1}
    assert r1.last_health_status == "up"
    assert r2.last_health_status == "down"
    assert r1.last_health_at == fake_clock.now()


def test_404_without_health_url_is_up(db, app, fake_clock):
    # 인증된 POST 만 받는 러너는 GET/ 에 404 를 준다 — 프로세스는 살아있으므로 '도달 가능=up'.
    r = _mk(db, app, "r-404", "http://127.0.0.1:8787")
    ob = _FakeOutbound(default=404)
    summary = run_all_runner_health_checks(db, outbound=ob, now=fake_clock.now())
    assert summary == {"checked": 1, "up": 1, "down": 0}
    assert r.last_health_status == "up"


def test_health_url_uses_strict_2xx(db, app, fake_clock):
    # 전용 health_url 이 있으면 엄격 기준(2xx/3xx) — 404 는 down.
    r = _mk(db, app, "r-hu", "http://127.0.0.1:8787", health_url="http://127.0.0.1:8789")
    ob = _FakeOutbound(code_by_url={"http://127.0.0.1:8789": 404})
    summary = run_all_runner_health_checks(db, outbound=ob, now=fake_clock.now())
    assert ob.calls == ["http://127.0.0.1:8789"]  # health_url 우선 호출
    assert summary == {"checked": 1, "up": 0, "down": 1}
    assert r.last_health_status == "down"


def test_disabled_runner_is_skipped(db, app, fake_clock):
    r_on = _mk(db, app, "r-on", "http://127.0.0.1:8787", enabled=True)
    r_off = _mk(db, app, "r-off", "http://127.0.0.1:8788", enabled=False)
    ob = _FakeOutbound(default=200)
    summary = run_all_runner_health_checks(db, outbound=ob, now=fake_clock.now())
    assert summary == {"checked": 1, "up": 1, "down": 0}
    assert ob.calls == ["http://127.0.0.1:8787"]  # 비활성 러너는 호출 안 함
    assert r_off.last_health_status == "unknown"  # 손대지 않음(기본값 유지)
    assert r_on.last_health_status == "up"


def test_sweep_isolates_exceptions(db, app, fake_clock):
    r1 = _mk(db, app, "r-ok", "http://127.0.0.1:8787")
    r2 = _mk(db, app, "r-boom", "http://127.0.0.1:8788")
    ob = _FakeOutbound(code_by_url={"http://127.0.0.1:8787": 200},
                       raise_urls={"http://127.0.0.1:8788"})
    summary = run_all_runner_health_checks(db, outbound=ob, now=fake_clock.now())
    assert summary == {"checked": 2, "up": 1, "down": 1}
    assert r1.last_health_status == "up"
    assert r2.last_health_status == "down"
