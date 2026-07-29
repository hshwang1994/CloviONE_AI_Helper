"""SSRF guard: outbound URL allowlists (spec §25.3).

Allowlists live in JSON files (allowed-services.json / allowed-runners.json /
allowed-workflows.json) under settings.config_dir. Matching is exact
``host:port`` after scheme-default port resolution. http/https only,
no userinfo, redirects are never followed (enforced by OutboundClient).
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

from app.core.errors import AppError

ALLOWLIST_FILES = {
    "services": "allowed-services.json",
    "runners": "allowed-runners.json",
    "workflows": "allowed-workflows.json",
}

_DEFAULT_PORTS = {"http": 80, "https": 443}


class URLNotAllowedError(AppError):
    status_code = 400
    code = "url_not_allowed"
    default_message = "허용 목록에 없는 URL입니다."


class Allowlist:
    def __init__(self, name: str, hosts: frozenset[str]) -> None:
        self.name = name
        self._hosts = hosts

    def check(self, url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https"):
            raise URLNotAllowedError("URL Scheme은 http 또는 https만 허용됩니다.")
        if parsed.username is not None or parsed.password is not None:
            raise URLNotAllowedError("URL에 인증 정보를 포함할 수 없습니다.")
        host = (parsed.hostname or "").lower()
        if not host:
            raise URLNotAllowedError("URL에 호스트가 없습니다.")
        port = parsed.port or _DEFAULT_PORTS[parsed.scheme]
        if f"{host}:{port}" not in self._hosts:
            raise URLNotAllowedError(
                f"허용 목록({self.name})에 없는 대상입니다: {host}:{port}"
            )


class AllowlistRegistry:
    """Loads allowlist files with mtime-based caching so admin edits apply
    without a restart."""

    def __init__(self, config_dir: Path) -> None:
        self._config_dir = Path(config_dir)
        self._cache: dict[str, tuple[float, Allowlist]] = {}

    def get(self, name: str) -> Allowlist:
        if name not in ALLOWLIST_FILES:
            raise URLNotAllowedError(f"알 수 없는 허용 목록입니다: {name}")
        path = self._config_dir / ALLOWLIST_FILES[name]
        if not path.exists():
            # Missing file = deny all, never allow-all.
            return Allowlist(name, frozenset())
        mtime = path.stat().st_mtime
        cached = self._cache.get(name)
        if cached is not None and cached[0] == mtime:
            return cached[1]
        data = json.loads(path.read_text(encoding="utf-8"))
        hosts = frozenset(str(h).strip().lower() for h in data.get("hosts", []))
        allowlist = Allowlist(name, hosts)
        self._cache[name] = (mtime, allowlist)
        return allowlist
