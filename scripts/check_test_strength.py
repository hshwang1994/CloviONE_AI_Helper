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

이 검사는 그 둘을 **기계적으로** 구분한다: 이번 작업에서 수정된 시험 파일의 단언을 기준
커밋과 비교해 **약해지면 실패**한다.

## S1 에서 막은 것 셋 — 이 검사는 세 방향으로 눈이 멀어 있었다

1. **기본 기준이 `HEAD` 였다.** 그러면 «커밋되지 않은» 약화만 보인다. 약화를 커밋하는 순간
   이 검사에서 **영원히 사라진다** — 다음 실행은 그 약화를 기준선으로 삼기 때문이다.
   이제 기준은 **직전 Session 커밋**이다(`docs/platform/WORK_STATE.md` 의
   `last_stable_commit`). 어디서도 못 찾으면 **실행을 거부한다** — HEAD 로 조용히 내려가지
   않는다.
2. **기준 ref 가 틀려도 통과했다.** `git diff <없는ref>` 는 빈 문자열을 주고, 이 검사는 그걸
   «변경 없음» 으로 읽어 초록을 찍었다. 이제 ref 를 먼저 `rev-parse --verify` 한다.
3. **단언을 «개수» 로만 셌다.** `toBe(3)` → `toBeDefined()` 는 개수가 그대로라 통과했다.
   이제 **약한 형태**(`toBeDefined`·`toBeTruthy`·`toBeFalsy`, 비교 없는 `assert x`)를 따로
   세고, **강한 단언 수가 줄면** 실패한다.

## 예외

파일 머리(첫 40줄) 에 사유를 적으면 통과한다. 기존 `clovi-allow-glyph` 관용과 같은
"이유를 적어라" 규약이다:

    qa-contract-change: <60자 이상의 사유>

시험 파일 **삭제**는 대체 파일을 명명하지 않으면 무조건 실패한다:

    qa-contract-replaced-by: <새 파일 경로>

를 그 대체 파일 머리에 적는다.

## 쓰는 법

    python scripts/check_test_strength.py              # 직전 Session 커밋과 비교
    python scripts/check_test_strength.py --base <ref> # 지정한 기준과 비교
    python scripts/check_test_strength.py --self-test  # 검사기 자기검증
