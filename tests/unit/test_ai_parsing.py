"""파일 → 글 + **인용 앵커** (S9).

## 왜 파일을 손으로 만드는가

`python-docx`·`python-pptx`·`openpyxl` 을 안 쓰기로 했으므로(`app/ai/parsing/ooxml.py`
머리말) 시험도 그것으로 파일을 만들 수 없다. 그래서 zip 과 XML 을 직접 만든다 —
그 편이 오히려 정직하다: 파서가 **실제 OOXML 모양**을 읽는지를 보는 것이지,
같은 라이브러리가 쓰고 읽는 왕복을 보는 것이 아니다.

## 앵커가 이 파일의 주인공이다

글자가 나오는 것보다 「그 글자가 어디 있었는가」가 더 중요하다. 인용이 틀린 자리를
가리키면 사용자는 답을 확인할 수 없고, 확인할 수 없는 답은 못 쓴다.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from app.ai.models import ANCHOR_PAGE, ANCHOR_SECTION, ANCHOR_SHEET, ANCHOR_SLIDE, ANCHOR_TEXT
from app.ai.parsing import ooxml, pdf, plain
from app.ai.parsing import registry as parsers
from app.ai.parsing.base import PARSE_EMPTY, PARSE_FAILED, PARSE_OK, PARSE_UNSUPPORTED

pytestmark = pytest.mark.unit

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
_S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_R = "http://schemas.openxmlformats.org/package/2006/relationships"


def _zip(entries: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name, body in entries.items():
            archive.writestr(name, body)
    return buf.getvalue()


def _write(tmp_path, name: str, data: bytes):
    path = tmp_path / name
    path.write_bytes(data)
    return path


# ── DOCX ─────────────────────────────────────────────────────────────────────


def _docx(paragraphs) -> bytes:
    body = []
    for style, text in paragraphs:
        style_xml = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        body.append(f"<w:p>{style_xml}<w:r><w:t>{text}</w:t></w:r></w:p>")
    return _zip({
        "[Content_Types].xml": "<Types/>",
        "word/document.xml": (
            f'<w:document xmlns:w="{_W}"><w:body>{"".join(body)}</w:body></w:document>'
        ),
    })


def test_docx_opens_a_new_section_at_every_heading(tmp_path):
    path = _write(tmp_path, "a.docx", _docx([
        ("Heading1", "1. 배경"),
        (None, "이 문서는 배경을 설명합니다."),
        ("Heading2", "2. 결정"),
        (None, "결정은 이렇습니다."),
    ]))
    result = ooxml.parse_docx(path)
    assert result.status == PARSE_OK
    assert [u.anchor_kind for u in result.units] == [ANCHOR_SECTION, ANCHOR_SECTION]
    assert [u.anchor_label for u in result.units] == ["1. 배경", "2. 결정"]
    assert "배경을 설명합니다" in result.units[0].text
    assert "배경을 설명합니다" not in result.units[1].text


def test_docx_keeps_the_heading_text_inside_its_section(tmp_path):
    """제목이 본문과 떨어지면 「이 절이 무엇에 관한 것인가」가 벡터에서 사라진다."""
    path = _write(tmp_path, "a.docx", _docx([("제목 1", "보안 정책"), (None, "본문입니다.")]))
    result = ooxml.parse_docx(path)
    assert result.units[0].text.startswith("보안 정책")


def test_docx_reads_paragraphs_before_the_first_heading(tmp_path):
    """제목 없이 시작하는 문서를 통째로 버리면 안 된다."""
    path = _write(tmp_path, "a.docx", _docx([(None, "제목 없는 첫 문단입니다.")]))
    result = ooxml.parse_docx(path)
    assert result.status == PARSE_OK
    assert "제목 없는 첫 문단" in result.units[0].text


def test_a_docx_with_no_text_is_empty_not_failed(tmp_path):
    """「빈 파일」과 「못 읽었다」는 다른 사실이다."""
    path = _write(tmp_path, "a.docx", _docx([]))
    assert ooxml.parse_docx(path).status == PARSE_EMPTY


def test_a_zip_that_is_not_a_docx_fails_with_a_reason(tmp_path):
    path = _write(tmp_path, "a.docx", _zip({"other.xml": "<x/>"}))
    result = ooxml.parse_docx(path)
    assert result.status == PARSE_FAILED
    assert result.detail


def test_a_file_that_is_not_a_zip_fails(tmp_path):
    path = _write(tmp_path, "a.docx", b"not a zip at all")
    assert ooxml.parse_docx(path).status == PARSE_FAILED


# ── PPTX ─────────────────────────────────────────────────────────────────────


def _pptx(slides) -> bytes:
    entries = {"[Content_Types].xml": "<Types/>"}
    for index, texts in enumerate(slides, start=1):
        runs = "".join(f"<a:p><a:r><a:t>{t}</a:t></a:r></a:p>" for t in texts)
        entries[f"ppt/slides/slide{index}.xml"] = (
            f'<p:sld xmlns:a="{_A}" xmlns:p="{_P}">'
            f"<p:cSld><p:spTree>{runs}</p:spTree></p:cSld></p:sld>"
        )
    return _zip(entries)


def test_pptx_gives_one_unit_per_slide_in_slide_order(tmp_path):
    """`slide10.xml` 이 `slide2.xml` 보다 앞에 오면 인용이 다른 슬라이드를 가리킨다."""
    slides = [[f"{i}번 슬라이드 내용입니다."] for i in range(1, 12)]
    path = _write(tmp_path, "a.pptx", _pptx(slides))
    result = ooxml.parse_pptx(path)
    assert result.status == PARSE_OK
    assert [u.anchor_ref for u in result.units] == [str(i) for i in range(1, 12)]
    assert result.units[9].anchor_kind == ANCHOR_SLIDE
    assert "10번 슬라이드" in result.units[9].text


def test_pptx_joins_every_text_run_on_a_slide(tmp_path):
    path = _write(tmp_path, "a.pptx", _pptx([["제목입니다", "본문 첫 줄", "본문 둘째 줄"]]))
    text = ooxml.parse_pptx(path).units[0].text
    assert "제목입니다" in text and "본문 둘째 줄" in text


# ── XLSX ─────────────────────────────────────────────────────────────────────


def _xlsx(sheets, *, shared=None, with_rels=True) -> bytes:
    shared = shared or []
    entries = {"[Content_Types].xml": "<Types/>"}
    sheet_tags, rel_tags = [], []
    for index, (title, rows) in enumerate(sheets, start=1):
        rid = f"rId{index}"
        sheet_tags.append(f'<sheet name="{title}" sheetId="{index}" r:id="{rid}"/>')
        rel_tags.append(
            f'<Relationship Id="{rid}" Target="worksheets/sheet{index}.xml"/>'
        )
        body = []
        for row_number, cells in rows:
            cell_xml = "".join(
                f'<c r="{ref}"{f" t={chr(34)}{kind}{chr(34)}" if kind else ""}>'
                f"<v>{value}</v></c>"
                for ref, kind, value in cells
            )
            body.append(f'<row r="{row_number}">{cell_xml}</row>')
        entries[f"xl/worksheets/sheet{index}.xml"] = (
            f'<worksheet xmlns="{_S}"><sheetData>{"".join(body)}</sheetData></worksheet>'
        )
    entries["xl/workbook.xml"] = (
        f'<workbook xmlns="{_S}" xmlns:r="{_R}"><sheets>{"".join(sheet_tags)}'
        "</sheets></workbook>"
    )
    if with_rels:
        entries["xl/_rels/workbook.xml.rels"] = (
            f'<Relationships xmlns="{_PKG_R}">{"".join(rel_tags)}</Relationships>'
        )
    if shared:
        items = "".join(f"<si><t>{s}</t></si>" for s in shared)
        entries["xl/sharedStrings.xml"] = f'<sst xmlns="{_S}">{items}</sst>'
    return _zip(entries)


def test_xlsx_anchors_to_the_sheet_and_the_used_range(tmp_path):
    data = _xlsx(
        [("실적", [
            (2, [("B2", "s", 0), ("D2", "s", 1)]),
            (5, [("C5", None, "42")]),
        ])],
        shared=["항목", "금액"],
    )
    result = ooxml.parse_xlsx(_write(tmp_path, "a.xlsx", data))
    assert result.status == PARSE_OK
    unit = result.units[0]
    assert unit.anchor_kind == ANCHOR_SHEET
    assert unit.anchor_ref == "실적!B2:D5"
    assert unit.anchor_label == "실적"
    assert "항목" in unit.text and "42" in unit.text


def test_xlsx_follows_the_relationship_instead_of_guessing_the_file_name(tmp_path):
    """시트를 지웠다 만든 파일에서는 `sheet1.xml` 이 첫 시트가 아니다. 관계를 안
    따라가면 **인용이 다른 시트를 가리킨다.**"""
    entries = {
        "[Content_Types].xml": "<Types/>",
        "xl/workbook.xml": (
            f'<workbook xmlns="{_S}" xmlns:r="{_R}"><sheets>'
            '<sheet name="두번째" sheetId="1" r:id="rIdB"/>'
            '<sheet name="첫번째" sheetId="2" r:id="rIdA"/>'
            "</sheets></workbook>"
        ),
        "xl/_rels/workbook.xml.rels": (
            f'<Relationships xmlns="{_PKG_R}">'
            '<Relationship Id="rIdA" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rIdB" Target="worksheets/sheet2.xml"/>'
            "</Relationships>"
        ),
        "xl/worksheets/sheet1.xml": (
            f'<worksheet xmlns="{_S}"><sheetData><row r="1">'
            '<c r="A1"><v>A시트값</v></c></row></sheetData></worksheet>'
        ),
        "xl/worksheets/sheet2.xml": (
            f'<worksheet xmlns="{_S}"><sheetData><row r="1">'
            '<c r="A1"><v>B시트값</v></c></row></sheetData></worksheet>'
        ),
    }
    result = ooxml.parse_xlsx(_write(tmp_path, "a.xlsx", _zip(entries)))
    assert [u.anchor_label for u in result.units] == ["두번째", "첫번째"]
    assert result.units[0].text == "B시트값"


def test_xlsx_reads_inline_strings_too(tmp_path):
    entries = {
        "[Content_Types].xml": "<Types/>",
        "xl/workbook.xml": (
            f'<workbook xmlns="{_S}" xmlns:r="{_R}"><sheets>'
            '<sheet name="시트" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            f'<Relationships xmlns="{_PKG_R}">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>'
        ),
        "xl/worksheets/sheet1.xml": (
            f'<worksheet xmlns="{_S}"><sheetData><row r="1">'
            '<c r="A1" t="inlineStr"><is><t>안쪽 문자열</t></is></c>'
            "</row></sheetData></worksheet>"
        ),
    }
    result = ooxml.parse_xlsx(_write(tmp_path, "a.xlsx", _zip(entries)))
    assert "안쪽 문자열" in result.units[0].text


def test_a_column_letter_past_z_is_handled(tmp_path):
    """`AA` 를 `A` 로 읽으면 범위가 틀리고, 그 범위가 곧 인용이다."""
    data = _xlsx([("넓은시트", [(1, [("A1", None, "왼쪽"), ("AB1", None, "오른쪽")])])])
    result = ooxml.parse_xlsx(_write(tmp_path, "a.xlsx", data))
    assert result.units[0].anchor_ref == "넓은시트!A1:AB1"


# ── PDF ──────────────────────────────────────────────────────────────────────


def _pdf(pages: list[str]) -> bytes:
    """손으로 만든 최소 PDF. 쪽마다 글 한 줄이 들어 있다.

    라이브러리로 쓰고 라이브러리로 읽으면 **그 라이브러리의 왕복**을 보는 것이지
    파서가 진짜 PDF 를 읽는지를 보는 것이 아니다.
    """
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids: list[int] = []
    contents: list[int] = []
    for text in pages:
        stream = f"BT /F1 24 Tf 72 700 Td ({text}) Tj ET".encode("ascii")
        contents.append(add(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream)))
    pages_id = len(objects) + len(pages) + 1
    for content_id in contents:
        page_ids.append(add(
            b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
            % (pages_id, font, content_id)
        ))
    kids = b" ".join(b"%d 0 R" % pid for pid in page_ids)
    real_pages_id = add(
        b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(page_ids))
    )
    assert real_pages_id == pages_id
    catalog_id = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % index + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1, catalog_id, xref_at
    )
    return bytes(out)


def test_pdf_gives_one_unit_per_page_with_a_page_anchor(tmp_path):
    path = _write(tmp_path, "a.pdf", _pdf(["First page text", "Second page text"]))
    result = pdf.parse(path)
    assert result.status == PARSE_OK
    assert [u.anchor_kind for u in result.units] == [ANCHOR_PAGE, ANCHOR_PAGE]
    assert [u.anchor_ref for u in result.units] == ["1", "2"]
    assert [u.anchor_label for u in result.units] == ["1쪽", "2쪽"]
    assert "First page" in result.units[0].text
    assert "Second page" in result.units[1].text


def test_a_broken_pdf_fails_with_a_reason_instead_of_raising(tmp_path):
    path = _write(tmp_path, "a.pdf", "%PDF-1.4\n쓰레기입니다\n".encode("utf-8"))
    result = pdf.parse(path)
    assert result.status in (PARSE_FAILED, PARSE_EMPTY)


# ── 평문 ─────────────────────────────────────────────────────────────────────


def test_plain_text_is_cut_into_character_segments(tmp_path):
    path = _write(tmp_path, "a.txt", ("문장입니다. " * 900).encode("utf-8"))
    result = plain.parse(path)
    assert result.status == PARSE_OK
    assert len(result.units) > 1
    assert result.units[0].anchor_kind == ANCHOR_TEXT
    assert result.units[0].anchor_ref.startswith("0-")


def test_euc_kr_is_read_too(tmp_path):
    """사내 문서에 아직 EUC-KR 이 남아 있다."""
    path = _write(tmp_path, "a.txt", "한글 본문입니다.".encode("euc-kr"))
    result = plain.parse(path)
    assert result.status == PARSE_OK
    assert "한글 본문" in result.units[0].text


def test_bytes_that_are_not_text_fail(tmp_path):
    path = _write(tmp_path, "a.txt", bytes(range(200, 256)) * 40)
    assert plain.parse(path).status == PARSE_FAILED


# ── registry ─────────────────────────────────────────────────────────────────


def test_an_image_is_unsupported_not_failed(tmp_path):
    """OCR 을 도입하지 않기로 했다. 그림에서 글자를 못 뽑는 것이 정상이다."""
    path = _write(tmp_path, "a.png", b"\x89PNG\r\n\x1a\n")
    result = parsers.parse_file(path, mime_type="image/png")
    assert result.status == PARSE_UNSUPPORTED
    assert not parsers.can_parse("image/png")


def test_the_registry_covers_the_four_formats_the_plan_names():
    assert parsers.can_parse(parsers.MIME_PDF)
    assert parsers.can_parse(parsers.MIME_DOCX)
    assert parsers.can_parse(parsers.MIME_PPTX)
    assert parsers.can_parse(parsers.MIME_XLSX)


def test_the_registry_dispatches_by_the_sniffed_type_not_the_extension(tmp_path):
    """확장자를 믿으면 S8 이 세운 「판정된 형식만 신뢰한다」가 그 한 줄에서 깨진다."""
    path = _write(tmp_path, "실제는_pptx.docx", _pptx([["슬라이드 글입니다."]]))
    result = parsers.parse_file(path, mime_type=parsers.MIME_PPTX)
    assert result.status == PARSE_OK
    assert result.units[0].anchor_kind == ANCHOR_SLIDE


# ── 상한 ─────────────────────────────────────────────────────────────────────


def test_an_oversized_entry_is_refused_before_it_is_read(tmp_path):
    """헤더 값은 거짓일 수 있다. 그래서 읽는 쪽에도 상한이 있다 — 두 겹이다."""
    huge = "가" * (ooxml.MAX_ENTRY_BYTES // 3 + 10)
    entries = {
        "[Content_Types].xml": "<Types/>",
        "word/document.xml": f'<w:document xmlns:w="{_W}"><w:body>'
                             f"<w:p><w:r><w:t>{huge}</w:t></w:r></w:p></w:body></w:document>",
    }
    result = ooxml.parse_docx(_write(tmp_path, "a.docx", _zip(entries)))
    assert result.status == PARSE_FAILED
    assert "큽니다" in result.detail
