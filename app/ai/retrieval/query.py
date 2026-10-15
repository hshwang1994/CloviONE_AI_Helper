"""세 레인의 SQL — 각각 **chunk id 를 등수대로** 낸다 (D-209 · D-210).

## 이 파일이 안 하는 것: 권한

여기서 만드는 것은 「무엇이 질의에 걸리는가」뿐이다. 「누가 볼 수 있는가」는
`service.py` 가 `effective_visibility_clause` 로 만들어 **각 레인의 `LIMIT` 앞에**
끼워 넣는다(D-202). 두 관심사를 한 함수에 섞으면 레인을 하나 더 붙이는 날 권한을
빠뜨릴 자리가 생긴다 — 그리고 그 실수는 오류를 안 낸다.

## 레인이 셋인 이유

| 레인 | 무엇을 하나 | 왜 필요한가 |
|---|---|---|
| `trgm` | `text_fold LIKE '%접은 질의%'` + 낱말별 `LIKE` 의 OR | **후보 생성의 정본.** 한국어 어절 내부 부분일치를 이것만 한다 |
| `fts` | `to_tsvector @@ to_tsquery(낱말마다 앞부분 일치의 OR)`(낱말이 없으면 `plainto_tsquery`) | 어절 단위로 걸고 **낱말 뭉치의 순위를 매긴다.** 사람이 기억나는 대로 친 질의를 이 레인이 혼자 짊어진다(D-260) |
| `vector` | `embedding <=> 질의벡터` | 글자가 안 겹쳐도 뜻이 가까운 것. 모델이 없으면 이 레인은 그냥 없다 |

## 질문에서 뽑은 낱말 (D-536)

AI 에게는 사람이 **문장**을 쓴다(「연차 신청은 어떻게 하나요?」). 검색창 규칙(접은 질의 한 덩이 · 3자 이상 낱말의 AND)으로는
그 문장이 0건이다. 그래서 두 레인이 `search_text.keywords()` 가 뽑은 낱말(조사 · 어미 · 부탁 말 · 잇는 말을 걷은 2자 이상 낱말,
최대 여덟)을 **OR 로** 더 건다: 트라이그램 레인은 낱말마다 `LIKE` 가지를 붙이고 점수에 맞은 낱말의 가중치를 더하며, FTS 레인은
낱말마다 앞부분 일치(`낱말:*`)를 `|` 로 잇는다. 낱말은 `[0-9a-z가-힣]` 뿐이라 질의 문법이 들어갈 길이 없다 — 여기서 한 번 더 본다.
통합 검색 화면(`app/search`)은 이 규칙을 쓰지 않는다.

## 낱말의 무게 — 흔한 낱말은 가볍게 (D-568)

맞은 낱말 수만 더하면 「프로젝트」처럼 어디에나 있는 낱말이 「하이닉스」처럼 드문 낱말과 같은 몫을 받는다. 그래서 보는
사람의 가시 조각 안에서 낱말마다 **몇 조각에 있는가**(df)를 한 문장으로 세고(`keyword_weights`), 드문 낱말에 큰 무게를 준다:

    w = KEYWORD_HIT_WEIGHT × clamp(ln((N+1)/(df+1)) / ln(N+1), 0.25, 1.0)

`ts_stat` 대신 가시 조각 안에서 세는 이유는 둘이다 — 숨은 문서의 낱말 분포가 새지 않고, 보는 사람의 범위에서 드문 것이
그 사람에게 드문 것이다. 동의어 표가 덧붙인 낱말(`search_synonyms.expand`)은 그 절반이다. 세기가 시간 상한에 걸리면
모든 낱말이 같은 무게(예전 동작)로 돌아간다.

## 벡터를 문자열로 넘긴다

`app/ai/models.py::Vector` 와 같은 판단이다 — `pgvector` 파이썬 패키지를 폐쇄망
wheelhouse 에 넣지 않는다. `CAST(:q AS vector(384))` 로 명시 캐스팅하는 것이 중요하다:
psycopg 는 파이썬 문자열을 `text` 로 보내므로, 캐스팅을 안 하면 PG 가
`vector <=> text` 연산자를 못 찾아 그 자리에서 죽는다.
"""

