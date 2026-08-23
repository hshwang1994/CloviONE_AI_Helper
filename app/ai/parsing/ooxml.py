"""DOCX · PPTX · XLSX → 글 + 앵커. **표준 라이브러리만 쓴다.**

## 왜 `python-docx` 를 안 쓰는가

OOXML 은 zip 안의 XML 이고, 우리가 필요한 것은 **글자와 그 글자가 있던 자리**뿐이다.
서식도, 그림도, 편집도 안 한다. 그것 하나 때문에 폐쇄망 wheelhouse 에 넣어야 하는
패키지를 셋(`python-docx`·`python-pptx`·`openpyxl`) 늘리지 않는다 — 그리고 S8 이 이미
같은 판단을 했다: 업로드 판정기가 zip 안의 **항목 이름**을 직접 읽어 OOXML 셋을 가른다
(`app/core/uploads.py::_sniff_zip_family`). 여는 방식이 그때와 같다.

정직한 한계도 적어 둔다. 이 파서는 **글자만** 가져온다. 도형 안의 글, 표 안의 글, 슬라이드
본문은 가져오지만 슬라이드 노트·머리글/바닥글·주석·차트 데이터 라벨은 안 가져온다.
필요해지면 그때 넓힌다 — 없는 것을 있는 척하지 않는다.

## zip 을 열 때 지키는 것 둘

1. **압축 해제 크기를 먼저 본다.** `ZipInfo.file_size` 는 헤더 값이라 거짓일 수 있지만,
   거짓이면 실제로 읽는 쪽에서 상한에 걸린다. 두 겹으로 둔다.
2. **항목 이름을 그대로 경로로 안 쓴다.** 아무것도 디스크에 안 쓰므로 traversal 자체가
   성립하지 않는다 — 이름은 **비교에만** 쓴다.
"""

from __future__ import annotations

import logging
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from app.ai.models import ANCHOR_SECTION, ANCHOR_SHEET, ANCHOR_SLIDE
from app.ai.parsing.base import (
    PARSE_FAILED,
    ParsedUnit,
    ParseResult,
    collect,
    failure,
)

logger = logging.getLogger("app.ai.parsing")

PARSER_DOCX = "docx"
PARSER_PPTX = "pptx"
PARSER_XLSX = "xlsx"

# ── 네임스페이스 ─────────────────────────────────────────────────────────────
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG_R = "{http://schemas.openxmlformats.org/package/2006/relationships}"

#: 항목 하나의 압축 해제 상한. 슬라이드 XML 하나가 32MB 면 그것은 문서가 아니다.
MAX_ENTRY_BYTES = 32 * 1024 * 1024
#: 한 파일에서 읽는 슬라이드·시트 수 상한.
MAX_PARTS = 500
#: 시트 하나에서 읽는 행 수 상한. 10만 행 스프레드시트를 통째로 싣지 않는다.
MAX_SHEET_ROWS = 5000

_SLIDE_RE = re.compile(r"^ppt/slides/slide(\d+)\.xml$")
_CELL_REF_RE = re.compile(r"^([A-Z]+)(\d+)$")
#: `Heading1` · `Title` · 한국어 스타일 이름(`제목 1`). 절을 여는 문단을 찾는 데 쓴다.
_HEADING_STYLE_RE = re.compile(r"^(heading|title|제목)", re.IGNORECASE)


class OoxmlError(Exception):
    """열지 못했다. 부르는 쪽이 값으로 접는다."""


# ── DOCX ─────────────────────────────────────────────────────────────────────


def parse_docx(path: Path) -> ParseResult:
    """제목 문단을 만날 때마다 새 절이 열린다. 앵커는 「몇 번째 절」과 그 제목이다."""
    try:
        root = _read_xml(path, "word/document.xml")
    except OoxmlError as exc:
        return failure(PARSE_FAILED, parser=PARSER_DOCX, detail=str(exc))

    units: list[ParsedUnit] = []
    lines: list[str] = []
    heading = ""
    index = 0

    def flush() -> None:
        nonlocal lines, heading, index
        body = "\n".join(lines).strip()
        if body:
            index += 1
            units.append(
                ParsedUnit(
                    anchor_kind=ANCHOR_SECTION,
                    anchor_ref=f"s{index}",
                    anchor_label=heading or f"{index}번째 절",
                    text=(f"{heading}\n{body}" if heading else body),
                    ordinal=index - 1,
                )
            )
        lines = []

    # `iter()` 는 문서 순서대로 준다 — 표 안의 문단도 제자리에서 나온다.
    for para in root.iter(f"{_W}p"):
        text = _docx_paragraph_text(para)
        if _is_heading(para):
            flush()
            heading = text
            continue
        if text:
            lines.append(text)
    flush()
    return collect(PARSER_DOCX, units)


