"""버튼 위계 회귀 방지 검사 (PA-RC-0023 acceptance_criteria 3, 7).

`scripts/check_button_hierarchy.py`가 실제 `frontend/src/screens/registry`가 아니라
**격리된 임시 디렉터리**를 보게 해서 시험한다 — 진짜 소스를 건드리지 않는다
(`test_typography_literals_scan.py`와 같은 관용).
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

pytestmark = pytest.mark.unit

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "check_button_hierarchy.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_button_hierarchy", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_real_registry_currently_passes():
    """진짜 저장소가 지금 이 검사를 통과하는지 직접 확인한다 — 다른 시험들은 격리된
    디렉터리만 쓰므로 이 확인이 유일하게 실물을 본다."""
    mod = _load()
    assert mod.main() == 0, "실제 registry/*.js가 버튼 위계 규범을 어기는 새 항목을 갖고 있다"


def test_danger_labeled_delete_passes(tmp_path):
    mod = _load()
    (tmp_path / "ok.js").write_text(
        '{ label: "삭제", variant: "danger", method: "DELETE" },\n', encoding="utf-8",
    )
    assert mod.main(tmp_path) == 0


def test_primary_and_variant_paired_passes(tmp_path):
    mod = _load()
    (tmp_path / "ok.js").write_text(
        '{ label: "+ 백업 실행", variant: "primary", primary: true, path: () => "/api/admin/backups" },\n',
        encoding="utf-8",
    )
    assert mod.main(tmp_path) == 0


def test_a_destructive_action_styled_primary_is_caught(tmp_path):
    """🔴 revert-to-verify — 이 실측(2026-08-16)이 실제로 잡았던 모양 그대로 재현한다:
    activeToggle()의 '활성화'가 한때 이 형태였다(그때는 라벨이 달랐지만, 파괴적 라벨이
    실수로 primary가 되는 것과 같은 종류의 결함이다)."""
    mod = _load()
    (tmp_path / "new.js").write_text(
        '{ label: "삭제", variant: "primary", method: "DELETE" },\n', encoding="utf-8",
    )
    assert mod.main(tmp_path) == 1, "파괴적 라벨이 primary인 새 항목을 놓쳤다"


def test_each_destructive_label_individually_is_caught(tmp_path):
    """DESTRUCTIVE_LABELS 목록의 여덟 라벨 전부가 실제로 걸리는지(목록에 넣기만 하고 정규식이
    한둘만 매칭하는 실수를 방지) 하나씩 확인한다."""
    mod = _load()
    for i, label in enumerate(_load().DESTRUCTIVE_LABELS):
        f = tmp_path / f"case{i}.js"
        f.write_text(f'{{ label: "{label}", variant: "primary" }},\n', encoding="utf-8")
    assert mod.main(tmp_path) == 1


def test_primary_true_without_variant_is_caught(tmp_path):
    """🔴 revert-to-verify — notion-mapping의 '자동 동기화'가 실제로 이 모양이었다:
    primary:true만 있고 variant:"primary"가 없어 평소 툴바에서는 외곽선으로 보였다."""
    mod = _load()
    (tmp_path / "new.js").write_text(
        '{ label: "자동 동기화", primary: true, path: () => "/api/x" },\n', encoding="utf-8",
    )
    assert mod.main(tmp_path) == 1, "primary:true인데 variant:\"primary\"가 짝지어 있지 않은 항목을 놓쳤다"


def test_non_destructive_primary_is_fine(tmp_path):
    """'재시도'처럼 파괴적이지 않은 동작은 primary여도 정당하다(잡을 이유가 없다)."""
    mod = _load()
    (tmp_path / "ok.js").write_text(
        '{ label: "재시도", variant: "primary", roles: OPS_ROLES },\n', encoding="utf-8",
    )
    assert mod.main(tmp_path) == 0


def test_comment_mentioning_a_destructive_label_is_not_flagged(tmp_path):
    """오탐 회귀 — 주석 안에서 '삭제'/'primary'를 함께 설명하는 문장을 코드로 오판하지 않는다."""
    mod = _load()
    (tmp_path / "documented.js").write_text(
        "// '삭제' 액션은 절대 variant: \"primary\"로 두면 안 된다.\n"
        '{ label: "삭제", variant: "danger" },\n',
        encoding="utf-8",
    )
    assert mod.main(tmp_path) == 0, "주석 안의 언급을 코드로 오판했다"


def test_test_files_are_not_scanned(tmp_path):
    """`.test.js` 안의 픽스처(일부러 나쁜 값을 넣어 검사 자체를 시험하는 코드)는 대상이
    아니다 — check_typography_literals.py와 같은 관용."""
    mod = _load()
    (tmp_path / "fixture.test.js").write_text(
        '{ label: "삭제", variant: "primary" },\n', encoding="utf-8",
    )
    assert mod.main(tmp_path) == 0