from __future__ import annotations

import logging
import math
import re

from sqlalchemy import Float, Integer, case, cast, func, literal, literal_column, or_, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.sql import Select

from app.ai.catalog import FTS_CONFIG, VECTOR_DIM
from app.ai.models import DocumentChunk, Vector
from app.ai.retrieval import fusion
from app.core import search_synonyms
from app.core.search_text import fold, like_folded, like_pattern

# 질의 정규화와 트라이그램 가지의 정본은 검색 모듈이다. 두 검색창이 같은 문장을 다르게
# 다루면 「검색에서는 나오는데 AI 는 못 찾는다」가 되고, 그 차이는 아무 오류도 안 낸다.
from app.search.query import MAX_QUERY_CHARS, normalize, trgm_condition

logger = logging.getLogger("app.ai.retrieval")

__all__ = [
    "LANE_CANDIDATES",
    "MAX_QUERY_CHARS",
    "chunk_rows",
    "expand_keywords",
    "fts_condition_for",
    "fts_lane",
    "keyword_groups",
    "df_statement",
    "keyword_weights",
    "normalize_query",
    "trgm_condition_for",
    "trgm_lane",
    "vector_lane",
    "vector_literal",
    "word_condition",
    "visible_chunk_ids",
]

#: 한 레인이 융합에 내놓는 후보 수. 셋을 합쳐도 150 건이라 파이썬에서 접기에 가볍고,
#: 한 레인이 혼자 상위를 다 차지해도 다른 레인의 상위가 밀려나지 않을 만큼은 넉넉하다.
LANE_CANDIDATES = 50

#: 트라이그램 점수에 더하는 「맞은 낱말 하나」의 몫(가장 드문 낱말의 무게). 유사도(0 ~ 1)는 긴 chunk 에서 작아지므로,
#: 질문의 낱말을 여럿 담은 chunk 가 낱말 하나만 우연히 닮은 짧은 chunk 를 이기게 한다.
KEYWORD_HIT_WEIGHT = 0.5

#: 무게의 아래 한계(흔한 낱말도 0 이 되지는 않는다)와 확장어의 몫.
MIN_WEIGHT_FACTOR = 0.25
EXPANDED_WEIGHT_FACTOR = 0.5

#: 낱말이 될 수 있는 글자 — `search_text.keywords()` 와 같은 표다. FTS 질의 문자열에 넣기 전에 한 번 더 본다.
_SAFE_KEYWORD = re.compile(r"[0-9a-z가-힣]+")


def safe_keywords(keywords) -> tuple[str, ...]:
    """질의 문법이 섞일 수 없는 낱말만 남긴다(`& | ! : * ( ) ' % _` · 역슬래시 · 공백이 든 것은 버린다)."""
    return tuple(k for k in (keywords or ()) if isinstance(k, str) and _SAFE_KEYWORD.fullmatch(k))


def expand_keywords(words, *, limit: int = search_synonyms.MAX_EXPANSIONS) -> tuple[str, ...]:
    """동의어 표가 덧붙이는 낱말(D-568). 원래 낱말과 겹치지 않고, 역시 안전한 꼴만 남는다."""
    return safe_keywords(search_synonyms.expand(safe_keywords(words), limit=limit))


