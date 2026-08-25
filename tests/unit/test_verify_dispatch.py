"""표적 검증 진입점이 전량을 몰래 열지 않는가.

qa-contract-change: 일상 개발은 변경 파일에 매핑된 시험만 돌리고, --full 은 캡처/Pilot 을
부르지 않는다. 매핑이 없으면 시험을 지어내지 않는다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.verify import (
    map_pytest, map_selftests, map_vitest, needs_coverage_plan, needs_test_strength,
    plan_dev, plan_failed, plan_full,
)

pytestmark = pytest.mark.unit


def _touch(root: Path, rel: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x\n", encoding="utf-8")


def test_generic_service_stem_uses_parent_name(tmp_path):
    _touch(tmp_path, "app/tickets/service.py")
    _touch(tmp_path, "tests/unit/test_tickets.py")
    _touch(tmp_path, "tests/unit/test_service.py")
    mapped = map_pytest(["app/tickets/service.py"], tmp_path)
    assert "tests/unit/test_tickets.py" in mapped
    assert "tests/unit/test_service.py" not in mapped


def test_specific_stem_maps_to_matching_test(tmp_path):
    _touch(tmp_path, "app/tickets/numbering.py")
    _touch(tmp_path, "tests/unit/test_numbering.py")
    assert map_pytest(["app/tickets/numbering.py"], tmp_path) == ["tests/unit/test_numbering.py"]


def test_does_not_invent_missing_tests(tmp_path):
    _touch(tmp_path, "app/tickets/numbering.py")
    assert map_pytest(["app/tickets/numbering.py"], tmp_path) == []


def test_test_file_maps_to_itself(tmp_path):
    _touch(tmp_path, "tests/unit/test_foo.py")
    assert map_pytest(["tests/unit/test_foo.py"], tmp_path) == ["tests/unit/test_foo.py"]


def test_vitest_colocation(tmp_path):
    _touch(tmp_path, "frontend/src/screens/MyTickets.jsx")
    _touch(tmp_path, "frontend/src/screens/MyTickets.test.jsx")
    _touch(tmp_path, "frontend/src/screens/Other.test.jsx")
    mapped = map_vitest(["frontend/src/screens/MyTickets.jsx"], tmp_path)
    assert mapped == ["frontend/src/screens/MyTickets.test.jsx"]


def test_selftest_only_when_no_pytest(tmp_path):
    checker = "scripts/check_example.py"
    _touch(tmp_path, checker)
    (tmp_path / checker).write_text("parser.add_argument('--self-test')\n", encoding="utf-8")
    assert map_selftests([checker], tmp_path, pytest_files=[]) == [[checker, "--self-test"]]
    covered = ["tests/unit/test_example_scan.py"]
    assert map_selftests([checker], tmp_path, pytest_files=covered) == []


def test_full_plan_does_not_invoke_capture_or_pilot(tmp_path):
    plan = plan_full(root=tmp_path, py="python", bash="bash")
    blob = " ".join(" ".join(step.argv) for step in plan.steps)
    assert plan.kind == "FULL"
    assert "run_full_regression.sh" in blob
    assert "static_checks.sh" in blob
    assert "--scope" in blob and "full" in blob
    assert "ui_qa.run" not in blob
    assert "local_capture" not in blob
    assert "pilot_e2e" not in blob
    assert "pilot_record" not in blob


def test_dev_plan_is_targeted_and_skips_full_regression(tmp_path):
    _touch(tmp_path, "scripts/static_checks.sh")
    plan = plan_dev(["app/tickets/numbering.py"], root=tmp_path, py="python", bash="bash")
    blob = " ".join(" ".join(step.argv) for step in plan.steps)
    assert plan.kind == "TARGETED"
    assert "--scope" in blob and "dev" in blob
    assert "run_full_regression" not in blob
    assert "ui_qa.run" not in blob
    assert any("전량 Evidence" in note for note in plan.notes)


def test_failed_plan_uses_pytest_last_failed(tmp_path):
    plan = plan_failed(root=tmp_path, py="python")
    blob = " ".join(" ".join(step.argv) for step in plan.steps)
    assert plan.kind == "TARGETED"
    assert "--lf" in blob
    assert "run_full_regression" not in blob


def test_coverage_plan_trigger():
    assert needs_coverage_plan(["docs/ui-renewal/ROUTE_COVERAGE.json"])
    assert needs_coverage_plan(["scripts/ui_qa/run.py"])
    assert not needs_coverage_plan(["app/tickets/service.py"])


def test_test_strength_trigger():
    assert needs_test_strength(["tests/unit/test_foo.py"])
    assert needs_test_strength(["frontend/src/screens/Foo.test.jsx"])
    assert not needs_test_strength(["frontend/src/screens/Foo.jsx"])
