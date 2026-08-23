"""RRF 융합과 인용 만들기 — **DB 없이 판정되는 부분** (S10 · D-209 · D-212).

여기서 보는 것은 「여러 레인이 함께 고른 것이 위로 온다」와 「인용이 그 자리를
가리킨다」 둘이다. 실제 SQL 이 그 순위를 내는지는 integration 이 본다.
"""

from __future__ import annotations

import pytest

from app.ai.models import (
    ANCHOR_BLOCK,
    ANCHOR_PAGE,
    ANCHOR_SHEET,
    SOURCE_DOCUMENT,
    SOURCE_FILE,
)
from app.ai.retrieval import citation as citation_mod
from app.ai.retrieval import fusion

pytestmark = pytest.mark.unit


class FakeChunk:
    """`DocumentChunk` 의 인용에 필요한 칸만. 행 하나를 만들려고 DB 를 켜지 않는다."""

    def __init__(
        self, *, chunk_id="c1", document_id="d1", source_kind=SOURCE_DOCUMENT,
        anchor_kind=ANCHOR_BLOCK, anchor_ref="blk-1", anchor_label="", text="본문",
        file_id=None,
    ):
        self.id = chunk_id
        self.document_id = document_id
        self.source_kind = source_kind
        self.anchor_kind = anchor_kind
        self.anchor_ref = anchor_ref
        self.anchor_label = anchor_label
        self.text_body = text
        self.file_id = file_id


# ── 융합 ─────────────────────────────────────────────────────────────────────


def test_two_lanes_agreeing_beats_one_lane_first_place():
    """**이것이 RRF 를 고른 이유다.** 한 레인의 1등이 두 레인의 합의를 못 이긴다."""
    fused = fusion.fuse({
        fusion.LANE_TRGM: ["solo", "both"],
        fusion.LANE_VECTOR: ["both"],
    })
    assert [row.key for row in fused] == ["both", "solo"]


def test_rank_gap_inside_one_lane_is_smaller_than_being_found_at_all():
    """1등과 2등의 차이가 「한 레인에만 있다」와 「둘 다에 있다」의 차이보다 작다."""
    inside = 1 / (fusion.RRF_K + 1) - 1 / (fusion.RRF_K + 2)
    across = 1 / (fusion.RRF_K + 1)
    assert inside < across / 10


def test_every_lane_carries_some_weight():
    """레인 하나를 0 으로 두면 그 레인만 찾는 질의군이 **통째로** 사라진다.

    S10 실측(`EVIDENCE/S10/retrieval_fusion.json`)의 단일 레인 MRR@10 이 그 사실이다:
    어절 내부 질의는 트라이그램 0.6600 대 FTS **0.0575**, 기억나는 대로 친 질의는 FTS
    0.9387 대 트라이그램 **0.0350**. 두 레인이 서로의 빈자리를 메운다.
    """
    assert all(fusion.WEIGHTS[lane] > 0 for lane in fusion.LANES)


def test_the_vector_lane_does_not_outweigh_the_word_lanes():
    """🔴 **거들 때는 도움이 되고 앞장서면 해가 된다.**

    같은 실측에서 벡터 가중치만 흔든 값(상한 0.16 · 나머지 고정): 0.0 → 0.8693 ·
    **0.5 → 0.8869** · 1.0 → 0.8313 · 1.5 → 0.6781. 단독 MRR 이 0.2187 인 레인이라
    앞장세우면 두 키워드 레인이 이미 맞힌 것을 밀어낸다.
    """
    keyword = min(fusion.WEIGHTS[fusion.LANE_TRGM], fusion.WEIGHTS[fusion.LANE_FTS])
    assert fusion.WEIGHTS[fusion.LANE_VECTOR] < keyword


def test_the_vector_lane_has_a_distance_ceiling():
    """상한이 없으면 최근접 이웃은 **언제나** 답을 내고, 「근거가 없다」가 성립하지 않는다.

    코사인 거리의 최대는 2 다 — 상한이 그 값이면 없는 것과 같다.
    """
    assert 0 < fusion.VECTOR_MAX_DISTANCE < 2.0


def test_a_lane_only_gets_one_vote_per_key():
    """같은 key 가 한 레인에 두 번 나와도 표는 하나다."""
    twice = fusion.fuse({fusion.LANE_TRGM: ["a", "a", "b"]})
    once = fusion.fuse({fusion.LANE_TRGM: ["a", "b"]})
    assert [r.key for r in twice] == [r.key for r in once]
    assert twice[0].score == pytest.approx(once[0].score)
    assert twice[1].ranks[fusion.LANE_TRGM] == 2


def test_ties_break_the_same_way_every_time():
    """순서가 흔들리면 「어제와 다른 답이 나온다」의 원인을 아무도 못 찾는다."""
    first = fusion.fuse({fusion.LANE_TRGM: ["b"], fusion.LANE_VECTOR: ["a"]})
    second = fusion.fuse({fusion.LANE_VECTOR: ["a"], fusion.LANE_TRGM: ["b"]})
    assert [r.key for r in first] == [r.key for r in second]