def normalize_query(raw: str | None) -> str:
    """앞뒤 공백 · 연속 공백 · **NFC** · 상한. 검색창과 같은 표시형이다.

    chunk 원문은 유니코드 표기를 맞추지 않은 채 저장된다(`app/ai/chunking.py` 는 글을 자르고
    앞뒤 공백을 걷을 뿐 NFC 로 바꾸지 않는다). 그래서 표기를 맞추는 일은 레인마다 다르다.
    트라이그램 레인은 양쪽을 접은 값으로 비교한다 — 질의는 `fold()` 를 지나고 원문은 DB 의
    접힌 사본(`text_fold`)으로 온다. FTS 레인은 이 표시형을 원문에 그대로 대므로 NFD 로
    저장된 chunk 는 그 레인에서 안 걸리고, 그 몫을 트라이그램 레인이 찾는다.
    """
    return normalize(raw)


def _ordered(stmt: Select) -> Select:
    """동점을 **항상 같은 순서로** 깬다.

    안 깨면 같은 질의가 요청마다 다른 순서를 내고, 융합 등수가 흔들려서 「어제와 다른
    답이 나온다」가 된다 — 원인을 찾을 수 없는 종류의 흔들림이다.
    """
    return stmt.order_by(DocumentChunk.document_id, DocumentChunk.ordinal, DocumentChunk.id)


def _contains(pattern: str):
    return like_folded(DocumentChunk.text_fold, pattern, stored=True)


