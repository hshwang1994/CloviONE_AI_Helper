"""검색 질의 규칙 — **한국어 부분일치가 실제로 걸리는가**를 인덱스에 대고 확인한다.

S1 이 실 PG16 에서 확정한 두 사실을 여기서 회귀로 못박는다(D-209):
  1. `pg_trgm` 이면 `"린트 회"` 가 `스프린트 회의록 정리` 에 걸린다(어절 **내부** recall 1.000).
  2. 그래도 **3자 미만은 트라이그램을 만들 수 없다** → 인덱스가 못 받고 전량 스캔이 된다.

둘 중 하나라도 조용히 깨지면 검색은 "고장났다"가 아니라 "결과가 없다"로 보인다 — 아무도
버그로 신고하지 않는 종류의 실패라 테스트가 유일한 방어선이다.

qa-contract-change: FTS5 MATCH 질의 언어가 통째로 사라져 fts_expression() 단위 시험 둘도 함께 사라졌다. 주입 표면이 없어진 것이 아니라 ILIKE 패턴의 %·_ escape 로 옮겨 갔고, 그 자리를 새 시험 둘이 대신한다.
사라졌다(질의 언어 자체가 없으므로 파싱될 연산자가 없다). 그 자리를 대신하는 것은 아래
`ILIKE` 패턴 escape 시험 둘이다 — 주입 표면이 옮겨 간 것이지 없어진 것이 아니다.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select

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
    """트라이그램 경로로만 조회한 제목들(서비스 계층을 거치지 않는다)."""
    normalized = q.normalize(raw)
    stmt = (
        select(SearchDocument.title)
        .where(q.trgm_clause(normalized))
        .order_by(q.rank_expression(normalized).desc(), SearchDocument.title)
    )
    return list(db.execute(stmt).scalars().all())


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


def test_two_char_query_still_finds_the_row_but_takes_the_scan_path(db):
    """2자 질의는 **찾기는 찾는다.** 다만 인덱스를 못 타서 전량 스캔이 된다.

    qa-contract-change: FTS5 시절 2자 질의는 0건이었고 단언이 == [] 였다. pg_trgm 은 같은 질의를 정확히 찾으므로 결과가 강해졌다 — 바뀐 것은 recall 이 아니라 비용(인덱스를 못 타 전량 스캔)이라, 단언을 뒤집고 mode 까지 함께 못박는다.

    즉 계약이 **강해졌다**. 그래서 여기서 못박는 것도 둘로 늘었다 — 결과가 맞는가,
    그리고 화면이 그 사실을 정직하게 말하도록 모드가 여전히 `like` 인가
    (`frontend/src/screens/Search.jsx` 가 그 값으로 "짧은 검색어라 부분 일치로
    찾았습니다" 를 켠다).
    """
    _add(db, "회의록 템플릿 개선")
    assert _fts(db, "회의") == ["회의록 템플릿 개선"]
    assert q.mode_for(q.normalize("회의")) == q.MODE_LIKE


def test_multi_word_query_matches_words_apart(db):
    """`스프린트 정리` 처럼 원문에서 떨어진 두 낱말도 찾는다(각 낱말 3자 이상일 때)."""
    _add(db, "스프린트 회의록 정리하기")
    assert _fts(db, "스프린트 정리하기") == ["스프린트 회의록 정리하기"]


def test_body_is_searchable_not_only_title(db):
    _add(db, "제목만 있는 티켓", body="본문에 파이프라인 이야기가 있다")
    assert _fts(db, "파이프라인") == ["제목만 있는 티켓"]


# ── 주입 / 특수문자 ──────────────────────────────────────────────────────────


def test_percent_is_escaped_not_a_wildcard(db):
    """`%` 를 그대로 넘기면 `ILIKE` 에서 **전부**가 걸린다. escape 해야 0건이다."""
    _add(db, "정상 문서")
    assert _fts(db, "abc%def") == []


def test_underscore_is_escaped_not_a_single_char_wildcard(db):
    """`_` 는 `ILIKE` 에서 아무 글자 하나다. escape 안 하면 `정상 문서` 가 걸린다."""
    _add(db, "정상 문서")
    assert _fts(db, "정_ 문서") == []


def test_query_is_matched_case_insensitively(db):
    """PG 의 `LIKE` 는 대소문자를 구분한다 — `ILIKE` 여야 한다.

    한글만 쓰는 화면에서는 이 차이가 한참 뒤에야 드러난다.
    """
    _add(db, "Sprint 회고 문서")
    assert _fts(db, "sprint") == ["Sprint 회고 문서"]


def test_fts_operators_are_literal_not_parsed(db):
    """옛 FTS5 질의 문법(`NEAR`/컬럼필터)이 연산자로 해석되면 안 된다 — 이제는 문법 자체가 없다."""
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
