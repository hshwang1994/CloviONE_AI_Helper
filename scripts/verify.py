"""일상 개발용 표적 검증 진입점.

전량 게이트와 같은 명령을 기본값으로 두지 않는다. 작은 변경은 관련 시험만 돌리고,
전체 회귀·캡처·Pilot 은 호출하지 않는다.

    python scripts/verify.py              # TARGETED: 변경 파일 매핑 + static --scope dev
    python scripts/verify.py <경로…>      # 그 경로를 «바뀐 것» 으로 보고 표적을 짠다
    python scripts/verify.py --failed     # 직전 실패만 (pytest --lf, 기록된 vitest)
    python scripts/verify.py --static     # static_checks 전량 (Exit 게이트)
    python scripts/verify.py --full       # static 전량 + 백엔드 청크 회귀 + vitest 전량
                                          # 브라우저 캡처/Pilot/E2E 는 넣지 않는다

부분 실행은 전량 Evidence 가 아니다. 이 스크립트는 캡처 산출물을 쓰지 않는다.

## 표적은 스스로 전량으로 번지지 않는다 (D-315)

이 스크립트가 지키는 규칙 셋이다. 셋 다 "표적이 조용히 전량이 되는" 경로를 막는다.

  1. **표적 실행기가 못 뜨면 전량으로 갈아타지 않는다.** `npx` 를 못 찾았을 때 `npm test`
     로 내려가면 사용자는 "표적을 돌렸다"고 믿는데 실제로는 전량이 돈다. 실행기가 없으면
     `RUNNER_MISSING` 으로 **그 단계만** 실패시킨다 — 무엇을 설치해야 하는지 함께 적는다.
  2. **소스 변경 자체는 전량 사유가 아니다.** 공용 부품(`kit.jsx` 등)을 고쳤다고 전량
     vitest 를 고르지 않는다. 매핑된 시험이 없으면 "없다"고 말하고 끝낸다 — 없는 시험을
     지어내지도, 대신 전량을 돌리지도 않는다.
  3. **표적 결과가 다른 전량을 자동으로 부르지 않는다.** 실패하면 실패 범위를 다시 보라고
     안내할 뿐이다(`--failed`). 전량은 사람이 `--full` 이라고 적을 때만 돈다.

Coverage·Pilot·Capture·Evidence 는 이 스크립트에 **없다**. 그것은 Acceptance 회차의 일이고
일상 구현의 완료 조건이 아니다 (MASTER_PLAN §9.4).
"""

from __future__ import annotations

import argparse
import json
import os
import re
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

# 표적 vitest 를 못 돌렸을 때 그 단계가 남기는 표식. 전량으로 갈아타는 대신 이것을 찍는다.
RUNNER_MISSING = "RUNNER_MISSING"

VITEST_HINT = (
    "frontend 의 vitest 를 못 찾았다. `cd frontend && npm ci` 로 node_modules 를 세우거나 "
    "PATH 에 npx 를 두어라. 전량으로 대신 돌리지 않는다."
)


@dataclass
class Step:
    name: str
    argv: list[str]
    cwd: str | None = None
    stdin_null: bool = False
    allow_exit: frozenset[int] = field(default_factory=lambda: frozenset({0}))
    # 이 단계가 돌린 vitest 파일. `--failed` 가 다시 쓰려면 argv 를 되짚지 않고 이걸 읽는다
    # (실행기 모양이 `npx vitest run …` 하나가 아니라서 위치로 자르면 조용히 어긋난다).
    vitest_files: list[str] = field(default_factory=list)
    # 실행기 자체가 없어서 만든 단계. 실행하지 않고 곧장 실패로 적는다.
    missing_runner: str | None = None


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


