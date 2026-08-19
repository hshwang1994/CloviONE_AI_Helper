"""시험을 약화시키면서 통과시키는 것을 막는다 (PLAN §테스트 계획 «재작성 규칙»).

## 왜 필요한가

전면 리뉴얼은 **옛 구조를 고정하던 Contract Test 를 반드시 깬다.** 그 자체는 정상이다 —
`theme-contract.test.js` 의 "chrome 은 발광하지 않는다"는 폐기된 방향의 단언이었고, 그것이
살아 있으면 시험이 제품에 Brand 가 생기는 것을 **금지**한다.

문제는 깬 다음에 무엇을 하느냐다. 빨간 시험을 초록으로 만드는 방법은 둘뿐이고 하나는
거짓이다:

  * 재작성 — 기대값을 바꾸거나, 메커니즘을 강화하거나, 고정된 구조를 그것이 지키던
    불변식으로 교체한다. 단언 수는 유지되거나 늘어난다.
  * 약화 — `it.skip`, 단언 삭제, `toBe` -> `toBeDefined`, 허용오차 확대, 파일 삭제.
    커밋 로그에서는 둘이 똑같이 "테스트 갱신"으로 보인다.

이 검사는 그 둘을 **기계적으로** 구분한다: 이번 작업에서 수정된 시험 파일의 단언 수를
기준 커밋과 비교해 **줄어들면 실패**한다.

## 예외

파일 머리(첫 40줄) 에 사유를 적으면 통과한다. 기존 `clovi-allow-glyph` 관용과 같은
"이유를 적어라" 규약이다:

    qa-contract-change: <60자 이상의 사유>

시험 파일 **삭제**는 대체 파일을 명명하지 않으면 무조건 실패한다:

    qa-contract-replaced-by: <새 파일 경로>

를 그 대체 파일 머리에 적는다.

## 쓰는 법

    python scripts/check_test_strength.py              # HEAD 와 비교
    python scripts/check_test_strength.py --base <ref> # 지정한 기준과 비교
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent

# 시험 파일로 취급하는 경로. 프런트는 파일명 규약, 백엔드는 디렉터리 규약이다.
FRONT_RE = re.compile(r"^frontend/src/.*\.test\.(js|jsx)$")
BACK_RE = re.compile(r"^tests/.*/test_.*\.py$|^tests/test_.*\.py$")

# 단언으로 세는 것. 프런트는 `expect(`, 파이썬은 `assert ` 와 `pytest.raises(`.
FRONT_ASSERT_RE = re.compile(r"\bexpect\s*\(")
BACK_ASSERT_RE = re.compile(r"^\s*assert\s|\bpytest\.raises\s*\(", re.MULTILINE)

# 약화의 직접 증거. 수가 유지돼도 이것이 늘면 실패다.
SKIP_RE = re.compile(r"\b(it|test|describe)\.skip\b|@pytest\.mark\.skip\b|\bxit\b")

ALLOW_RE = re.compile(r"qa-contract-change:\s*(.+)")
REPLACED_RE = re.compile(r"qa-contract-replaced-by:\s*(\S+)")
MIN_REASON = 60
HEADER_LINES = 40


def run(*args: str) -> str:
    out = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return out.stdout if out.returncode == 0 else ""


def is_test(path: str) -> bool:
    return bool(FRONT_RE.match(path) or BACK_RE.match(path))


def count(path: str, text: str) -> int:
    rx = FRONT_ASSERT_RE if FRONT_RE.match(path) else BACK_ASSERT_RE
    return len(rx.findall(text))


def skips(text: str) -> int:
    return len(SKIP_RE.findall(text))


def header(text: str) -> str:
    return "\n".join(text.splitlines()[:HEADER_LINES])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="HEAD", help="비교 기준 ref (기본: HEAD)")
    args = ap.parse_args()

    # 기준 대비 바뀐 파일 — 스테이지 여부와 무관하게 본다(작업 중에도 돌릴 수 있어야 한다).
    names = run("diff", "--name-status", args.base)
    if not names.strip():
        print(f"[OK ] TEST_STRENGTH_OK ({args.base} 대비 변경 없음)")
        return 0

    problems: list[str] = []
    checked = 0
    replaced_by: dict[str, str] = {}

    rows = []
    for line in names.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0], parts[-1]
        if is_test(path):
            rows.append((status, path))

    # 대체 선언을 먼저 모은다 — 삭제 판정이 그것에 기대기 때문이다.
    for _status, path in rows:
        p = ROOT / path
        if not p.exists():
            continue
        m = REPLACED_RE.search(header(p.read_text(encoding="utf-8", errors="replace")))
        if m:
            replaced_by[m.group(1).strip()] = path

    for status, path in rows:
        before = run("show", f"{args.base}:{path}")
        p = ROOT / path

        if status.startswith("D") or not p.exists():
            if path in replaced_by:
                print(f"[note] {path} -> {replaced_by[path]} 로 대체됨")
                continue
            problems.append(f"{path}: 시험 파일이 삭제됐는데 대체 파일이 명명되지 않았다")
            continue

        after = p.read_text(encoding="utf-8", errors="replace")
        if not before:
            checked += 1
            continue  # 신규 파일 — 비교 대상이 없다

        n_before, n_after = count(path, before), count(path, after)
        s_before, s_after = skips(before), skips(after)
        checked += 1

        reason = ALLOW_RE.search(header(after))
        excused = bool(reason) and len(reason.group(1).strip()) >= MIN_REASON

        if n_after < n_before and not excused:
            problems.append(
                f"{path}: 단언이 {n_before} -> {n_after} 로 줄었다. "
                f"재작성이라면 사유를 파일 머리에 `qa-contract-change: <{MIN_REASON}자 이상>` 로 적어라"
            )
        if s_after > s_before:
            problems.append(f"{path}: skip 이 {s_before} -> {s_after} 로 늘었다 (예외 없음)")
        if reason and len(reason.group(1).strip()) < MIN_REASON:
            problems.append(
                f"{path}: `qa-contract-change` 사유가 {MIN_REASON}자 미만이다"
            )

    if problems:
        print("[FAIL] 시험이 약해졌다:")
        for line in problems:
            print(f"  - {line}")
        return 1

    print(f"[OK ] TEST_STRENGTH_OK ({args.base} 대비 시험 파일 {checked}개 검사)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
