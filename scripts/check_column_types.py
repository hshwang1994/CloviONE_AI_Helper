"""표의 열이 **자기가 무엇인지** 말하는가 (`type`).

## 이 검사가 있는 이유

몸통 칸의 정렬·폭·자릿수 고정은 열의 `type` 에서 파생한다(`frontend/src/ui/columnTypes.js`).
`type` 을 안 적은 열은 `UNTYPED` 로 떨어지고, 그것은 **가운데 정렬 + 4.5rem 바닥**이다.

그 기본값은 조용히 틀린다. 정렬이 아니라 **폭과 줄바꿈**이 틀린다 — 타입이 없으면 말줄임이
안 걸려 산문이 여러 줄로 접히고, 바닥 폭도 그 값에 맞지 않는다. 정렬로만 보면 예전에는 더
험했다: `/users` 의 「최근 로그인」은 왼쪽이고 「생성 일자」는 가운데였다(둘 다 날짜인데
한쪽만 `type:"date"` 를 적어서다). 2026-09-06 에 제목을 뺀 전부를 가운데로 모아 그 축은
갈리지 않지만, 폭과 줄바꿈은 여전히 타입이 정한다.

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

## 「제목」 열은 제목 열이다 (D-501)

라벨이 「제목」인 열은 `type: "title"` 이어야 한다. 제목은 그 행이 무엇인지 말하는 열이라 표에서 홀로
왼쪽에 서고(D-471) 남는 폭을 갖는다. 관리 알림 · 공지 배너 · 메일 발송의 「제목」은 `identifier`
이거나 타입이 없어 가운데에 섰고, 폭은 옆 열과 똑같이 나눠 가졌다.

이 규칙은 `FAILURE_COLUMNS = [` 처럼 **대문자 이름의 열 배열**도 본다. 위의 「타입이 있는가」 규칙은
여전히 소문자 `columns` 배열만 본다 — 그 규칙을 대문자 배열로 넓히면 다른 화면의 무타입 열 여덟이
한꺼번에 걸린다(메일 발송 · 오프보딩 · 사용자). 그 화면들의 회차가 타입을 붙인 뒤에 넓힌다.

    python scripts/check_column_types.py             # 판정
    python scripts/check_column_types.py --selftest  # 검사기 자기검증(Known Bad · Known Good 문자열)
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
#: 「제목」 규칙이 보는 배열 — 대소문자를 가리지 않는다(`FAILURE_COLUMNS = [` · `DEV_SUMMARY_COLUMNS = [`).
TITLE_ARRAY_RE = re.compile(r"columns\s*[:=]\s*\[", re.IGNORECASE)
KEY_RE = re.compile(r"\bkey\s*:")
TYPE_RE = re.compile(r"\btype\s*:")
IDENTIFIER_RE = re.compile(r"\bidentifier\s*:")
CALL_RE = re.compile(r"^([A-Za-z_$][\w$]*)\s*\(")
SPREAD_CALL_RE = re.compile(r"\.\.\.\s*([A-Za-z_$][\w$]*)\s*\(")
LABEL_RE = re.compile(r"""\blabel\s*:\s*["']([^"']*)["']""")
TITLE_TYPE_RE = re.compile(r"""\btype\s*:\s*["']title["']""")
#: 제목 열이어야 하는 라벨.
TITLE_LABELS = {"제목"}


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


def _split_items_at(body: str) -> list[tuple[int, str]]:
    """배열 본문을 최상위 쉼표로 자른다. 항목마다 (본문 안에서 첫 뜻 있는 글자의 자리, 글자) 다.

    자리를 따로 세는 이유: 주석은 글자에 안 담기므로 글자 길이로 자리를 거꾸로 셀 수 없다. 예전에는
    그렇게 셌고, 그래서 한 배열의 모든 항목이 배열 첫 줄 번호로 보고됐다.
    """
    items, depth, buf, i, n = [], 0, [], 0, len(body)
    first = -1
    while i < n:
        ch = body[i]
        if first < 0 and not ch.isspace() and not (ch == "/" and i + 1 < n and body[i + 1] in "/*"):
            first = i
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
            items.append((first, "".join(buf))); buf = []; first = -1
        else:
            buf.append(ch)
        i += 1
    if "".join(buf).strip():
        items.append((first, "".join(buf)))
    return items


def _split_items(body: str) -> list[str]:
    """배열 본문을 최상위 쉼표로 자른다."""
    return [raw for _at, raw in _split_items_at(body)]


def _call_args(item: str, open_at: int) -> list[str]:
    close_at = _balanced(item, open_at, "(", ")")
    return _split_items(item[open_at + 1:close_at]) if close_at > 0 else []


def _string_literal(arg: str) -> str | None:
    m = re.fullmatch(r"""\s*["']([^"']*)["']\s*""", arg or "")
    return m.group(1) if m else None


def _label_and_title(item: str) -> tuple[str | None, bool]:
    """열 항목 하나의 (라벨, 제목 타입인가).

    라벨은 객체 리터럴의 `label:` 이거나 공장 호출(`col("title", "제목")` · `...col(…)`)의 둘째 인자다.
    제목 타입은 `type: "title"` 이거나 `col(키, 라벨, "title")` 의 셋째 인자다.
    """
    label = None
    is_title = bool(TITLE_TYPE_RE.search(item))
    call = CALL_RE.match(item) if not item.startswith("{") else None
    spread = SPREAD_CALL_RE.search(item) if item.startswith("{") else None
    head = call or spread
    if head:
        args = _call_args(item, item.index("(", head.start()))
        if len(args) > 1:
            label = _string_literal(args[1])
        if head.group(1) in TYPED_ARG_FACTORIES and len(args) > TYPED_ARG_FACTORIES[head.group(1)]:
            is_title = is_title or _string_literal(args[TYPED_ARG_FACTORIES[head.group(1)]]) == "title"
    if item.startswith("{"):
        own = LABEL_RE.search(item)
        if own:
            label = own.group(1)
    return label, is_title


def check_title_columns(path: Path, text: str) -> list[str]:
    """라벨이 「제목」인 열은 `type: "title"` 이어야 한다(D-501)."""
    problems: list[str] = []
    for match in TITLE_ARRAY_RE.finditer(text):
        open_at = text.index("[", match.start())
        close_at = _balanced(text, open_at, "[", "]")
        if close_at < 0:
            continue
        for at, raw in _split_items_at(text[open_at + 1:close_at]):
            item = raw.strip()
            if not item or item.startswith("...") or at < 0:
                continue
            label, is_title = _label_and_title(item)
            if label in TITLE_LABELS and not is_title:
                line = _line_of(text, open_at + 1 + at)
                problems.append(
                    f"{_rel(path)}:{line}: 열 «{label}» 은 그 행의 제목이다 — `type: \"title\"` 을 준다"
                )
    return problems


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def check_text(path: Path, text: str) -> list[str]:
    """한 파일의 문제 목록 — 타입 누락 규칙과 「제목」 규칙 둘 다."""
    problems: list[str] = []
    for match in ARRAY_RE.finditer(text):
        open_at = text.index("[", match.start())
        close_at = _balanced(text, open_at, "[", "]")
        if close_at < 0:
            continue
        body = text[open_at + 1:close_at]
        for at, raw in _split_items_at(body):
            item = raw.strip()
            if not item or item.startswith("..."):
                continue
            line = _line_of(text, open_at + 1 + max(at, 0))
            if item.startswith("{"):
                if not KEY_RE.search(item):
                    continue          # 열이 아니다(조건부 스프레드의 잔해 등)
                if TYPE_RE.search(item) or IDENTIFIER_RE.search(item):
                    continue
                label = (re.search(r'label\s*:\s*"([^"]*)"', item) or [None, "?"])[1]
                problems.append(
                    f"{_rel(path)}:{line}: 열 «{label}» 에 `type` 이 없다"
                )
                continue
            call = CALL_RE.match(item)
            if not call:
                continue
            name = call.group(1)
            if name in TYPED_FACTORIES:
                continue
            if name in TYPED_ARG_FACTORIES:
                args = _call_args(item, item.index("("))
                need = TYPED_ARG_FACTORIES[name]
                if len(args) > need and args[need].strip():
                    continue
                problems.append(
                    f"{_rel(path)}:{line}: `{name}({args[0].strip() if args else '…'}, …)` 에 타입 인자가 없다"
                )
                continue
            problems.append(
                f"{_rel(path)}:{line}: `{name}(…)` 는 타입을 안 붙인다"
            )
    problems.extend(check_title_columns(path, text))
    return problems


def check_file(path: Path) -> list[str]:
    return check_text(path, io.open(path, encoding="utf-8").read())


def selftest() -> int:
    """검사기 자기검증 — 「제목」 규칙이 잡아야 할 모양(Known Bad)과 놓아줘야 할 모양(Known Good)."""
    bad = (
        "const FAILURE_COLUMNS = [\n"
        '  { key: "kind", label: "종류", type: "enum" },\n'
        '  { key: "subject", label: "제목" },\n'
        "];\n"
        "export const A = { columns: [{ ...col(\"title\", \"제목\"), identifier: true, sortable: true },\n"
        '  mapCol("type", "유형", MAP)] };\n'
        'export const B = { columns: [col("title", "제목", "text")] };\n'
    )
    good = (
        "const DOC_COLUMNS = [\n"
        '  // 제목은 행의 이름이다\n'
        '  { key: "title", label: "제목", type: "title", minWidth: "16rem" },\n'
        '  { key: "who", label: "제목 작성자", type: "name" },\n'
        "];\n"
        'export const A = { columns: [{ ...col("title", "제목", "title"), sortable: true }, col("t2", "제목2", "text")] };\n'
        'const fields = [{ name: "title", label: "제목", type: "text", required: true }];\n'
    )
    problems = []
    got_bad = check_title_columns(Path("Bad.jsx"), bad)
    lines = sorted(int(p.split(":")[1]) for p in got_bad)
    if lines != [3, 5, 7]:
        problems.append(f"Known Bad 셋(무타입 · identifier 스프레드 · 셋째 인자 text)을 제 줄에서 못 잡음: {got_bad}")
    got_good = check_title_columns(Path("Good.jsx"), good)
    if got_good:
        problems.append(f"Known Good(제목 타입 · 다른 라벨 · 폼 필드)을 잘못 잡음: {got_good}")
    # 줄 번호는 항목 자리에서 센다 — 주석이 끼어도 배열 첫 줄로 몰리지 않는다.
    typed = check_text(Path("Lines.jsx"), 'export const C = { columns: [\n  // 설명\n  { key: "a", label: "가", type: "text" },\n  { key: "b", label: "나" },\n] };\n')
    if typed != ["Lines.jsx:4: 열 «나» 에 `type` 이 없다"]:
        problems.append(f"타입 누락의 줄 번호가 항목 자리가 아니다: {typed}")
    if problems:
        for p in problems:
            print("[SELFTEST] " + p)
        print("COLUMN_TYPES_SELFTEST_FAILED")
        return 1
    print("COLUMN_TYPES_SELFTEST_OK (Known Bad 셋 · Known Good 오탐 0 · 항목 줄 번호)")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in args:
        return selftest()
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
