"""AI 제공자 주소가 기본 허용 목록에 있다 (계획 3.14 · 3.17, D-515).

qa-contract-replaced-by: tests/security/test_llm_api_backend_allowlisted.py

옛 시험은 API 백엔드 하나의 주소를 봤다. 이제 제공자 어댑터가 부르는 주소를 전부 본다 - 허용 목록에 없으면 설치한
사람이 서버의 파일을 손으로 고쳐야 AI 가 동작하고(계획 3.17 이 없애려는 수동 단계), 반대로 목록에 없는 주소를 코드가
부르면 호출이 조용히 막혀 「인증 또는 구성 오류」로만 보인다.

바깥 호출의 경계(SSRF 허용 목록)는 그대로다. 어댑터가 부르는 주소는 이 목록 안에 있어야 하고, 이 목록 밖으로는
나갈 수 없다(`app/core/http_client.py`).
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest

pytestmark = pytest.mark.security

ROOT = Path(__file__).resolve().parents[2]


def _allowed() -> set[str]:
    return set(json.loads((ROOT / "config" / "allowed-services.json").read_text(encoding="utf-8"))["hosts"])


def _host_port(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.hostname}:{parts.port or (443 if parts.scheme == 'https' else 80)}"


def test_every_provider_url_is_in_the_default_allowlist():
    from app.ai.providers import anthropic

    urls = [anthropic.MESSAGES_URL, anthropic.MODELS_URL]
    missing = sorted({_host_port(u) for u in urls} - _allowed())
    assert missing == [], f"기본 허용 목록에 없는 AI 제공자 주소: {missing}"


def test_provider_calls_go_through_the_services_allowlist():
    from app.ai.providers import anthropic

    assert anthropic.ALLOWLIST == "services"
    for url in (anthropic.MESSAGES_URL, anthropic.MODELS_URL):
        assert url.startswith("https://"), url