def test_unknown_lane_is_refused_not_silently_zero_weighted():
    """0 으로 접으면 오타 하나가 레인을 통째로 끄는데 아무 오류도 안 난다."""
    with pytest.raises(ValueError):
        fusion.fuse({"trigram": ["a"]})


def test_lanes_are_reported_in_a_fixed_order():
    fused = fusion.fuse({fusion.LANE_VECTOR: ["a"], fusion.LANE_TRGM: ["a"]})
    assert fused[0].lanes == (fusion.LANE_TRGM, fusion.LANE_VECTOR)


def test_limit_cuts_after_scoring_not_before():
    """레인별로 먼저 자르면 두 레인이 합의한 것이 잘려 나간다."""
    fused = fusion.fuse(
        {fusion.LANE_TRGM: ["x", "y", "both"], fusion.LANE_FTS: ["both"]}, limit=1
    )
    assert [row.key for row in fused] == ["both"]


def test_only_a_semantic_hit_is_worth_explaining():
    """「낱말 검색이 찾았습니다」는 사용자가 이미 아는 사실이라 적을 값이 없다.

    적을 값이 있는 것은 **찾은 낱말이 하나도 없는데 나온 문서** 하나뿐이다.
    """
    assert fusion.semantic_only((fusion.LANE_VECTOR,)) is True
    assert fusion.semantic_only((fusion.LANE_TRGM,)) is False
    assert fusion.semantic_only((fusion.LANE_FTS,)) is False
    # 낱말 레인이 함께 찾았으면 설명할 것이 없다.
    assert fusion.semantic_only((fusion.LANE_TRGM, fusion.LANE_VECTOR)) is False
    assert fusion.semantic_only(()) is False


# ── 인용 ─────────────────────────────────────────────────────────────────────


def test_block_anchor_becomes_part_of_the_link():
    """블록 id 는 판이 올라도 안 바뀐다 — 어제의 인용이 오늘도 같은 문장을 가리킨다."""
    route = citation_mod.route_for(FakeChunk(document_id="doc-9", anchor_ref="blk-7"))
    assert route == "/knowledge/doc-9?block=blk-7"


def test_a_chunk_without_a_block_anchor_still_links_to_the_document():
    """자리를 모르면 문서까지만 간다. **틀린 자리로 보내는 것보다 낫다.**"""
    chunk = FakeChunk(
        source_kind=SOURCE_FILE, anchor_kind=ANCHOR_PAGE, anchor_ref="12", file_id="f1"
    )
    assert citation_mod.route_for(chunk) == "/knowledge/d1"


def test_the_parser_label_wins_over_a_generated_one():
    chunk = FakeChunk(anchor_kind=ANCHOR_SHEET, anchor_ref="Sheet1!A1:D20", anchor_label="1번 시트")
    assert citation_mod.where_of(chunk) == "1번 시트"


def test_a_file_citation_says_which_file_it_came_from():
    chunk = FakeChunk(
        source_kind=SOURCE_FILE, anchor_kind=ANCHOR_PAGE, anchor_ref="12",
        anchor_label="12쪽", file_id="f1",
    )
    assert citation_mod.where_of(chunk, filename="보고서.pdf") == "보고서.pdf 12쪽"


def test_the_excerpt_is_cut_but_the_context_text_is_not():
    """화면은 잘린 글을 보여 주고 모델은 chunk 전체를 받는다."""
    body = "가" * 500
    cite = citation_mod.build(
        FakeChunk(text=body), document_title="제목", excerpt_chars=100
    )
    assert len(cite.excerpt) <= 101
    assert cite.excerpt.endswith("…")
    assert cite.text_for_context == body


def test_the_payload_answers_the_question_instead_of_naming_lanes():
    """화면이 `trgm` 을 해석하게 두지 않는다 — 사람에게 아무 뜻이 없는 이름이다."""
    cite = citation_mod.build(
        FakeChunk(), document_title="제목", lanes=("vector",), excerpt_chars=100
    )
    body = cite.as_dict()
    assert body["semantic_only"] is True
    assert "lanes" not in body


def test_the_response_payload_does_not_carry_the_whole_chunk():
    """인용 여덟 건이 매 요청 수만 자가 되지 않게."""
    cite = citation_mod.build(
        FakeChunk(text="가" * 500), document_title="제목", excerpt_chars=100
    )
    assert "text_for_context" not in cite.as_dict()


def test_every_anchor_kind_has_a_word_for_it():
    """CHECK 제약이 아는 종류를 화면이 모르면 「」 만 나온다."""
    from app.ai.models import ANCHOR_KINDS

    assert set(ANCHOR_KINDS) == set(citation_mod.KIND_WORDS)
