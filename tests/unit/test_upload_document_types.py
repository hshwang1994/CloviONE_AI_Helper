"""판정기를 넓혔다 — **판정기는 여전히 하나다** (S8).

지식 문서 첨부는 이미지와 PDF 만으로 부족하다. 회의록에 붙는 것은 보통 문서와
스프레드시트다. 그런데 판정기를 새로 만들면 한쪽만 아는 형식이 생기고, 그 차이는
「어떤 화면에서는 되는데 어떤 화면에서는 안 된다」로만 드러난다.

그래서 `sniff_media_type` 하나를 넓히고, **무엇을 받을지는 네임스페이스가 좁힌다.**
이 파일이 지키는 것 둘:

  1. 옛 네임스페이스(게시판·채팅·티켓·프로필)의 답이 **한 글자도 안 바뀐다**
  2. 넓힌 쪽도 확장자나 선언된 형식을 안 믿는다 — 실제 바이트만 본다
"""

from __future__ import annotations

import io
import zipfile

import pytest

from app.core import uploads

pytestmark = pytest.mark.unit

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PDF = b"%PDF-1.7\n" + b"\x00" * 32


def _ooxml(entry: str) -> bytes:
    """그 계열의 **결정적인 항목 하나**를 담은 최소 zip."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr(entry, "<xml/>")
    return buf.getvalue()


DOCX = _ooxml("word/document.xml")
XLSX = _ooxml("xl/workbook.xml")
PPTX = _ooxml("ppt/presentation.xml")


# ── 옛 계약은 그대로다 ───────────────────────────────────────────────────────


@pytest.mark.parametrize("data,expected", [
    (PNG, "image/png"),
    (b"\xff\xd8\xff\xe0" + b"\x00" * 12, "image/jpeg"),
    (b"GIF89a" + b"\x00" * 10, "image/gif"),
    (b"RIFF\x00\x00\x00\x00WEBP", "image/webp"),
    (PDF, "application/pdf"),
    (b"not an image at all", None),
])
def test_the_head_only_call_answers_exactly_as_before(data, expected):
    assert uploads.sniff_media_type(data[:16]) == expected


def test_without_the_full_content_an_office_file_is_still_unknown():
    """🔴 옛 네임스페이스가 조용히 넓어지면 안 된다. 게시판은 여전히 다섯 형식만 안다."""
    assert uploads.sniff_media_type(DOCX[:16]) is None
    assert uploads.sniff_media_type(b"plain text"[:16]) is None


def test_the_legacy_allow_list_did_not_grow():
    assert uploads.ALLOWED_MEDIA_TYPES == frozenset(
        {"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"}
    )


# ── 넓힌 쪽 ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("data,expected", [
    (DOCX, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    (XLSX, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    (PPTX, "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
])
def test_office_files_are_told_apart_by_what_is_actually_inside(data, expected):
    assert uploads.sniff_media_type(data[:16], full=data) == expected


def test_a_plain_zip_is_named_as_a_zip_not_as_an_office_file():
    """모르는 것을 「모른다」가 아니라 정확한 이름으로 부른다 — 그래야 거절 사유가
    「허용되지 않은 형식」으로 정확히 나간다."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("hello.txt", "hi")
    assert uploads.sniff_media_type(buf.getvalue()[:16], full=buf.getvalue()) == "application/zip"


def test_a_zip_is_not_accepted_as_a_document_attachment():
    """안에 무엇이 들었는지 서버가 판정할 수 없는데 받으면, 「판정된 형식만 신뢰한다」는
    원칙이 그 한 줄에서 깨진다."""
    assert "application/zip" not in uploads.DOCUMENT_MEDIA_TYPES


def test_a_file_that_claims_to_be_docx_gets_judged_by_its_bytes():
    """확장자도 선언된 형식도 안 믿는다. **판정된 이름이 그 파일의 이름이다.**

    글자만 든 파일이라면 `text/plain` 이 맞는 답이고(그것도 받는 형식이다), 바이너리
    쓰레기라면 아무 이름도 없다 — `.docx` 라고 부른 사실은 어느 쪽에도 안 쓰인다.
    """
    text_named_docx = b"this is not a zip at all, but I called it report.docx"
    assert uploads.sniff_media_type(text_named_docx[:16], full=text_named_docx) == "text/plain"

    binary_named_docx = b"\x01\x02\x03\x04 report.docx \xff\xfe"
    assert uploads.sniff_media_type(binary_named_docx[:16], full=binary_named_docx) is None


def test_a_broken_zip_does_not_crash_the_sniffer():
    broken = b"PK\x03\x04" + b"\x00" * 40
    assert uploads.sniff_media_type(broken[:16], full=broken) is None


# ── 평문 ─────────────────────────────────────────────────────────────────────


def test_utf8_text_is_plain_text():
    data = "회의록\n1. 안건\t확인\n".encode("utf-8")
    assert uploads.sniff_media_type(data[:16], full=data) == "text/plain"


def test_a_byte_order_mark_does_not_confuse_the_judgement():
    """윈도우 메모장이 붙인다. 이걸 못 읽으면 사용자는 「메모장으로 저장하면 안 된다」를
    스스로 알아내야 한다."""
    data = b"\xef\xbb\xbf" + "제목\n".encode("utf-8")
    assert uploads.sniff_media_type(data[:16], full=data) == "text/plain"


@pytest.mark.parametrize("data", [
    b"binary\x00payload",           # 널바이트
    b"\x1b[31mescape codes\x1b[0m",  # 제어문자
    "한글".encode("euc-kr"),         # UTF-8 이 아니다
    b"",                            # 빈 파일
])
def test_things_that_are_not_text_are_not_called_text(data):
    assert uploads.sniff_media_type(data[:16], full=data) != "text/plain"


# ── 확장자 ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("media,ext", [
    ("image/png", ".png"),
    ("application/pdf", ".pdf"),
    ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
    ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    ("text/plain", ".txt"),
])
def test_the_stored_extension_comes_from_the_judged_type(media, ext):
    assert uploads.extension_for(media) == ext


def test_an_unknown_type_has_no_extension():
    assert uploads.extension_for("application/x-made-up") == ""


def test_only_images_and_pdf_are_shown_inline():
    """`nosniff` 가 실행을 막지만, 「받아서 여는 것」과 「탭 안에서 열리는 것」은
    사용자가 느끼는 위험이 다르다."""
    assert "application/pdf" in uploads.INLINE_MEDIA_TYPES
    assert "text/plain" not in uploads.INLINE_MEDIA_TYPES
    assert not (uploads.INLINE_MEDIA_TYPES - uploads.DOCUMENT_MEDIA_TYPES)
