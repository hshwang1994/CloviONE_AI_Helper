"""ChatGPT 계정 연결 — 공식 「Sign in with ChatGPT」의 토큰 묶음, 만료, 갱신, 끊기 (계획 3.14 · 3.15, D-516).

## 공식 계약 (developers.openai.com/siwc/token-sharing-open-source, 2026-09-30 확인)

  인가     GET  https://auth.openai.com/api/accounts/authorize   (client_id 는 첫 연결에 dynamic_agent_client)
  교환     POST https://auth.openai.com/api/accounts/oauth/token  (폼 본문, client secret 없음, PKCE S256)
  갱신     같은 주소, grant_type=refresh_token. **갱신 토큰은 쓸 때마다 바뀐다** - 같은 연결의 갱신은 한 번에 하나만
  끊기     POST https://auth.openai.com/api/accounts/oauth/revoke (빈 200 이 성공이다. 이미 무효인 토큰도 200 이다)
  ID 토큰  RS256 서명(JWKS), 발급자, 대상(발급된 client_id), 만료, nonce 를 본다. 신원은 검증된 `sub` 다
  콜백     http://127.0.0.1:<포트>/auth/callback - 포트만 바뀔 수 있다. 브라우저가 있는 PC 에 닿는다

## 만료 시각의 정본은 제공자의 응답이다

공식 문서가 적은 수명(access 1시간, refresh 30일)을 코드의 고정값으로 쓰지 않는다. 응답을 받을 때마다

  access   `expires_in` → access token 이 JWT 면 `exp` → 둘 다 없으면 설정 `ai_openai_access_ttl_fallback_seconds`
  refresh  `refresh_token_expires_in` → 없으면 설정 `ai_openai_refresh_ttl_fallback_days`

순서로 정하고, 어느 쪽으로 정했는지(`expiry_source`)를 함께 남긴다. 제공자가 수명을 바꾸면 응답이 바뀌는 대로 따라간다.

## 토큰은 비밀 칸 하나에만 산다

묶음은 `ai.openai.chatgpt` 비밀 칸(JSON)에 두고 특권 헬퍼로 쓴다(계획 2.3). DB 에는 계정 이름, client_id, 호스트 id,
만료 시각만 둔다(`ai_credential_state`). 토큰 값은 로그, 감사, 응답 어디에도 싣지 않는다.

## 이 서버가 갱신을 맡는다

자체 호스팅 VM 지침 그대로다: 로그인은 브라우저가 있는 PC 에서 끝나지만 이후 갱신은 서버가 제 `ext_agent_host_id` 로
한다. 로그인은 붙여 넣기 하나다 - 관리자가 붙여 넣는 콜백 주소에는 인가 코드만 있고, 코드는 서버의 PKCE verifier
없이는 쓸모가 없다(`app/ai/credentials/login_flow.py`, D-540).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode

from app.ai.providers import base
from app.core.errors import AppError

logger = logging.getLogger("app.ai.chatgpt")

AUTH_BASE = "https://auth.openai.com"
ISSUER = AUTH_BASE
AUTHORIZE_URL = AUTH_BASE + "/api/accounts/authorize"
TOKEN_URL = AUTH_BASE + "/api/accounts/oauth/token"
REVOKE_URL = AUTH_BASE + "/api/accounts/oauth/revoke"
JWKS_URL = AUTH_BASE + "/.well-known/jwks.json"
RESOURCE = "https://api.openai.com/v1"
ALLOWLIST = "services"

SCOPES = ("openid", "profile", "email", "offline_access", "resource.invoke", "chatgpt.tokens.use.direct")
PLAN_SCOPE = "chatgpt.tokens.use.direct"
DYNAMIC_CLIENT_ID = "dynamic_agent_client"
REDIRECT_HOST = "127.0.0.1"
REDIRECT_PATH = "/auth/callback"
DEFAULT_REDIRECT_PORT = 1455
AGENT_NAME = "ClovirAssist"
MANAGE_USAGE_URL = "https://chatgpt.com/settings/usage"

SETTING_ACCESS_FALLBACK = "ai_openai_access_ttl_fallback_seconds"
SETTING_REFRESH_FALLBACK = "ai_openai_refresh_ttl_fallback_days"
SETTING_REFRESH_LEAD = "ai_token_refresh_lead_seconds"
DEFAULT_ACCESS_FALLBACK_SECONDS = 3600
DEFAULT_REFRESH_FALLBACK_DAYS = 30
DEFAULT_REFRESH_LEAD_SECONDS = 300

TOKEN_TIMEOUT_SECONDS = 20.0
JWKS_TTL_SECONDS = 3600.0
LOCK_KEY = "openai.chatgpt"
LOCK_WAIT_SECONDS = 20.0

# 갱신이 이렇게 거절되면 연결이 끊긴 것이다 - 다시 로그인해야 한다(공식 오류표).
REAUTH_CODES = frozenset({
    "invalid_grant", "invalid_refresh_token", "token_expired", "refresh_token_expired",
    "refresh_token_invalidated", "refresh_token_reused",
})
# 묶음에서 토큰을 지울 때 남기는 것 - 다시 로그인할 때 같은 client_id 와 호스트 id 를 쓰고, 계정 이름을 힌트로 준다.
TOKEN_FIELDS = ("access_token", "refresh_token", "id_token")


class OAuthError(AppError):
    """토큰 주소가 거절했거나 닿지 못했다. ``kind`` 는 `app/ai/providers/base.py::ERROR_*` 다. 값은 싣지 않는다.

    이 모듈과 연결 흐름 안에서 잡아 값으로 바꾼다. 요청까지 새어 나가도 원문 없는 한 문장으로만 보인다.
    """

    status_code = 502
    code = "chatgpt_token_error"
    default_message = "ChatGPT 인증 서버와 통신하지 못했습니다."

    def __init__(self, kind: str, reason: str) -> None:
        super().__init__()
        self.kind = kind
        self.reason = reason


@dataclass(frozen=True)
class TokenStatus:
    ok: bool
    kind: str | None = None
    code: str | None = None


OK = TokenStatus(True)


# ── 시각 ─────────────────────────────────────────────────────────────────────


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def parse_time(value) -> datetime | None:
    """ISO 문자열이나 유닉스 초 → UTC(naive). 못 읽으면 None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).replace(tzinfo=None)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str) and value.strip():
        text = value.strip()
        if text.replace(".", "", 1).isdigit():
            return parse_time(float(text))
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    return None