"""

from __future__ import annotations

import argparse
import os
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

# **약한 단언** — 개수는 그대로인데 내용이 빠져나가는 형태.
#
# `toBe(3)` → `toBeDefined()` 는 «값이 3 이다» 를 «무언가 있다» 로 바꾼다. 개수만 세면 이게
# 통과한다(그래서 이 검사는 오래 눈이 멀어 있었다). 파이썬 쪽은 비교가 없는 `assert x` 가
# 같은 자리다 — `assert resp.status_code == 200` 과 `assert resp` 는 다른 단언이다.
FRONT_WEAK_RE = re.compile(r"\.(toBeDefined|toBeTruthy|toBeFalsy)\s*\(")
BACK_WEAK_RE = re.compile(r"^\s*assert\s+(?![^\n]*(==|!=|<|>|\bin\b|\bis\b))[^\n]+$",
                          re.MULTILINE)

# 기준 커밋을 어디서 읽는가. **HEAD 로 조용히 내려가지 않는다.**
BASE_SOURCES = (
    ("docs/platform/WORK_STATE.md", re.compile(
        r"^-\s*last_stable_commit:\s*\**`?([0-9a-fA-F]{7,40})`?", re.M)),
    ("docs/ui-renewal/WORK_STATE.md", re.compile(
        r"^-\s*commit:\s*\**`?([0-9a-fA-F]{7,40})`?", re.M)),
)

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


def weak(path: str, text: str) -> int:
    rx = FRONT_WEAK_RE if FRONT_RE.match(path) else BACK_WEAK_RE
    return len(rx.findall(text))


def strong(path: str, text: str) -> int:
    """내용을 지키는 단언 수. **이것이 줄면 약화다** — 총수가 같아도."""
    return count(path, text) - weak(path, text)


def resolve_base(explicit: str) -> tuple[str, str]:
    """(ref, 어디서 왔는가). 못 찾으면 `("", 사유)` 를 준다."""
    if explicit:
        return explicit, "--base"
    env = os.environ.get("TEST_STRENGTH_BASE", "").strip()
    if env:
        return env, "$TEST_STRENGTH_BASE"
    for rel, rx in BASE_SOURCES:
        path = ROOT / rel
        if not path.exists():
            continue
        m = rx.search(path.read_text(encoding="utf-8", errors="replace"))
        if m:
            return m.group(1), rel
    return "", ("기준 커밋을 못 찾았다 — docs/platform/WORK_STATE.md 의 `last_stable_commit` "
                "을 채우거나 --base 를 넘겨라. HEAD 로 내려가지 않는다: 그러면 **커밋된 "
                "약화가 영원히 안 보인다**")


SELF_TEST_CASES = [
    # (경로, before, after, 약화인가, 무엇을 지키는 사례인가)
    ("frontend/src/a.test.js", "expect(x).toBe(3);", "expect(x).toBe(4);", False,
     "기대값을 고치는 것은 재작성이다"),
    ("frontend/src/a.test.js", "expect(x).toBe(3);", "expect(x).toBeDefined();", True,
     "개수는 그대로인데 «값이 3» 이 «무언가 있다» 로 바뀌었다 — 예전엔 통과했다"),
    ("frontend/src/a.test.js", "expect(x).toBe(3);", "expect(x).toBe(3);\nexpect(y).toBe(1);",
     False, "단언을 늘리는 것은 강화다"),
    ("frontend/src/a.test.js", "expect(x).toBe(3);\nexpect(y).toBe(1);", "expect(x).toBe(3);",
     True, "단언을 지우면 약화다(기존 규칙)"),
    ("tests/test_a.py", "    assert resp.status_code == 200", "    assert resp", True,
     "비교가 사라졌다"),
    ("tests/test_a.py", "    assert resp.status_code == 200",
     "    assert resp.status_code == 201", False, "기대값 변경은 재작성이다"),
    ("tests/test_a.py", "    with pytest.raises(ValueError):\n        f()",
     "    with pytest.raises(ValueError):\n        f()", False, "그대로면 통과"),
]

#: 삭제 선언 파싱의 자기검증 — (파일 머리 문자열, 그 머리가 명명하는 경로들).
#: 뒤의 둘이 **반례**다: 선언이 없거나 머리 40줄 밖이면 못 찾아야 한다. 이것이 없으면
#: 「여러 개를 받는다」는 완화가 「아무거나 통과한다」로 조용히 미끄러질 수 있다.
REPLACED_SELF_TEST = [
    ("qa-contract-replaced-by: tests/a.py\n", ["tests/a.py"]),
    ("qa-contract-replaced-by: tests/a.py\nqa-contract-replaced-by: tests/b.py\n",
     ["tests/a.py", "tests/b.py"]),
    ("삭제했지만 아무 선언도 안 적었다\n", []),
    ("\n" * (HEADER_LINES + 1) + "qa-contract-replaced-by: tests/late.py\n", []),
]


def self_test() -> int:
    bad = []
    for text, expected in REPLACED_SELF_TEST:
        found = [m.group(1).strip() for m in REPLACED_RE.finditer(header(text))]
        if found != expected:
            bad.append(f"삭제 선언 파싱: 기대 {expected} / 실제 {found}")
    for path, before, after, should_flag, why in SELF_TEST_CASES:
        weakened = strong(path, after) < strong(path, before)
        if weakened != should_flag:
            bad.append("%s: 기대 %s / 실제 %s  (강 %d -> %d)"
                       % (why, "검출" if should_flag else "통과",
                          "검출" if weakened else "통과",
                          strong(path, before), strong(path, after)))
    if bad:
        print("[FAIL] 검사기 자체가 고장 났다 — 초록이 아무것도 증명하지 못한다:")
        for line in bad:
            print(f"  - {line}")
        return 1
    print("[OK ] TEST_STRENGTH_SELF_TEST_OK (약화·재작성 %d사례 + 삭제 선언 %d사례)"
          % (len(SELF_TEST_CASES), len(REPLACED_SELF_TEST)))
    return 0


def skips(text: str) -> int:
    return len(SKIP_RE.findall(text))


def header(text: str) -> str:
    return "\n".join(text.splitlines()[:HEADER_LINES])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="",
                    help="비교 기준 ref (기본: 직전 Session 커밋 — WORK_STATE 에서 읽는다)")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if self_test() != 0:
        return 1

    base, origin = resolve_base(args.base)
    if not base:
        print("[FAIL] %s" % origin)
        return 1
    # ref 가 실재하는지 **먼저** 확인한다. 없으면 `git diff` 가 빈 문자열을 주고, 예전 코드는
    # 그것을 «변경 없음» 으로 읽어 초록을 찍었다 — fail-open 이 하나 더 있었던 자리다.
    if not run("rev-parse", "--verify", "--quiet", f"{base}^{{commit}}").strip():
        print(f"[FAIL] 기준 ref 를 못 찾았다: {base} (출처 {origin}). "
              "없는 기준으로 비교하면 «변경 없음» 이 되어 조용히 통과한다")
        return 1

    # 기준 대비 바뀐 파일 — 스테이지 여부와 무관하게 본다(작업 중에도 돌릴 수 있어야 한다).
    names = run("diff", "--name-status", base)
    if not names.strip():
        print(f"[OK ] TEST_STRENGTH_OK ({base} 대비 변경 없음, 출처 {origin})")
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
    #
    # **한 파일이 여러 삭제를 대신할 수 있다**(`finditer`). 기능 하나가 통째로 사라지면
    # (S11 의 n8n·러너) 그 기능의 시험 열일곱 개가 함께 사라지는데, 1:1 을 강제하면
    # 아무것도 안 지키는 껍데기 파일 열일곱 개를 만들게 된다 — 그것이 더 나쁘다.
    # 규칙의 뜻은 「1:1」이 아니라 **「지운 파일마다 이름이 명시적으로 적혀 있다」**이고,
    # 그 뜻은 그대로다: 선언 없는 삭제는 여전히 실패한다(아래 self-test 두 사례).
    for _status, path in rows:
        p = ROOT / path
        if not p.exists():
            continue
        for m in REPLACED_RE.finditer(header(p.read_text(encoding="utf-8", errors="replace"))):
            replaced_by[m.group(1).strip()] = path

    for status, path in rows:
        before = run("show", f"{base}:{path}")
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
        g_before, g_after = strong(path, before), strong(path, after)
        s_before, s_after = skips(before), skips(after)
        checked += 1

        reason = ALLOW_RE.search(header(after))
        excused = bool(reason) and len(reason.group(1).strip()) >= MIN_REASON

        if n_after < n_before and not excused:
            problems.append(
                f"{path}: 단언이 {n_before} -> {n_after} 로 줄었다. "
                f"재작성이라면 사유를 파일 머리에 `qa-contract-change: <{MIN_REASON}자 이상>` 로 적어라"
            )
        elif g_after < g_before and not excused:
            problems.append(
                f"{path}: 단언 수는 {n_before} -> {n_after} 로 유지됐지만 **내용을 지키는 "
                f"단언이 {g_before} -> {g_after} 로 줄었다** "
                f"(`toBe`→`toBeDefined` 류, 또는 비교가 사라진 `assert`). "
                f"의도한 재작성이면 `qa-contract-change:` 로 사유를 적어라"
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

    print(f"[OK ] TEST_STRENGTH_OK ({base} 대비 시험 파일 {checked}개 검사, 출처 {origin})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
