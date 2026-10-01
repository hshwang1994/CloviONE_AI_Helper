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
    ghost-slot          글자 단추(`variant="ghost"`)를 메시지 박스(`<Callout`) · 발(`<ActionFooter` · `<ModalFooter` · 모달
                        `footer=`) · 판 머리 동작(`<SectionTitle` · `<Section` 의 `action=`) · 페이지 머리 동작(`actions=`)에 둔다
                        — 그 자리는 30 · 34 보조다. 글자 단추는 목록 안 부수 동작(조건 지우기 · 더 보기 · 댓글 줄 동작)의 자리다
    primary-last        페이지 머리 동작(`<PageHeader actions=…>`)에서 채움 단추(`variant="primary"`) 뒤에 단추가 또 선다 — 순서는
                        보조 → 더 보기 → 주 동작이고 채움은 오른쪽 끝이다(D-501). 한 머리 안의 단추끼리만 비교한다
    page-max-width      화면이 판 폭 상한(`READ_COLUMN` 이나 `min(100%, Nrem)` 모양)을 건다 — 페이지는 폭을 묶지 않고 긴 줄은
                        카드 격자와 카드 안 글 폭(`PROSE_MAX_WIDTH`)으로 접는다(계획 2.1, D-520). 글 폭 상한은 잡지 않는다
    tab-count-chip      `<TabShell tabs=…>` 의 탭 이름에 수를 이어 붙인다(`` `사람 (${n})` `` · `"사람 " + n`) — 수는 탭의
                        `count` 가 이름 옆 칩으로 그린다(계획 3.2 · 3.18)
    callout-margin      메시지 박스(`<Callout sx={{ mt|mb|my|m… }}>`)에 위아래 여백을 준다 — 덩어리 사이 간격은 담는 쪽
                        (`.c-screen` · `FlowStack` · `Card stack` · 탭 판)이 준다(D-528)
    primitive-geometry-override
                        공통 부품(`Field` · `FieldRow` · `FormSection` · `HeadRow` · `SectionHeader` · `Section` · `Card` ·
                        `FilterBar` · `Callout` · `DataTable` · `ActionFooter` · `PageHeader` …)의 여백 · 폭 · 높이를 `sx` 의
                        `m*` · `p*` · `top` · `width` · `minWidth` · `height` … 로 덮는다 — 부품의 속성(`spacing` · `flush` ·
                        `padding` · 크기 토큰 · 열 속성)으로 말한다(D-526 ~ D-528). `minWidth: 0` · `minHeight: 0` 은 크기가
                        아니라 격자 · flex 안에서 줄어들어도 된다는 허락이라 잡지 않는다. 옮길 수 없는 자리는 태그 안이나
                        바로 위 두 줄에 `clovi-allow-geometry: 까닭` 을 단다. MUI 에서 가져온 같은 이름(`Toolbar`)은 부품이 아니다

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
    "ghost-slot": "메시지 박스 · 발 · 판 머리 · 페이지 머리 동작에 글자 단추를 둔다 — 30 · 34 보조",
    "primary-last": "페이지 머리 동작의 채움 단추 뒤에 단추가 또 선다 — 채움은 오른쪽 끝이다(D-501)",
    "page-max-width": "화면이 판 폭 상한을 건다 — 페이지는 폭을 묶지 않는다(계획 2.1)",
    "tab-count-chip": "탭 이름에 수를 이어 붙인다 — 탭의 `count` 가 칩으로 그린다(계획 3.18)",
    "callout-margin": "메시지 박스에 위아래 여백을 준다 — 간격은 담는 쪽이 준다(D-528)",
    "primitive-geometry-override": "공통 부품의 여백 · 폭 · 높이를 sx 로 덮는다 — 부품의 속성으로 말한다(D-526 ~ D-528)",
}

