"""UI 리뉴얼 Control Plane Gate.

## 이 스크립트가 대신하는 것

`scripts/check_traceability.py` 는 삭제된 `docs/UI_RENEWAL_TRACEABILITY.md` 를 요구하며
지금 `static_checks.sh` 를 빨갛게 만들고 있다. 이 스크립트가 그 네 가지 검사(번호 누락,
빈 필드, 없는 Phase 참조, 자기모순)를 새 추적표 위에서 이어받고 범위를 넓힌다.

## 단계

    --stage plan       계획 자체를 검사한다. 구현 전에 돌린다.
    --stage wave       Wave 종료 검사 (C1~C14). W0 에서 완성한다.
    --stage complete   최종 완료 검사 (C1~C14 + 완료 조건). W0 에서 완성한다.

세 단계 전부 구현돼 있다. `wave` 는 조건 C1~C14 를 현재 Wave 범위로 좁혀 적용하고,
`complete` 는 범위를 풀고 Critical/High Finding 과 남은 `NOT_AUDITED` 까지 본다.
Before 캡처만은 Wave 로 봐주지 않는다 — 제품 코드가 바뀌기 전에만 찍을 수 있어서
그 창이 W0 에 한 번뿐이기 때문이다.

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

    def count(self, prefix: str) -> int:
        """이 조건이 낸 실패 수. OK 줄은 **자기 검사**만 보고 판단해야 한다 —
        다른 검사의 실패 때문에 통과 사실이 화면에서 사라지면 남은 실패를 읽기 어려워진다."""
        return sum(1 for cond, _ in self.fails if cond.startswith(prefix))

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


# ─────────────────────────────────────────────────────────────────────────────
# 소스 진실 리더 — 어느 것도 ROUTE_COVERAGE.json 을 믿지 않는다
# ─────────────────────────────────────────────────────────────────────────────
#
# 커버리지를 커버리지로 검증하면 아무것도 검증하지 않은 것이다. 아래 리더 넷은 전부
# **프런트 소스 텍스트와 하네스 모듈**에서 직접 읽는다.
#
# 다섯 번째 진실인 REGISTRY 28키는 여기서 읽지 않는다. 계획 세션이 Python 정규식으로
# 7개 도메인 파일을 훑었을 때 28개 중 1개(`admin-notifications`)를 조용히 놓쳤고, 놓친
# 키는 커버리지에 없어도 Gate 가 초록이 됐다 — 검사가 없는 것보다 나쁜 상태다.
# REGISTRY 는 JS 객체 조립의 결과라서 그걸 정확히 아는 도구는 JS 자신뿐이다. 그 대조는
# `frontend/src/screens/registry-surface-parity.test.js` 가 하고, `static_checks.sh` 가
# 그 파일을 실제로 돌린다. 여기서는 **그 검사가 존재하고 살아 있는지**만 확인한다.

USER_ROUTES_JSX = os.path.join(ROOT, "frontend", "src", "app", "UserRoutes.jsx")
ADMIN_ROUTES_JSX = os.path.join(ROOT, "frontend", "src", "app", "AdminRoutes.jsx")
SETTINGS_SHELL_JSX = os.path.join(ROOT, "frontend", "src", "screens", "settings", "SettingsShell.jsx")
PARITY_TEST_JS = os.path.join(ROOT, "frontend", "src", "screens", "registry-surface-parity.test.js")

ARCHETYPES = {
    "dashboard_home", "list_table", "reading_page", "work_detail", "form", "wizard",
    "report_board", "ops_console", "chat", "settings_panel", "split_view", "auth", "alias",
    # 화면 원형이 아니라 **그릇**. Header/Sidebar 는 전 Route 에 렌더돼 자기 Route 가 없지만,
    # R-13 · R-48 · R-58 · R-79 · R-0-2.13 이 붙을 곳이 필요하다 — 없으면 그 요구는 어느
    # Wave 도 소유하지 않은 채 사람 눈에만 맡겨진다.
    "app_shell",
}
SURFACE_STATUSES = {
    "NOT_AUDITED", "IN_PROGRESS", "IMPLEMENTED", "VISUAL_PASS", "FUNCTIONAL_PASS",
    "DONE", "BLOCKED", "DEFERRED",
}
BAD_STATUSES = {"UNKNOWN", "TODO", "NOT_AUDITED"}
AUDIT_RESULTS = {"PASS", "FAIL", "PENDING", "N/A"}
FLOW_STATUSES = {"NOT_AUDITED", "IN_PROGRESS", "PASS", "FAIL", "BLOCKED"}
CHAIN_STEPS = ("ui_action", "frontend_state", "url_state", "api_request",
               "backend_query", "data_relation", "api_response", "rendered")
CHAIN_MIN = ("api_request", "backend_query", "api_response", "rendered")
FILTERISH = {"search", "filter", "sort", "pagination", "combobox"}
ACTIONISH = {"row_action", "overflow_action", "modal_action", "settings_apply",
             "admin_op", "notification_action", "approval_action"}
DEAD_CLASSES = {"dead_action", "frontend_only_state", "not_persisted", "missing_backend",
                "missing_ui", "dead_route", "bad_query_param", "stale_cache",
                "duplicate_request", "race_condition", "permission_mismatch"}
LAYOUT_CLASSES = {"equal_column_split", "column_width_vs_content", "isolated_control_row",
                  "oversized_empty_surface", "dead_blank_region", "detail_side_imbalance",
                  "surface_repetition"}
TABLE_ASSERTIONS = ("column_width_vs_content", "header_cell_alignment_mismatch", "numeric_alignment")

# ── Assertion 승격 일정 (PLAN «새 Assertion 13종» 의 «Gate vs Advisory» 절이 정본) ──────
#
# 승격은 **선언이 아니라 실행**이어야 한다. W0~W4 는 «이 Wave 부터 `--fail-on`» 이라고 적어
# 두고 한 번도 그 플래그를 붙이지 않았다 — 그래서 W0 에서 승격했다는 두 검사는 W0 이후
# 계속 빨간 채였고 아무도 몰랐다(W5 독립 조사). 이제 게이트가 **After 실행의 `run.fail_on`**
# 을 직접 읽어, 이 Wave 까지 승격된 클래스가 실제로 걸려 있었는지 확인한다.
# `--fail-on` 은 원장이 아니라 그 실행의 페이지 판정만 보므로, Finding 의 `wave` 를 옮겨서는
# 이 조건을 통과할 수 없다.
PROMOTED_AT = {
    "W0": ("header_cell_alignment_mismatch", "numeric_alignment", "plain_dropdown_for_entity"),
    "W5": ("isolated_control_row", "control_baseline_mismatch"),
    "W6": ("equal_column_split", "column_width_vs_content", "brand_role_coverage"),
    "W7": ("mascot_visible_size",),
    "W9": ("detail_side_imbalance",),
}


def _promoted_upto(waves: list, wave: str) -> set:
    """이 Wave 까지 `--fail-on` 이어야 하는 클래스."""
    out: set = set()
    if wave not in waves:
        return out
    for w in waves[: waves.index(wave) + 1]:
        out.update(PROMOTED_AT.get(w, ()))
    return out
UNSUPPRESSIBLE = {"header_cell_alignment_mismatch", "numeric_alignment",
                  "plain_dropdown_for_entity", "brand_presence"}
# 소스에서 Assertion 을 끄는 속성. `QA_SUPPRESSIONS.md` 의 행과 1:1 이어야 한다.
# `data-col-role` 은 억제가 아니라 **컬럼의 의미 선언**이라(식별자형 숫자는 우정렬 대상이
# 아니다) 여기 넣지 않는다 — 끄는 것과 알려 주는 것은 다르다.
SUPPRESSION_MARKERS = (
    "data-equal-grid", "data-control-row", "data-surface-intent", "data-page-density",
    "data-detail-rail", "data-surface-set", "data-qa-slack", "data-entity-select",
    "data-mascot-role",
)
EVIDENCE_PREFIXES = ("ev:capture:", "ev:qa_run:", "ev:test:", "ev:commit:", "ev:api:",
                     "ev:db:", "ev:review:", "ev:note:")


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


class SourceReadError(RuntimeError):
    """리더가 소스에서 아무것도(또는 너무 적게) 읽지 못했다.

    **이 예외가 이 파일에 있는 이유**: 리더 셋이 예전에는 못 읽으면 `[]`/`{}` 를 돌려줬다.
    빈 목록을 도는 `for` 는 0번 돌고, 0번 도는 검사는 실패를 만들 수 없다 — Gate 는 초록을
    찍는다. 이 전환은 **Route 집합을 통째로 바꾼다.** 정확히 그때 이 경로로 조용히
    통과한다(R4).

    「검사가 위반을 못 찾았다」와 「검사가 아무것도 안 봤다」는 다른 사실이고, 종료 코드가
    같으면 그 둘을 구별할 수 없다.
    """


# 리더가 눈을 감았는지 판별하는 하한.
#
# 이 수는 «지금 몇 개인가» 가 아니라 **«리더가 정상이면 그 아래로 내려갈 수 없는 수»** 다.
# 지금 값(2026-08-21 측정): User 28 · Admin 리터럴 21 · TAB_GROUPS 5그릇 10탭 · TAB_DEFS 4 ·
# 하네스 84. 하한은 그 절반 언저리로 둔다 — 정규식이 조금씩 어긋나는 «부분 실명» 까지
# 잡으면서, 화면을 한둘 지우는 정상 변경에는 안 걸리는 자리다.
#
# **Route 를 정말로 줄이는 변경은 이 값을 함께 내린다.** 그때 사람이 한 번 「정말 줄었나」를
# 판단하게 되는 것이 이 상수의 목적이다. 자동으로 따라 내려가는 하한은 하한이 아니다.
SOURCE_FLOOR = {
    "UserRoutes.jsx": 14,
    "AdminRoutes.jsx": 10,
    "TAB_GROUPS": 3,
    "TAB_DEFS": 3,
    "harness": 40,
}


def parse_jsx_routes(text: str, rel: str, *, floor: int = 0) -> dict:
    """`<Route path="…">` 을 파일 위치와 함께 읽는다.

    JSX 를 파싱하지 않는다(빌드 도구 없이는 무리다). `<Route` 부터 600자를 잘라 그 안의
    첫 `path="…"` 와 `<Navigate to="…"` 를 본다 — `element={<Navigate … />}` 안에 `>` 가
    들어 있어서 `<Route[^>]*>` 류 정규식은 통째로 어긋난다.

    `path={g.path}` 처럼 **계산된** 경로는 리터럴이 아니라 여기서 읽지 않는다. 그쪽은
    TAB_GROUPS 리더와 JS 대조 테스트가 담당한다.

    **모든 `<Route` 는 셋 중 하나로 분류돼야 한다** — 리터럴 · 계산 · index. 어느 것도
    아니면 그건 «이 리더가 못 읽은 Route» 이고, 예전에는 `continue` 로 조용히 버려졌다.
    이제는 `SourceReadError` 다.
    """
    out: dict[str, dict] = {}
    hits = list(re.finditer(r"<Route\b", text))
    computed = index = 0
    unread: list[str] = []
    for n, m in enumerate(hits):
        stop = hits[n + 1].start() if n + 1 < len(hits) else len(text)
        chunk = text[m.start():min(stop, m.start() + 600)]
        line = _line_of(text, m.start())
        p = re.search(r'path="([^"]+)"', chunk)
        if not p:
            if re.search(r"path=\{", chunk):
                computed += 1
            elif re.search(r"\bindex\b", chunk):
                index += 1
            else:
                unread.append("%s:%d %s" % (rel, line, chunk.split("\n")[0][:60]))
            continue
        nav = re.search(r'<Navigate\s+to="([^"]+)"', chunk)
        out[p.group(1)] = {
            "file": rel, "line": line,
            "navigate_to": nav.group(1) if nav else None,
        }
    if unread:
        raise SourceReadError(
            "%s: `<Route` %d개 중 %d개를 리터럴·계산·index 어느 쪽으로도 읽지 못했다 — "
            "이 리더가 그만큼 눈이 먼 상태다: %s"
            % (rel, len(hits), len(unread), "; ".join(unread[:3])))
    if len(out) < floor:
        raise SourceReadError(
            "%s: 리터럴 Route 를 %d개만 읽었다(하한 %d). 리더가 어긋났거나 Route 가 실제로 "
            "줄었다 — 후자라면 `SOURCE_FLOOR` 를 함께 내려라(그 판단이 이 하한의 목적이다). "
            "`<Route` %d개 · 계산 %d개 · index %d개"
            % (rel, len(out), floor, len(hits), computed, index))
    return out


def read_jsx_routes(path: str) -> dict:
    rel = os.path.relpath(path, ROOT).replace("\\", "/")
    if not os.path.exists(path):
        raise SourceReadError("%s: 파일이 없다 — 읽지 못한 것을 «위반 0» 으로 세지 않는다" % rel)
    return parse_jsx_routes(read(path), rel, floor=SOURCE_FLOOR.get(os.path.basename(path), 0))


def parse_tab_groups(text: str, *, floor: int = 0) -> list[dict]:
    """`AdminRoutes.jsx::TAB_GROUPS` — 그릇 경로와 그 안의 탭 키.

    앵커(`export const TAB_GROUPS = [ … ];`)를 못 찾으면 예전에는 `[]` 였다. 상수 이름을
    바꾸거나 배열을 함수 조립으로 바꾸는 것만으로 이 검사가 통째로 사라졌다는 뜻이다.
    """
    m = re.search(r"export const TAB_GROUPS = \[(.*?)\n\];", text, re.S)
    if not m:
        raise SourceReadError(
            "AdminRoutes.jsx: `export const TAB_GROUPS = [ … ];` 앵커를 못 찾았다. "
            "상수 이름·형태가 바뀌었으면 이 리더를 함께 고쳐라 — 못 읽은 채 통과시키지 않는다")
    body = m.group(1)
    groups: list[dict] = []
    for gm in re.finditer(r'path:\s*"([^"]+)"', body):
        start = gm.end()
        nxt = re.search(r'path:\s*"', body[start:])
        seg = body[start:start + (nxt.start() if nxt else len(body))]
        groups.append({
            "path": gm.group(1),
            "tabs": re.findall(r'key:\s*"([^"]+)"', seg),
            "line": _line_of(text, m.start(1) + gm.start()),
        })
    empty = [g["path"] for g in groups if not g["tabs"]]
    if empty:
        raise SourceReadError(
            "AdminRoutes.jsx: TAB_GROUPS 그릇 %s 에서 탭 키를 하나도 읽지 못했다 — "
            "그릇만 세고 본문을 못 세면 탭 Surface 가 통째로 검사 밖이다" % ", ".join(empty))
    if len(groups) < floor:
        raise SourceReadError(
            "AdminRoutes.jsx: TAB_GROUPS 그릇을 %d개만 읽었다(하한 %d)" % (len(groups), floor))
    return groups


def read_tab_groups() -> list[dict]:
    if not os.path.exists(ADMIN_ROUTES_JSX):
        raise SourceReadError("AdminRoutes.jsx: 파일이 없다")
    return parse_tab_groups(read(ADMIN_ROUTES_JSX), floor=SOURCE_FLOOR["TAB_GROUPS"])


def parse_settings_tabs(text: str, *, floor: int = 0) -> list[str]:
    m = re.search(r"export const TAB_DEFS = \[(.*?)\n\];", text, re.S)
    if not m:
        raise SourceReadError(
            "SettingsShell.jsx: `export const TAB_DEFS = [ … ];` 앵커를 못 찾았다 — "
            "이 리더가 조용해지면 설정 탭 본문 1,216줄이 검사 밖으로 나간다")
    tabs = re.findall(r'key:\s*"([^"]+)"', m.group(1))
    if len(tabs) < floor:
        raise SourceReadError(
            "SettingsShell.jsx: TAB_DEFS 탭을 %d개만 읽었다(하한 %d)" % (len(tabs), floor))
    return tabs


def read_settings_tabs() -> list[str]:
    if not os.path.exists(SETTINGS_SHELL_JSX):
        raise SourceReadError("SettingsShell.jsx: 파일이 없다")
    return parse_settings_tabs(read(SETTINGS_SHELL_JSX), floor=SOURCE_FLOOR["TAB_DEFS"])


def read_harness():
    """하네스는 Python 모듈이라 정규식이 아니라 **import 해서** 읽는다."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from scripts.ui_qa.routes import ALIAS_ROUTES, ALL_ROUTES  # noqa: PLC0415
    if len(ALL_ROUTES) < SOURCE_FLOOR["harness"]:
        raise SourceReadError(
            "scripts/ui_qa/routes.py: ALL_ROUTES 가 %d개다(하한 %d). 하네스가 비면 «찍히는데 "
            "추적되지 않는 화면» 검사가 0번 돈다" % (len(ALL_ROUTES), SOURCE_FLOOR["harness"]))
    return ALL_ROUTES, ALIAS_ROUTES