def _docx_paragraph_text(para) -> str:
    parts = [node.text or "" for node in para.iter(f"{_W}t")]
    # `w:tab` 은 글자가 아니라 요소다. 안 넣으면 표 셀들이 한 덩어리로 붙는다.
    if para.find(f".//{_W}tab") is not None and parts:
        return "\t".join(p for p in parts if p).strip()
    return "".join(parts).strip()


def _is_heading(para) -> bool:
    style = para.find(f"{_W}pPr/{_W}pStyle")
    if style is None:
        return False
    value = style.get(f"{_W}val") or ""
    return bool(_HEADING_STYLE_RE.match(value))


# ── PPTX ─────────────────────────────────────────────────────────────────────


def parse_pptx(path: Path) -> ParseResult:
    """슬라이드마다 글 하나. 앵커는 슬라이드 번호다."""
    try:
        with _open_zip(path) as archive:
            names = [n for n in archive.namelist() if _SLIDE_RE.match(n)]
            # `slide10.xml` 이 `slide2.xml` 보다 앞에 오면 안 된다. 번호로 정렬한다.
            names.sort(key=lambda n: int(_SLIDE_RE.match(n).group(1)))
            units = []
            for number, name in enumerate(names[:MAX_PARTS], start=1):
                root = _parse_entry(archive, name)
                texts = [node.text or "" for node in root.iter(f"{_A}t")]
                units.append(
                    ParsedUnit(
                        anchor_kind=ANCHOR_SLIDE,
                        anchor_ref=str(number),
                        anchor_label=f"{number}번 슬라이드",
                        text="\n".join(t for t in texts if t.strip()),
                        ordinal=number - 1,
                    )
                )
    except OoxmlError as exc:
        return failure(PARSE_FAILED, parser=PARSER_PPTX, detail=str(exc))
    return collect(PARSER_PPTX, units)


# ── XLSX ─────────────────────────────────────────────────────────────────────


def parse_xlsx(path: Path) -> ParseResult:
    """시트마다 글 하나. 앵커는 `시트이름!A1:D20` — 시트와 **실제로 쓴 범위**다."""
    try:
        with _open_zip(path) as archive:
            shared = _shared_strings(archive)
            units = []
            for number, (title, part) in enumerate(_sheet_parts(archive)[:MAX_PARTS], start=1):
                text, ref = _sheet_text(archive, part, shared)
                units.append(
                    ParsedUnit(
                        anchor_kind=ANCHOR_SHEET,
                        anchor_ref=f"{title}!{ref}" if ref else title,
                        anchor_label=title,
                        text=text,
                        ordinal=number - 1,
                    )
                )
    except OoxmlError as exc:
        return failure(PARSE_FAILED, parser=PARSER_XLSX, detail=str(exc))
    return collect(PARSER_XLSX, units)


def _shared_strings(archive) -> list[str]:
    """`sharedStrings.xml` 은 없을 수 있다(전부 inline string 인 파일)."""
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = _parse_entry(archive, "xl/sharedStrings.xml")
    return ["".join(n.text or "" for n in item.iter(f"{_S}t")) for item in root.findall(f"{_S}si")]


def _sheet_parts(archive) -> list[tuple[str, str]]:
    """(시트 이름, zip 안의 경로) 목록을 **워크북 순서대로**.

    이름은 `xl/workbook.xml` 에 있고 경로는 관계 파일에 있다. 관계를 안 따라가면
    `sheet1.xml` 이 첫 번째 시트라고 가정하게 되는데, 시트를 지웠다 만든 파일에서는
    그 가정이 깨진다 — 그러면 **인용이 다른 시트를 가리킨다.**
    """
    names = archive.namelist()
    if "xl/workbook.xml" not in names:
        return _fallback_sheets(names)
    book = _parse_entry(archive, "xl/workbook.xml")
    rels: dict[str, str] = {}
    if "xl/_rels/workbook.xml.rels" in names:
        rel_root = _parse_entry(archive, "xl/_rels/workbook.xml.rels")
        for rel in rel_root.iter(f"{_PKG_R}Relationship"):
            rels[rel.get("Id") or ""] = rel.get("Target") or ""
    out: list[tuple[str, str]] = []
    for sheet in book.iter(f"{_S}sheet"):
        title = (sheet.get("name") or "").strip() or "시트"
        target = rels.get(sheet.get(f"{_R}id") or "", "")
        part = _normalize_target(target)
        if part in names:
            out.append((title, part))
    return out or _fallback_sheets(names)