# 화면이 sx 로 덮으면 안 되는 공통 부품. 부품을 **구현하는** 곳(`ui/`)은 재료를 쓰는 자리라 보지 않는다.
GEOMETRY_PRIMITIVES = {
    "Field", "FieldRow", "FormSection", "FormField", "FormFieldCell", "HeadRow", "FlowStack", "SectionHeader",
    "SectionTitle", "Section", "SubGroup", "Card", "ListCard", "FilterBar", "Callout", "DataTable", "ActionFooter",
    "PageHeader", "Toolbar", "ToolbarRow",
}
# 메시지 박스의 위아래 여백(`callout-margin`). 같은 키를 `primitive-geometry-override` 가 두 번 세지 않는다.
CALLOUT_MARGIN_KEYS = {
    "m", "mt", "mb", "my", "margin", "marginTop", "marginBottom", "marginBlock", "marginBlockStart", "marginBlockEnd",
}
GEOMETRY_KEY = re.compile(
    r"(?:m|mt|mb|my|mx|ml|mr|p|pt|pb|py|px|pl|pr|top|width|minWidth|maxWidth|height|minHeight|maxHeight"
    r"|margin[A-Za-z]*|padding[A-Za-z]*)$")
# 줄어들어도 된다는 허락(0)이지 크기가 아니다. `{ md: 0 }` 처럼 모든 갈래가 0 인 반응형 값도 같다.
SHRINK_KEYS = {"minWidth", "minHeight"}
ALLOW_GEOMETRY = re.compile(r"clovi-allow-geometry:\s*[^\s*/}]")  # 까닭 없는 표식은 표식이 아니다
MUI_IMPORT = re.compile(r"""import\s*(?:\{([^}]*)\}|([A-Za-z_$][\w$]*))\s*from\s*["']@mui/[^"']+["']""", re.S)

# 판 폭 상한의 모양. `READ_COLUMN` 은 걷었고(D-520), 같은 값을 글자로 다시 적어도 잡는다. 글 폭(`PROSE_MAX_WIDTH`,
# `60ch`)과 대화상자 폭은 판 폭이 아니라 잡지 않는다.
PAGE_WIDTH_CAP = re.compile(
    r"""maxWidth\s*:\s*(?:READ_COLUMN\b|["'`]min\(\s*100%\s*,\s*\d+(?:\.\d+)?rem\s*\)["'`])""")
TABSHELL_OPEN = re.compile(r"<TabShell\b")
# 탭 이름에 수를 잇는 모양 - 템플릿 안의 `${…}` 이거나 `+` 로 잇는 식.
TAB_LABEL_WITH_NUMBER = re.compile(r"""\blabel\s*:\s*(?:`[^`]*\$\{[^`]*`|[^,}\n]*\+)""")

FILTER_PARTS = {
    "FilterSurface", "ToolbarRow", "ToolbarEnd", "FilterRow", "FilterActions", "ResultLine",
    "FilterChips", "FilterConditionLine", "CHIP_ROW_CONTROL",
}
FILTERBAR_IMPORT = re.compile(r"""import\s*\{([^}]*)\}\s*from\s*["'][./]*(?:ui/)?FilterBar(?:\.jsx)?["']""", re.S)
TABLE_TAGS = {"DataTable", "GroupedTickets"}
WRAPPER_TAGS = {"Card", "ListCard"}
ROW_BUTTON_TAGS = {"Button", "IconButton"}
# 글자 단추가 서면 안 되는 자리(핸드오프 RULES §1 · §3 · §8 · 조합 계약 C-4). 요소 이름은 그 요소의 속성 · 자식 전체,
# `이름@속성` 은 그 속성 식 안만이다 — `<Section>` 의 자식(첨부 줄 「떼기」 같은 목록 안 부수 동작)은 자리가 아니다.
GHOST_BUTTON_TAGS = {"Button", "KitButton"}
GHOST_VARIANT = re.compile(r"""\bvariant\s*=\s*\{?\s*["']ghost["']""")
PRIMARY_VARIANT = re.compile(r"""\bvariant\s*=\s*\{?\s*["']primary["']""")
# 채움 단추가 오른쪽 끝이어야 하는 자리. 속성 식 하나가 한 묶음이다 — 한 파일의 두 머리를 섞지 않게 식이 열린 자리를
# 이름 뒤에 붙인다(`PageHeader@actions#123`).
PRIMARY_LAST_SLOT = "PageHeader@actions#"
GHOST_SLOTS = {
    "Callout": "메시지 박스",
    "ActionFooter": "발",
    "ModalFooter": "모달 발",
    "Modal@footer": "모달 발",
    "FormModal@footer": "모달 발",
    "SectionTitle@action": "판 머리 동작",
    "Section@action": "판 머리 동작",
    "PageHeader@actions": "페이지 머리 동작",
}
_ATTR_BEFORE_BRACE = re.compile(r"([A-Za-z_$][\w$-]*)\s*=\s*$")

