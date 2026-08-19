"""UI 리뉴얼 Control Plane Gate.

## 이 스크립트가 대신하는 것

`scripts/check_traceability.py` 는 삭제된 `docs/UI_RENEWAL_TRACEABILITY.md` 를 요구하며
지금 `static_checks.sh` 를 빨갛게 만들고 있다. 이 스크립트가 그 네 가지 검사(번호 누락,
빈 필드, 없는 Phase 참조, 자기모순)를 새 추적표 위에서 이어받고 범위를 넓힌다.

## 단계

    --stage plan       계획 자체를 검사한다. 구현 전에 돌린다.
    --stage wave       Wave 종료 검사 (C1~C14). W0 에서 완성한다.
    --stage complete   최종 완료 검사 (C1~C14 + 완료 조건). W0 에서 완성한다.

`wave` 와 `complete` 는 **아직 구현되지 않았다**. 구현되지 않은 검사를 통과로 보고하는
Gate 는 없는 Gate 보다 나쁘므로, 그 두 단계는 종료 코드 2(정직하게 실행 불가)로 멈춘다.

## 종료 코드

    0  통과
    1  조건 위반
    2  정직하게 실행 불가 (Artifact 없음/파싱 불가/미구현 단계)
    3  --stage complete 인데 증거 Artifact 가 이 머신에 없음

## 오탐 두 가지를 의도적으로 피한다

1. "이름 없는 행" 검사는 **Wave 표에만** 적용한다. 비교표의 좌상단 빈 모서리 셀은
   정상적인 Markdown 이다.
2. 진행 상태 표기 검사는 **규칙 문장 자체를 제외**한다. R-96 과 이 파일이 금지 대상
   문자열을 인용하고 있으므로, 인용을 세면 Gate 가 자기 자신 때문에 영원히 실패한다.

측정값이 이상하면 대상을 고치기 전에 프로브를 먼저 의심한다 — `scripts/ui_qa/README.md`
가 같은 교훈을 적고 있다.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UIR = os.path.join(ROOT, "docs", "ui-renewal")

PLAN = os.path.join(UIR, "PLAN.md")
MATRIX = os.path.join(UIR, "REQUIREMENT_MATRIX.md")
ROUTE_COV = os.path.join(UIR, "ROUTE_COVERAGE.json")
FUNC_COV = os.path.join(UIR, "FUNCTIONAL_COVERAGE.json")
WORK_STATE = os.path.join(UIR, "WORK_STATE.md")
SUPPRESSIONS = os.path.join(UIR, "QA_SUPPRESSIONS.md")

REQUIRED_FIELDS = ["Wave", "Requirement", "Affected", "Implementation",
                   "Verification", "Status", "Evidence", "Findings", "Depends on"]
STATUSES = {"NOT_STARTED", "IN_PROGRESS", "DONE", "BLOCKED", "DEFERRED"}
RUNNERS = ("python", "pytest", "npm", "npx", "node", "bash", "curl", "openssl",
           "powershell", "pwsh", "assertion", "독립")

EXIT_OK, EXIT_VIOLATION, EXIT_CANNOT_RUN, EXIT_NO_EVIDENCE = 0, 1, 2, 3


class Report:
    def __init__(self) -> None:
        self.fails: list[tuple[str, str]] = []
        self.oks: list[str] = []

    def fail(self, cond: str, msg: str) -> None:
        self.fails.append((cond, msg))

    def ok(self, msg: str) -> None:
        self.oks.append(msg)

    def emit(self) -> int:
        for msg in self.oks:
            print("[OK]   %s" % msg)
        by_cond: dict[str, list[str]] = {}
        for cond, msg in self.fails:
            by_cond.setdefault(cond, []).append(msg)
        for cond in sorted(by_cond):
            print("[FAIL] %s: %d" % (cond, len(by_cond[cond])))
            for msg in by_cond[cond][:20]:
                print("       - %s" % msg)
            if len(by_cond[cond]) > 20:
                print("       ... 그리고 %d건 더" % (len(by_cond[cond]) - 20))
        return EXIT_VIOLATION if self.fails else EXIT_OK


def read(path: str) -> str:
    return io.open(path, encoding="utf-8").read()


def expected_requirement_ids(matrix_ids: set[str]) -> set[str]:
    """기대 집합. 지시서 구조에서 유도한다.

    0 과 그 하위 8항, 0-1~0-22, 0-2 의 Finding 21개, 1~84, 84-1~84-12,
    그리고 사용자 보강 요구 85~97.
    """
    want = {"R-0"}
    want |= {"R-0.%d" % i for i in range(1, 9)}
    want |= {"R-0-%d" % i for i in range(1, 23)}
    want |= {"R-0-2.%d" % i for i in range(1, 22)}
    want |= {"R-%d" % i for i in range(1, 98)}
    want |= {"R-84-%d" % i for i in range(1, 13)}
    return want


def parse_matrix(text: str):
    """`## R-x. 제목` 블록과 `- **필드**: 값` 을 읽는다.

    형식은 폐기하는 `check_traceability.py` 가 쓰던 것과 같다 — 검증된 파서를 이어받는다.
    """
    entries = []
    cur = None
    for lineno, line in enumerate(text.split("\n"), 1):
        m = re.match(r"^##\s+(R-[0-9.\-]+)\.\s+(.+?)\s*$", line)
        if m:
            cur = {"id": m.group(1), "title": m.group(2), "line": lineno, "fields": {}}
            entries.append(cur)
            continue
        if cur is None:
            continue
        f = re.match(r"^-\s+\*\*(.+?)\*\*\s*:\s*(.*)$", line)
        if f:
            cur["fields"][f.group(1).strip()] = f.group(2).strip()
    return entries


def normalized(s: str) -> str:
    return re.sub(r"[\s`*·,.()\[\]]+", "", s)


def check_matrix(rep: Report, waves: set[str]) -> None:
    text = read(MATRIX)
    entries = parse_matrix(text)
    ids = [e["id"] for e in entries]
    seen: set[str] = set()
    for e in entries:
        if e["id"] in seen:
            rep.fail("P2 번호 중복", "%s (%s:%d)" % (e["id"], "REQUIREMENT_MATRIX.md", e["line"]))
        seen.add(e["id"])

    want = expected_requirement_ids(seen)
    missing = sorted(want - seen, key=lambda x: (len(x), x))
    extra = sorted(seen - want, key=lambda x: (len(x), x))
    for mid in missing:
        rep.fail("P1 번호 누락", mid)
    for xid in extra:
        rep.fail("P1 기대 밖 번호", xid)
    if not missing and not extra:
        rep.ok("요구사항 %d개가 전부 있다 (누락 0, 기대 밖 0)" % len(seen))

    for e in entries:
        where = "%s (line %d)" % (e["id"], e["line"])
        for field in REQUIRED_FIELDS:
            if field not in e["fields"]:
                rep.fail("P3 필드 없음", "%s: %s" % (where, field))
            elif not e["fields"][field].strip():
                rep.fail("P3 빈 필드", "%s: %s" % (where, field))
        if not e["fields"]:
            continue

        wave = e["fields"].get("Wave", "")
        if wave and wave not in waves:
            rep.fail("P4 없는 Wave 참조", "%s: Wave=%s" % (where, wave))

        req = e["fields"].get("Requirement", "")
        if req and len(req) < 40:
            rep.fail("P5 Requirement 가 너무 짧다", "%s: %d자" % (where, len(req)))
        if req and normalized(req) == normalized(e["title"]):
            rep.fail("P5 Requirement 가 제목의 재진술", where)

        impl = e["fields"].get("Implementation", "")
        if impl and not impl.startswith("NONE"):
            paths = re.findall(r"`([^`]+)`", impl)
            real = [p for p in paths if os.path.exists(os.path.join(ROOT, p.split("::")[0].split(":")[0]))]
            if not real:
                rep.fail("P6 Implementation 경로가 실재하지 않는다", "%s: %s" % (where, impl[:70]))
        elif impl.startswith("NONE") and len(impl) < 45:
            rep.fail("P6 NONE 사유가 짧다", where)

        ver = e["fields"].get("Verification", "")
        if ver and not any(r in ver for r in RUNNERS) and "`" not in ver:
            rep.fail("P7 Verification 이 실행 가능한 것을 명명하지 않는다", where)

        st = e["fields"].get("Status", "")
        if st and st not in STATUSES:
            rep.fail("P8 Status 값이 잘못됐다", "%s: %s" % (where, st))

    header = re.search(r"\*\*항목\s+(\d+)개", text)
    if header and int(header.group(1)) != len(entries):
        rep.fail("P9 머리글 자기모순",
                 "머리글은 %s개라는데 실제는 %d개" % (header.group(1), len(entries)))
    elif header:
        rep.ok("머리글이 주장하는 항목 수와 실제 항목 수가 같다 (%d)" % len(entries))

    for legacy, must in (("R-64", "preview-standalone"), ("R-65", "Design Direction")):
        hit = next((e for e in entries if e["id"] == legacy), None)
        if hit is None:
            rep.fail("P10 기존 번호 훼손", "%s 가 없다" % legacy)
        elif must not in (hit["title"] + hit["fields"].get("Requirement", "")):
            rep.fail("P10 기존 번호 훼손",
                     "%s 의 의미가 원래와 다르다 (%s 를 다루지 않는다)" % (legacy, must))
    if all(any(e["id"] == l for e in entries) for l in ("R-64", "R-65")):
        rep.ok("기존 R-64 / R-65 가 원래 의미로 남아 있다")


def check_plan_structure(rep: Report, waves: set[str]) -> None:
    text = read(PLAN)
    lines = text.split("\n")

    start = next((i for i, l in enumerate(lines) if l.startswith("| Wave | 내용 |")), -1)
    if start < 0:
        rep.fail("P11 계획 구조", "PLAN.md 에서 Wave 표를 찾지 못했다")
        return
    end = next((i for i in range(start + 1, len(lines)) if not lines[i].startswith("|")), len(lines))
    block = lines[start:end]

    wave_rows = [(i, l) for i, l in enumerate(block, start + 1) if l.startswith("| **W")]
    for i, l in enumerate(block, start + 1):
        if re.match(r"^\|\s*\|", l):
            rep.fail("P11 이름 없는 Wave 행", "PLAN.md:%d" % i)
    for i, l in wave_rows:
        cells = [c.strip() for c in l.strip().strip("|").split("|")]
        if len(cells) != 5:
            rep.fail("P12 Wave 행의 칸 수가 5가 아니다", "PLAN.md:%d (%d칸)" % (i, len(cells)))
            continue
        for j, name in enumerate(["Wave", "내용", "소유 공유 파일", "전제", "Exit Gate"]):
            if not cells[j]:
                rep.fail("P12 Wave 행 빈 칸", "PLAN.md:%d %s" % (i, name))
    if wave_rows:
        rep.ok("Wave 행 %d개가 전부 이름과 다섯 칸을 갖는다" % len(wave_rows))

    declared = set()
    for _, l in wave_rows:
        m = re.match(r"^\|\s*\*\*(W[0-9]+B?)\*\*", l)
        if m:
            declared.add(m.group(1))
    unknown = sorted(declared - waves)
    if unknown:
        rep.fail("P13 ROUTE_COVERAGE.waves 에 없는 Wave", ", ".join(unknown))
    missing = sorted(waves - declared)
    if missing:
        rep.fail("P13 선언됐지만 계획에 없는 Wave", ", ".join(missing))
    if not unknown and not missing:
        rep.ok("계획의 Wave 집합과 ROUTE_COVERAGE.waves 가 일치한다 (%d개)" % len(waves))

    # 진행 상태 표기 검사 — 규칙 문장(금지 대상을 인용하는 줄)은 제외한다.
    banned = ["작성 중", "반영 예정", "TBD"]
    quoting = ("금지", "없어야", "없음", "0건", "제외", "인용", "Gate", "검사")
    for i, l in enumerate(lines, 1):
        for b in banned:
            if b in l and not any(q in l for q in quoting):
                rep.fail("P14 미완 상태 표기", "PLAN.md:%d (%s)" % (i, b))


def check_json_artifacts(rep: Report):
    try:
        route = json.load(io.open(ROUTE_COV, encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print("[FAIL] ROUTE_COVERAGE.json 을 읽을 수 없다: %s" % exc)
        sys.exit(EXIT_CANNOT_RUN)
    try:
        func = json.load(io.open(FUNC_COV, encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print("[FAIL] FUNCTIONAL_COVERAGE.json 을 읽을 수 없다: %s" % exc)
        sys.exit(EXIT_CANNOT_RUN)

    waves = set(route.get("waves") or [])
    if not waves:
        rep.fail("P15 waves 선언 없음", "ROUTE_COVERAGE.json 에 waves 가 없다")
    surfaces = route.get("surfaces") or []
    if not surfaces:
        rep.fail("P15 Surface 없음", "ROUTE_COVERAGE.json 에 surfaces 가 비어 있다")
    else:
        rep.ok("Surface %d개 (route/tab/widget/alias)" % len(surfaces))

    ids = [s.get("id") for s in surfaces]
    if len(ids) != len(set(ids)):
        rep.fail("P16 Surface id 중복", "중복 %d건" % (len(ids) - len(set(ids))))

    fsurf = {f.get("surface") for f in (func.get("surfaces") or [])}
    expect = {s["id"] for s in surfaces if s.get("kind") in ("route", "tab", "widget")}
    gap = sorted(expect - fsurf)
    if gap:
        rep.fail("P17 Functional Coverage 누락 Surface", ", ".join(gap[:10]))
    else:
        rep.ok("Functional Coverage 가 검증 대상 Surface %d개를 전부 담고 있다" % len(expect))

    return route, func, waves


def check_work_state(rep: Report, waves: set[str]) -> None:
    text = read(WORK_STATE)
    lines = text.split("\n")
    if len(lines) > 120:
        rep.fail("P18 WORK_STATE 가 길다", "%d줄 (상한 120)" % len(lines))
    heads = [l.strip() for l in lines if l.startswith("## ")]
    want = ["## CHECKPOINT", "## NOW", "## NEXT", "## BLOCKERS"]
    if heads != want:
        rep.fail("P18 WORK_STATE 절 구성", "실제=%s" % (heads or "(없음)"))
    else:
        rep.ok("WORK_STATE 가 CHECKPOINT/NOW/NEXT/BLOCKERS 네 절만 갖는다")
    m = re.search(r"^-\s*wave:\s*(\S+)", text, re.M)
    if m and m.group(1) not in waves:
        rep.fail("P19 WORK_STATE 의 wave 가 없는 Wave", m.group(1))


def stage_plan() -> int:
    rep = Report()
    missing = [p for p in (PLAN, MATRIX, ROUTE_COV, FUNC_COV, WORK_STATE, SUPPRESSIONS)
               if not os.path.exists(p)]
    if missing:
        for p in missing:
            print("[FAIL] Artifact 가 없다: %s" % os.path.relpath(p, ROOT))
        print("UI_RENEWAL_COVERAGE_CANNOT_RUN (stage=plan)")
        return EXIT_CANNOT_RUN

    _route, _func, waves = check_json_artifacts(rep)
    check_matrix(rep, waves)
    check_plan_structure(rep, waves)
    check_work_state(rep, waves)

    code = rep.emit()
    if code == EXIT_OK:
        print("UI_RENEWAL_COVERAGE_OK (stage=plan)")
    else:
        print("UI_RENEWAL_COVERAGE_FAILED (stage=plan, 위반 %d건)" % len(rep.fails))
    return code


def main() -> int:
    ap = argparse.ArgumentParser(description="UI 리뉴얼 Control Plane Gate")
    ap.add_argument("--stage", choices=["plan", "wave", "complete"], default="plan")
    ap.add_argument("--wave", default="")
    args = ap.parse_args()

    print("== UI 리뉴얼 커버리지 게이트 (stage=%s) ==" % args.stage)
    if args.stage == "plan":
        return stage_plan()

    print("[FAIL] --stage %s 는 아직 구현되지 않았다 (W0 에서 C1~C14 를 구현한다)." % args.stage)
    print("       구현되지 않은 검사를 통과로 보고하지 않는다.")
    print("UI_RENEWAL_COVERAGE_CANNOT_RUN (stage=%s)" % args.stage)
    return EXIT_CANNOT_RUN


if __name__ == "__main__":
    sys.exit(main())
