"""질의 문자열 → SQL 조건. **한국어에서 실제로 걸리는 방식**만 남겼다.

## 왜 trigram 이고, 왜 1~2자는 FTS 를 안 쓰는가

FTS5 기본 토크나이저 `unicode61` 은 공백으로만 자른다. 한국어는 조사·접미가 어절에 붙으므로
`회의` 로는 `회의록` 을 못 찾는다 — 검색이 사실상 동작하지 않는다. `trigram` 토크나이저는
3글자 창을 훑기 때문에 `"린트 회"` 가 `스프린트 회의록 정리` 에 걸린다.

그 대가는 **3자 미만은 인덱스에 걸 트라이그램 자체가 없다**는 것이다. 2자 질의를 FTS 로
보내면 예외도 아니고 오류도 아니고 **조용히 0건**이 돌아온다 — 사용자에겐 "없다"로 보인다.
그래서 1~2자는 `LIKE` 로 답한다. 코퍼스가 작아(수천 건) 전수 스캔이 사람 눈에 안 보인다.

## 주입 경로

FTS5 `MATCH` 는 자체 질의 문법을 가진다. 사용자 문자열을 그대로 넘기면 `NEAR`, `*`, 컬럼
필터 같은 연산자가 해석된다. **큰따옴표로 감싸면 그 안은 전부 리터럴**이 되므로, 내부의
`"` 만 두 배로 escape 하고 통째로 감싼다. LIKE 쪽은 `%`/`_` 를 escape 한다.
"""

from __future__ import annotations

from sqlalchemy import or_

from app.search.models import SearchDocument

# trigram 인덱스가 답할 수 있는 최소 길이. 이 값을 낮추면 조용히 0건이 된다.
MIN_FTS_CHARS = 3

# 사람이 검색창에 칠 만한 길이의 상한. 넘으면 자른다 — 긴 문자열은 결과를 좁히지 못하고
# trigram 질의만 비싸게 만든다.
MAX_QUERY_CHARS = 100

MODE_FTS = "fts"
MODE_LIKE = "like"
MODE_EMPTY = "empty"


def normalize(raw: str | None) -> str:
    """앞뒤 공백 제거 + 연속 공백 1칸. 검색어 판정과 표시에 같은 값을 쓴다."""
    return " ".join(str(raw or "").split())[:MAX_QUERY_CHARS]


def mode_for(query: str) -> str:
    """이 질의를 FTS 로 답할지 LIKE 로 답할지.

    공백을 뺀 글자 수로 센다 — `"가 나"` 는 3자처럼 보이지만 trigram 에는 2글자 두 덩이라
    걸릴 트라이그램이 `"가 "`, `" 나"` 뿐이다. 실제로는 걸리지만 의도한 검색이 아니고,
    LIKE 로 답하는 편이 사용자가 기대한 결과에 가깝다.
    """
    if not query:
        return MODE_EMPTY
    return MODE_FTS if len(query.replace(" ", "")) >= MIN_FTS_CHARS else MODE_LIKE


def _phrase(text: str) -> str:
    """FTS5 리터럴 구문 하나. 내부 `"` 는 두 배로 escape 한다."""
    return '"' + text.replace('"', '""') + '"'


def fts_expression(query: str) -> str:
    """`search_index MATCH ?` 에 넘길 문자열.

    기본은 **질의 전체를 한 구문으로** 본다 — trigram 은 공백까지 포함해 색인하므로
    `"린트 회"` 가 `스프린트 회의록 정리` 에 걸린다(계획서가 실험으로 확정한 동작).

    거기에 더해, 낱말이 여럿이고 **각 낱말이 3자 이상**이면 `AND` 조합을 OR 로 덧붙인다.
    `스프린트 정리` 처럼 원문에서 떨어져 있는 두 낱말도 찾게 하기 위해서다. 3자 미만
    낱말이 하나라도 섞이면 그 조합은 붙이지 않는다 — 그 낱말이 trigram 에서 0건이라
    AND 전체가 0건이 되어 오히려 결과를 없앤다.
    """
    parts = [_phrase(query)]
    words = query.split()
    if len(words) > 1 and all(len(w) >= MIN_FTS_CHARS for w in words):
        parts.append("(" + " AND ".join(_phrase(w) for w in words) + ")")
    return " OR ".join(parts)


def like_clause(query: str):
    """제목 또는 본문에 그대로 들어 있는가. 1~2자 폴백 전용."""
    pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    return or_(
        SearchDocument.title.like(pattern, escape="\\"),
        SearchDocument.body.like(pattern, escape="\\"),
    )
