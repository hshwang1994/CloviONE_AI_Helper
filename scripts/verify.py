"""일상 개발용 표적 검증 진입점.

전량 게이트와 같은 명령을 기본값으로 두지 않는다. 작은 변경은 관련 시험만 돌리고,
전체 회귀·캡처·Pilot 은 호출하지 않는다.

    python scripts/verify.py              # TARGETED: 변경 파일 매핑 + static --scope dev
    python scripts/verify.py --failed     # 직전 실패만 (pytest --lf, 기록된 vitest)
    python scripts/verify.py --static     # static_checks 전량 (Exit 게이트)
    python scripts/verify.py --full       # static 전량 + 백엔드 청크 회귀 + vitest 전량
                                          # 브라우저 캡처/Pilot/E2E 는 넣지 않는다

부분 실행은 전량 Evidence 가 아니다. 이 스크립트는 캡처 산출물을 쓰지 않는다.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GENERIC_STEMS = frozenset({
    "service", "main", "utils", "util", "helpers", "models", "routes",
    "router", "api", "views", "__init__", "base", "common", "helpers",
})

COVERAGE_PLAN_PREFIXES = (
    "docs/ui-renewal/",
    "scripts/check_ui_renewal_coverage.py",
    "scripts/ui_qa/",
)


@dataclass
class Step:
    name: str
    argv: list[str]
    cwd: str | None = None
    stdin_null: bool = False
    allow_exit: frozenset[int] = field(default_factory=lambda: frozenset({0}))


@dataclass
class Plan:
    kind: str  # TARGETED | FULL
    title: str
    steps: list[Step]
    notes: list[str] = field(default_factory=list)


def posix(path: str | Path) -> str:
    return str(path).replace("\\", "/").lstrip("./")


def python_exe(root: Path = ROOT) -> str:
    win = root / ".venv" / "Scripts" / "python.exe"
    unix = root / ".venv" / "bin" / "python"
    if win.is_file():
        return str(win)
    if unix.is_file():
        return str(unix)
    return sys.executable


def bash_exe() -> str:
    for name in ("bash", "bash.exe"):
        found = shutil.which(name)
        if found:
            return found
    for guess in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
    ):
        if Path(guess).is_file():
            return guess
    return "bash"


def changed_files(root: Path = ROOT) -> list[str]:
    """HEAD 대비 수정·추가(추적 안 된 것 포함). git 이 없으면 빈 목록."""
    out: list[str] = []
    seen: set[str] = set()

    def take(raw: str) -> None:
        for line in raw.splitlines():
            rel = posix(line.strip())
            if rel and rel not in seen:
                seen.add(rel)
                out.append(rel)

    try:
        diff = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=root, capture_output=True, text=True, encoding="utf-8",
            check=False,
        )
        if diff.returncode == 0:
            take(diff.stdout)
        extra = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=root, capture_output=True, text=True, encoding="utf-8",
            check=False,
        )
        if extra.returncode == 0:
            take(extra.stdout)
    except OSError:
        return []
    return out


def _add_existing(root: Path, rel: str, bucket: list[str], seen: set[str]) -> None:
    rel = posix(rel)
    if rel in seen:
        return
    if (root / rel).is_file():
        seen.add(rel)
        bucket.append(rel)


def map_pytest(rel_paths: list[str], root: Path) -> list[str]:
    """변경 경로 → 존재하는 pytest 파일. 없는 시험을 지어내지 않는다."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in rel_paths:
        rel = posix(raw)
        path = Path(rel)
        if rel.startswith("tests/") and rel.endswith(".py") and path.name.startswith("test_"):
            _add_existing(root, rel, out, seen)
            continue
        if rel.startswith("app/") and rel.endswith(".py"):
            stem = path.stem
            parent = path.parent.name
            keys = [parent] if stem in GENERIC_STEMS else [stem]
            if stem not in GENERIC_STEMS and parent and parent != "app":
                keys.append(f"{parent}_{stem}")
            for key in keys:
                for hit in root.glob(f"tests/**/test_{key}.py"):
                    _add_existing(root, hit.relative_to(root).as_posix(), out, seen)
                for hit in root.glob(f"tests/**/test_{key}_*.py"):
                    _add_existing(root, hit.relative_to(root).as_posix(), out, seen)
        if rel.startswith("scripts/") and rel.endswith(".py"):
            stem = path.stem
            name = stem[6:] if stem.startswith("check_") else stem
            if stem.startswith("verify"):
                _add_existing(root, "tests/unit/test_verify_dispatch.py", out, seen)
            candidates = [
                f"tests/unit/test_{stem}.py",
                f"tests/unit/test_{name}.py",
                f"tests/unit/test_{name}_scan.py",
                f"tests/unit/test_{stem}_scan.py",
                f"tests/regression/test_{stem}.py",
                f"tests/regression/test_{name}.py",
            ]
            if rel.startswith("scripts/ui_qa/"):
                candidates.extend([
                    f"tests/regression/test_ui_qa_{name}.py",
                    "tests/regression/test_ui_qa_harness_honesty.py",
                    "tests/regression/test_ui_qa_route_registry_completeness.py",
                ])
            for cand in candidates:
                _add_existing(root, cand, out, seen)
            for hit in root.glob(f"tests/**/test_{name}*.py"):
                _add_existing(root, hit.relative_to(root).as_posix(), out, seen)
            for hit in root.glob(f"tests/**/test_{stem}*.py"):
                _add_existing(root, hit.relative_to(root).as_posix(), out, seen)
    return out


