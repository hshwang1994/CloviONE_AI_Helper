"""세 레인의 SQL — 각각 **chunk id 를 등수대로** 낸다 (D-209 · D-210).

## 이 파일이 안 하는 것: 권한

여기서 만드는 것은 「무엇이 질의에 걸리는가」뿐이다. 「누가 볼 수 있는가」는
`service.py` 가 `effective_visibility_clause` 로 만들어 **각 레인의 `LIMIT` 앞에**
끼워 넣는다(D-202). 두 관심사를 한 함수에 섞으면 레인을 하나 더 붙이는 날 권한을
빠뜨릴 자리가 생긴다 — 그리고 그 실수는 오류를 안 낸다.

## 레인이 셋인 이유

| 레인 | 무엇을 하나 | 왜 필요한가 |
|---|---|---|
| `trgm` | `text ILIKE '%질의%'` | **후보 생성의 정본.** 한국어 어절 내부 부분일치를 이것만 한다 |
| `fts` | `to_tsvector @@ plainto_tsquery` | 어절 단위로 걸고 **낱말 뭉치의 순위를 매긴다.** 사람이 기억나는 대로 친 질의를 이 레인이 혼자 짊어진다(D-260) |
| `vector` | `embedding <=> 질의벡터` | 글자가 안 겹쳐도 뜻이 가까운 것. 모델이 없으면 이 레인은 그냥 없다 |

## 벡터를 문자열로 넘긴다

`app/ai/models.py::Vector` 와 같은 판단이다 — `pgvector` 파이썬 패키지를 폐쇄망
wheelhouse 에 넣지 않는다. `CAST(:q AS vector(384))` 로 명시 캐스팅하는 것이 중요하다:
psycopg 는 파이썬 문자열을 `text` 로 보내므로, 캐스팅을 안 하면 PG 가
`vector <=> text` 연산자를 못 찾아 그 자리에서 죽는다.
"""

from __future__ import annotations

from sqlalchemy import Float, cast, func, literal, literal_column, select
from sqlalchemy.sql import Select

from app.ai.catalog import FTS_CONFIG, VECTOR_DIM
from app.ai.models import DocumentChunk, Vector
from app.ai.retrieval import fusion

# 질의 정규화와 `ILIKE` escape 의 정본은 검색 모듈이다. 두 검색창이 같은 문장을 다르게
# 다루면 「검색에서는 나오는데 AI 는 못 찾는다」가 되고, 그 차이는 아무 오류도 안 낸다.
from app.search.query import MAX_QUERY_CHARS, normalize, trgm_condition

__all__ = [
    "LANE_CANDIDATES",
    "MAX_QUERY_CHARS",
    "chunk_rows",
    "fts_lane",
    "normalize_query",
    "trgm_lane",
    "vector_lane",
    "vector_literal",
    "visible_chunk_ids",
]

#: 한 레인이 융합에 내놓는 후보 수. 셋을 합쳐도 150 건이라 파이썬에서 접기에 가볍고,
#: 한 레인이 혼자 상위를 다 차지해도 다른 레인의 상위가 밀려나지 않을 만큼은 넉넉하다.
LANE_CANDIDATES = 50


def normalize_query(raw: str | None) -> str:
    """앞뒤 공백 · 연속 공백 · **NFC**. 검색창과 같은 정규화를 지난다.

    NFC 를 여기서도 하는 이유는 `app/search/query.py` 와 같다: macOS 에서 복사한 글은
    NFD 로 들어오고, 색인 쪽(`chunking`)이 지나는 정규화와 표기가 다르면 눈에 같아
    보이는 글자가 안 걸린다.
    """
    return normalize(raw)


def _ordered(stmt: Select) -> Select:
    """동점을 **항상 같은 순서로** 깬다.

    안 깨면 같은 질의가 요청마다 다른 순서를 내고, 융합 등수가 흔들려서 「어제와 다른
    답이 나온다」가 된다 — 원인을 찾을 수 없는 종류의 흔들림이다.
    """
    return stmt.order_by(DocumentChunk.document_id, DocumentChunk.ordinal, DocumentChunk.id)


def _contains(pattern: str):
    return DocumentChunk.text_body.ilike(pattern, escape="\\")


def trgm_lane(query: str, *, narrowing=None, limit: int = LANE_CANDIDATES) -> Select:
    """트라이그램 레인. `ix_chunk_text_trgm` 이 받는 모양이다.

    조건은 검색창과 **같은 가지**를 쓴다(`trgm_condition`): 질의 전체 한 덩이, 그리고
    낱말이 여럿이고 전부 3자 이상이면 낱말별 AND 조합. 두 번째 가지가 없으면 사람이
    기억나는 대로 친 질의(`스프린트 정리`)를 이 레인이 통째로 놓친다 — S10 실측에서
    그 질의군의 MRR 이 **0.01** 이었다.

    `narrowing` 은 권한 조건이고 **`LIMIT` 앞에** 들어간다. 없으면(전역 관리자) 안 건다.
    """
    score = func.similarity(DocumentChunk.text_body, query)
    stmt = select(DocumentChunk.id, cast(score, Float).label("score")).where(
        trgm_condition(query, _contains)
    )
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


def _tsquery(query: str):
    """질의 → `tsquery`. `plainto_tsquery` 는 사용자가 친 글을 그대로 받는다.

    `to_tsquery` 를 안 쓴다 — 그쪽은 `&`·`|`·`!` 를 문법으로 읽어서, 사람이 검색창에
    친 `A & B` 같은 글자가 **문법 오류로 500** 을 만든다. 사용자가 친 것은 질의어이지
    질의 문법이 아니다.
    """
    return func.plainto_tsquery(_FTS_REGCONFIG, query)


def _tsvector():
    """인덱스 식과 **글자 하나까지 같아야** 인덱스를 탄다."""
    return func.to_tsvector(_FTS_REGCONFIG, DocumentChunk.text_body)


def fts_lane(query: str, *, narrowing=None, limit: int = LANE_CANDIDATES) -> Select:
    """전문검색 레인. 어절 정확일치를 판별한다 — 후보 생성은 트라이그램의 몫이다."""
    vector = _tsvector()
    tsquery = _tsquery(query)
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
