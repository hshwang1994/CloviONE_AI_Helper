"""SSRF guard: outbound URL allowlists (spec §25.3).

Allowlists live in JSON files (allowed-services.json) under
settings.config_dir. Matching is exact
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
        try:
            # CORE-05: `urlsplit(...).port`는 파싱이 아니라 **접근 시점**에 범위(0~65535)를
            # 검사해 `ValueError`를 던진다 — 저장 시점엔 URL 검증이 없으니(base_url/
            # health_url/webhook_url이 평범한 str) 관리자가 `:99999` 같은 포트를 저장해
            # 두면 헬스체크마다 이 함수가 이 계약(400 URLNotAllowedError)을 빠져나가
            # 불투명한 500이 됐다.
            port = parsed.port or _DEFAULT_PORTS[parsed.scheme]
        except ValueError:
            raise URLNotAllowedError("URL의 포트 번호가 올바르지 않습니다.") from None
        if f"{host}:{port}" not in self._hosts:
            raise URLNotAllowedError(
                f"허용 목록({self.name})에 없는 대상입니다: {host}:{port}"
            )


class AllowlistRegistry:
    """Loads allowlist files with mtime-based caching so admin edits apply
    without a restart."""

    def __init__(self, config_dir: Path) -> None:
        self._config_dir = Path(config_dir)
        self._cache: dict[str, tuple[tuple, Allowlist]] = {}

    def get(self, name: str) -> Allowlist:
        if name not in ALLOWLIST_FILES:
            raise URLNotAllowedError(f"알 수 없는 허용 목록입니다: {name}")
        path = self._config_dir / ALLOWLIST_FILES[name]
        if not path.exists():
            # Missing file = deny all, never allow-all.
            return Allowlist(name, frozenset())
        # CORE-06: `st_mtime`(초 단위) 하나만 캐시 키로 쓰면, 타임스탬프를 보존하는 복원
        # (`cp -p`·`rsync -a`·tar·installer)이 예전 mtime을 그대로 들고 오는 순간 프로세스
        # 수명 내내 그 mtime의 옛 허용목록을 계속 쓴다(더 넓은 쪽으로 낡을 수 있다는 뜻이라
        # 위험하다). `feature_flags._stat_key`가 같은 문제를 `(mtime_ns, size)`로 이미
        # 풀어 뒀다 — 여기도 같은 키 모양을 쓴다.
        stat = path.stat()
        key = (stat.st_mtime_ns, stat.st_size)
        cached = self._cache.get(name)
        if cached is not None and cached[0] == key:
            return cached[1]
        data = json.loads(path.read_text(encoding="utf-8"))
        hosts = frozenset(str(h).strip().lower() for h in data.get("hosts", []))
        allowlist = Allowlist(name, hosts)
        self._cache[name] = (key, allowlist)
        return allowlist
