"""MUI `sx` 의 **논리 테두리 속성**이 실제로 그려지는 형태인지 검사한다 (W4).

## 왜 필요한가 — 같은 함정을 세 자리에서 밟았다

`@mui/system` 의 border 스타일 함수(`borders/borders.js` 의 `compose` 목록)가 펴 주는 이름은
물리 속성뿐이다: `border` · `borderTop|Right|Bottom|Left` · `border*Color` · `borderRadius` ·
`outline*`. **논리 속성(`borderInlineStart` 등)은 그 목록에 없다.**

그래서 `sx={{ borderInlineStart: 1 }}` 는 MUI 를 그냥 통과해 emotion 에 닿고, emotion 은
숫자에 단위를 붙여 `border-inline-start: 1px` 를 낸다. 그 선언에는 **`style` 이 없다** —
`border-style` 의 초기값이 `none` 이라 **아무것도 그려지지 않는다.** 콘솔에도 시험에도 아무
흔적이 없고, 코드에는 테두리를 그리라고 적혀 있다.

이 저장소에서 실제로 일어난 일이다.

  * W2 — `AppShell.jsx` 사이드바 바깥 모서리, `CommandPalette.jsx` 선택 레일.
    두 자리 모두 자기 Wave 안에서 발견하고 세 속성으로 고쳤다.
  * W4 — `ui/kit.jsx` 세 자리(`Callout` 앞머리 선 · `MetricStrip` 칸 구분선 · `MetaBar` 칸
    구분선). 배포본 실측에서 `user_me.png` 판독 줄 `y=240` 이 `x=621~1886` 단일 흰 런이었다 —
    **칸 구분선 픽셀 0개**(F-W2R-01).

같은 자리를 세 번 밟았으면 그건 사람이 기억할 문제가 아니다.

## 무엇을 보는가

세 가지 형태를 잡는다. 셋 다 "선언은 있는데 화면에는 없다" 로 끝난다.

  1. **shorthand 에 style 이 없다** — `borderInlineStart: 2`, `borderBlockEnd: "1px"`.
  2. **width 만 있고 style 이 없다** — `borderInlineStartWidth: 1` 만 두고 같은 객체에
     `...Style` 도 `borderStyle` 도 없다.
  3. **`...Color` 에 팔레트 경로를 문자열로 준다** — `borderInlineStartColor: "divider"`.
     MUI 가 해석해 주는 것은 물리 이름(`borderColor`/`border*Color`) 뿐이라
     `border-inline-start-color: divider` 라는 무효 선언이 나간다.

정상형은 둘이다.

    borderInlineStartStyle: "solid",
    borderInlineStartWidth: "3px",
    borderInlineStartColor: (t) => t.palette.chrome.rail,

    borderInlineStart: "3px solid", borderColor: "divider",   // style 이 들어 있다

물리 속성(`borderLeft: 1` 등)은 대상이 아니다 — MUI 가 `1px solid` 로 펴 준다. 그것이 이
함정이 눈에 안 띄었던 이유이기도 하다: 바로 옆 줄의 `borderTop: 1` 은 멀쩡히 그려진다.

지우는 선언(`borderInline: 0`)도 대상이 아니다 — 폭을 0 으로 만드는 것이 목적이고 실제로
그렇게 된다(`kit.jsx` 의 표가 세로 괘선을 지울 때 쓴다).

CSS 파일은 보지 않는다 — 거기서는 무효 선언이 브라우저 파서에 걸려 개발자 도구에 그대로
표시된다. 문제는 **JS 객체를 거쳐 조용히 사라지는** 경로다.

주석은 지우고 본다. 고친 자리마다 "예전에는 `borderInlineStart: 2` 였다" 라고 **금지 형태를
인용**해 두었기 때문이다 — 인용을 세면 고친 자리가 영원히 실패한다
(`check_ui_renewal_coverage.py` 가 같은 이유로 규칙 문장을 스스로 제외한다).
시험 파일도 같은 이유로 제외한다.

## 검사기 자신을 먼저 검사한다

`--self-test` 가 열한 사례로 검출과 위양성을 양방향 확인한다. 본 실행도 자기 검사를 먼저
통과해야 한다 — 초록이 무엇을 뜻하는지 초록 자신이 증명하게 한다. 첫 판이 실제로 위양성
넷을 냈다(주석 안의 인용 둘 · 콜백 색 둘 · 지우는 선언 하나) — 프로브를 대상보다 먼저
의심한 결과가 아래 사례 목록이다.

## 쓰는 법

    python scripts/check_logical_border_props.py
    python scripts/check_logical_border_props.py --self-test
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "frontend" / "src"

SIDES = r"(?:Inline|Block)(?:Start|End)?"
STYLE_WORDS = r"(?:solid|dashed|dotted|double|groove|ridge|inset|outset|none|hidden)"

# shorthand: `borderInlineStart: <값>`. 뒤에 Width/Style/Color 가 붙은 것은 longhand 라 제외.
SHORTHAND_RE = re.compile(
    r"\bborder(?P<side>" + SIDES + r")\s*:\s*(?P<value>[^,\n}]+)")
WIDTH_RE = re.compile(r"\bborder(?P<side>" + SIDES + r")Width\s*:")
COLOR_RE = re.compile(r"\bborder(?P<side>" + SIDES + r")Color\s*:\s*(?P<value>[^,\n}]+)")

STYLE_NEARBY_RE = re.compile(r"\bborder(?:" + SIDES + r")?Style\s*:")
# `...Style` 이 같은 객체 안에 있는지 볼 범위. 한 sx 객체가 이보다 길면 그건 다른 문제다.
STYLE_WINDOW = 400

# 색을 **해석된 값**으로 준 형태. 이 중 하나면 통과다.
RESOLVED_COLOR_RE = re.compile(
    r"^\s*(?:"
    r"\(\s*[A-Za-z_$][\w$]*\s*\)\s*=>"          # (t) => t.palette.… (W2 가 배포본 픽셀로 검증)
    r"|[A-Za-z_$][\w$]*\s*[.(\[]"               # alpha(…) · theme[…] · t.palette…
    r"|`"                                        # 템플릿 리터럴
    r"|[\"']#"                                   # 리터럴 hex
    r"|[\"'](?:rgb|hsl|var|color-mix)"
    r"|[\"'](?:transparent|currentColor|inherit|initial|unset)[\"']"
    r")")

# 지우는 선언. `borderInline: 0` 은 폭을 0 으로 만들어 실제로 지운다.
CLEARING_RE = re.compile(r"^(?:0|[\"']0[\"']|[\"']none[\"'])$")

BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
LINE_COMMENT_RE = re.compile(r"(?<![:\w])//[^\n]*")

FIX_HINT = ("논리 테두리는 MUI 가 펴 주지 않는다 — "
            "`...Style` + `...Width` + `...Color`(해석된 값) 세 속성으로 쓴다")


def strip_comments(text: str) -> str:
    """줄 번호가 어긋나지 않게 주석을 **같은 길이의 공백**으로 바꾼다."""
    def blank(m: re.Match) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))
    return LINE_COMMENT_RE.sub(blank, BLOCK_COMMENT_RE.sub(blank, text))


def _has_style_nearby(text: str, pos: int) -> bool:
    if STYLE_NEARBY_RE.search(text, pos, pos + STYLE_WINDOW):
        return True
    return bool(STYLE_NEARBY_RE.search(text, max(0, pos - STYLE_WINDOW), pos))


def scan(raw: str, rel: str) -> list[str]:
    out: list[str] = []
    text = strip_comments(raw)

    def line_of(pos: int) -> int:
        return text.count("\n", 0, pos) + 1

    for m in SHORTHAND_RE.finditer(text):
        value = m.group("value").strip().rstrip(",")
        if re.search(STYLE_WORDS, value):
            continue                       # `"3px solid"` — style 이 들어 있다
        if CLEARING_RE.match(value):
            continue                       # `borderInline: 0` — 지우는 선언
        out.append("%s:%d: border%s: %s — border-style 이 없어 렌더되지 않는다. %s"
                   % (rel, line_of(m.start()), m.group("side"), value, FIX_HINT))

    for m in WIDTH_RE.finditer(text):
        if _has_style_nearby(text, m.start()):
            continue
        out.append("%s:%d: border%sWidth 만 있고 border-style 이 없다 — 렌더되지 않는다. %s"
                   % (rel, line_of(m.start()), m.group("side"), FIX_HINT))

    for m in COLOR_RE.finditer(text):
        value = m.group("value").strip().rstrip(",")
        if RESOLVED_COLOR_RE.match(value):
            continue
        out.append("%s:%d: border%sColor: %s — 논리 이름에는 MUI 가 팔레트 경로를 "
                   "해석해 주지 않는다. 실제 색을 넣어라(테마 콜백 · hex · var())"
                   % (rel, line_of(m.start()), m.group("side"), value))

    return out


def offenders() -> list[str]:
    out: list[str] = []
    for path in sorted(SRC.rglob("*.js*")):
        if ".test." in path.name:
            continue
        out += scan(path.read_text(encoding="utf-8", errors="replace"),
                    path.relative_to(ROOT).as_posix())
    return out


SELF_TEST_CASES = [
    # (소스, 걸려야 하는가, 무엇을 지키는 사례인가)
    ('sx={{ borderInlineStart: 2, borderColor: `${paletteKey}.main` }}',
     True, "숫자 shorthand — F-W2R-01 의 원형"),
    ('sx={{ borderInlineStart: "1px", borderColor: "divider" }}',
     True, "style 없는 문자열 shorthand"),
    ('sx={{ borderInlineStartWidth: "3px", borderInlineStartColor: t.palette.chrome.rail }}',
     True, "width 만 있고 style 이 없다"),
    ('sx={{ borderBlockEnd: 1 }}',
     True, "블록 축도 같은 함정이다"),
    ('sx={{ borderInlineStartStyle: "solid", borderInlineStartWidth: 1,'
     ' borderInlineStartColor: "divider" }}',
     True, "색이 팔레트 경로 문자열이라 안 풀린다"),
    ('sx={{ borderInlineStartStyle: "solid", borderInlineStartWidth: "3px",'
     ' borderInlineStartColor: (t) => t.palette.chrome.rail }}',
     False, "정상형 — 세 속성 + 콜백 색"),
    ('sx={{ borderInlineStart: "3px solid", borderColor: "divider" }}',
     False, "style 이 들어 있는 shorthand"),
    ('sx={{ borderLeft: 1, borderTop: 2, borderColor: "divider" }}',
     False, "물리 속성은 MUI 가 펴 준다 — 위양성이면 안 된다"),
    ('sx={{ "& td, & th": { borderInline: 0 } }}',
     False, "지우는 선언 — 폭 0 은 실제로 지운다"),
    ('sx={{ borderInlineStartStyle: "solid", borderInlineStartWidth: 1,'
     ' borderInlineStartColor: "#A9BAFF" }}',
     False, "리터럴 hex 색"),
    ('/* 예전에는 `borderInlineStart: 2` 만 두었는데 안 그려졌다. */\n'
     'sx={{ borderInlineStartStyle: "solid", borderInlineStartWidth: "2px",'
     ' borderInlineStartColor: "transparent" }}',
     False, "주석 안의 인용 — 고친 자리가 자기 설명 때문에 실패하면 안 된다"),
]


def self_test() -> int:
    bad = []
    for src, should_flag, why in SELF_TEST_CASES:
        hits = scan(src, "<self-test>")
        if bool(hits) != should_flag:
            bad.append("%s: 기대 %s / 실제 %s%s"
                       % (why, "검출" if should_flag else "통과",
                          "검출" if hits else "통과",
                          (" — " + hits[0]) if hits and not should_flag else ""))
    if bad:
        print("[FAIL] 검사기 자체가 고장 났다 — 초록이 아무것도 증명하지 못한다:")
        for line in bad:
            print("  - %s" % line)
        return 1
    print("[OK ] LOGICAL_BORDER_SELF_TEST_OK (사례 %d개, 검출·위양성 양방향)"
          % len(SELF_TEST_CASES))
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    if self_test() != 0:
        return 1
    bad = offenders()
    if bad:
        print("[FAIL] 논리 테두리가 선언만 있고 그려지지 않는다:")
        for line in bad:
            print("  - %s" % line)
        return 1
    print("[OK ] LOGICAL_BORDER_OK (선언만 있고 안 그려지는 논리 테두리 0건)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
