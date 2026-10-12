"""AI 인증 방식의 범위 — 운영 설치는 API 키뿐이고 ChatGPT 계정 연결은 개인 평가 플래그가 켜진 설치의 기능이다 (D-559),
그리고 상태 면은 서버가 준 사실만 그린다 (D-558).

못박는 성질:
1. 플래그가 꺼진 설치(기본)에는 ChatGPT 방식이 제공자 표에 없다. 그 방식을 고르는 저장은 422, 로그인 시작은 409 다.
2. 꺼진 설치에 옛 `chatgpt` 저장값과 토큰 묶음이 남아 있어도 상태는 「미설정」이고 다음 할 일은 「API 키로 연결하세요」다.
   저장된 토큰은 쓰지 않는다 — 연결 확인 · 도우미 · 헬스 틱 모두.
3. 켜진 설치에서는 연결한 사람 본인만 AI 를 쓴다. 다른 사용자 · 시스템 호출은 미설정이고 사용 기록에 남지 않는다. 관리자의
   연결 확인(verify)은 본인 검사를 하지 않는다. 주인을 적지 않은 옛 묶음은 아무의 것도 아니다.
4. 상태 면의 사실: 자격이 없으면 제공자 · 인증 방식 줄만 있고 모델 · 최근 성공 줄이 없다. 자격이 있으면 모델 줄이 선다.
   열린 로그인 시도는 「로그인 진행 중」이고 다음 할 일은 「붙여 넣기」다. 지문이 바뀐 옛 기록의 최근 확인 시각은 보이지 않는다.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.ai import actions as actions_mod
from app.ai import health
from app.ai.credentials import chatgpt
from app.ai.gateway import contract
from app.ai.models import AiUsageRecord
from app.ai.runtime import CHATGPT_DISABLED_TEXT, PERSONAL_ONLY
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


# ── 1 · 2 플래그가 꺼진 설치(운영) ─────────────────────────────────────────────


def test_a_production_install_offers_api_keys_only(client, login_as, settings):
    assert settings.ai_chatgpt_personal_eval is False, "기본값은 꺼짐이다 — 운영 설치의 경로는 API 키다"
    csrf = login_as("system_admin")
    body = _overview(client, csrf)
    (openai,) = [p for p in body["providers"] if p["key"] == "openai"]
    assert [m["key"] for m in openai["auth_methods"]] == ["api_key"], "꺼진 설치에 ChatGPT 방식이 보인다"
    assert body["chatgpt_allowed"] is False
    chosen = client.put("/api/admin/ai/config", json={"provider": "openai", "auth_method": "chatgpt"},
                        headers={"X-CSRF-Token": csrf})
    assert chosen.status_code == 422 and CHATGPT_DISABLED_TEXT in chosen.text
    started = client.post("/api/admin/ai/oauth/openai/start", headers={"X-CSRF-Token": csrf})
    assert started.status_code == 409, "화면에 없는 흐름을 API 로 열 수 있다"


def test_an_old_chatgpt_config_on_a_production_install_is_unconfigured_and_its_tokens_are_not_used(
    client, login_as, app, settings, fake_http, fake_clock, db,
):
    csrf = login_as("system_admin")
    now = fake_clock.now()
    runtime, adapter = _chatgpt_install(app, bundle=_bundle(now))
    body = _overview(client, csrf)
    assert body["state"]["state"] == "unconfigured"
    assert body["state"]["display"]["label"] == "미설정"
    assert body["state"]["display"]["message"] == CHATGPT_DISABLED_TEXT
    assert body["credentials"]["ready"] is False
    assert body["next"] == {"label": CHATGPT_DISABLED_TEXT, "action": "api_key"}
    assert [f["key"] for f in body["facts"]] == ["provider", "auth"], "미설정에 모델 · 최근 성공 줄이 보인다"
    # 저장된 토큰은 쓰지 않는다: 연결 확인도 도우미도 미설정이고, 헬스 틱은 갱신하지 않는다.
    assert runtime.verify(db)["status"] == contract.STATUS_UNCONFIGURED
    assert adapter.calls == []
    fake_http.on(chatgpt.TOKEN_URL, json_body={"access_token": "at-2", "refresh_token": "rt-2", "expires_in": 3600})
    done = health.run_ai_health(runtime, app.state.session_factory, now=now)
    assert done["refreshed"] is None and done["checked"] is None
    assert not [r for r in fake_http.requests if str(r.url).startswith(chatgpt.TOKEN_URL)], "꺼진 설치가 토큰을 갱신했다"
    # 다른 칸(제한 시간)을 고치는 것은 막지 않는다 — 옛 값이 남아 있을 뿐이다.
    assert client.put("/api/admin/ai/config", json={"timeout_seconds": 45}, headers={"X-CSRF-Token": csrf}).status_code == 200


# ── 3 켜진 설치(개인 · 로컬 개발) — 연결한 본인만 ─────────────────────────────


def test_on_a_personal_install_only_the_connector_uses_the_ai(client, login_as, make_user, app, settings, db,
                                                               fake_clock):
    settings.ai_chatgpt_personal_eval = True
    owner = make_user(email="system-admin@goodmit.co.kr", role="system_admin")
    other = make_user(email="colleague@goodmit.co.kr", role="user")
    runtime, adapter = _chatgpt_install(app, bundle=_bundle(fake_clock.now(), owner_user_id=owner.id))
    before = _usage_rows(db)

    mine = runtime.generate(db, action_key=actions_mod.HOME_NARRATIVE, data="오늘", actor=owner)
    assert mine.ok, mine
    theirs = runtime.generate(db, action_key=actions_mod.HOME_NARRATIVE, data="오늘", actor=other)
    assert (theirs.status, theirs.error_code) == (contract.STATUS_UNCONFIGURED, PERSONAL_ONLY)
    system = runtime.generate(db, action_key=actions_mod.WEEKLY_SUMMARY, data="주간", actor=None)
    assert (system.status, system.error_code) == (contract.STATUS_UNCONFIGURED, PERSONAL_ONLY), "배치 호출이 남의 요금제를 쓴다"
    assert len(adapter.calls) == 1, "본인의 호출만 제공자에 닿는다"
    assert _usage_rows(db) == before + 1, "아무것도 시도하지 않은 호출이 사용 기록에 남았다"

    # 관리자의 연결 확인은 본인 검사를 하지 않는다(사람이 아닌 시스템의 점검이다).
    assert runtime.verify(db)["ok"] is True

    # 화면의 판정도 같다 — 본인은 쓸 수 있고 동료는 「연결한 사람 본인만」이다.
    login_as("system_admin")
    assert client.get("/api/ai/status").json()["assistant"]["reason"] is None
    login_as("user", email="colleague@goodmit.co.kr")
    shown = client.get("/api/ai/status").json()["assistant"]
    assert shown["available"] is False and shown["reason"] == "personal_only"
    assert "본인만" in shown["notice"]


def test_a_bundle_without_an_owner_belongs_to_nobody(app, settings, make_user, db, fake_clock):
    settings.ai_chatgpt_personal_eval = True
    admin = make_user(email="system-admin@goodmit.co.kr", role="system_admin")
    runtime, adapter = _chatgpt_install(app, bundle=_bundle(fake_clock.now()))
    result = runtime.generate(db, action_key=actions_mod.HOME_NARRATIVE, data="오늘", actor=admin)
    assert (result.status, result.error_code) == (contract.STATUS_UNCONFIGURED, PERSONAL_ONLY)
    assert adapter.calls == []


def test_a_personal_install_still_offers_the_chatgpt_method_and_an_api_key_install_is_untouched(
    client, login_as, app, settings, fake_clock, make_user,
):
    settings.ai_chatgpt_personal_eval = True
    csrf = login_as("system_admin")
    body = _overview(client, csrf)
    (openai,) = [p for p in body["providers"] if p["key"] == "openai"]
    assert [m["key"] for m in openai["auth_methods"]] == ["api_key", "chatgpt"], "API 키가 먼저다"
    assert body["chatgpt_allowed"] is True
    # API 키 설치(Anthropic)는 플래그와 무관하다 — 모두 쓴다.
    runtime = install_runtime(app, ScriptedAdapter(["답"]))
    other = make_user(email="colleague@goodmit.co.kr", role="user")
    with app.state.session_factory() as db:
        assert runtime.personal_only_for(runtime.config(db), other) is False


# ── 4 상태 면의 사실 ───────────────────────────────────────────────────────────


def test_facts_follow_the_credentials_and_an_open_login_is_authenticating(client, login_as, app, settings, fake_clock,
                                                                           make_user):
    settings.ai_chatgpt_personal_eval = True
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