def _all_words(keywords, expanded) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(질문의 낱말, 확장어) — 둘 다 안전한 꼴이고 서로 겹치지 않는다."""
    base = tuple(dict.fromkeys(safe_keywords(keywords)))
    extra = tuple(w for w in dict.fromkeys(safe_keywords(expanded)) if w not in base)
    return base, extra


def uniform_weights(keywords, expanded=()) -> dict[str, float]:
    """세지 않았을 때의 무게 — 질문의 낱말은 `KEYWORD_HIT_WEIGHT`, 확장어는 그 절반."""
    base, extra = _all_words(keywords, expanded)
    out = {w: KEYWORD_HIT_WEIGHT for w in base}
    out.update({w: KEYWORD_HIT_WEIGHT * EXPANDED_WEIGHT_FACTOR for w in extra})
    return out


def idf_factor(n: int, df: int) -> float:
    """조각 N 개 중 df 개에 있는 낱말의 무게 배율 — `[MIN_WEIGHT_FACTOR, 1.0]`. df 가 커질수록 작아진다(단조)."""
    n = max(0, int(n))
    df = max(0, min(int(df), n))
    if n <= 0:
        return 1.0
    raw = math.log((n + 1) / (df + 1)) / math.log(n + 1)
    return max(MIN_WEIGHT_FACTOR, min(1.0, raw))


def df_statement(words, *, narrowing=None) -> Select:
    """한 문장: 가시 조각 수(N)와 낱말마다 그 낱말이 든 조각 수(df). 열 순서는 `[N, df(words[0]), df(words[1]), …]` 이다."""
    columns = [func.count()] + [
        func.count().filter(word_condition(word)).label(f"df_{index}") for index, word in enumerate(words)
    ]
    stmt = select(*columns).select_from(DocumentChunk)
    if narrowing is not None:
        stmt = stmt.where(narrowing)
    return stmt


def keyword_weights(db, keywords, expanded=(), *, narrowing=None) -> dict[str, float]:
    """낱말 → 트라이그램 점수에 더할 무게(D-568). **한 문장**으로 전체 N 과 낱말별 df 를 센다.

    `narrowing` 은 권한 조건이다 — 보는 사람의 가시 조각 안에서만 센다(숨은 문서의 낱말 분포가 새지 않는다). 저장점
    안에서 돌려서 시간 상한에 걸려도 바깥 트랜잭션이 깨지지 않고, 그때는 모든 낱말이 같은 무게다. `db` 가 없으면
    같은 무게다(순수 SQL 조립 시험).
    """
    base, extra = _all_words(keywords, expanded)
    words = base + extra
    if not words:
        return {}
    if db is None:
        return uniform_weights(base, extra)
    stmt = df_statement(words, narrowing=narrowing)
    try:
        with db.begin_nested():
            row = db.execute(stmt).one()
    except DBAPIError:
        logger.warning("낱말 무게를 제때 세지 못해 같은 무게로 찾는다")
        return uniform_weights(base, extra)
    total = int(row[0] or 0)
    out: dict[str, float] = {}
    for index, word in enumerate(words):
        factor = idf_factor(total, int(row[index + 1] or 0))
        share = EXPANDED_WEIGHT_FACTOR if word in extra else 1.0
        out[word] = KEYWORD_HIT_WEIGHT * factor * share
    return out


def word_condition(word: str):
    """낱말 하나가 조각의 접힌 글에 들어 있는가(LIKE 부분일치). 세기의 「모든 낱말」 판정도 이것을 쓴다."""
    return _contains(like_pattern(fold(word)))


def _mixed_script(word: str) -> bool:
    has_hangul = any("가" <= ch <= "힣" for ch in word)
    has_latin = any(ch.isascii() and ch.isalnum() for ch in word)
    return has_hangul and has_latin


def keyword_groups(keywords, expanded=()) -> list[tuple[str, ...]]:
    """「모든 낱말이 든 문서」를 셀 때의 묶음(D-568). 질문의 낱말 하나와 그 대체어가 한 묶음이다.

    대체어는 둘이다: 혼합 토큰의 조각(「sk하이닉스」 뒤의 「하이닉스」 · 「sk」 — `search_text.keywords` 가 통째 낱말 바로 뒤에
    낸다)과 동의어 표의 짝(「네트워크」의 「nsx」). 묶음 안의 어느 하나만 있어도 그 낱말은 있는 것이다 — 「SK 하이닉스」라고
    쓴 문서는 「sk」 조각이 없어도 「하이닉스」 묶음을 채운다.
    """
    base, extra = _all_words(keywords, expanded)
    groups: list[list[str]] = []
    for word in base:
        head = groups[-1][0] if groups else None
        if head is not None and word != head and word in head and _mixed_script(head):
            groups[-1].append(word)
        else:
            groups.append([word])
    for word in extra:
        for group in groups:
            if any(word in search_synonyms.partners_of(member) for member in group):
                group.append(word)
                break
    return [tuple(group) for group in groups]


def _keyword_hits(keywords, expanded) -> list[tuple[str, object]]:
    """(낱말, LIKE 가지) 목록 — 질문의 낱말이 먼저, 확장어가 뒤다."""
    base, extra = _all_words(keywords, expanded)
    out = []
    for word in base + extra:
        folded = fold(word)
        if folded:
            out.append((word, _contains(like_pattern(folded))))
    return out


def trgm_condition_for(query: str, *, keywords=(), expanded=()):
    """트라이그램 레인의 조건 하나 — 검색창 가지(`trgm_condition`) OR 낱말별 LIKE 가지. 세기(`count_matching_documents`)와
    레인이 **같은 조건**을 쓴다(둘이 갈리면 「6건 중 8건을 보였다」가 된다)."""
    hits = [clause for _word, clause in _keyword_hits(keywords, expanded)]
    if hits:
        return or_(trgm_condition(query, _contains), *hits)
    return trgm_condition(query, _contains)


def trgm_lane(query: str, *, keywords=(), expanded=(), weights=None, narrowing=None,
              limit: int = LANE_CANDIDATES) -> Select:
    """트라이그램 레인. `ix_chunk_text_fold_trgm` 이 받는 모양이다.

    조건은 검색창과 **같은 가지**를 쓴다(`trgm_condition`): 접은 질의 전체 한 덩이, 그리고
    낱말이 여럿이고 접은 낱말이 전부 3자 이상이면 낱말별 AND 조합. 두 번째 가지가 없으면
    사람이 기억나는 대로 친 질의(`스프린트 정리`)를 이 레인이 통째로 놓친다 — S10 실측에서
    그 질의군의 MRR 이 **0.01** 이었다. 점수도 접힌 값끼리 잰다.

    `keywords` 를 주면(AI 의 질문, D-536) 낱말마다 `LIKE` 가지를 OR 로 더 붙이고 맞은 낱말의 무게(`weights`, 없으면
    낱말마다 `KEYWORD_HIT_WEIGHT`, 확장어는 절반)를 점수에 더한다.

    `narrowing` 은 권한 조건이고 **`LIMIT` 앞에** 들어간다. 없으면(전역 관리자) 안 건다.
    """
    hits = _keyword_hits(keywords, expanded)
    score = func.similarity(DocumentChunk.text_fold, fold(query))
    if hits:
        chosen = weights if weights is not None else uniform_weights(keywords, expanded)
        matched = None
        for word, clause in hits:
            weight = float(chosen.get(word, KEYWORD_HIT_WEIGHT))
            term = weight * cast(case((clause, 1), else_=0), Integer)
            matched = term if matched is None else matched + term
        score = score + matched
        condition = or_(trgm_condition(query, _contains), *[clause for _word, clause in hits])
    else:
        condition = trgm_condition(query, _contains)
    stmt = select(DocumentChunk.id, cast(score, Float).label("score")).where(condition)
    if narrowing is not None:
        stmt = stmt.where(narrowing)
    return _ordered(stmt.order_by(score.desc())).limit(limit)


# 🔴 설정 이름을 **바인드 파라미터가 아니라 리터럴로** 넣는다. 이유가 둘이다.
#
#   1. `to_tsvector($1::varchar, text)` 는 **함수가 아예 없다** — PG 의 두 인자짜리는
#      `to_tsvector(regconfig, text)` 이고, 파라미터에 붙는 `::varchar` 캐스팅은 그것을
#      못 찾는다. 이 자리는 실제로 그 오류를 한 번 냈다.
#   2. `::regconfig` 로 캐스팅해도 **인덱스를 못 탄다.** 인덱스 식은
#      `to_tsvector('simple'::regconfig, text)` 라는 **상수**이고, 파라미터는 상수가
#      아니라서 플래너가 두 식을 같다고 보지 않는다.
#
# 값은 우리 상수라 주입 경로가 없지만, 그 사실을 주석이 아니라 **검사**로 지킨다 —
# 언젠가 이 값이 설정에서 오게 되는 날 이 줄이 조용히 통과하면 안 된다.
if not FTS_CONFIG.isalpha():
    raise ValueError("FTS 설정 이름은 알파벳만 씁니다.")
_FTS_REGCONFIG = literal_column(f"'{FTS_CONFIG}'")


def _tsquery(query: str, keywords=(), expanded=()):
    """질의 → `tsquery`. 낱말이 없으면 `plainto_tsquery` 가 사용자가 친 글을 그대로 받는다.

    사람이 친 글은 `to_tsquery` 에 넣지 않는다 — 그쪽은 `&`·`|`·`!` 를 문법으로 읽어서, 검색창에 친 `A & B` 같은 글자가
    **문법 오류로 500** 을 만든다. 낱말(`keywords`)은 다르다: `[0-9a-z가-힣]` 만 남은 낱말이라(`safe_keywords`) 문법이 될 글자가
    없고, 낱말마다 앞부분 일치(`낱말:*` — 「신청」이 「신청은」에 걸린다)를 `|` 로 이어 하나라도 맞으면 건다(D-536). 확장어도
    같은 OR 에 든다.
    """
    base, extra = _all_words(keywords, expanded)
    words = base + extra
    if words:
        return func.to_tsquery(_FTS_REGCONFIG, literal(" | ".join(f"{w}:*" for w in words)))
    return func.plainto_tsquery(_FTS_REGCONFIG, query)


def _tsvector():
    """인덱스 식과 **글자 하나까지 같아야** 인덱스를 탄다."""
    return func.to_tsvector(_FTS_REGCONFIG, DocumentChunk.text_body)


def fts_condition_for(query: str, *, keywords=(), expanded=()):
    """전문검색 레인의 조건 하나 — 세기와 레인이 같은 조건을 쓴다."""
    return _tsvector().op("@@")(_tsquery(query, keywords, expanded))


def fts_lane(query: str, *, keywords=(), expanded=(), narrowing=None, limit: int = LANE_CANDIDATES) -> Select:
    """전문검색 레인. 어절 정확일치를 판별한다 — 후보 생성은 트라이그램의 몫이다. 낱말을 주면 OR 앞부분 일치다."""
    vector = _tsvector()
    tsquery = _tsquery(query, keywords, expanded)
    score = func.ts_rank(vector, tsquery)
    stmt = select(DocumentChunk.id, cast(score, Float).label("score")).where(
        vector.op("@@")(tsquery)
    )
    if narrowing is not None:
        stmt = stmt.where(narrowing)
    return _ordered(stmt.order_by(score.desc())).limit(limit)


def vector_literal(values) -> str:
    """실수 배열 → pgvector 의 텍스트 표현. 차원이 다르면 **여기서** 거절한다.

    PG 도 거절하지만 그 오류는 「어느 값이」를 안 알려 준다.
    """
    floats = [float(v) for v in values]
    if len(floats) != VECTOR_DIM:
        raise ValueError(f"질의 벡터가 {VECTOR_DIM}차원이어야 합니다(받은 값 {len(floats)}).")
    return "[" + ",".join(repr(v) for v in floats) + "]"


def vector_lane(
    embedding, *, narrowing=None, limit: int = LANE_CANDIDATES,
    max_distance: float = fusion.VECTOR_MAX_DISTANCE,
) -> Select:
    """벡터 레인. **코사인 거리**라 작을수록 가깝다 (D-211 의 `vector_cosine_ops`).

    🔴 **거리 상한이 이 레인의 「못 찾았다」다.** 최근접 이웃은 언제나 `limit` 건을
    내놓으므로, 상한이 없으면 아무 관계 없는 질의에도 근거가 생긴다(`fusion` 참조).

    벡터가 없는 chunk 는 아예 제외한다. `<=>` 는 NULL 에 NULL 을 돌려주므로 안 걸러도
    결과에는 안 나오지만, 조건을 명시해야 `ix_chunk_pending_embedding` 을 만든 것과 같은
    사실을 질의가 스스로 말한다 — 「벡터가 없는 chunk 는 이 레인의 대상이 아니다」.
    """
    target = cast(literal(vector_literal(embedding)), Vector(VECTOR_DIM))
    distance = DocumentChunk.embedding.op("<=>", return_type=Float)(target)
    stmt = select(DocumentChunk.id, cast(distance, Float).label("score")).where(
        DocumentChunk.embedding.isnot(None),
        distance <= float(max_distance),
    )
    if narrowing is not None:
        stmt = stmt.where(narrowing)
    return _ordered(stmt.order_by(distance.asc())).limit(limit)


def visible_chunk_ids(narrowing=None, *, limit: int = 1) -> Select:
    """권한을 통과한 chunk 가 하나라도 있는가 — **음성 테스트가 쓰는 자리**다.

    「Context 에 안 들어갔다」를 증명하려면 「그 사람에게는 후보가 0 이다」를 따로 볼 수
    있어야 한다. 답변 문자열을 보는 것은 증거가 아니다(D-202).
    """
    stmt = select(DocumentChunk.id)
    if narrowing is not None:
        stmt = stmt.where(narrowing)
    return stmt.limit(limit)


def chunk_rows(chunk_ids) -> Select:
    """융합이 고른 chunk 들의 본문과 앵커. **순서는 부르는 쪽이 이미 안다.**

    SQL 에 `ORDER BY` 를 안 거는 이유는 융합 순서가 SQL 로 표현되지 않기 때문이다 —
    여기서 아무 순서나 주고 파이썬이 다시 정렬한다.
    """
    ids = [str(cid) for cid in chunk_ids]
    return select(DocumentChunk).where(DocumentChunk.id.in_(ids))
