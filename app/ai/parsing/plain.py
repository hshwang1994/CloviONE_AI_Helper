"""평문 → 문자 구간마다 글 하나.

평문에는 쪽도 슬라이드도 절도 없다. 그래서 앵커는 **문자 구간**이다(`0-1800`). 그것이
가리키는 자리가 흐릿한 것은 사실이고, 흐릿하다고 앵커를 안 다는 것보다는 낫다 —
「이 파일 어딘가」보다 「이 파일의 이 근처」가 확인하기 쉽다.

인코딩은 UTF-8 을 먼저 보고 안 되면 EUC-KR 을 본다. S8 의 판정기가 같은 순서를 쓴다
(`app/core/uploads.py::_sniff_text`) — 사내 문서에 아직 EUC-KR 이 남아 있다.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.ai.models import ANCHOR_TEXT
from app.ai.parsing.base import (
    MAX_TEXT_CHARS,
    PARSE_FAILED,
    ParsedUnit,
    ParseResult,
    collect,
    failure,
)

logger = logging.getLogger("app.ai.parsing")

PARSER_NAME = "text"

#: 앵커 하나가 담는 문자 수. chunk 크기와 같은 자리를 노린다 — 그래야 앵커와 chunk 가
#: 대체로 1:1 이 되어 인용이 정확해진다.
SEGMENT_CHARS = 1800

#: 읽어 들이는 바이트 상한. 첨부 상한(10MB)보다 넉넉할 이유가 없다.
MAX_BYTES = 10 * 1024 * 1024


def parse(path: Path) -> ParseResult:
    try:
        raw = Path(path).read_bytes()[:MAX_BYTES]
    except OSError:
        logger.exception("평문 파일을 읽지 못했다")
        return failure(PARSE_FAILED, parser=PARSER_NAME, detail="파일을 읽지 못했습니다.")
    text = _decode(raw)
    if text is None:
        return failure(
            PARSE_FAILED, parser=PARSER_NAME, detail="글자 인코딩을 알아보지 못했습니다."
        )
    units = []
    for start in range(0, min(len(text), MAX_TEXT_CHARS), SEGMENT_CHARS):
        segment = text[start:start + SEGMENT_CHARS]
        end = start + len(segment)
        units.append(
            ParsedUnit(
                anchor_kind=ANCHOR_TEXT,
                anchor_ref=f"{start}-{end}",
                anchor_label=f"{start:,}번째 글자부터",
                text=segment,
                ordinal=start // SEGMENT_CHARS,
            )
        )
    return collect(PARSER_NAME, units)


def _decode(raw: bytes) -> str | None:
    for encoding in ("utf-8-sig", "euc-kr"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None