def _is_vitest_file(name: str) -> bool:
    return ".test." in name and name.endswith((".js", ".jsx", ".ts", ".tsx"))


def map_vitest(rel_paths: list[str], root: Path) -> list[str]:
    """frontend/src 변경 → 같은 줄기 시험 파일. 캡처/E2E 를 부르지 않는다."""
    out: list[str] = []
    seen: set[str] = set()
    frontend = root / "frontend"
    for raw in rel_paths:
        rel = posix(raw)
        if not rel.startswith("frontend/"):
            continue
        path = Path(rel)
        if _is_vitest_file(path.name):
            _add_existing(root, rel, out, seen)
            continue
        if not rel.startswith("frontend/src/") or path.suffix not in {".js", ".jsx", ".ts", ".tsx"}:
            continue
        stem = path.stem
        parent = root / path.parent
        if not parent.is_dir():
            continue
        for hit in parent.glob(f"{stem}*.test.js"):
            _add_existing(root, hit.relative_to(root).as_posix(), out, seen)
        for hit in parent.glob(f"{stem}*.test.jsx"):
            _add_existing(root, hit.relative_to(root).as_posix(), out, seen)
        for hit in parent.glob(f"{stem}*.test.ts"):
            _add_existing(root, hit.relative_to(root).as_posix(), out, seen)
        for hit in parent.glob(f"{stem}*.test.tsx"):
            _add_existing(root, hit.relative_to(root).as_posix(), out, seen)
        # frontend 루트 기준 상대 경로도 허용 (파일이 frontend/ 밖에 매핑된 경우 없음)
        _ = frontend
    return out


def supports_self_test(path: Path) -> bool:
    try:
        return "--self-test" in path.read_text(encoding="utf-8")
    except OSError:
        return False


def map_selftests(rel_paths: list[str], root: Path, *, pytest_files: list[str]) -> list[list[str]]:
    """대응 pytest 가 없는 check_*.py 만 --self-test. 있는 시험을 중복 호출하지 않는다."""
    steps: list[list[str]] = []
    for raw in rel_paths:
        rel = posix(raw)
        if not rel.startswith("scripts/check_") or not rel.endswith(".py"):
            continue
        stem = Path(rel).stem
        name = stem[6:]
        covered = any(
            Path(p).stem in {f"test_{stem}", f"test_{name}", f"test_{name}_scan", f"test_{stem}_scan"}
            or Path(p).stem.startswith(f"test_{name}")
            or Path(p).stem.startswith(f"test_{stem}")
            for p in pytest_files
        )
        if covered:
            continue
        script = root / rel
        if script.is_file() and supports_self_test(script):
            steps.append([rel, "--self-test"])
    return steps


def needs_coverage_plan(rel_paths: list[str]) -> bool:
    for rel in rel_paths:
        p = posix(rel)
        if any(p.startswith(prefix) for prefix in COVERAGE_PLAN_PREFIXES):
            return True
    return False