# ── PKCE 와 인가 주소 ─────────────────────────────────────────────────────────


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def pkce_verifier(session_secret: str, state: str) -> str:
    """PKCE verifier 를 **저장하지 않고** 서버 비밀 값과 state 로 만든다. DB 만 새어서는 verifier 를 알 수 없다."""
    key = hmac.new(session_secret.encode("utf-8"), b"clovirassist:siwc-pkce", hashlib.sha256).digest()
    return b64url(hmac.new(key, state.encode("utf-8"), hashlib.sha256).digest())


def pkce_challenge(verifier: str) -> str:
    return b64url(hashlib.sha256(verifier.encode("ascii")).digest())


def redirect_uri(port: int) -> str:
    return f"http://{REDIRECT_HOST}:{int(port)}{REDIRECT_PATH}"


def authorize_url(*, client_id: str, redirect: str, state: str, nonce: str, challenge: str, host_id: str,
                  login_hint: str | None = None) -> str:
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect,
        "scope": " ".join(SCOPES),
        "resource": RESOURCE,
        "state": state,
        "nonce": nonce,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
        "ext_agent_host_id": host_id,
    }
    if client_id == DYNAMIC_CLIENT_ID:
        # 첫 등록에만 싣는다(공식 안내). 사용자가 승인 화면에서 보는 앱 이름이다.
        params["agent_name_hint"] = AGENT_NAME
    if login_hint:
        params["login_hint"] = login_hint
    return AUTHORIZE_URL + "?" + urlencode(params, quote_via=quote)


# ── JWT ──────────────────────────────────────────────────────────────────────


def _b64url_decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def unverified_claims(token) -> dict | None:
    """서명을 **보지 않고** 본문만 읽는다. 만료 시각을 잡는 데만 쓴다 - 신원 판단에는 쓰지 않는다."""
    if not isinstance(token, str) or token.count(".") != 2:
        return None
    try:
        data = json.loads(_b64url_decode(token.split(".")[1]))
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def jwt_exp(token) -> datetime | None:
    claims = unverified_claims(token)
    exp = claims.get("exp") if claims else None
    return parse_time(exp) if isinstance(exp, (int, float)) and not isinstance(exp, bool) else None