def _normalize_target(target: str) -> str:
    target = (target or "").lstrip("/")
    if not target:
        return ""
    if target.startswith("xl/"):
        return target
    return f"xl/{target}"


def _fallback_sheets(names) -> list[tuple[str, str]]:
    parts = sorted(n for n in names if n.startswith("xl/worksheets/") and n.endswith(".xml"))
    return [(Path(part).stem, part) for part in parts]


def _sheet_text(archive, part: str, shared: list[str]) -> tuple[str, str]:
    root = _parse_entry(archive, part)
    lines: list[str] = []
    min_col = max_col = None
    min_row = max_row = None
    for count, row in enumerate(root.iter(f"{_S}row")):
        if count >= MAX_SHEET_ROWS:
            break
        cells: list[str] = []
        for cell in row.findall(f"{_S}c"):
            value = _cell_value(cell, shared)
            if not value:
                continue
            cells.append(value)
            column, number = _split_ref(cell.get("r") or "")
            if column is not None:
                min_col = column if min_col is None else min(min_col, column)
                max_col = column if max_col is None else max(max_col, column)
            if number is not None:
                min_row = number if min_row is None else min(min_row, number)
                max_row = number if max_row is None else max(max_row, number)
        if cells:
            # 탭으로 잇는다. 빈 줄로 이으면 한 행이 여러 줄이 되어 chunk 경계가 흐려진다.
            lines.append("\t".join(cells))
    if min_col is None or min_row is None:
        return "\n".join(lines), ""
    ref = f"{_column_name(min_col)}{min_row}:{_column_name(max_col)}{max_row}"
    return "\n".join(lines), ref


def _cell_value(cell, shared: list[str]) -> str:
    kind = cell.get("t") or ""
    if kind == "s":
        node = cell.find(f"{_S}v")
        try:
            return shared[int((node.text or "0").strip())].strip() if node is not None else ""
        except (ValueError, IndexError):
            return ""
    if kind == "inlineStr":
        return "".join(n.text or "" for n in cell.iter(f"{_S}t")).strip()
    node = cell.find(f"{_S}v")
    return (node.text or "").strip() if node is not None else ""


def _split_ref(ref: str) -> tuple[int | None, int | None]:
    match = _CELL_REF_RE.match((ref or "").strip().upper())
    if not match:
        return None, None
    letters, digits = match.groups()
    column = 0
    for char in letters:
        column = column * 26 + (ord(char) - 64)
    return column, int(digits)


def _column_name(column: int | None) -> str:
    if not column or column < 1:
        return "A"
    out = ""
    while column > 0:
        column, rest = divmod(column - 1, 26)
        out = chr(65 + rest) + out
    return out


# ── zip 다루기 ───────────────────────────────────────────────────────────────


def _open_zip(path: Path) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise OoxmlError("파일을 열지 못했습니다.") from exc


def _parse_entry(archive: zipfile.ZipFile, name: str):
    try:
        info = archive.getinfo(name)
    except KeyError as exc:
        raise OoxmlError("문서 구조가 예상과 다릅니다.") from exc
    if info.file_size > MAX_ENTRY_BYTES:
        # 헤더 값이라 거짓일 수 있다. 그래서 아래 `read` 에도 상한을 건다 — 두 겹이다.
        raise OoxmlError("문서 안의 조각이 너무 큽니다.")
    try:
        with archive.open(info) as stream:
            data = stream.read(MAX_ENTRY_BYTES + 1)
    except (zipfile.BadZipFile, OSError) as exc:
        raise OoxmlError("문서 안의 조각을 읽지 못했습니다.") from exc
    if len(data) > MAX_ENTRY_BYTES:
        raise OoxmlError("문서 안의 조각이 너무 큽니다.")
    try:
        return ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise OoxmlError("문서 구조를 해석하지 못했습니다.") from exc


def _read_xml(path: Path, name: str):
    with _open_zip(path) as archive:
        return _parse_entry(archive, name)