def vitest_runner(root: Path = ROOT) -> list[str] | None:
    """vitest 를 부르는 argv 앞머리. 못 찾으면 `None`.

    🔴 `["npx", "vitest", …]` 를 그대로 `subprocess.run` 에 넘기면 **윈도우에서 안 뜬다**
    (P-48). PATH 에 있는 것은 `npx.CMD` 인데 `CreateProcess` 는 PATHEXT 를 안 붙여 보고
    `[WinError 2]` 로 죽는다. 셸을 켜서 우회하는 방법은 인자 따옴표 규칙이 플랫폼마다
    달라져 파일 경로에 공백이 있을 때 다시 깨진다 — 실행기를 **이름으로 해석**한다.

    순서에 이유가 있다.
      1. `frontend/node_modules/.bin/vitest[.cmd]` — 이 저장소가 실제로 쓰는 그 버전이다.
         npx 를 거치지 않아 레지스트리 조회도, 버전이 갈릴 여지도 없다.
      2. `shutil.which("npx")` — 로컬 설치가 없는 환경(clean clone 직후)을 위한 대안.
         `which` 는 PATHEXT 를 보므로 윈도우에서도 `npx.CMD` 의 실제 경로가 나온다.

    둘 다 없으면 `None` 이다. 부르는 쪽은 전량으로 갈아타지 않고 그 단계를 실패시킨다.
    """
    local = root / "frontend" / "node_modules" / ".bin"
    names = ("vitest.cmd", "vitest") if os.name == "nt" else ("vitest",)
    for name in names:
        candidate = local / name
        if candidate.is_file():
            return [str(candidate)]
    npx = shutil.which("npx")
    if npx:
        return [npx, "vitest"]
    return None


def vitest_step(name: str, rel_files: list[str], *, root: Path) -> Step:
    """vitest 한 단계. 실행기가 없으면 **실행하지 않는 실패 단계**를 만든다."""
    runner = vitest_runner(root)
    if runner is None:
        return Step(name, [], cwd=str(root / "frontend"), missing_runner=VITEST_HINT)
    return Step(
        name,
        [*runner, "run", *rel_files],
        cwd=str(root / "frontend"),
        vitest_files=list(rel_files),
    )


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


# 한 부품을 들여오는 시험이 이보다 많으면 **표적으로 안 고른다.** `ui/kit.jsx` 를 고치면
# 169개가 걸리는데 그것은 사실상 전량이고, 전량은 사람이 `--full` 이라고 적을 때만 돈다(D-315).
IMPORTER_CAP = 20
# 되짚는 깊이. 1 = 시험이 그 파일을 직접 들여온다. 2 = 시험이 들여온 화면이 그 파일을 쓴다
# (`document-views.js` ← `Trash.jsx` ← `trash-doc-detail-invalidation.test.jsx` 가 그 모양이다).
IMPORTER_DEPTH = 2

_IMPORT_RE = re.compile(r"""(?:from|import)\s*\(?\s*["']([./][^"']+)["']""")


def _frontend_sources(root: Path) -> list[Path]:
    src = root / "frontend" / "src"
    if not src.is_dir():
        return []
    return [p for p in src.rglob("*") if p.suffix in {".js", ".jsx", ".ts", ".tsx"}]


def _resolve_import(base: Path, spec: str, known: set[str], root: Path) -> str | None:
    """상대 import 를 저장소 상대 경로로. 확장자 생략과 `index` 를 함께 본다."""
    target = (base.parent / spec).resolve()
    for cand in (target, *(target.with_suffix(s) for s in (".js", ".jsx", ".ts", ".tsx")),
                 *(target / f"index{s}" for s in (".js", ".jsx", ".ts", ".tsx"))):
        try:
            rel = posix(cand.relative_to(root.resolve()))
        except ValueError:
            continue
        if rel in known:
            return rel
    return None


def importing_tests(rel_paths: list[str], root: Path) -> tuple[list[str], list[str]]:
    """변경 파일을 (간접적으로) 들여오는 시험 파일. 반환은 `(고른 것, 안 고른 사유)`.

    이 저장소의 시험은 **계약 이름**으로 불린다(`ticket-share-scope.test.jsx`). 그래서 파일
    줄기로만 맞추면 화면을 고칠 때 표적이 **한 건도** 안 잡힌다 — 그러면 사람이 `--full` 로
    가고, 그건 이 스크립트가 막으려던 바로 그 일이다. import 를 거꾸로 따라가되, 걸리는 수가
    `IMPORTER_CAP` 을 넘으면 **안 고른다**(그건 전량이지 표적이 아니다).
    """
    sources = _frontend_sources(root)
    if not sources:
        return [], []
    known = {posix(p.relative_to(root)) for p in sources}
    # 소비처 → 그 파일이 들여오는 것들
    imports: dict[str, set[str]] = {}
    for path in sources:
        rel = posix(path.relative_to(root))
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hit = {r for spec in _IMPORT_RE.findall(text)
               if (r := _resolve_import(path, spec, known, root))}
        imports[rel] = hit

    picked: list[str] = []
    notes: list[str] = []
    for raw in rel_paths:
        seed = posix(raw)
        if seed not in known:
            continue
        reach = {seed}
        for _ in range(IMPORTER_DEPTH):
            grown = {c for c, used in imports.items() if used & reach}
            if not grown - reach:
                break
            reach |= grown
        found = sorted(r for r in reach if _is_vitest_file(Path(r).name))
        if not found:
            continue
        if len(found) > IMPORTER_CAP:
            notes.append(
                f"{seed}: 시험 {len(found)}개가 이 부품을 들여온다 — 표적으로 안 고른다"
                f" (상한 {IMPORTER_CAP}). 골라 돌리려면"
                " python scripts/verify.py <시험 경로…>")
            continue
        picked.extend(found)
    return picked, notes


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


