"""Chunk 만들기 (S9).

## 이 파일이 지키는 것 둘

1. **파일 chunk 는 앵커를 넘지 않는다.** 3쪽 끝과 4쪽 처음을 합치면 그 인용은 3쪽도
   4쪽도 아니고, 사용자가 눌러서 확인하면 그 자리에 그 문장이 없다.
2. **chunk 는 임베딩 상한 안에 있다.** 512 토큰 위는 **버려지는데 오류가 안 난다** —
   chunk 를 크게 잡을수록 뒷부분이 조용히 사라진다.
"""

from __future__ import annotations

import pytest

from app.ai import chunking
from app.ai.models import ANCHOR_BLOCK, ANCHOR_PAGE
from app.ai.parsing.base import ParsedUnit

pytestmark = pytest.mark.unit


def _page(number: int, text: str) -> ParsedUnit:
    return ParsedUnit(
        anchor_kind=ANCHOR_PAGE, anchor_ref=str(number), anchor_label=f"{number}쪽",
        text=text, ordinal=number - 1,
    )


def _block(block_id: str, text: str, ordinal: int) -> ParsedUnit:
    return ParsedUnit(
        anchor_kind=ANCHOR_BLOCK, anchor_ref=block_id, anchor_label=text[:10],
        text=text, ordinal=ordinal,
    )


# ── 앵커 경계 ────────────────────────────────────────────────────────────────


def test_file_chunks_never_span_two_pages():
    """이 한 줄이 인용을 지킨다."""
    units = [_page(1, "가" * 200), _page(2, "나" * 200)]
    chunks = chunking.chunk_units(units, merge_anchors=False)
    for chunk in chunks:
        assert not ("가" in chunk.text and "나" in chunk.text)
    assert {c.anchor_ref for c in chunks} == {"1", "2"}


def test_document_chunks_may_merge_blocks_and_anchor_to_the_first():
    """블록은 같은 화면 안의 이어진 문단이다. 한 줄짜리 문단마다 chunk 를 만들면
    뜻이 없는 조각 수백 개가 생기고 임베딩 예산만 쓴다."""
    units = [_block(f"b{i}", f"{i}번째 문단입니다. " * 3, i) for i in range(6)]
    chunks = chunking.chunk_units(units, merge_anchors=True)
    assert len(chunks) < len(units)
    assert chunks[0].anchor_ref == "b0"
    # 합쳤어도 앵커는 「여기서 시작한다」는 참말이다.
    assert chunks[0].text.startswith("0번째 문단")


def test_a_page_longer_than_the_limit_is_split_but_keeps_its_anchor():
    units = [_page(7, "문장입니다. " * 600)]
    chunks = chunking.chunk_units(units, merge_anchors=False)
    assert len(chunks) > 1
    assert {c.anchor_ref for c in chunks} == {"7"}


# ── 크기 ─────────────────────────────────────────────────────────────────────


def test_no_chunk_exceeds_the_hard_limit():
    """상한을 넘으면 임베딩이 뒷부분을 조용히 버린다."""
    long_text = "한국어 문장을 이어 붙입니다. " * 400
    for chunk in chunking.chunk_units([_page(1, long_text)], merge_anchors=False):
        assert len(chunk.text) <= chunking.MAX_CHARS


def test_a_single_sentence_longer_than_the_limit_is_still_cut():
    """마침표가 하나도 없는 글(표를 옮긴 것)이 여기 걸린다."""
    wall = "가" * 5000
    chunks = chunking.split_text(wall)
    assert chunks and all(len(c) <= chunking.MAX_CHARS for c in chunks)
    assert sum(len(c) for c in chunks) >= len(wall) * 0.9


def test_short_noise_is_dropped():
    """쪽 번호만 있는 쪽(`- 3 -`)은 검색에서 쓸모가 없고 임베딩 예산만 쓴다."""
    assert chunking.chunk_units([_page(3, "- 3 -")], merge_anchors=False) == ()
    assert chunking.chunk_units([_page(4, "12")], merge_anchors=False) == ()


def test_a_title_only_slide_is_kept():
    """제목 한 줄짜리 슬라이드는 **진짜 내용**이다. 버리면 그 슬라이드는 검색에서
    영영 안 나오고, 그 사실은 아무 데도 안 남는다."""
    chunks = chunking.chunk_units([_page(1, "2026년 사업 계획")], merge_anchors=False)
    assert len(chunks) == 1
    assert chunks[0].text == "2026년 사업 계획"


def test_nothing_at_all_produces_nothing():
    assert chunking.chunk_units([], merge_anchors=False) == ()
    assert chunking.split_text("   ") == ()


# ── 겹침 ─────────────────────────────────────────────────────────────────────


def test_consecutive_chunks_overlap():
    """문장이 chunk 경계에 걸치면 어느 쪽에서도 온전하지 않다."""
    text = " ".join(f"{i}번 문장입니다." for i in range(400))
    chunks = chunking.split_text(text)
    assert len(chunks) > 1
    tail = chunks[0][-chunking.OVERLAP_CHARS:]
    # 겹침 구간의 어느 한 조각이 다음 chunk 앞에 다시 실린다.
    assert any(word and word in chunks[1] for word in tail.split(" ")[1:])


# ── 지문과 토큰 추정 ─────────────────────────────────────────────────────────


def test_the_same_text_always_has_the_same_fingerprint():
    """지문이 흔들리면 「안 바뀐 chunk 는 다시 임베딩하지 않는다」가 안 먹는다."""
    a = chunking.Chunk(ANCHOR_PAGE, "1", "1쪽", "같은 글", 0)
    b = chunking.Chunk(ANCHOR_PAGE, "9", "9쪽", "같은 글", 5)
    assert a.sha256 == b.sha256
    assert len(a.sha256) == 64


def test_korean_costs_more_tokens_per_character_than_ascii():
    """추정이 반대로 되어 있으면 「상한 근처인가」를 사람이 반대로 읽는다."""
    korean = chunking.estimate_tokens("가나다라마바사아자차")
    ascii_text = chunking.estimate_tokens("abcdefghij")
    assert korean > ascii_text
    assert chunking.estimate_tokens("") == 0
