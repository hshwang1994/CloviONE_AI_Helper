# -*- coding: utf-8 -*-
"""화면이 목록 · 필터 · 발을 **정본 조합 부품 대신 낱개로 조립**하고 있지 않은가 (UI 3차 · 조합 계약 C-1 ~ C-5).

## 무엇을 막나

`check_kit_consumers.py` 는 화면이 MUI 원재료를 직접 쓰는지 본다. 그 검사를 통과해도 화면은 정본 **낱개
부품**을 제각각 조립할 수 있다 — 필터 면 밖에 칩 줄과 결과 줄을 두 줄로 세우고, 표를 여백 판으로 한 번 더
감싸고, 목록 발을 표 밖 가운데에 그리고, 열 `render` 안에 채움 단추를 직접 넣는다. 부품은 전부 정본인데
조합이 화면마다 다른 상태다. 이 검사는 그 조립 자국을 소스에서 잡는다.

    filter-parts        화면이 필터 바 낱개(`FilterSurface` · `FilterRow` · `ResultLine` · `FilterChips` …)를 import 한다
    fab-clearance       걷힌 마스코트 FAB 의 여백 토큰(`FAB_CLEARANCE`)을 쓴다
    list-footer         화면이 목록 발(`<ListFooter`)을 표 밖에 따로 그린다
    card-wrapped-table  `<DataTable` · `<GroupedTickets` 를 `<Card` · `<ListCard` 안에 둔다(`placement="card"` 가 아닌데)
    row-button          열 `render` 안에 `<Button` · `<IconButton` 을 `RowActions` 밖에서 직접 그린다
    table-tag           열 `render` 안에 면 있는 `<Tag` 를 그린다(표 안 정해진 축 값은 `DotLabel`)

## 예외와 대기 목록

- **예외**는 `docs/ui-renewal/COMPONENT_LEDGER.md` 「조합 예외」 표(`| 파일 | 조합 규칙 | 이유 | 대체 불가 근거 |`)에
  적힌 자리뿐이다. 적혀 있는데 그 파일에서 더는 안 걸리는 예외는 **죽은 예외**로 실패한다.
- **대기(PENDING)** 는 이 검사를 세운 시점에 이미 있던 위반이다. 작업 묶음마다 줄이고, 끝에는 빈 목록이어야
  한다. 목록에 있는데 더는 안 걸리는 항목(stale)도 실패한다 — 고쳤으면 목록에서도 지운다.

## 쓰는 법

    python scripts/check_composition.py            # 판정
    python scripts/check_composition.py --report   # 실패해도 0 으로 끝나고 전수 목록만 낸다
    python scripts/check_composition.py --selftest # 검사기 자기검증(Known Bad · Known Good 문자열)
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "frontend" / "src"
LEDGER = REPO_ROOT / "docs" / "ui-renewal" / "COMPONENT_LEDGER.md"

RULES = {
    "filter-parts": "필터 바 낱개 부품을 화면이 직접 조립한다 — `FilterBar` 조합 부품을 쓴다",
    "fab-clearance": "걷힌 FAB 의 여백 토큰을 쓴다",
    "list-footer": "목록 발을 표 밖에 따로 그린다 — `DataTable list` 가 판 안 발에 그린다",
    "card-wrapped-table": "목록 표를 여백 판으로 한 번 더 감싼다 — `DataTable placement`",
    "row-button": "열 render 안에 단추를 직접 그린다 — `RowActions`",
    "table-tag": "표 칸 안에 면 있는 Tag 를 그린다 — `DotLabel`",
}

FILTER_PARTS = {
    "FilterSurface", "ToolbarRow", "ToolbarEnd", "FilterRow", "FilterActions", "ResultLine",
    "FilterChips", "FilterConditionLine", "CHIP_ROW_CONTROL",
}
FILTERBAR_IMPORT = re.compile(r"""import\s*\{([^}]*)\}\s*from\s*["'][./]*(?:ui/)?FilterBar(?:\.jsx)?["']""", re.S)
TABLE_TAGS = {"DataTable", "GroupedTickets"}
WRAPPER_TAGS = {"Card", "ListCard"}
ROW_BUTTON_TAGS = {"Button", "IconButton"}

# 이 검사를 세운 시점(UI 3차 P0)의 위반. 묶음마다 줄이고 끝에는 비어야 한다.
PENDING: set[tuple[str, str]] = {
    # card-wrapped-table
    ("screens/Board.jsx", "card-wrapped-table"),
    ("screens/Dashboard.jsx", "card-wrapped-table"),
    ("screens/DataScreen.jsx", "card-wrapped-table"),
    ("screens/Home.jsx", "card-wrapped-table"),
    ("screens/Integrity.jsx", "card-wrapped-table"),
    ("screens/Knowledge.jsx", "card-wrapped-table"),
    ("screens/MailStatus.jsx", "card-wrapped-table"),
    ("screens/MyApprovals.jsx", "card-wrapped-table"),
    ("screens/MyStats.jsx", "card-wrapped-table"),
    ("screens/MyTickets.jsx", "card-wrapped-table"),
    ("screens/Offboarding.jsx", "card-wrapped-table"),
    ("screens/ProjectDocuments.jsx", "card-wrapped-table"),
    ("screens/ProjectTickets.jsx", "card-wrapped-table"),
    ("screens/ProjectWbs.jsx", "card-wrapped-table"),
    ("screens/Projects.jsx", "card-wrapped-table"),
    ("screens/StorageProviders.jsx", "card-wrapped-table"),
    ("screens/TeamTickets.jsx", "card-wrapped-table"),
    ("screens/Trash.jsx", "card-wrapped-table"),
    ("screens/Users.jsx", "card-wrapped-table"),
    ("screens/settings/SettingVersions.jsx", "card-wrapped-table"),
    ("screens/settings/SettingsMain.jsx", "card-wrapped-table"),
    # fab-clearance
    ("screens/MyTickets.jsx", "fab-clearance"),
    ("screens/Search.jsx", "fab-clearance"),
    ("screens/game-room/RoomSidebar.jsx", "fab-clearance"),
    ("ui/theme.js", "fab-clearance"),
    # filter-parts
    ("screens/Activity.jsx", "filter-parts"),
    ("screens/Board.jsx", "filter-parts"),
    ("screens/DataScreen.jsx", "filter-parts"),
    ("screens/DevReport.jsx", "filter-parts"),
    ("screens/Knowledge.jsx", "filter-parts"),
    ("screens/Offboarding.jsx", "filter-parts"),
    ("screens/OrgConsole.jsx", "filter-parts"),
    ("screens/ProjectDocuments.jsx", "filter-parts"),
    ("screens/ProjectTickets.jsx", "filter-parts"),
    ("screens/Projects.jsx", "filter-parts"),
    ("screens/SchedulerCalendar.jsx", "filter-parts"),
    ("screens/Search.jsx", "filter-parts"),
    ("screens/Sprint.jsx", "filter-parts"),
    ("screens/TicketFilterBar.jsx", "filter-parts"),
    ("screens/Users.jsx", "filter-parts"),
    ("screens/UsersBulk.jsx", "filter-parts"),
    ("screens/WorkBoard.jsx", "filter-parts"),
    ("screens/data-screen/SubListDrawer.jsx", "filter-parts"),
    ("screens/dev/KitGallery.jsx", "filter-parts"),
    ("screens/knowledge/KnowledgeFilterBar.jsx", "filter-parts"),
    ("screens/settings/SettingsMain.jsx", "filter-parts"),
    # list-footer
    ("screens/Activity.jsx", "list-footer"),
    ("screens/Board.jsx", "list-footer"),
    ("screens/DataScreen.jsx", "list-footer"),
    ("screens/Knowledge.jsx", "list-footer"),
    ("screens/MyApprovals.jsx", "list-footer"),
    ("screens/MyTickets.jsx", "list-footer"),
    ("screens/Offboarding.jsx", "list-footer"),
    ("screens/ProjectTickets.jsx", "list-footer"),
    ("screens/Projects.jsx", "list-footer"),
    ("screens/TeamTickets.jsx", "list-footer"),
    ("screens/Trash.jsx", "list-footer"),
    ("screens/Users.jsx", "list-footer"),
    ("screens/WorkBoard.jsx", "list-footer"),
    # row-button
    ("screens/MyApprovals.jsx", "row-button"),
    ("screens/MyTickets.jsx", "row-button"),
    ("screens/Trash.jsx", "row-button"),
    ("screens/data-screen/SubListDrawer.jsx", "row-button"),
    ("screens/dev/KitGallery.jsx", "row-button"),
    ("screens/settings/SettingVersions.jsx", "row-button"),
    ("screens/settings/SettingsMain.jsx", "row-button"),
    # table-tag
    ("screens/Board.jsx", "table-tag"),
    ("screens/ProjectDocuments.jsx", "table-tag"),
    ("screens/dev/KitGallery.jsx", "table-tag"),
    ("screens/knowledge/documentColumns.jsx", "table-tag"),
    ("screens/settings/SettingsMain.jsx", "table-tag"),
}

# 조합 규칙마다 보는 파일. 부품을 **구현하는** 곳(`ui/`)은 재료를 쓰는 자리라 화면 규칙을 받지 않는다.
SCREEN_ROOTS = ("screens/", "app/")


# ── JSX 를 아는 작은 훑개 ────────────────────────────────────────────────────
# 문자열 · 템플릿 · 주석 · 정규식 문자 · JSX 속성 식 · JSX 자식 글자를 구분해서, JSX 요소가 **열리는 자리**와
# 그때의 조상 요소 이름, 그리고 그 자리가 열 `render:` 식 안인지를 돌려준다. AST 가 아니다 — 이 저장소의
# 정적 검사 관례(줄 단위 정규식 · 의존성 없음)를 지키면서 중첩 판정만 할 수 있을 만큼이다.

_REGEX_PRE = set("(,=:[!&|?{};+-*%~^<>")
_IDENT = re.compile(r"[A-Za-z_$][\w$.]*")


def _skip_string(text: str, i: int) -> int:
    quote = text[i]
    i += 1
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == quote or (ch == "\n" and quote != "`"):
            return i + 1
        if quote == "`" and ch == "$" and text.startswith("${", i):
            i = _scan_js(text, i + 2, stop="}", events=None, renders=None, ancestors=[])
            continue
        i += 1
    return i


def _prev_significant(text: str, i: int) -> str:
    j = i - 1
    while j >= 0 and text[j] in " \t\r\n":
        j -= 1
    if j < 0:
        return ""
    if text[j].isalpha():
        k = j
        while k >= 0 and (text[k].isalnum() or text[k] in "_$"):
            k -= 1
        return text[k + 1:j + 1]
    return text[j]


def _jsx_can_start(text: str, i: int) -> bool:
    if i + 1 >= len(text) or not (text[i + 1].isalpha() or text[i + 1] == ">"):
        return False
    prev = _prev_significant(text, i)
    return prev == "" or prev in _REGEX_PRE or prev in ("return", "default", "case", "yield", "await") or prev == "?"


def _scan_tag(text: str, i: int, events, renders, ancestors) -> tuple[int, str | None]:
    """`<` 자리에서 여는 태그를 읽는다. (끝 다음 자리, 열린 요소 이름 또는 None(스스로 닫힘 · 조각))."""
    j = i + 1
    m = _IDENT.match(text, j)
    name = m.group(0) if m else ""
    j = m.end() if m else j
    start = i
    while j < len(text):
        ch = text[j]
        if ch in "\"'":
            j = _skip_string(text, j)
            continue
        if ch == "{":
            j = _scan_js(text, j + 1, stop="}", events=events, renders=renders, ancestors=ancestors + ([name] if name else []))
            continue
        if text.startswith("/>", j):
            if events is not None and name:
                events.append((start, name, list(ancestors), text[start:j + 2], _in_render(renders, start)))
            return j + 2, None
        if ch == ">":
            if events is not None and name:
                events.append((start, name, list(ancestors), text[start:j + 1], _in_render(renders, start)))
            return j + 1, (name or "")
        j += 1
    return j, None


def _in_render(renders, pos: int) -> bool:
    return bool(renders) and any(r[0] <= pos and (r[1] is None or pos < r[1]) for r in renders)


def _scan_children(text: str, i: int, name: str, events, renders, ancestors) -> int:
    while i < len(text):
        if text.startswith("</", i):
            end = text.find(">", i)
            return (end + 1) if end >= 0 else len(text)
        ch = text[i]
        if ch == "{":
            i = _scan_js(text, i + 1, stop="}", events=events, renders=renders, ancestors=ancestors)
            continue
        if ch == "<" and i + 1 < len(text) and (text[i + 1].isalpha() or text[i + 1] == ">"):
            i, opened = _scan_tag(text, i, events, renders, ancestors)
            if opened is not None:
                i = _scan_children(text, i, opened, events, renders, ancestors + ([opened] if opened else []))
            continue
        i += 1
    return i


def _scan_js(text: str, i: int, stop: str | None, events, renders, ancestors) -> int:
    """JS 식을 `stop` 닫는 괄호까지 읽는다(None 이면 파일 끝). 끝 다음 자리를 돌려준다."""
    closers: list[str] = []
    while i < len(text):
        ch = text[i]
        if text.startswith("//", i):
            nl = text.find("\n", i)
            i = len(text) if nl < 0 else nl + 1
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = len(text) if end < 0 else end + 2
            continue
        if ch in "\"'`":
            i = _skip_string(text, i)
            continue
        if ch == "/" and _prev_significant(text, i) in _REGEX_PRE | {"", "return"}:
            j = i + 1
            in_class = False
            while j < len(text) and text[j] != "\n":
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == "[":
                    in_class = True
                elif text[j] == "]":
                    in_class = False
                elif text[j] == "/" and not in_class:
                    break
                j += 1
            i = j + 1
            continue
        if ch == "<" and _jsx_can_start(text, i):
            i, opened = _scan_tag(text, i, events, renders, ancestors)
            if opened is not None:
                i = _scan_children(text, i, opened, events, renders, ancestors + ([opened] if opened else []))
            continue
        if renders is not None and text.startswith("render", i) and not (i and (text[i - 1].isalnum() or text[i - 1] in "_$.")):
            m = re.match(r"render\s*:", text[i:])
            if m:
                body = i + m.end()
                renders.append([body, None, len(closers), id(closers)])
                i = body
                continue
        if ch in "([{":
            closers.append({"(": ")", "[": "]", "{": "}"}[ch])
        elif ch in ")]}":
            if not closers:
                if stop is not None and ch == stop:
                    _close_renders(renders, i, -1, id(closers))
                    return i + 1
            else:
                closers.pop()
                _close_renders(renders, i, len(closers), id(closers))
        elif ch == "," and renders:
            for r in renders:
                if r[1] is None and r[3] == id(closers) and r[2] == len(closers) and r[0] < i:
                    r[1] = i
        i += 1
    _close_renders(renders, i, -1, id(closers))
    return i


def _close_renders(renders, pos: int, depth: int, level: int) -> None:
    """이 훑기 단계(`level`)에서 연 `render:` 식만 닫는다 — 안쪽 속성 식이 끝났다고 바깥 식을 닫지 않는다."""
    if not renders:
        return
    for r in renders:
        if r[1] is None and r[3] == level and depth < r[2]:
            r[1] = pos


def jsx_events(text: str):
    events: list = []
    renders: list = []
    _scan_js(text, 0, stop=None, events=events, renders=renders, ancestors=[])
    return events


# ── 판정 ────────────────────────────────────────────────────────────────────

def read_exceptions(ledger: Path) -> set[tuple[str, str]]:
    """대장 「조합 예외」 표: `| 파일 | 조합 규칙 | 이유 | 대체 불가 근거 |`."""
    out: set[tuple[str, str]] = set()
    if not ledger.is_file():
        return out
    in_table = False
    for line in ledger.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s.startswith("|"):
            in_table = False
            continue
        cells = [c.strip().strip("`") for c in s.strip("|").split("|")]
        if len(cells) >= 2 and cells[0] == "파일" and cells[1] == "조합 규칙":
            in_table = True
            continue
        if not in_table or set("".join(cells)) <= set("-: "):
            continue
        path = cells[0].replace("frontend/src/", "")
        for rule in re.split(r"[,·/]", cells[1]):
            rule = rule.strip().strip("`")
            if rule:
                out.add((path, rule))
    return out


def scan_file(rel: str, text: str) -> list[tuple[str, int, str]]:
    """(규칙, 줄, 설명) 목록."""
    hits: list[tuple[str, int, str]] = []
    line_of = lambda pos: text.count("\n", 0, pos) + 1  # noqa: E731
    if "FAB_CLEARANCE" in text:
        pos = text.find("FAB_CLEARANCE")
        hits.append(("fab-clearance", line_of(pos), "FAB_CLEARANCE"))
    if not rel.startswith(SCREEN_ROOTS):
        return hits
    for m in FILTERBAR_IMPORT.finditer(text):
        names = {n.strip().split(" as ")[0].strip() for n in m.group(1).split(",") if n.strip()}
        parts = sorted(names & FILTER_PARTS)
        if parts:
            hits.append(("filter-parts", line_of(m.start()), ", ".join(parts)))
    if "<" not in text:
        return hits
    for pos, name, ancestors, tag, in_render in jsx_events(text):
        if name == "ListFooter":
            hits.append(("list-footer", line_of(pos), "<ListFooter>"))
        if name in TABLE_TAGS:
            wrapped = [a for a in ancestors if a in WRAPPER_TAGS]
            placement = re.search(r"""\bplacement\s*=\s*["'{]\s*["']?(\w+)""", tag)
            if wrapped and not (placement and placement.group(1) in ("card", "plain")):
                hits.append(("card-wrapped-table", line_of(pos), f"<{name}> in <{wrapped[-1]}>"))
        if in_render and name in ROW_BUTTON_TAGS and "RowActions" not in ancestors:
            hits.append(("row-button", line_of(pos), f"<{name}> in render"))
        if in_render and name == "Tag":
            hits.append(("table-tag", line_of(pos), "<Tag> in render"))
    return hits


def scan(src: Path, ledger: Path, pending: set[tuple[str, str]]):
    exceptions = read_exceptions(ledger)
    found: dict[tuple[str, str], list[str]] = {}
    for path in sorted(src.rglob("*")):
        if path.suffix not in (".js", ".jsx") or ".test." in path.name:
            continue
        rel = path.relative_to(src).as_posix()
        text = path.read_text(encoding="utf-8")
        for rule, line, what in scan_file(rel, text):
            found.setdefault((rel, rule), []).append(f"{rel}:{line} {what}")
    new = {k: v for k, v in found.items() if k not in pending and k not in exceptions}
    stale = sorted(k for k in pending if k not in found)
    dead = sorted(k for k in exceptions if k not in found)
    waiting = {k: v for k, v in found.items() if k in pending}
    return new, waiting, stale, dead


def selftest() -> int:
    bad_screen = (
        'import { FilterSurface, FilterRow, ResultLine, FilterToggle } from "../ui/FilterBar.jsx";\n'
        'import { FAB_CLEARANCE } from "../ui/theme.js";\n'
        "const cols = [\n"
        '  { key: "a", label: "제목", render: (r) => <Tag label={r.kind} /> },\n'
        '  { key: "b", label: "작업", render: (r) => (<Box sx={{ display: "flex" }}>'
        '<Button variant="primary" onClick={() => go(r)}>배정</Button></Box>) },\n'
        "];\n"
        "export function Bad() {\n"
        "  return (<>\n"
        "    <ListCard sx={{ p: 0 }}><DataTable columns={cols} rows={[]} /></ListCard>\n"
        "    <ListFooter total={1} loaded={1} />\n"
        "  </>);\n"
        "}\n"
    )
    good_screen = (
        'import { FilterBar, FilterToggle } from "../ui/FilterBar.jsx";\n'
        "const cols = [\n"
        '  { key: "a", label: "제목", render: (r) => <DotLabel label={r.kind} /> },\n'
        '  { key: "b", label: "작업", render: (r) => (<RowActions items={[{ label: "배정", onClick: () => go(r) }]} />) },\n'
        '  { key: "c", label: "동작", render: (r) => <RowActions><Button size="sm">보기</Button></RowActions> },\n'
        "];\n"
        "const msg = 'a <b> c';\n"
        "const re = /<Button/;\n"
        "export function Good() {\n"
        '  return (<Card><DataTable placement="card" columns={cols} rows={[]} /></Card>);\n'
        "}\n"
        "export const X = () => <DataTable placement=\"surface\" columns={cols} rows={[]} list={{}} />;\n"
    )
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src" / "screens"
        src.mkdir(parents=True)
        (src / "Bad.jsx").write_text(bad_screen, encoding="utf-8")
        (src / "Good.jsx").write_text(good_screen, encoding="utf-8")
        (src / "Gone.jsx").write_text("export const Gone = 1;\n", encoding="utf-8")
        ledger = root / "ledger.md"
        ledger.write_text(
            "| 파일 | 조합 규칙 | 이유 | 대체 불가 근거 |\n|---|---|---|---|\n"
            "| `screens/Gone.jsx` | `list-footer` | 사라진 자리 | 없음 |\n", encoding="utf-8")
        new, _waiting, stale, dead = scan(root / "src", ledger, {("screens/Nowhere.jsx", "row-button")})
    bad_rules = {rule for (rel, rule) in new if rel == "screens/Bad.jsx"}
    for rule in RULES:
        if rule not in bad_rules:
            problems.append(f"Known Bad 를 못 잡음: {rule}")
    good_hits = [v for (rel, _rule), v in new.items() if rel == "screens/Good.jsx"]
    if good_hits:
        problems.append(f"Known Good 을 잘못 잡음: {good_hits}")
    if ("screens/Nowhere.jsx", "row-button") not in stale:
        problems.append("stale 대기 항목을 못 잡음")
    if ("screens/Gone.jsx", "list-footer") not in dead:
        problems.append("죽은 예외를 못 잡음")
    if problems:
        for p in problems:
            print("[SELFTEST] " + p)
        print("COMPOSITION_SELFTEST_FAILED")
        return 1
    print(f"COMPOSITION_SELFTEST_OK (Known Bad {len(RULES)}규칙 전부 잡음 · Known Good 오탐 0 · stale · 죽은 예외)")
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="목록 · 필터 · 발 조합 검사")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    new, waiting, stale, dead = scan(SRC, LEDGER, PENDING)
    if args.report:
        allhits = {**waiting, **new}
        for (rel, rule), lines in sorted(allhits.items()):
            print(f"[{rule}] {rel} ({len(lines)})  {lines[0]}")
        print(f"COMPOSITION_REPORT (위반 파일·규칙 {len(allhits)} · 대기 {len(waiting)} · stale {len(stale)} · 죽은 예외 {len(dead)})")
        return 0
    for title, rows in (
        ("새 위반(대장 예외 · 대기 목록 밖)", [f"[{r}] {lines[0]}" for (_rel, r), lines in sorted(new.items())]),
        ("stale 대기 항목(더는 안 걸린다 — PENDING 에서 지운다)", [f"[{r}] {rel}" for rel, r in stale]),
        ("죽은 예외(대장에 있는데 안 걸린다)", [f"[{r}] {rel}" for rel, r in dead]),
    ):
        if rows:
            print(f"[FAIL] {title}: {len(rows)}건")
            for row in rows:
                print("   ", row)
    if new or stale or dead:
        print(f"COMPOSITION_FAILED (새 위반 {len(new)} · stale {len(stale)} · 죽은 예외 {len(dead)} · 대기 {len(waiting)})")
        return 1
    print(f"COMPOSITION_OK (대기 {len(waiting)} · 새 위반 0 · stale 0 · 죽은 예외 0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
