"""타이포 리터럴 재유입 방지 검사 (PA-RC-0001 acceptance_criteria 5).

`scripts/check_typography_literals.py`가 실제 `frontend/src`가 아니라 **격리된 임시
디렉터리**를 보게 해서 시험한다 — 진짜 소스를 건드리지 않는다.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

pytestmark = pytest.mark.unit

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "check_typography_literals.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_typography_literals", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_real_repository_currently_passes():
    """진짜 저장소가 지금 이 검사를 통과하는지 직접 확인한다(EXEMPT 목록이 실제 소스와
    맞는지의 최종 근거) — 다른 시험들은 격리된 디렉터리만 쓰므로 이 확인이 유일하게 실물을
    본다."""
    mod = _load()
    assert mod.main() == 0, "실제 frontend/src가 검증되지 않은 새 타이포 리터럴을 갖고 있다"


def test_token_reference_passes(tmp_path):
    mod = _load()
    (tmp_path / "Ok.jsx").write_text(
        'const x = <Box sx={{ fontSize: FONT_SIZE.body }} />;\n', encoding="utf-8",
    )
    assert mod.main(tmp_path) == 0


def test_ternary_of_tokens_passes(tmp_path):
    mod = _load()
    (tmp_path / "Ok.jsx").write_text(
        'const x = <Box sx={{ fontSize: compact ? FONT_SIZE.bodySm : FONT_SIZE.body }} />;\n',
        encoding="utf-8",
    )
    assert mod.main(tmp_path) == 0


def test_a_brand_new_unjustified_literal_is_caught():
    """🔴 revert-to-verify — EXEMPT에 없는 새 값은 반드시 걸린다."""
    mod = _load()
    tmp_path = pathlib.Path(__file__).resolve().parent / "_typography_scan_fixture_tmp"
    tmp_path.mkdir(exist_ok=True)
    try:
        (tmp_path / "New.jsx").write_text(
            'const x = <Box sx={{ fontSize: "13.37px" }} />;\n', encoding="utf-8",
        )
        assert mod.main(tmp_path) == 1, "EXEMPT 목록에 없는 새 fontSize 리터럴을 놓쳤다"
    finally:
        (tmp_path / "New.jsx").unlink()
        tmp_path.rmdir()


def test_a_new_fontweight_literal_is_caught(tmp_path):
    """fontWeight는 이미 전량 토큰화돼 있으므로 0건이 아니면 무조건 실패해야 한다."""
    mod = _load()
    (tmp_path / "New.jsx").write_text(
        'const x = <Box sx={{ fontWeight: 650 }} />;\n', encoding="utf-8",
    )
    assert mod.main(tmp_path) == 1


def test_jsdoc_comment_mentioning_a_named_constant_is_not_flagged(tmp_path):
    """오탐 회귀 — BrandLogo.jsx의 JSDoc 설명문(`* ... fontSize: BRAND_UNIT ...`)이 이 검사
    초판에서 코드로 오판돼 걸렸었다. 주석 안 언급은 코드가 아니다."""
    mod = _load()
    (tmp_path / "Documented.jsx").write_text(
        "/**\n"
        " * 정렬: 바깥 상자에 `fontSize: BRAND_UNIT` 을 한 번 주고 안쪽은 전부 em 이다.\n"
        " */\n"
        "const x = <Box sx={{ fontSize: BRAND_UNIT }} />;\n",
        encoding="utf-8",
    )
    assert mod.main(tmp_path) == 0, "JSDoc 주석 안의 언급을 코드로 오판했다"


def test_clamp_responsive_formula_is_not_flagged(tmp_path):
    """`clamp(...)`는 고정 스텝이 아니라 반응형 공식이라 이 검사의 대상이 아니다. 내부에
    쉼표가 있어 RX_FS가 뒷부분을 잘라 캡처해도(`"clamp(1.25rem`) 접두사로 안전히 판별된다."""
    mod = _load()
    (tmp_path / "Fluid.jsx").write_text(
        'const x = <Typography sx={{ fontSize: "clamp(1.25rem, 1rem + .8vw, 1.75rem)" }} />;\n',
        encoding="utf-8",
    )
    assert mod.main(tmp_path) == 0