def c0_source_readers(rep: Report) -> dict | None:
    """C0r — **리더 다섯이 실제로 무엇을 읽었는지 표본 수와 함께 먼저 말한다.**

    C1 이 「위반 0」을 낼 수 있는 방법은 둘이다: 진짜로 일치하거나, 대조할 목록이 비어
    있거나. 예전 출력은 그 둘을 구별하지 못했다 — 아래 한 줄이 그것을 구별한다.

    리더가 하나라도 실패하면 `None` 을 돌려주고 **C1 을 아예 돌리지 않는다.** 눈이 먼
    상태의 대조 결과는 통과도 실패도 아니라 그냥 무의미하다.
    """
    src: dict = {}
    readers = (
        ("user", lambda: read_jsx_routes(USER_ROUTES_JSX)),
        ("admin", lambda: read_jsx_routes(ADMIN_ROUTES_JSX)),
        ("tab_groups", read_tab_groups),
        ("settings_tabs", read_settings_tabs),
        ("harness", read_harness),
    )
    for key, fn in readers:
        try:
            src[key] = fn()
        except SourceReadError as exc:
            rep.fail("C0r 소스 리더가 읽지 못했다", str(exc))
        except Exception as exc:  # noqa: BLE001
            rep.fail("C0r 소스 리더가 읽지 못했다",
                     "%s: %s: %s" % (key, type(exc).__name__, exc))
    if rep.count("C0r"):
        rep.fail("C0r 소스 리더가 읽지 못했다",
                 "리더가 눈을 감은 채로는 C1 을 돌리지 않는다 — 이 실행의 C1 결과는 없다")
        return None
    all_routes, alias_routes = src["harness"]
    rep.ok("소스 리더 표본 — User Route %d · Admin Route %d(리다이렉트 %d) · "
           "TAB_GROUPS %d그릇/%d탭 · 설정 탭 %d · 하네스 Route %d(별칭 %d)"
           % (len(src["user"]), len(src["admin"]),
              sum(1 for v in src["admin"].values() if v["navigate_to"]),
              len(src["tab_groups"]), sum(len(g["tabs"]) for g in src["tab_groups"]),
              len(src["settings_tabs"]), len(all_routes), len(alias_routes)))
    return src


