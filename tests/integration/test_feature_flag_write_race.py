"""기능 플래그 동시 저장 — 서로 다른 두 스위치를 같이 켜면 둘 다 켜진다.

## 무엇이 터졌나 (2026-09-06 실측)

`_write_flag` 는 키 하나를 바꾸려고 파일 **전체**를 읽어 딕셔너리에 얹고 전체를 다시 쓴다.
읽기와 쓰기 사이에 잠금이 없어서, `board_enabled` 와 `chat_enabled` 를 동시에 켜면 나중에
`os.replace` 한 쪽의 스냅숏이 상대의 변경을 통째로 덮었다 — 단위가 키가 아니라 파일이다.
6회 중 6회 한쪽이 사라졌고, 그중 5회는 **응답이 200 이고 `{"value": true}` 라고 말했다**.
쓰기 직후 파일을 다시 읽어 그 값을 돌려줬기 때문에 남의 파일을 자기 성공으로 실어 보냈다.

기능 플래그는 화면 하나를 통째로 켜고 끄는 스위치다(`board_enabled` 를 끄면 모든 사용자의
사이드바에서 자유게시판이 사라진다). 장애 대응 중에 「켰습니다」를 받고도 꺼진 채 남는
것이 가장 위험한 실패다.

## 이 파일이 못박는 것

유실 0, 거짓 200 이 0, 그리고 **응답이 말한 값이 파일에 실제로 있다.** 잠금이 없으면
첫 시험이 거의 매번 빨간불이 된다(실측 6/6).
"""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

# 파일 소유 플래그 전부. 서로 **다른** 키를 동시에 쓰는 것이 이 결함의 모양이다 —
# 같은 키를 쓰면 마지막이 이기는 것이 정상이라 아무것도 증명하지 못한다.
# 목록은 레지스트리에서 뽑는다 - AI 기능 셋은 DB 소유로 옮겼다(D-507).
from app.core.feature_flags import FILE_OWNED  # noqa: E402

FLAGS = tuple(FILE_OWNED)
assert len(FLAGS) >= 5, FLAGS


@pytest.fixture()
def flags_dir(tmp_path: Path):
    """시험 전용 설정 디렉터리. 저장소의 `config/` 를 건드리지 않는다."""
    from app.core.feature_flags import FLAGS_FILENAME, reset_cache

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / FLAGS_FILENAME).write_text(
        json.dumps({name: False for name in FLAGS}, indent=2) + "\n", encoding="utf-8"
    )
    reset_cache()
    yield config_dir
    reset_cache()


def _on_disk(config_dir: Path) -> dict:
    from app.core.feature_flags import FLAGS_FILENAME

    return json.loads((config_dir / FLAGS_FILENAME).read_text(encoding="utf-8"))


def test_concurrent_writes_to_different_flags_lose_nothing(flags_dir, tmp_path):
    from app.admin.feature_flags import _write_flag
    from app.core.feature_flags import flags_path

    path = flags_path(flags_dir)
    lock_dir = tmp_path / "data"

    def turn_on(name: str):
        return name, _write_flag(path, name, True, default=False, lock_dir=lock_dir)

    with ThreadPoolExecutor(max_workers=len(FLAGS)) as pool:
        results = dict(pool.map(turn_on, FLAGS))

    saved = _on_disk(flags_dir)
    lost = [name for name in FLAGS if saved.get(name) is not True]
    assert lost == [], f"동시에 켠 플래그가 파일에서 사라졌다: {lost}"
    # 돌려준 값이 파일과 같다 — 「켰습니다」가 거짓말이 아니다.
    for name in FLAGS:
        assert results[name] == (False, True), f"{name} 의 before/after 가 틀렸다: {results[name]}"


def test_concurrent_writes_keep_the_comment_field_and_unknown_keys(flags_dir, tmp_path):
    """반례 축 — 잠금을 넣느라 「다른 키는 보존한다」가 깨지지 않았는지 본다."""
    from app.admin.feature_flags import _write_flag
    from app.core.feature_flags import FLAGS_FILENAME, flags_path

    data = _on_disk(flags_dir)
    data["_comment"] = "손으로 적어 둔 설명"
    data["retired_flag"] = True
    (flags_dir / FLAGS_FILENAME).write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )

    path = flags_path(flags_dir)
    lock_dir = tmp_path / "data"
    with ThreadPoolExecutor(max_workers=len(FLAGS)) as pool:
        list(pool.map(lambda n: _write_flag(path, n, True, default=False, lock_dir=lock_dir), FLAGS))

    saved = _on_disk(flags_dir)
    assert saved["_comment"] == "손으로 적어 둔 설명"
    assert saved["retired_flag"] is True
    assert all(saved[name] is True for name in FLAGS)


def test_single_write_reports_the_value_it_wrote(flags_dir, tmp_path):
    """반례 축 — 평범한 한 번의 저장이 before/after 를 정확히 말한다."""
    from app.admin.feature_flags import _write_flag
    from app.core.feature_flags import flags_path

    path = flags_path(flags_dir)
    lock_dir = tmp_path / "data"

    assert _write_flag(path, "board_enabled", True, default=False, lock_dir=lock_dir) == (
        False, True,
    )
    assert _write_flag(path, "board_enabled", False, default=False, lock_dir=lock_dir) == (
        True, False,
    )
    assert _on_disk(flags_dir)["board_enabled"] is False


def test_non_boolean_value_in_the_file_reads_as_the_registry_default(flags_dir, tmp_path):
    """따옴표 붙은 `"false"` 는 값이 없는 것으로 본다(CORE-10 과 같은 규칙).

    이것이 어긋나면 응답과 감사 로그의 `before` 가 파일과 다른 말을 한다.
    """
    from app.admin.feature_flags import _write_flag
    from app.core.feature_flags import FLAGS_FILENAME, flags_path

    data = _on_disk(flags_dir)
    data["board_enabled"] = "false"
    (flags_dir / FLAGS_FILENAME).write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )

    before, after = _write_flag(
        flags_path(flags_dir), "board_enabled", True, default=True, lock_dir=tmp_path / "data"
    )
    assert (before, after) == (True, True)