# 이 검사를 세운 시점(UI 3차 P0)의 위반. 묶음마다 줄이고 끝에는 비어야 한다.
PENDING: set[tuple[str, str]] = set()
# P4 에서 마지막 대기 넷(fab-clearance — 새 티켓 · 통합 검색 · 놀이방 사이드바 · 토큰)을 걷었다. 여기는 빈 채로 둔다.

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
    """`i` 앞의 뜻 있는 낱말 · 글자. 사이의 빈칸과 주석은 건너뛴다 — `return ( /* 설명 */ <Callout …` 의 요소를
    주석 끝 글자(`/`) 뒤로 읽어 JSX 가 아니라고 놓치던 자리다(UI 3차 P7 — 알림함 · 상태 알림의 메시지 박스)."""
    j = i - 1
    while j >= 0:
        while j >= 0 and text[j] in " \t\r\n":
            j -= 1
        if j >= 1 and text[j] == "/" and text[j - 1] == "*":
            open_at = text.rfind("/*", 0, j - 1)
            if open_at < 0:
                break
            j = open_at - 1
            continue
        line_start = text.rfind("\n", 0, j + 1) + 1
        if text[line_start:j + 1].lstrip().startswith("//"):
            j = line_start - 1
            continue
        break
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
            # 속성 식이면 요소 이름 뒤에 `이름@속성` 을 하나 더 얹는다 — 기존 규칙은 요소 이름만 보므로 판정이 같다.
            attr = _ATTR_BEFORE_BRACE.search(text, start, j)
            # 셋째 이름(`이름@속성#자리`)은 **그 식 하나**를 가리킨다 — 같은 파일의 머리 둘을 한 묶음으로 세지 않게.
            scope = ([name] + ([f"{name}@{attr.group(1)}", f"{name}@{attr.group(1)}#{j}"] if attr else [])) if name else []
            j = _scan_js(text, j + 1, stop="}", events=events, renders=renders, ancestors=ancestors + scope)
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


def _opened_scope(opened: str, at: int) -> list[str]:
    """자식을 읽을 때 조상에 얹는 이름. 요소 이름(예전 그대로) 뒤에 **그 요소 하나**를 가리키는 표식(`이름#자리`,
    조각은 `<>#자리`)을 하나 더 얹는다 — 기존 규칙은 이름만 보므로 판정이 같다. `primary-last` 가 같은 머리 안의
    두 갈래(`cond ? <>…</> : <>…</>`)를 가르는 데 쓴다."""
    return ([opened] if opened else []) + [f"{opened or '<>'}#{at}"]


def _in_render(renders, pos: int) -> bool:
    return bool(renders) and any(r[0] <= pos and (r[1] is None or pos < r[1]) for r in renders)


def _scan_children(text: str, i: int, name: str, events, renders, ancestors) -> int:
    while i < len(text):
        if text.startswith("</", i):
            end = text.find(">", i)
            return (end + 1) if end >= 0 else len(text)
        ch = text[i]
        if ch == "{":
            # 자식 자리의 식에 든 요소는 조건부이거나 여럿이다 — `{}#자리` 표식이 그 사실을 조상에 남긴다(`primary-last`).
            i = _scan_js(text, i + 1, stop="}", events=events, renders=renders, ancestors=ancestors + [f"{{}}#{i}"])
            continue
        if ch == "<" and i + 1 < len(text) and (text[i + 1].isalpha() or text[i + 1] == ">"):
            at = i
            i, opened = _scan_tag(text, i, events, renders, ancestors)
            if opened is not None:
                i = _scan_children(text, i, opened, events, renders, ancestors + _opened_scope(opened, at))
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
            at = i
            i, opened = _scan_tag(text, i, events, renders, ancestors)
            if opened is not None:
                i = _scan_children(text, i, opened, events, renders, ancestors + _opened_scope(opened, at))
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
    for m in PAGE_WIDTH_CAP.finditer(text):
        hits.append(("page-max-width", line_of(m.start()), m.group(0)))
    hits.extend(_tab_label_hits(text, line_of))
    for m in FILTERBAR_IMPORT.finditer(text):
        names = {n.strip().split(" as ")[0].strip() for n in m.group(1).split(",") if n.strip()}
        parts = sorted(names & FILTER_PARTS)
        if parts:
            hits.append(("filter-parts", line_of(m.start()), ", ".join(parts)))
    if "<" not in text:
        return hits
    header_groups: dict[str, list[tuple[int, str, bool, bool]]] = {}
    mui_names = {n.strip().split(" as ")[-1].strip()
                 for m in MUI_IMPORT.finditer(text) for n in (m.group(1) or m.group(2)).split(",")}
    for pos, name, ancestors, tag, in_render in jsx_events(text):
        if name in GEOMETRY_PRIMITIVES and name not in mui_names:
            for rule, what in _geometry_hits(name, tag, text, pos):
                hits.append((rule, line_of(pos), what))
        if name in GHOST_BUTTON_TAGS:
            group = _header_group(ancestors)
            if group:
                key, conditional = group
                header_groups.setdefault(key, []).append(
                    (pos, name, bool(PRIMARY_VARIANT.search(_own_attrs(tag))), conditional))
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
        if name in GHOST_BUTTON_TAGS and GHOST_VARIANT.search(_own_attrs(tag)):
            slot = next((GHOST_SLOTS[a] for a in reversed(ancestors) if a in GHOST_SLOTS), None)
            if slot:
                hits.append(("ghost-slot", line_of(pos), f"<{name} variant=ghost> in {slot}"))
    hits.extend(_primary_last_hits(header_groups.values(), line_of, ""))
    return hits