def base_path(route: str) -> str:
    """쿼리를 뗀 경로. 탭·검색 상태 Surface 는 `?tab=`·`?q=` 로 구분해 등록된다."""
    return (route or "").split("?", 1)[0]


def is_major(surface: dict) -> bool:
    """주요 Surface 인가 — **Gate 가 파생한다.** 계획서에 손으로 적은 목록은 늙는다.

    화면이면서 별칭이 아니면 주요다. 위젯(`kind: widget`)은 host 화면의 일부라
    자기 Before/After 쌍을 요구하지 않고, 별칭은 화면이 아니다.
    """
    return surface.get("kind") in ("route", "tab") and not surface.get("alias_of")


def evidence_tokens(items) -> list[str]:
    return [x for x in (items or []) if isinstance(x, str) and x.startswith(EVIDENCE_PREFIXES)]


def real_evidence(items) -> list[str]:
    """`ev:note:` 는 사람이 적은 메모라 증거로 치지 않는다 — 그것만 있으면 근거가 없는 것이다."""
    return [x for x in evidence_tokens(items) if not x.startswith("ev:note:")]


# ─────────────────────────────────────────────────────────────────────────────
# C1 ~ C14
# ─────────────────────────────────────────────────────────────────────────────


def c1_source_vs_coverage(rep: Report, surfaces: list[dict], src: dict) -> None:
    """C1 · C1b — 소스에 있는 화면이 커버리지에 있는가, 그리고 리다이렉트를 화면으로 세지 않는가.

    리더는 여기서 부르지 않는다 — `c0_source_readers` 가 이미 읽었고, 읽지 못했으면 이
    함수는 애초에 호출되지 않는다.
    """
    user = src["user"]
    admin = src["admin"]
    by_route: dict[str, list[dict]] = {}
    for sf in surfaces:
        by_route.setdefault(base_path(sf.get("route")), []).append(sf)
    exact = {sf.get("route"): sf for sf in surfaces}

    literal = {}
    navigate = {}
    # 반복 변수를 `src` 로 두면 위 인자를 가린다 — 실제로 한 번 가렸고 `KeyError` 로 드러났다.
    for in_file in (user, admin):
        for path, meta in in_file.items():
            if path == "*":
                continue
            (navigate if meta["navigate_to"] else literal)[path] = meta

    missing = []
    for path, meta in sorted(literal.items()):
        hits = [x for x in by_route.get(path, []) if x.get("kind") in ("route", "tab")]
        if not hits:
            missing.append("%s (%s:%d)" % (path, meta["file"], meta["line"]))
    for path in missing:
        rep.fail("C1 소스에 있는데 커버리지에 없는 Route", path)

    # 탭 그릇 · 탭 본문 · 설정 탭 — Route 리터럴이 아니라 계산돼 위 정규식이 못 본다.
    for grp in src["tab_groups"]:
        if not [x for x in by_route.get(grp["path"], []) if x.get("kind") in ("route", "tab")]:
            rep.fail("C1 소스에 있는데 커버리지에 없는 Route",
                     "%s (AdminRoutes.jsx:%d TAB_GROUPS 그릇)" % (grp["path"], grp["line"]))
        for tab in grp["tabs"]:
            want = "%s?tab=%s" % (grp["path"], tab)
            if want not in exact:
                rep.fail("C1 커버리지에 없는 탭 본문",
                         "%s (AdminRoutes.jsx:%d) — 탭 본문은 별도 Surface 다" % (want, grp["line"]))
            old = "/" + tab
            if old != grp["path"] and not by_route.get(old):
                rep.fail("C1 커버리지에 없는 옛 주소",
                         "%s (리다이렉트가 아니라 제자리 렌더다)" % old)
    for tab in src["settings_tabs"]:
        want = "/settings?tab=%s" % tab
        if want not in exact:
            rep.fail("C1 커버리지에 없는 탭 본문",
                     "%s (SettingsShell.jsx::TAB_DEFS) — 탭 본문 1,216줄이 검사 밖에 있었다" % want)

    # C1b — 소스가 `<Navigate>` 인 경로.
    for path, meta in sorted(navigate.items()):
        hits = by_route.get(path) or []
        if not hits:
            rep.fail("C1b 리다이렉트가 커버리지에 없다",
                     "%s → %s (%s:%d)" % (path, meta["navigate_to"], meta["file"], meta["line"]))
            continue
        for sf in hits:
            if sf.get("kind") != "state_variant" or not sf.get("alias_of"):
                rep.fail("C1b 리다이렉트를 화면으로 세고 있다",
                         "%s 은 %s 로 가는 <Navigate> 다(%s:%d). Surface %s 의 kind=%s alias_of=%s "
                         "— 찍히는 것은 도착지 화면이고 검사는 전부 거기서 통과한다"
                         % (path, meta["navigate_to"], meta["file"], meta["line"],
                            sf.get("id"), sf.get("kind"), sf.get("alias_of")))

    # 하네스 ↔ 커버리지 (리더 ⑤, 역방향)
    all_routes, alias_routes = src["harness"]
    for r in all_routes:
        p = base_path(r.hash_template.replace("{id}", ":id") or r.hash_path)
        if not by_route.get(base_path(p)):
            rep.fail("C1 하네스에 있는데 커버리지에 없는 Route",
                     "%s (%s) — 찍히는데 추적되지 않는 화면이다" % (r.id, p))
    misfiled = [r.id for r in all_routes if base_path(r.hash_path) in navigate]
    for rid in misfiled:
        rep.fail("C1b 하네스가 리다이렉트를 화면으로 등록했다", rid)
    for r in alias_routes:
        if base_path(r.hash_path) not in navigate:
            rep.fail("C1b 별칭인데 소스는 리다이렉트가 아니다",
                     "%s (%s) — 별칭 목록이 늙었다" % (r.id, r.hash_path))

    if not rep.count("C1"):
        rep.ok("소스 Route %d개 · 탭 본문 %d개 · 리다이렉트 %d개가 커버리지와 일치한다"
               % (len(literal),
                  len(src["settings_tabs"]) + sum(len(g["tabs"]) for g in src["tab_groups"]),
                  len(navigate)))


def c_parity_test_alive(rep: Report) -> None:
    """REGISTRY 28키 대조는 JS 가 한다 — 그 검사가 살아 있는지 확인한다.

    Python 정규식은 이 대조에서 28개 중 1개를 조용히 놓친 전력이 있다. 그래서 Gate 는
    직접 세지 않고 **JS 검사의 존재와 내용**을 확인하고, `static_checks.sh` 가 그걸 돌린다.
    """
    if not os.path.exists(PARITY_TEST_JS):
        rep.fail("C1 REGISTRY 대조 검사가 없다",
                 "frontend/src/screens/registry-surface-parity.test.js — Python 은 이 대조를 "
                 "못 한다(28개 중 1개를 놓친 전력)")
        return
    body = read(PARITY_TEST_JS)
    for token in ("REGISTRY", "TAB_GROUPS", "ROUTE_COVERAGE.json"):
        if token not in body:
            rep.fail("C1 REGISTRY 대조 검사가 비었다", "%s 를 읽지 않는다" % token)
    sc = read(os.path.join(ROOT, "scripts", "static_checks.sh"))
    if "registry-surface-parity" not in sc:
        rep.fail("C1 REGISTRY 대조가 Gate 에 안 걸려 있다",
                 "static_checks.sh 가 registry-surface-parity.test.js 를 돌리지 않는다 — "
                 "존재하지만 아무도 실행하지 않는 검사는 없는 검사다")
    if not rep.count("C1 REGISTRY"):
        rep.ok("REGISTRY 키 대조를 JS 가 증명하고 static_checks 가 실행한다")


