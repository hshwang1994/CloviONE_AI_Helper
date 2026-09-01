"""표의 열이 **자기가 무엇인지** 말하는가 (`type`).

## 이 검사가 있는 이유

몸통 칸의 정렬·폭·자릿수 고정은 열의 `type` 에서 파생한다(`frontend/src/ui/columnTypes.js`).
`type` 을 안 적은 열은 `UNTYPED` 로 떨어지고, 그것은 **왼쪽 정렬 + 4.5rem 바닥**이다.

그 기본값은 조용히 틀린다. 한 표 안에서 실제로 이렇게 갈렸다 — `/users` 의 「최근 로그인」은
왼쪽이고 「생성 일자」는 가운데였다. 둘 다 날짜인데 한쪽만 `type:"date"` 를 적어서다.
사용자가 「관리자 화면의 정렬이 사용자 화면과 다르다」고 한 것이 이 부류다.

어휘를 만든 것만으로는 안 됐다. `column-types.test.jsx` 가 어휘 자체(어느 타입이 가운데인가)를
지키지만, **그 어휘를 실제로 쓰는가**는 아무도 안 봤다. 이 검사가 그 자리를 맡는다.

## 무엇을 보는가

`columns: [...]` / `columns = [...]` 배열 안의 항목만 본다. 상세 필드(`fields:`)는 정렬 규칙이
없으므로 대상이 아니다.

  * 객체 리터럴이면 `type:` 또는 `identifier:` 가 있어야 한다.
  * 공장 함수 호출이면 그 함수가 **타입을 붙여 주는 공장**이어야 한다(아래 목록).
  * 펼침(`...FOO`)과 변수 참조는 그 자리에서 판단할 수 없어 건너뛴다 — 그 배열의 정본을
    따라가면 거기서 다시 이 검사에 걸린다.

새 공장을 만들면 이 목록에 이름을 더한다. 목록에 없는 이름은 「타입을 안 붙인다」로 본다 —
모르는 것을 통과시키면 이 검사가 서서히 아무것도 안 지키게 된다.
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "src"

#: 타입을 **스스로** 붙이는 공장. 정본은 `frontend/src/screens/data-screen/columnHelpers.jsx`
#: 와 `frontend/src/screens/registry/shared.js` 다.
TYPED_FACTORIES = {
    "badgeCol", "mapCol", "dateCol", "activeCol", "enabledCol", "readCol",
    "linkCol", "truncateCol", "boolCol", "objCol", "actionCol", "personField",
    "snapCol", "selectionColumn",
}

#: 타입을 **인자로 받는** 공장 → `{이름: 타입이 있어야 하는 인자 번호(0부터)}`.
#: `col("created_at", "생성", "date")` 처럼 세 번째 자리에 타입이 온다.
TYPED_ARG_FACTORIES = {"col": 2}

ARRAY_RE = re.compile(r"columns\s*[:=]\s*\[")
KEY_RE = re.compile(r"\bkey\s*:")
TYPE_RE = re.compile(r"\btype\s*:")
IDENTIFIER_RE = re.compile(r"\bidentifier\s*:")
CALL_RE = re.compile(r"^([A-Za-z_$][\w$]*)\s*\(")


def _balanced(text: str, start: int, open_ch: str, close_ch: str) -> int:
    """`start` 의 여는 괄호와 짝이 되는 닫는 괄호의 위치. 못 찾으면 -1.

    문자열·주석 안의 괄호는 세지 않는다 — 안 그러면 `label: "["` 하나가 배열의 끝을
    엉뚱한 자리로 옮긴다.
    """
    depth = 0
    i = start
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in "\"'`":
            quote = ch
            i += 1
            while i < n and text[i] != quote:
                if text[i] == "\\":
                    i += 1
                i += 1
        elif ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
        elif ch == "/" and i + 1 < n and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            i = end + 1 if end >= 0 else n
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _split_items(body: str) -> list[str]:
    """배열 본문을 최상위 쉼표로 자른다."""
    items, depth, buf, i, n = [], 0, [], 0, len(body)
    while i < n:
        ch = body[i]
        if ch in "\"'`":
            quote = ch
            buf.append(ch)
            i += 1
            while i < n and body[i] != quote:
                if body[i] == "\\":
                    buf.append(body[i]); i += 1
                buf.append(body[i]); i += 1
            if i < n:
                buf.append(body[i])
        elif ch == "/" and i + 1 < n and body[i + 1] == "/":
            while i < n and body[i] != "\n":
                i += 1
            continue
        elif ch == "/" and i + 1 < n and body[i + 1] == "*":
            end = body.find("*/", i + 2)
            i = (end + 2) if end >= 0 else n
            continue
        elif ch in "{[(":
            depth += 1; buf.append(ch)
        elif ch in "}])":
            depth -= 1; buf.append(ch)
        elif ch == "," and depth == 0:
            items.append("".join(buf)); buf = []
        else:
            buf.append(ch)
        i += 1
    if "".join(buf).strip():
        items.append("".join(buf))
    return items


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def check_file(path: Path) -> list[str]:
    text = io.open(path, encoding="utf-8").read()
    problems: list[str] = []
    for match in ARRAY_RE.finditer(text):
        open_at = text.index("[", match.start())
        close_at = _balanced(text, open_at, "[", "]")
        if close_at < 0:
            continue
        body = text[open_at + 1:close_at]
        for raw in _split_items(body):
            item = raw.strip()
            if not item or item.startswith("..."):
                continue
            line = _line_of(text, open_at) + raw[: len(raw) - len(raw.lstrip())].count("\n")
            if item.startswith("{"):
                if not KEY_RE.search(item):
                    continue          # 열이 아니다(조건부 스프레드의 잔해 등)
                if TYPE_RE.search(item) or IDENTIFIER_RE.search(item):
                    continue
                label = (re.search(r'label\s*:\s*"([^"]*)"', item) or [None, "?"])[1]
                problems.append(
                    f"{path.relative_to(ROOT)}:{line}: 열 «{label}» 에 `type` 이 없다"
                )
                continue
            call = CALL_RE.match(item)
            if not call:
                continue
            name = call.group(1)
            if name in TYPED_FACTORIES:
                continue
            if name in TYPED_ARG_FACTORIES:
                open_at = item.index("(")
                close_at = _balanced(item, open_at, "(", ")")
                args = _split_items(item[open_at + 1:close_at]) if close_at > 0 else []
                need = TYPED_ARG_FACTORIES[name]
                if len(args) > need and args[need].strip():
                    continue
                problems.append(
                    f"{path.relative_to(ROOT)}:{line}: `{name}({args[0].strip() if args else '…'}, …)` 에 타입 인자가 없다"
                )
                continue
            problems.append(
                f"{path.relative_to(ROOT)}:{line}: `{name}(…)` 는 타입을 안 붙인다"
            )
    return problems


def main() -> int:
    files = [p for p in SRC.rglob("*.js") if ".test." not in p.name]
    files += [p for p in SRC.rglob("*.jsx") if ".test." not in p.name]
    problems: list[str] = []
    for path in sorted(files):
        problems.extend(check_file(path))
    if problems:
        print("COLUMN_TYPE_MISSING")
        for line in problems:
            print("  " + line)
        print(f"\n{len(problems)}건. 열은 자기가 무엇인지 말해야 정렬·폭이 화면마다 같아진다.")
        print("어휘는 frontend/src/ui/columnTypes.js 에 있다.")
        return 1
    print(f"COLUMN_TYPES_OK ({len(files)} files)")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
