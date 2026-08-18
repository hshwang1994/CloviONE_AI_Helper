"""지시 56 Gate — 요구사항 추적표를 **스크립트가** 검사한다.

## 왜 필요한가

`docs/UI_RENEWAL_TRACEABILITY.md` 는 스스로 "생성 시 번호 누락과 빈 필드를 스크립트가
검사한다" 고 적어 두었지만, 그 스크립트가 저장소에 없었다(2026-08-19 전수 감사에서 발견).
그래서 실제로는 **사람이 눈으로 본 것**이 유일한 근거였고, 지시 56 이 요구한 것은 정확히
그 반대다("빠진 번호 0건, 내용 없는 번호 0건, 없는 Phase 참조 0건을 확인한다").

문서가 자기 검사기를 주장하면서 검사기가 없는 상태는, 검사가 없는 것보다 나쁘다 — 다음
사람이 "이미 검사받고 있다" 고 믿는다.

## 무엇을 검사하는가

1. **번호 누락 0건** — 지시 1~70 이 전부 있다. 중복도 없다.
2. **빈 필드 0건** — 항목마다 필수 필드 여섯이 있고 값이 비어 있지 않다.
3. **없는 Phase 참조 0건** — 각 항목의 `Phase` 가 계획서(`misty-honking-wirth.md` §3)에
   실제로 존재하는 Phase 이름이다. 계획서를 못 찾으면 그 검사만 건너뛰고 그 사실을 말한다
   (CI 나 다른 머신에서 계획서가 없을 수 있다 — 조용히 통과시키지는 않는다).
4. **자기모순 0건** — 머리글이 주장하는 항목 수가 실제 항목 수와 같다.

## 쓰는 법

    .venv/Scripts/python.exe scripts/check_traceability.py

`scripts/static_checks.sh` 가 부른다. 실패하면 무엇이 어디서 틀렸는지 줄 번호로 말한다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "UI_RENEWAL_TRACEABILITY.md"
PLAN_CANDIDATES = (
    Path.home() / ".claude" / "plans" / "misty-honking-wirth.md",
    ROOT / "docs" / "misty-honking-wirth.md",
)

EXPECTED = tuple(range(1, 71))

# 항목마다 있어야 하는 필드. 라벨은 문서가 실제로 쓰는 문자열 그대로다.
REQUIRED_FIELDS = (
    "Phase",
    "현재 문제 / 조사 대상",
    "변경할 기능 또는 UX",
    "영향 범위",
    "필요한 공통 Component / 정책",
    "검증 방법",
    "완료 판단 기준",
)

RX_HEADING = re.compile(r"^##\s+(\d+)\.\s*(.+?)\s*$", re.M)
RX_FIELD = re.compile(r"^-\s+\*\*(.+?)\*\*\s*:\s*(.*)$")
RX_CLAIMED_COUNT = re.compile(r"항목\s+(\d+)개")
# 계획서의 Phase 정의 두 모양:
#   최상위 — "### P3. App Shell · Navigation ..." (제목)
#   하위   — "- **P3-5 관리자 IA 재설계** (지시 30·51):" (목록 항목의 굵은 머리)
# 둘 다 **정의**하는 자리다. 본문에서 스쳐 지나가는 언급("P12 에서 다룬다")은 정의가
# 아니므로 세지 않는다 — 그렇게 하면 오타로 만든 Phase 이름도 통과한다.
RX_PLAN_TOP = re.compile(r"^###\s+(P\d+)", re.M)
RX_PLAN_SUB = re.compile(r"^\s*[-*]\s*\*\*(P\d+-\d+)", re.M)


def fail(msgs: list[str]) -> None:
    print("[FAIL] 추적표 Gate (지시 56)")
    for m in msgs:
        print("  - " + m)
    sys.exit(1)


def parse_items(text: str) -> dict[int, dict]:
    """번호 → {필드: 값, "_line": 시작 줄}."""
    items: dict[int, dict] = {}
    heads = list(RX_HEADING.finditer(text))
    for i, m in enumerate(heads):
        num = int(m.group(1))
        start = m.end()
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[start:end]
        fields: dict = {"_line": text[: m.start()].count("\n") + 1, "_title": m.group(2)}
        for line in body.splitlines():
            fm = RX_FIELD.match(line.strip())
            if fm:
                fields[fm.group(1).strip()] = fm.group(2).strip()
        if num in items:
            fields["_duplicate"] = True
        items[num] = fields
    return items


def plan_phases() -> set[str] | None:
    for path in PLAN_CANDIDATES:
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="replace")
            found = set(RX_PLAN_TOP.findall(text)) | set(RX_PLAN_SUB.findall(text))
            # 하위 Phase 가 정의돼 있으면 그 상위도 유효한 참조다(예: "P2" 만 적은 항목).
            found |= {p.split("-")[0] for p in found}
            return found or None
    return None


def main() -> None:
    problems: list[str] = []

    if not DOC.exists():
        fail([f"{DOC.relative_to(ROOT)} 가 없다 — 지시 56 이 요구한 추적표 자체가 없다"])

    text = DOC.read_text(encoding="utf-8", errors="replace")
    items = parse_items(text)

    # 1) 번호 누락·중복
    missing = [n for n in EXPECTED if n not in items]
    if missing:
        problems.append(f"빠진 지시 번호: {missing}")
    extra = sorted(n for n in items if n not in EXPECTED)
    if extra:
        problems.append(f"1~70 밖의 번호가 있다: {extra}")
    dupes = sorted(n for n, f in items.items() if f.get("_duplicate"))
    if dupes:
        problems.append(f"같은 번호가 두 번 나온다: {dupes}")

    # 2) 빈 필드
    for num in sorted(items):
        fields = items[num]
        for label in REQUIRED_FIELDS:
            if label not in fields:
                problems.append(f"{DOC.name}:{fields['_line']} 지시 {num} — 필드 없음: {label}")
            elif not fields[label].strip():
                problems.append(f"{DOC.name}:{fields['_line']} 지시 {num} — 필드가 비었다: {label}")

    # 3) 없는 Phase 참조
    phases = plan_phases()
    if phases is None:
        print("[WARN] 계획서를 못 찾아 Phase 참조 검사는 건너뛴다(번호·빈 필드 검사는 수행).")
        print("       찾은 경로 후보: " + ", ".join(str(p) for p in PLAN_CANDIDATES))
    else:
        for num in sorted(items):
            raw = items[num].get("Phase", "")
            # "P3-2, P4-1" · "P2(PageHeader), P9-3" · "§1.6, P1-2" 같은 표기를 모두 받는다.
            refs = re.findall(r"P\d+(?:-\d+)?", raw)
            if not refs:
                # 계획서 Phase 가 아니라 §절을 가리키는 항목도 있다(지시 50·64 등) — 그건
                # 참조가 없는 것이 아니라 다른 종류의 참조다. 둘 다 없으면 문제다.
                if "§" not in raw:
                    problems.append(
                        f"{DOC.name}:{items[num]['_line']} 지시 {num} — Phase 참조를 못 읽었다: {raw!r}")
                continue
            for ref in refs:
                if ref not in phases:
                    problems.append(
                        f"{DOC.name}:{items[num]['_line']} 지시 {num} — 계획서에 없는 Phase: {ref}")

    # 4) 머리글의 자기 주장과 실제 개수
    claimed = RX_CLAIMED_COUNT.search(text)
    if claimed and int(claimed.group(1)) != len(items):
        problems.append(
            f"머리글은 항목 {claimed.group(1)}개라고 하는데 실제로는 {len(items)}개다")

    if problems:
        fail(problems)

    phase_note = "Phase 참조 확인" if phases else "Phase 참조 건너뜀"
    print(f"[OK  ] TRACEABILITY_OK (항목 {len(items)}개, 필드 {len(REQUIRED_FIELDS)}종, {phase_note})")


if __name__ == "__main__":
    main()
