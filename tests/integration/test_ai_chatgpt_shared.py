"""ChatGPT 계정 연결은 API 키와 같은 정식 인증 방식이다 (D-566 — 사용자 결정으로 D-559 를 대체), 상태 면은 서버가 준 사실만 그린다 (D-558).

못박는 성질:
1. 모든 설치의 제공자 표에 OpenAI 의 두 방식(API 키 · ChatGPT 계정)이 선다 — API 키가 먼저다. 그 방식을 고르는 저장과 로그인 시작은
   설치 플래그 없이 된다(D-559 의 `AI_CHATGPT_PERSONAL_EVAL` 은 걷었다).
2. 연결한 ChatGPT 계정 하나를 이 설치의 모든 사용자와 시스템(배치) 호출이 함께 쓴다 — 연결한 사람 · 다른 사용자 · 배치 모두 제공자에 닿고
   사용 기록에 남는다. 주인을 적지 않은 옛 묶음도 같다(`owner_user_id` 는 누가 연결했는지의 기록일 뿐이다).
3. 저장된 토큰은 쓴다 — 상태 면의 자격 · 연결 확인 · 도우미 가용성 · 헬스 틱.
4. 상태 면의 사실: 자격이 없으면 제공자 · 인증 방식 줄만 있고 모델 · 최근 성공 줄이 없다. 자격이 있으면 모델 줄이 선다.
   열린 로그인 시도는 「로그인 진행 중」이고 다음 할 일은 「붙여 넣기」다.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.ai import actions as actions_mod
from app.ai import health
from app.ai.models import AiUsageRecord
from tests.fakes.ai import ScriptedAdapter, install_runtime

pytestmark = pytest.mark.integration

SLOT = "ai.openai.chatgpt"


def _bundle(now, *, owner_user_id=None) -> dict:
    bundle = {"login_id": "L1", "client_id": "oaiapp_1", "ext_agent_host_id": "urn:uuid:h", "email": "o@example.com",
              "access_token": "at-1", "refresh_token": "rt-1",
              "access_expires_at": (now + timedelta(hours=1)).isoformat(),
              "refresh_expires_at": (now + timedelta(days=25)).isoformat()}
    if owner_user_id is not None:
        bundle["owner_user_id"] = owner_user_id
    return bundle


def _chatgpt_install(app, *, bundle: dict | None, model: str = "gpt-6.1-sol", enabled: bool = True):
    """설정을 OpenAI · ChatGPT 계정으로 두고 가짜 제공자를 끼운 런타임. 묶음이 있으면 비밀 칸에 쓴다."""
    from app.settings.service import apply_setting

    adapter = ScriptedAdapter(["답입니다."], models=[model])
    runtime = install_runtime(app, adapter, enabled=enabled, model=model)
    path = app.state.settings.secrets_dir / SLOT
    if bundle is not None:
        path.write_text(json.dumps(bundle), encoding="utf-8")
    elif path.exists():
        path.unlink()
    with app.state.session_factory() as db:
        for key, value in {"ai_provider": "openai", "ai_auth_method": "chatgpt"}.items():
            apply_setting(db, app.state.settings_cache, key=key, value=value, updated_by=None, now=app.state.clock.now())
        db.commit()
    return runtime, adapter


def _usage_rows(db) -> int:
    return int(db.execute(select(func.count()).select_from(AiUsageRecord)).scalar_one())


def _overview(client, csrf) -> dict:
    return client.get("/api/admin/ai", headers={"X-CSRF-Token": csrf}).json()


# ── 1 모든 설치에 두 방식 ─────────────────────────────────────────────────────


def test_every_install_offers_both_openai_methods_and_can_pick_and_start_chatgpt(client, login_as, settings):
    assert not hasattr(settings, "ai_chatgpt_personal_eval"), "D-559 의 설치 플래그는 걷었다(D-566)"
    csrf = login_as("system_admin")
    body = _overview(client, csrf)
    (openai,) = [p for p in body["providers"] if p["key"] == "openai"]
    assert [m["key"] for m in openai["auth_methods"]] == ["api_key", "chatgpt"], "API 키가 먼저, ChatGPT 계정이 그 다음이다"
    assert [m["label"] for m in openai["auth_methods"]] == ["API 키", "ChatGPT 계정"], "「개인 평가용」 꼬리표가 남았다"
    assert "chatgpt_allowed" not in body
    chosen = client.put("/api/admin/ai/config", json={"provider": "openai", "auth_method": "chatgpt"},
                        headers={"X-CSRF-Token": csrf})
    assert chosen.status_code == 200, chosen.text
    started = client.post("/api/admin/ai/oauth/openai/start", headers={"X-CSRF-Token": csrf})
    assert started.status_code == 200, started.text


# ── 2 · 3 연결한 계정 하나를 모두가 쓴다 ──────────────────────────────────────


def test_a_connected_chatgpt_account_is_shared_by_every_user_and_by_batch_calls(client, login_as, make_user, app, db,
                                                                                 fake_clock):
    owner = make_user(email="system-admin@goodmit.co.kr", role="system_admin")
    other = make_user(email="colleague@goodmit.co.kr", role="user")
    runtime, adapter = _chatgpt_install(app, bundle=_bundle(fake_clock.now(), owner_user_id=owner.id))
    before = _usage_rows(db)

    mine = runtime.generate(db, action_key=actions_mod.HOME_NARRATIVE, data="오늘", actor=owner)
    theirs = runtime.generate(db, action_key=actions_mod.HOME_NARRATIVE, data="오늘", actor=other)
    system = runtime.generate(db, action_key=actions_mod.WEEKLY_SUMMARY, data="주간", actor=None)
    assert mine.ok and theirs.ok and system.ok, (mine, theirs, system)
    assert len(adapter.calls) == 3, "세 호출 모두 연결한 계정으로 제공자에 닿는다"
    assert _usage_rows(db) == before + 3, "세 호출 모두 사용 기록에 남는다"
    assert runtime.verify(db)["ok"] is True

    # 화면의 판정도 같다 — 연결한 사람도 동료도 쓸 수 있다.
    login_as("system_admin")
    assert client.get("/api/ai/status").json()["assistant"]["reason"] is None
    login_as("user", email="colleague@goodmit.co.kr")
    shown = client.get("/api/ai/status").json()["assistant"]
    assert shown["available"] is True and shown["reason"] is None, shown


def test_a_bundle_without_an_owner_is_used_like_any_other(app, make_user, db, fake_clock):
    admin = make_user(email="system-admin@goodmit.co.kr", role="system_admin")
    runtime, adapter = _chatgpt_install(app, bundle=_bundle(fake_clock.now()))
    result = runtime.generate(db, action_key=actions_mod.HOME_NARRATIVE, data="오늘", actor=admin)
    assert result.ok, result
    assert len(adapter.calls) == 1


def test_stored_tokens_count_as_credentials_and_the_health_tick_keeps_them(client, login_as, app, fake_clock, db):
    csrf = login_as("system_admin")
    now = fake_clock.now()
    runtime, adapter = _chatgpt_install(app, bundle=_bundle(now))
    body = _overview(client, csrf)
    assert body["credentials"]["ready"] is True and body["credentials"]["method"] == "chatgpt"
    assert body["state"]["state"] != "unconfigured"
    assert body["next"] is None or body["next"]["action"] != "api_key", "API 키로 바꾸라고 하지 않는다"
    assert runtime.verify(db)["ok"] is True
    done = health.run_ai_health(runtime, app.state.session_factory, now=now)
    assert done["refreshed"] is True, done


# ── 4 상태 면의 사실 ───────────────────────────────────────────────────────────


def test_facts_follow_the_credentials_and_an_open_login_is_authenticating(client, login_as, app, fake_clock, make_user):
    owner = make_user(email="system-admin@goodmit.co.kr", role="system_admin")
    csrf = login_as("system_admin")
    _chatgpt_install(app, bundle=None)
    body = _overview(client, csrf)
    assert body["credentials"] == {"ready": False, "method": "chatgpt", "account_label": None}
    assert [f["key"] for f in body["facts"]] == ["provider", "auth"]
    assert body["next"]["action"] == "login"
    assert body["login"]["open"] is False

    started = client.post("/api/admin/ai/oauth/openai/start", headers={"X-CSRF-Token": csrf})
    assert started.status_code == 200
    body = _overview(client, csrf)
    assert body["login"]["open"] is True and body["login"]["transaction_id"] == started.json()["transaction_id"]
    assert body["state"]["display"]["key"] == "authenticating"
    assert body["state"]["display"]["label"] == "로그인 진행 중"
    assert body["next"]["action"] == "paste"

    _chatgpt_install(app, bundle=_bundle(fake_clock.now(), owner_user_id=owner.id))
    body = _overview(client, csrf)
    assert body["credentials"]["ready"] is True and body["credentials"]["account_label"]
    keys = [f["key"] for f in body["facts"]]
    assert keys[:3] == ["provider", "auth", "model"]
    assert body["state"]["display"]["key"] == "unverified"
    assert body["next"]["action"] == "verify"
    # 시도 행은 아직 열려 있어도(`login.open`) 자격이 생겼으면 더는 「로그인 진행 중」이 아니다 - 낱말은 자격이 정한다.
    assert body["login"]["open"] is True