def needs_test_strength(rel_paths: list[str]) -> bool:
    for rel in rel_paths:
        p = posix(rel)
        if p.startswith("tests/"):
            return True
        if _is_vitest_file(Path(p).name):
            return True
    return False


def _vitest_rel(files: list[str]) -> list[str]:
    out = []
    for rel in files:
        if rel.startswith("frontend/"):
            out.append(rel[len("frontend/"):])
        else:
            out.append(rel)
    return out


def plan_dev(changed: list[str], *, root: Path, py: str, bash: str) -> Plan:
    pytest_files = map_pytest(changed, root)
    vitest_files = map_vitest(changed, root)
    selftests = map_selftests(changed, root, pytest_files=pytest_files)
    steps: list[Step] = [
        Step(
            "정적 검사 (dev)",
            [bash, str(root / "scripts" / "static_checks.sh"), "--scope", "dev"],
            stdin_null=True,
        ),
    ]
    notes = [
        "TARGETED: 전량 Evidence 가 아니다.",
        "전량: python scripts/verify.py --full",
        "캡처: python -m scripts.ui_qa.local_capture --routes … 또는 python -m scripts.ui_qa.run --full",
    ]
    if pytest_files:
        steps.append(Step(
            "pytest 표적",
            [py, "-m", "pytest", *pytest_files, "-q"],
            stdin_null=True,
        ))
    else:
        notes.append("매핑된 pytest 파일이 없다.")
    if vitest_files:
        steps.append(Step(
            "vitest 표적",
            ["npx", "vitest", "run", *_vitest_rel(vitest_files)],
            cwd=str(root / "frontend"),
        ))
    else:
        notes.append("매핑된 vitest 파일이 없다.")
    for argv in selftests:
        steps.append(Step("검사기 자기검증", [py, *argv]))
    if not pytest_files and not vitest_files and not selftests:
        notes.append("관련 시험을 지어내지 않았다. 필요하면 경로를 직접 지정하라.")
    return Plan(kind="TARGETED", title="일상 표적 검증", steps=steps, notes=notes)


def plan_failed(*, root: Path, py: str) -> Plan:
    steps = [
        Step(
            "pytest 직전 실패",
            [py, "-m", "pytest", "--lf", "-q"],
            stdin_null=True,
            allow_exit=frozenset({0, 5}),
        ),
    ]
    notes = [
        "TARGETED: 직전 실패만 다시 본다. 전량 Evidence 가 아니다.",
        "pytest 종료 코드 5(수집 0건)는 다시 볼 실패가 없다는 뜻이라 통과로 친다.",
    ]
    last = read_last_vitest_failed(root)
    if last:
        steps.append(Step(
            "vitest 직전 실패",
            ["npx", "vitest", "run", *last],
            cwd=str(root / "frontend"),
        ))
    else:
        notes.append("기록된 vitest 실패 파일이 없다 (dist/qa/last-vitest-failed.json).")
    return Plan(kind="TARGETED", title="실패 범위 재검증", steps=steps, notes=notes)


def plan_static(*, root: Path, bash: str) -> Plan:
    return Plan(
        kind="FULL",
        title="정적 전량 게이트",
        steps=[Step(
            "정적 검사 (full)",
            [bash, str(root / "scripts" / "static_checks.sh"), "--scope", "full"],
            stdin_null=True,
        )],
        notes=["FULL static: 번들 신선도, git secrets, coverage plan 을 포함한다."],
    )


def plan_full(*, root: Path, py: str, bash: str) -> Plan:
    """브라우저 캡처/Pilot/E2E 는 호출하지 않는다. 전량 캡처는 run.py --full 이다."""
    return Plan(
        kind="FULL",
        title="전량 검증 (캡처 제외)",
        steps=[
            Step(
                "정적 검사 (full)",
                [bash, str(root / "scripts" / "static_checks.sh"), "--scope", "full"],
                stdin_null=True,
            ),
            Step(
                "백엔드 전량 회귀",
                [bash, str(root / "scripts" / "run_full_regression.sh")],
                stdin_null=True,
            ),
            Step(
                "프런트 전량",
                ["npx", "vitest", "run"],
                cwd=str(root / "frontend"),
            ),
        ],
        notes=[
            "FULL: 정적 + pytest 청크 + vitest 전량. 캡처/Pilot/E2E 는 이 명령에 없다.",
            "전량 캡처: python -m scripts.ui_qa.run --full --label <label>",
        ],
    )


