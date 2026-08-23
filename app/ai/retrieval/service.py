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
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
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
from app.knowledge.models import Document
from app.storage.models import File

logger = logging.getLogger("app.ai.retrieval")

__all__ = ["RetrievalResult", "MAX_TOP_K", "TOP_K", "retrieve", "visible_document_ids"]

#: Context 에 싣는 인용 수의 기본값. 여덟이면 e5-small 의 chunk(최대 1,000자) 기준
#: 8,000자 안쪽이라 `app/llm/prompt.py::MAX_BODY_CHARS`(20,000) 를 넘지 않는다.
TOP_K = 8
#: 화면이 요청할 수 있는 상한. 넘겨 봐야 프롬프트가 잘리므로 여기서 자른다.
MAX_TOP_K = 20

#: 인용 한 줄에 싣는 글자 수. 화면이 접어서 보여 주는 미리보기이고, 답변에 실리는
#: 본문은 이것이 아니라 chunk 전체다.
EXCERPT_CHARS = 240


@dataclass(frozen=True)
class RetrievalResult:
    """검색 결과 하나. **이것이 곧 Context 다** — 답변은 이 목록 밖을 못 본다."""

    query: str
    citations: tuple[citation_mod.Citation, ...] = ()
    #: 세 레인이 각각 몇 건을 냈는가. 「왜 안 나오지」에 답하는 유일한 값이다.
    lane_counts: dict[str, int] = field(default_factory=dict)
    #: 벡터 레인이 안 돈 이유. 돌았으면 None 이다.
    vector_status: str | None = None

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
            "lane_counts": dict(self.lane_counts),
            "semantic": self.semantic,
            "vector_notice": (
                None if self.vector_status is None
                else contract.notice_for(self.vector_status)
            ),
        }


def visible_document_ids(db: Session, user):
    """이 사람이 볼 수 있는 문서 id 의 **서브쿼리**.

    파이썬으로 id 를 먼저 뽑지 않는다 — 문서가 수천 건이면 그 목록이 그대로 SQL
    파라미터가 되고, 무엇보다 **상한 앞에** 걸려야 하는 조건인데 파이썬 왕복이 끼면
    그 순서를 지키기 어렵다(`app/authz/visibility.py::_project_id_subquery` 와 같은 이유).
    """
    ctx = context_for_user(db, user)
    clause = effective_visibility_clause(ctx, RESOURCE_KNOWLEDGE_DOC)
    stmt = select(Document.id).where(Document.archived.is_(False))
    return stmt if clause is None else stmt.where(clause)


def _narrowing(db: Session, user):
    """chunk 에 거는 권한 조건. **모든 레인이 이것을 `LIMIT` 앞에 받는다.**"""
    return DocumentChunk.document_id.in_(visible_document_ids(db, user))


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


def retrieve(
    db: Session,
    user,
    *,
    raw_query: str | None,
    gateway: contract.Gateway,
    top_k: int = TOP_K,
    lane_candidates: int = query_mod.LANE_CANDIDATES,
) -> RetrievalResult:
    """질의 → 권한을 통과한 인용 목록. **예외를 올리지 않는다.**

    생성 Provider 가 없어도 여기는 끝까지 돈다(D-201 의 경계). 임베딩 모델까지 없으면
    벡터 레인만 빠지고 키워드 두 레인으로 답한다 — 그 사실을 `vector_status` 가 말한다.
    """
    text = query_mod.normalize_query(raw_query)
    if not text:
        return RetrievalResult(query="")

    top_k = max(1, min(int(top_k or TOP_K), MAX_TOP_K))
    narrowing = _narrowing(db, user)

    rankings: dict[str, list[str]] = {
        fusion.LANE_TRGM: _rank(
            db, query_mod.trgm_lane(text, narrowing=narrowing, limit=lane_candidates)
        ),
        fusion.LANE_FTS: _rank(
            db, query_mod.fts_lane(text, narrowing=narrowing, limit=lane_candidates)
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

    fused = fusion.fuse(rankings, limit=top_k)
    lane_counts = {lane: len(keys) for lane, keys in rankings.items()}
    if not fused:
        return RetrievalResult(query=text, lane_counts=lane_counts, vector_status=vector_status)

    citations = _load_citations(db, fused)
    return RetrievalResult(
        query=text, citations=citations, lane_counts=lane_counts, vector_status=vector_status
    )


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
