"""ChatGPT 계정 연결의 토큰 — 만료의 정본, PKCE, 인가 주소, ID 토큰 검증, 토큰 주소의 오류 (계획 3.14 · 3.15, D-516).

못박는 성질:
1. 만료 시각의 정본은 제공자의 응답이다. `expires_in` 이 7200 이면 기본값 3600 을 쓰지 않는다. 응답에 없을 때만
   JWT `exp`, 그다음 설정의 기본값을 쓰고, 어느 쪽으로 정했는지 남긴다. 설정을 바꾸면 코드 변경 없이 다음 계산에 쓰인다.
2. PKCE verifier 는 저장하지 않는다 - 서버 비밀 값과 state 로 다시 만든다. state 가 다르면 verifier 도 다르다.
3. 인가 주소는 공식 계약 그대로다(127.0.0.1 루프백, `/auth/callback`, S256, resource, 호스트 id).
4. ID 토큰은 RS256 서명, 발급자, 대상, 만료, nonce 를 모두 본다. 하나라도 틀리면 믿지 않는다.
5. 갱신 거절(`invalid_grant` 등)은 재로그인 필요, `invalid_client` 는 구성 오류, 5xx 는 일시 장애다.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.ai.credentials import chatgpt
from app.ai.providers import base
from app.core.allowlist import AllowlistRegistry
from app.core.http_client import OutboundClient
from app.core.secret_refs import FileSecretReferenceProvider
from tests.fakes.http import FakeHTTP

NOW = datetime(2026, 9, 30, 12, 0, 0)


def _jwt_without_signature(claims: dict) -> str:
    seg = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()  # noqa: E731
    return f"{seg({'alg': 'none'})}.{seg(claims)}.sig"


# ── 만료 ─────────────────────────────────────────────────────────────────────


def test_expires_in_from_the_provider_wins_over_the_fallback():
    expiry = chatgpt.compute_expiry({"access_token": "a", "refresh_token": "r", "expires_in": 7200}, now=NOW,
                                    access_fallback_seconds=3600, refresh_fallback_days=30)
    assert expiry.access_expires_at == NOW + timedelta(seconds=7200)
    assert expiry.source.startswith("expires_in+")


def test_jwt_exp_is_used_when_expires_in_is_missing():
    exp = int(datetime(2026, 9, 30, 12, 42, tzinfo=timezone.utc).timestamp())
    token = _jwt_without_signature({"exp": exp})
    expiry = chatgpt.compute_expiry({"access_token": token, "refresh_token": "r"}, now=NOW,
                                    access_fallback_seconds=3600, refresh_fallback_days=30)
    assert expiry.access_expires_at == NOW + timedelta(minutes=42)
    assert expiry.source.startswith("jwt_exp+")


def test_the_setting_fallback_is_used_only_without_any_provider_information():
    payload = {"access_token": "opaque", "refresh_token": "r"}
    first = chatgpt.compute_expiry(payload, now=NOW, access_fallback_seconds=3600, refresh_fallback_days=30)
    changed = chatgpt.compute_expiry(payload, now=NOW, access_fallback_seconds=1800, refresh_fallback_days=7)
    assert first.access_expires_at == NOW + timedelta(seconds=3600)
    assert changed.access_expires_at == NOW + timedelta(seconds=1800), "설정을 바꾸면 코드 변경 없이 반영된다"
    assert changed.refresh_expires_at == NOW + timedelta(days=7)
    assert first.source == "fallback+fallback"


def test_refresh_lifetime_from_the_provider_and_kept_when_not_rotated():
    given = chatgpt.compute_expiry({"access_token": "a", "refresh_token": "r2", "expires_in": 3600,
                                    "refresh_token_expires_in": 86400}, now=NOW, access_fallback_seconds=3600,
                                   refresh_fallback_days=30)
    assert given.refresh_expires_at == NOW + timedelta(days=1) and given.source == "expires_in+provider"
    earlier = NOW + timedelta(days=9)
    kept = chatgpt.compute_expiry({"access_token": "a", "expires_in": 3600}, now=NOW, access_fallback_seconds=3600,
                                  refresh_fallback_days=30, previous_refresh_expires_at=earlier)
    assert kept.refresh_expires_at == earlier and kept.source.endswith("+kept")


def test_earliest_refresh_at_accepts_epoch_and_iso():
    assert chatgpt.parse_time(0) == datetime(1970, 1, 1)
    assert chatgpt.parse_time("2026-09-30T12:00:00Z") == NOW
    assert chatgpt.parse_time("2026-09-30T21:00:00+09:00") == NOW
    assert chatgpt.parse_time("not a time") is None
    assert chatgpt.parse_time(True) is None


def test_needs_refresh_honours_the_lead_and_the_earliest_refresh_time():
    tokens = chatgpt.ChatGptTokens(secrets=None, store=None, outbound=None)
    lead = timedelta(minutes=5)
    fresh = {"access_expires_at": (NOW + timedelta(minutes=30)).isoformat()}
    near = {"access_expires_at": (NOW + timedelta(minutes=3)).isoformat()}
    held = {**near, "earliest_refresh_at": (NOW + timedelta(minutes=1)).isoformat()}
    expired = {"access_expires_at": (NOW - timedelta(seconds=1)).isoformat(),
               "earliest_refresh_at": (NOW + timedelta(minutes=1)).isoformat()}
    assert tokens.needs_refresh(fresh, NOW, lead) is False
    assert tokens.needs_refresh(near, NOW, lead) is True
    assert tokens.needs_refresh(held, NOW, lead) is False, "제공자가 정한 이른 갱신 금지 시각을 지킨다"
    assert tokens.needs_refresh(expired, NOW, lead) is True, "끝난 토큰은 금지 시각과 상관없이 갱신한다"
    assert tokens.needs_refresh({}, NOW, lead) is True


# ── PKCE 와 인가 주소 ─────────────────────────────────────────────────────────


def test_pkce_verifier_is_derived_not_stored():
    one = chatgpt.pkce_verifier("server-secret-value", "state-a")
    again = chatgpt.pkce_verifier("server-secret-value", "state-a")
    other_state = chatgpt.pkce_verifier("server-secret-value", "state-b")
    other_secret = chatgpt.pkce_verifier("another-secret-value", "state-a")
    assert one == again and len(one) == 43
    assert len({one, other_state, other_secret}) == 3
    digest = hashlib.sha256(one.encode("ascii")).digest()
    assert chatgpt.pkce_challenge(one) == base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def test_the_authorize_url_follows_the_official_contract():
    url = chatgpt.authorize_url(client_id=chatgpt.DYNAMIC_CLIENT_ID, redirect=chatgpt.redirect_uri(1459),
                                state="st", nonce="nn", challenge="ch", host_id="urn:uuid:abc")
    parts = urlsplit(url)
    query = {k: v[0] for k, v in parse_qs(parts.query).items()}
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == chatgpt.AUTHORIZE_URL
    assert query["redirect_uri"] == "http://127.0.0.1:1459/auth/callback"
    assert query["response_type"] == "code" and query["code_challenge_method"] == "S256"
    assert query["resource"] == "https://api.openai.com/v1"
    assert set(query["scope"].split()) >= {"openid", "offline_access", "chatgpt.tokens.use.direct"}
    assert query["agent_name_hint"] == "ClovirAssist" and query["ext_agent_host_id"] == "urn:uuid:abc"
    issued = chatgpt.authorize_url(client_id="oaiapp_1", redirect=chatgpt.redirect_uri(1455), state="s",
                                   nonce="n", challenge="c", host_id="urn:uuid:abc", login_hint="a@b.example")
    issued_query = parse_qs(urlsplit(issued).query)
    assert "agent_name_hint" not in issued_query, "앱 이름 힌트는 첫 등록에만 싣는다"
    assert issued_query["login_hint"] == ["a@b.example"]


# ── ID 토큰 ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwks(key, kid="k1") -> dict:
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    public.update(kid=kid, use="sig", alg="RS256")
    return {"keys": [public]}


def _id_token(key, *, kid="k1", alg="RS256", **overrides) -> str:
    now = int(time.time())
    claims = {"iss": chatgpt.ISSUER, "aud": "oaiapp_1", "sub": "user-sub", "email": "a@b.example",
              "iat": now, "exp": now + 600, "nonce": "nonce-1", **overrides}
    if alg == "HS256":
        return jwt.encode(claims, "shared-secret-" + "x" * 32, algorithm="HS256", headers={"kid": kid})
    return jwt.encode(claims, key, algorithm=alg, headers={"kid": kid})


def test_a_valid_id_token_passes(signing_key):
    claims = chatgpt.validate_id_token(_id_token(signing_key), jwks=_jwks(signing_key), client_id="oaiapp_1",
                                       nonce="nonce-1")
    assert claims["sub"] == "user-sub" and claims["email"] == "a@b.example"


@pytest.mark.parametrize("overrides, reason", [
    ({"nonce": "other"}, "id_token_bad_nonce"),
    ({"aud": "someone-else"}, "id_token_bad_audience"),
    ({"iss": "https://evil.example"}, "id_token_bad_issuer"),
    ({"exp": int(time.time()) - 3600}, "id_token_expired"),
])
def test_every_claim_is_checked(signing_key, overrides, reason):
    with pytest.raises(chatgpt.IdTokenError) as caught:
        chatgpt.validate_id_token(_id_token(signing_key, **overrides), jwks=_jwks(signing_key),
                                  client_id="oaiapp_1", nonce="nonce-1")
    assert caught.value.reason == reason


def test_an_unsigned_or_foreign_key_token_is_refused(signing_key):
    with pytest.raises(chatgpt.IdTokenError) as bad_alg:
        chatgpt.validate_id_token(_id_token(signing_key, alg="HS256"), jwks=_jwks(signing_key),
                                  client_id="oaiapp_1", nonce="nonce-1")
    assert bad_alg.value.reason == "id_token_bad_alg"
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(chatgpt.IdTokenError) as foreign:
        chatgpt.validate_id_token(_id_token(other), jwks=_jwks(signing_key), client_id="oaiapp_1", nonce="nonce-1")
    assert foreign.value.reason == "id_token_invalid", "다른 키로 서명한 토큰을 믿으면 안 된다"
    with pytest.raises(chatgpt.IdTokenError) as unknown:
        chatgpt.validate_id_token(_id_token(signing_key, kid="rotated"), jwks=_jwks(signing_key),
                                  client_id="oaiapp_1", nonce="nonce-1")
    assert unknown.value.reason == "id_token_unknown_key"


# ── 토큰 주소 ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def outbound(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "allowed-services.json").write_text(json.dumps({"hosts": ["auth.openai.com:443"]}), encoding="utf-8")
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    fake = FakeHTTP()
    client = OutboundClient(AllowlistRegistry(config), FileSecretReferenceProvider(secrets), transport=fake.transport())
    yield client, fake
    client.close()


@pytest.mark.parametrize("status, body, kind, reason", [
    (400, {"error": "invalid_grant"}, base.ERROR_REAUTH, "invalid_grant"),
    (400, {"error": "refresh_token_reused"}, base.ERROR_REAUTH, "refresh_token_reused"),
    (400, {"error": {"code": "refresh_token_expired"}}, base.ERROR_REAUTH, "refresh_token_expired"),
    (401, {"error": "invalid_client"}, base.ERROR_CONFIG, "invalid_client"),
    (429, {"error": "slow_down"}, base.ERROR_TRANSIENT, "http_429"),
    (502, {"error": "bad_gateway"}, base.ERROR_TRANSIENT, "http_502"),
    (200, {"token_type": "Bearer"}, base.ERROR_TRANSIENT, "bad_token_response"),
])
def test_token_endpoint_errors_map_to_states(outbound, status, body, kind, reason):
    client, fake = outbound
    fake.on(chatgpt.TOKEN_URL, status=status, json_body=body)
    with pytest.raises(chatgpt.OAuthError) as caught:
        chatgpt.refresh_grant(client, refresh_token="rt", client_id="oaiapp_1")
    assert (caught.value.kind, caught.value.reason) == (kind, reason)


def test_refresh_sends_the_official_form_without_scope(outbound):
    client, fake = outbound
    fake.on(chatgpt.TOKEN_URL, json_body={"access_token": "new", "refresh_token": "r2", "expires_in": 3600})
    chatgpt.refresh_grant(client, refresh_token="rt-old", client_id="oaiapp_1")
    form = parse_qs(fake.requests[0].content.decode())
    assert form == {"grant_type": ["refresh_token"], "refresh_token": ["rt-old"], "client_id": ["oaiapp_1"],
                    "resource": ["https://api.openai.com/v1"]}


def test_revoke_is_true_only_for_a_200(outbound):
    client, fake = outbound
    fake.on(chatgpt.REVOKE_URL, status=200, text="")
    assert chatgpt.revoke(client, refresh_token="rt", client_id="c") is True
    form = parse_qs(fake.requests[0].content.decode())
    assert form["token_type_hint"] == ["refresh_token"] and form["token"] == ["rt"]
    fake.on(chatgpt.REVOKE_URL, status=400, json_body={"error": "invalid_request"})
    assert chatgpt.revoke(client, refresh_token="rt", client_id="c") is False
    fake.on_connect_error(chatgpt.REVOKE_URL)
    assert chatgpt.revoke(client, refresh_token="rt", client_id="c") is False


def test_forgetting_tokens_keeps_what_a_new_login_needs():
    bundle = {"access_token": "a", "refresh_token": "r", "id_token": "i", "client_id": "oaiapp_1",
              "ext_agent_host_id": "urn:uuid:x", "email": "a@b.example", "login_id": "L"}
    kept = chatgpt.without_tokens(bundle, reason="invalid_grant", now=NOW)
    assert not {"access_token", "refresh_token", "id_token"} & set(kept)
    assert kept["client_id"] == "oaiapp_1" and kept["ext_agent_host_id"] == "urn:uuid:x"
    assert kept["login_id"] == "L", "로그인 표식이 그대로여야 연결 상태가 확인 전으로 튀지 않는다"
    assert kept["disconnect_reason"] == "invalid_grant"
