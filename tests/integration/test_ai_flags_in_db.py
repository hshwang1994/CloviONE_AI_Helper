"""AI 기능 플래그 셋은 DB 소유다 (계획 3.13, D-507).

예전에는 `/etc/clovirassist/feature-flags.json` 소유라 운영에서 관리 화면이 켜지 못했다(409).
확인하는 것:
- 옛 파일 값은 한 번만 DB 로 옮기고, DB 에 값이 있으면 건드리지 않는다.
- 파일 값이 기본값과 같으면 행을 만들지 않는다.
- 관리 화면(설정 API)에서 켠 값이 재시작 없이 소비처에 닿는다.
- 부서 범위 관리자는 이 값을 못 바꾼다(system_admin 전용 키).
"""

from __future__ import annotations

import json

import pytest

from app.core.feature_flags import import_legacy_file_values
from app.settings.models import AppSetting

pytestmark = pytest.mark.integration


def _write_flags(config_dir, values: dict) -> None:
    (config_dir / "feature-flags.json").write_text(json.dumps(values), encoding="utf-8")


def test_legacy_file_values_move_once_and_never_override(db, tmp_path):
    _write_flags(tmp_path, {"game_ai_enabled": True, "chat_enabled": True, "assistant_narrative_enabled": False})
    moved = import_legacy_file_values(db, tmp_path)
    db.commit()
    # chat_enabled=true 와 narrative=false 는 기본값이라 행을 만들지 않는다.
    assert moved == ["game_ai_enabled"]
    assert json.loads(db.get(AppSetting, "game_ai_enabled").value_json) is True
    assert db.get(AppSetting, "chat_enabled") is None

    # 관리자가 화면에서 끈 뒤 파일이 여전히 true 여도 DB 값이 이긴다.
    db.get(AppSetting, "game_ai_enabled").value_json = json.dumps(False)
    db.commit()
    assert import_legacy_file_values(db, tmp_path) == []
    db.commit()
    assert json.loads(db.get(AppSetting, "game_ai_enabled").value_json) is False


def test_a_string_true_in_the_file_is_not_trusted(db, tmp_path):
    _write_flags(tmp_path, {"game_ai_enabled": "true"})
    assert import_legacy_file_values(db, tmp_path) == []


def test_turning_on_quiz_ai_from_settings_reaches_the_game_screen_without_restart(client, login_as):
    csrf = login_as("system_admin")
    before = client.get("/api/games/rooms")
    assert before.status_code == 200, before.text
    assert before.json()["game_ai_enabled"] is False

    r = client.put("/api/admin/settings/game_ai_enabled", json={"value": True},
                   headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    after = client.get("/api/games/rooms")
    assert after.json()["game_ai_enabled"] is True


def test_turning_off_chat_closes_the_chat_api(client, login_as):
    csrf = login_as("system_admin")
    assert client.get("/api/conversations").status_code == 200
    r = client.put("/api/admin/settings/chat_enabled", json={"value": False},
                   headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    assert client.get("/api/conversations").status_code == 404
    # 메뉴도 함께 사라진다 - 눌러 봐야 거절당하는 항목을 남기지 않는다.
    assert client.get("/api/me").json()["features"]["chat_enabled"] is False


def test_a_department_admin_cannot_flip_ai_flags(client, login_as):
    csrf = login_as("admin")
    r = client.put("/api/admin/settings/game_ai_enabled", json={"value": True},
                   headers={"X-CSRF-Token": csrf})
    assert r.status_code == 403, r.text