def _sx_object(tag: str) -> str | None:
    """여는 태그의 **자기** `sx={{ … }}` 객체 글(바깥 중괄호 포함). 함수 · 변수 · 배열이면 None — 소스만으로 키를 모른다."""
    depth, i = 0, 0
    while i < len(tag):
        ch = tag[i]
        if ch in "\"'`":
            i = _skip_string(tag, i)
            continue
        if ch == "{":
            if depth == 0:
                attr = _ATTR_BEFORE_BRACE.search(tag, 0, i)
                if attr and attr.group(1) == "sx":
                    inner = _balanced(tag, i, "{", "}")[1:-1].strip()
                    return inner if inner.startswith("{") and inner.endswith("}") else None
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        i += 1
    return None


def _top_props(obj: str) -> list[tuple[str, str]]:
    """`{ a: 1, b: { md: 0 }, ...X }` 의 최상위 (키, 값). 펼침(`...`)과 선택자 키(`"& .x"`)는 뺀다."""
    body = obj.strip()[1:-1]
    parts, depth, cur, i = [], 0, "", 0
    while i < len(body):
        ch = body[i]
        if ch in "\"'`":
            j = _skip_string(body, i)
            cur += body[i:j]
            i = j
            continue
        if body.startswith("/*", i):
            end = body.find("*/", i + 2)
            i = len(body) if end < 0 else end + 2
            continue
        if ch in "({[":
            depth += 1
        elif ch in ")}]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
        i += 1
    parts.append(cur)
    out = []
    for part in parts:
        m = re.match(r"""\s*["']?([A-Za-z]+)["']?\s*:\s*(.*)$""", part, re.S)
        if m:
            out.append((m.group(1), m.group(2).strip()))
    return out


def _is_shrink_permission(key: str, value: str) -> bool:
    if key not in SHRINK_KEYS:
        return False
    if value == "0":
        return True
    values = re.findall(r":\s*([^,}]+)", value) if value.startswith("{") else []
    return bool(values) and all(v.strip() == "0" for v in values)


def _geometry_hits(name: str, tag: str, text: str, pos: int) -> list[tuple[str, str]]:
    """공통 부품 여는 태그의 sx 가 여백 · 폭 · 높이를 덮는가. 까닭 표식이 태그 안이나 바로 위 두 줄에 있으면 넘긴다."""
    obj = _sx_object(tag)
    if obj is None:
        return []
    line_start = text.rfind("\n", 0, pos) + 1
    prev1 = text.rfind("\n", 0, max(0, line_start - 1)) + 1
    prev2 = text.rfind("\n", 0, max(0, prev1 - 1)) + 1
    if ALLOW_GEOMETRY.search(tag) or ALLOW_GEOMETRY.search(text[prev2:pos]):
        return []
    out = []
    for key, value in _top_props(obj):
        if not GEOMETRY_KEY.match(key) or _is_shrink_permission(key, value):
            continue
        if name == "Callout" and key in CALLOUT_MARGIN_KEYS:
            out.append(("callout-margin", f"<Callout sx {key}: {value[:24]}>"))
        else:
            out.append(("primitive-geometry-override", f"<{name} sx {key}: {value[:24]}>"))
    return out


