"""`subprocess` 텍스트 모드에 인코딩을 안 적은 곳을 찾는다.

## 왜 검사가 필요한가

`subprocess.run(..., text=True)` 는 인코딩을 안 적으면 **로케일**로 디코드한다. 한국어
Windows 에서는 cp949 다. 자식 프로세스가 UTF-8 한글을 한 글자라도 뱉으면 리더 스레드가
`UnicodeDecodeError` 로 죽고, 그러면 **`result.stderr` 를 못 읽는다.**

즉 마이그레이션이나 빌드가 **실패했을 때 정작 그 이유가 사라진다.** 이유가 가장 필요한
순간에 없어지는 부류라 조용히 넘어가면 안 된다.

## 왜 사람 기억에 맡기지 않는가

이 결함을 이미 **세 번** 고쳤다. 처음엔 `app/sysops/runner.py`, 다음엔 `tests/conftest.py`,
그리고 이번에 마이그레이션 회귀 테스트 6개 — 그중 둘은 **바로 그 라운드에 새로 만들면서
다시 넣은 것**이다. 새 파일을 쓰는 사람은 옆 파일을 복사하고, 옆 파일이 낡았으면 결함도 함께
복사된다. 사람이 기억할 수 있는 종류의 일이 아니다.

## 무엇을 잡고 무엇을 안 잡는가

`text=True` 또는 `universal_newlines=True` 가 있는 호출에서 같은 호출 안에 `encoding=` 이
없으면 잡는다. 바이트 모드(`text` 없음)는 디코드를 안 하므로 대상이 아니다.
"""

from __future__ import annotations

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCAN_DIRS = ("app", "tests", "scripts")
# 검사기 자신은 위 설명에 `text=True` 를 적으므로 제외한다(자기 문서를 결함으로 세지 않는다).
EXEMPT = {"scripts/check_subprocess_encoding.py"}

TEXT_KWARGS = {"text", "universal_newlines"}


def _is_subprocess_call(node: ast.Call) -> bool:
    """`subprocess.run(...)` / `subprocess.Popen(...)` / `run(...)` 형태를 넓게 본다."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr in {"run", "Popen", "check_output", "check_call", "call"}
    if isinstance(func, ast.Name):
        return func.id in {"run", "Popen", "check_output", "check_call", "call"}
    return False


def offenders(path: pathlib.Path) -> list[int]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    hits: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_subprocess_call(node):
            continue
        names = {kw.arg for kw in node.keywords if kw.arg}
        if not (names & TEXT_KWARGS):
            continue          # 바이트 모드 - 디코드를 안 하므로 대상이 아니다
        if "encoding" in names:
            continue
        hits.append(node.lineno)
    return hits


def main() -> int:
    found: list[str] = []
    scanned = 0
    for folder in SCAN_DIRS:
        base = ROOT / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if rel in EXEMPT or "__pycache__" in rel:
                continue
            scanned += 1
            for line in offenders(path):
                found.append(f"{rel}:{line}")

    if not scanned:
        print("[FAIL] 검사할 파이썬 파일을 못 찾았다 - 검사가 뜻이 없다", file=sys.stderr)
        return 1
    if found:
        print(
            "[FAIL] subprocess 텍스트 모드에 encoding 이 없다 - 실패했을 때 그 이유를 못 읽는다:",
            file=sys.stderr,
        )
        for item in found:
            print("       " + item, file=sys.stderr)
        print('       고치는 법: encoding="utf-8", errors="replace" 를 함께 넘긴다',
              file=sys.stderr)
        return 1
    print(f"SUBPROCESS_ENCODING_OK ({scanned}개 파일)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
