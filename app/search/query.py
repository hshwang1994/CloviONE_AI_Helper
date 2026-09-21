"""질의 문자열 → SQL 조건. **한국어에서 실제로 걸리는 방식**만 남겼다.

## 왜 trigram 이고, 왜 1~2자는 인덱스를 못 쓰는가

한국어는 조사·접미가 어절에 붙는다. 그래서 **어절 내부 부분일치가 예외가 아니라 기본**이다 —
`회의` 로 `회의록` 을 못 찾으면 검색이 사실상 동작하지 않는다.

PostgreSQL 의 전문검색(`to_tsvector('simple')`)은 그것을 못 한다. 공백으로만 쪼개기 때문이다.
S1 이 실 PG16 에서 쟀다(D-209): 어절 내부 질의 20건 중 **19건이 아무것도 못 찾았다**
(recall 0.083). 같은 질의에서 `pg_trgm` GIN 은 **recall 1.000** 이고 seqscan 보다 80배 빠르다.

**그래서 후보 생성은 `pg_trgm` GIN 하나가 책임진다.** 이 모듈이 만드는 조건은 전부
`title_fold LIKE '%…%'` 모양이고, `search_documents` 의 접힌 생성 열 위 `gin_trgm_ops`
인덱스가 그것을 받는다(`app/search/models.py`).

그 대가는 FTS5 `trigram` 토크나이저 때와 **똑같다**: 3글자 미만은 만들 트라이그램 자체가
없어서 인덱스가 못 받는다. 그때는 전량 스캔으로 내려간다 — 예외도 오류도 아니고, 코퍼스가
작아(수천 건) 사람 눈에 안 보인다(D-209 실측 3ms). 조용히 0건을 돌려주는 것보다 훨씬 낫다.

## 대소문자 · 공백 · 표기를 어떻게 맞추는가 (D-495)

질의와 색인 **양쪽**을 같은 규칙으로 접는다(`app/core/search_text.py::fold`). 질의는 파이썬이
접고, 색인은 DB 가 `search_fold()` 로 접어 생성 열(`title_fold`·`body_fold`)에 저장한다. 그래서
「현황 제외」가 「현황제외」에 걸리고, 「ClovirONE」·「clovirone」·전각 표기가 서로를 찾는다.

예전에는 `ILIKE` 로 대소문자만 맞췄다. 공백은 질의 쪽에서만 정리했기 때문에 대상의 공백
하나가 검색을 통째로 빗나가게 했다. 이제 양쪽이 이미 소문자라 `ILIKE` 가 할 일이 없다 —
조건은 `LIKE` 다.

화면에 돌려주는 검색어는 표시형(`normalize`)이다. 접힌 값은 대조에만 쓴다.

## 주입 경로

LIKE 패턴의 `%`·`_`·`\\` 를 escape 한다(`search_text.escape_like` — 백엔드의 유일한 escape).
FTS5 시절의 `MATCH` 질의 문법(NEAR·컬럼 필터)은 이제 존재하지 않으므로 그 경로 자체가 사라졌다.
"""

from __future__ import annotations

from sqlalchemy import and_, false, func, or_

from app.core.search_text import (
    MAX_QUERY_CHARS,
    MIN_TRGM_CHARS,
    fold,
    like_folded,
    like_pattern,
    normalize_query,
)
from app.search.models import SearchDocument

__all__ = [
    "MAX_QUERY_CHARS",
    "MIN_FTS_CHARS",
    "MIN_TRGM_CHARS",
    "MODE_EMPTY",
    "MODE_FTS",
    "MODE_LIKE",
    "MODE_TRGM",
    "clause_for",
    "ilike_pattern",
    "like_clause",
    "mode_for",
    "normalize",
    "rank_expression",
    "trgm_clause",
    "trgm_condition",
]

# 옛 이름. `mode_for` 의 판정 근거가 "trigram 이 만들어지는가" 라는 뜻은 그대로다.
MIN_FTS_CHARS = MIN_TRGM_CHARS

# 응답의 `mode` 값. **문자열은 옛 값 그대로 둔다** — 화면이 `mode === "like"` 하나로
# "짧은 검색어라 부분 일치로 찾았습니다" 안내를 켜고(`frontend/src/screens/Search.jsx`),
# 그 사용자 계약은 엔진이 바뀌어도 달라지지 않았다. 뜻도 그대로다: **인덱스가 받은 질의인가,
# 전량 스캔으로 내려간 짧은 질의인가.**
MODE_TRGM = "fts"
MODE_LIKE = "like"
MODE_EMPTY = "empty"

# 옛 이름 — 호출부가 아직 이 이름으로 부른다.
MODE_FTS = MODE_TRGM


def normalize(raw: str | None) -> str:
    """표시형 — 앞뒤 공백 제거 + 연속 공백 1칸 + **한글 표기 통일(NFC)** + 상한.

    화면과 주소에 다시 싣는 값이다. 대조는 이 값을 한 번 더 접어서 한다(`fold`). 규칙의 정본은
    `app/core/search_text.py::normalize_query` 이고, 여기는 옛 이름을 지키는 자리다.

    ⚠️ 글자 수를 세기 **전에** 정규화해야 한다. NFD 로 온 두 글자는 코드포인트로는 여섯이라,
    정규화 전에 세면 `MIN_TRGM_CHARS` 판정이 뒤집혀 2자 질의가 인덱스 경로로 간다.
    """
    return normalize_query(raw)