def _balanced(text: str, start: int, opening: str, closing: str) -> str:
    """`start` 의 여는 괄호부터 짝이 맞는 닫는 괄호까지의 글. 문자열 속 괄호는 세지 않는다(`_skip_string`)."""
    depth, i = 0, start
    while i < len(text):
        ch = text[i]
        if ch in "\"'`":
            i = _skip_string(text, i)
            continue
        if ch == opening:
            depth += 1
        elif ch == closing:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    return text[start:]


def _tab_label_hits(text: str, line_of) -> list[tuple[str, int, str]]:
    """`<TabShell tabs=…>` 의 탭 이름에 수를 이어 붙였는가. 탭 목록이 같은 파일의 상수면 그 정의를 본다."""
    hits = []
    for m in TABSHELL_OPEN.finditer(text):
        attr = re.compile(r"\btabs\s*=\s*\{").search(text, m.end())
        # 이 요소의 속성이어야 한다 - 다음 `<TabShell` 보다 앞이고 멀지 않은 자리만 본다.
        following = TABSHELL_OPEN.search(text, m.end())
        if attr is None or attr.start() - m.end() > 3000 or (following and attr.start() > following.start()):
            continue
        expr = _balanced(text, attr.end() - 1, "{", "}")[1:-1].strip()
        body = expr
        name = re.fullmatch(r"[A-Za-z_$][\w$]*", expr)
        if name:
            decl = re.compile(r"\bconst\s+" + re.escape(expr) + r"\s*=\s*\[").search(text)
            if decl is None:
                continue
            body = _balanced(text, decl.end() - 1, "[", "]")
        for label in TAB_LABEL_WITH_NUMBER.finditer(body):
            hits.append(("tab-count-chip", line_of(m.start()), label.group(0)[:40]))
    return hits


def _header_group(ancestors) -> tuple[str, bool] | None:
    """페이지 머리 동작 안 단추의 (묶음 열쇠, 조건부인가). 머리 밖이면 None.

    열쇠는 그 머리 식 하나 + 식 안 **바깥** 조각 · 요소다 — 삼항의 두 갈래(`cond ? <>…</> : <>…</>`)가 각자 한 묶음이다.
    조건부는 그 바깥 그릇 아래에 자식 식(`{cond ? … : null}`)을 지나 선 단추다."""
    idx = max((i for i, a in enumerate(ancestors) if a.startswith(PRIMARY_LAST_SLOT)), default=-1)
    if idx < 0:
        return None
    rest = ancestors[idx + 1:]
    anchor = next((j for j, a in enumerate(rest) if "#" in a and not a.startswith("{}#")), None)
    key = ancestors[idx] + "|" + (rest[anchor] if anchor is not None else "")
    after = rest[anchor + 1:] if anchor is not None else rest
    return key, any(a.startswith("{}#") for a in after)


def _primary_last_hits(groups, line_of, where: str) -> list[tuple[str, int, str]]:
    """채움 뒤에 단추가 서는가. 단추마다 (자리, 이름, 채움인가, 조건부인가)다.

    조건부 채움 뒤의 조건부 단추는 **판정하지 않는다** — `state === "planned"` 의 「회차 열기」와 `state === "active"` 의
    「회차 닫기」처럼 함께 서지 않는 갈래일 수 있고, 소스만으로는 그것을 가를 수 없다. 채움이 늘 서거나(조건 없음) 뒤의
    단추가 늘 서면 둘이 함께 서는 날이 반드시 있으므로 잡는다(진단 「진단 수집」 뒤의 「복사」 · 「JSON 다운로드」)."""
    out = []
    for buttons in groups:
        for i, (pos, name, primary, conditional) in enumerate(buttons):
            if not primary:
                continue
            after = buttons[i + 1:]
            clash = [b for b in after if not (conditional and b[3])]
            if clash:
                out.append(("primary-last", line_of(pos), f"<{name} variant=primary>{where} 뒤에 단추 {len(clash)}개"))
    return out