# 「어떤 변경이 coverage plan 게이트를 부르는가」와 「어떤 변경이 시험 강도 검사를 부르는가」는
# 여기 없다. 그 판정은 `scripts/static_checks.sh` 의 `changed_match` 한 곳에 있고 이 스크립트는
# 그 스크립트를 부른다 — 같은 정책을 두 벌 들면 한쪽만 고쳐지고 그때부터 둘이 다른 말을 한다.


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
    importers, importer_notes = importing_tests(changed, root)
    seen = set(vitest_files)
    for rel in importers:
        if rel not in seen:
            seen.add(rel)
            vitest_files.append(rel)
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
    notes.extend(importer_notes)
    if vitest_files:
        steps.append(vitest_step("vitest 표적", _vitest_rel(sorted(vitest_files)), root=root))
    else:
        # 공용 부품을 고쳤는데 같은 줄기 시험이 없을 수 있다. 그때 전량 vitest 를 대신
        # 고르지 않는다 — 소스 변경 자체는 전량 사유가 아니다(D-315).
        notes.append("매핑된 vitest 파일이 없다. 전량으로 대신 돌리지 않는다.")
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
        steps.append(vitest_step("vitest 직전 실패", last, root=root))
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
            vitest_step("프런트 전량 (vitest)", [], root=root),
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


def record_vitest_failures(root: Path, rel_files: list[str]) -> None:
    """표적 vitest 가 실패하면 그 파일 목록을 남겨 --failed 가 다시 쓴다.

    전량 실행(파일 목록이 비어 있다)은 기록하지 않는다 — 「직전 실패」로 전량을 다시 부르면
    그 순간 `--failed` 가 전량 게이트가 된다.
    """
    if not rel_files:
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
            if step.missing_runner:
                print(f"DRY {step.name}: [{RUNNER_MISSING}] {step.missing_runner}", flush=True)
                continue
            print(f"DRY {step.name}: {' '.join(step.argv)}{where}", flush=True)
        print(f"{plan.kind}_DRY_RUN", flush=True)
        return 0

    failed: list[str] = []
    for step in plan.steps:
        print(flush=True)
        print(f"== {step.name} ==", flush=True)
        # 실행기가 없다. 다른 명령으로 갈아타지 않고 여기서 끝낸다 — 전량으로 번지는
        # 자동 확대를 만들지 않는 것이 이 분기의 존재 이유다(D-315).
        if step.missing_runner:
            print(f"[FAIL] {step.name}: {RUNNER_MISSING} — {step.missing_runner}", flush=True)
            failed.append(step.name)
            continue
        stdin = subprocess.DEVNULL if step.stdin_null else None
        try:
            result = subprocess.run(
                step.argv,
                cwd=step.cwd or str(root),
                stdin=stdin,
            )
        except OSError as exc:
            print(f"[FAIL] {step.name}: {RUNNER_MISSING} — {exc}", flush=True)
            failed.append(step.name)
            continue
        if result.returncode != 0:
            record_vitest_failures(root, step.vitest_files)
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
    parser.add_argument(
        "paths", nargs="*",
        help="이 경로들을 «바뀐 것» 으로 보고 표적을 짠다 (기본: git 이 말하는 변경 파일)")
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
    elif args.paths:
        changed = [posix(p) for p in args.paths]
        print(f"지정 {len(changed)}개 경로", flush=True)
        for rel in changed:
            print(f"  {rel}", flush=True)
        plan = plan_dev(changed, root=ROOT, py=py, bash=bash)
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
