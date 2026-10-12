"""AI 연결 주기 확인 — 배치 워커의 15분 틱 (계획 3.15, D-516 · D-539).

qa-contract-change: 「일시 장애는 가벼운 확인(모델 목록)이 답하면 정상으로 돌아온다」를 뒤집었다(D-539). 정상은 같은 설정
지문으로 실제 생성이 성공한 뒤에만 서고, 모델 목록은 생성 권한 · 모델 이름을 재지 않는다 — 목록은 되는데 생성은 안 되는
모델에서 거짓 「정상」이 섰다. 이제 그 시험은 「목록이 답해도 일시 장애 그대로」를 잰다. 연결 시도 정리 시험은 0045 가 짝짓기
토큰 칸을 걷어 그 칸 없이 시도를 만든다.

못박는 성질:
1. 계정 연결의 access token 이 30분 안에 끝나면 틱이 미리 갱신한다.
2. 갱신 토큰이 5일 안에 끝나면 관리자에게 한 번 알린다. 새 갱신 토큰을 받기 전에는 다시 알리지 않는다.
3. 가벼운 확인(모델 목록)은 상태를 올리지 않는다 - 일시 장애는 실제 생성이 성공할 때만 정상으로 돌아온다. 키가 거절되면
   막힌 상태가 되고 관리자가 안다.
4. 일시 장애가 30분 넘게 이어지면 관리자에게 한 번 알린다.
5. 하루 지난 계정 연결 시도는 지운다. 열린 채 만료된 시도는 닫는다.
6. 틱은 주기를 지킨다 - 워커 루프가 도는 만큼 제공자에 묻지 않는다.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.ai import health
from app.ai.credentials import chatgpt
from app.ai.credentials import state as state_mod
from app.ai.providers import base, openai
from app.ai.runtime import AiRuntime
from app.notifications.models import Notification
from tests.fakes.ai import FreeLock, ScriptedAdapter, configure_ai

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _personal_eval(settings):
    """ChatGPT 계정 연결은 개인 평가 플래그가 켜진 설치에만 있다(D-559) - 이 파일은 그 설치를 잰다."""
    settings.ai_chatgpt_personal_eval = True


class CheckAdapter(ScriptedAdapter):
    """모델 목록 답을 시험이 정한다."""

    def __init__(self, listing: base.ModelList):
        super().__init__()
        self.listing = listing
        self.checks = 0

    def list_models(self, *, timeout):
        self.checks += 1
        return self.listing


def _runtime(app, adapter=None) -> AiRuntime:
    state = app.state
    return AiRuntime(
        settings=state.settings, outbound=state.outbound_client, secrets=state.secret_provider,
        session_factory=state.session_factory, settings_cache=state.settings_cache, clock=state.clock,
        adapter_factory=(lambda provider, auth_method: adapter) if adapter is not None else None,
        lock_factory=lambda config: FreeLock(),
    )


def _configure_chatgpt(app, bundle: dict) -> None:
    from app.settings.service import apply_setting

    (app.state.settings.secrets_dir / "ai.openai.chatgpt").write_text(json.dumps(bundle), encoding="utf-8")
    with app.state.session_factory() as db:
        for key, value in {"ai_provider": "openai", "ai_auth_method": "chatgpt", "ai_model": "gpt-6.1-sol",
                           "ai_generation_enabled": True}.items():
            apply_setting(db, app.state.settings_cache, key=key, value=value, updated_by=None, now=app.state.clock.now())
        db.commit()


def _bundle(now, *, access_in: timedelta) -> dict:
    return {"login_id": "L1", "client_id": "oaiapp_1", "ext_agent_host_id": "urn:uuid:h", "email": "o@example.com",
            "access_token": "at-1", "refresh_token": "rt-1", "access_expires_at": (now + access_in).isoformat(),
            "refresh_expires_at": (now + timedelta(days=25)).isoformat()}


def _ai_notices(db) -> int:
    return int(db.execute(select(func.count()).select_from(Notification)
                          .where(Notification.type == "ai_provider_state")).scalar_one())


def _state(app, runtime) -> str:
    with app.state.session_factory() as db:
        return runtime.status(db)["state"]


def test_a_chatgpt_token_ending_within_half_an_hour_is_refreshed_ahead(app, fake_http, fake_clock):
    now = fake_clock.now()
    _configure_chatgpt(app, _bundle(now, access_in=timedelta(minutes=20)))
    fake_http.on(chatgpt.TOKEN_URL, json_body={"access_token": "at-2", "refresh_token": "rt-2", "expires_in": 3600})
    fake_http.on(openai.MODELS_URL, json_body={"models": [{"slug": "gpt-6.1-sol", "visibility": "list"}]})
    done = health.run_ai_health(_runtime(app), app.state.session_factory, now=now)
    assert done["refreshed"] is True
    saved = json.loads((app.state.settings.secrets_dir / "ai.openai.chatgpt").read_text(encoding="utf-8"))
    assert saved["access_token"] == "at-2", "사람의 요청이 갱신을 기다리지 않게 틱이 먼저 갱신한다"
    assert done["checked"] is True
    assert _state(app, _runtime(app)) == state_mod.STATE_UNVERIFIED, "모델 목록만으로 정상이라 적지 않는다"


def test_an_ending_refresh_token_is_announced_once_per_refresh_token(app, db, fake_http, fake_clock, make_user):
    make_user(email="sa@goodmit.co.kr", role="system_admin")
    now = fake_clock.now()
    _configure_chatgpt(app, _bundle(now, access_in=timedelta(hours=2)))
    fake_http.on(openai.MODELS_URL, json_body={"models": []})
    with app.state.session_factory() as s:
        state_mod.update_account(s, base.PROVIDER_OPENAI, base.AUTH_CHATGPT, now=now,
                                 refresh_expires_at=now + timedelta(days=3),
                                 refresh_obtained_at=now - timedelta(days=27))
        s.commit()
    runtime = _runtime(app)
    assert health.run_ai_health(runtime, app.state.session_factory, now=now)["warned"] is True
    first = _ai_notices(db)
    assert first >= 1
    assert health.run_ai_health(runtime, app.state.session_factory, now=now + timedelta(minutes=15))["warned"] is False
    assert _ai_notices(db) == first
    with app.state.session_factory() as s:
        state_mod.update_account(s, base.PROVIDER_OPENAI, base.AUTH_CHATGPT, now=now,
                                 refresh_obtained_at=now + timedelta(minutes=20))
        s.commit()
    assert health.run_ai_health(runtime, app.state.session_factory, now=now + timedelta(minutes=30))["warned"] is True


def test_a_light_check_does_not_lift_degraded_to_ok(app, fake_clock):
    configure_ai(app)
    adapter = CheckAdapter(base.ModelList(ok=True, models=({"id": "m", "label": "m"},)))
    runtime = _runtime(app, adapter)
    with app.state.session_factory() as db:
        config = runtime.config(db)
    runtime.record(config, result=base.ERROR_TRANSIENT, code="timeout", now=fake_clock.now())
    assert _state(app, runtime) == state_mod.STATE_DEGRADED
    health.run_ai_health(runtime, app.state.session_factory, now=fake_clock.now())
    assert adapter.checks == 1
    assert _state(app, runtime) == state_mod.STATE_DEGRADED, "모델 목록만으로 정상을 지어냈다"
    # 실제 생성의 성공만이 정상으로 되돌린다(사람의 호출이나 연결 확인).
    runtime.record(config, result=state_mod.RESULT_OK, code=None, now=fake_clock.now())
    assert _state(app, runtime) == state_mod.STATE_OK


def test_a_rejected_key_found_by_the_check_blocks_and_tells_admins(app, db, fake_clock, make_user):
    make_user(email="sa2@goodmit.co.kr", role="system_admin")
    configure_ai(app)
    adapter = CheckAdapter(base.ModelList(ok=False, error_kind=base.ERROR_AUTH, error_code="http_401"))
    runtime = _runtime(app, adapter)
    health.run_ai_health(runtime, app.state.session_factory, now=fake_clock.now())
    assert _state(app, runtime) == state_mod.STATE_ERROR
    assert _ai_notices(db) >= 1


def test_half_an_hour_of_degraded_is_announced_once(app, db, fake_clock, make_user):
    make_user(email="sa3@goodmit.co.kr", role="system_admin")
    configure_ai(app)
    adapter = CheckAdapter(base.ModelList(ok=False, error_kind=base.ERROR_TRANSIENT, error_code="http_503"))
    runtime = _runtime(app, adapter)
    with app.state.session_factory() as s:
        config = runtime.config(s)
    start = fake_clock.now()
    runtime.record(config, result=base.ERROR_TRANSIENT, code="timeout", now=start)
    assert _ai_notices(db) == 0, "짧은 흔들림은 알리지 않는다"
    health.run_ai_health(runtime, app.state.session_factory, now=start + timedelta(minutes=31))
    once = _ai_notices(db)
    assert once >= 1
    health.run_ai_health(runtime, app.state.session_factory, now=start + timedelta(minutes=46))
    assert _ai_notices(db) == once


def test_old_connection_attempts_are_closed_and_then_removed(app, db, fake_clock, make_user):
    from app.ai.models import AiOAuthTransaction

    admin = make_user(email="sa4@goodmit.co.kr", role="system_admin")
    now = fake_clock.now()

    def attempt(ident, expires_at, phase="browser"):
        db.add(AiOAuthTransaction(
            id=ident, provider="openai", state=ident + "-s", redirect_port=50000,
            nonce=ident + "-n", admin_user_id=admin.id, phase=phase, failures=0, created_at=now, updated_at=now,
            expires_at=expires_at))

    attempt("old", now - timedelta(days=2))
    attempt("stale", now - timedelta(hours=1))
    db.commit()
    done = health.run_ai_health(_runtime(app), app.state.session_factory, now=now)
    assert done["cleaned"] == 1
    db.expire_all()
    assert db.get(AiOAuthTransaction, "old") is None
    stale = db.get(AiOAuthTransaction, "stale")
    assert (stale.phase, stale.error_code) == ("failed", "expired")


def test_the_tick_keeps_its_interval(monkeypatch, fake_clock):
    calls: list = []
    monkeypatch.setattr(health, "run_ai_health", lambda runtime, factory, now: calls.append(now))

    class Worker:
        tick_callbacks: list = []

    worker = Worker()
    tick = health.register_ai_health_tick(worker, session_factory=None, runtime=None, interval=900)
    start = fake_clock.now()
    for seconds in (0, 60, 899, 900, 901):
        tick(start + timedelta(seconds=seconds))
    assert calls == [start, start + timedelta(seconds=900)]
    assert worker.tick_callbacks == [tick]
