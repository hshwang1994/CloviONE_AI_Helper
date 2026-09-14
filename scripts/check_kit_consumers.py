# -*- coding: utf-8 -*-
"""화면이 **정본 부품 대신 MUI 원재료를 직접** 쓰고 있지 않은가 (핸드오프 §0-7 · §0-11 · ACCEPTANCE A2).

## 무엇을 막나

같은 의미의 UI 는 정본 부품 하나로 선다(`ui/kit.jsx` 등). 화면이 MUI `Alert` · `Chip` · `Tabs` ·
`Paper` 를 직접 들고 오면, 그 자리는 정본 계약(높이 · 모서리 · 톤 · 접근성)을 **자기 식으로 다시
그린 사본**이 된다. 갤러리와 계약 시험은 정본만 보므로 그 사본은 아무 검사에도 안 걸린다.

## 두 부류 (COMPONENT_LEDGER.md 「raw MUI primitive 경계」와 같은 표)

  A  정본 wrapper 가 있는 원재료. 화면에서 import 하면 실패다 — 대장 「예외」 표에 파일과 이름이
     있을 때만 통과.
  B  직접 써도 되는 기초 원재료(IconButton · Switch · Checkbox · TextField · Popover …). 대신
     크기 · 색 · 모서리를 **화면에서 숫자로** 주면 실패다(`height: "2rem"`, `borderRadius: 12`,
     `color: "#fff"`). 토큰 식(`remPx(CONTROL.buttonSm)`)은 통과.

대장에 적혀 있는데 그 파일에서 더는 안 쓰는 예외는 **죽은 예외**로 실패시킨다 — 대장이 현실보다
넓어지면 그 표는 곧 아무도 안 읽는 허가증이 된다.

## 쓰는 법

    python scripts/check_kit_consumers.py            # 판정
    python scripts/check_kit_consumers.py --report   # 실패해도 0 으로 끝나고 목록만 낸다(B 인벤토리)
    python scripts/check_kit_consumers.py --self-test
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

A_PRIMITIVES = {
    "Alert", "Chip", "Dialog", "DialogTitle", "DialogContent", "DialogActions", "Menu", "MenuList",
    "Tabs", "Tab", "ToggleButton", "ToggleButtonGroup", "Table", "TableBody", "TableCell",
    "TableContainer", "TableFooter", "TableHead", "TableRow", "Snackbar", "Paper", "Card",
    "CardContent", "Autocomplete", "Badge", "Skeleton", "Button",
}
B_PRIMITIVES = {
    "IconButton", "Switch", "Checkbox", "Radio", "TextField", "InputBase", "OutlinedInput",
    "Popover", "Drawer", "LinearProgress", "CircularProgress", "Slider",
}
# 정본 부품을 **구현하는** 파일. 여기서는 A 원재료가 재료다.
CANONICAL_HOSTS = {
    "ui/kit.jsx": A_PRIMITIVES,
    "ui/FilterBar.jsx": {"Chip"},
    "ui/filters.jsx": {"Autocomplete", "MenuItem", "Chip"},
    "ui/TabShell.jsx": {"Tabs", "Tab"},
    "ui/TagPicker.jsx": {"Chip", "Autocomplete"},
    "ui/TableHeaderCell.jsx": {"TableCell"},
    "ui/VirtualRows.jsx": {"TableCell", "TableRow"},
}

IMPORT_DEFAULT = re.compile(r"""import\s+(\w+)\s+from\s+["']@mui/material/(\w+)["']""")
IMPORT_NAMED = re.compile(r"""import\s*\{([^}]*)\}\s*from\s*["']@mui/material["']""", re.S)
# B 원재료 여는 태그 안의 화면 전용 시각 리터럴
HEIGHT_LITERAL = re.compile(
    r"""\b(height|minHeight|maxHeight)\s*:\s*(["'][0-9.]+(px|rem)["']|[0-9]+(?![.\w]))""")
# 아이콘 단추는 정사각형이라 폭도 크기 계약이다(다른 원재료의 폭은 배치다).
SQUARE_LITERAL = re.compile(
    r"""\b(width|minWidth)\s*:\s*(["'][0-9.]+(px|rem)["']|[0-9]+(?![.\w]))""")
RADIUS_LITERAL = re.compile(r"""\bborderRadius\s*:\s*(["'][0-9.]+(px|rem|%)?["']|[0-9]+(?![.\w]))""")
COLOR_LITERAL = re.compile(r"""#[0-9A-Fa-f]{3,8}\b|rgba?\(\s*[0-9]""")


def element_span(text: str, start: int) -> int | None:
    """여는 태그의 끝 `>` — 중괄호 깊이 0 에서만 센다(`sx={{ "&:hover > *": … }}`)."""
    depth = 0
    i = start
    while i < len(text):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == ">" and depth == 0:
            return i
        i += 1
    return None


def imports_of(text: str) -> dict[str, str]:
    """로컬 이름 → MUI 원재료 이름."""
    found: dict[str, str] = {}
    for m in IMPORT_DEFAULT.finditer(text):
        found[m.group(1)] = m.group(2)
    for m in IMPORT_NAMED.finditer(text):
        for part in m.group(1).split(","):
            part = part.strip()
            if not part:
                continue
            if " as " in part:
                src, local = [p.strip() for p in part.split(" as ", 1)]
            else:
                src = local = part
            found[local] = src
    return found


def read_exceptions(ledger: Path) -> dict[str, set[str]]:
    """대장 「예외」 표: `| 파일 | 원재료 | 이유 | 대체 불가 근거 |`."""
    out: dict[str, set[str]] = {}
    if not ledger.is_file():
        return out
    in_table = False
    for line in ledger.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s.startswith("|"):
            in_table = False
            continue
        cells = [c.strip().strip("`") for c in s.strip("|").split("|")]
        if len(cells) >= 2 and cells[0] == "파일" and cells[1] == "원재료":
            in_table = True
            continue
        if not in_table or set("".join(cells)) <= set("-: "):
            continue
        path = cells[0].replace("frontend/src/", "")
        names = {n.strip().strip("`") for n in re.split(r"[,·/]", cells[1]) if n.strip()}
        out.setdefault(path, set()).update(names)
    return out


def scan(src: Path, ledger: Path) -> tuple[list[str], list[str], list[str], int]:
    exceptions = read_exceptions(ledger)
    a_hits: list[str] = []
    b_hits: list[str] = []
    used: dict[str, set[str]] = {}
    files = 0
    for path in sorted(src.rglob("*")):
        if path.suffix not in (".js", ".jsx") or ".test." in path.name:
            continue
        rel = path.relative_to(src).as_posix()
        text = path.read_text(encoding="utf-8")
        if "@mui/material" not in text:
            continue
        files += 1
        imported = imports_of(text)
        prims = set(imported.values())
        host_allowed = CANONICAL_HOSTS.get(rel, set())
        allowed = host_allowed | exceptions.get(rel, set())
        for local, prim in sorted(imported.items()):
            if prim == "MenuItem" and not ({"Menu", "MenuList"} & prims):
                continue  # `TextField select` 안의 항목은 B 다
            if prim in A_PRIMITIVES and prim not in allowed:
                line = text[: text.find(local)].count("\n") + 1
                a_hits.append(f"{rel}:{line} {prim}")
            if prim in A_PRIMITIVES and prim in exceptions.get(rel, set()):
                used.setdefault(rel, set()).add(prim)
            if prim in B_PRIMITIVES and prim in exceptions.get(rel, set()):
                used.setdefault(rel, set()).add(prim)
            if prim in B_PRIMITIVES and rel not in CANONICAL_HOSTS and prim not in exceptions.get(rel, set()):
                for m in re.finditer(r"<" + re.escape(local) + r"\b", text):
                    end = element_span(text, m.end())
                    if end is None:
                        continue
                    tag = text[m.start():end]
                    bad = [x.group(0) for x in HEIGHT_LITERAL.finditer(tag)]
                    if prim == "IconButton":
                        bad += [x.group(0) for x in SQUARE_LITERAL.finditer(tag)]
                    bad += [x.group(0) for x in RADIUS_LITERAL.finditer(tag)]
                    bad += [x.group(0) for x in COLOR_LITERAL.finditer(tag)]
                    if bad:
                        line = text.count("\n", 0, m.start()) + 1
                        b_hits.append(f"{rel}:{line} {prim} {', '.join(bad[:3])}")
    dead = []
    for rel, names in sorted(exceptions.items()):
        missing = sorted(n for n in names if n in (A_PRIMITIVES | B_PRIMITIVES) and n not in used.get(rel, set()))
        if missing:
            dead.append(f"{rel}: {', '.join(missing)}")
    return a_hits, b_hits, dead, files


def self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        (src / "screens").mkdir(parents=True)
        (src / "screens" / "Bad.jsx").write_text(
            'import Alert from "@mui/material/Alert";\n'
            'import IconButton from "@mui/material/IconButton";\n'
            'export default () => <><Alert severity="error">x</Alert>'
            '<IconButton aria-label="x" sx={{ height: "2rem" }} /></>;\n', encoding="utf-8")
        (src / "screens" / "Good.jsx").write_text(
            'import Dialog from "@mui/material/Dialog";\n'
            'import IconButton from "@mui/material/IconButton";\n'
            'export default () => <Dialog open><IconButton aria-label="닫기" size="small" /></Dialog>;\n',
            encoding="utf-8")
        ledger = root / "ledger.md"
        ledger.write_text(
            "| 파일 | 원재료 | 이유 | 대체 불가 근거 |\n|---|---|---|---|\n"
            "| `screens/Good.jsx` | `Dialog` | 명령 팔레트 | 모달 계약과 다르다 |\n"
            "| `screens/Gone.jsx` | `Paper` | 사라진 자리 | — |\n", encoding="utf-8")
        a_hits, b_hits, dead, _ = scan(src, ledger)
    problems = []
    if not any("Bad.jsx" in h and "Alert" in h for h in a_hits):
        problems.append("Known Bad: 화면의 MUI Alert 를 못 잡음")
    if not any("Bad.jsx" in h and "IconButton" in h for h in b_hits):
        problems.append("Known Bad: IconButton 높이 리터럴을 못 잡음")
    if any("Good.jsx" in h for h in a_hits + b_hits):
        problems.append("Known Good: 대장 예외 · 토큰만 쓰는 IconButton 을 잘못 잡음")
    if not any("Gone.jsx" in d for d in dead):
        problems.append("죽은 예외를 못 잡음")
    if problems:
        for p in problems:
            print("[SELF-TEST] " + p)
        print("KIT_CONSUMERS_SELF_TEST_FAILED")
        return 1
    print("KIT_CONSUMERS_SELF_TEST_OK")
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="정본 부품 대신 MUI 원재료를 쓰는 자리")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    a_hits, b_hits, dead, files = scan(SRC, LEDGER)
    for title, rows in (("A 원재료를 화면이 직접 쓴다(대장 예외 없음)", a_hits),
                        ("B 원재료에 화면 전용 시각 리터럴", b_hits),
                        ("죽은 예외(대장에는 있는데 그 파일에서 안 쓴다)", dead)):
        if rows:
            print(f"[{'REPORT' if args.report else 'FAIL'}] {title}: {len(rows)}건")
            for r in rows:
                print("   ", r)
    total = len(a_hits) + len(b_hits) + len(dead)
    if total and not args.report:
        print(f"KIT_CONSUMERS_FAILED (A {len(a_hits)} · B {len(b_hits)} · 죽은 예외 {len(dead)} / MUI 파일 {files}개)")
        return 1
    print(f"KIT_CONSUMERS_{'REPORT' if args.report else 'OK'} "
          f"(A {len(a_hits)} · B {len(b_hits)} · 죽은 예외 {len(dead)} / MUI 파일 {files}개)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
