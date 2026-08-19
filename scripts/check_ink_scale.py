"""`text.faint` 를 **AA-large 자리**에만 쓰게 강제한다 (W4 · F-W1R-03 / F-W1-02).

## 왜 필요한가

이 제품의 잉크는 세 단계다: `text.primary` · `text.secondary` · `text.faint`.
그런데 오랫동안 **셋이 아니라 둘**이었다 — `secondary`(#565E7A)와 `faint`(#5C6480)의 대비가
**1.10:1** 이라 눈으로는 같은 색이었다(다크 1.19:1). 독립 검수가 배포본 캡처에서 그 붕괴를
짚었다(F-W1R-03): `/projects` 의 «평균 진행률» 라벨과 그 아래 보조 설명이 같은 무게로 읽힌다.

값 선택 실수가 아니라 제약이었다. 다섯 면(plate·inset·canvas·sunken·brandTint) 전부에서
AA(4.5)를 요구하면 가장 어두운 면 기준 여유가 1.16배뿐이라 세 단계를 벌릴 자리가 없다.
`theme.js` 는 그 사실을 적어 두고 판단을 W4 로 넘겼다.

**W4 의 결정은 값을 미는 것이 아니라 역할을 좁히는 것이다.** `faint` 는 본문 잉크에서
빠지고 AA-large(3:1)가 허용되는 자리로 한정된다. 그 대가로 값을 실제로 벌려
`secondary` 와의 분리도가 1.53(L)/1.60(D)이 됐다.

문서로만 적으면 다음 사람이 13px 각주에 `text.faint` 를 쓴다 — 그러면 3단 위계는 조용히
다시 2단이 되고, 아무 시험도 그것을 말하지 않는다. 그래서 검사로 고정한다.

## 무엇이 AA-large 자리인가 (WCAG 1.4.3)

  * 18.66px 이상 텍스트 -> `FONT_SIZE.title`(19) · `pageTitle`(28) · `readout`(40)
  * 굵은 14px 이상 텍스트 -> `FONT_SIZE.bodySm` 이상 + `FONT_WEIGHT.semibold|bold`
  * **텍스트가 아닌 것** -> `aria-hidden` 글리프·표지, 그리고 `color` 가 아닌 속성
    (`bgcolor`·`background`·`fill`·`borderColor` 등)
  * `text.disabled` -> WCAG 는 비활성 요소를 대비 요구에서 제외한다. 팔레트에서 같은 값을
    가리키지만 이 검사는 `text.faint` 라는 **이름**만 본다

## 판정 방식과 그 한계

정적으로 "이 글자가 몇 px 인가" 를 정확히 알 수는 없다. 그래서 **모르면 실패**로 둔다
(`contrast.py` 의 "모르면 모른다고 한다" 규율과 같다). 근처(±400자)에서 AA-large 근거를
찾지 못하면 실패하고, 정당한 자리는 근거를 코드에 드러내면 통과한다 — 즉 이 검사는
"근거를 옆에 적어라" 는 요구이기도 하다.

CSS 도 같은 규칙으로 본다: `color: var(--color-faint)` 를 쓰는 규칙은 같은 규칙 안에
`font-size` 가 1.1875rem 이상이어야 한다.

## 검사기 자신을 먼저 검사한다

`--self-test` 가 아홉 사례로 검출과 위양성을 양방향 확인한다. 본 실행도 자기 검사를 먼저
통과해야 한다.

## 쓰는 법

    python scripts/check_ink_scale.py
    python scripts/check_ink_scale.py --self-test
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

WINDOW = 400

# 잉크로 쓰이는 자리만 본다. `bgcolor:`/`fill:`/`borderColor:` 등은 텍스트가 아니다.
COLOR_USE_RE = re.compile(r"\bcolor\s*[:=]\s*[^,\n]*?[\"']text\.faint[\"']")
# 잉크가 아닌 자리(표지 점 등)까지 세지 않으려면 위 정규식이 `bgcolor` 를 배제해야 한다.
NON_INK_PREFIX_RE = re.compile(r"[A-Za-z]color\s*[:=]\s*$", re.I)

AA_LARGE_SIZE_RE = re.compile(r"FONT_SIZE\.(title|pageTitle|readout|sectionTitle|statValue)\b")
BOLD_SMALL_RE = re.compile(r"FONT_SIZE\.bodySm\b[\s\S]{0,120}?FONT_WEIGHT\.(semibold|bold)\b")
ARIA_HIDDEN_RE = re.compile(r"aria-hidden")

BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
LINE_COMMENT_RE = re.compile(r"(?<![:\w])//[^\n]*")

CSS_FAINT_RE = re.compile(r"color\s*:\s*var\(\s*--color-faint")
CSS_RULE_RE = re.compile(r"\{[^{}]*\}", re.S)
CSS_FONT_SIZE_RE = re.compile(r"font-size\s*:\s*([0-9.]+)rem")
AA_LARGE_REM = 1.1875

HINT = ("`text.faint` 는 AA-large 자리 전용이다(18.66px 이상 · 굵은 14px 이상 · 비텍스트). "
        "본문 크기 글자에는 `text.secondary` 를 쓰고, 셋째 단계가 필요하면 색이 아니라 "
        "크기와 자리로 만든다")


def strip_comments(text: str) -> str:
    def blank(m: re.Match) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))
    return LINE_COMMENT_RE.sub(blank, BLOCK_COMMENT_RE.sub(blank, text))


def scan_js(raw: str, rel: str) -> list[str]:
    out: list[str] = []
    text = strip_comments(raw)
    for m in COLOR_USE_RE.finditer(text):
        head = text[max(0, m.start() - 24):m.start() + 6]
        if NON_INK_PREFIX_RE.search(head[: head.find("text.faint")] if "text.faint" in head else head):
            continue  # bgcolor / borderColor 등 — 잉크가 아니다
        near = text[max(0, m.start() - WINDOW):m.start() + WINDOW]
        if ARIA_HIDDEN_RE.search(near):
            continue
        if AA_LARGE_SIZE_RE.search(near):
            continue
        if BOLD_SMALL_RE.search(near):
            continue
        line = text.count("\n", 0, m.start()) + 1
        out.append("%s:%d: color=text.faint 인데 근처에 AA-large 근거가 없다. %s" % (rel, line, HINT))
    return out


def scan_css(raw: str, rel: str) -> list[str]:
    out: list[str] = []
    for m in CSS_RULE_RE.finditer(raw):
        body = m.group(0)
        if not CSS_FAINT_RE.search(body):
            continue
        size = CSS_FONT_SIZE_RE.search(body)
        if size and float(size.group(1)) >= AA_LARGE_REM:
            continue
        line = raw.count("\n", 0, m.start()) + 1
        out.append("%s:%d: color: var(--color-faint) 인데 이 규칙의 font-size 가 "
                   "%s 다(1.1875rem 이상이어야 한다). %s"
                   % (rel, line, size.group(1) + "rem" if size else "선언되지 않았다", HINT))
    return out


def offenders() -> list[str]:
    out: list[str] = []
    for path in sorted(SRC.rglob("*.js*")):
        if ".test." in path.name:
            continue
        out += scan_js(path.read_text(encoding="utf-8", errors="replace"),
                       path.relative_to(ROOT).as_posix())
    for path in sorted(SRC.rglob("*.css")):
        out += scan_css(path.read_text(encoding="utf-8", errors="replace"),
                        path.relative_to(ROOT).as_posix())
    return out


SELF_TEST_CASES = [
    ('<Typography sx={{ fontSize: FONT_SIZE.caption, color: "text.faint" }}>각주</Typography>',
     True, "13px 각주에 faint — F-W1R-03 의 원형"),
    ('<Typography color="text.faint" sx={{ fontSize: FONT_SIZE.body }}>값</Typography>',
     True, "15px 본문에 faint"),
    ('<Box sx={{ color: "text.faint" }}>알 수 없음</Box>',
     True, "크기 근거가 아예 없다 — 모르면 실패한다"),
    ('<Box sx={{ fontSize: FONT_SIZE.readout, color: "text.faint" }}>{icon}</Box>',
     False, "40px 글리프 — AA-large"),
    ('<Typography sx={{ fontSize: FONT_SIZE.title, color: "text.faint" }}>제목</Typography>',
     False, "19px — AA-large 하한을 넘는다"),
    ('<Box aria-hidden="true" sx={{ color: "text.faint" }}><Icon /></Box>',
     False, "aria-hidden 글리프 — 텍스트가 아니다"),
    ('<Box sx={{ bgcolor: "text.faint", width: 6, height: 6 }} />',
     False, "표지 점의 배경색 — 잉크가 아니다"),
    ('<Typography sx={{ fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.semibold,'
     ' color: "text.faint" }}>굵은 14px</Typography>',
     False, "굵은 14px — AA-large"),
    ('sx={{ borderColor: "text.faint" }}',
     False, "테두리색 — 잉크가 아니다"),
]

CSS_SELF_TEST_CASES = [
    (".x { color: var(--color-faint); font-size: 0.8125rem; }", True, "13px CSS 규칙"),
    (".x { color: var(--color-faint); font-size: 1.75rem; }", False, "28px CSS 규칙"),
    (".x { color: var(--color-faint); }", True, "font-size 가 없는 CSS 규칙"),
]


def self_test() -> int:
    bad = []
    for src, should_flag, why in SELF_TEST_CASES:
        hits = scan_js(src, "<self-test>")
        if bool(hits) != should_flag:
            bad.append("JS %s: 기대 %s / 실제 %s" % (why, "검출" if should_flag else "통과",
                                                     "검출" if hits else "통과"))
    for src, should_flag, why in CSS_SELF_TEST_CASES:
        hits = scan_css(src, "<self-test>")
        if bool(hits) != should_flag:
            bad.append("CSS %s: 기대 %s / 실제 %s" % (why, "검출" if should_flag else "통과",
                                                      "검출" if hits else "통과"))
    if bad:
        print("[FAIL] 검사기 자체가 고장 났다 — 초록이 아무것도 증명하지 못한다:")
        for line in bad:
            print("  - %s" % line)
        return 1
    print("[OK ] INK_SCALE_SELF_TEST_OK (사례 %d개, 검출·위양성 양방향)"
          % (len(SELF_TEST_CASES) + len(CSS_SELF_TEST_CASES)))
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    if self_test() != 0:
        return 1
    bad = offenders()
    if bad:
        print("[FAIL] 본문 크기 글자에 `text.faint` 를 썼다 — 3단 잉크가 다시 2단이 된다:")
        for line in bad:
            print("  - %s" % line)
        return 1
    print("[OK ] INK_SCALE_OK (AA-large 밖에서 faint 를 쓰는 자리 0건)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
