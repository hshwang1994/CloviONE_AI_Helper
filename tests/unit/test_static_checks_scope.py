"""static_checks.sh 의 일상/전량 분기가 소스에 실제로 있는가.

qa-contract-change: --scope dev 는 번들 신선도와 git fsck 를 건너뛰고, 기본은 full 이다.
이 시험은 스크립트를 실행하지 않는다 — 전량 게이트를 열지 않기 위해서다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "static_checks.sh"


def test_default_scope_is_full_and_dev_is_opt_in():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "SCOPE=full" in text
    assert "--scope" in text
    assert "STATIC_CHECKS_DEV_OK" in text
    assert "STATIC_CHECKS_OK" in text
    assert "python scripts/verify.py" in text


def test_dev_skips_bundle_fresh_and_git_fsck():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'skip "번들 신선도"' in text
    assert 'skip "Repository hygiene (git fsck)"' in text
    assert 'skip "coverage --stage plan"' in text
    assert 'skip "시험 강도"' in text


def test_final_verify_uses_chunked_regression_not_single_pytest():
    verify = SCRIPT.parent / "final_verify.sh"
    text = verify.read_text(encoding="utf-8")
    assert "run_full_regression.sh" in text
    assert "static_checks.sh --scope full" in text
    assert 'step "백엔드 스위트" bash scripts/run_full_regression.sh' in text
    assert 'step "백엔드 스위트" "$PY" -m pytest tests/' not in text


def test_harness_mode_does_not_pass_base_url_argv():
    src = Path(__file__).resolve().parents[2] / "scripts" / "ui_qa" / "local_capture.py"
    text = src.read_text(encoding="utf-8")
    assert 'sys.argv = [name + ".py", *passthrough, *rest]' in text
    assert "UI_QA_BASE_URL" in text
    assert 'cap_mod.DEFAULT_BASE_URL = base' in text


def test_stage_static_update_closes_stdin():
    src = Path(__file__).resolve().parents[2] / "tests" / "regression" / "test_stage_static_update.py"
    text = src.read_text(encoding="utf-8")
    assert text.count("stdin=subprocess.DEVNULL") >= 4
