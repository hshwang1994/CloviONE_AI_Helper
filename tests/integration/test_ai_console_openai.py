"""AI 설정 API 의 OpenAI — 두 인증 방식, 계정 연결 칸, 프록시 표시, 토큰 수명 기본값 (계획 3.13 · 3.14 · 2.10, D-516).

못박는 성질:
1. OpenAI 는 API 키와 ChatGPT 계정 두 방식을 보이고, 계정 방식에는 키 끝자리를 보이지 않는다(토큰 묶음이다).
2. 계정 연결 칸은 연결했는지와 계정 이름과 만료만 보인다 - 토큰은 없다. 토큰이 지워진 묶음은 「끊김」이다.
3. 계정 연결로 모델 목록을 물으면 묶음의 access token 으로 요금제 목록을 받는다.
4. 토큰 수명 기본값은 시스템 관리자만 바꾸고, 범위 밖 값은 거절된다.
5. 프록시가 걸려 있으면 화면이 `호스트:포트` 로 안다.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from app.ai.providers import openai
from app.core import outbound_proxy

pytestmark = pytest.mark.integration

SLOT = "ai.openai.chatgpt"


def _write_bundle(app, **fields) -> None:
    now = app.state.clock.now()
    bundle = {"login_id": "L1", "client_id": "oaiapp_1", "email": "o@example.com", "access_token": "chatgpt-at",
              "refresh_token": "rt", "access_expires_at": (now + timedelta(hours=1)).isoformat(), **fields}
    (app.state.settings.secrets_dir / SLOT).write_text(json.dumps(bundle), encoding="utf-8")


def test_openai_offers_two_methods_and_hides_the_bundle(client, login_as, app):
    login_as("system_admin")
    _write_bundle(app)
    body = client.get("/api/admin/ai").json()
    provider = next(p for p in body["providers"] if p["key"] == "openai")
    methods = {m["key"]: m for m in provider["auth_methods"]}
    assert set(methods) == {"api_key", "chatgpt"}
    assert methods["chatgpt"]["account"] is True and methods["api_key"]["account"] is False
    assert methods["chatgpt"]["secret_hint"] is None, "토큰 묶음의 끝자리를 보이면 안 된다"
    assert body["chatgpt"]["connected"] is True and body["chatgpt"]["disconnected"] is False
    assert body["chatgpt"]["manage_usage_url"] == "https://chatgpt.com/settings/usage"
    assert "chatgpt-at" not in json.dumps(body)
    assert body["token_settings"] == {
        "ai_openai_access_ttl_fallback_seconds": 3600, "ai_openai_refresh_ttl_fallback_days": 30,
        "ai_token_refresh_lead_seconds": 300,
    }
    assert body["proxy"] is None


def test_a_bundle_without_tokens_reads_as_disconnected(client, login_as, app):
    login_as("system_admin")
    _write_bundle(app, access_token=None, refresh_token=None)
    chatgpt = client.get("/api/admin/ai").json()["chatgpt"]
    assert (chatgpt["connected"], chatgpt["disconnected"]) == (False, True)


def test_chatgpt_model_listing_uses_the_plan_catalog(client, login_as, app, fake_http):
    login_as("system_admin")
    _write_bundle(app)
    fake_http.on(openai.MODELS_URL, json_body={"models": [
        {"slug": "gpt-6.1-sol", "display_name": "GPT-6.1 Sol", "visibility": "list"},
        {"slug": "hidden", "visibility": "hide"},
    ]})
    reply = client.get("/api/admin/ai/models?provider=openai&auth_method=chatgpt")
    assert reply.status_code == 200, reply.text
    # 요금제 목록은 서버 순서의 첫 `visibility=list` 모델이 추천이다(D-539).
    assert reply.json() == {"models": [{"id": "gpt-6.1-sol", "label": "GPT-6.1 Sol", "recommended": True}],
                            "recommended_id": "gpt-6.1-sol"}
    sent = [r for r in fake_http.requests if str(r.url).startswith(openai.MODELS_URL)][0]
    assert sent.headers["Authorization"] == "Bearer chatgpt-at"


def test_token_lifetime_defaults_are_system_admin_only_and_bounded(client, login_as):
    csrf = login_as("admin")
    denied = client.put("/api/admin/settings/ai_token_refresh_lead_seconds", json={"value": 600},
                        headers={"X-CSRF-Token": csrf})
    assert denied.status_code == 403
    client.post("/logout", headers={"X-CSRF-Token": csrf})
    csrf = login_as("system_admin")
    ok = client.put("/api/admin/settings/ai_token_refresh_lead_seconds", json={"value": 600},
                    headers={"X-CSRF-Token": csrf})
    assert ok.status_code == 200, ok.text
    too_small = client.put("/api/admin/settings/ai_openai_refresh_ttl_fallback_days", json={"value": 0},
                           headers={"X-CSRF-Token": csrf})
    assert too_small.status_code == 422


def test_the_screen_knows_when_calls_go_through_a_proxy(client, login_as, app):
    login_as("system_admin")
    app.state.outbound_client._proxy = outbound_proxy.ProxySettings(https="http://user:pw@proxy.corp.example:3128")
    assert client.get("/api/admin/ai").json()["proxy"] == "proxy.corp.example:3128"
