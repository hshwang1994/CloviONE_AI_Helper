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
