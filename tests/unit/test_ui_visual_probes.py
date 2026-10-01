"""시각 규율 프로브의 자기검증 (F7 · D-553).

`scripts/ui_qa/visual_probes.py` 의 프로브(카드 안 카드 · 보라 면적 · 첫 화면 데이터)를 헤드리스 브라우저에서 맞는 견본 ·
틀린 견본(`scripts/ui_qa/fixtures/visual/*.html`)에 돌린다. 맞는 견본은 하나도 걸리면 안 되고 표본 수(`checked`)가 0 이면 안
되며, 틀린 견본은 프로브마다 정해진 사유로 걸려야 한다. 브라우저가 없는 환경에서는 건너뛴다(실행되지 않은 것이지 통과가 아니다).
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location("visual_probes", ROOT / "scripts" / "ui_qa" / "visual_probes.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def measured():
    sync_api = pytest.importorskip("playwright.sync_api")
    mod = _load()
    results = {}
    with sync_api.sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=True)
        except Exception as exc:  # noqa: BLE001 - 브라우저 바이너리가 없는 환경
            pytest.skip(f"헤드리스 브라우저를 띄우지 못했다: {exc}")
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            for kind in ("good", "bad"):
                page.set_content(mod.fixture_html(kind), wait_until="load")
                results[kind] = page.evaluate(mod.VISUAL_JS, {**mod.VISUAL_CONTRACT, "scope": None})
        finally:
            browser.close()
    return mod, results


def test_selftest_verdict_is_clean(measured):
    mod, results = measured
    assert mod.selftest_verdict(results["good"], results["bad"]) == []


def test_good_sample_is_measured_and_clean(measured):
    mod, results = measured
    good = results["good"]
    for name in mod.VISUAL_CHECKS:
        assert good[name]["checked"] > 0, f"{name} 표본 0 은 통과가 아니라 미실행이다"
        assert good[name]["failed"] == 0, good[name]["bad"]
    # 선택 행 · 주 동작 단추의 보라는 면적에 세지 않는다.
    assert good["brand_pct"] < mod.VISUAL_CONTRACT["brandTotalPct"]
    assert good["visual_report"]["surface_count"] >= 2


def test_bad_sample_fails_for_the_stated_reason(measured):
    mod, results = measured
    bad = results["bad"]
    for name, want in mod.SELFTEST_EXPECT_BAD.items():
        assert bad[name]["failed"] >= want, (name, bad[name])
    assert bad["brand_pct"] > 10
    assert bad["first_data_top"] > mod.VISUAL_CONTRACT["firstDataTop"]["short"]
    report = bad["visual_report"]
    assert report["status_colors"] == ["error", "info", "success", "warning"]
    assert report["empty_plate"] >= 1


def test_tables_agree():
    mod = _load()
    assert set(mod.SELFTEST_EXPECT_BAD) == set(mod.VISUAL_CHECKS)
    assert set(mod.SELFTEST_EXPECT_REASONS) == set(mod.VISUAL_CHECKS)
    assert (ROOT / "scripts" / "ui_qa" / "fixtures" / "visual" / "good.html").is_file()
    assert (ROOT / "scripts" / "ui_qa" / "fixtures" / "visual" / "bad.html").is_file()
