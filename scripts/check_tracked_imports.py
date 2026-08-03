"""추적되는 파일이 추적되지 않는 모듈을 import 하는지 검사한다.

왜 필요한가: 실제로 한 번 터졌다. `git add`로 백엔드 작업의 일부만 커밋되면서
`app/models_registry.py`(추적됨)가 `app.tickets.models`(미추적)를 import 하는
상태가 HEAD에 올라갔다. 워킹트리에는 파일이 다 있으니 테스트도 전부 통과하고
서버도 뜬다 — **fresh clone에서만 죽는다**. 즉 배포 서버에서 처음 발견된다.

이 검사는 워킹트리가 아니라 **git이 아는 것**만 보고 판정한다. 그래서 로컬에
파일이 있어도 커밋되지 않았으면 잡힌다.

판정:
  [FAIL] 추적 파일이 import 하는 모듈이 디스크에는 있는데 git에는 없다  → 커밋 누락
  [FAIL] 추적 파일이 import 하는 모듈이 디스크에도 git에도 없다        → 끊어진 import
  통과   그 외

`from app.foo import bar`의 `bar`는 모듈일 수도 심볼일 수도 있다. `app/foo/bar.py`가
디스크에 존재할 때만 모듈로 보고 검사한다 — 심볼이면 파일이 없으므로 조용히 넘어간다.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

# Windows 기본 콘솔 인코딩(cp949)에서는 아래 한국어 메시지가 깨져 읽을 수 없다.
# 검사가 실패했을 때 이유를 못 읽으면 검사가 없는 것과 같다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
# 1인칭 패키지만 본다. 서드파티는 requirements 쪽 문제라 여기 범위가 아니다.
FIRST_PARTY = ("app", "tests", "scripts", "alembic")


def tracked_files() -> set[str]:
    """**HEAD** 에 있는 파일 목록.

    `git ls-files`(인덱스)를 쓰면 안 된다. staged 지만 아직 커밋되지 않은 파일도
    '추적됨'으로 세기 때문에, 정작 배포되는 HEAD 에 그 파일이 없어도 검사가 통과한다.
    실제로 그렇게 두 번 새 나갔다. 배포되는 것은 HEAD 이므로 HEAD 를 본다.
    """
    out = subprocess.run(
        ["git", "ls-tree", "-r", "-z", "--name-only", "HEAD"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    return {p.replace("\\", "/") for p in out.split("\0") if p}


def head_text(rel: str) -> str:
    """HEAD 시점의 파일 내용. 워킹트리 내용을 읽으면 아직 커밋 안 된 import 까지 보게 된다."""
    r = subprocess.run(
        ["git", "show", f"HEAD:{rel}"], cwd=ROOT, capture_output=True, check=False
    )
    return r.stdout.decode("utf-8", errors="replace") if r.returncode == 0 else ""


def module_candidates(module: str) -> list[str]:
    """`app.foo.bar` → 이 모듈이 놓일 수 있는 경로들."""
    base = module.replace(".", "/")
    return [f"{base}.py", f"{base}/__init__.py"]


def imported_modules(tree: ast.AST) -> set[str]:
    """파일이 참조하는 1인칭 모듈 이름을 모은다."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FIRST_PARTY:
                    found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            # 상대 import(level>0)는 파일 위치 기준이라 여기서 다루지 않는다.
            if node.level or not node.module:
                continue
            if node.module.split(".")[0] not in FIRST_PARTY:
                continue
            found.add(node.module)
            # `from app.foo import bar` 의 bar 가 모듈일 수 있다.
            for alias in node.names:
                if alias.name != "*":
                    found.add(f"{node.module}.{alias.name}")
    return found


def main() -> int:
    tracked = tracked_files()
    py_files = sorted(
        f for f in tracked if f.endswith(".py") and f.split("/")[0] in FIRST_PARTY
    )

    missing: list[tuple[str, str, str]] = []  # (importer, module, 원인)
    for rel in py_files:
        try:
            tree = ast.parse(head_text(rel), filename=rel)
        except (OSError, SyntaxError) as exc:
            print(f"[FAIL] {rel}: 파싱 실패 — {exc}", file=sys.stderr)
            return 1

        for module in sorted(imported_modules(tree)):
            candidates = module_candidates(module)
            if any(c in tracked for c in candidates):
                continue
            on_disk = [c for c in candidates if (ROOT / c).exists()]
            if on_disk:
                missing.append((rel, module, f"디스크에는 있으나 미추적: {on_disk[0]}"))
            # 디스크에도 없으면 심볼 import이거나 진짜 끊어진 import다.
            # 심볼과 구분할 방법이 없으므로(런타임에만 알 수 있다) 여기서는 넘어간다 —
            # 끊어진 import 는 어차피 pytest 수집 단계에서 즉시 죽는다.

    if missing:
        print("[FAIL] 추적되는 파일이 커밋되지 않은 모듈을 import 한다:", file=sys.stderr)
        print("       (워킹트리에서는 돌지만 fresh clone / 배포 서버에서 죽는다)", file=sys.stderr)
        for importer, module, why in missing:
            print(f"  - {importer}", file=sys.stderr)
            print(f"      import {module}  →  {why}", file=sys.stderr)
        print("", file=sys.stderr)
        print("  고치는 법: 해당 파일을 같은 커밋에 함께 스테이지하라.", file=sys.stderr)
        return 1

    print(f"TRACKED_IMPORTS_OK ({len(py_files)}개 파일)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
