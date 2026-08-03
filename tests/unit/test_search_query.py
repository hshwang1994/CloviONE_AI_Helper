"""검색 질의 규칙 — **한국어 부분일치가 실제로 걸리는가**를 인덱스에 대고 확인한다.

계획서가 실험으로 확정한 두 사실을 여기서 회귀로 못박는다:
  1. `trigram` 토크나이저면 `"린트 회"` 가 `스프린트 회의록 정리` 에 걸린다.
  2. 그래도 **3자 미만은 FTS 가 0건**이다 → 1~2자는 LIKE 폴백이어야 한다.

둘 중 하나라도 조용히 깨지면 검색은 "고장났다"가 아니라 "결과가 없다"로 보인다 — 아무도
버그로 신고하지 않는 종류의 실패라 테스트가 유일한 방어선이다.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import text

from app.search import query as q
from app.search.models import SearchDocument

NOW = datetime(2026, 8, 3, 9, 0, 0)


def _add(db, title: str, body: str = "", kind: str = "ticket", ref: str | None = None):
    row = SearchDocument(
        kind=kind, ref_id=ref or title, title=title, body=body,
        owner_user_ids="", route="/x", indexed_at=NOW,
    )
    db.add(row)
    db.flush()
    return row


def _fts(db, raw: str) -> list[str]:
    """FTS 경로로만 조회한 제목들(서비스 계층을 거치지 않는다)."""
    expression = q.fts_expression(q.normalize(raw))
    rowids = db.execute(
        text("SELECT rowid FROM search_index WHERE search_index MATCH :m ORDER BY rank"),
        {"m": expression},
    ).scalars().all()
    if not rowids:
        return []
    rows = db.execute(
        text(
            "SELECT title FROM search_documents WHERE rowid IN ("
            + ",".join(str(int(r)) for r in rowids) + ")"
        )
    ).scalars().all()
    return list(rows)


# ── 모드 판정 ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("", q.MODE_EMPTY),
        ("   ", q.MODE_EMPTY),
        ("회", q.MODE_LIKE),        # 1자
        ("회의", q.MODE_LIKE),      # 2자 — trigram 이 못 만드는 길이
        ("회의록", q.MODE_FTS),     # 3자
        ("린트 회", q.MODE_FTS),    # 공백 제외 3자
        ("가 나", q.MODE_LIKE),     # 공백 제외 2자 — 공백을 세면 안 된다
    ],
)
def test_mode_for(raw, expected):
    assert q.mode_for(q.normalize(raw)) == expected


def test_normalize_collapses_whitespace_and_caps_length():
    assert q.normalize("  린트   회  ") == "린트 회"
    assert len(q.normalize("가" * 500)) == q.MAX_QUERY_CHARS


# ── FTS5 trigram: 계획서가 확정한 동작 ────────────────────────────────────────


def test_korean_substring_matches_across_a_space(db):
    """계획서의 확정 사례. 이 한 줄이 이 기능의 존재 이유다."""
    _add(db, "스프린트 회의록 정리")
    _add(db, "전혀 관계없는 제목")
    assert _fts(db, "린트 회") == ["스프린트 회의록 정리"]


def test_korean_substring_matches_inside_a_word(db):
    """`회의` 가 `회의록` 에 걸린다 — unicode61 로는 안 되던 것."""
    _add(db, "회의록 템플릿 개선")
    assert _fts(db, "회의록") == ["회의록 템플릿 개선"]


def test_two_char_query_finds_nothing_in_fts(db):
    """왜 LIKE 폴백이 필요한가에 대한 증거. 2자는 예외도 오류도 아니고 **0건**이다."""
    _add(db, "회의록 템플릿 개선")
    assert _fts(db, "회의") == []


def test_multi_word_query_matches_words_apart(db):
    """`스프린트 정리` 처럼 원문에서 떨어진 두 낱말도 찾는다(각 낱말 3자 이상일 때)."""
    _add(db, "스프린트 회의록 정리하기")
    assert _fts(db, "스프린트 정리하기") == ["스프린트 회의록 정리하기"]


def test_body_is_searchable_not_only_title(db):
    _add(db, "제목만 있는 티켓", body="본문에 파이프라인 이야기가 있다")
    assert _fts(db, "파이프라인") == ["제목만 있는 티켓"]


# ── 주입 / 특수문자 ──────────────────────────────────────────────────────────


def test_fts_expression_quotes_the_whole_query():
    assert q.fts_expression("린트 회") == '"린트 회"'


def test_fts_expression_escapes_double_quotes():
    assert q.fts_expression('a"b') == '"a""b"'


def test_fts_operators_are_literal_not_parsed(db):
    """`NEAR`/`*`/컬럼필터가 연산자로 해석되면 안 된다 — 큰따옴표 안은 전부 리터럴이다."""
    _add(db, "정상 문서")
    # FTS5 문법으로 해석되면 예외가 나거나 전 행이 걸린다. 리터럴이면 0건이다.
    assert _fts(db, 'title : NEAR("정상")') == []


def test_fts_query_with_quotes_does_not_raise(db):
    _add(db, '따옴표 "포함" 제목')
    assert _fts(db, '"포함"') == ['따옴표 "포함" 제목']


# ── LIKE 폴백 ────────────────────────────────────────────────────────────────


def test_like_clause_escapes_wildcards(db):
    """`%` 를 그대로 넘기면 전 행이 걸린다 — 사용자가 친 `%` 는 글자다."""
    from sqlalchemy import select

    _add(db, "퍼센트 100% 달성")
    _add(db, "관계없는 제목")
    rows = db.execute(
        select(SearchDocument.title).where(q.like_clause("100%"))
    ).scalars().all()
    assert list(rows) == ["퍼센트 100% 달성"]

    rows = db.execute(select(SearchDocument.title).where(q.like_clause("%"))).scalars().all()
    assert list(rows) == ["퍼센트 100% 달성"]
