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

이 검사가 **안** 하는 것: "화면마다 contained가 최소 1개"(acceptance_criteria 1)는 여기 없다 —
그건 "이 화면이 정말 아무 동작도 없는 순수 조회 화면인가"라는 판단이 필요해서 파일 하나를
줄 단위로 훑는 것만으로는 안전하게 못 정한다(오탐이 더 해롭다). 그 축은 화면별로 사람이
직접 확인하고 `docs/BACKLOG.md`/`DECISIONS.md`에 근거를 남긴다.
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


def main(registry_dir: Path | None = None) -> int:
    registry_dir = registry_dir or REGISTRY_DIR
    destructive_hits: list[str] = []
    unpaired_primary_hits: list[str] = []

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

    if destructive_hits or unpaired_primary_hits:
        return 1

    print(f"BUTTON_HIERARCHY_OK (파괴적 라벨 {len(DESTRUCTIVE_LABELS)}종 감시, registry 전수)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
