"""Retrieval — **권한이 먼저다** (D-202).

    User → effective_visibility_clause(principal)   ← D-194 의 그 함수, AI 도 같은 것을 쓴다
         → 후보 집합 결정                             ← 권한 없는 행은 여기서 이미 없다
         → Hybrid Retrieval (pg_trgm ⊕ FTS ⊕ pgvector, RRF)
         → Context 조립 → Model Gateway.generate()

## 🔴 금지: 전체 검색 → LLM 전달 → 「숨기라고 지시」

권한 조건은 각 레인의 **`LIMIT` 앞에** 들어간다. 뒤에 걸면 범위 밖 chunk 가 상한을
채워서 내 범위 결과가 한 건도 안 남는데, 화면에는 오류가 아니라 「결과 없음」으로만
보인다 — 아무도 신고하지 않는다(Z6). 그리고 그것보다 나쁜 쪽은, 상한 안에 남은 범위 밖
chunk 가 그대로 Context 에 실리는 것이다.

**증명 방식도 정해져 있다**(D-202): 권한 없는 사용자의 질의에서 그 데이터가 **Context 에
들어가지 않음**을 음성 테스트로 본다. 답변에 안 나왔다는 것은 증거가 아니다 — 모델이
그때 안 쓴 것일 수도 있다. 그래서 이 모듈은 답변 문자열이 아니라 **`RetrievalResult`**
를 돌려주고, 시험은 그 안의 인용 목록을 본다.

## 권한을 chunk 에 안 구웠기 때문에 이 질의가 유일한 판정이다 (D-256)

`document_chunks` 에는 권한 컬럼이 없다. 그래서 반영 지연이 0 이고 — 그 대신 **판정을
빠뜨릴 자리가 여기 하나뿐**이다. `scripts/check_visibility_single_source.py` 가 이
파일의 도달을 확인한다.

## 보관된 문서는 후보가 아니다

`archived` 문서는 목록에서 이미 안 보인다. 검색은 찾아 주면서 AI 는 안 찾아 주는 것도,
반대도 이상하다 — 그런데 인용은 **답변의 근거**라 「보관해 둔 옛 문서를 근거로 답했다」
쪽이 훨씬 나쁘다. 그래서 뺀다. 찾고 싶은 사람은 그 문서를 보관 해제하면 된다.

## 조각과 문서, 두 단위 (D-567)

`/ai` 화면은 **조각** 단위다 — 같은 문서의 여러 자리가 각각 인용으로 선다(어느 문단인지가 답의 근거다).
AI 도우미의 `search_documents` 는 **문서** 단위다(`distinct_documents=True`) — 융합 순서에서 문서마다 첫 조각만
남기고 `offset` 으로 쪽을 넘긴다. 「문서 6개」라고 말하려면 조각이 아니라 문서를 세어야 하고, 그 수는
`count_matching_documents` 가 같은 조건 · 같은 권한 절로 따로 센다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.ai import catalog
from app.ai.gateway import contract
from app.ai.models import SOURCE_FILE, DocumentChunk
from app.ai.retrieval import citation as citation_mod
from app.ai.retrieval import fusion, query as query_mod
from app.authz.visibility import (
    RESOURCE_KNOWLEDGE_DOC,
    context_for_user,
    effective_visibility_clause,
)
from app.core.search_text import keywords as question_keywords
from app.core.search_text import normalize_question
from app.knowledge.models import Document, KnowledgeSpace
from app.storage.models import File

logger = logging.getLogger("app.ai.retrieval")

__all__ = [
    "MatchCount", "RetrievalResult", "MAX_TOP_K", "TOP_K", "count_matching_documents", "retrieve",
    "visible_document_ids",
]

#: Context 에 싣는 인용 수의 기본값. 여덟이면 e5-small 의 chunk(최대 1,000자) 기준
#: 8,000자 안쪽이라 `app/llm/prompt.py::MAX_BODY_CHARS`(20,000) 를 넘지 않는다.
TOP_K = 8
#: 화면이 요청할 수 있는 상한. 넘겨 봐야 프롬프트가 잘리므로 여기서 자른다.
MAX_TOP_K = 20
#: 문서 단위 검색이 쪽을 넘길 수 있는 상한(offset). 그 뒤는 화면(`/knowledge`)에서 본다.
MAX_OFFSET = 40
#: 문서 단위로 접을 때 레인 하나가 내는 조각 후보 수. 한 문서의 조각 여럿이 후보를 나눠 가지므로 조각 단위(50)보다 넉넉하다 —
#: `MAX_OFFSET + MAX_TOP_K` 문서를 고를 수 있어야 쪽 넘기기가 뜻이 있다.
DISTINCT_LANE_CANDIDATES = 80

#: 인용 한 줄에 싣는 글자 수. 화면이 접어서 보여 주는 미리보기이고, 답변에 실리는
#: 본문은 이것이 아니라 chunk 전체다.
EXCERPT_CHARS = 240


@dataclass(frozen=True)
class RetrievalResult:
    """검색 결과 하나. **이것이 곧 Context 다** — 답변은 이 목록 밖을 못 본다."""

    query: str
    citations: tuple[citation_mod.Citation, ...] = ()
    #: 모델에 가는 질문 원문(NFC · 공백 정리, 100자로 자르지 않는다). `query` 는 화면에 다시 싣는 표시형이다.
    question: str = ""
    #: 질문에서 뽑아 두 낱말 레인에 OR 로 건 낱말(D-536). 「무엇을 찾았는데 없었나」를 말할 때 쓴다.
    keywords: tuple[str, ...] = ()
    #: 저장소 안 동의어 표가 덧붙인 낱말(D-568). 절반 가중으로 함께 찾는다. 「함께 찾은 낱말」로 말한다.
    expanded: tuple[str, ...] = ()
    #: 세 레인이 각각 몇 건을 냈는가. 「왜 안 나오지」에 답하는 유일한 값이다.
    lane_counts: dict[str, int] = field(default_factory=dict)
    #: 벡터 레인이 안 돈 이유. 돌았으면 None 이다.
    vector_status: str | None = None
    #: 문서 단위로 접었을 때 — 융합 후보 안에서 서로 다른 문서의 수(이 쪽의 앞뒤를 포함). 조각 단위면 None.
    distinct_total: int | None = None
    #: 문서 단위로 접었을 때 — 후보 조각이 **전부** 의미 검색 레인에서만 나온 문서(낱말이 하나도 안 걸렸다). 세기가 이 문서를
    #: 더해야 「N건 중 M건」의 N 이 보인 문서를 다 품는다(`count_matching_documents(also_documents=)`).
    semantic_only_documents: tuple[str, ...] = ()

    @property
    def empty(self) -> bool:
        return not self.citations

    @property
    def semantic(self) -> bool:
        """의미 검색이 실제로 돌았는가. 화면이 이 값으로 안내 문구를 고른다."""
        return self.vector_status is None

    def context_text(self) -> str:
        """모델에게 넘길 **데이터**. System Instruction 이 아니다 (D-202).

        인용 번호를 함께 적는다 — 답변이 「[2]」라고 쓰면 화면이 두 번째 인용을
        가리킬 수 있다. 번호가 없으면 답변과 근거를 사람이 눈으로 맞춰야 한다.
        """
        parts: list[str] = []
        for index, cite in enumerate(self.citations, start=1):
            head = f"[{index}] {cite.document_title}"
            if cite.where:
                head = f"{head} — {cite.where}"
            parts.append(f"{head}\n{cite.text_for_context}")
        return "\n\n".join(parts)

    def as_dict(self) -> dict:
        return {
            "query": self.query,
            "citations": [c.as_dict() for c in self.citations],
            "keywords": list(self.keywords),
            "expanded_keywords": list(self.expanded),
            "lane_counts": dict(self.lane_counts),
            "semantic": self.semantic,
            "vector_notice": (
                None if self.vector_status is None
                else contract.notice_for(self.vector_status)
            ),
        }


def visible_document_ids(db: Session, user, *, project_id: str | None = None, author_id: str | None = None):
    """이 사람이 볼 수 있는 문서 id 의 **서브쿼리**.

    파이썬으로 id 를 먼저 뽑지 않는다 — 문서가 수천 건이면 그 목록이 그대로 SQL
    파라미터가 되고, 무엇보다 **상한 앞에** 걸려야 하는 조건인데 파이썬 왕복이 끼면
    그 순서를 지키기 어렵다(`app/authz/visibility.py::_project_id_subquery` 와 같은 이유).

    `project_id` 는 그 프로젝트가 소유한 공간의 문서로 **더 좁힌다**(문서 목록의 `project_id` 와 같은 판정). 권한은
    그대로 먼저 걸린다 — 볼 수 없는 프로젝트를 넘기면 조건을 만족하는 공간이 없어 0건이 될 뿐이다.

    `author_id` 는 그 사람이 만든 문서로 더 좁힌다(문서 화면 `mine=true` 와 같은 `created_by` 판정). 도우미는 묻는 사람의
    id 만 넘긴다(「내 문서 중 VMware 관련」) — 다른 사람의 id 를 받는 인자는 없다.
    """
    ctx = context_for_user(db, user)
    clause = effective_visibility_clause(ctx, RESOURCE_KNOWLEDGE_DOC)
    stmt = select(Document.id).where(Document.archived.is_(False))
    if clause is not None:
        stmt = stmt.where(clause)
    if author_id:
        stmt = stmt.where(Document.created_by == author_id)
    if project_id:
        from app.core.ownership import OWNER_PROJECT

        stmt = stmt.where(Document.space_id.in_(
            select(KnowledgeSpace.id).where(
                KnowledgeSpace.owner_kind == OWNER_PROJECT, KnowledgeSpace.owner_project_id == project_id,
            )
        ))
    return stmt


def _narrowing(db: Session, user, *, project_id: str | None = None, author_id: str | None = None):
    """chunk 에 거는 권한 조건. **모든 레인이 이것을 `LIMIT` 앞에 받는다.**"""
    return DocumentChunk.document_id.in_(visible_document_ids(db, user, project_id=project_id, author_id=author_id))


def _query_embedding(gateway: contract.Gateway, text: str):
    """질의 벡터 하나. 못 만들면 `(None, 이유)` 다 — 예외를 올리지 않는다.

    🔴 `kind=query` 를 반드시 넘긴다. e5 계열은 질의와 본문에 다른 접두사를 요구하고,
    안 붙이면 **오류가 하나도 안 나면서** 품질만 떨어진다(S9 가 그것만 수치로 확인했다 —
    두 접두사의 벡터 코사인 거리 0.060378).
    """
    result = gateway.embed([text], kind=catalog.KIND_QUERY)
    if not result.ok or not result.vectors:
        return None, (result.status or contract.STATUS_FAILED)
    return result.vectors[0], None


def _rank(db: Session, stmt) -> list[str]:
    return [str(row[0]) for row in db.execute(stmt).all()]


def _first_chunk_per_document(db: Session, fused, *, offset: int, limit: int):
    """융합 순서에서 **문서마다 첫 조각만** 남기고 쪽을 자른다.

    (고른 융합 행들, 서로 다른 문서 수, 의미 검색에서만 나온 문서 id 들)을 돌려준다. 「의미 검색에서만」은 그 문서의 후보 조각
    어느 것도 낱말 레인에 걸리지 않았다는 뜻이다(`fusion.semantic_only`).
    """
    keys = [row.key for row in fused]
    if not keys:
        return [], 0, ()
    owner = dict(db.execute(
        select(DocumentChunk.id, DocumentChunk.document_id).where(DocumentChunk.id.in_(keys))
    ).all())
    seen: set[str] = set()
    worded: set[str] = set()
    picked = []
    for row in fused:
        document_id = owner.get(row.key)
        if document_id is None:
            continue
        if not fusion.semantic_only(row.lanes):
            worded.add(document_id)
        if document_id in seen:
            continue
        seen.add(document_id)
        picked.append(row)
    semantic_only = tuple(sorted(seen - worded))
    return picked[offset:offset + limit], len(picked), semantic_only


def retrieve(
    db: Session,
    user,
    *,
    raw_query: str | None,
    gateway: contract.Gateway,
    top_k: int = TOP_K,
    lane_candidates: int = query_mod.LANE_CANDIDATES,
    distinct_documents: bool = False,
    offset: int = 0,
    project_id: str | None = None,
    author_id: str | None = None,
) -> RetrievalResult:
    """질의 → 권한을 통과한 인용 목록. **예외를 올리지 않는다.**

    생성 Provider 가 없어도 여기는 끝까지 돈다(D-201 의 경계). 임베딩 모델까지 없으면
    벡터 레인만 빠지고 키워드 두 레인으로 답한다 — 그 사실을 `vector_status` 가 말한다.

    ``distinct_documents`` 는 문서 단위다(모듈 머리말) — 융합 뒤 문서마다 첫 조각만 남기고 ``offset`` 부터 ``top_k`` 건을
    낸다. ``project_id`` 는 그 프로젝트 공간의 문서로 좁힌다(권한 절은 그대로 먼저 걸린다).
    """
    text = query_mod.normalize_query(raw_query)
    if not text:
        return RetrievalResult(query="")
    # 낱말은 표시형(100자)이 아니라 질문 원문에서 뽑는다 — 긴 질문의 뒤쪽 낱말이 잘려 나가지 않게(D-536).
    question = normalize_question(raw_query)
    words = question_keywords(question)
    expanded = query_mod.expand_keywords(words)

    top_k = max(1, min(int(top_k or TOP_K), MAX_TOP_K))
    offset = max(0, min(int(offset or 0), MAX_OFFSET)) if distinct_documents else 0
    if distinct_documents:
        lane_candidates = max(int(lane_candidates or 0), DISTINCT_LANE_CANDIDATES)
    narrowing = _narrowing(db, user, project_id=project_id, author_id=author_id)
    weights = query_mod.keyword_weights(db, words, expanded, narrowing=narrowing)

    rankings: dict[str, list[str]] = {
        fusion.LANE_TRGM: _rank(
            db, query_mod.trgm_lane(text, keywords=words, expanded=expanded, weights=weights, narrowing=narrowing,
                                    limit=lane_candidates)
        ),
        fusion.LANE_FTS: _rank(
            db, query_mod.fts_lane(text, keywords=words, expanded=expanded, narrowing=narrowing,
                                   limit=lane_candidates)
        ),
    }

    vector_status: str | None = None
    embedding, reason = _query_embedding(gateway, text)
    if embedding is None:
        vector_status = reason
    else:
        try:
            rankings[fusion.LANE_VECTOR] = _rank(
                db, query_mod.vector_lane(embedding, narrowing=narrowing, limit=lane_candidates)
            )
        except ValueError:
            # 차원이 안 맞는다 — 모델을 바꿨는데 마이그레이션을 안 한 상태다. 키워드
            # 두 레인으로 계속 답한다. 검색이 통째로 죽는 것보다 낫다.
            logger.exception("질의 벡터의 차원이 스키마와 다르다")
            vector_status = contract.STATUS_FAILED

    lane_counts = {lane: len(keys) for lane, keys in rankings.items()}
    distinct_total: int | None = None
    semantic_only: tuple[str, ...] = ()
    if distinct_documents:
        fused, distinct_total, semantic_only = _first_chunk_per_document(
            db, fusion.fuse(rankings), offset=offset, limit=top_k,
        )
    else:
        fused = fusion.fuse(rankings, limit=top_k)
    if not fused:
        return RetrievalResult(query=text, question=question, keywords=words, expanded=expanded,
                               lane_counts=lane_counts, vector_status=vector_status, distinct_total=distinct_total,
                               semantic_only_documents=semantic_only)

    citations = _load_citations(db, fused)
    return RetrievalResult(
        query=text, question=question, keywords=words, expanded=expanded, citations=citations,
        lane_counts=lane_counts, vector_status=vector_status, distinct_total=distinct_total,
        semantic_only_documents=semantic_only,
    )


@dataclass(frozen=True)
class MatchCount:
    """문서 단위 검색의 수 둘(D-567). 둘 다 같은 권한 절 안에서 센다."""

    #: 찾아본 낱말(또는 질의 통째) 가운데 하나라도 걸린 문서 — 목록이 이 집합에서 나오므로 `total` 이 이것이다.
    documents: int
    #: 질문의 낱말 묶음(`query.keyword_groups`)을 **모두** 채운 문서. 「X 관련 문서가 몇 개야」에 더 가까운 수다.
    with_every_word: int
    #: 낱말이 하나도 안 걸렸는데 의미 검색이 찾은 문서(`also_documents` 가운데 위 집합 밖). 보인 목록이 이 문서를 품을 수 있다.
    semantic_only: int = 0

    @property
    def total(self) -> int:
        """목록이 나올 수 있는 집합 전체 — 낱말이 걸린 문서와 의미 검색만 찾은 문서의 합."""
        return self.documents + self.semantic_only


def count_matching_documents(
    db: Session, user, *, text: str, words=(), expanded=(), project_id: str | None = None, also_documents=(),
    author_id: str | None = None,
) -> MatchCount | None:
    """낱말 두 레인의 조건(트라이그램 OR 낱말 LIKE OR tsquery)에 걸리는 **서로 다른 문서의 수** — 같은 권한 절 안에서.

    `search_documents` 의 `total` 이다. 레인은 후보를 상한(`LANE_CANDIDATES`)으로 자르므로 「몇 건인가」는 따로 세어야
    맞다. 조건은 레인과 **같은 것**이다(`trgm_condition_for` · `fts_condition_for`) — 갈리면 「6건 중 8건」이 된다. 한 문장으로
    두 수를 낸다: 하나라도 걸린 문서와 낱말 묶음을 모두 채운 문서(`MatchCount`).

    시간 초과(문 상한 3초)면 `None` 이다 — 그 수를 지어내지 않는다. 저장점 안에서 돌려서 시간 초과가 바깥 트랜잭션을 깨지
    않는다(읽기 전용 세션의 다음 문이 그대로 돈다). 벡터 레인은 세지 않는다 — 최근접 이웃은 언제나 상한만큼 나오므로
    「몇 건인가」에 답하지 못한다. 대신 ``also_documents``(의미 검색만 찾은 후보 문서, `RetrievalResult.semantic_only_documents`)
    가운데 낱말 조건 밖의 것을 `semantic_only` 로 따로 세어, 보인 목록이 언제나 전체 수 안에 들게 한다.
    """
    text = query_mod.normalize_query(text)
    if not text:
        return MatchCount(documents=0, with_every_word=0)
    also = tuple(dict.fromkeys(str(d) for d in (also_documents or ()) if d))
    narrowing = _narrowing(db, user, project_id=project_id, author_id=author_id)
    condition = or_(
        query_mod.trgm_condition_for(text, keywords=words, expanded=expanded),
        query_mod.fts_condition_for(text, keywords=words, expanded=expanded),
    )
    groups = query_mod.keyword_groups(words, expanded)
    columns = [DocumentChunk.document_id.label("document_id")] + [
        func.bool_or(or_(*[query_mod.word_condition(word) for word in group])).label(f"g{index}")
        for index, group in enumerate(groups)
    ]
    per_document = (
        select(*columns).where(condition).where(narrowing).group_by(DocumentChunk.document_id).subquery()
    )
    every = and_(*[per_document.c[f"g{index}"] for index in range(len(groups))]) if groups else None
    stmt = select(
        func.count(),
        func.count().filter(every) if every is not None else func.count(),
    ).select_from(per_document)
    try:
        with db.begin_nested():
            documents, with_every = db.execute(stmt).one()
            inside: set[str] = set()
            if also:
                inside = {
                    str(row[0]) for row in db.execute(
                        select(DocumentChunk.document_id).where(condition).where(narrowing)
                        .where(DocumentChunk.document_id.in_(also)).distinct()
                    ).all()
                }
    except DBAPIError:
        logger.warning("문서 검색의 전체 수를 제때 세지 못했다(시간 초과)")
        return None
    return MatchCount(documents=int(documents or 0), with_every_word=int(with_every or 0),
                      semantic_only=len([d for d in also if d not in inside]))


def _load_citations(db: Session, fused) -> tuple[citation_mod.Citation, ...]:
    """융합이 고른 chunk → 인용. 문서 제목과 파일 이름을 **한 질의씩**으로 붙인다."""
    order = {row.key: index for index, row in enumerate(fused)}
    lanes_of = {row.key: row.lanes for row in fused}
    rows = list(db.execute(query_mod.chunk_rows(order.keys())).scalars().all())
    if not rows:
        return ()

    titles = dict(
        db.execute(
            select(Document.id, Document.title).where(
                Document.id.in_({row.document_id for row in rows})
            )
        ).all()
    )
    file_ids = {row.file_id for row in rows if row.source_kind == SOURCE_FILE and row.file_id}
    filenames = (
        dict(db.execute(select(File.id, File.filename).where(File.id.in_(file_ids))).all())
        if file_ids else {}
    )

    rows.sort(key=lambda row: order.get(row.id, len(order)))
    return tuple(
        citation_mod.build(
            row,
            document_title=titles.get(row.document_id) or "(제목 없음)",
            filename=filenames.get(row.file_id, "") if row.file_id else "",
            lanes=lanes_of.get(row.id, ()),
            excerpt_chars=EXCERPT_CHARS,
        )
        for row in rows
    )
