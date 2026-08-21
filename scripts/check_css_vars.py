"""정의된 적 없는 CSS 변수를 fallback 없이 쓰는 곳을 찾는다.

왜 필요한가: 실제로 로그인 화면에서 터졌다. `auth.css`의 `eye-error` 키프레임이
`scaleY(var(--eye-open))`을 쓰는데 `--eye-open`은 어디에도 정의돼 있지 않았다
(ChatGPT가 만든 원본 v2부터 그랬고 그대로 이식됐다).

CSS 변수의 무서운 점: 정의되지 않은 `var()`를 fallback 없이 참조하면 **그 선언
하나만 무시되는 게 아니라 선언 전체가 무효**가 된다("invalid at computed-value
time"). 위 경우 `transform` 전체가 `none`이 되어 시선 위치(`translate3d`)까지 함께
사라졌다. Chrome으로 확인한 실제 값:
    fallback 없음 → matrix(1,0,0,1,0,0)      (시선 소실)
    fallback 1    → matrix(1,0,0,1,3.8,1)    (시선 유지)

빌드도 린트도 테스트도 이걸 못 잡는다. 화면에서 눈으로 봐야만 보이는데, 오류
애니메이션처럼 자주 안 나오는 상태면 배포 후에도 한참 모른다.

**런타임에 JS가 넣는 변수**는 CSS에 정의가 없는 게 정상이다(`--eye-x`/`--eye-y`가
그렇다). 그래서 JS 소스에서 `style.setProperty('--x')` / `--x:` 형태로 **설정하는**
변수는 정의된 것으로 친다.

## S1 에서 막은 것 — "언급"과 "정의"는 다르다

예전 판정은 JS 파일 515개를 **통째로 이어 붙인 문자열에서 `--\\w+` 를 전부** 긁어
"정의됨"으로 쳤다. 그래서 주석의 구분선(`----------`), CLI 플래그(`--fail-on`·`--record`),
그리고 그냥 **이름만 언급된** CSS 변수까지 정의로 셌다 — 실측하면 48개 중 진짜 정의는
**6개**뿐이었다. 즉 이 검사는 「JS가 넣어 준다」는 이유로 거의 모든 미정의 변수를 눈감을 수
있는 상태였다. `find_dead_css.py` 가 주석에만 남은 클래스를 "사용 중"으로 세던 것과 같은
실패 모드다.

이제 **정의 구문만** 인정한다: `setProperty("--x", …)` · 객체 키 `"--x":` ·
템플릿 문자열 안의 선언 `--x:`.

사용법:
  .venv/Scripts/python.exe scripts/check_css_vars.py
  .venv/Scripts/python.exe scripts/check_css_vars.py --self-test
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

CSS_ROOTS = [ROOT / "app" / "static" / "css", ROOT / "frontend" / "src" / "styles"]
JS_ROOTS = [ROOT / "app" / "static" / "js", ROOT / "frontend" / "src"]

DEFINE = re.compile(r"(--[a-zA-Z0-9_-]+)\s*:")
# fallback 이 없는 참조만 잡는다: var(--x) 는 잡고 var(--x, 1) 은 넘어간다.
USE_NO_FALLBACK = re.compile(r"var\(\s*(--[a-zA-Z0-9_-]+)\s*\)")

# JS 가 **실제로 값을 넣는** 세 형태만 정의로 인정한다. 이름을 그냥 적어 둔 것은 정의가 아니다.
JS_DEFINE_RES = (
    re.compile(r"""setProperty\(\s*['"`](--[a-zA-Z0-9_-]+)"""),   # el.style.setProperty("--x", v)
    re.compile(r"""['"](--[a-zA-Z0-9_-]+)['"]\s*:"""),            # { "--x": v }
    re.compile(r"""(--[a-zA-Z0-9_-]+)\s*:\s*[^\s;{}]"""),         # `--x: ${v}` (템플릿 CSS)
)


def js_defined(blob: str) -> set[str]:
    out: set[str] = set()
    for rx in JS_DEFINE_RES:
        out |= set(rx.findall(blob))
    return out


SELF_TEST_CASES = [
    # (JS 소스, 정의로 쳐야 하는 이름, 정의로 치면 안 되는 이름, 무엇을 지키는 사례인가)
    ('el.style.setProperty("--eye-x", x);', {"--eye-x"}, set(), "setProperty 는 진짜 정의다"),
    ('const s = { "--gap": "8px" };', {"--gap"}, set(), "객체 키로 넣는 것도 정의다"),
    ('const css = `.a { --ring: ${c}; }`;', {"--ring"}, set(), "템플릿 문자열 안의 선언"),
    ('// 색 토큰은 --color-bg 를 쓴다', set(), {"--color-bg"},
     "주석의 언급은 정의가 아니다 — 예전엔 이것도 정의로 셌다"),
    ('run("--fail-on", "all");  // ---------- 구분선', set(), {"--fail-on", "----------"},
     "CLI 플래그와 구분선까지 정의로 세던 자리"),
    ('const name = "--shadow-card";', set(), {"--shadow-card"},
     "이름만 담은 문자열은 정의가 아니다"),
]


def self_test() -> int:
    bad = []
    for src, want, must_not, why in SELF_TEST_CASES:
        got = js_defined(src)
        missing = want - got
        extra = must_not & got
        if missing or extra:
            bad.append("%s: 놓침 %s / 잘못 인정 %s"
                       % (why, sorted(missing) or "-", sorted(extra) or "-"))
    if bad:
        print("[FAIL] 검사기 자체가 고장 났다 — 초록이 아무것도 증명하지 못한다:")
        for line in bad:
            print("  -", line)
        return 1
    print("[OK ] CSS_VARS_SELF_TEST_OK (사례 %d개, 정의·비정의 양방향)" % len(SELF_TEST_CASES))
    return 0


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def collect(roots: list[Path], patterns: tuple[str, ...]) -> list[Path]:
    out: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for pattern in patterns:
            out += [p for p in root.rglob(pattern) if "node_modules" not in p.parts]
    return sorted(set(out))


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    if self_test() != 0:
        return 1
    css_files = collect(CSS_ROOTS, ("*.css",))
    js_files = collect(JS_ROOTS, ("*.js", "*.jsx"))
    if not css_files:
        print("검사할 CSS가 없다", file=sys.stderr)
        return 1

    # 정의: 어느 CSS 파일에서든 선언되면 정의된 것으로 본다(파일 간 참조가 정상이다).
    defined: set[str] = set()
    for path in css_files:
        defined |= set(DEFINE.findall(read(path)))

    # JS 가 런타임에 넣는 변수도 정의된 것으로 친다 — **넣는 것만**이다(위 docstring 참조).
    js_blob = "\n".join(read(p) for p in js_files)
    runtime_defined = js_defined(js_blob)

    problems: list[tuple[str, int, str]] = []
    for path in css_files:
        for lineno, line in enumerate(read(path).splitlines(), 1):
            for name in USE_NO_FALLBACK.findall(line):
                if name in defined or name in runtime_defined:
                    continue
                problems.append((str(path.relative_to(ROOT)).replace("\\", "/"), lineno, name))

    if problems:
        print("[FAIL] 정의된 적 없는 CSS 변수를 fallback 없이 참조한다:", file=sys.stderr)
        print("       (그 선언 하나가 아니라 선언 전체가 무효가 된다)", file=sys.stderr)
        for rel, lineno, name in problems:
            print(f"  - {rel}:{lineno}  var({name})", file=sys.stderr)
        print("", file=sys.stderr)
        print(f"  고치는 법: 변수를 정의하거나 var({problems[0][2]}, <기본값>) 로 fallback 을 줘라.",
              file=sys.stderr)
        return 1

    print(f"CSS_VARS_OK (CSS {len(css_files)}개 · JS {len(js_files)}개, "
          f"CSS 정의 {len(defined)}개 · JS 런타임 정의 {len(runtime_defined)}개)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
