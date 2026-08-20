"""Brand 토큰이 실제로 제품에 도달하는지 검사한다 (PLAN §Theme 마이그레이션, 지시 0-1).

이 저장소는 정확히 두 가지 방식으로 Brand 를 잃어버렸고, 둘 다 시험이 없었다.

**1. Brand 토큰에 소비처가 0이었다.** `palette.brand` 에 네 개의 Brand 색이 정의돼 있었지만
`theme.js` 밖에서 아무도 읽지 않았다. 팔레트는 초록이고 문서도 초록인데 화면에는 Brand 가
없다 — "정의했다"와 "쓴다" 사이에 검사가 없으면 이 상태가 조용히 유지된다.

**2. 화면 파일이 자기 그라디언트를 들고 있었다.** 그래서 Chrome Gradient 가 한 번도 측정되지
않은 채 배포됐다(Sidebar 는 flat 대비만 1건, Topbar Gradient 는 0건). 색이 테마 밖에 있으면
대비 시험이 그 색의 존재 자체를 모른다.

그래서 이 검사는 둘을 막는다:

  (a) `frontend/src/screens/**` 와 `frontend/src/app/**` 에 raw gradient 리터럴 금지.
      Gradient 는 제품에 정확히 넷이고 전부 `palette.gradient` 에서 나온다.
  (b) `palette.brand` 에 `theme.js` 밖 소비처가 최소 하나 있어야 한다.

쓰는 법:  python scripts/check_brand_tokens.py
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
THEME = SRC / "ui" / "theme.js"

# (a) — 화면 계층. `ui/` 는 공유 Primitive 라 Wave 진행에 따라 범위를 넓힌다(현재 잔존:
# `ui/Mascot.jsx` 의 Clovi Halo — 색은 이미 Brand 토큰에서 오지만 모양은 아직 인라인이다).
GRADIENT_SCOPES = ("screens", "app")
GRADIENT_RE = re.compile(r"\b(linear|radial|conic)-gradient\s*\(")

# PLAN 은 이 검사의 범위로 `screens/**` 와 `app/**` 를 지정했다. 위 두 스코프는 SPA 쪽
# `frontend/src/{screens,app}` 이고, **저장소 root 의 `app/`(Jinja 화면)** 은 빠져 있었다 —
# 독립 Requirement Reviewer 가 잡았다. 여기서 그 구멍을 닫되, 두 파일은 사유와 소유 Wave 를
# 적어 예외로 둔다. 예외를 **코드에** 두는 이유는 문서에만 적으면 다음 사람이 검사 출력을
# 보고 "전부 통과"로 읽기 때문이다.
JINJA_CSS_DIR = ROOT / "app" / "static" / "css"
JINJA_CSS_ALLOW = {
    # 생성 파일. 네 Gradient 토큰이 여기서 나온다 — 이 파일이 리터럴을 갖는 것이 정상이다.
    "tokens.css": "생성 파일(generate_design_tokens.mjs) — Gradient 토큰의 출력 자리다",
    # 승인된 디자인 원본. `.hero` 는 W1 이 `var(--gradient-hero)` 로 승격했고, 남은 것은
    # 페이지 배경의 ambient orb 두 겹과 `.form-panel` 한 겹이다. 값 자체가 승인된 원본이라
    # W1 이 임의로 바꾸지 않는다 — Hostname/Identity 를 다루며 로그인 화면을 손대는 W13 소유.
    "login.css": "승인된 로그인 원본의 ambient orb / form-panel 배경 — 값 변경은 W13 소유 (F-W1R-42)",
    "auth.css": "로그인·비밀번호 화면 공용 리셋. 자체 팔레트 fork 도 W13 이 함께 정리한다",
    "change_password.css": "비밀번호 변경 화면 배경 — login.css 와 같은 계열, W13 소유",
}

# (b) — Brand 토큰 소비. `palette.brand.x` / `theme.palette.brand` / `"brand.x"` 셋 다 센다.
BRAND_USE_RE = re.compile(r"palette\.brand\b|[\"']brand\.[a-zA-Z]")

# (c) — Chart 시리즈 팔레트 소비. (b) 와 **같은 실패가 다른 토큰 가족에서 반복됐다**:
# `CHART_SERIES`/`CHART_DASH` 는 W1 이 만들고 `palette.chart` 로 내보냈는데 제품 소비처가
# 0곳이었다. 그동안 화면에 실제로 나간 색은 `charts/base.jsx` 의 옛 기본값 `primary.main`
# — 즉 **사용자 Accent** 였고, dark 에서 plate 대비 2.90:1 로 비텍스트 3:1 을 깼다.
# 그런데 `theme-contract.test.js` 는 아무도 안 쓰는 `palette.chart`(6.81:1)를 재고 초록이었다.
# (b) 를 만든 이유("정의만 있고 화면에 도달하지 않는다")가 그대로 반복된 것이라 규칙도 그대로 둔다.
CHART_USE_RE = re.compile(r"palette\.chart\b|\bCHART_DASH\b|\bCHART_SERIES\b")


def source_files(base: Path):
    for path in sorted(base.rglob("*")):
        if path.suffix not in (".js", ".jsx"):
            continue
        if ".test." in path.name:
            continue
        yield path


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def main() -> int:
    problems: list[str] = []

    scanned = 0
    for scope in GRADIENT_SCOPES:
        base = SRC / scope
        if not base.exists():
            continue
        for path in source_files(base):
            scanned += 1
            text = path.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(text.splitlines(), 1):
                if GRADIENT_RE.search(line):
                    problems.append(
                        f"{rel(path)}:{i} raw gradient 리터럴 — "
                        f"`palette.gradient.{{shell|ai|hero|mark}}` 에서 받아라"
                    )

    jinja_scanned = 0
    if JINJA_CSS_DIR.exists():
        for path in sorted(JINJA_CSS_DIR.glob("*.css")):
            jinja_scanned += 1
            if path.name in JINJA_CSS_ALLOW:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(text.splitlines(), 1):
                if GRADIENT_RE.search(line):
                    problems.append(
                        f"{rel(path)}:{i} raw gradient 리터럴 — "
                        f"`var(--gradient-{{shell|ai|hero|mark}})` 에서 받아라"
                    )

    consumers = []
    chart_consumers = []
    for path in source_files(SRC):
        if path == THEME:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if BRAND_USE_RE.search(text):
            consumers.append(rel(path))
        if CHART_USE_RE.search(text):
            chart_consumers.append(rel(path))

    if not consumers:
        problems.append(
            "palette.brand 에 theme.js 밖 소비처가 없다 — Brand 색이 정의만 되고 "
            "화면에 도달하지 않는 상태다(이번 리뉴얼 이전의 실제 상태)"
        )

    if not chart_consumers:
        problems.append(
            "palette.chart / CHART_SERIES 에 theme.js 밖 소비처가 없다 — Chart 시리즈 색이 "
            "정의만 되고 화면에 도달하지 않는 상태다. 그러면 실제 렌더 색은 사용자 Accent 로 "
            "떨어지고, 토큰만 재는 대비 시험은 그 사실을 모른 채 초록으로 남는다(W5 실측)"
        )

    if problems:
        print("[FAIL] Brand 토큰 검사 실패:")
        for line in problems:
            print(f"  - {line}")
        return 1

    print(
        f"[OK ] BRAND_TOKENS_OK (gradient 범위 SPA {scanned}개 + Jinja CSS {jinja_scanned}개"
        f"(예외 {len(JINJA_CSS_ALLOW)}) · palette.brand 소비처 {len(consumers)}곳"
        f" · palette.chart 소비처 {len(chart_consumers)}곳)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
