"""ChatGPT 계정 연결의 토큰 갱신 (계획 3.15, D-516).

못박는 성질:
1. 만료가 멀면 갱신하지 않는다(제공자에 한 번도 묻지 않는다).
2. 만료가 가까우면 공식 폼으로 갱신하고, 바뀐 갱신 토큰과 **응답이 준** 만료 시각을 묶음과 연결 상태 표에 적는다.
3. 두 프로세스가 동시에 갱신하려 해도 제공자에는 한 번만 묻는다(DB 잠금). 늦은 쪽은 바뀐 토큰을 그대로 쓴다.
4. 갱신 토큰이 거절되면 묶음에서 토큰을 지우고 재로그인 필요를 돌려준다. 그 뒤로는 제공자에 묻지 않는다.
5. 갱신 중 네트워크 오류는 일시 장애이고 가진 토큰을 지우지 않는다.
6. 새 토큰을 저장할 수 없으면 갱신하지 않는다 - 갱신하는 순간 옛 토큰이 무효가 되기 때문이다.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import timedelta
from urllib.parse import parse_qs

import httpx
import pytest

from app.ai.credentials import chatgpt
from app.ai.credentials import state as state_mod
from app.ai.providers import base
from app.core.secret_store import SecretStore

SLOT = "ai.openai.chatgpt"


def _bundle(now, *, access_in: timedelta, refresh_token="rt-1", access_token="at-1") -> dict:
    return {
        "login_id": "login-1", "client_id": "oaiapp_1", "ext_agent_host_id": "urn:uuid:host",
        "email": "owner@example.com", "access_token": access_token, "refresh_token": refresh_token,
        "access_expires_at": (now + access_in).isoformat(),
        "refresh_expires_at": (now + timedelta(days=20)).isoformat(),
    }


def _write(app, bundle: dict) -> None:
    (app.state.settings.secrets_dir / SLOT).write_text(json.dumps(bundle), encoding="utf-8")


def _read(app) -> dict:
    return json.loads((app.state.settings.secrets_dir / SLOT).read_text(encoding="utf-8"))


def _tokens(app, *, store=None) -> chatgpt.ChatGptTokens:
    return chatgpt.ChatGptTokens(
        secrets=app.state.secret_provider, store=store or SecretStore(app.state.secret_provider),
        outbound=app.state.outbound_client, session_factory=app.state.session_factory, clock=app.state.clock,
        settings_cache=app.state.settings_cache, lock_wait_seconds=10,
    )


def _token_calls(fake_http) -> list:
    return [r for r in fake_http.requests if str(r.url).startswith(chatgpt.TOKEN_URL)]


def test_a_fresh_token_is_not_refreshed(app, fake_http, fake_clock):
    _write(app, _bundle(fake_clock.now(), access_in=timedelta(minutes=40)))
    assert _tokens(app).ensure_fresh().ok
    assert _token_calls(fake_http) == []


def test_a_near_expiry_token_is_refreshed_with_the_provider_lifetime(app, fake_http, fake_clock, db):
    now = fake_clock.now()
    _write(app, _bundle(now, access_in=timedelta(minutes=2)))
    fake_http.on(chatgpt.TOKEN_URL, json_body={
        "access_token": "at-2", "refresh_token": "rt-2", "expires_in": 7200, "token_type": "Bearer",
    })
    assert _tokens(app).ensure_fresh().ok
    form = parse_qs(_token_calls(fake_http)[0].content.decode())
    assert form["grant_type"] == ["refresh_token"] and form["refresh_token"] == ["rt-1"]
    assert form["client_id"] == ["oaiapp_1"] and "scope" not in form
    saved = _read(app)
    assert (saved["access_token"], saved["refresh_token"]) == ("at-2", "rt-2")
    assert saved["access_expires_at"] == (now + timedelta(seconds=7200)).isoformat(), "응답의 7200 초를 쓴다"
    assert saved["login_id"] == "login-1", "갱신은 새 로그인이 아니다"
    row = state_mod.credential_row(db, base.PROVIDER_OPENAI, base.AUTH_CHATGPT)
    assert row.access_expires_at == now + timedelta(seconds=7200)
    assert row.expiry_source == "expires_in+fallback"


@pytest.mark.real_db
def test_two_processes_refreshing_at_once_ask_the_provider_once(app, fake_http, fake_clock):
    _write(app, _bundle(fake_clock.now(), access_in=timedelta(minutes=1)))
    counter = {"n": 0}

    def slow_token(request):
        counter["n"] += 1
        time.sleep(0.6)  # 잠금을 쥔 채 오래 걸리는 갱신 - 다른 쪽은 그동안 잠금을 기다린다
        return httpx.Response(200, json={"access_token": f"at-{counter['n'] + 1}", "refresh_token": "rt-new",
                                         "expires_in": 3600}, request=request)

    fake_http.on_handler(chatgpt.TOKEN_URL, slow_token)
    results: list = []
    workers = [threading.Thread(target=lambda: results.append(_tokens(app).ensure_fresh())) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=30)
    assert [r.ok for r in results] == [True, True]
    assert counter["n"] == 1, "같은 갱신 토큰으로 두 번 갱신하면 늦은 쪽이 「이미 쓴 토큰」으로 연결을 잃는다"
    assert _read(app)["refresh_token"] == "rt-new"


def test_a_rejected_refresh_token_clears_the_tokens_and_asks_for_a_new_login(app, fake_http, fake_clock):
    _write(app, _bundle(fake_clock.now(), access_in=timedelta(seconds=30)))
    fake_http.on(chatgpt.TOKEN_URL, status=400, json_body={"error": "refresh_token_reused"})
    tokens = _tokens(app)
    status = tokens.ensure_fresh()
    assert (status.ok, status.kind, status.code) == (False, base.ERROR_REAUTH, "refresh_token_reused")
    saved = _read(app)
    assert "access_token" not in saved and "refresh_token" not in saved
    assert saved["client_id"] == "oaiapp_1" and saved["login_id"] == "login-1"
    before = len(_token_calls(fake_http))
    again = tokens.ensure_fresh()
    assert (again.kind, again.code) == (base.ERROR_REAUTH, "account_disconnected")
    assert len(_token_calls(fake_http)) == before, "끊긴 연결로 제공자에 다시 묻지 않는다"


def test_a_network_error_while_refreshing_keeps_the_tokens(app, fake_http, fake_clock):
    original = _bundle(fake_clock.now(), access_in=timedelta(seconds=30))
    _write(app, original)
    fake_http.on_connect_error(chatgpt.TOKEN_URL)
    status = _tokens(app).ensure_fresh()
    assert (status.ok, status.kind) == (False, base.ERROR_TRANSIENT)
    assert _read(app)["refresh_token"] == original["refresh_token"]


class _UnreadyStore:
    def ready(self):
        return False

    def write(self, *_a, **_k):  # pragma: no cover - 불리면 안 된다
        raise AssertionError("저장할 수 없는데 썼다")


def test_no_refresh_when_new_tokens_could_not_be_stored(app, fake_http, fake_clock):
    _write(app, _bundle(fake_clock.now(), access_in=timedelta(seconds=30)))
    status = _tokens(app, store=_UnreadyStore()).ensure_fresh()
    assert (status.kind, status.code) == (base.ERROR_CONFIG, "secret_store_unavailable")
    assert _token_calls(fake_http) == [], "옛 갱신 토큰을 무효로 만든 뒤 새 토큰을 버리게 된다"
