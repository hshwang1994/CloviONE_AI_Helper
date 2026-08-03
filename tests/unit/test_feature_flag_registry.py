"""기능 플래그 레지스트리 동등성 — 설정 split-brain 이 다시 열리지 않게 한다 (0026).

**고쳤던 사고.** `maintenance_mode` 와 `document_automation_enabled` 는 두 곳에 동시에
정의돼 있었다: `config/feature-flags.json` 과 `app/settings/registry.py`(DB). 읽는 코드는
DB 쪽만 봤다. 즉 운영자가 서버에서 JSON 을 고치고 재시작해도 **아무 일도 일어나지 않는다** —
오류도 경고도 없이. 점검 모드를 켰다고 믿은 채로 사용자 요청이 그대로 들어온다.

이 파일은 그 상태가 **다시 만들어지지 못하게** 막는다. 사람이 주석으로 "여기 적지 마세요"라고
써 두는 것으로는 안 된다 — 다음 사람은 그 주석을 보기 전에 키를 하나 추가한다.
"""

import json
from pathlib import Path

import pytest

from app.core.feature_flags import (
    DB_OWNED,
    FILE_OWNED,
    FLAG_REGISTRY,
    OWNER_DB,
    OWNER_FILE,
    load_feature_flags,
    reset_cache,
)
from app.settings.registry import REGISTRY as SETTINGS_REGISTRY

pytestmark = pytest.mark.unit

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FLAGS_FILE = PROJECT_ROOT / "config" / "feature-flags.json"


def _file_keys() -> set[str]:
    data = json.loads(FLAGS_FILE.read_text(encoding="utf-8"))
    return {k for k in data if not k.startswith("_")}


def test_no_flag_is_owned_by_both_the_file_and_the_database():
    """**이 파일의 핵심 단언.** 한 플래그의 정본은 한 곳뿐이어야 한다."""
    overlap = set(FILE_OWNED) & set(SETTINGS_REGISTRY)
    assert not overlap, (
        f"이 키들이 파일과 DB 양쪽에 정본으로 있다: {sorted(overlap)}. "
        "한쪽에서 바꿔도 효과가 없는 스위치가 생긴다 — 소유자를 하나로 정하라."
    )


def test_db_owned_flags_really_live_in_the_settings_registry():
    """DB 소유라고 선언했는데 정작 설정 레지스트리에 없으면, 아무 데서도 바꿀 수 없다."""
    for name in DB_OWNED:
        assert name in SETTINGS_REGISTRY, (
            f"{name} 은 DB 소유라고 선언됐는데 app/settings/registry.py 에 없다"
        )


def test_the_config_file_only_contains_file_owned_keys():
    """파일에 DB 소유 키가 남아 있으면 운영자가 그것을 고치고 효과를 기대한다."""
    stray = _file_keys() - set(FILE_OWNED)
    assert not stray, (
        f"config/feature-flags.json 에 파일 소유가 아닌 키가 있다: {sorted(stray)}"
    )


def test_every_file_owned_flag_is_present_in_the_config_file():
    """반대 방향 — 레지스트리에만 있고 파일엔 없으면 운영자가 그 스위치의 존재를 모른다."""
    missing = set(FILE_OWNED) - _file_keys()
    assert not missing, (
        f"레지스트리에는 있는데 config/feature-flags.json 에 없는 플래그: {sorted(missing)}"
    )


def test_load_feature_flags_returns_exactly_the_file_owned_keys(tmp_path):
    reset_cache()
    (tmp_path / "feature-flags.json").write_text(
        json.dumps({"_comment": "x", "board_enabled": False}), encoding="utf-8"
    )
    flags = load_feature_flags(tmp_path)
    assert set(flags) == set(FILE_OWNED)
    assert flags["board_enabled"] is False


def test_a_db_owned_key_written_into_the_file_is_ignored(tmp_path):
    """돌려주면 부르는 쪽이 진짜라고 믿는다 — 그 지점이 split-brain 이 다시 열리는 자리다."""
    reset_cache()
    (tmp_path / "feature-flags.json").write_text(
        json.dumps({"maintenance_mode": True, "board_enabled": True}), encoding="utf-8"
    )
    flags = load_feature_flags(tmp_path)
    assert "maintenance_mode" not in flags


def test_registry_owners_are_only_the_two_known_values():
    for name, spec in FLAG_REGISTRY.items():
        assert spec.owner in (OWNER_FILE, OWNER_DB), f"{name}: 알 수 없는 소유자 {spec.owner}"


# ── 캐시 ──────────────────────────────────────────────────────────────────────


def test_a_missing_file_falls_back_to_defaults(tmp_path):
    reset_cache()
    flags = load_feature_flags(tmp_path / "does-not-exist")
    assert flags["board_enabled"] is True


def test_a_broken_file_falls_back_to_defaults_instead_of_crashing(tmp_path):
    """플래그 파일 하나가 앱 전체를 500 으로 만들 권한을 가져선 안 된다."""
    reset_cache()
    (tmp_path / "feature-flags.json").write_text("{ 깨진 JSON", encoding="utf-8")
    flags = load_feature_flags(tmp_path)
    assert flags["board_enabled"] is True


def test_editing_the_file_takes_effect_on_the_next_call(tmp_path):
    """캐시가 프로세스 수명 동안 고정되면 '껐는데 안 꺼진다'가 된다.

    assets.py 가 정확히 그 실수로 한 번 데었다(지문을 캐시했더니 파일을 바꿔도 옛 주소가
    계속 나갔다). 여기서 같은 실수를 하지 않았음을 확인한다.
    """
    reset_cache()
    path = tmp_path / "feature-flags.json"
    path.write_text(json.dumps({"games_enabled": True}), encoding="utf-8")
    assert load_feature_flags(tmp_path)["games_enabled"] is True

    path.write_text(json.dumps({"games_enabled": False}), encoding="utf-8")
    # mtime 해상도가 거칠어도 크기가 달라지므로 캐시 키가 바뀐다. 둘 다 같을 수 있는
    # 경우를 없애기 위해 값 길이가 다른 값(True/False)을 골랐다.
    assert load_feature_flags(tmp_path)["games_enabled"] is False


def test_the_returned_dict_is_a_copy(tmp_path):
    """부르는 쪽이 결과를 고쳐도 캐시가 오염되면 안 된다(§2-7 불변성)."""
    reset_cache()
    (tmp_path / "feature-flags.json").write_text(
        json.dumps({"games_enabled": True}), encoding="utf-8"
    )
    first = load_feature_flags(tmp_path)
    first["games_enabled"] = "오염"
    assert load_feature_flags(tmp_path)["games_enabled"] is True
