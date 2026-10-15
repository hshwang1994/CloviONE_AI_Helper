"""AI 검색의 낱말 레인 — 조립된 SQL 을 본다 (D-536).

질문에서 뽑은 낱말은 두 레인에 **OR 로** 붙는다: 트라이그램 레인은 낱말마다 `LIKE` 가지(점수에 맞은 낱말 수의 절반), FTS 레인은
`to_tsquery('낱말:* | …')`. 낱말이 없으면 두 레인은 예전 그대로다(검색창과 같은 가지 · `plainto_tsquery`).

🔴 FTS 질의 문자열은 사람이 친 글이 아니라 **걸러진 낱말**로만 만든다 — `to_tsquery` 는 `& | ! : * ( )` 를 문법으로 읽어서, 사람이
친 글이 그대로 들어가면 문법 오류 500 이 나거나 질의의 뜻이 바뀐다. 그 거름을 레인 함수가 한 번 더 한다(`safe_keywords`).
"""
import re

from sqlalchemy.dialects import postgresql

from app.ai.retrieval import query as query_mod


def _sql(stmt) -> tuple[str, dict]:
    compiled = stmt.compile(dialect=postgresql.dialect())
    return str(compiled), dict(compiled.params)


def test_without_keywords_the_lanes_are_unchanged():
    trgm, _ = _sql(query_mod.trgm_lane("연차 규정", limit=5))
    fts, _ = _sql(query_mod.fts_lane("연차 규정", limit=5))
    assert "CASE" not in trgm
    assert "plainto_tsquery('simple'" in fts
    assert not re.search(r"(?<!plain)to_tsquery\(", fts), "낱말이 없는데 문법을 읽는 to_tsquery 를 쓴다"


def test_keywords_add_one_like_branch_each_and_a_hit_score():
    sql, params = _sql(query_mod.trgm_lane("연차 신청은 어떻게 하나요?", keywords=("연차", "신청"), limit=5))
    patterns = [v for v in params.values() if isinstance(v, str) and v.startswith("%")]
    assert "%연차%" in patterns and "%신청%" in patterns
    # 점수 식은 SELECT 와 ORDER BY 에 한 번씩 선다 — 낱말 둘 × 두 자리.
    assert sql.count("CASE WHEN") == 4, "맞은 낱말 수가 점수에 들어가지 않는다"
    assert query_mod.KEYWORD_HIT_WEIGHT in params.values()


def test_fts_keywords_become_an_or_of_prefix_matches():
    sql, params = _sql(query_mod.fts_lane("연차 신청은 어떻게 하나요?", keywords=("연차", "신청"), limit=5))
    assert re.search(r"(?<!plain)to_tsquery\('simple'", sql) and "plainto_tsquery" not in sql
    assert "연차:* | 신청:*" in params.values()


def test_hostile_keywords_never_reach_the_query_string():
    """낱말 거름을 거치지 않은 값이 들어와도 레인이 한 번 더 거른다 — 질의 문법이 섞일 수 없다."""
    hostile = ("보안", "a&b", "x:*", "'", "정책 보안", "%", "ok_1", "!(", "\\", "|")
    assert query_mod.safe_keywords(hostile) == ("보안",)
    _sql_text, params = _sql(query_mod.fts_lane("보안", keywords=hostile, limit=5))
    assert "보안:*" in params.values()
    assert not any(isinstance(v, str) and any(ch in v for ch in "&!()'%\\") for v in params.values())
    # 남는 낱말이 없으면 낱말 레인이 아니라 예전 레인이다.
    sql, _ = _sql(query_mod.fts_lane("a & b", keywords=("a&b", "!"), limit=5))
    assert "plainto_tsquery" in sql


# ── 낱말의 무게 (D-568) ──────────────────────────────────────────────────────────────────────────────────────


def test_the_weight_factor_falls_as_the_word_gets_common():
    """드문 낱말이 흔한 낱말보다 무겁다 — df 가 커질수록 배율이 줄고, 아래 한계에서 멈춘다."""
    n = 2000
    factors = [query_mod.idf_factor(n, df) for df in (0, 1, 5, 20, 100, 500, 1000, 2000)]
    assert factors == sorted(factors, reverse=True)
    assert factors[0] == 1.0
    assert factors[-1] == query_mod.MIN_WEIGHT_FACTOR
    assert all(query_mod.MIN_WEIGHT_FACTOR <= f <= 1.0 for f in factors)
    # 빈 범위(볼 수 있는 조각이 없다)는 같은 무게다 — 0 으로 나누지 않는다.
    assert query_mod.idf_factor(0, 0) == 1.0


def test_document_frequency_is_one_statement_inside_the_permission_clause():
    narrowing = query_mod.DocumentChunk.document_id.in_(["d-1"])
    sql, params = _sql(query_mod.df_statement(("연차", "신청"), narrowing=narrowing))
    assert sql.count("count(*) FILTER (WHERE") == 2, "낱말마다 df 칸이 하나여야 한다"
    assert "document_chunks.document_id IN" in sql, "권한 절 없이 세면 숨은 문서의 낱말 분포가 샌다"
    assert {"%연차%", "%신청%"} <= {v for v in params.values() if isinstance(v, str)}


def test_expanded_words_weigh_half_and_without_a_session_the_weights_are_uniform():
    weights = query_mod.keyword_weights(None, ("vmware",), ("vsphere",))
    assert weights == {
        "vmware": query_mod.KEYWORD_HIT_WEIGHT,
        "vsphere": query_mod.KEYWORD_HIT_WEIGHT * query_mod.EXPANDED_WEIGHT_FACTOR,
    }
    assert query_mod.keyword_weights(None, (), ()) == {}


def test_the_trigram_score_uses_the_given_weights_and_the_expanded_words_join_both_lanes():
    sql, params = _sql(query_mod.trgm_lane("vmware 문서", keywords=("vmware",), expanded=("vsphere",),
                                           weights={"vmware": 0.41, "vsphere": 0.07}, limit=5))
    assert 0.41 in params.values() and 0.07 in params.values()
    assert "%vsphere%" in params.values()
    _fts, fts_params = _sql(query_mod.fts_lane("vmware 문서", keywords=("vmware",), expanded=("vsphere",), limit=5))
    assert "vmware:* | vsphere:*" in fts_params.values()


def test_keyword_groups_tie_parts_and_synonyms_to_their_word():
    """「모든 낱말이 든 문서」는 묶음마다 하나만 있으면 된다 — 「SK 하이닉스」라고 쓴 문서는 「sk」 조각 없이도 묶음을 채운다."""
    groups = query_mod.keyword_groups(("sk하이닉스", "하이닉스", "sk", "프로젝트"), ("hynix",))
    assert groups == [("sk하이닉스", "하이닉스", "sk", "hynix"), ("프로젝트",)]
    groups = query_mod.keyword_groups(("vmware", "네트워크"), ("vsphere", "nsx"))
    assert groups == [("vmware", "vsphere"), ("네트워크", "nsx")]
    # 순수 한글 낱말 안의 다른 낱말은 조각이 아니다 — 묶지 않는다.
    assert query_mod.keyword_groups(("회의록", "회의"), ()) == [("회의록",), ("회의",)]
