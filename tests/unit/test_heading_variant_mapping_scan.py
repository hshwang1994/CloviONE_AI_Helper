"""Heading 시각/의미 분리 재유입 방지 검사 (PA-RC-0012 acceptance_criteria 2, 5).

`scripts/check_heading_variant_mapping.py`가 실제 `frontend/src`가 아니라 **격리된 임시
디렉터리**를 보게 해서 시험한다(`test_typography_literals_scan.py`와 같은 관용).
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

pytestmark = pytest.mark.unit

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "check_heading_variant_mapping.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_heading_variant_mapping", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_real_source_tree_currently_passes():
    """진짜 저장소가 지금 이 검사를 통과하는지 직접 확인한다 — 다른 시험들은 격리된
    디렉터리만 쓰므로 이 확인이 유일하게 실물을 본다."""
    mod = _load()
    assert mod.main() == 0, "frontend/src가 heading variant/component 규범을 어기는 새 항목을 갖고 있다"


def test_variant_h6_with_component_passes(tmp_path):
    mod = _load()
    (tmp_path / "ok.jsx").write_text(
        '<Typography variant="h6" component="h2">제목</Typography>\n', encoding="utf-8",
    )
    assert mod.main(tmp_path) == 0


def test_variant_h1_and_h2_are_not_checked(tmp_path):
    """h1/h2는 component= 없이 써도 기본 매핑이 이미 h1/h2라 이 검사의 대상이 아니다."""
    mod = _load()
    (tmp_path / "ok.jsx").write_text(
        '<Typography variant="h1">제목</Typography>\n'
        '<Typography variant="h2">부제목</Typography>\n',
        encoding="utf-8",
    )
    assert mod.main(tmp_path) == 0


def test_variant_h6_without_component_is_caught(tmp_path):
    """revert-to-verify — PA-RC-0012가 실제로 잡은 결함 그대로 재현한다: LlmConsole.jsx 등
    5개 화면이 이 모양이었다."""
    mod = _load()
    (tmp_path / "new.jsx").write_text(
        '<Typography variant="h6">지금 적용 중인 값</Typography>\n', encoding="utf-8",
    )
    assert mod.main(tmp_path) == 1, "component= 없는 variant=\"h6\"를 놓쳤다"


@pytest.mark.parametrize("level", ["h3", "h4", "h5", "h6", "subtitle1", "subtitle2"])
def test_each_checked_level_individually_is_caught(tmp_path, level):
    mod = _load()
    f = tmp_path / f"case_{level}.jsx"
    f.write_text(f'<Typography variant="{level}">제목</Typography>\n', encoding="utf-8")
    assert mod.main(tmp_path) == 1


def test_subtitle1_without_component_is_caught(tmp_path):
    """🔴 revert-to-verify — Offboarding.jsx가 실제로 이 모양이었다: MUI 기본 매핑에서
    subtitle1도 <h6>로 떨어진다는 걸 놓쳐서, 처음 짠 버전(h3~h6만 검사)은 이걸 못 잡았고
    heading-order.test.jsx(렌더 회귀)가 대신 잡았다. 그 뒤 여기 추가했다."""
    mod = _load()
    (tmp_path / "new.jsx").write_text(
        '<Typography variant="subtitle1">보유 티켓 3건</Typography>\n', encoding="utf-8",
    )
    assert mod.main(tmp_path) == 1, "component= 없는 variant=\"subtitle1\"을 놓쳤다"


def test_comment_mentioning_variant_h6_is_not_flagged(tmp_path):
    """오탐 회귀 — 주석 안에서 variant="h6"를 언급하는 문장을 코드로 오판하지 않는다."""
    mod = _load()
    (tmp_path / "documented.jsx").write_text(
        '// variant="h6"는 component=를 반드시 같이 써야 한다.\n'
        '<Typography variant="h6" component="h2">제목</Typography>\n',
        encoding="utf-8",
    )
    assert mod.main(tmp_path) == 0, "주석 안의 언급을 코드로 오판했다"


def test_test_files_are_not_scanned(tmp_path):
    """`.test.jsx` 안의 픽스처(일부러 나쁜 값을 넣어 검사 자체를 시험하는 코드)는 대상이
    아니다 — check_typography_literals.py와 같은 관용."""
    mod = _load()
    (tmp_path / "fixture.test.jsx").write_text(
        '<Typography variant="h6">제목</Typography>\n', encoding="utf-8",
    )
    assert mod.main(tmp_path) == 0
