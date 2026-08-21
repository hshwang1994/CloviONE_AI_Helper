"""질의 문자열 → SQL 조건. **한국어에서 실제로 걸리는 방식**만 남겼다.

## 왜 trigram 이고, 왜 1~2자는 인덱스를 못 쓰는가

한국어는 조사·접미가 어절에 붙는다. 그래서 **어절 내부 부분일치가 예외가 아니라 기본**이다 —
`회의` 로 `회의록` 을 못 찾으면 검색이 사실상 동작하지 않는다.

PostgreSQL 의 전문검색(`to_tsvector('simple')`)은 그것을 못 한다. 공백으로만 쪼개기 때문이다.
S1 이 실 PG16 에서 쟀다(D-209): 어절 내부 질의 20건 중 **19건이 아무것도 못 찾았다**
(recall 0.083). 같은 질의에서 `pg_trgm` GIN 은 **recall 1.000** 이고 seqscan 보다 80배 빠르다.

**그래서 후보 생성은 `pg_trgm` GIN 하나가 책임진다.** 이 모듈이 만드는 조건은 전부
`ILIKE '%…%'` 이고, `search_documents` 의 `gin_trgm_ops` 인덱스가 그것을 받는다
(`app/search/models.py`).

그 대가는 FTS5 `trigram` 토크나이저 때와 **똑같다**: 3글자 미만은 만들 트라이그램 자체가
없어서 인덱스가 못 받는다. 그때는 전량 스캔으로 내려간다 — 예외도 오류도 아니고, 코퍼스가
작아(수천 건) 사람 눈에 안 보인다(D-209 실측 3ms). 조용히 0건을 돌려주는 것보다 훨씬 낫다.

## `ILIKE` 인 이유

PG 의 `LIKE` 는 **대소문자를 구분한다**(SQLite 는 ASCII 범위에서 구분하지 않았다). 그대로
옮기면 `Sprint` 로 검색한 사람이 `sprint` 를 못 찾고, 한글만 쓰는 화면에서는 그 차이가
한참 뒤에야 드러난다.

## 주입 경로

`ILIKE` 패턴의 `%`·`_`·`\\` 를 escape 한다. FTS5 시절의 `MATCH` 질의 문법(NEAR·컬럼 필터)은
이제 존재하지 않으므로 그 경로 자체가 사라졌다.
"""

from __future__ import annotations

from sqlalchemy import and_, func, or_

from app.search.models import SearchDocument

# 트라이그램 인덱스가 답할 수 있는 최소 길이. 이 값을 낮추면 인덱스를 못 타고 전량 스캔이 된다.
MIN_TRGM_CHARS = 3

# 옛 이름. `mode_for` 의 판정 근거가 "trigram 이 만들어지는가" 라는 뜻은 그대로다.
MIN_FTS_CHARS = MIN_TRGM_CHARS

# 사람이 검색창에 칠 만한 길이의 상한. 넘으면 자른다 — 긴 문자열은 결과를 좁히지 못하고
# 트라이그램 질의만 비싸게 만든다.
MAX_QUERY_CHARS = 100

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
    """앞뒤 공백 제거 + 연속 공백 1칸 + **한글 표기 통일(NFC)**. 판정과 표시에 같은 값을 쓴다.

    NFC 를 여기서 하는 이유 (Z4): `한`(1코드포인트)과 `한`(ㅎ+ㅏ+ㄴ)은 화면에서 같아 보이지만
    바이트가 다르다. macOS 에서 복사한 글이나 파일 이름은 NFD 로 들어오는 일이 흔하다.
    색인 쪽(`indexer._clip`)도 같은 정규화를 지나므로 **두 쪽 표기가 항상 같아진다** —
    한쪽만 하면 고친 것이 아니라 어긋나는 방향만 바뀐다.

    ⚠️ 글자 수를 세기 **전에** 정규화해야 한다. NFD 로 온 두 글자는 코드포인트로는 여섯이라,
    정규화 전에 세면 `MIN_TRGM_CHARS` 판정이 뒤집혀 2자 질의가 인덱스 경로로 간다.
    """
    import unicodedata

    text = unicodedata.normalize("NFC", str(raw or ""))
    return " ".join(text.split())[:MAX_QUERY_CHARS]


def mode_for(query: str) -> str:
    """이 질의를 트라이그램 인덱스로 답할지 전량 스캔으로 답할지.

    공백을 뺀 글자 수로 센다 — `"가 나"` 는 3자처럼 보이지만 트라이그램에는 2글자 두 덩이라
    만들어지는 트라이그램이 `"가 "`, `" 나"` 뿐이다. 실제로는 걸리지만 의도한 검색이 아니고,
    전량 스캔으로 답하는 편이 사용자가 기대한 결과에 가깝다.
    """
    if not query:
        return MODE_EMPTY
    return MODE_TRGM if len(query.replace(" ", "")) >= MIN_TRGM_CHARS else MODE_LIKE


def _pattern(text: str) -> str:
    """`ILIKE` 패턴 하나. `\\`·`%`·`_` 를 escape 한다(순서가 중요하다 — `\\` 가 먼저다)."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _contains(pattern: str):
    """제목 또는 본문에 이 패턴이 들어 있는가. `gin_trgm_ops` 인덱스가 받는 모양이다."""
    return or_(
        SearchDocument.title.ilike(pattern, escape="\\"),
        SearchDocument.body.ilike(pattern, escape="\\"),
    )


def trgm_clause(query: str):
    """3자 이상 질의의 조건. 트라이그램 GIN 이 받는다.

    기본은 **질의 전체를 한 덩이로** 본다 — 트라이그램은 공백까지 포함해 색인하므로
    `린트 회` 가 `스프린트 회의록 정리` 에 걸린다.

    거기에 더해, 낱말이 여럿이고 **각 낱말이 3자 이상**이면 낱말별 AND 조합을 OR 로 덧붙인다.
    `스프린트 정리` 처럼 원문에서 떨어져 있는 두 낱말도 찾게 하기 위해서다. 3자 미만 낱말이
    하나라도 섞이면 그 조합은 붙이지 않는다 — 그 낱말은 인덱스를 못 타서 AND 전체를
    전량 스캔으로 끌어내린다.
    """
    branches = [_contains(_pattern(query))]
    words = query.split()
    if len(words) > 1 and all(len(w) >= MIN_TRGM_CHARS for w in words):
        branches.append(and_(*[_contains(_pattern(w)) for w in words]))
    return or_(*branches)


def like_clause(query: str):
    """1~2자 폴백. 조건 자체는 같고, 다만 인덱스가 못 받아 전량 스캔이 된다."""
    return _contains(_pattern(query))


def clause_for(query: str, mode: str):
    """모드에 맞는 조건 하나. 호출부가 모드별 분기를 갖지 않게 한다."""
    return trgm_clause(query) if mode == MODE_TRGM else like_clause(query)


def rank_expression(query: str):
    """관련도. 큰 값이 먼저다.

    **제목 일치를 본문 일치보다 위에 둔다.** 사람이 검색창에 치는 말은 대개 제목의 일부라,
    본문 어딘가에 스친 문서가 제목이 정확히 맞는 문서를 밀어내면 검색이 쓸모없어진다.
    제목 점수에 가중치를 곱하므로 값이 1을 넘을 수 있다 — 정렬에만 쓰므로 상관없다.

    `similarity()` 는 `pg_trgm` 이 준다. 옛 FTS5 `rank` 자리이고, 역할이 같다.
    """
    return func.greatest(
        func.similarity(SearchDocument.title, query) * 2.0,
        func.similarity(SearchDocument.body, query),
    )
