"""The single outbound-HTTP choke point (spec §25.3).

This is the ONLY module in app/ allowed to import httpx — enforced by a
static test. Every outbound request passes the SSRF allowlist at call time,
never follows redirects, ignores proxy environment variables, and injects
authentication from secret references without exposing plaintext.
"""

from __future__ import annotations

import httpx

from app.core.allowlist import AllowlistRegistry
from app.core.errors import ValidationAppError
from app.core.secret_refs import FileSecretReferenceProvider

AUTH_NONE = "none"
AUTH_BEARER = "bearer"
AUTH_API_KEY_HEADER = "api_key_header"

AUTH_TYPES = frozenset({AUTH_NONE, AUTH_BEARER, AUTH_API_KEY_HEADER})

DEFAULT_TIMEOUT_SECONDS = 10.0


class OutboundClient:
    def __init__(
        self,
        allowlists: AllowlistRegistry,
        secrets: FileSecretReferenceProvider,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._allowlists = allowlists
        self._secrets = secrets
        self._client = httpx.Client(
            transport=transport,
            follow_redirects=False,
            trust_env=False,
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        allowlist: str,
        json: dict | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        auth_type: str = AUTH_NONE,
        secret_ref: str | None = None,
    ) -> httpx.Response:
        # Enforcement happens here, at call time — registry-save-time checks
        # are UX, this is the security boundary.
        self._allowlists.get(allowlist).check(url)

        final_headers = dict(headers or {})
        if auth_type != AUTH_NONE:
            if auth_type not in AUTH_TYPES:
                raise ValidationAppError(f"알 수 없는 인증 방식입니다: {auth_type}")
            if not secret_ref:
                raise ValidationAppError("인증 방식에 필요한 secret reference가 없습니다.")
            secret = self._secrets.require(secret_ref)
            if auth_type == AUTH_BEARER:
                final_headers["Authorization"] = f"Bearer {secret.reveal()}"
            elif auth_type == AUTH_API_KEY_HEADER:
                final_headers["X-API-Key"] = secret.reveal()

        return self._client.request(
            method, url, json=json, headers=final_headers, timeout=timeout
        )

    def get(self, url: str, **kwargs) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def close(self) -> None:
        self._client.close()


def is_transport_error(exc: Exception) -> bool:
    return isinstance(exc, httpx.TransportError)


def is_timeout_error(exc: Exception) -> bool:
    return isinstance(exc, httpx.TimeoutException)
