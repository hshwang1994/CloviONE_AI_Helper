"""Feature flags from config_dir/feature-flags.json (spec §14.4)."""

from __future__ import annotations

import json
from pathlib import Path

_DEFAULTS = {
    "maintenance_mode": False,
    "document_automation_enabled": True,
    "limited_service_actions_enabled": False,
    "self_approval_allowed": False,
    # 팀 공간 기능별 토글(§23). 파일에서 끄면 해당 API가 404를 돌려주고 신규 기능이 격리된다.
    "board_enabled": True,
    "team_docs_enabled": True,
    "games_enabled": True,
    # 게임 AI 생성(§7-9)은 기본 OFF(fail-closed) — 러너/Claude 호출을 켤 때만 명시적으로 연다.
    "game_ai_enabled": False,
}


def load_feature_flags(config_dir: Path) -> dict:
    path = Path(config_dir) / "feature-flags.json"
    if not path.exists():
        return dict(_DEFAULTS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(_DEFAULTS)
    flags = dict(_DEFAULTS)
    flags.update({k: v for k, v in data.items() if not k.startswith("_")})
    return flags