class IdTokenError(AppError):
    """ID 토큰을 믿을 수 없다. ``reason`` 이 까닭이다(서명, 발급자, 대상, 만료, nonce)."""

    status_code = 502
    code = "chatgpt_id_token_invalid"
    default_message = "ChatGPT 가 준 계정 정보를 확인하지 못했습니다."

    def __init__(self, reason: str) -> None:
        super().__init__()
        self.reason = reason


def validate_id_token(id_token: str, *, jwks: dict, client_id: str, nonce: str, leeway: int = 60) -> dict:
    """공식 안내의 검증: RS256 서명(JWKS), 발급자, 대상(발급된 client_id), 만료, nonce. 검증된 본문을 돌려준다."""
    import jwt

    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError as exc:
        raise IdTokenError("id_token_malformed") from exc
    if header.get("alg") != "RS256":
        raise IdTokenError("id_token_bad_alg")
    try:
        keyset = jwt.PyJWKSet.from_dict(jwks)
    except jwt.PyJWTError as exc:
        raise IdTokenError("jwks_invalid") from exc
    kid = header.get("kid")
    keys = [k for k in keyset.keys if kid is None or k.key_id == kid]
    if not keys:
        raise IdTokenError("id_token_unknown_key")
    try:
        claims = jwt.decode(
            id_token, key=keys[0].key, algorithms=["RS256"], audience=client_id, issuer=ISSUER, leeway=leeway,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise IdTokenError("id_token_expired") from exc
    except jwt.InvalidAudienceError as exc:
        raise IdTokenError("id_token_bad_audience") from exc
    except jwt.InvalidIssuerError as exc:
        raise IdTokenError("id_token_bad_issuer") from exc
    except jwt.PyJWTError as exc:
        raise IdTokenError("id_token_invalid") from exc
    if not hmac.compare_digest(str(claims.get("nonce") or ""), nonce):
        raise IdTokenError("id_token_bad_nonce")
    return claims


_jwks_cache: dict = {"at": 0.0, "value": None}


def fetch_jwks(outbound, *, force: bool = False, monotonic=time.monotonic) -> dict:
    cached = _jwks_cache["value"]
    if not force and cached is not None and monotonic() - _jwks_cache["at"] < JWKS_TTL_SECONDS:
        return cached
    try:
        response = outbound.request("GET", JWKS_URL, allowlist=ALLOWLIST, timeout=TOKEN_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001
        raise _transport_error(exc) from None
    if response.status_code != 200:
        raise OAuthError(base.ERROR_TRANSIENT, "jwks_unavailable")
    try:
        data = response.json()
    except ValueError:
        raise OAuthError(base.ERROR_TRANSIENT, "jwks_unavailable") from None
    if not isinstance(data, dict) or not isinstance(data.get("keys"), list):
        raise OAuthError(base.ERROR_TRANSIENT, "jwks_unavailable")
    _jwks_cache.update(at=monotonic(), value=data)
    return data


def verified_claims(outbound, id_token: str, *, client_id: str, nonce: str) -> dict:
    """JWKS 를 받아 검증한다. 모르는 키면 키를 한 번 새로 받는다(제공자가 키를 돌렸을 수 있다)."""
    try:
        return validate_id_token(id_token, jwks=fetch_jwks(outbound), client_id=client_id, nonce=nonce)
    except IdTokenError as exc:
        if exc.reason != "id_token_unknown_key":
            raise
    return validate_id_token(id_token, jwks=fetch_jwks(outbound, force=True), client_id=client_id, nonce=nonce)


# ── 만료 ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Expiry:
    access_expires_at: datetime
    refresh_expires_at: datetime | None
    earliest_refresh_at: datetime | None
    #: `<access 출처>+<refresh 출처>` - access 는 expires_in · jwt_exp · fallback, refresh 는 provider · fallback · kept.
    source: str


def _positive_seconds(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value > 0 else None


def compute_expiry(payload: dict, *, now: datetime, access_fallback_seconds: int, refresh_fallback_days: int,
                   previous_refresh_expires_at: datetime | None = None) -> Expiry:
    """토큰 응답 하나 → 만료 시각. 응답이 정본이고 설정은 응답에 정보가 없을 때만 쓴다(머리말)."""
    seconds = _positive_seconds(payload.get("expires_in"))
    if seconds is not None:
        access_at, access_source = now + timedelta(seconds=seconds), "expires_in"
    else:
        exp = jwt_exp(payload.get("access_token"))
        if exp is not None:
            access_at, access_source = exp, "jwt_exp"
        else:
            access_at, access_source = now + timedelta(seconds=int(access_fallback_seconds)), "fallback"
    refresh_seconds = _positive_seconds(payload.get("refresh_token_expires_in"))
    if refresh_seconds is not None:
        refresh_at, refresh_source = now + timedelta(seconds=refresh_seconds), "provider"
    elif payload.get("refresh_token"):
        refresh_at, refresh_source = now + timedelta(days=int(refresh_fallback_days)), "fallback"
    else:
        # 갱신 응답이 새 갱신 토큰을 주지 않았다 - 옛 토큰과 그 만료를 그대로 쓴다.
        refresh_at, refresh_source = previous_refresh_expires_at, "kept"
    return Expiry(
        access_expires_at=access_at, refresh_expires_at=refresh_at,
        earliest_refresh_at=parse_time(payload.get("earliest_refresh_at")),
        source=f"{access_source}+{refresh_source}",
    )


def settings_numbers(values: dict) -> tuple[int, int, int]:
    """(access 대체 초, refresh 대체 일, 갱신 여유 초). 설정이 비었거나 틀리면 기본값."""

    def _int(key: str, default: int) -> int:
        value = values.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else default

    return (
        _int(SETTING_ACCESS_FALLBACK, DEFAULT_ACCESS_FALLBACK_SECONDS),
        _int(SETTING_REFRESH_FALLBACK, DEFAULT_REFRESH_FALLBACK_DAYS),
        _int(SETTING_REFRESH_LEAD, DEFAULT_REFRESH_LEAD_SECONDS),
    )


# ── 토큰 주소 ─────────────────────────────────────────────────────────────────


def _transport_error(exc: Exception) -> OAuthError:
    from app.core.allowlist import URLNotAllowedError
    from app.core.http_client import is_timeout_error, is_transport_error

    if isinstance(exc, URLNotAllowedError):
        return OAuthError(base.ERROR_CONFIG, "host_not_allowed")
    if is_timeout_error(exc):
        return OAuthError(base.ERROR_TRANSIENT, "timeout")
    if is_transport_error(exc):
        return OAuthError(base.ERROR_TRANSIENT, "connect")
    logger.warning("ChatGPT 토큰 주소 호출 실패: %s", type(exc).__name__)
    return OAuthError(base.ERROR_TRANSIENT, "unexpected")


def _token_post(outbound, form: dict) -> dict:
    try:
        response = outbound.request(
            "POST", TOKEN_URL, allowlist=ALLOWLIST, data=form, headers={"Accept": "application/json"},
            timeout=TOKEN_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001
        raise _transport_error(exc) from None
    if response.status_code >= 500:
        raise OAuthError(base.ERROR_TRANSIENT, f"http_{response.status_code}")
    try:
        data = response.json()
    except ValueError:
        raise OAuthError(base.ERROR_TRANSIENT, "bad_json") from None
    if response.status_code >= 400:
        error = data.get("error") if isinstance(data, dict) else None
        code = str((error.get("code") or error.get("type")) if isinstance(error, dict) else (error or ""))
        if code in REAUTH_CODES:
            raise OAuthError(base.ERROR_REAUTH, code)
        if code == "invalid_client":
            # 발급된 client_id 를 제공자가 더 이상 알지 못한다. 토큰도 함께 쓸모없다(부른 쪽이 지운다).
            raise OAuthError(base.ERROR_CONFIG, "invalid_client")
        if response.status_code == 429:
            raise OAuthError(base.ERROR_TRANSIENT, "http_429")
        raise OAuthError(base.ERROR_CONFIG, code or f"http_{response.status_code}")
    if not isinstance(data, dict) or not isinstance(data.get("access_token"), str) or not data["access_token"]:
        raise OAuthError(base.ERROR_TRANSIENT, "bad_token_response")
    return data


def exchange_code(outbound, *, code: str, client_id: str, redirect: str, verifier: str) -> dict:
    return _token_post(outbound, {
        "grant_type": "authorization_code", "code": code, "client_id": client_id, "redirect_uri": redirect,
        "code_verifier": verifier, "resource": RESOURCE,
    })


def refresh_grant(outbound, *, refresh_token: str, client_id: str) -> dict:
    # scope 를 보내지 않는다 - 보내지 않으면 처음 받은 권한 그대로다(공식 안내).
    return _token_post(outbound, {
        "grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": client_id, "resource": RESOURCE,
    })


def revoke(outbound, *, refresh_token: str, client_id: str) -> bool:
    """갱신 토큰을 무효로 만든다. 빈 200 이 성공이다. 확인하지 못하면 False(부른 쪽이 사람에게 알린다)."""
    try:
        response = outbound.request(
            "POST", REVOKE_URL, allowlist=ALLOWLIST, timeout=TOKEN_TIMEOUT_SECONDS,
            data={"token": refresh_token, "token_type_hint": "refresh_token", "client_id": client_id},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("ChatGPT 토큰 무효화 실패: %s", type(exc).__name__)
        return False
    return response.status_code == 200


# ── 묶음 ─────────────────────────────────────────────────────────────────────


def scopes_of(payload: dict, fallback: str | None = None) -> list[str]:
    raw = payload.get("scope")
    if not isinstance(raw, str) or not raw.strip():
        raw = fallback or ""
    return sorted({item for item in raw.split() if item})


def new_bundle(*, payload: dict, claims: dict, client_id: str, host_id: str, expiry: Expiry, now: datetime,
               scopes: list[str], owner_user_id: str | None = None) -> dict:
    """로그인 한 번 → 묶음. `login_id` 는 이 로그인에만 붙는다 - 연결 상태의 지문이 갱신이 아니라 새 로그인에만 바뀐다.

    `owner_user_id` 는 연결한 관리자다(D-559 개인 평가 모드) — 이 요금제의 토큰은 그 사람의 것이라 AI 도 그 사람만 쓴다.
    """
    return {
        "version": 1,
        "login_id": uuid.uuid4().hex,
        "owner_user_id": owner_user_id,
        "issuer": ISSUER,
        "subject": str(claims.get("sub") or ""),
        "email": claims.get("email") if isinstance(claims.get("email"), str) else None,
        "client_id": client_id,
        "ext_agent_host_id": host_id,
        "id_token": payload.get("id_token"),
        "access_token": payload["access_token"],
        "refresh_token": payload.get("refresh_token"),
        "token_type": payload.get("token_type") or "Bearer",
        "scopes": scopes,
        "access_expires_at": iso(expiry.access_expires_at),
        "refresh_expires_at": iso(expiry.refresh_expires_at),
        "earliest_refresh_at": iso(expiry.earliest_refresh_at),
        "expiry_source": expiry.source,
        "refresh_obtained_at": iso(now),
        "saved_at": iso(now),
    }


def refreshed_bundle(current: dict, payload: dict, *, expiry: Expiry, now: datetime) -> dict:
    updated = dict(current)
    updated["access_token"] = payload["access_token"]
    if isinstance(payload.get("refresh_token"), str) and payload["refresh_token"]:
        updated["refresh_token"] = payload["refresh_token"]
        updated["refresh_obtained_at"] = iso(now)
    if isinstance(payload.get("id_token"), str) and payload["id_token"]:
        updated["id_token"] = payload["id_token"]
    updated["access_expires_at"] = iso(expiry.access_expires_at)
    updated["refresh_expires_at"] = iso(expiry.refresh_expires_at)
    updated["earliest_refresh_at"] = iso(expiry.earliest_refresh_at)
    updated["expiry_source"] = expiry.source
    updated["saved_at"] = iso(now)
    return updated


def without_tokens(current: dict, *, reason: str, now: datetime) -> dict:
    """연결이 끊겼을 때의 묶음 - 토큰만 지우고 다시 로그인에 쓸 것(client_id, 호스트 id, 계정 이름)은 남긴다."""
    kept = {k: v for k, v in current.items() if k not in TOKEN_FIELDS}
    kept["disconnected_at"] = iso(now)
    kept["disconnect_reason"] = reason
    return kept


def token_fingerprint(bundle: dict | None) -> str:
    token = (bundle or {}).get("access_token") or ""
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()[:16]


# ── 토큰 관리자 ───────────────────────────────────────────────────────────────


class ChatGptTokens:
    """계정 연결 하나의 토큰. 어댑터는 부르기 전에 `ensure_fresh`, 401 을 받으면 `force_refresh` 를 부른다.

    갱신은 DB 잠금(`NS_AI_TOKEN_REFRESH`)으로 프로세스 사이에서 한 번에 하나만 한다. 잠근 뒤 묶음을 **다시 읽어**
    아직 갱신이 필요할 때만 갱신한다 - 기다리는 동안 다른 프로세스가 이미 바꿨을 수 있다.
    """

    def __init__(self, *, secrets, store, outbound, session_factory=None, clock=None, settings_cache=None,
                 lock_wait_seconds: float = LOCK_WAIT_SECONDS) -> None:
        from app.core.secret_slots import SLOT_OPENAI_CHATGPT

        self.slot = SLOT_OPENAI_CHATGPT
        self._secrets = secrets
        self._store = store
        self._outbound = outbound
        self._session_factory = session_factory
        self._clock = clock
        self._settings_cache = settings_cache
        self._lock_wait = lock_wait_seconds

    # ── 읽기 ──

    def now(self) -> datetime:
        if self._clock is not None:
            return self._clock.now()
        from app.core.models_base import utcnow

        return utcnow()

    def values(self) -> dict:
        try:
            return self._settings_cache.current() if self._settings_cache is not None else {}
        except Exception:  # noqa: BLE001 - 설정을 못 읽으면 기본값으로 판단한다
            return {}

    def bundle(self) -> dict | None:
        if self._secrets is None:
            return None
        try:
            value = self._secrets.get(self.slot)
        except Exception:  # noqa: BLE001
            return None
        if value is None:
            return None
        try:
            data = json.loads(value.reveal())
        except ValueError:
            logger.warning("ChatGPT 계정 연결 묶음을 읽지 못했다")
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def connected(bundle: dict | None) -> bool:
        return bool(bundle and bundle.get("access_token") and bundle.get("refresh_token"))

    def needs_refresh(self, bundle: dict, now: datetime, lead: timedelta) -> bool:
        expires = parse_time(bundle.get("access_expires_at"))
        if expires is None:
            return True
        if now >= expires:
            return True
        earliest = parse_time(bundle.get("earliest_refresh_at"))
        if earliest is not None and now < earliest:
            # 제공자가 「이보다 먼저 갱신하지 말라」고 한 시각 전이다. 토큰이 아직 살아 있으면 기다린다.
            return False
        return now >= expires - lead

    # ── 갱신 ──

    def ensure_fresh(self, *, lead: timedelta | None = None) -> TokenStatus:
        bundle = self.bundle()
        if bundle is None:
            return TokenStatus(False, base.ERROR_REAUTH, "account_not_connected")
        if not self.connected(bundle):
            return TokenStatus(False, base.ERROR_REAUTH, "account_disconnected")
        if lead is None:
            lead = timedelta(seconds=settings_numbers(self.values())[2])
        if not self.needs_refresh(bundle, self.now(), lead):
            return OK
        return self._refresh(seen=token_fingerprint(bundle), force=False, lead=lead)

    def force_refresh(self) -> TokenStatus:
        bundle = self.bundle()
        if not self.connected(bundle):
            return TokenStatus(False, base.ERROR_REAUTH, "account_disconnected")
        return self._refresh(seen=token_fingerprint(bundle), force=True, lead=timedelta(0))

    def _refresh(self, *, seen: str, force: bool, lead: timedelta) -> TokenStatus:
        from app.core.advisory_lock import NS_AI_TOKEN_REFRESH, wait_lock

        if self._session_factory is None or self._outbound is None:
            return TokenStatus(False, base.ERROR_TRANSIENT, "refresh_unavailable")
        # 새 토큰을 저장할 수 없으면 갱신하지 않는다. 갱신하는 순간 옛 갱신 토큰이 무효가 되므로, 저장하지 못한 새
        # 토큰은 연결 자체를 잃게 만든다(D-516).
        if not self._store.ready():
            return TokenStatus(False, base.ERROR_CONFIG, "secret_store_unavailable")
        with self._session_factory() as db:
            with wait_lock(db, NS_AI_TOKEN_REFRESH, LOCK_KEY, wait_seconds=self._lock_wait) as got:
                now = self.now()
                current = self.bundle()
                if not self.connected(current):
                    return TokenStatus(False, base.ERROR_REAUTH, "account_disconnected")
                if not got:
                    expires = parse_time(current.get("access_expires_at"))
                    if expires is not None and now < expires and not force:
                        return OK
                    return TokenStatus(False, base.ERROR_TRANSIENT, "refresh_busy")
                if token_fingerprint(current) != seen:
                    # 기다리는 동안 다른 프로세스가 갱신했다.
                    return OK
                if not force and not self.needs_refresh(current, now, lead):
                    return OK
                try:
                    payload = refresh_grant(self._outbound, refresh_token=current["refresh_token"],
                                            client_id=str(current.get("client_id") or ""))
                except OAuthError as exc:
                    if exc.kind == base.ERROR_REAUTH or exc.reason == "invalid_client":
                        self._forget_tokens(current, reason=exc.reason, now=now)
                    return TokenStatus(False, exc.kind, exc.reason)
                access_fallback, refresh_fallback, _lead = settings_numbers(self.values())
                expiry = compute_expiry(
                    payload, now=now, access_fallback_seconds=access_fallback, refresh_fallback_days=refresh_fallback,
                    previous_refresh_expires_at=parse_time(current.get("refresh_expires_at")),
                )
                updated = refreshed_bundle(current, payload, expiry=expiry, now=now)
                try:
                    self._store.write(self.slot, json.dumps(updated, ensure_ascii=False))
                except Exception:  # noqa: BLE001 - 값은 싣지 않는다
                    logger.error("갱신한 ChatGPT 토큰을 저장하지 못했다(비밀 저장 도우미)")
                    return TokenStatus(False, base.ERROR_CONFIG, "secret_store_unavailable")
                self._record_expiry(db, updated, now=now)
                db.commit()
        return OK

    # ── 쓰기 ──

    def store_ready(self) -> bool:
        """지금 묶음을 저장할 수 있는가(`SecretStore.ready`)."""
        return self._store.ready()

    def save_login(self, bundle: dict) -> None:
        """새 로그인의 묶음을 저장한다. 저장하지 못하면 예외가 그대로 올라간다(연결 화면이 사람에게 말한다)."""
        self._store.write(self.slot, json.dumps(bundle, ensure_ascii=False))

    def forget(self) -> bool:
        """묶음을 지운다(로그아웃). 원래 있었는지를 돌려준다."""
        return self._store.delete(self.slot)

    def _forget_tokens(self, current: dict, *, reason: str, now: datetime) -> None:
        try:
            self._store.write(self.slot, json.dumps(without_tokens(current, reason=reason, now=now), ensure_ascii=False))
        except Exception:  # noqa: BLE001
            logger.error("끊긴 ChatGPT 연결의 토큰을 지우지 못했다")

    def _record_expiry(self, db, bundle: dict, *, now: datetime) -> None:
        from app.ai.credentials import state as state_mod

        try:
            state_mod.update_account(
                db, base.PROVIDER_OPENAI, base.AUTH_CHATGPT, now=now,
                access_expires_at=parse_time(bundle.get("access_expires_at")),
                refresh_expires_at=parse_time(bundle.get("refresh_expires_at")),
                refresh_obtained_at=parse_time(bundle.get("refresh_obtained_at")),
                expiry_source=str(bundle.get("expiry_source") or "")[:32] or None,
            )
        except Exception:  # noqa: BLE001 - 표시용 기록이 갱신을 실패로 만들면 안 된다
            logger.exception("ChatGPT 토큰 만료 시각을 적지 못했다")
