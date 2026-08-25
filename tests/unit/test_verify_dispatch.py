"""표적 검증 진입점이 전량을 몰래 열지 않는가.

qa-contract-change: 일상 개발은 변경 파일에 매핑된 시험만 돌리고, --full 은 캡처/Pilot 을
부르지 않는다. 매핑이 없으면 시험을 지어내지 않는다.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.verify import (
    RUNNER_MISSING, importing_tests, map_pytest, map_selftests, map_vitest,
    plan_dev, plan_failed, plan_full, vitest_runner, vitest_step,
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


# ── 표적 실행기 (P-48 · D-315) ───────────────────────────────────────────────
#
# 🔴 실제로 막힌 자리다. `["npx", "vitest", …]` 를 셸 없이 부르면 윈도우에서 `[WinError 2]`
# 가 난다 — PATH 에 있는 것은 `npx.CMD` 인데 `CreateProcess` 는 PATHEXT 를 안 붙인다.
# 그래서 이 저장소의 표적 vitest 단계는 개발 머신에서 한 번도 안 떴고, 회차마다 같은
# 명령을 손으로 돌렸다. 아래 셋이 그 자리를 지킨다: 실행기를 이름으로 해석하는가 ·
# 못 찾으면 **전량으로 갈아타지 않고** 그 단계만 실패하는가 · 전량이 표적 실패 기록을
# 덮지 않는가.


def test_the_local_vitest_binary_is_preferred_over_npx(tmp_path):
    binary = "vitest.cmd" if os.name == "nt" else "vitest"
    _touch(tmp_path, f"frontend/node_modules/.bin/{binary}")
    runner = vitest_runner(tmp_path)
    assert runner is not None
    assert runner[0].endswith(binary), runner
    assert "npx" not in runner[0].lower(), "로컬 설치가 있는데 npx 를 거친다"


def test_the_resolved_runner_is_a_real_file_not_a_bare_name(tmp_path):
    """이름 그대로 넘기면 윈도우에서 안 뜬다 — 해석된 **경로**여야 한다."""
    binary = "vitest.cmd" if os.name == "nt" else "vitest"
    _touch(tmp_path, f"frontend/node_modules/.bin/{binary}")
    runner = vitest_runner(tmp_path)
    assert Path(runner[0]).is_file(), runner


def test_a_missing_runner_fails_that_step_and_never_widens_to_full(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.verify.shutil.which", lambda name: None)
    step = vitest_step("vitest 표적", ["src/a.test.jsx"], root=tmp_path)
    assert step.missing_runner, "실행기가 없는데 단계가 그냥 만들어졌다"
    assert step.argv == [], f"실행기가 없는데 명령이 있다: {step.argv}"
    assert "npm test" not in (step.missing_runner or ""), "전량으로 갈아타라고 안내한다"


def test_a_missing_runner_reports_runner_missing(tmp_path, monkeypatch, capsys):
    from scripts.verify import Plan, run_plan

    monkeypatch.setattr("scripts.verify.shutil.which", lambda name: None)
    plan = Plan(kind="TARGETED", title="t", steps=[vitest_step("vitest 표적", [], root=tmp_path)])
    assert run_plan(plan, root=tmp_path) == 1
    out = capsys.readouterr().out
    assert RUNNER_MISSING in out, out
    assert "TARGETED_FAILED" in out, out


def test_a_full_vitest_run_does_not_overwrite_the_targeted_failure_record(tmp_path):
    """전량은 파일 목록이 없다. 그것을 「직전 실패」로 적으면 `--failed` 가 전량이 된다."""
    from scripts.verify import record_vitest_failures

    record_vitest_failures(tmp_path, [])
    assert not (tmp_path / "dist" / "qa" / "last-vitest-failed.json").exists()
    record_vitest_failures(tmp_path, ["src/a.test.jsx"])
    assert (tmp_path / "dist" / "qa" / "last-vitest-failed.json").is_file()


# ── import 를 거꾸로 따라가는 매핑 (D-315) ──────────────────────────────────
#
# 이 저장소의 시험은 **계약 이름**으로 불린다(`ticket-share-scope.test.jsx`). 파일 줄기로만
# 맞추면 화면을 고칠 때 표적이 한 건도 안 잡히고, 그러면 사람이 `--full` 로 간다 — 이
# 스크립트가 막으려던 바로 그 일이다. 그래서 import 를 되짚되, 걸리는 수가 상한을 넘으면
# **안 고른다**(그건 표적이 아니라 전량이다).


def test_a_contract_named_test_is_found_through_its_import(tmp_path):
    _touch(tmp_path, "frontend/src/screens/MyTickets.jsx")
    (tmp_path / "frontend/src/screens/share-scope.test.jsx").write_text(
        'import { TicketShareScope } from "./MyTickets.jsx";\n', encoding="utf-8")
    picked, notes = importing_tests(["frontend/src/screens/MyTickets.jsx"], tmp_path)
    assert picked == ["frontend/src/screens/share-scope.test.jsx"], (picked, notes)


def test_one_hop_through_a_screen_is_followed(tmp_path):
    """`document-views.js` ← `Trash.jsx` ← `trash-*.test.jsx` 가 실제로 그 모양이다."""
    _touch(tmp_path, "frontend/src/screens/document-views.js")
    (tmp_path / "frontend/src/screens/Trash.jsx").write_text(
        'import { invalidateDocumentViews } from "./document-views.js";\n', encoding="utf-8")
    (tmp_path / "frontend/src/screens/trash-invalidation.test.jsx").write_text(
        'import { Trash } from "./Trash.jsx";\n', encoding="utf-8")
    picked, _ = importing_tests(["frontend/src/screens/document-views.js"], tmp_path)
    assert picked == ["frontend/src/screens/trash-invalidation.test.jsx"], picked


def test_a_widely_imported_part_is_reported_not_selected(tmp_path):
    """`ui/kit.jsx` 는 시험 169개가 들여온다. 그것을 고르면 표적이 전량이 된다."""
    from scripts.verify import IMPORTER_CAP

    _touch(tmp_path, "frontend/src/ui/kit.jsx")
    for i in range(IMPORTER_CAP + 3):
        (tmp_path / f"frontend/src/ui/part{i}.test.jsx").write_text(
            'import { Card } from "./kit.jsx";\n', encoding="utf-8")
    picked, notes = importing_tests(["frontend/src/ui/kit.jsx"], tmp_path)
    assert picked == [], picked
    assert notes and "안 고른다" in notes[0], notes


def test_a_shared_component_without_a_colocated_test_does_not_select_the_full_suite(tmp_path):
    """공용 부품을 고쳤는데 같은 줄기 시험이 없다 — 그때 전량 vitest 를 고르면 안 된다."""
    _touch(tmp_path, "scripts/static_checks.sh")
    _touch(tmp_path, "frontend/src/ui/kit.jsx")
    plan = plan_dev(["frontend/src/ui/kit.jsx"], root=tmp_path, py="python", bash="bash")
    blob = " ".join(" ".join(step.argv) for step in plan.steps)
    assert "vitest" not in blob, blob
    assert any("전량으로 대신 돌리지 않는다" in note for note in plan.notes), plan.notes