def c2_statuses(rep: Report, scoped: list[dict]) -> None:
    for sf in scoped:
        st = sf.get("status")
        if st not in SURFACE_STATUSES:
            rep.fail("C2 Surface status 값이 잘못됐다", "%s: %s" % (sf.get("id"), st))
        elif st in BAD_STATUSES:
            rep.fail("C2 미검사 Surface 가 남아 있다",
                     "%s (wave=%s, status=%s)" % (sf.get("id"), sf.get("wave"), st))
    if scoped:
        rep.ok("이 Wave 가 담당하는 Surface %d개에 UNKNOWN/TODO/NOT_AUDITED 가 없다" % len(scoped))


def c_shape(rep: Report, surfaces: list[dict]) -> None:
    """Wave 와 무관하게 항상 참이어야 하는 Surface 자체의 형태.

    Archetype 미분류는 "아직 안 봤다"와 같은 말이라 Wave 로 봐줄 대상이 아니다 —
    지시 84-9 Plan Gate 3번(전 Route 가 Archetype 으로 분류)이 W0 의 종료 조건이다.
    """
    waves = _waves()
    for sf in surfaces:
        sid = sf.get("id")
        arch = sf.get("archetype")
        if arch not in ARCHETYPES:
            rep.fail("C2 Archetype 미분류", "%s: %r" % (sid, arch))
        if sf.get("wave") not in waves:
            rep.fail("C2 없는 Wave", "%s: %r" % (sid, sf.get("wave")))
        if is_major(sf) and not sf.get("component"):
            rep.fail("C2 구현 위치 없음", "%s — 어떤 파일이 그리는지 모르면 고칠 수도 없다" % sid)
        if sf.get("alias_of") and sf.get("kind") != "state_variant":
            rep.fail("C1b 별칭인데 kind 가 state_variant 가 아니다", str(sid))
    if not rep.count("C2 Archetype"):
        rep.ok("Surface %d개가 전부 Archetype 으로 분류됐다" % len(surfaces))


def c3_requirement_mapping(rep: Report, surfaces: list[dict], waves: set[str]) -> None:
    """C3 — Matrix ↔ Surface 양방향. 매핑 안 된 요구도, 요구 없는 주요 화면도 실패다."""
    entries = parse_matrix(read(MATRIX))
    ids = {s.get("id") for s in surfaces}
    consoles = {s.get("console") for s in surfaces}
    for e in entries:
        where = "%s (line %d)" % (e["id"], e["line"])
        aff = e["fields"].get("Affected", "").strip()
        if aff.startswith("NONE"):
            if len(aff) < 45:
                rep.fail("C3 NONE 사유가 짧다", where)
            continue
        if aff == "ALL":
            continue
        resolved = 0
        for tok in [t.strip() for t in aff.split(",") if t.strip()]:
            if tok.startswith("CONSOLE:"):
                if tok.split(":", 1)[1] in consoles:
                    resolved += 1
                else:
                    rep.fail("C3 없는 Console 참조", "%s: %s" % (where, tok))
            elif tok.startswith("ARCHETYPE:"):
                arch = tok.split(":", 1)[1]
                if arch not in ARCHETYPES:
                    rep.fail("C3 없는 Archetype 참조", "%s: %s" % (where, tok))
                elif any(s.get("archetype") == arch for s in surfaces):
                    resolved += 1
                else:
                    rep.fail("C3 0 Surface 로 해석되는 Archetype", "%s: %s" % (where, tok))
            elif tok in ids:
                resolved += 1
            else:
                rep.fail("C3 없는 Surface 참조",
                         "%s: %s — ROUTE_COVERAGE 의 id 가 아니다(하네스 id 와 표기가 다르다)"
                         % (where, tok))
        if not resolved:
            rep.fail("C3 Affected 가 0 Surface 로 해석된다",
                     "%s: %r — 특정 화면에 살지 않으면 `NONE (사유)` 로 적는다" % (where, aff[:60]))

    mapped = set()
    for sf in surfaces:
        mapped.update(sf.get("requirements") or [])
    known = {e["id"] for e in entries}
    for rid in sorted(mapped - known):
        rep.fail("C3 Surface 가 없는 요구사항을 가리킨다", rid)
    naked = [s.get("id") for s in surfaces if is_major(s) and not (s.get("requirements") or [])]
    for sid in naked:
        rep.fail("C3 주요 Surface 에 요구사항이 없다",
                 "%s — 무엇 때문에 고치는지 없으면 무엇이 끝인지도 없다" % sid)
    if not naked and not rep.count("C3"):
        rep.ok("주요 Surface 전부가 요구사항에 연결됐다 (Matrix 참조도 전부 해석된다)")
    _ = waves


def _cap_ok(cap) -> tuple[bool, str]:
    if not isinstance(cap, dict):
        return False, "없음"
    path = cap.get("path")
    if not path:
        return False, "path 없음"
    if not os.path.exists(os.path.join(ROOT, path)):
        return False, "파일이 없다: %s" % path
    if not cap.get("build_index_sha256"):
        return False, "build_index_sha256 없음"
    return True, ""


def c4_c6_evidence(rep: Report, surfaces: list[dict], scoped: list[dict], build_sha: str) -> None:
    """C4 완료인데 Evidence 없음 · C6 Before/After.

    Before 는 Wave 로 봐주지 않는다 — 제품 코드가 바뀌기 전에만 찍을 수 있고 그 창은 W0 에
    한 번뿐이다. 나중에 "이 Wave 것만 찍겠다"는 선택지가 애초에 없다.
    """
    for sf in surfaces:
        if not is_major(sf):
            continue
        ok, why = _cap_ok(sf.get("before_capture"))
        if not ok:
            rep.fail("C6 Before 캡처 없음", "%s: %s" % (sf.get("id"), why))
    if not rep.count("C6 Before"):
        rep.ok("주요 Surface 전부에 Before 캡처가 있다")

    for sf in scoped:
        sid = sf.get("id")
        if sf.get("status") != "DONE":
            continue
        ev = real_evidence((sf.get("evidence") or {}).get("items") or sf.get("evidence_items") or [])
        if not ev:
            rep.fail("C4 완료인데 Evidence 없음",
                     "%s — `ev:note:` 단독은 증거가 아니다" % sid)
        stale = [x for x in (sf.get("evidence") or {}).get("build_index_sha256", [build_sha])
                 if build_sha and x and x != build_sha]
        if stale:
            rep.fail("C4 EVIDENCE_STALE_BUILD", "%s: %s (현재 %s)" % (sid, stale, build_sha))
        if is_major(sf):
            ok, why = _cap_ok(sf.get("after_capture"))
            if not ok:
                rep.fail("C6 완료인데 After 캡처 없음", "%s: %s" % (sid, why))
            else:
                b = (sf.get("before_capture") or {}).get("build_index_sha256")
                a = (sf.get("after_capture") or {}).get("build_index_sha256")
                if b and a and b == a:
                    rep.fail("C6 Before 와 After 가 같은 번들이다",
                             "%s (%s) — 같은 빌드의 before/after 는 before/after 가 아니다" % (sid, b))


def c5_audits(rep: Report, scoped: list[dict], profiles: dict) -> None:
    for sf in scoped:
        sid = sf.get("id")
        if sf.get("status") in ("NOT_AUDITED", "IN_PROGRESS", "BLOCKED", "DEFERRED"):
            continue
        for key in ("visual_audit", "functional_audit"):
            aud = sf.get(key) or {}
            res = aud.get("result")
            if res not in AUDIT_RESULTS:
                rep.fail("C5 Audit 결과 값이 잘못됐다", "%s.%s: %r" % (sid, key, res))
                continue
            if res == "PENDING":
                rep.fail("C5 Audit 이 비어 있다", "%s.%s" % (sid, key))
                continue
            if res == "PASS":
                if not real_evidence(aud.get("evidence")):
                    rep.fail("C5 PASS 인데 증거가 note 뿐이다", "%s.%s" % (sid, key))
                if not aud.get("by") or not aud.get("at"):
                    rep.fail("C5 PASS 에 누가·언제가 없다", "%s.%s" % (sid, key))
        if is_major(sf) and not ((sf.get("functional_audit") or {}).get("flows")):
            rep.fail("C5 주요 Surface 에 Flow 가 없다", sid)
        resp = sf.get("responsive_audit") or {}
        prof = profiles.get(resp.get("required_profile") or "")
        if prof:
            want = len(prof.get("viewports", [])) * len(prof.get("themes", [])) * len(prof.get("zooms", [1]))
            got = len(resp.get("matrix") or [])
            if got < want:
                rep.fail("C5 Responsive 교차곱 미달",
                         "%s: %d/%d (profile=%s)" % (sid, got, want, resp.get("required_profile")))


