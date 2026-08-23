"""PDF → 쪽마다 글 하나 (`pypdf`).

## 왜 `pypdf` 인가

순수 파이썬이고(컴파일 의존 0) BSD 라이선스이며 폐쇄망 wheelhouse 에 그대로 들어간다.
PDF 의 글자 추출은 손으로 쓸 것이 못 된다 — 내용 스트림 연산자, 글꼴 인코딩, CMap 이
전부 얽혀 있고, 직접 쓰면 「글자가 나오긴 하는데 순서가 이상한」 결과가 조용히 나온다.

## OCR 을 안 한다

스캔 PDF 는 글자가 아니라 그림이다. 그때 이 파서는 **빈 결과**를 돌려주고, 그것은
결함이 아니라 사실이다(`PARSE_EMPTY`). OCR 은 도입하지 않기로 한 것이고
(INVENTORY 06), 도입한다면 그때 파서를 **하나 더** 붙인다.

## 암호가 걸린 PDF

`pypdf` 는 열리긴 하는데 글자가 안 나온다. 그것을 「빈 파일」로 접으면 운영자가
못 알아챈다 — 여기서 먼저 물어서 실패로 말한다.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.ai.models import ANCHOR_PAGE
from app.ai.parsing.base import (
    PARSE_FAILED,
    ParsedUnit,
    ParseResult,
    collect,
    failure,
)

logger = logging.getLogger("app.ai.parsing")

PARSER_NAME = "pdf"

#: 한 파일에서 읽는 쪽 수 상한. 넘으면 앞부분만 싣는다 — 1,000쪽 규격서 하나가
#: 색인 한 판을 통째로 잡아먹지 않게 한다.
MAX_PAGES = 500


def parse(path: Path) -> ParseResult:
    try:
        from pypdf import PdfReader
    except Exception:  # noqa: BLE001 - 런타임이 없는 설치도 있다
        logger.warning("pypdf 를 불러오지 못해 PDF 를 읽지 않는다")
        return failure(PARSE_FAILED, parser=PARSER_NAME, detail="PDF 읽기 도구가 없습니다.")

    try:
        reader = PdfReader(str(path))
        if getattr(reader, "is_encrypted", False):
            # 빈 결과로 접지 않는다. 「암호가 걸렸다」는 운영자가 고칠 수 있는 사실이다.
            return failure(
                PARSE_FAILED, parser=PARSER_NAME, detail="암호가 걸린 PDF 입니다."
            )
        pages = list(reader.pages)[:MAX_PAGES]
    except Exception:  # noqa: BLE001 - 깨진 파일 하나가 레인을 죽이지 않는다
        logger.exception("PDF 를 열지 못했다")
        return failure(PARSE_FAILED, parser=PARSER_NAME, detail="PDF 를 읽지 못했습니다.")

    units = []
    for number, page in enumerate(pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001 - 한 쪽이 깨져도 나머지는 읽는다
            logger.warning("PDF %d쪽을 읽지 못해 건너뛴다", number)
            continue
        units.append(
            ParsedUnit(
                anchor_kind=ANCHOR_PAGE,
                anchor_ref=str(number),
                anchor_label=f"{number}쪽",
                text=text,
                ordinal=number - 1,
            )
        )
    return collect(PARSER_NAME, units)
