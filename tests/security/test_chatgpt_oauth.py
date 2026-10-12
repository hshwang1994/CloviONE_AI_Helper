"""ChatGPT 계정 연결 흐름의 보안 — 붙여 넣기 로그인 하나 (계획 A3, D-516 · D-540).

qa-contract-change: 연결 도우미와 짝짓기 토큰이 없어졌다(D-540). 짝짓기 토큰의 길이 · 해시 저장 · 한 번 쓰기 · 같은 거절 문장,
도우미 문의 Origin 검사 · 속도 제한 · 파일 내려주기 시험은 그 대상이 사라져 걷었다. 그 자리는 「도우미 문이 다시 생기지 않는다」
(이 파일과 `tests/regression/test_no_connect_helper.py`)와 「시도마다 높은 포트를 무작위로 고른다」가 잰다. state 다섯 번 · 교환
계약 · 응답에 비밀 없음 · 시도의 주인 · 루프백 주소만 받기 · 로그아웃 성질은 그대로 옮겼다.

못박는 성질:
1. 시작 응답은 `flow: "paste"` 와 인가 주소이고, 시도마다 49152 ~ 65535 의 포트를 새로 고른다. 명령 · 도우미 내려받기가 없다.
2. state 가 틀린 끝내기는 실패로 세고, 다섯 번이면 그 시도를 닫는다(맞는 state 도 더는 받지 않는다).
3. 인가 코드 교환은 공식 계약대로다: 이 시도의 포트로 만든 같은 redirect_uri, 서버가 만든 PKCE verifier, client secret
   없음. ID 토큰의 nonce 가 틀리면 믿지 않는다. 요금제 사용 권한을 받지 못하면 연결하지 않는다.
4. 응답 · 감사 · 로그에는 토큰과 인가 코드가 없다 - 계정 이름만 있다.
5. 연결 시도는 시작한 관리자와 그 세션만 본다. AI 설정 권한이 없는 역할은 시작할 수 없다.
6. 붙여 넣은 주소는 루프백 주소와 정해진 경로와 이 시도의 포트만 받는다. 끝난 시도에 같은 주소를 다시 넣어도 코드를 두 번
   쓰지 않는다. 새로 시작하면 앞 시도는 닫힌다. 10분이 지나면 끝낼 수 없다.
7. 쿠키 없는 도우미 문(`/api/connect/*`)과 도우미 파일(`/connect/*`)은 없다.
8. 로그아웃은 제공자에 갱신 토큰 무효화를 요청하고, 결과와 상관없이 이 서버의 토큰을 지운다.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.ai.credentials import chatgpt, oauth

pytestmark = pytest.mark.security


@pytest.fixture(autouse=True)
def _personal_eval(settings):
    """ChatGPT 계정 연결은 개인 평가 플래그가 켜진 설치에만 있다(D-559) - 이 파일은 그 설치를 잰다."""
    settings.ai_chatgpt_personal_eval = True

SLOT = "ai.openai.chatgpt"
ISSUED = "oaiapp_new_client"
EMAIL = "owner@example.com"


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def _fresh_jwks_cache():
    chatgpt._jwks_cache.update(at=0.0, value=None)
    yield
    chatgpt._jwks_cache.update(at=0.0, value=None)


def _jwks(key) -> dict:
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    public.update(kid="k1", use="sig", alg="RS256")
    return {"keys": [public]}


def _id_token(key, *, nonce: str, aud: str = ISSUED) -> str:
    now = int(time.time())
    return jwt.encode({"iss": chatgpt.ISSUER, "aud": aud, "sub": "acct-sub", "email": EMAIL, "iat": now,
                       "exp": now + 600, "nonce": nonce}, key, algorithm="RS256", headers={"kid": "k1"})


def _start(client, csrf) -> dict:
    reply = client.post("/api/admin/ai/oauth/openai/start", headers={"X-CSRF-Token": csrf})
    assert reply.status_code == 200, reply.text
    return reply.json()


def _query(url: str) -> dict:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def _provider(fake_http, key, *, nonce_from, scope="openid profile email offline_access resource.invoke "
                                                     "chatgpt.tokens.use.direct", seen=None, id_nonce=None):
    """토큰 주소와 JWKS 를 흉내 낸다. `seen` 에 받은 교환 폼을 남긴다."""

    def token(request):
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        if seen is not None:
            seen.append(form)
        return httpx.Response(200, json={
            "access_token": "ACCESS-SECRET-VALUE", "refresh_token": "REFRESH-SECRET-VALUE",
            "id_token": _id_token(key, nonce=id_nonce or nonce_from()), "token_type": "Bearer",
            "expires_in": 3600, "scope": scope,
        }, request=request)

    fake_http.on_handler(chatgpt.TOKEN_URL, token)
    fake_http.on(chatgpt.JWKS_URL, json_body=_jwks(key))


def _paste(client, csrf, tx, url):
    return client.post(f"/api/admin/ai/oauth/openai/transactions/{tx}/complete",
                       json={"callback_url": url}, headers={"X-CSRF-Token": csrf})


def _callback(started, *, state=None, code="AUTH-CODE-1", client_id=ISSUED, port=None):
    query = _query(started["authorize_url"])
    redirect = query["redirect_uri"] if port is None else f"http://127.0.0.1:{port}/auth/callback"
    return (f"{redirect}?code={code}&state={state or query['state']}&client_id={client_id}"
            "&scope=chatgpt.tokens.use.direct")


# ── 1: 시작 ───────────────────────────────────────────────────────────────────


def test_start_is_a_paste_flow_on_a_fresh_high_port_each_time(client, login_as):
    csrf = login_as("system_admin")
    first, second = _start(client, csrf), _start(client, csrf)
    for started in (first, second):
        assert started["flow"] == "paste" and started["phase"] == "browser"
        assert not {"commands", "downloads", "server_url", "fingerprint"} & set(started), "도우미 흔적이 남았다"
        redirect = urlsplit(_query(started["authorize_url"])["redirect_uri"])
        assert (redirect.scheme, redirect.hostname, redirect.path) == ("http", "127.0.0.1", "/auth/callback")
        assert oauth.PORT_MIN <= redirect.port <= oauth.PORT_MAX
        assert started["redirect_uri"] == _query(started["authorize_url"])["redirect_uri"]
    ports = {urlsplit(_query(s["authorize_url"])["redirect_uri"]).port for s in (first, second)}
    states = {_query(s["authorize_url"])["state"] for s in (first, second)}
    assert len(states) == 2, "시도마다 state 가 새로 생긴다"
    # 포트는 무작위라 두 번이 겹칠 수는 있다 - 범위와 분포는 아래 시험이 잰다.
    assert all(oauth.PORT_MIN <= port <= oauth.PORT_MAX for port in ports)


def test_ports_are_drawn_from_the_whole_dynamic_range():
    drawn = {oauth.pick_port() for _ in range(400)}
    assert all(oauth.PORT_MIN <= port <= oauth.PORT_MAX for port in drawn)
    assert len(drawn) > 300, "같은 포트가 너무 자주 나온다 - 무작위가 아니다"


def test_starting_again_closes_the_previous_attempt(client, login_as, fake_http, signing_key):
    csrf = login_as("system_admin")
    old = _start(client, csrf)
    _start(client, csrf)
    _provider(fake_http, signing_key, nonce_from=lambda: _query(old["authorize_url"])["nonce"])
    late = _paste(client, csrf, old["transaction_id"], _callback(old))
    assert late.status_code == 409
    assert "새 연결" in late.json()["error"]["message"]
    assert not [r for r in fake_http.requests if str(r.url).startswith(chatgpt.TOKEN_URL)]


# ── 2: state ──────────────────────────────────────────────────────────────────


def test_state_mismatches_count_and_five_close_the_attempt(client, login_as, fake_http, signing_key):
    csrf = login_as("system_admin")
    started = _start(client, csrf)
    tx = started["transaction_id"]
    _provider(fake_http, signing_key, nonce_from=lambda: _query(started["authorize_url"])["nonce"])
    for _ in range(5):
        assert _paste(client, csrf, tx, _callback(started, state="forged")).status_code == 409
    closed = _paste(client, csrf, tx, _callback(started))
    assert closed.status_code == 409, "다섯 번 틀린 뒤에는 맞는 state 도 받지 않는다"
    assert not [r for r in fake_http.requests if str(r.url).startswith(chatgpt.TOKEN_URL)]


# ── 3 · 4: 교환과 응답 ────────────────────────────────────────────────────────


def test_the_code_exchange_follows_the_contract_and_leaks_nothing(app, client, login_as, fake_http, signing_key,
                                                                   db, caplog):
    caplog.set_level(logging.DEBUG)
    csrf = login_as("system_admin")
    started = _start(client, csrf)
    query = _query(started["authorize_url"])
    assert query["client_id"] == chatgpt.DYNAMIC_CLIENT_ID and query["agent_name_hint"] == "ClovirAssist"
    assert query["ext_agent_host_id"].startswith("urn:uuid:")
    seen: list = []
    _provider(fake_http, signing_key, nonce_from=lambda: query["nonce"], seen=seen)
    done = _paste(client, csrf, started["transaction_id"], _callback(started))
    assert done.status_code == 200, done.text
    assert done.json()["ok"] is True and done.json()["account_label"] == EMAIL

    form = seen[0]
    assert form["grant_type"] == "authorization_code" and form["code"] == "AUTH-CODE-1"
    assert form["client_id"] == ISSUED and form["redirect_uri"] == query["redirect_uri"]
    assert "client_secret" not in form
    digest = hashlib.sha256(form["code_verifier"].encode("ascii")).digest()
    assert base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == query["code_challenge"]

    saved = json.loads((app.state.settings.secrets_dir / SLOT).read_text(encoding="utf-8"))
    assert saved["access_token"] == "ACCESS-SECRET-VALUE" and saved["client_id"] == ISSUED
    assert saved["ext_agent_host_id"] == query["ext_agent_host_id"]
    polled = client.get(f"/api/admin/ai/oauth/openai/transactions/{started['transaction_id']}")
    assert polled.json()["phase"] == "done" and polled.json()["account_label"] == EMAIL
    overview = client.get("/api/admin/ai").json()
    assert overview["chatgpt"]["connected"] is True and overview["chatgpt"]["account_label"] == EMAIL

    everything = done.text + polled.text + json.dumps(overview) + caplog.text
    audits = db.execute(text("SELECT coalesce(after_json::text, '') FROM audit_logs WHERE action LIKE 'ai.oauth.%'"))
    everything += " ".join(value for (value,) in audits)
    for secret in ("ACCESS-SECRET-VALUE", "REFRESH-SECRET-VALUE", "AUTH-CODE-1", form["code_verifier"]):
        assert secret not in everything, "응답, 감사, 로그에 토큰이나 코드가 새면 안 된다"

    again = _paste(client, csrf, started["transaction_id"], _callback(started))
    assert again.status_code == 409 and len(seen) == 1, "끝난 시도에 같은 주소를 넣어 코드를 두 번 썼다"


def test_a_wrong_nonce_or_missing_plan_scope_does_not_connect(app, client, login_as, fake_http, signing_key):
    csrf = login_as("system_admin")
    for kwargs, reason in (({"id_nonce": "someone-elses-nonce"}, "id_token_invalid"),
                           ({"scope": "openid profile email offline_access"}, "plan_scope_missing")):
        started = _start(client, csrf)
        query = _query(started["authorize_url"])
        _provider(fake_http, signing_key, nonce_from=lambda q=query: q["nonce"], **kwargs)
        failed = _paste(client, csrf, started["transaction_id"], _callback(started))
        assert failed.status_code == 409, failed.text
        polled = client.get(f"/api/admin/ai/oauth/openai/transactions/{started['transaction_id']}").json()
        assert (polled["phase"], polled["error_code"]) == ("failed", reason)
    assert not (app.state.settings.secrets_dir / SLOT).exists()


# ── 5: 누가 볼 수 있는가 ──────────────────────────────────────────────────────


def test_only_system_admins_can_start(client, login_as):
    csrf = login_as("admin")
    assert client.post("/api/admin/ai/oauth/openai/start", headers={"X-CSRF-Token": csrf}).status_code == 403


def test_another_admin_or_another_session_cannot_poll_or_complete(app, client, login_as, make_user):
    started = _start(client, login_as("system_admin"))
    path = f"/api/admin/ai/oauth/openai/transactions/{started['transaction_id']}"
    assert client.get(path).status_code == 200
    with TestClient(app, base_url="https://testserver", raise_server_exceptions=False) as other:
        make_user(email="other-sa@goodmit.co.kr", role="system_admin")
        login = other.post("/login", json={"email": "other-sa@goodmit.co.kr", "password": "Str0ng-Passw0rd!"})
        assert login.status_code == 200
        assert other.get(path).status_code == 404
        csrf = login.json().get("csrf_token") or other.cookies.get("csrf_token") or ""
        refused = other.post(path + "/complete", json={"callback_url": _callback(started)},
                             headers={"X-CSRF-Token": csrf})
        assert refused.status_code in (403, 404), "남의 시도를 끝낼 수 있다"
    with TestClient(app, base_url="https://testserver", raise_server_exceptions=False) as same_person:
        assert same_person.post("/login", json={"email": "system-admin@goodmit.co.kr",
                                                 "password": "Str0ng-Passw0rd!"}).status_code == 200
        assert same_person.get(path).status_code == 404, "같은 사람이라도 다른 세션은 이 시도를 모른다"


# ── 6: 붙여 넣은 주소 ─────────────────────────────────────────────────────────


def test_only_this_attempts_loopback_callback_is_accepted(client, login_as, fake_http, signing_key):
    csrf = login_as("system_admin")
    started = _start(client, csrf)
    tx = started["transaction_id"]
    port = urlsplit(started["redirect_uri"]).port
    other_port = oauth.PORT_MIN if port != oauth.PORT_MIN else oauth.PORT_MAX
    _provider(fake_http, signing_key, nonce_from=lambda: _query(started["authorize_url"])["nonce"])
    tail = _callback(started).split("?", 1)[1]
    for bad in (f"http://localhost:{port}/auth/callback", f"http://127.0.0.1:{port}/callback",
                f"http://127.0.0.1:{other_port}/auth/callback", f"https://127.0.0.1:{port}/auth/callback",
                f"http://evil.example:{port}/auth/callback"):
        refused = _paste(client, csrf, tx, bad + "?" + tail)
        assert refused.status_code == 409, bad
    done = _paste(client, csrf, tx, _callback(started))
    assert done.status_code == 200 and done.json()["account_label"] == EMAIL


def test_an_expired_attempt_cannot_be_completed(client, login_as, fake_http, signing_key, fake_clock):
    csrf = login_as("system_admin")
    started = _start(client, csrf)
    _provider(fake_http, signing_key, nonce_from=lambda: _query(started["authorize_url"])["nonce"])
    fake_clock.advance(11 * 60)
    late = _paste(client, csrf, started["transaction_id"], _callback(started))
    assert late.status_code == 409 and "시간이 지났" in late.json()["error"]["message"]


# ── 7: 도우미 문은 없다 ───────────────────────────────────────────────────────


def test_the_helper_door_and_files_are_gone(client, login_as):
    login_as("system_admin")
    for path in ("/api/connect/openai/begin", "/api/connect/openai/complete"):
        assert client.post(path, json={"pairing_token": "x" * 43, "port": 50000}).status_code in (404, 405), path
    for path in ("/connect/clovirassist-connect.ps1", "/connect/clovirassist-connect.py"):
        assert client.get(path).status_code == 404, path


# ── 8: 로그아웃 ───────────────────────────────────────────────────────────────


def test_logout_revokes_then_forgets_even_if_revocation_fails(app, client, login_as, fake_http):
    csrf = login_as("system_admin")
    secret = app.state.settings.secrets_dir / SLOT
    secret.write_text(json.dumps({"login_id": "L", "client_id": ISSUED, "access_token": "a", "refresh_token": "r"}),
                      encoding="utf-8")
    fake_http.on(chatgpt.REVOKE_URL, status=200, text="")
    done = client.post("/api/admin/ai/oauth/openai/logout", headers={"X-CSRF-Token": csrf}).json()
    assert done["revoked"] is True and not secret.exists()
    revoke = [r for r in fake_http.requests if str(r.url).startswith(chatgpt.REVOKE_URL)][0]
    assert parse_qs(revoke.content.decode())["token"] == ["r"]

    secret.write_text(json.dumps({"login_id": "L2", "client_id": ISSUED, "access_token": "a", "refresh_token": "r"}),
                      encoding="utf-8")
    fake_http.on_connect_error(chatgpt.REVOKE_URL)
    failed = client.post("/api/admin/ai/oauth/openai/logout", headers={"X-CSRF-Token": csrf}).json()
    assert failed["revoked"] is False and not secret.exists()
    assert "ChatGPT 설정" in failed["message"], "무효화를 확인하지 못했으면 사람에게 끊을 곳을 알려 준다"
