"""글 + 앵커 → chunk. **앵커를 넘어 합치지 않는다.**

## 이 규칙 하나가 인용을 지킨다

3쪽 끝과 4쪽 처음을 한 chunk 로 합치면 그 chunk 의 인용은 3쪽도 4쪽도 아니다. 검색은
잘 되는데 **사용자가 눌러서 확인하면 그 자리에 그 문장이 없다.** 그런 인용은 없느니만
못하다 — 답이 틀렸을 때 사람이 알아챌 수 있게 하는 것이 인용의 존재 이유이기 때문이다.

그래서 chunk 는 항상 앵커 **안**에서 만들어진다. 짧은 블록 여럿을 합치는 것도 같은
앵커일 때만 한다.

## 크기를 왜 그렇게 잡는가

임베딩 모델이 512 토큰에서 자른다(`catalog.E5_SMALL.max_tokens`). 그 위는 **버려지는데
오류가 안 난다** — chunk 를 크게 잡을수록 뒷부분이 조용히 사라진다.

한국어는 XLM-R 계열 토크나이저에서 대략 **1토큰 = 1.5자**다. 512토큰이면 약 780자다.
영어는 1토큰 ≈ 4자라 같은 512토큰에 2,000자가 들어가지만, **둘을 나눠 재지 않는다** —
한 문서에 한국어와 영어가 섞이는 것이 보통이고, 짧게 잡아 손해 보는 것은 chunk 수뿐이다.
잘려서 잃는 것과 비교할 값이 아니다.

## 겹침을 왜 두는가

문장이 chunk 경계에 걸치면 그 문장은 어느 쪽에서도 온전하지 않다. 앞 chunk 의 끝
몇 줄을 다음 chunk 앞에 다시 싣는다. 대가는 인덱스가 대략 15% 커지는 것이고, 얻는
것은 경계에 걸친 문장이 최소 한 번은 온전히 실린다는 것이다.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

#: chunk 하나가 노리는 글자 수. 위 문단의 780자에서 여유를 뒀다.
TARGET_CHARS = 700
#: 이 위로는 자른다. 넘으면 임베딩이 뒷부분을 버린다.
MAX_CHARS = 1000
#: 앞 chunk 에서 다시 싣는 글자 수.
OVERLAP_CHARS = 120
#: 이보다 짧은 조각은 버린다. **잡아내려는 것은 「쪽 번호만 있는 쪽」이다** — `- 3 -`,
#: `Page 4 of 20`, 구분선. 그런 chunk 는 검색에서 쓸모가 없고 임베딩 예산만 쓴다.
#:
#: 크게 잡으면 안 된다. 제목 한 줄짜리 슬라이드(`2026년 사업 계획` — 11자)는 **진짜
#: 내용**이고, 그것을 버리면 그 슬라이드는 검색에서 영영 안 나온다. 그 사실은 아무 데도
#: 안 남는다. 그래서 값을 낮게 잡는다 — 「사람이 쓴 문장으로 보기 어려운 길이」다.
#: 그 대가로 `Page 4 of 20` 같은 조각 몇 개는 통과한다. 잃는 쪽이 훨씬 크다.
MIN_CHARS = 8

#: 문장 끝으로 볼 자리. 한국어 종결(`다.` `요.` `까?`)과 서양 문장부호를 함께 본다.
_SENTENCE_END = re.compile(r"(?<=[.!?。？！])\s+|(?<=[다요])\.\s+|\n{2,}")
#: 문장으로 못 끊을 때의 다음 후보.
_LINE_BREAK = re.compile(r"\n")


@dataclass(frozen=True)
class Chunk:
    """저장 직전의 chunk 하나. DB 컬럼과 같은 어휘를 쓴다."""

    anchor_kind: str
    anchor_ref: str
    anchor_label: str
    text: str
    ordinal: int

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    @property
    def token_estimate(self) -> int:
        return estimate_tokens(self.text)


def estimate_tokens(text: str) -> int:
    """토큰 수의 **추정**이다. 진짜 값은 토크나이저만 안다.

    쓰는 자리는 하나 — 「이 chunk 가 상한 근처인가」를 사람이 로그에서 읽는 것이다.
    판정에 쓰지 않는다. 판정은 토크나이저가 자르는 것으로 이미 끝나 있다.
    """
    if not text:
        return 0
    hangul = sum(1 for ch in text if "가" <= ch <= "힣")
    rest = len(text) - hangul
    return int(hangul / 1.5 + rest / 4) + 1


def chunk_units(units, *, merge_anchors: bool = False) -> tuple[Chunk, ...]:
    """`ParsedUnit`(또는 같은 모양) 목록 → chunk 목록.

    입력은 문서 순서대로 들어온다고 본다. 순서를 여기서 다시 정하지 않는다 —
    파서가 문서 순서를 아는 유일한 자리다.

    ## `merge_anchors` 가 무엇을 가르는가

    **파일은 `False` 다.** 3쪽과 4쪽은 사용자가 각각 찾아가는 **다른 자리**다. 둘을
    한 chunk 로 합치면 그 인용은 3쪽도 4쪽도 아니고, 눌러서 확인하면 그 자리에 그
    문장이 없다.

    **문서 본문은 `True` 다.** 블록은 같은 화면 안의 이어진 문단이고, 앵커는 그 화면을
    그 위치로 스크롤한다. 한 줄짜리 문단마다 chunk 를 만들면 뜻이 없는 조각 수백 개가
    생기고 임베딩 예산만 쓴다. 합칠 때 앵커는 **첫 블록**의 것이다 — 「이 chunk 는
    여기서 시작한다」는 참말이다.
    """
    out: list[Chunk] = []
    carry: list = []

    def key_of(unit):
        return (unit.anchor_kind, unit.anchor_ref, unit.anchor_label)

    for unit in units:
        if carry and not merge_anchors and key_of(carry[0]) != key_of(unit):
            _emit(out, carry)
            carry = []
        carry.append(unit)
        if len("\n".join(u.text for u in carry)) >= TARGET_CHARS:
            _emit(out, carry)
            carry = []
    if carry:
        _emit(out, carry)
    return tuple(out)


def _emit(out: list[Chunk], units) -> None:
    first = units[0]
    body = "\n".join(u.text for u in units).strip()
    if not body:
        return
    for piece in split_text(body):
        if len(piece) < MIN_CHARS:
            # 쪽 번호만 있는 쪽(`- 3 -`)이 여기 걸린다. 그런 chunk 는 검색에서 쓸모가
            # 없고 임베딩 예산만 쓴다. **버렸다는 사실이 어디에도 안 남는 것**이
            # 걸리지만, 남길 값이 없는 조각이라 남길 자리도 없다.
            continue
        out.append(
            Chunk(
                anchor_kind=first.anchor_kind,
                anchor_ref=first.anchor_ref,
                anchor_label=first.anchor_label,
                text=piece,
                ordinal=len(out),
            )
        )


def split_text(text: str) -> tuple[str, ...]:
    """긴 글 하나 → 조각 여럿. **문장 → 줄 → 글자** 순으로 끊을 자리를 찾는다.

    글자 단위로 바로 자르지 않는 이유: 단어 중간에서 끊긴 조각은 그 자체로 뜻이 없고,
    임베딩이 그것을 그대로 벡터로 만든다. 검색이 이상해지는데 원인이 안 보인다.
    """
    text = text.strip()
    if not text:
        return ()
    if len(text) <= MAX_CHARS:
        return (text,)

    pieces: list[str] = []
    buffer = ""
    for sentence in _sentences(text):
        if not buffer:
            buffer = sentence
            continue
        if len(buffer) + 1 + len(sentence) <= TARGET_CHARS:
            buffer = f"{buffer} {sentence}" if not buffer.endswith("\n") else buffer + sentence
            continue
        pieces.append(buffer.strip())
        buffer = _overlap(buffer) + sentence
    if buffer.strip():
        pieces.append(buffer.strip())

    # 문장으로 못 끊은 조각(한 문장이 통째로 상한을 넘는 경우)만 글자로 자른다.
    out: list[str] = []
    for piece in pieces:
        if len(piece) <= MAX_CHARS:
            out.append(piece)
            continue
        for start in range(0, len(piece), TARGET_CHARS):
            part = piece[start:start + TARGET_CHARS].strip()
            if part:
                out.append(part)
    return tuple(out)


def _sentences(text: str):
    for block in _SENTENCE_END.split(text):
        block = (block or "").strip()
        if not block:
            continue
        if len(block) <= MAX_CHARS:
            yield block
            continue
        # 한 「문장」이 상한을 넘으면 줄로 한 번 더 끊는다. 목록이나 표를 옮긴 글이
        # 대개 여기 걸린다 — 마침표가 하나도 없다.
        for line in _LINE_BREAK.split(block):
            line = line.strip()
            if line:
                yield line


def _overlap(buffer: str) -> str:
    """앞 조각의 끝 일부. 단어 중간에서 시작하지 않게 공백에서 맞춘다."""
    if OVERLAP_CHARS <= 0 or len(buffer) <= OVERLAP_CHARS:
        return ""
    tail = buffer[-OVERLAP_CHARS:]
    space = tail.find(" ")
    if 0 <= space < len(tail) - 1:
        tail = tail[space + 1:]
    return tail.strip() + " "