# ── 머리 동작을 옆 부품으로 뺀 자리 ─────────────────────────────────────────────
# 진단의 머리 동작은 `DiagnosticActions` 가 그린다 — `<PageHeader actions={<DiagnosticActions …/>}>`. 단추가 머리 식 안에
# 글자로 없으므로 파일 하나만 보면 안 보인다. 머리 식 안에 선 부품 이름을 모든 화면 파일에서 모은 뒤, 그 이름을 정의한
# 파일에서 그 부품 본문의 단추를 한 묶음으로 본다(부품 하나 = 머리 하나).
_COMPONENT_DEF = r"(?:^|\n)(?:export\s+)?(?:default\s+)?(?:function\s+{name}\s*\(|const\s+{name}\s*=)"
_COMPONENT_END = re.compile(r"\n(?:\}|\);|\};)[ \t]*(?:\n|$)")


def header_component_names(text: str) -> set[str]:
    """페이지 머리 식 안에 선 부품 이름(단추 · 메뉴 말고, 대문자로 시작하는 것)."""
    names = set()
    for _pos, name, ancestors, _tag, _in_render in jsx_events(text):
        if name and name[0].isupper() and "." not in name and name not in GHOST_BUTTON_TAGS and _header_group(ancestors):
            names.add(name)
    return names


def header_component_hits(text: str, names: set[str]) -> list[tuple[str, int, str]]:
    """이 파일이 정의한 머리 동작 부품의 본문에서 채움이 끝이 아닌가."""
    spans = []
    for name in sorted(names):
        m = re.search(_COMPONENT_DEF.format(name=re.escape(name)), text)
        if not m:
            continue
        end = _COMPONENT_END.search(text, m.end())
        spans.append((name, m.start(), end.end() if end else len(text)))
    if not spans:
        return []
    line_of = lambda pos: text.count("\n", 0, pos) + 1  # noqa: E731
    events = jsx_events(text)
    hits = []
    for name, start, end in spans:
        buttons = [(pos, n, bool(PRIMARY_VARIANT.search(_own_attrs(tag))), any(a.startswith("{}#") for a in anc))
                   for pos, n, anc, tag, _r in events if start <= pos < end and n in GHOST_BUTTON_TAGS]
        hits.extend(_primary_last_hits([buttons], line_of, f" in {name}(머리 동작 부품)"))
    return hits


_BRACED_LITERAL = re.compile(r"""=\s*\{\s*(["'][^"'{}]*["'])\s*\}""")


def _own_attrs(tag: str) -> str:
    """여는 태그에서 **자기 속성**만 남긴다 — 속성 식 안에 든 다른 요소의 `variant` 를 제 것으로 읽지 않게 `{…}` 를 비운다.
    글자 하나만 든 식(`variant={"ghost"}`)은 먼저 따옴표 값으로 푼다."""
    out, depth = [], 0
    for ch in _BRACED_LITERAL.sub(r"=\1", tag):
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth = max(0, depth - 1)
            continue
        if depth == 0:
            out.append(ch)
    return "".join(out)


