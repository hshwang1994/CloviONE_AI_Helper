"""파싱 결과의 모양 — **글과 그 글이 있던 자리**.

## 왜 「글」만으로는 부족한가

인용이 「이 문서 어딘가」를 가리키면 사용자는 그것을 확인할 수 없다. 답변이 맞는지
아닌지를 사람이 직접 못 보면 그 답변은 못 쓴다. 그래서 파서는 글과 함께 **그 글이
있던 자리**를 돌려준다 — PDF 는 쪽, PPTX 는 슬라이드, DOCX 는 절, XLSX 는 시트와 범위다.

## 실패를 값으로 돌려준다

못 읽는 파일 하나가 색인 레인을 죽이면 안 된다. 그리고 **「빈 파일」과 「못 읽었다」는
다른 사실이다** — 앞은 정상이고 뒤는 운영자가 볼 일이다. 그래서 상태를 나눠 둔다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: 파싱 상태.
PARSE_OK = "ok"
#: 그 형식을 읽는 파서가 없다. 이미지 첨부가 여기다 — 결함이 아니다.
PARSE_UNSUPPORTED = "unsupported"
#: 파일이 깨졌거나 암호가 걸렸다. 운영자가 볼 일이다.
PARSE_FAILED = "failed"
#: 읽었는데 글자가 없다. 스캔 PDF 가 여기다(OCR 은 도입하지 않는다 — INVENTORY 06).
PARSE_EMPTY = "empty"

#: 한 파일에서 뽑는 글자 수 상한. 넘으면 앞부분만 싣고 그 사실을 말한다.
#: 10MB 짜리 스프레드시트 하나가 임베딩 예산을 통째로 태우지 않게 한다.
MAX_TEXT_CHARS = 400_000

#: 앵커 하나가 담는 글자 수 상한. 시트 한 장이 20만 자면 chunk 하나가 그만큼 커지는
#: 것이 아니라 여기서 먼저 잘린다.
MAX_UNIT_CHARS = 60_000


@dataclass(frozen=True)
class ParsedUnit:
    """파일 안의 한 자리에서 나온 글.

    `ordinal` 은 파일 안의 순서다. 앵커 문자열(`"12"`)로 정렬하면 10 이 2 보다 앞에 온다.
    """

    anchor_kind: str
    anchor_ref: str
    anchor_label: str
    text: str
    ordinal: int


@dataclass(frozen=True)
class ParseResult:
    """파일 하나의 파싱 결과 전부."""

    status: str
    #: 어느 파서가 읽었는가. 사람이 로그에서 읽는 이름이다.
    parser: str = ""
    units: tuple[ParsedUnit, ...] = field(default_factory=tuple)
    truncated: bool = False
    #: 실패 이유 한 줄. **경로와 파일 이름을 안 넣는다**(OPS-05 — 로그와 화면 양쪽에
    #: 같은 문자열이 갈 수 있다).
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == PARSE_OK

    @property
    def text_length(self) -> int:
        return sum(len(u.text) for u in self.units)


def failure(status: str, *, parser: str = "", detail: str = "") -> ParseResult:
    return ParseResult(status=status, parser=parser, detail=detail)


def collect(parser: str, units) -> ParseResult:
    """단위 목록 → 결과. **빈 단위를 버리고 상한을 여기서 한 번에 건다.**

    상한을 파서마다 따로 걸면 하나가 빠뜨리고, 빠뜨린 그 파서가 언젠가 10MB 짜리
    파일을 만난다.
    """
    kept: list[ParsedUnit] = []
    total = 0
    truncated = False
    for unit in units:
        text = _squeeze(unit.text)
        if not text:
            continue
        if len(text) > MAX_UNIT_CHARS:
            text = text[:MAX_UNIT_CHARS]
            truncated = True
        if total + len(text) > MAX_TEXT_CHARS:
            room = MAX_TEXT_CHARS - total
            truncated = True
            if room <= 0:
                break
            text = text[:room]
        total += len(text)
        kept.append(
            ParsedUnit(
                anchor_kind=unit.anchor_kind,
                anchor_ref=unit.anchor_ref,
                anchor_label=unit.anchor_label,
                text=text,
                ordinal=len(kept),
            )
        )
    if not kept:
        return ParseResult(status=PARSE_EMPTY, parser=parser)
    return ParseResult(
        status=PARSE_OK, parser=parser, units=tuple(kept), truncated=truncated
    )


def _squeeze(value) -> str:
    """공백을 정리한다. 파서마다 다른 모양의 공백을 내놓아 그대로 두면 같은 글이
    다른 지문을 갖는다 — 그러면 「안 바뀐 chunk 는 다시 임베딩하지 않는다」가 안 먹는다."""
    if not isinstance(value, str):
        return ""
    lines = [line.strip() for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    out: list[str] = []
    blank = False
    for line in lines:
        if not line:
            blank = True
            continue
        if out and blank:
            out.append("")
        blank = False
        out.append(line)
    return "\n".join(out).strip()