def mode_for(query: str) -> str:
    """이 질의를 트라이그램 인덱스로 답할지 전량 스캔으로 답할지.

    **접은 길이**로 센다. 색인이 접힌 값이므로 트라이그램도 접힌 글자에서 만들어진다 —
    `"가 나"` 는 공백이 지워져 `"가나"` 두 글자라 인덱스가 받지 못한다. 접은 뒤 아무것도 안
    남으면(공백·제로폭 공백만 친 경우) 빈 질의다. 그 질의를 `LIKE '%%'` 로 보내면 전 행이 걸린다.
    """
    length = len(fold(query))
    if length == 0:
        return MODE_EMPTY
    return MODE_TRGM if length >= MIN_TRGM_CHARS else MODE_LIKE


def ilike_pattern(text: str) -> str:
    """부분일치 패턴 하나. `\\`·`%`·`_` 를 escape 한다(순서가 중요하다 — `\\` 가 먼저다).

    이름은 옛것이다. 이제 조건은 `ILIKE` 가 아니라 접힌 값 위의 `LIKE` 이고, 넘기는 글자도
    이미 접힌 값이어야 한다. escape 의 정본은 `app/core/search_text.py::escape_like` 하나다 —
    두 벌로 적으면 한쪽만 `\\` 를 먼저 바꾸는 날이 오고, 그때 `%` 하나가 든 질의가 조용히
    전 행에 걸린다.
    """
    return like_pattern(text)


#: 옛 이름. 이 파일 안에서만 쓴다.
_pattern = ilike_pattern


def _contains(pattern: str):
    """제목 또는 본문에 이 패턴이 들어 있는가. 접힌 생성 열 위 `gin_trgm_ops` 인덱스가 받는다."""
    return or_(
        like_folded(SearchDocument.title_fold, pattern, stored=True),
        like_folded(SearchDocument.body_fold, pattern, stored=True),
    )


def trgm_condition(query: str, contains):
    """트라이그램 조건 하나. `contains(pattern) -> 조건` 을 주면 어느 표에든 건다.

    **공개 이름인 이유**: AI Retrieval 의 트라이그램 레인이 같은 가지를 쓴다
    (`app/ai/retrieval/query.py`). 두 벌로 적으면 한쪽에만 낱말 가지가 생기고, 그러면
    「검색에서는 나오는데 AI 는 못 찾는다」가 된다 — 실제로 S10 이 그 상태를 한 번
    만들었고 융합 실측에서 「기억나는 대로」 질의의 MRR 이 0.01 로 나왔다.

    `query` 는 표시형이다. 기본은 **질의 전체를 접은 한 덩이**다 — 공백이 지워지므로
    `린트 회` 가 `스프린트 회의록 정리`(접으면 `스프린트회의록정리`)에 걸린다.

    거기에 더해, 표시형의 낱말이 여럿이고 **접은 낱말이 각각 3자 이상**이면 낱말별 AND 조합을
    OR 로 덧붙인다. `스프린트 정리` 처럼 원문에서 떨어져 있는 두 낱말도 찾게 하기 위해서다.
    3자 미만 낱말이 하나라도 섞이면 그 조합은 붙이지 않는다 — 그 낱말은 인덱스를 못 타서
    AND 전체를 전량 스캔으로 끌어내린다.

    접은 뒤 빈 질의는 **거짓**이다. 빈 바늘은 `LIKE '%%'` 가 되어 전 행에 걸린다.
    """
    needle = fold(query)
    if not needle:
        return false()
    branches = [contains(like_pattern(needle))]
    words = [fold(word) for word in query.split()]
    if len(words) > 1 and all(len(word) >= MIN_TRGM_CHARS for word in words):
        branches.append(and_(*[contains(like_pattern(word)) for word in words]))
    return or_(*branches)


def trgm_clause(query: str):
    """3자 이상 질의의 조건. 트라이그램 GIN 이 받는다."""
    return trgm_condition(query, _contains)


def like_clause(query: str):
    """1~2자 폴백. 조건 자체는 같고, 다만 인덱스가 못 받아 전량 스캔이 된다."""
    needle = fold(query)
    if not needle:
        return false()
    return _contains(like_pattern(needle))


def clause_for(query: str, mode: str):
    """모드에 맞는 조건 하나. 호출부가 모드별 분기를 갖지 않게 한다."""
    return trgm_clause(query) if mode == MODE_TRGM else like_clause(query)


def rank_expression(query: str):
    """관련도. 큰 값이 먼저다.

    **제목 일치를 본문 일치보다 위에 둔다.** 사람이 검색창에 치는 말은 대개 제목의 일부라,
    본문 어딘가에 스친 문서가 제목이 정확히 맞는 문서를 밀어내면 검색이 쓸모없어진다.
    제목 점수에 가중치를 곱하므로 값이 1을 넘을 수 있다 — 정렬에만 쓰므로 상관없다.

    점수도 접힌 값끼리 잰다. 조건은 접힌 값으로 걸고 점수만 원문으로 재면, 걸린 행의 순위가
    공백과 대소문자에 따라 흔들린다.

    `similarity()` 는 `pg_trgm` 이 준다. 옛 FTS5 `rank` 자리이고, 역할이 같다.
    """
    needle = fold(query)
    return func.greatest(
        func.similarity(SearchDocument.title_fold, needle) * 2.0,
        func.similarity(SearchDocument.body_fold, needle),
    )
