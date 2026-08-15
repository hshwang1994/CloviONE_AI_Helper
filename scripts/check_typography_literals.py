"""타이포 리터럴 재유입 방지 검사 (PA-RC-0001 acceptance_criteria 5).

왜 필요한가: `FONT_SIZE`(6단계, `theme.js`)가 있는데도 화면 코드가 직접 `fontSize: "0.9375rem"`
처럼 raw 값을 쓰면 다시 리터럴이 흩어진다(이 Root Cause가 애초에 이런 식으로 생겼다 —
`fontSize`가 31종·278회였다). `fontWeight`는 이미 전량 토큰으로 옮겨져 있으니(0건) 그 상태를
그대로 지킨다.

`fontSize`는 `fontWeight`와 달리 **완전 금지가 아니다** — 아이콘 크기 지정(MUI 정상 관례),
서체 본문(prose), 입력창(iOS 확대 방지), 자격증명 표시(monospace), 이모지/아바타 글리프처럼
정당한 예외가 이미 있다. 그래서 새 값이 나오면 실패하고, `EXEMPT_FONT_SIZE_VALUES`에 있는
**이미 검증된 값**만 통과한다 — 값 하나하나를 실제 소스 문맥으로 직접 대조해서 넣었다
(2026-08-16, PA-RC-0001 7차 확장까지의 판정과 일치, `docs/DECISIONS.md` D-81).

파일이 아니라 **값** 단위로 면제한다 — 같은 값이 새 파일에 나와도 그 역할(아이콘 크기 등)이
바뀌지 않는 한 정당하기 때문이다(간격의 `p: 2`가 파일을 안 가리는 것과 같은 이유). 대신
**새로운 값**은 무조건 걸린다 — 그게 이 검사의 핵심이다: 6단계 스케일을 두고 굳이 또 다른
raw 값을 새로 만드는 것을 막는다.
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

RX_FW = re.compile(r'fontWeight:\s*([0-9]{3}|["\'][a-z]+["\'])', re.IGNORECASE)
RX_FS = re.compile(r"fontSize:\s*([^,\n}]+)")

TOKEN_LEAF_RE = re.compile(r"^(FONT_SIZE\.\w+|STAT_VALUE_FONT_SIZE|BRAND_UNIT|undefined)$")

# 2026-08-16 직접 소스 문맥으로 낱개 확인됨(각 값이 실제로 어떤 역할인지 grep + 코드 대조로
# 검증) — 새 예외를 추가하려면 같은 방식으로 확인한 뒤 이유를 적는다. 근거 없이 값만 늘리지
# 않는다(D-81).
EXEMPT_FONT_SIZE_VALUES: dict[str, str] = {
    '"1em"': "상대 단위(부모 크기를 그대로 따름) — BrandLogo 락업 기준 단위",
    '"1rem"': "낱개 확인(9파일 13건): 입력창(iOS 확대 방지)·아이콘·이모지 버튼·서체 본문·"
              "자격증명 표시(monospace) 중 하나",
    '"0.9375rem"': "입력창 또는 서체 본문(prose, lineHeight 1.6~1.75) — PA-01 5~7차 확장에서 전수 확인",
    '"0.625rem"': "ChatPane.jsx 메신저 읽음 표시 — 본문보다 작아야 하는 보조 지표라 caption(12px)"
                  "로 올리면 본문과 시각적으로 경쟁한다",
    '"0.6875rem"': "kit.jsx StatCard 심각도 배지(12px로 올리면 실측 줄바꿈 위험) + "
                   "theme.js MuiTableCell head(기준선 th{11px}와 정확히 일치, 손대면 오히려 이탈)",
    '"19px"': "TopSearch.jsx 검색 아이콘(SearchRoundedIcon)",
    '"1.125rem"': "Home.jsx/SchedulerCalendar.jsx 보조 통계(18px, sectionTitle 17px·pageTitle 20px "
                  "사이라 기존 토큰과 안 맞음, 실측 없이 스냅 안 함) 또는 SendRoundedIcon",
    '"1.375rem"': "WelcomeStatus.jsx 채팅 환영 제목(22px) — MUI 기본 h5(24px)보다 의도적으로 작게",
    '"1.5rem"': "GameStage.jsx/ProjectWbs.jsx/ui/charts/Donut.jsx 24px+extrabold 관용 "
                "(3곳이 서로 참조하는 주석으로 연결된 의도된 값)",
    '"2.75rem"': "GameStage.jsx 가위바위보 이모지(aria-hidden 글리프)",
    '"2.125rem"': "RpsViews.jsx 가위바위보 이모지(aria-hidden 글리프)",
    '"2rem"': "Profile.jsx Avatar 이니셜 폴백",
    "20": "kit.jsx ChevronRightRoundedIcon 크기(aria-hidden 장식 아이콘)",
    "32": "kit.jsx StatCard 아이콘 슬롯의 compact=false 분기(aria-hidden 장식 아이콘, "
          "compact 분기 20과 짝, `compact ? 20 : 32`)",
    '"24px"': "Mascot.jsx 사이드바 화살표 글리프(aria-hidden 장식, 기준선 .sidebar-clovi-arrow)",
    "STAT_VALUE_FONT_SIZE": "density.js 명명 상수 — 기준선 .kpi-value(30px)와 직접 대조된 값 "
                            "(FONT_SIZE.statValue와 같은 값, kit.jsx 주석에 근거)",
}


def _leaf_is_safe(leaf: str) -> bool:
    """토큰(`FONT_SIZE.x`/`BRAND_UNIT`/`undefined`)이거나, 검증된 EXEMPT 값이거나,
    `clamp(...)` 반응형 수식(고정 스텝이 아니라 공식이라 애초에 이 검사의 대상이 아니다 —
    내부에 쉼표가 있어 `RX_FS`가 뒷부분을 잘라 캡처해도 접두사로 안전하게 판별된다)이면 된다."""
    leaf = leaf.strip()
    if TOKEN_LEAF_RE.match(leaf):
        return True
    if leaf in EXEMPT_FONT_SIZE_VALUES:
        return True
    if leaf.startswith('"clamp(') or leaf.startswith("`clamp(") or leaf.startswith("clamp("):
        return True
    return False


def _value_is_safe(value: str) -> bool:
    """단일 값이거나, `조건 ? 참 : 거짓` 삼항이면 조건은 안 보고 두 분기만 검사한다
    (조건은 `compact`처럼 boolean prop 이름이라 토큰/EXEMPT 판정 대상이 아니다)."""
    if "?" in value:
        _, _, rest = value.partition("?")
        true_branch, has_colon, false_branch = rest.partition(":")
        if not has_colon:
            return False
        return _leaf_is_safe(true_branch) and _leaf_is_safe(false_branch)
    return _leaf_is_safe(value)


def _is_comment_line(line: str) -> bool:
    """JSDoc 연속줄(`* ...`)이나 `//` 라인 코멘트 안의 언급을 코드로 오판하지 않는다 —
    실제로 BrandLogo.jsx 의 JSDoc 설명문(`* ... fontSize: BRAND_UNIT ...`)이 이 검사 초판에서
    코드로 오탐됐다. 이 저장소의 JSDoc 관용(`/** ... * 줄 ... */`)과 `//` 라인 코멘트만
    다룬다 — 문자열 리터럴 안의 `//`까지 완벽히 가려내는 범용 JS 파서는 아니다."""
    stripped = line.strip()
    if stripped.startswith("*") or stripped.startswith("/*"):
        return True
    return "//" in line.split("fontSize:")[0]


def _iter_source_files(src_dir: Path):
    for path in sorted(src_dir.rglob("*")):
        if path.suffix not in (".js", ".jsx"):
            continue
        if ".test." in path.name:
            continue
        yield path


def main(src_dir: Path | None = None) -> int:
    src_dir = src_dir or SRC
    weight_hits: list[str] = []
    size_hits: list[str] = []

    for path in _iter_source_files(src_dir):
        rel = path.relative_to(src_dir).as_posix()
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _is_comment_line(line):
                continue
            for m in RX_FW.finditer(line):
                weight_hits.append(f"{rel}:{lineno}: fontWeight {m.group(1)!r}")
            for m in RX_FS.finditer(line):
                value = m.group(1).strip()
                if _value_is_safe(value):
                    continue
                size_hits.append(f"{rel}:{lineno}: fontSize {value!r} — EXEMPT 목록에 없는 새 값")

    if weight_hits:
        print("[FAIL] fontWeight 리터럴이 재유입됐다(FONT_WEIGHT 토큰만 써야 한다):", file=sys.stderr)
        for h in weight_hits:
            print(f"  - {h}", file=sys.stderr)
    if size_hits:
        print("[FAIL] 검증되지 않은 새 fontSize 리터럴:", file=sys.stderr)
        for h in size_hits:
            print(f"  - {h}", file=sys.stderr)
        print("", file=sys.stderr)
        print("  이 값이 정말 정당한 예외라면(아이콘/이모지/입력창/서체본문/자격증명표시 등)", file=sys.stderr)
        print("  scripts/check_typography_literals.py의 EXEMPT_FONT_SIZE_VALUES에 실제 코드", file=sys.stderr)
        print("  문맥을 확인한 뒤 이유와 함께 추가하라. 근거 없이 그냥 추가하지 마라.", file=sys.stderr)

    if weight_hits or size_hits:
        return 1

    print(f"TYPOGRAPHY_LITERALS_OK (fontSize 예외 {len(EXEMPT_FONT_SIZE_VALUES)}종 등록됨)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