def read_last_vitest_failed(root: Path) -> list[str]:
    path = root / "dist" / "qa" / "last-vitest-failed.json"
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    files = payload.get("testFiles") if isinstance(payload, dict) else payload
    if not isinstance(files, list):
        return []
    return [str(item) for item in files if item]


def record_vitest_failures(root: Path, result: subprocess.CompletedProcess, rel_files: list[str]) -> None:
    """표적 vitest 가 실패하면 그 파일 목록을 남겨 --failed 가 다시 쓴다."""
    if result.returncode == 0:
        return
    dest = root / "dist" / "qa"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "last-vitest-failed.json").write_text(
        json.dumps({"testFiles": rel_files}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _print_banner(plan: Plan) -> None:
    print("=" * 72, flush=True)
    print(f"{plan.kind}: {plan.title}", flush=True)
    print("=" * 72, flush=True)
    for note in plan.notes:
        print(f"  {note}", flush=True)
    print(flush=True)


def run_plan(plan: Plan, *, root: Path = ROOT, dry_run: bool = False) -> int:
    _print_banner(plan)
    if dry_run:
        for step in plan.steps:
            where = f"  (cwd {step.cwd})" if step.cwd else ""
            print(f"DRY {step.name}: {' '.join(step.argv)}{where}", flush=True)
        print(f"{plan.kind}_DRY_RUN", flush=True)
        return 0

    failed: list[str] = []
    for step in plan.steps:
        print(flush=True)
        print(f"== {step.name} ==", flush=True)
        stdin = subprocess.DEVNULL if step.stdin_null else None
        try:
            result = subprocess.run(
                step.argv,
                cwd=step.cwd or str(root),
                stdin=stdin,
            )
        except OSError as exc:
            print(f"[FAIL] {step.name}: {exc}", flush=True)
            failed.append(step.name)
            continue
        if step.name.startswith("vitest") and result.returncode != 0:
            rel = [a for a in step.argv[3:] if not a.startswith("-")] if "vitest" in step.argv else []
            record_vitest_failures(root, result, rel)
        if result.returncode not in step.allow_exit:
            print(f"[FAIL] {step.name} (exit {result.returncode})", flush=True)
            failed.append(step.name)
        else:
            print(f"[OK ] {step.name}", flush=True)

    print(flush=True)
    if failed:
        print(f"{plan.kind}_FAILED: {', '.join(failed)}", flush=True)
        if plan.kind == "TARGETED":
            print("실패 범위만 다시: python scripts/verify.py --failed", flush=True)
        return 1
    print(f"{plan.kind}_OK", flush=True)
    if plan.kind == "TARGETED":
        print("이 결과는 전량 검증이 아니다. 전량: python scripts/verify.py --full", flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="일상 표적 검증. 전량은 --full. 캡처는 이 명령에 없다.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--failed", action="store_true", help="직전 실패만 다시 본다")
    mode.add_argument("--static", action="store_true", help="static_checks.sh 전량")
    mode.add_argument("--full", action="store_true",
                      help="정적 전량 + 백엔드 청크 회귀 + vitest 전량 (캡처 없음)")
    parser.add_argument("--dry-run", action="store_true", help="명령을 출력만 하고 실행하지 않는다")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    args = build_parser().parse_args(argv)
    py = python_exe(ROOT)
    bash = bash_exe()
    if args.full:
        plan = plan_full(root=ROOT, py=py, bash=bash)
    elif args.static:
        plan = plan_static(root=ROOT, bash=bash)
    elif args.failed:
        plan = plan_failed(root=ROOT, py=py)
    else:
        changed = changed_files(ROOT)
        print(f"변경 {len(changed)}개 파일 (HEAD + untracked)", flush=True)
        for rel in changed[:30]:
            print(f"  {rel}", flush=True)
        if len(changed) > 30:
            print(f"  … {len(changed) - 30}개 더", flush=True)
        plan = plan_dev(changed, root=ROOT, py=py, bash=bash)
    return run_plan(plan, root=ROOT, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
