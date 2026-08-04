"""손으로 쓴 CSS 중 아무도 안 쓰는 클래스를 찾는다.

왜 필요한가: MUI로 전면 이관하면서 화면들이 sx/테마로 옮겨갔고, 예전 클래스는
파일에만 남았다. CSS는 지워도 빌드가 안 깨지고 테스트도 안 깨진다 — 그래서
아무도 안 지우고, 다음 사람은 그게 살아있는 규칙인 줄 알고 따라 쓴다.

**보수적으로** 판정한다. 잘못 지우면 화면이 조용히 깨지는데, 그건 빌드도
테스트도 못 잡는 종류의 사고다. 그래서:
  - 클래스 이름을 소스 전체에서 **부분 문자열**로 찾는다. `clsx`, 템플릿 리터럴,
    `"c-btn " + variant` 같은 동적 조립도 걸리게 하려는 것이다.
  - 접두사 조립(`` `c-btn-${size}` ``)을 감안해, 이름의 마지막 하이픈 앞부분이
    소스에 있으면 '쓰일 수 있음'으로 본다.
  - CSS 안에서만 참조되는 것(다른 셀렉터의 일부)도 사용으로 치지 않는다 —
    그건 죽은 규칙끼리 서로를 참조하는 것뿐이다.

즉 **여기서 '미사용'이라고 나온 것만** 지우면 안전하고, 놓치는 것이 있어도
그건 남겨두는 방향이라 사고가 안 난다.

사용법:
  .venv/Scripts/python.exe scripts/find_dead_css.py              # 요약
  .venv/Scripts/python.exe scripts/find_dead_css.py --list       # 미사용 전체 목록
  .venv/Scripts/python.exe scripts/find_dead_css.py --used       # 사용 중인 것 목록
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS_DIR = ROOT / "frontend" / "src" / "styles"
SOURCE_GLOBS = ("*.js", "*.jsx", "*.html")
SOURCE_ROOTS = (
    ROOT / "frontend" / "src",
    ROOT / "app" / "templates_html",
    ROOT / "app" / "static" / "js",
)

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# 셀렉터의 클래스만 뽑는다. 선언 블록 안(`color: .5`)은 걸리지 않게 줄 시작 쪽 셀렉터만 본다.
CLASS_IN_SELECTOR = re.compile(r"\.(-?[_a-zA-Z][_a-zA-Z0-9-]*)")


def css_files() -> list[Path]:
    """SPA 가 실제로 로드하는 손수 쓴 CSS 전부.

    styles/ 만 보면 ui/kit.css 가 빠진다 — main.jsx 는 그 파일도 import 하는데 검사에서만
    빠져 있어서, 화면을 MUI 로 옮겨 규칙이 죽어도 아무도 알려 주지 않았다.
    """
    out = sorted(p for p in CSS_DIR.glob("*.css")) if CSS_DIR.exists() else []
    kit = ROOT / "frontend" / "src" / "ui" / "kit.css"
    if kit.exists():
        out.append(kit)
    return out


def declared_classes(path: Path) -> set[str]:
    """셀렉터에 나오는 클래스 이름. 선언 블록은 건너뛴다."""
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)  # 주석 제거
    found: set[str] = set()
    depth = 0
    buf: list[str] = []
    for ch in text:
        if ch == "{":
            if depth == 0:
                found |= set(CLASS_IN_SELECTOR.findall("".join(buf)))
            buf = []
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
            buf = []
        elif depth == 0:
            buf.append(ch)
    return found


def source_blob() -> str:
    """CSS 를 제외한 모든 소스를 한 덩어리로. 부분 문자열 검색용."""
    parts: list[str] = []
    for root in SOURCE_ROOTS:
        if not root.exists():
            continue
        for pattern in SOURCE_GLOBS:
            for path in root.rglob(pattern):
                if "node_modules" in path.parts:
                    continue
                try:
                    parts.append(path.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError):
                    continue
    return "\n".join(parts)


def is_used(name: str, blob: str) -> bool:
    if name in blob:
        return True
    # `` `c-btn-${size}` `` 처럼 접두사만 소스에 있는 경우를 살려 준다.
    if "-" in name:
        prefix = name.rsplit("-", 1)[0] + "-"
        if len(prefix) >= 4 and prefix in blob:
            return True
    return False


def main() -> int:
    files = css_files()
    if not files:
        print(f"CSS 디렉터리가 없다: {CSS_DIR}", file=sys.stderr)
        return 1

    blob = source_blob()
    show_list = "--list" in sys.argv
    show_used = "--used" in sys.argv

    total_declared = 0
    total_dead = 0
    print(f"소스 검색 대상 {len(blob):,} 글자\n")
    print(f"{'파일':<20} {'선언':>6} {'사용':>6} {'미사용':>7}")
    print("-" * 44)
    per_file: dict[str, list[str]] = {}
    for path in files:
        declared = declared_classes(path)
        dead = sorted(n for n in declared if not is_used(n, blob))
        used = sorted(n for n in declared if is_used(n, blob))
        per_file[path.name] = dead
        total_declared += len(declared)
        total_dead += len(dead)
        print(f"{path.name:<20} {len(declared):>6} {len(used):>6} {len(dead):>7}")
        if show_used and used:
            for n in used:
                print(f"      (사용) .{n}")
    print("-" * 44)
    print(f"{'합계':<20} {total_declared:>6} {total_declared - total_dead:>6} {total_dead:>7}")

    if show_list:
        for name, dead in per_file.items():
            if not dead:
                continue
            print(f"\n== {name} — 미사용 {len(dead)}개 ==")
            for n in dead:
                print(f"  .{n}")

    print(
        "\n판정은 보수적이다(부분 문자열 + 접두사 조립 허용). "
        "여기서 미사용으로 나온 것만 지우면 안전하다."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
