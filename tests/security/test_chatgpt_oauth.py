"""ChatGPT 계정 연결 흐름의 보안 (계획 3.14, D-516).

못박는 성질:
1. 짝짓기 토큰은 256비트 무작위 값이고 서버에는 해시만 있다. 원문은 시작 응답에만 실리고 DB, 감사, 로그 어디에도 없다.
2. 짝짓기 토큰은 한 번만 쓴다. 틀린 토큰, 다시 쓴 토큰, 만료된 토큰은 같은 한 문장으로 거절된다.
3. state 가 틀린 끝내기는 실패로 세고, 다섯 번이면 그 시도를 닫는다.
4. 인가 코드 교환은 공식 계약대로다: 도우미가 고른 포트의 같은 redirect_uri, 서버가 만든 PKCE verifier, client secret
   없음. ID 토큰의 nonce 가 틀리면 믿지 않는다. 요금제 사용 권한을 받지 못하면 연결하지 않는다.
5. 응답에는 토큰과 인가 코드가 없다 - 계정 이름만 있다.
6. 연결 시도는 시작한 관리자와 그 세션만 본다. AI 설정 권한이 없는 역할은 시작할 수 없다.
7. 대체 경로는 루프백 주소와 정해진 경로와 이 시도의 포트만 받는다.
8. 도우미의 문은 다른 사이트에서 온 브라우저 요청을 받지 않고, 한 IP 의 요청 폭주를 막는다.
9. 로그아웃은 제공자에 갱신 토큰 무효화를 요청하고, 결과와 상관없이 이 서버의 토큰을 지운다.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.ai.credentials import chatgpt

pytestmark = pytest.mark.security

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


def _start(client, csrf) -> tuple[dict, str]:
    reply = client.post("/api/admin/ai/oauth/openai/start", headers={"X-CSRF-Token": csrf})
    assert reply.status_code == 200, reply.text
    body = reply.json()
    token = re.search(r"--token (\S+)", body["commands"]["unix"]).group(1)
    return body, token


def _helper(app) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _begin(helper, token, port=1460):
    return helper.post("/api/connect/openai/begin", json={"pairing_token": token, "port": port})


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


def _complete(helper, token, tx, *, state, code="AUTH-CODE-1", client_id=ISSUED):
    return helper.post("/api/connect/openai/complete", json={
        "pairing_token": token, "transaction_id": tx,
        "callback": {"code": code, "state": state, "client_id": client_id,
                     "scope": "openid chatgpt.tokens.use.direct"},
    })


# ── 1 · 2: 짝짓기 토큰 ────────────────────────────────────────────────────────


def test_the_pairing_token_is_long_random_and_stored_only_as_a_hash(client, login_as, db, caplog):
    caplog.set_level(logging.DEBUG)
    started, token = _start(client, login_as("system_admin"))
    assert len(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))) >= 32, "256비트보다 짧다"
    row = db.execute(text("SELECT * FROM ai_oauth_transactions WHERE id = :id"),
                     {"id": started["transaction_id"]}).mappings().one()
    assert row["pairing_token_hash"] == hashlib.sha256(token.encode()).hexdigest()
    assert token not in json.dumps({k: str(v) for k, v in row.items()})
    audits = db.execute(text("SELECT coalesce(after_json::text, '') FROM audit_logs WHERE action = 'ai.oauth.start'"))
    assert all(token not in value for (value,) in audits)
    assert token not in caplog.text


def test_wrong_reused_and_expired_tokens_are_refused_alike(app, client, login_as, fake_clock):
    csrf = login_as("system_admin")
    _started, token = _start(client, csrf)
    helper = _helper(app)
    wrong = _begin(helper, "x" * 43)
    assert wrong.status_code == 403
    assert _begin(helper, token).status_code == 200
    reused = _begin(helper, token)
    assert reused.status_code == 403
    assert reused.json()["error"]["message"] == wrong.json()["error"]["message"], "까닭을 자세히 말하지 않는다"
    _second, fresh = _start(client, csrf)
    fake_clock.advance(11 * 60)
    assert _begin(helper, fresh).status_code == 403, "10분이 지난 토큰"


def test_starting_again_closes_the_previous_attempt(app, client, login_as):
    csrf = login_as("system_admin")
    _first, old = _start(client, csrf)
    _start(client, csrf)
    assert _begin(_helper(app), old).status_code == 403


# ── 3: state ──────────────────────────────────────────────────────────────────


def test_state_mismatches_count_and_five_close_the_attempt(app, client, login_as, fake_http, signing_key):
    started, token = _start(client, login_as("system_admin"))
    helper = _helper(app)
    begun = _begin(helper, token).json()
    real_state = _query(begun["authorize_url"])["state"]
    _provider(fake_http, signing_key, nonce_from=lambda: _query(begun["authorize_url"])["nonce"])
    for _ in range(5):
        assert _complete(helper, token, started["transaction_id"], state="forged").status_code == 409
    closed = _complete(helper, token, started["transaction_id"], state=real_state)
    assert closed.status_code == 403, "다섯 번 틀린 뒤에는 맞는 state 도 받지 않는다"
    assert not [r for r in fake_http.requests if str(r.url).startswith(chatgpt.TOKEN_URL)]


# ── 4 · 5: 교환과 응답 ────────────────────────────────────────────────────────


def test_the_code_exchange_follows_the_contract_and_leaks_nothing(app, client, login_as, fake_http, signing_key,
                                                                   db, caplog):
    caplog.set_level(logging.DEBUG)
    csrf = login_as("system_admin")
    started, token = _start(client, csrf)
    helper = _helper(app)
    begun = _begin(helper, token, port=1461).json()
    query = _query(begun["authorize_url"])
    assert query["redirect_uri"] == "http://127.0.0.1:1461/auth/callback"
    assert query["client_id"] == chatgpt.DYNAMIC_CLIENT_ID and query["agent_name_hint"] == "ClovirAssist"
    assert query["ext_agent_host_id"].startswith("urn:uuid:")
    seen: list = []
    _provider(fake_http, signing_key, nonce_from=lambda: query["nonce"], seen=seen)
    done = _complete(helper, token, started["transaction_id"], state=query["state"])
    assert done.status_code == 200, done.text
    assert done.json() == {"ok": True, "account_label": EMAIL}

    form = seen[0]
    assert form["grant_type"] == "authorization_code" and form["code"] == "AUTH-CODE-1"
    assert form["client_id"] == ISSUED and form["redirect_uri"] == "http://127.0.0.1:1461/auth/callback"
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
    for secret in ("ACCESS-SECRET-VALUE", "REFRESH-SECRET-VALUE", "AUTH-CODE-1", token, form["code_verifier"]):
        assert secret not in everything, "응답, 감사, 로그에 토큰이나 코드가 새면 안 된다"


def test_a_wrong_nonce_or_missing_plan_scope_does_not_connect(app, client, login_as, fake_http, signing_key):
    csrf = login_as("system_admin")
    for kwargs, reason in (({"id_nonce": "someone-elses-nonce"}, "id_token_invalid"),
                           ({"scope": "openid profile email offline_access"}, "plan_scope_missing")):
        started, token = _start(client, csrf)
        helper = _helper(app)
        begun = _begin(helper, token).json()
        query = _query(begun["authorize_url"])
        _provider(fake_http, signing_key, nonce_from=lambda q=query: q["nonce"], **kwargs)
        failed = _complete(helper, token, started["transaction_id"], state=query["state"])
        assert failed.status_code == 409, failed.text
        polled = client.get(f"/api/admin/ai/oauth/openai/transactions/{started['transaction_id']}").json()
        assert (polled["phase"], polled["error_code"]) == ("failed", reason)
    assert not (app.state.settings.secrets_dir / SLOT).exists()


# ── 6: 누가 볼 수 있는가 ──────────────────────────────────────────────────────


def test_only_system_admins_can_start(client, login_as):
    csrf = login_as("admin")
    assert client.post("/api/admin/ai/oauth/openai/start", headers={"X-CSRF-Token": csrf}).status_code == 403


def test_another_admin_or_another_session_cannot_poll(app, client, login_as, make_user):
    started, _token = _start(client, login_as("system_admin"))
    path = f"/api/admin/ai/oauth/openai/transactions/{started['transaction_id']}"
    assert client.get(path).status_code == 200
    with TestClient(app, raise_server_exceptions=False) as other:
        make_user(email="other-sa@goodmit.co.kr", role="system_admin")
        assert other.post("/login", json={"email": "other-sa@goodmit.co.kr",
                                           "password": "Str0ng-Passw0rd!"}).status_code == 200
        assert other.get(path).status_code == 404
    with TestClient(app, raise_server_exceptions=False) as same_person:
        assert same_person.post("/login", json={"email": "system-admin@goodmit.co.kr",
                                                 "password": "Str0ng-Passw0rd!"}).status_code == 200
        assert same_person.get(path).status_code == 404, "같은 사람이라도 다른 세션은 이 시도를 모른다"


# ── 7: 대체 경로 ──────────────────────────────────────────────────────────────


def test_the_manual_path_accepts_only_this_attempts_loopback_callback(app, client, login_as, fake_http, signing_key):
    csrf = login_as("system_admin")
    started, _token = _start(client, csrf)
    tx = started["transaction_id"]
    manual = client.post(f"/api/admin/ai/oauth/openai/transactions/{tx}/manual", headers={"X-CSRF-Token": csrf})
    assert manual.status_code == 200
    query = _query(manual.json()["authorize_url"])
    assert query["redirect_uri"] == "http://127.0.0.1:1455/auth/callback"
    _provider(fake_http, signing_key, nonce_from=lambda: query["nonce"])
    tail = f"?code=C1&state={query['state']}&client_id={ISSUED}&scope=chatgpt.tokens.use.direct"
    for bad in ("http://localhost:1455/auth/callback", "http://127.0.0.1:1455/callback",
                "http://127.0.0.1:9999/auth/callback", "https://127.0.0.1:1455/auth/callback",
                "http://evil.example:1455/auth/callback"):
        refused = client.post(f"/api/admin/ai/oauth/openai/transactions/{tx}/complete",
                              json={"callback_url": bad + tail}, headers={"X-CSRF-Token": csrf})
        assert refused.status_code == 409, bad
    done = client.post(f"/api/admin/ai/oauth/openai/transactions/{tx}/complete",
                       json={"callback_url": "http://127.0.0.1:1455/auth/callback" + tail},
                       headers={"X-CSRF-Token": csrf})
    assert done.status_code == 200 and done.json()["account_label"] == EMAIL


# ── 8: 도우미의 문 ────────────────────────────────────────────────────────────


def test_the_helper_door_refuses_cross_site_browser_requests(app, client, login_as):
    _started, token = _start(client, login_as("system_admin"))
    reply = _helper(app).post("/api/connect/openai/begin", json={"pairing_token": token, "port": 1460},
                              headers={"Sec-Fetch-Site": "cross-site"})
    assert reply.status_code == 403 and reply.json()["error"]["code"] == "origin_mismatch"


def test_the_helper_door_limits_a_flood_from_one_address(app):
    helper = _helper(app)
    codes = [_begin(helper, "y" * 43).status_code for _ in range(12)]
    assert codes[0] == 403 and codes[-1] == 429


def test_helper_files_are_served_and_nothing_else(client):
    got = client.get("/connect/clovirassist-connect.py")
    assert got.status_code == 200 and "attachment" in got.headers["content-disposition"]
    assert b"api/connect/openai/begin" in got.content
    assert client.get("/connect/clovirassist-connect.ps1").status_code == 200
    for bad in ("/connect/main.py", "/connect/..%2Fapp%2Fmain.py", "/connect/%2e%2e%2fconfig%2fallowed-services.json"):
        assert client.get(bad).status_code == 404, bad


# ── 9: 로그아웃 ───────────────────────────────────────────────────────────────


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