def scan(src: Path, ledger: Path, pending: set[tuple[str, str]]):
    exceptions = read_exceptions(ledger)
    found: dict[tuple[str, str], list[str]] = {}
    texts: dict[str, str] = {}
    for path in sorted(src.rglob("*")):
        if path.suffix not in (".js", ".jsx") or ".test." in path.name:
            continue
        rel = path.relative_to(src).as_posix()
        text = path.read_text(encoding="utf-8")
        texts[rel] = text
        for rule, line, what in scan_file(rel, text):
            found.setdefault((rel, rule), []).append(f"{rel}:{line} {what}")
    screen_texts = {rel: text for rel, text in texts.items() if rel.startswith(SCREEN_ROOTS) and "<" in text}
    header_parts = set()
    for text in screen_texts.values():
        header_parts |= header_component_names(text)
    for rel, text in screen_texts.items():
        for rule, line, what in header_component_hits(text, header_parts):
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
        '    <Callout tone="warn" action={<Button size="sm" variant="ghost" onClick={retry}>다시 시도</Button>}>안내</Callout>\n'
        '    <PageHeader title="진단" actions={<><Button variant="primary" onClick={run}>진단 수집</Button><Button onClick={copy}>복사</Button></>} />\n'
        '    <Box sx={{ display: "grid", maxWidth: READ_COLUMN }}>판</Box>\n'
        '    <TabShell tabs={[{ key: "p", label: `사람 (${people})` }]} />\n'
        '    <Callout tone="info" sx={{ mt: 2 }}>위 여백</Callout>\n'
        '    <Section title="구획" sx={{ mb: 3, width: "20rem" }}>몸</Section>\n'
        "  </>);\n"
        "}\n"
    )
    # 까닭 없는 표식은 넘기지 않는다 — 부품마다 · 키마다 따로 잡히는지 본다.
    bad_geometry = (
        "export function BadGeometry() {\n"
        "  return (<>\n"
        "    {/* clovi-allow-geometry: */}\n"
        '    <Card sx={{ p: 0, height: "10rem" }}>판</Card>\n'
        '    <Callout tone="warn" sx={{ my: 1, px: 2 }}>상자</Callout>\n'
        "  </>);\n"
        "}\n"
    )
    good_geometry = (
        'import Toolbar from "@mui/material/Toolbar";\n'
        "export function GoodGeometry() {\n"
        "  return (<>\n"
        '    <Toolbar sx={{ minHeight: 56, pr: 0 }} />\n'
        '    <Card padding="none" sx={{ overflow: "hidden", minWidth: 0, minHeight: { md: 0 } }}>판</Card>\n'
        "    {/* clovi-allow-geometry: 좁은 판을 보이는 견본이다. */}\n"
        '    <Card sx={{ maxWidth: "32rem" }}>견본</Card>\n'
        '    <Callout tone="info" sx={{ "& ul": { mt: 0.75 } }}>선택자 안의 키</Callout>\n'
        '    <Card sx={cardSx}>변수 sx</Card>\n'
        '    <Box sx={{ mt: 2, width: "10rem" }}>부품이 아니다</Box>\n'
        '    <Section flush title="구획">몸</Section>\n'
        "  </>);\n"
        "}\n"
    )
    # 글자 단추 자리 — 틀린 자리마다 따로 잡히는지 본다(메시지 박스 · 판 머리 동작 · 모달 발 · 발 부품).
    bad_ghosts = (
        "export function BadGhosts() {\n"
        "  return (<>\n"
        '    <SectionTitle title="첨부" action={<Button size="small" variant="ghost">파일 올리기</Button>} />\n'
        '    <Modal open title="실행" footer={<Button variant={"ghost"}>닫기</Button>}>몸</Modal>\n'
        '    <Card><ActionFooter placement="card"><KitButton variant="ghost">취소</KitButton></ActionFooter></Card>\n'
        "  </>);\n"
        "}\n"
    )
    good_ghosts = (
        "export function GoodGhosts() {\n"
        '  return (<Section title="첨부" action={<Button size="small">파일 올리기</Button>}>\n'
        '    <Stack><Button size="small" variant="ghost" onClick={drop}>떼기</Button></Stack>\n'
        '    <Callout tone="warn" action={<Button size="sm" onClick={retry}>다시 시도</Button>}>안내</Callout>\n'
        '    <Callout tone="info" action={<Button size="sm" startIcon={<Icon variant="ghost" />}>자세히</Button>}>속성 식 안의 다른 요소</Callout>\n'
        '    <Modal open title="관리" footer={<Button>닫기</Button>}><Button size="sm" variant="ghost">전체 보기</Button></Modal>\n'
        "  </Section>);\n"
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
        "export function GoodHeads() {\n"
        '  return (<>\n'
        '    <PageHeader title="백업" actions={<><Button onClick={guide}>복원 안내</Button><OverflowMenu items={[]} /><Button variant="primary" onClick={run}>백업 실행</Button></>} />\n'
        '    <PageHeader title="둘째 머리" actions={<Button onClick={copy}>복사</Button>} />\n'
        '    <PageHeader title="갈래" actions={off ? (<><Button>이력</Button><Button variant="primary">복원</Button></>) : (<><Button>이동</Button><Button variant="primary">저장</Button></>)} />\n'
        '    <PageHeader title="부품" actions={<GoodHeadParts onRun={run} />} />\n'
        '    <Box><Button variant="primary">본문 채움</Button><Button>본문 보조</Button></Box>\n'
        '    <Box sx={{ maxWidth: PROSE_MAX_WIDTH }}>긴 글</Box>\n'
        '    <TabShell tabs={GOOD_TABS} />\n'
        '    <FilterChips chips={[{ key: "q", label: `검색: ${q}` }]} />\n'
        "  </>);\n"
        "}\n"
        'const GOOD_TABS = [{ key: "p", label: "사람", count: people }];\n'
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
        (src / "BadGhosts.jsx").write_text(bad_ghosts, encoding="utf-8")
        (src / "GoodGhosts.jsx").write_text(good_ghosts, encoding="utf-8")
        # 머리 동작을 옆 부품으로 뺀 자리 — 진단의 `DiagnosticActions` 모양. 쓰는 화면과 정의한 파일이 다르다.
        (src / "UsesHeadParts.jsx").write_text(
            'export const Page = () => <PageHeader title="진단" actions={<><Stamp /><BadHeadParts onRun={run} /><Lifecycle state={s} /></>} />;' + "\n", encoding="utf-8")
        (src / "HeadParts.jsx").write_text(
            "export function BadHeadParts({ onRun }) {" + "\n"
            + "  return (<><Button variant=\"primary\" onClick={onRun}>진단 수집</Button>{copy ? <Button>복사</Button> : null}</>);" + "\n"
            + "}" + "\n"
            + "export function GoodHeadParts({ onRun }) {" + "\n"
            + "  return (<><Button>복사</Button><Button variant=\"primary\" onClick={onRun}>진단 수집</Button></>);" + "\n"
            + "}" + "\n"
            + "export function Lifecycle({ state }) {" + "\n"
            + "  return (<>{state === \"planned\" ? <Button variant=\"primary\">회차 열기</Button> : null}{state === \"active\" ? <Button>회차 닫기</Button> : null}</>);" + "\n"
            + "}" + "\n", encoding="utf-8")
        ghost_hits = scan_file("screens/BadGhosts.jsx", bad_ghosts)
        geometry_hits = sorted((rule, what) for rule, _line, what in scan_file("screens/BadGeometry.jsx", bad_geometry))
        good_geometry_hits = scan_file("screens/GoodGeometry.jsx", good_geometry)
        good_ghost_hits = scan_file("screens/GoodGhosts.jsx", good_ghosts)
        ledger = root / "ledger.md"
        ledger.write_text(
            "| 파일 | 조합 규칙 | 이유 | 대체 불가 근거 |\n|---|---|---|---|\n"
            "| `screens/Gone.jsx` | `list-footer` | 사라진 자리 | 없음 |\n", encoding="utf-8")
        new, _waiting, stale, dead = scan(root / "src", ledger, {("screens/Nowhere.jsx", "row-button")})
    bad_rules = {rule for (rel, rule) in new if rel == "screens/Bad.jsx"}
    for rule in RULES:
        if rule not in bad_rules:
            problems.append(f"Known Bad 를 못 잡음: {rule}")
    good_hits = [v for (rel, _rule), v in new.items() if rel in ("screens/Good.jsx", "screens/GoodGhosts.jsx")]
    if good_hits:
        problems.append(f"Known Good 을 잘못 잡음: {good_hits}")
    ghost_slots = sorted(what.split(" in ", 1)[1] for rule, _line, what in ghost_hits if rule == "ghost-slot")
    if ghost_slots != ["모달 발", "발", "판 머리 동작"]:
        problems.append(f"글자 단추 자리 셋(판 머리 동작 · 모달 발 · 카드 발)을 따로 못 잡음: {ghost_slots}")
    if good_ghost_hits:
        problems.append(f"글자 단추의 맞는 자리(목록 안 · 모달 몸 · 속성 식 안 다른 요소)를 잘못 잡음: {good_ghost_hits}")
    want_geometry = [
        ("callout-margin", "<Callout sx my: 1>"),
        ("primitive-geometry-override", "<Callout sx px: 2>"),
        ("primitive-geometry-override", '<Card sx height: "10rem">'),
        ("primitive-geometry-override", "<Card sx p: 0>"),
    ]
    if geometry_hits != want_geometry:
        problems.append(f"부품 기하 덮기(까닭 없는 표식 · 키마다)를 잡지 못함: {geometry_hits}")
    if good_geometry_hits:
        problems.append(f"부품 기하의 맞는 자리(MUI 이름 · 속성 · 줄어듦 허락 · 표식 · 선택자 · 변수 · 부품 아님)를 잘못 잡음: {good_geometry_hits}")
    if ("screens/Nowhere.jsx", "row-button") not in stale:
        problems.append("stale 대기 항목을 못 잡음")
    if ("screens/Gone.jsx", "list-footer") not in dead:
        problems.append("죽은 예외를 못 잡음")
    part_hits = new.get(("screens/HeadParts.jsx", "primary-last"), [])
    if len(part_hits) != 1 or "BadHeadParts" not in part_hits[0]:
        problems.append(f"옆 부품으로 뺀 머리 동작의 채움 앞자리를 한 번만 잡지 못함: {part_hits}")
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
