"""MUI 아이콘에 **없는 prop** 을 넘기는 것을 금지한다 (PLAN «Icon System» 신규 static check ⓐ).

## 왜 필요한가

`@mui/icons-material` 의 글리프는 전부 `SvgIcon` 이다. `SvgIcon` 에는

  * `size` prop 이 **없다** — 크기는 `fontSize`(`"small"|"medium"|"large"` 또는 CSS 값)다.
  * `strokeWidth` 는 **무효다** — 이 글리프들은 fill 기반 도형이라 획 두께가 없다.

React 는 모르는 prop 을 그냥 DOM 으로 흘려보내므로 **아무 오류도 나지 않는다.** 화면에는
기본값(`fontSize: "medium"` = 24px)이 그려지고, 코드에는 `size={18}` 이 적혀 있다.

이건 가정이 아니라 이 저장소에서 실제로 일어난 일이다. `AppShell.jsx` 의 사이드바 자식
항목이 `<ItemIcon size={18} strokeWidth={1.8} />` 로 렌더돼 **24px** 로 그려졌고, 같은 화면의
부모 그룹 아이콘은 `fontSize="small"` 로 **20px** 이었다 — 정보 위계가 뒤집힌 채(자식이
부모보다 크다) 시험은 전부 초록이었다. Lucide(획 기반 계열)를 쓰던 시절의 관용이 계열
통일 뒤에도 남아 구현을 오도한 것이다(F-W1R-05 · F-W1R-38).

PLAN 은 이 검사를 W1 이 요구했지만 W1 은 넣을 수 **없었다** — 원본 버그가 살아 있는 상태에서
검사를 추가하면 즉시 실패해 모든 Wave 공통 Exit Gate E5(`static_checks.sh` 초록)가 깨진다.
가드는 수정과 **같은 커밋**에 실려야 한다. 그래서 W3 것이다.

## 무엇을 보는가

`size={…}` 와 `strokeWidth={…}` 를 **아이콘 컴포넌트에 넘길 때만** 잡는다. 아이콘인지의 판정은
파일마다 둘로 한다:

  1. 그 파일이 `@mui/icons-material/...` 에서 깊은 경로로 import 한 이름.
  2. 이름이 `Icon` 으로 끝나거나 `Icon` 인 것 — 이 저장소가 간접 참조에 쓰는 관용이다
     (`const GroupIcon = g.icon`, `const Icon = item.Icon`). 정규식으로 별칭 대입을 따라가면
     조용히 틀리므로 이름 규약을 계약으로 삼는다.

두 축 모두 **위양성을 먼저 의심한 결과**다. 첫 판은 대문자로 시작하는 모든 JSX 태그의
`size=` 를 잡았고 그 즉시 `<MuiButton size="small">` · `<CircularProgress size={18}>` ·
`<Modal size="lg">` · `<MascotPose size={96}>` 열 자리를 결함이라고 불렀다 — 전부 자기
`size` prop 을 실제로 구현한 컴포넌트다. 프로브가 대상보다 먼저 의심받아야 한다
(`scripts/ui_qa/README.md` 가 같은 교훈을 기록한다).

소문자 태그(`<svg>`·`<circle>`·`<path>`)는 애초에 대상이 아니다 — 거기서 `strokeWidth` 는
정당한 SVG 속성이고 차트가 실제로 쓴다.

시험 파일은 제외한다 — 시험은 이 형태가 **되돌아오지 않았는지** 문자열로 확인하는 쪽이라
자기가 금지 문자열을 인용한다(같은 이유로 `check_ui_renewal_coverage.py` 도 규칙 문장을
스스로 제외한다).

## 검사기 자신을 먼저 검사한다

`--self-test` 는 다섯 사례로 검출과 위양성을 **양방향** 확인한다. 이게 붙어 있는 이유는
겪었기 때문이다 — 처음 돌렸을 때 초록이었는데 그건 결함이 없어서가 아니라 정규식 하나가
조용히 망가져 있어서였다(같은 결함을 vitest 쪽이 잡아 준 덕에 드러났다). 초록이 무엇을
뜻하는지 초록 자신이 증명하게 한다. 본 실행도 자기 검사를 먼저 통과해야 한다.

## 쓰는 법

    python scripts/check_icon_props.py
    python scripts/check_icon_props.py --self-test
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

# JSX 여는 태그 하나. `<Name ... >` 또는 `<Name ... />`.
TAG_RE = re.compile(r"<([A-Z][A-Za-z0-9_]*)\b([^>]*?)/?>", re.S)
# `import Foo from "@mui/icons-material/BarOutlined";` — 깊은 경로만 쓴다(배럴 금지 검사가 따로 있다).
MUI_ICON_IMPORT_RE = re.compile(r"""import\s+([A-Za-z0-9_]+)\s+from\s+['"]@mui/icons-material/""")
BAD_PROP_RE = {
    "size": re.compile(r"\bsize=[{\"']"),
    "strokeWidth": re.compile(r"\bstrokeWidth=[{\"']"),
}


def icon_names(text: str) -> set[str]:
    """이 파일 안에서 '아이콘 컴포넌트'로 취급할 이름들."""
    names = set(MUI_ICON_IMPORT_RE.findall(text))
    names |= {m.group(1) for m in TAG_RE.finditer(text)
              if m.group(1) == "Icon" or m.group(1).endswith("Icon")}
    return names


def scan(text: str, rel: str) -> list[str]:
    out: list[str] = []
    icons = icon_names(text)
    if not icons:
        return out
    for m in TAG_RE.finditer(text):
        name, attrs = m.group(1), m.group(2)
        if name not in icons:
            continue
        for prop, rx in BAD_PROP_RE.items():
            if not rx.search(attrs):
                continue
            line = text.count("\n", 0, m.start()) + 1
            out.append(
                f"{rel}:{line}: <{name} {prop}=…> — MUI SvgIcon 에 없는 prop 이다. "
                f"크기는 sx=[[ fontSize: remPx(ICON.nav) ]] 로 준다"
            )
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
    ('import HomeIcon from "@mui/icons-material/HomeOutlined";\n<HomeIcon size={18} />',
     True, "MUI 아이콘에 size="),
    ('const GroupIcon = g.icon;\n<GroupIcon\n  strokeWidth={1.8}\n  aria-hidden="true"\n/>',
     True, "여러 줄 태그의 *Icon 간접 참조에 strokeWidth="),
    ('import HomeIcon from "@mui/icons-material/HomeOutlined";\n'
     '<HomeIcon sx={{ fontSize: remPx(ICON.nav) }} />',
     False, "sx.fontSize 로 준 정상 형태"),
    ('<MuiButton size="small" />\n<CircularProgress size={18} />\n<Modal size="lg" />',
     False, "자기 size prop 을 구현한 컴포넌트 — 위양성이면 안 된다"),
    ('<svg strokeWidth="1.6" />\n<circle strokeWidth={2} />',
     False, "raw SVG 의 정당한 획 두께"),
]


def self_test() -> int:
    bad = []
    for src, should_flag, why in SELF_TEST_CASES:
        hits = scan(src, "<self-test>")
        if bool(hits) != should_flag:
            bad.append("%s: 기대 %s / 실제 %s"
                       % (why, "검출" if should_flag else "통과", "검출" if hits else "통과"))
    if bad:
        print("[FAIL] 검사기 자체가 고장 났다 — 초록이 아무것도 증명하지 못한다:")
        for line in bad:
            print(f"  - {line}")
        return 1
    print(f"[OK ] ICON_PROPS_SELF_TEST_OK (사례 {len(SELF_TEST_CASES)}개, 검출·위양성 양방향)")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    if self_test() != 0:
        return 1
    bad = offenders()
    if bad:
        print("[FAIL] MUI 아이콘에 없는 prop 을 넘긴다 (조용히 무시되고 기본 24px 로 그려진다):")
        for line in bad:
            print(f"  - {line}")
        return 1
    print("[OK ] ICON_PROPS_OK (size= / strokeWidth= 로 아이콘 크기를 정하는 자리 0건)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