def _latest_results(rep: Report, label: str = "", cov: dict | None = None) -> dict:
    """이 Wave 의 **After 실행** 결과. Coverage 의 finding 행이 아니라 측정 원본을 다시 읽는다.

    행을 지워서 finding 을 닫을 수 없게 하는 것이 목적이다.

    ── W5 정정: «가장 최근» 이 아니라 «Coverage 가 After 라고 선언한 것» ──────────
    예전에는 `dist/ui-qa/*/results.json` 중 **mtime 이 가장 최신**인 것을 골랐다. 그런데
    Wave 하나가 끝날 무렵에는 전량 실행(664 페이지) 뒤에 작은 보조 실행(모달 10 페이지,
    스모크 몇 페이지)이 이어지는 것이 정상 절차라, 그 마지막 작은 실행이 항상 이긴다.
    실제로 W4 에서 이 백스톱은 `w4-modals`(10 페이지 · 5 라우트 · 1 뷰포트)를 읽고 있었다 —
    664 페이지 중 654 페이지의 실패를 **구조적으로 못 보는 상태**였다. 백스톱이 백스톱을
    안 하고 있었던 것이다.

    그래서 순서를 바꾼다: ① 호출부가 라벨을 주면 그것 ② `ROUTE_COVERAGE.capture_labels.after`
    ③ 그래도 없으면 **페이지 수가 가장 많은** 실행(가장 최신이 아니라). 셋 다 «작은 실행이
    큰 실행을 덮는다» 를 막는다.
    """
    root = os.path.join(ROOT, "dist", "ui-qa")
    if not os.path.isdir(root):
        return {}
    want = label or ((cov or {}).get("capture_labels") or {}).get("after") or ""
    cands = []
    for name in os.listdir(root):
        path = os.path.join(root, name, "results.json")
        if not os.path.exists(path):
            continue
        if want and name != want:
            continue
        try:
            pages = len(json.load(io.open(path, encoding="utf-8")).get("pages") or [])
        except Exception:  # noqa: BLE001
            pages = 0
        cands.append((pages, os.path.getmtime(path), name, path))
    if not cands and want:
        rep.fail("C10 After 라벨의 QA 결과가 없다",
                 "capture_labels.after=%s — dist/ui-qa/%s/results.json 를 찾지 못했다" % (want, want))
        return {}
    if not cands:
        return {}
    cands.sort()
    _, _, name, path = cands[-1]
    try:
        data = json.load(io.open(path, encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        rep.fail("C10 QA 결과를 읽을 수 없다", "%s: %s" % (path, exc))
        return {}
    data["__label"] = name
    return data


def _assert_status(results: dict) -> dict:
    """`class -> {surface_or_route -> status}` 로 접는다."""
    out: dict[str, dict[str, str]] = {}
    for page in results.get("pages") or []:
        # 하네스 id 는 `route` 키에 들어간다(`results.json` 실측). `route_id` 를 읽으면
        # 언제나 None 이라 이 검사가 조용히 통과한다.
        key = page.get("route") or page.get("hash_path") or "?"
        for cls, verdict in (page.get("assertions") or {}).items():
            out.setdefault(cls, {})[key] = (verdict or {}).get("status", "?")
    return out


def c0_after_label_current(rep: Report, cov: dict) -> None:
    """**선언한 After 가 이번 Wave 의 전량 실행인가.**

    ── W5 정정 ────────────────────────────────────────────────────────────────
    `_latest_results` 가 «가장 최근» 대신 «Coverage 가 After 라고 선언한 것» 을 읽게 바꾸자
    새 구멍이 생겼다: **그 선언이 낡으면 게이트가 낡은 실행을 읽는다.** 실제로 그랬다 —
    `capture_labels.after` 는 W1 이 적은 `w1-after` 그대로였고, W2·W3·W4 는 자기 실행을
    돌려 놓고 포인터를 안 옮겼다. 즉 세 Wave 의 `--stage wave` 는 **W1 의 측정**을 보고
    초록이 됐다.

    선언을 믿되 **낡았으면 말한다**: `dist/ui-qa/` 안에 그 선언보다 페이지가 많은 실행이
    있으면 그것은 «전량 실행을 하고도 가리키지 않았다» 는 뜻이다. 백스톱이 백스톱을 하려면
    자기가 무엇을 읽고 있는지도 검사 대상이어야 한다.
    """
    want = ((cov or {}).get("capture_labels") or {}).get("after") or ""
    if not want:
        rep.fail("C0 After 라벨이 선언되지 않았다",
                 "ROUTE_COVERAGE.capture_labels.after 가 비었다 — 게이트가 무엇을 읽어야 하는지 모른다")
        return
    root = os.path.join(ROOT, "dist", "ui-qa")
    if not os.path.isdir(root):
        return
    sizes = {}
    for name in os.listdir(root):
        path = os.path.join(root, name, "results.json")
        if not os.path.exists(path):
            continue
        try:
            with io.open(path, encoding="utf-8") as fh:
                sizes[name] = len((json.load(fh).get("pages") or []))
        except Exception:  # noqa: BLE001 - 깨진 실행은 후보가 아니다
            continue
    if want not in sizes:
        rep.fail("C0 선언한 After 실행이 없다",
                 "capture_labels.after=%s — dist/ui-qa/%s/results.json 이 없다" % (want, want))
        return
    bigger = sorted(((n, c) for n, c in sizes.items() if c > sizes[want]),
                    key=lambda x: -x[1])
    if bigger:
        rep.fail("C0 선언한 After 가 낡았다",
                 "capture_labels.after=%s (%d페이지) 인데 더 큰 실행이 있다: %s. "
                 "전량 실행을 하고도 가리키지 않으면 게이트는 옛 측정을 읽는다"
                 % (want, sizes[want], ", ".join("%s(%d)" % b for b in bigger[:3])))
    else:
        rep.ok("After 라벨 `%s` 가 이 저장소에서 가장 큰 실행이다 (%d페이지)"
               % (want, sizes[want]))


def c10c_promotion_enforced(rep: Report, cov: dict, waves: list, wave: str) -> None:
    """승격했다고 적은 검사가 **실제로 `--fail-on` 으로 걸린 채** 돌았는가."""
    want = _promoted_upto(waves, wave)
    if not want:
        return
    results = _latest_results(rep, cov=cov)
    if not results:
        return
    got = set((results.get("run") or {}).get("fail_on") or [])
    missing = sorted(want - got)
    if missing:
        rep.fail("C10c 승격한 검사가 `--fail-on` 없이 돌았다",
                 "%s — After 실행(%s)의 fail_on=%s. 승격은 선언이 아니라 실행이다"
                 % (", ".join(missing), results.get("__label"), sorted(got) or "(없음)"))
    else:
        rep.ok("승격한 검사 %d개가 `--fail-on` 으로 걸린 채 돌았다 (%s)"
               % (len(want), results.get("__label")))


def c9_c10_findings(rep: Report, surfaces: list[dict], scoped: list[dict], stage: str, cov: dict) -> None:
    results = _latest_results(rep, cov=cov)
    per_class = _assert_status(results)

    for sf in scoped:
        sid = sf.get("id")
        if sf.get("archetype") != "list_table" or sf.get("status") != "DONE":
            continue
        seen = (sf.get("evidence") or {}).get("qa_run") or {}
        for cls in TABLE_ASSERTIONS:
            got = seen.get(cls)
            if got in (None, "skip"):
                rep.fail("C9 컬럼 폭·정렬 판정 증거 없음",
                         "%s.%s=%r — `skip` 은 증거가 아니다(폭 >=1366 에서 실제 판정이 필요하다)"
                         % (sid, cls, got))

    for sf in scoped:
        if sf.get("status") != "DONE":
            continue
        for fd in sf.get("findings") or []:
            if fd.get("class") in LAYOUT_CLASSES and fd.get("status") != "CLOSED":
                rep.fail("C10 완료 화면에 Layout Finding 잔존",
                         "%s: %s (%s)" % (sf.get("id"), fd.get("id"), fd.get("class")))

    # 행을 지워도 소용없게 — 최신 실행에서 fail 이면 Coverage 에 finding 이 없어도 실패다.
    if per_class:
        done = {s.get("id") for s in scoped if s.get("status") == "DONE"}
        harness_of = {s.get("harness_id") or s.get("id") for s in surfaces if s.get("id") in done}
        for cls in LAYOUT_CLASSES:
            for key, st in (per_class.get(cls) or {}).items():
                if st == "fail" and key in harness_of:
                    rep.fail("C10 최신 QA 실행에서 여전히 실패한다",
                             "%s @ %s (label=%s)" % (cls, key, results.get("__label")))
    elif stage == "complete":
        rep.fail("C10 최신 QA 결과가 없다", "dist/ui-qa/*/results.json 이 이 머신에 없다")


# W4 종료 조건 — "`surface_repetition`·`oversized_empty_surface` Advisory 수치가
# **Surface 별로 기록됨**". 이 두 검사는 임계값이 취향을 인코딩하므로 영구 Advisory 다
# (PLAN «Gate vs Advisory»). Advisory 는 실패해도 게이트를 막지 않으니, 대신 **잰 값이
# 남아 있는지**를 게이트가 본다 — 안 그러면 "측정했다" 와 "측정하지 않았다" 가 똑같이
# 조용하다. `merge_qa_findings.py` 가 실행마다 `surface.advisory[cls]` 에 적는다.
ADVISORY_RECORDED = ("surface_repetition", "oversized_empty_surface")


def c10b_advisory_recorded(rep: Report, scoped: list[dict], wave: str) -> None:
    """W4 이후, 완료로 표시된 Surface 는 두 Advisory 의 실측 숫자를 갖고 있어야 한다."""
    order = _waves()
    if wave not in order or "W4" not in order or order.index(wave) < order.index("W4"):
        return
    missing = []
    for sf in scoped:
        if sf.get("status") != "DONE":
            continue
        rec = sf.get("advisory") or {}
        for cls in ADVISORY_RECORDED:
            got = rec.get(cls)
            if not got or not got.get("label"):
                missing.append("%s.%s" % (sf.get("id"), cls))
                continue
            # 전부 skip 이면 잰 것이 아니다 — `narrow_main` 의 "144 pass / 144 skip" 함정.
            if not (got.get("pass") or got.get("fail")):
                missing.append("%s.%s (전부 skip — 재지 않았다)" % (sf.get("id"), cls))
    if missing:
        for row in missing[:20]:
            rep.fail("C10b Advisory 수치가 Surface 에 기록되지 않았다", row)
    else:
        rep.ok("완료 Surface 전부에 `surface_repetition`·`oversized_empty_surface` 실측 수치가 있다")


def c7_findings_accepted(rep: Report, surfaces: list[dict]) -> None:
    entries = parse_matrix(read(MATRIX))
    deferred_findings = set()
    for e in entries:
        if e["fields"].get("Status") == "DEFERRED":
            deferred_findings.update(re.findall(r"F-\d+", e["fields"].get("Findings", "")))
    for sf in surfaces:
        for fd in sf.get("findings") or []:
            sev = (fd.get("severity") or "").capitalize()
            if sev not in ("Critical", "High"):
                continue
            st = fd.get("status")
            if st == "CLOSED":
                continue
            if st != "ACCEPTED":
                rep.fail("C7 Critical/High Finding 잔존",
                         "%s: %s (%s, %s)" % (sf.get("id"), fd.get("id"), sev, st))
                continue
            why = fd.get("accepted_reason") or ""
            if len(why) < 60:
                rep.fail("C7 수용 사유가 짧다", "%s: %d자 (60자 이상)" % (fd.get("id"), len(why)))
            if fd.get("id") not in deferred_findings:
                rep.fail("C7 수용이 결정에 추적되지 않는다",
                         "%s 가 어떤 DEFERRED 요구사항의 Findings 에도 없다" % fd.get("id"))


def c8_entity_selectors(rep: Report, scoped: list[dict], cov: dict) -> None:
    results = _latest_results(rep, cov=cov)
    per_class = _assert_status(results)
    runtime = per_class.get("plain_dropdown_for_entity") or {}
    for sf in scoped:
        declared = sf.get("entity_selectors") or []
        if not declared:
            continue
        key = sf.get("harness_id") or sf.get("id")
        st = runtime.get(key)
        if st == "fail":
            rep.fail("C8 검색형이어야 할 Entity Selector 가 평범한 Dropdown 이다",
                     "%s: %s" % (sf.get("id"), ", ".join(declared)))
        elif sf.get("status") == "DONE" and st in (None, "skip"):
            rep.fail("C8 Entity Selector 판정 증거 없음",
                     "%s: 런타임 판정이 %r 다 — 정적 후보만으로는 통과시키지 않는다"
                     % (sf.get("id"), st))


def c11_c14_functional(rep: Report, surfaces: list[dict], func: dict, scoped_ids: set[str],
                       stage: str) -> None:
    by_id = {s.get("id"): s for s in surfaces}
    fsurf = {f.get("surface"): f for f in (func.get("surfaces") or [])}

    for sid, entry in sorted(fsurf.items()):
        if entry.get("inventory_status") in (None, "NOT_INVENTORIED"):
            rep.fail("C12 Functional Inventory 미작성",
                     "%s — 27개 범주 중 이 화면에 실재하는 것이 무엇인지 아무도 세지 않았다" % sid)

    # Flow ID 는 **전역 유일**해야 한다. Surface 별로만 유일하면 증거가 어느 화면 것인지
    # 말할 수 없다 — `functional_audit.flows` 는 ID 목록일 뿐이고, `*_e2e.py` 산출물도
    # `flows.json` 안에서 ID 로만 식별된다. W2 가 `shell_topbar` 에 새 Flow 다섯을 추가하면서
    # W0 이 `shell_sidebar` 에 이미 준 번호와 겹쳤고(FF-1193~1197), 아무 검사도 그것을
    # 못 봤다. 여기서 막는다 — 겹친 순간 두 Surface 의 증거가 서로를 덮는다.
    # 범위를 현재 Wave 로 좁히지 않는다: 충돌은 두 Surface 사이의 성질이라 한쪽만 보면 안 보인다.
    seen_flow_ids: dict[str, str] = {}
    for sid, entry in sorted(fsurf.items()):
        for fl in entry.get("flows") or []:
            fid = fl.get("id")
            if not fid:
                rep.fail("C12 Flow 에 ID 가 없다", "%s: %r" % (sid, fl.get("name")))
                continue
            if fid in seen_flow_ids:
                rep.fail("C12 Flow ID 가 겹친다",
                         "%s 를 %s 와 %s 가 함께 쓴다 — 증거가 어느 화면 것인지 말할 수 없다"
                         % (fid, seen_flow_ids[fid], sid))
            else:
                seen_flow_ids[fid] = sid

    for sid in sorted(scoped_ids):
        entry = fsurf.get(sid)
        if entry is None:
            continue
        sf = by_id.get(sid) or {}
        flows = entry.get("flows") or []
        for fl in flows:
            if fl.get("category") not in (func.get("categories") or []):
                rep.fail("C12 없는 범주", "%s/%s: %r" % (sid, fl.get("id"), fl.get("category")))
            if fl.get("status") not in FLOW_STATUSES:
                rep.fail("C12 Flow status 값이 잘못됐다", "%s/%s: %r" % (sid, fl.get("id"), fl.get("status")))
            if fl.get("exists") and fl.get("status") == "NOT_AUDITED":
                rep.fail("C12 검증하지 않은 Flow 가 남아 있다", "%s/%s (%s)"
                         % (sid, fl.get("id"), fl.get("category")))
            if fl.get("status") == "PASS":
                chain = fl.get("chain") or {}
                gap = [k for k in CHAIN_MIN if not chain.get(k)]
                if gap:
                    rep.fail("C11 PASS 인데 사슬이 비어 있다",
                             "%s/%s: %s 없음 — 화면에서 값이 바뀐 것은 정상 동작의 증거가 아니다"
                             % (sid, fl.get("id"), ", ".join(gap)))
                bad = [k for k in chain if k not in CHAIN_STEPS]
                if bad:
                    rep.fail("C11 사슬에 없는 단계", "%s/%s: %s" % (sid, fl.get("id"), bad))
            if fl.get("status") == "FAIL":
                for fd in fl.get("findings") or []:
                    if fd.get("class") in DEAD_CLASSES and fd.get("status") != "CLOSED":
                        rep.fail("C14 죽은 Action / Backend 미연결 잔존",
                                 "%s/%s: %s (%s)" % (sid, fl.get("id"), fd.get("id"), fd.get("class")))

        cats = {fl.get("category") for fl in flows}
        if cats & FILTERISH:
            names = {fl.get("name", "") for fl in flows}
            for needed, why in (
                ("복합", "복합 조건 Flow"), ("초기화", "page 리셋 Flow"),
                ("경합", "race Flow"), ("캐시", "cache key Flow"), ("뒤로", "back/forward Flow"),
            ):
                if not any(needed in n for n in names):
                    rep.fail("C11 Filter 검증 범주 누락", "%s: %s 가 없다" % (sid, why))
        derived = {"user_me", "admin_dashboard", "user_sprint", "user_my-stats"}
        if sid in derived:
            for fl in flows:
                exp = fl.get("expected") or {}
                if fl.get("status") == "PASS" and exp.get("source") not in ("known-data", "derived-check"):
                    rep.fail("C13 KPI 가 렌더 여부로만 통과했다",
                             "%s/%s: expected.source=%r" % (sid, fl.get("id"), exp.get("source")))
        for fl in flows:
            if fl.get("category") in ("status_change", "priority_change", "assignee_change",
                                      "create", "delete", "inline_edit"):
                if fl.get("status") == "PASS" and not (fl.get("cross_surface") or []):
                    rep.fail("C13 화면 간 정합성 확인 없음",
                             "%s/%s (%s) — 한 화면이 200 이라고 완료가 아니다"
                             % (sid, fl.get("id"), fl.get("category")))
        _ = sf

    if stage == "complete":
        leftover = [
            "%s/%s" % (sid, fl.get("id"))
            for sid, entry in fsurf.items()
            for fl in (entry.get("flows") or [])
            if fl.get("exists") and fl.get("status") == "NOT_AUDITED"
        ]
        for x in leftover[:50]:
            rep.fail("C12 완료 시점에 NOT_AUDITED Flow 잔존", x)

    if not rep.count("C12 Functional Inventory"):
        rep.ok("Functional Inventory 가 Surface %d개에 대해 작성됐다" % len(fsurf))


def c_suppressions(rep: Report, surfaces: list[dict]) -> int:
    """억제 규율 — 억제는 결정이 아니라 **날짜 있는 약속**이다."""
    text = read(SUPPRESSIONS)
    rows = []
    for line in text.split("\n"):
        if not line.startswith("|") or line.startswith("|---") or "| id |" in line:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 9 and cells[0] and cells[0] != "id":
            rows.append(cells)

    from datetime import date
    seen_class: dict[str, int] = {}
    for cells in rows:
        rid, assertion, marker, surface, reason, owner, opened, expires = cells[:8]
        where = "%s (%s)" % (rid, assertion)
        if assertion in UNSUPPRESSIBLE:
            rep.fail("S1 억제할 수 없는 클래스", where)
        seen_class[assertion] = seen_class.get(assertion, 0) + 1
        if len(reason) < 40:
            rep.fail("S2 사유가 짧다", "%s: %d자" % (where, len(reason)))
        for banned in ("임시", "나중에", "TODO", "일단"):
            if banned in reason:
                rep.fail("S2 사유에 금지어", "%s: %r — 이건 억제가 아니라 DEFERRED 다" % (where, banned))
        if not owner:
            rep.fail("S3 owner 없음", where)
        try:
            o = date.fromisoformat(opened)
            x = date.fromisoformat(expires)
        except ValueError:
            rep.fail("S4 날짜 형식", "%s: opened=%r expires=%r" % (where, opened, expires))
            continue
        if (x - o).days > 60:
            rep.fail("S4 만료가 60일을 넘는다", "%s: %d일" % (where, (x - o).days))
        declared = {s for sf in surfaces for s in (sf.get("suppressions") or [])}
        if rid not in declared and surface:
            rep.fail("S5 Surface 가 이 억제를 선언하지 않는다", "%s → %s" % (rid, surface))
        # 소스 쪽 마커와의 양방향 정합.
        hits = 0
        for base, _dirs, files in os.walk(os.path.join(ROOT, "frontend", "src")):
            for name in files:
                if name.endswith((".jsx", ".js")) and marker in read(os.path.join(base, name)):
                    hits += 1
        if not hits:
            rep.fail("S6 표에는 있는데 소스에 마커가 없다", "%s: %s" % (where, marker))

    # 반대 방향 — 소스에 마커가 있는데 표에 행이 없다. 이쪽이 더 위험하다: 마커를 붙이는
    # 순간 그 검사가 조용히 꺼지는데 표에는 흔적이 없어 만료도 예산도 걸리지 않는다.
    declared_markers = {c[2] for c in rows if len(c) > 2 and c[2]}
    src_root = os.path.join(ROOT, "frontend", "src")
    for base, _dirs, files in os.walk(src_root):
        for name in files:
            if not name.endswith((".jsx", ".js")) or ".test." in name:
                continue
            path = os.path.join(base, name)
            body = read(path)
            for marker in SUPPRESSION_MARKERS:
                if marker in body and marker not in declared_markers:
                    rel = os.path.relpath(path, ROOT).replace("\\", "/")
                    line = body[: body.index(marker)].count("\n") + 1
                    rep.fail("S6 소스에 마커가 있는데 표에 행이 없다",
                             "%s @ %s:%d — 마커 하나가 검사를 조용히 끄고 있다" % (marker, rel, line))

    if len(rows) > 15:
        rep.fail("S7 억제 예산 초과", "%d행 (상한 15)" % len(rows))
    for cls, n in seen_class.items():
        if n > 2:
            rep.fail("S7 클래스당 억제 상한 초과", "%s: %d행 (상한 2)" % (cls, n))
    return len(rows)


def _waves() -> list[str]:
    try:
        route = json.load(io.open(ROUTE_COV, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    return list(route.get("waves") or [])


def _current_wave(explicit: str) -> str:
    if explicit:
        return explicit
    m = re.search(r"^-\s*wave:\s*(\S+)", read(WORK_STATE), re.M)
    return m.group(1) if m else ""


def _run_conditions(rep: Report, stage: str, wave: str) -> int:
    route, func, waves = check_json_artifacts(rep)
    surfaces = route.get("surfaces") or []
    order = list(route.get("waves") or [])
    if wave not in order:
        print("[FAIL] 알 수 없는 Wave: %r (waves=%s)" % (wave, order))
        return EXIT_CANNOT_RUN
    upto = set(order[: order.index(wave) + 1])
    scoped = [s for s in surfaces if s.get("wave") in upto]

    # **CHECKPOINT 가 실제 작업보다 뒤에 있으면 실패한다.**
    #
    # 이 게이트는 검사 범위를 `WORK_STATE.md` 의 `wave:` 에서 읽고 그 값을 믿는다. 그래서 그
    # 줄을 올리는 것을 잊으면 게이트가 **조용히 앞 Wave 를 다시 검사하고 초록을 찍는다** —
    # W3 에서 실제로 그랬고, 문서가 그 초록을 이번 Wave 의 증거로 인용했다(F-W3R-03).
    # 잡을 수 있는 모순은 하나다: 어떤 Surface 가 Wave X 소유이면서 이미 `DONE` 인데
    # CHECKPOINT 가 X 보다 앞을 가리키고 있다면, 게이트는 **이미 끝났다고 적힌 것을 범위에서
    # 빼고** 검사하는 중이다. 그건 초록이 아무것도 뜻하지 않는 상태다.
    rank = {name: i for i, name in enumerate(order)}
    done_ranks = [rank[s.get("wave")] for s in surfaces
                  if s.get("status") == "DONE" and s.get("wave") in rank]
    if done_ranks and max(done_ranks) > rank[wave]:
        behind = order[max(done_ranks)]
        rep.fail("C2 CHECKPOINT 가 실제 작업보다 뒤에 있다",
                 "WORK_STATE 의 wave 는 %s 인데 %s 소유 Surface 가 이미 DONE 이다 — "
                 "이 실행은 그 Surface 를 범위에서 빼고 검사한다. CHECKPOINT 를 먼저 올려라"
                 % (wave, behind))
    scoped_ids = {s.get("id") for s in scoped}
    build_sha = ""
    # WORK_STATE 는 이 값을 코드 스팬(`…`)으로 적는다 — 사람이 읽는 문서이므로 그게 맞다.
    # 예전 정규식은 `(\S+)` 라 **백틱까지 캡처**해서, 값이 같아도 EVIDENCE_STALE_BUILD 로
    # 실패했다(W2 에서 처음 밟았다 — W1 까지는 DONE 인 Surface 가 없어 이 비교가 안 돌았다).
    # 해시 문자만 잡는다.
    m = re.search(r"^-\s*build_index_sha256:\s*`?([0-9a-fA-F]{8,64})`?", read(WORK_STATE), re.M)
    if m:
        build_sha = m.group(1)

    check_matrix(rep, waves)
    check_plan_structure(rep, waves)
    check_work_state(rep, waves)
    c_parity_test_alive(rep)
    sources = c0_source_readers(rep)
    if sources is not None:
        c1_source_vs_coverage(rep, surfaces, sources)
    c_shape(rep, surfaces)
    c2_statuses(rep, scoped)
    c3_requirement_mapping(rep, surfaces, waves)
    c4_c6_evidence(rep, surfaces, scoped, build_sha)
    c5_audits(rep, scoped, route.get("responsive_profiles") or {})
    c8_entity_selectors(rep, scoped, route)
    c9_c10_findings(rep, surfaces, scoped, stage, route)
    c0_after_label_current(rep, route)
    c10c_promotion_enforced(rep, route, order, wave)
    c10b_advisory_recorded(rep, scoped, wave)
    c11_c14_functional(rep, surfaces, func, scoped_ids, stage)
    if stage == "complete":
        c7_findings_accepted(rep, surfaces)
    suppressed = c_suppressions(rep, surfaces)

    code = rep.emit()
    print("억제 %d건" % suppressed)
    if code == EXIT_OK:
        print("UI_RENEWAL_COVERAGE_OK (stage=%s, wave=%s, 억제 %d건)" % (stage, wave, suppressed))
    else:
        print("UI_RENEWAL_COVERAGE_FAILED (stage=%s, wave=%s, 위반 %d건, 억제 %d건)"
              % (stage, wave, len(rep.fails), suppressed))
    return code


def stage_wave(wave: str) -> int:
    rep = Report()
    return _run_conditions(rep, "wave", _current_wave(wave))


def stage_complete(wave: str) -> int:
    rep = Report()
    root = os.path.join(ROOT, "dist", "ui-qa")
    if not os.path.isdir(root) or not os.listdir(root):
        print("[FAIL] --stage complete 인데 증거 Artifact 가 이 머신에 없다 (dist/ui-qa/ 비어 있음).")
        print("       이것을 통과로 접지 않는다 — 증거를 못 보는 것과 증거가 없는 것은 다르다.")
        print("UI_RENEWAL_COVERAGE_NO_EVIDENCE (stage=complete)")
        return EXIT_NO_EVIDENCE
    order = _waves()
    return _run_conditions(rep, "complete", _current_wave(wave) or (order[-1] if order else ""))


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


# ─────────────────────────────────────────────────────────────────────────────
# 리더 자기검증 — 양방향
#
# 「빈 결과 FATAL」은 그 자체가 규칙이라 **규칙이 살아 있는지**를 따로 증명해야 한다.
# 아래 사례는 합성 소스 문자열이다(제품 파일이 아니다) — 제품이 바뀌어도 반례는 살아 있어야
# 다음 사람이 규칙을 되돌릴 때 걸린다(`scripts/ui_qa/probe_selftest.py` 와 같은 발상).
# ─────────────────────────────────────────────────────────────────────────────

_JSX_HEALTHY = '''
  <Routes>
    <Route path="/" element={<Home />} />
    <Route path="/tickets" element={<Tickets />} />
    <Route path="/old" element={<Navigate to="/tickets" replace />} />
  </Routes>
'''
_JSX_COMPUTED = '''
  <Routes>
    <Route path="/keep" element={<Keep />} />
    {TAB_GROUPS.map((g) => (
      <Route key={g.path} path={g.path} element={<Shell />} />
    ))}
  </Routes>
'''
_JSX_BLIND = '''
  <Routes>
    <Route element={<Home />} />
  </Routes>
'''
_TABS_HEALTHY = '''
export const TAB_GROUPS = [
  { path: "/backup", tabs: [{ key: "backup" }, { key: "restore" }] },
  { path: "/audit", tabs: [{ key: "audit" }, { key: "integrity" }] },
];
'''
_TABS_RENAMED = _TABS_HEALTHY.replace("TAB_GROUPS", "ADMIN_TAB_GROUPS")
_TABS_EMPTY_GROUP = '''
export const TAB_GROUPS = [
  { path: "/backup", tabs: [{ id: "backup" }, { id: "restore" }] },
];
'''
_DEFS_HEALTHY = '''
export const TAB_DEFS = [
  { key: "policy" }, { key: "os" }, { key: "integration" }, { key: "ai" },
];
'''
_DEFS_RENAMED = _DEFS_HEALTHY.replace("TAB_DEFS", "SETTINGS_TABS")


def _reader_case(fn, *, expect_raise: bool):
    try:
        value = fn()
    except SourceReadError:
        return expect_raise, "FATAL"
    return (not expect_raise), value


SELF_TEST_CASES = [
    # (이름, 호출, FATAL 이어야 하는가, 무엇을 지키는 사례인가)
    ("jsx/정상 소스는 통과한다",
     lambda: parse_jsx_routes(_JSX_HEALTHY, "<self-test>", floor=3), False,
     "리터럴 3개 — 하한을 넘으므로 읽히고, 위양성이면 안 된다"),
    ("jsx/계산된 path 는 리터럴이 아니지만 미분류도 아니다",
     lambda: parse_jsx_routes(_JSX_COMPUTED, "<self-test>", floor=1), False,
     "`path={g.path}` 는 TAB_GROUPS 리더 담당이다 — 미분류로 세면 정상 소스가 빨개진다"),
    ("jsx/path 없는 Route 는 FATAL",
     lambda: parse_jsx_routes(_JSX_BLIND, "<self-test>", floor=0), True,
     "리터럴도 계산도 index 도 아니면 이 리더가 못 읽은 것이다 — 예전엔 continue 였다"),
    ("jsx/Route 가 하나도 없으면 FATAL",
     lambda: parse_jsx_routes("<div/>", "<self-test>", floor=1), True,
     "R4 그 자체 — 빈 결과를 도는 검사는 0번 돌고 OK 를 찍는다"),
    ("jsx/하한 미달은 FATAL",
     lambda: parse_jsx_routes(_JSX_HEALTHY, "<self-test>", floor=99), True,
     "정규식이 «조금만» 어긋나는 부분 실명도 잡는다"),
    ("tab_groups/정상 소스는 통과한다",
     lambda: parse_tab_groups(_TABS_HEALTHY, floor=2), False,
     "그릇 2개 · 각 2탭"),
    ("tab_groups/상수 이름이 바뀌면 FATAL",
     lambda: parse_tab_groups(_TABS_RENAMED, floor=1), True,
     "앵커가 사라지면 예전엔 `[]` 였다 — 탭 Surface 가 통째로 검사 밖으로 나간다"),
    ("tab_groups/탭 키를 못 읽으면 FATAL",
     lambda: parse_tab_groups(_TABS_EMPTY_GROUP, floor=1), True,
     "그릇만 세고 본문을 0개로 세는 것이 가장 조용한 실명이다"),
    ("settings_tabs/정상 소스는 통과한다",
     lambda: parse_settings_tabs(_DEFS_HEALTHY, floor=4), False,
     "TAB_DEFS 4개"),
    ("settings_tabs/상수 이름이 바뀌면 FATAL",
     lambda: parse_settings_tabs(_DEFS_RENAMED, floor=1), True,
     "설정 탭 본문 1,216줄이 이 앵커 하나에 달려 있다"),
]


def _wiring_cases() -> list[str]:
    """리더의 FATAL 이 **Gate 실패로 실제로 옮겨지는가.**

    `parse_*` 가 올바르게 던지는 것과 Gate 가 그것 때문에 빨개지는 것은 다른 사실이다.
    W5 에서 아픈 것을 배운 자리가 정확히 여기다 — 「승격했다」고 적힌 검사가 한 번도 실제로
    걸린 적이 없었다. 배선을 직접 태워 본다.
    """
    bad: list[str] = []

    # ① 리더 하나가 눈을 감으면 → C0r 실패 + C1 미실행
    rep = Report()
    saved = globals()["read_tab_groups"]

    def _blind():
        raise SourceReadError("<self-test> 리더가 눈을 감았다")

    globals()["read_tab_groups"] = _blind
    try:
        got = c0_source_readers(rep)
    finally:
        globals()["read_tab_groups"] = saved
    if got is not None or rep.count("C0r") == 0:
        bad.append("배선/리더 FATAL 이 Gate 실패로 안 옮겨진다 "
                   "(반환 %s · C0r 실패 %d건) — 이게 곧 R4 다"
                   % ("dict" if got is not None else "None", rep.count("C0r")))

    # ② 정상 소스에서는 표본 수가 실제로 찍혀야 한다 — «아무것도 안 재고 통과» 의 반대편
    rep2 = Report()
    src = c0_source_readers(rep2)
    if src is None or rep2.count("C0r"):
        bad.append("배선/정상 소스인데 리더가 실패했다: %s"
                   % ("; ".join(m for _c, m in rep2.fails[:2]) or "(사유 없음)"))
    elif not src["user"] or not src["tab_groups"] or not src["settings_tabs"]:
        bad.append("배선/리더가 빈 결과를 돌려주는데 실패로 안 잡혔다 — 표본 0")
    return bad


def self_test() -> int:
    bad = []
    for name, fn, expect_raise, why in SELF_TEST_CASES:
        okay, got = _reader_case(fn, expect_raise=expect_raise)
        if not okay:
            bad.append("%s: 기대 %s / 실제 %s  (%s)"
                       % (name, "FATAL" if expect_raise else "통과",
                          "FATAL" if got == "FATAL" else "통과", why))
    bad += _wiring_cases()
    if bad:
        print("[FAIL] 리더 자기검증 실패 — 이 게이트의 초록은 아무것도 증명하지 못한다:")
        for line in bad:
            print("  - %s" % line)
        return EXIT_CANNOT_RUN
    print("[OK ] COVERAGE_READER_SELF_TEST_OK (사례 %d개 + 배선 2건, FATAL·위양성 양방향)"
          % len(SELF_TEST_CASES))
    return EXIT_OK


def main() -> int:
    ap = argparse.ArgumentParser(description="UI 리뉴얼 Control Plane Gate")
    ap.add_argument("--stage", choices=["plan", "wave", "complete"], default="plan")
    ap.add_argument("--wave", default="")
    ap.add_argument("--self-test", action="store_true",
                    help="리더 자기검증만 돌리고 끝낸다 (본 실행도 이것을 먼저 통과해야 한다)")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    # 실제 스캔 전에 자기검증을 먼저 돌린다. 실패하면 **아무것도 보고하지 않는다** —
    # 눈이 먼 검사기의 «위반 0» 은 위반이 없다는 뜻이 아니다.
    if self_test() != EXIT_OK:
        return EXIT_CANNOT_RUN

    print("== UI 리뉴얼 커버리지 게이트 (stage=%s) ==" % args.stage)
    if args.stage == "plan":
        return stage_plan()

    if args.stage == "wave":
        return stage_wave(args.wave)
    return stage_complete(args.wave)


if __name__ == "__main__":
    sys.exit(main())
