"""FN-02: `llm_backend=api`가 실제로 부르는 호스트가 SSRF allowlist에 있어야 한다.

`app/llm/api_backend.py`가 `ALLOWLIST = "services"`(→ `config/allowed-services.json`)로
Anthropic API를 부르는데, 그 파일에 `api.anthropic.com:443`이 없으면 매 호출이
`URLNotAllowedError`로 영구 실패하고 규칙기반 요약으로 조용히 대체된다 — allowlist UI
자체가 없어 관리자가 원인을 알 길이 없다(파일 직접 확인이 유일한 진단 경로).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.security

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_allowed_services_json_lists_the_anthropic_api_host():
    data = json.loads((PROJECT_ROOT / "config" / "allowed-services.json").read_text(encoding="utf-8"))
    assert "api.anthropic.com:443" in data["hosts"], (
        "llm_backend=api가 부르는 host가 SSRF allowlist에 없다 — 매 호출이 영구 실패한다"
    )


def test_allowlist_class_accepts_the_anthropic_host_when_loaded_from_the_real_config():
    from app.core.allowlist import Allowlist

    data = json.loads((PROJECT_ROOT / "config" / "allowed-services.json").read_text(encoding="utf-8"))
    allowlist = Allowlist("services", frozenset(data["hosts"]))
    allowlist.check("https://api.anthropic.com/v1/messages")  # no raise
