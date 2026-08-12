"""자동 연동 헬스 스윕(run_all_integration_health_checks) — 워커가 주기적으로 호출.

WF1 감사: 수동 POST /{id}/health만 있어 아무도 안 누르면 last_health_status가 오래된 값에
멈춰 있었다 — 연동 상세가 25일 전 점검 결과를 지금 상태처럼 초록 「정상」으로 보여줬다.
run_all_runner_health_checks(app/runners/service.py)와 같은 이유의 같은 모양 스윕이지만,
기존 단건 함수 run_health_check()를 그대로 재사용한다(판정 기준 복제 없음). 비활성 연동은
건너뛰고, 한 연동의 예외가 스윕 전체를 막지 않는다. Notion 대신 fake outbound(.get)로
HTTP를 대체한다.
"""

import pytest

from app.integrations.schemas import IntegrationConfig
from app.integrations.service import create_integration, run_all_integration_health_checks

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
    cfg = IntegrationConfig(name=name, provider_type="http_service", base_url=base_url, health_url=health_url, enabled=enabled)
    row = create_integration(db, cfg, allowlists=app.state.allowlists, created_by=None)
    db.commit()
    return row


def test_reachable_marks_up_unreachable_down(db, app, fake_clock):
    r1 = _mk(db, app, "i-up", "http://127.0.0.1:8787")
    r2 = _mk(db, app, "i-down", "http://127.0.0.1:8788")
    ob = _FakeOutbound(code_by_url={
        "http://127.0.0.1:8787": 200,
        "http://127.0.0.1:8788": 503,
    })
    summary = run_all_integration_health_checks(db, outbound=ob, now=fake_clock.now())
    assert summary == {"checked": 2, "up": 1, "down": 1}
    assert r1.last_health_status == "up"
    assert r2.last_health_status == "down"
    assert r1.last_health_at == fake_clock.now()


def test_strict_2xx_only_unlike_runner_sweep(db, app, fake_clock):
    # run_health_check()는 러너와 달리 health_url 유무와 무관하게 항상 엄격 2xx만 정상이다
    # (round36 사고 이후의 러너 이중 기준과 갈라져도 문제 없다 — 여기는 함수를 재사용하므로
    # 갈라질 기준 자체가 없다). 404는 down.
    r = _mk(db, app, "i-404", "http://127.0.0.1:8787")
    ob = _FakeOutbound(default=404)
    summary = run_all_integration_health_checks(db, outbound=ob, now=fake_clock.now())
    assert summary == {"checked": 1, "up": 0, "down": 1}
    assert r.last_health_status == "down"


def test_health_url_is_used_when_present(db, app, fake_clock):
    r = _mk(db, app, "i-hu", "http://127.0.0.1:8787", health_url="http://127.0.0.1:8789")
    ob = _FakeOutbound(code_by_url={"http://127.0.0.1:8789": 200})
    summary = run_all_integration_health_checks(db, outbound=ob, now=fake_clock.now())
    assert ob.calls == ["http://127.0.0.1:8789"]  # health_url 우선 호출
    assert summary == {"checked": 1, "up": 1, "down": 0}
    assert r.last_health_status == "up"


def test_disabled_integration_is_skipped(db, app, fake_clock):
    r_on = _mk(db, app, "i-on", "http://127.0.0.1:8787", enabled=True)
    r_off = _mk(db, app, "i-off", "http://127.0.0.1:8788", enabled=False)
    ob = _FakeOutbound(default=200)
    summary = run_all_integration_health_checks(db, outbound=ob, now=fake_clock.now())
    assert summary == {"checked": 1, "up": 1, "down": 0}
    assert ob.calls == ["http://127.0.0.1:8787"]  # 비활성 연동은 호출 안 함
    assert r_off.last_health_status == "unknown"  # 손대지 않음(기본값 유지)
    assert r_on.last_health_status == "up"


def test_sweep_isolates_exceptions(db, app, fake_clock):
    r1 = _mk(db, app, "i-ok", "http://127.0.0.1:8787")
    r2 = _mk(db, app, "i-boom", "http://127.0.0.1:8788")
    ob = _FakeOutbound(code_by_url={"http://127.0.0.1:8787": 200},
                       raise_urls={"http://127.0.0.1:8788"})
    summary = run_all_integration_health_checks(db, outbound=ob, now=fake_clock.now())
    assert summary == {"checked": 2, "up": 1, "down": 1}
    assert r1.last_health_status == "up"
    assert r2.last_health_status == "down"
