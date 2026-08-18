"""버튼 위계 회귀 방지 검사 (PA-RC-0023 acceptance_criteria 3, 7).

왜 필요한가: `frontend/src/screens/registry/*.js`의 액션 객체가 그 화면의 버튼 색을 정한다
(`DataScreen.jsx`가 `variant={a.variant || "default"}`로 그대로 옮긴다 — `ui/kit.jsx`의
`BUTTON_VARIANT`에서 `primary`는 `contained`, `danger`도 `contained`+`color:error`다). 문서로만
규범을 적어 두면 다음 화면을 추가하는 사람이 그 문서를 안 읽는다 — `check_typography_literals.py`
(PA-RC-0001)가 같은 이유로 이미 이 저장소의 관례다, 같은 자리(줄 단위 정규식, AST 없음)에
그대로 얹는다.

이 파일이 잡는 두 가지(둘 다 2026-08-16 PA-RC-0023 조사에서 실제로 재현된 결함이다):

1. **파괴적 동작이 primary(채운 파란 버튼)면 안 된다** — 삭제·비활성화·보관 등은 이미 전부
   `variant:"danger"`(채운 빨간 버튼)로 올바르게 돼 있었지만, 문서가 아니라 검사가 없으면
   다음에 추가되는 액션이 그 관례를 모르고 primary로 새는 걸 아무도 못 잡는다. 예외 없음 —
   파괴적 동작이 primary여야 할 정당한 이유는 없다(fontWeight 리터럴과 같은 종류의 완전 금지).
2. **`primary: true`(빈 상태 CTA로 승격)인데 `variant: "primary"`가 없다** — 실제로
   `notion-mapping`의 '자동 동기화'가 이 상태였다: 목록이 비었을 때만 파란 버튼으로 보이고,
   보통 상태(대상이 있을 때)에는 툴바에 외곽선 버튼으로 떠 있어 "이 화면의 핵심 동작"이라는
   의도와 실제 모습이 어긋났다. `DataScreen.jsx`는 툴바에서 `variant`만 보고 `primary:true`는
   빈 상태 CTA를 계산할 때만 보므로(별개 필드), 항상 짝을 맞춰야 두 자리에서 같은 색으로 보인다.

3. **화면마다 `contained`(primary) 액션이 최소 1개** (acceptance_criteria 1) — `*_SCREENS`/
   `*_SCREEN` export 안의 화면 블록만 본다(actions.js의 `subList` 같은 공유 조각은 자기
   `key:` 필드가 없어 화면으로 안 친다). "primary 있음"은 `variant:"primary"`뿐 아니라
   `DataScreen.jsx`가 registry 내용과 무관하게 항상 그리는 두 버튼도 센다 — `edit:`가 있으면
   상세 footer에 고정 primary "수정"이, `create:`가 있으면 헤더에 고정 primary "추가"가
   뜬다(DataScreen.jsx의 `canEdit`/`showCreate` 분기). 이 넓은 판정도 오탐(정말 primary가
   있는데 없다고 잘못 잡는 것)보다 미탐이 나은 방향으로 일부러 기울였다. 그래도 남는 순수
   조회 화면은 `ZERO_PRIMARY_EXCEPTIONS`에 근거와 함께 정식 등재한다 — 등재 안 된 화면이
   새로 0-primary가 되면 실패시킨다(대개 실수로 모든 액션이 default/danger가 된 것이다).
4. **같은 영역(헤더 툴바 / 상세·행 액션)에 `contained`가 2개 이상 있으면 안 된다**
   (acceptance_criteria 2) — 실제로 `actions.js`의 `activeToggle()` "활성화"가 이 모양이었다
   (`edit:`가 그리는 고정 primary "수정"과 상세 footer에서 충돌, D-95). `headerActions:`/
   `actions:` 배열마다 따로 세고, `create:`/`edit:`의 암묵 primary도 그 영역에 더한다.

이 검사가 **안** 하는 것: `SystemOps.jsx`·`MyStats.jsx`·`Activity.jsx`·`DisplaySettings.jsx`
같은 registry 밖 독립 화면은 못 본다 — 이 파일은 `frontend/src/screens/registry/*.js`의
데이터 shape만 훑는다(AST 없음), 임의 JSX의 버튼 렌더를 안전하게 줄 단위로 판별할 방법이
없다. 그 화면들의 0-primary 근거는 `docs/DECISIONS.md`(D-95)에 사람이 직접 남겼다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_DIR = ROOT / "frontend" / "src" / "screens" / "registry"

# 2026-08-16 registry/*.js 전수 확인(Explore 조사)으로 만든 목록 — 실제로 삭제·되돌릴 수
# 없는 상태 변경 라벨로 쓰인 것만 담는다. 새 파괴적 액션을 추가하면서 라벨이 이 목록에 없으면
# 이 검사가 못 잡으므로(오탐보다 미탐이 나은 종류가 아니다), 새 파괴적 라벨을 추가할 때는
# 여기도 같이 넓힌다.
DESTRUCTIVE_LABELS = [
    "삭제", "비활성화", "보관", "거절", "취소", "롤백", "연결 해제", "위임 거두기",
]

RX_VARIANT_PRIMARY = re.compile(r'variant:\s*["\']primary["\']')
RX_LABEL = re.compile(r'label:\s*["\']([^"\']+)["\']')
RX_PRIMARY_TRUE = re.compile(r'\bprimary:\s*true\b')

RX_SCREENS_EXPORT = re.compile(r'^export const [A-Z_]+_SCREENS?\s*=\s*\{\s*$')
RX_TOP_LEVEL_CLOSE = re.compile(r'^\};?\s*$')
RX_SCREEN_BLOCK_START = re.compile(r'^  (?:"([A-Za-z0-9_-]+)"|([A-Za-z_][A-Za-z0-9_-]*)):\s*\{\s*$')
RX_SCREEN_BLOCK_END = re.compile(r'^  \},?\s*$')
RX_KEY_FIELD = re.compile(r'\bkey:\s*["\']([^"\']+)["\']')
RX_EDIT_BLOCK = re.compile(r'^ {4}edit:\s*\{')
RX_CREATE_BLOCK = re.compile(r'^ {4}create:\s*\{')
RX_HEADER_ACTIONS_START = re.compile(r'^ {4}headerActions:\s*\[')
RX_ACTIONS_START = re.compile(r'^ {4}actions:\s*\[')
RX_ARRAY_CLOSE_4SP = re.compile(r'^ {4}\],?\s*$')

# 화면 단위 "primary 0개" 예외 등재(acceptance_criteria 1) — 2026-08-16 D-95에서 사람이 직접
# 확인한, registry가 표현하는 순수 조회/보고 화면만 담는다. 새 화면을 추가로 등재하려면 그
# 화면이 정말 조회 전용인지 먼저 확인하고 여기·DECISIONS.md 양쪽에 근거를 남긴다.
ZERO_PRIMARY_EXCEPTIONS = {
    "audit": "감사 로그 조회 전용 — 원본 데이터는 다른 화면에서 바뀐다, 여기서는 바꾸지 않는다.",
    "audit-anomalies": "감사 이상 징후 조회 전용 — 근거를 보여줄 뿐 여기서 조치하지 않는다.",
    "rbac": "역할별 권한 매트릭스 조회 전용 — 권한 자체는 코드가 정의하고, 화면은 읽기만 한다.",
    "prompt-usage": "프롬프트 사용 통계 조회 전용.",
    "policy-usage": "정책 사용 통계 조회 전용.",
    "restore-drills": "복구 리허설 안내 — 실제 동작은 서버 CLI 단계다(forceOnboarding으로 이미 표시), 화면엔 누를 버튼이 없다.",
    "org-tree": "조직 > 부서 > 사용자 소속 관계 조회 전용 — 행 액션(소속 인원 펼치기)도 같은 자리에서 더 보여줄 뿐 무엇도 바꾸지 않는다, 변경은 부서 관리 화면에서 한다.",
}


def _is_comment_line(line: str) -> bool:
    """check_typography_literals.py와 같은 관용 — JSDoc 연속줄과 `//` 라인 코멘트만 거른다."""
    stripped = line.strip()
    if stripped.startswith("*") or stripped.startswith("/*"):
        return True
    return stripped.startswith("//")


def _iter_registry_files(registry_dir: Path):
    for path in sorted(registry_dir.rglob("*.js")):
        if ".test." in path.name:
            continue
        yield path


def _iter_screen_blocks(text: str):
    """`*_SCREENS`/`*_SCREEN` export 안의 2-space 자식 블록만 화면으로 낸다. export 밖에
    있거나(actions.js의 `subList`처럼 화면이 아닌 공유 조각) 자기 `key:` 필드가 없는 2-space
    블록은 화면으로 보지 않는다 — 화면은 전부 `key: "그 자신의 property 이름"`을 반복해서
    갖는 게 이 저장소의 관례다(registry/*.js 전수 확인, D-95)."""
    lines = text.splitlines()
    in_export = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if not in_export:
            if RX_SCREENS_EXPORT.match(line):
                in_export = True
            i += 1
            continue
        if RX_TOP_LEVEL_CLOSE.match(line):
            in_export = False
            i += 1
            continue
        m = RX_SCREEN_BLOCK_START.match(line)
        if not m:
            i += 1
            continue
        screen_key = m.group(1) or m.group(2)
        start = i
        j = i + 1
        while j < len(lines) and not RX_SCREEN_BLOCK_END.match(lines[j]):
            j += 1
        if j >= len(lines):
            break  # 짝이 안 맞는 중괄호 — 이 검사가 다룰 문제가 아니다, 조용히 멈춘다.
        block_lines = lines[start:j + 1]
        key_match = RX_KEY_FIELD.search("\n".join(block_lines))
        if key_match and key_match.group(1) == screen_key:
            yield screen_key, start + 1, block_lines
        i = j + 1


def _region_primary_count(block_lines: list[str], start_rx: re.Pattern) -> int:
    """`block_lines`(화면 하나) 안에서 `start_rx`로 시작하는 4-space 배열(headerActions:
    또는 actions:)의 몸통만 잘라, 그 안의 코드 줄(주석 제외) 중 variant:"primary" 개수를
    센다. 그 배열 자체가 없으면 0."""
    start = next((i for i, l in enumerate(block_lines) if start_rx.match(l)), None)
    if start is None:
        return 0
    end = start + 1
    while end < len(block_lines) and not RX_ARRAY_CLOSE_4SP.match(block_lines[end]):
        end += 1
    body = block_lines[start:end]
    return sum(1 for l in body if not _is_comment_line(l) and RX_VARIANT_PRIMARY.search(l))


def main(registry_dir: Path | None = None) -> int:
    registry_dir = registry_dir or REGISTRY_DIR
    destructive_hits: list[str] = []
    unpaired_primary_hits: list[str] = []
    zero_primary_hits: list[str] = []
    too_many_primary_hits: list[str] = []
    screens_scanned = 0

    for path in _iter_registry_files(registry_dir):
        rel = path.relative_to(registry_dir).as_posix()
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _is_comment_line(line):
                continue

            if RX_VARIANT_PRIMARY.search(line):
                label_match = RX_LABEL.search(line)
                label = label_match.group(1) if label_match else None
                if label in DESTRUCTIVE_LABELS:
                    destructive_hits.append(f"{rel}:{lineno}: label={label!r}가 variant:\"primary\"다")

            if RX_PRIMARY_TRUE.search(line) and not RX_VARIANT_PRIMARY.search(line):
                unpaired_primary_hits.append(f"{rel}:{lineno}: primary:true인데 같은 줄에 variant:\"primary\"가 없다")

        for screen_key, lineno, block_lines in _iter_screen_blocks(text):
            screens_scanned += 1
            has_edit = any(RX_EDIT_BLOCK.match(bl) for bl in block_lines)
            has_create = any(RX_CREATE_BLOCK.match(bl) for bl in block_lines)

            header_primaries = _region_primary_count(block_lines, RX_HEADER_ACTIONS_START) + (1 if has_create else 0)
            detail_primaries = _region_primary_count(block_lines, RX_ACTIONS_START) + (1 if has_edit else 0)
            if header_primaries >= 2:
                too_many_primary_hits.append(
                    f"{rel}:{lineno}: key={screen_key!r} — 헤더 툴바에 primary가 {header_primaries}개다(1개여야 한다)")
            if detail_primaries >= 2:
                too_many_primary_hits.append(
                    f"{rel}:{lineno}: key={screen_key!r} — 상세/행 액션에 primary가 {detail_primaries}개다"
                    "(1개여야 한다 — edit:가 있으면 고정 primary '수정'과 충돌하는지 확인)")

            if screen_key in ZERO_PRIMARY_EXCEPTIONS:
                continue
            block_text = "\n".join(block_lines)
            has_primary = (
                RX_VARIANT_PRIMARY.search(block_text)
                or RX_PRIMARY_TRUE.search(block_text)
                or has_edit or has_create
            )
            if not has_primary:
                zero_primary_hits.append(f"{rel}:{lineno}: key={screen_key!r} — primary 액션이 하나도 없다(예외 미등재)")

    if destructive_hits:
        print("[FAIL] 파괴적 동작이 primary(채운 버튼)로 스타일링됐다 — danger여야 한다:", file=sys.stderr)
        for h in destructive_hits:
            print(f"  - {h}", file=sys.stderr)
        print("", file=sys.stderr)
        print("  삭제·비활성화·보관 같은 되돌리기 어려운 동작은 항상 variant:\"danger\"다", file=sys.stderr)
        print("  (별도 그룹 + 확인 단계와 함께). 예외 없음 — PA-RC-0023.", file=sys.stderr)

    if unpaired_primary_hits:
        print("[FAIL] primary:true 헤더 액션에 variant:\"primary\"가 짝지어 있지 않다:", file=sys.stderr)
        for h in unpaired_primary_hits:
            print(f"  - {h}", file=sys.stderr)
        print("", file=sys.stderr)
        print("  primary:true는 목록이 비었을 때의 CTA로만 승격한다(DataScreen.jsx createBtn) —", file=sys.stderr)
        print("  같은 줄에 variant:\"primary\"도 없으면 평소 툴바에서는 외곽선 버튼으로 보여", file=sys.stderr)
        print("  '이 화면의 핵심 동작'이라는 의도와 실제 모습이 어긋난다.", file=sys.stderr)

    if zero_primary_hits:
        print("[FAIL] 화면에 primary(핵심 동작) 액션이 하나도 없는데 예외로 등재돼 있지 않다:", file=sys.stderr)
        for h in zero_primary_hits:
            print(f"  - {h}", file=sys.stderr)
        print("", file=sys.stderr)
        print("  화면 하나에는 보통 '이 화면의 핵심 동작'이 있다 — 대부분은 액션 하나를", file=sys.stderr)
        print("  variant:\"primary\"로 올리는 걸 빠뜨린 실수다. 정말 순수 조회 화면이면", file=sys.stderr)
        print("  scripts/check_button_hierarchy.py의 ZERO_PRIMARY_EXCEPTIONS에 근거와 함께", file=sys.stderr)
        print("  등재하고 docs/DECISIONS.md에도 남겨라(PA-RC-0023).", file=sys.stderr)

    if too_many_primary_hits:
        print("[FAIL] 한 화면의 같은 영역에 primary(핵심 동작)가 2개 이상이다:", file=sys.stderr)
        for h in too_many_primary_hits:
            print(f"  - {h}", file=sys.stderr)
        print("", file=sys.stderr)
        print("  화면/오버레이당 contained는 정확히 1개다 — 나머지는 outlined(default)나", file=sys.stderr)
        print("  danger(파괴적 동작)여야 한다. PA-RC-0023 acceptance_criteria 2.", file=sys.stderr)

    if destructive_hits or unpaired_primary_hits or zero_primary_hits or too_many_primary_hits:
        return 1

    print(
        f"BUTTON_HIERARCHY_OK (파괴적 라벨 {len(DESTRUCTIVE_LABELS)}종 감시, "
        f"화면 {screens_scanned}개 중 0-primary 예외 {len(ZERO_PRIMARY_EXCEPTIONS)}개, registry 전수)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
