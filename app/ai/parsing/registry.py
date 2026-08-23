"""형식 → 파서. **판정된 형식만 믿는다.**

확장자도, 사용자가 보낸 Content-Type 도 안 본다. `files.mime_type` 은 S8 의
`sniff_media_type` 이 **내용을 보고** 판정해 저장한 값이다(D-199). 여기서 다시
판정하지 않는 이유는 그때와 같다 — 판정기가 두 벌이 되면 한쪽만 아는 형식이 생기고,
그 차이는 「어떤 화면에서는 되는데 어떤 화면에서는 안 된다」로만 드러난다.

이미지 첨부에 파서가 없는 것은 **결함이 아니다.** OCR 을 도입하지 않기로 했고
(INVENTORY 06), 그래서 그림에서 글자를 못 뽑는 것이 정상이다. `unsupported` 는
「못 했다」가 아니라 「안 한다」이고, 색인 상태도 그것을 실패로 세지 않는다.
"""

from __future__ import annotations

from pathlib import Path

from app.ai.parsing import ooxml, pdf, plain
from app.ai.parsing.base import PARSE_UNSUPPORTED, ParseResult, failure

MIME_PDF = "application/pdf"
MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MIME_PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
MIME_TEXT = "text/plain"

#: 판정된 형식 → 파서 함수. 여기 없는 형식은 안 읽는다.
PARSERS = {
    MIME_PDF: pdf.parse,
    MIME_DOCX: ooxml.parse_docx,
    MIME_XLSX: ooxml.parse_xlsx,
    MIME_PPTX: ooxml.parse_pptx,
    MIME_TEXT: plain.parse,
}

#: 글자를 뽑을 수 있는 형식 전부. 「이 첨부가 색인 대상인가」를 묻는 자리가 이것 하나다.
PARSABLE_MEDIA_TYPES = frozenset(PARSERS)


def can_parse(mime_type: str) -> bool:
    return (mime_type or "") in PARSERS


def parse_file(path: Path, *, mime_type: str) -> ParseResult:
    """판정된 형식으로 파일 하나를 읽는다. **예외를 올리지 않는다.**"""
    parser = PARSERS.get(mime_type or "")
    if parser is None:
        return failure(PARSE_UNSUPPORTED, detail="글자를 뽑을 수 있는 형식이 아닙니다.")
    return parser(Path(path))
