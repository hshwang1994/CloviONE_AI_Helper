"""AI 검색은 사람이 쓴 질문으로 찾는다 — 실 PostgreSQL 위의 낱말 레인 (D-536).

검색창 규칙(접은 질의 한 덩이 · 3자 이상 낱말의 AND)은 기억나는 구절에 맞다. AI 에게 쓰는 문장 — 「휴가 신청은 어떻게 하나요?」 —
은 그 규칙으로 0건이었다: 2자 낱말(「휴가」)이 AND 조합을 끄고, 「어떻게」 · 「하나요」가 FTS 의 AND 를 깼다. 그래서 AI 의 검색은
질문에서 뽑은 낱말을 OR 로 더 건다. 여기서 지키는 것:

* 문장 질문이 실제로 걸린다 — 그리고 **같은 질문을 낱말 없이 돌리면 0건**이다(이 시험이 무엇을 가르는지 반례로 보인다).
* 맞은 낱말이 많은 chunk 가 위다(점수에 맞은 낱말 수가 들어간다).
* 결과가 무엇을 찾았는지 말한다(`keywords`) — 「찾지 못했습니다」 문장이 그 낱말을 쓴다.
* 모델에는 질문 원문이 간다 — 100자 표시형으로 잘리지 않는다.
* 권한은 그대로다 — 낱말 가지도 `LIMIT` 앞의 권한 조건 안에서 돈다(볼 수 없는 문서는 낱말로도 안 나온다).

qa-contract-change: 채팅 · 작업 공간 질문의 옛 `answer()` 를 걷었다(D-535 - 질문은 AI 도우미 한 차례가 답한다). 근거 검색 → 생성의 같은 문(생성이 막혀도 인용이 나간다, 모델은 인용 밖을 못 본다, 근거가 없으면 부르지 않는다, 질문 원문이 간다)은 문서 초안(`draft_document`)이 그대로 지나므로 같은 단언을 그 소비자로 잰다.
"""

from __future__ import annotations

import pytest

from app.ai import catalog
from app.ai.gateway import contract
from app.ai.index import service as index_service
from app.ai.retrieval import answer as answer_mod
from app.ai.retrieval import fusion
from app.ai.retrieval import query as query_mod
from app.ai.retrieval import service as retrieval
from app.knowledge import versions
from app.knowledge.models import Document, KnowledgeSpace
from app.org.constants import DEFAULT_ORG_ID
from tests.fakes.ai import offline_runtime

pytestmark = pytest.mark.integration


class NoEmbed(contract.EmbedAdapter):
    """의미 검색 모델이 없는 설치(흔한 상태) — 낱말 두 레인만 돈다. 이 파일은 낱말 레인을 보므로 벡터를 끈다."""

    name = "none"
    model = catalog.DEFAULT_EMBEDDING_MODEL_ID
    dim = catalog.VECTOR_DIM

    def capability(self):
        return contract.unavailable(contract.CAP_EMBED, contract.STATUS_MODEL_MISSING, model=self.model)

    def embed(self, texts, *, kind=catalog.KIND_PASSAGE):
        return contract.EmbedResult(status=contract.STATUS_MODEL_MISSING, model=self.model, dim=self.dim, vectors=())


class Recorder:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def generate(self, *, system, user, model, max_output_tokens, timeout):
        from app.ai.providers import base

        self.calls.append((system, user))
        return base.success("답변입니다 [1].")


def _gateway() -> contract.Gateway:
    return contract.Gateway(enabled=True, embed_adapter=NoEmbed())


def _doc(*paragraphs: str) -> dict:
    return {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": p}]} for p in paragraphs]}


@pytest.fixture()
def space(db):
    row = KnowledgeSpace(org_id=DEFAULT_ORG_ID, name="사내 규정", slug="rules-kw", owner_kind="organization")
    db.add(row)
    db.flush()
    return row


@pytest.fixture()
def reader(db, make_user):
    user = make_user(email="kw-reader@goodmit.co.kr", role="admin", display_name="reader")
    user.org_id = DEFAULT_ORG_ID
    db.flush()
    return user


def _make(db, space, title, *paragraphs):
    doc = Document(space_id=space.id, title=title)
    db.add(doc)
    db.flush()
    versions.snapshot(db, doc, _doc(*paragraphs), author_id=None)
    db.flush()
    return doc


@pytest.fixture()
def world(db, space):
    made = {
        "vacation": _make(db, space, "여름 휴가 운영", "휴가 신청은 팀장 승인을 받습니다. 신청서는 사흘 전까지 냅니다."),
        "vacation_only": _make(db, space, "휴가 일수", "휴가 일수는 입사 연도에 따라 다릅니다."),
        "security": _make(db, space, "보안 정책", "보안 정책은 접근 통제부터 정합니다."),
    }
    index_service.run_once(db, gateway=_gateway(), limit=50)
    db.flush()
    return made


def _titles(result):
    return [c.document_title for c in result.citations]


def test_a_natural_question_finds_the_document_and_the_bare_lanes_would_not(db, reader, world):
    question = "휴가 신청은 어떻게 하나요?"
    result = retrieval.retrieve(db, reader, raw_query=question, gateway=_gateway())
    assert result.keywords == ("휴가", "신청")
    assert _titles(result)[0] == "여름 휴가 운영", _titles(result)

    # 반례 — 같은 질문을 낱말 없이(검색창 규칙으로) 돌리면 두 레인 모두 0건이다. 이 시험이 가르는 것이 바로 그 차이다.
    text = query_mod.normalize_query(question)
    assert db.execute(query_mod.trgm_lane(text, limit=50)).all() == []
    assert db.execute(query_mod.fts_lane(text, limit=50)).all() == []


def test_more_matched_words_rank_higher(db, reader, world):
    result = retrieval.retrieve(db, reader, raw_query="휴가 신청 방법을 알려줘", gateway=_gateway())
    titles = _titles(result)
    assert titles.index("여름 휴가 운영") < titles.index("휴가 일수"), titles
    assert "보안 정책" not in titles
    assert result.lane_counts[fusion.LANE_TRGM] >= 2 and result.lane_counts[fusion.LANE_FTS] >= 2


def test_a_question_with_no_matching_words_is_an_empty_result_that_names_the_words(db, reader, world):
    result = retrieval.retrieve(db, reader, raw_query="출장비 정산 절차 알려줘", gateway=_gateway())
    assert result.empty
    assert result.keywords == ("출장비", "정산", "절차")
    assert result.as_dict()["keywords"] == ["출장비", "정산", "절차"]


def test_the_model_receives_the_whole_question_not_the_display_cut(db, reader, world):
    recorder = Recorder()
    question = "휴가 신청 " + "그리고 " * 40 + "마지막 조건은 사흘 전까지 내는 것인지 알려줘"
    assert len(query_mod.normalize_query(question)) == query_mod.MAX_QUERY_CHARS
    result = answer_mod.draft_document(db, reader, instruction=question, gateway=_gateway(), runtime=offline_runtime(recorder))
    assert result.ok
    _system, user_message = recorder.calls[0]
    assert "마지막 조건은 사흘 전까지 내는 것인지 알려줘" in user_message
    assert result.retrieval.query == query_mod.normalize_query(question), "표시형은 그대로 100자다"


def test_keyword_branches_stay_inside_the_permission_filter(db, make_user, space, world):
    """낱말 가지도 `LIMIT` 앞의 권한 조건 안에서 돈다 — 볼 수 없는 공간의 문서는 낱말로도 안 나온다."""
    hidden_space = KnowledgeSpace(org_id=DEFAULT_ORG_ID, name="비공개", slug="secret-kw", owner_kind="unset")
    db.add(hidden_space)
    db.flush()
    _make(db, hidden_space, "휴가 비밀 규정", "휴가 신청 비밀 조항입니다.")
    index_service.run_once(db, gateway=_gateway(), limit=50)
    db.flush()

    member = make_user(email="kw-member@goodmit.co.kr", role="user", display_name="member")
    member.org_id = DEFAULT_ORG_ID
    db.flush()
    result = retrieval.retrieve(db, member, raw_query="휴가 신청은 어떻게 하나요?", gateway=_gateway())
    assert "휴가 비밀 규정" not in _titles(result)


# ── 낱말의 무게 · 혼합 토큰 (D-568) ──────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def weighted_world(db):
    space = KnowledgeSpace(org_id=DEFAULT_ORG_ID, name="벤치 공간", slug="weights-kw", owner_kind="organization")
    db.add(space)
    db.flush()
    for index in range(10):
        _make(db, space, f"주간 메모 {index}", f"프로젝트 일정과 현황판을 {index}번째로 정리합니다.")
    made = {
        "rare": _make(db, space, "장비 점검", "하이닉스 장비 점검 결과를 적습니다."),
        "common": _make(db, space, "회의 정리", "프로젝트 일정과 현황판 회의를 정리합니다."),
        "spaced": _make(db, space, "고객 장비", "SK 하이닉스 장비 교체 계획입니다."),
    }
    index_service.run_once(db, gateway=_gateway(), limit=50)
    db.flush()
    return made


def _lane_documents(db, stmt):
    from sqlalchemy import select

    from app.ai.models import DocumentChunk

    keys = [str(row[0]) for row in db.execute(stmt).all()]
    owners = dict(db.execute(select(DocumentChunk.id, DocumentChunk.document_id)
                             .where(DocumentChunk.id.in_(keys))).all())
    return [owners[k] for k in keys]


def test_a_rare_word_outweighs_two_common_words(db, reader, weighted_world):
    """「하이닉스 프로젝트 현황」 — 맞은 낱말 수만 세면 흔한 낱말 둘이 이긴다. 가시 조각 안의 df 로 무게를 주면 드문 낱말이 이긴다."""
    question = "하이닉스 프로젝트 현황"
    text = query_mod.normalize_query(question)
    words = ("하이닉스", "프로젝트", "현황")
    rare, common = weighted_world["rare"].id, weighted_world["common"].id
    # 반례 — 같은 무게(예전 동작)에서는 흔한 낱말 둘을 가진 문서가 위다.
    uniform = _lane_documents(db, query_mod.trgm_lane(text, keywords=words, limit=50))
    assert uniform.index(common) < uniform.index(rare), uniform
    weights = query_mod.keyword_weights(db, words, ())
    assert weights["하이닉스"] > weights["프로젝트"] and weights["하이닉스"] > weights["현황"]
    weighted = _lane_documents(db, query_mod.trgm_lane(text, keywords=words, weights=weights, limit=50))
    assert weighted.index(rare) < weighted.index(common), weighted


def test_a_mixed_token_reaches_a_document_that_spaces_it_out(db, reader, weighted_world):
    """「SK하이닉스」로 물어도 「SK 하이닉스」라고 쓴 조각이 걸린다 — 전문검색은 띄어 쓴 두 어절을 조각 낱말로 맞춘다."""
    text = query_mod.normalize_query("SK하이닉스")
    spaced = weighted_world["spaced"].id
    whole_only = _lane_documents(db, query_mod.fts_lane(text, keywords=("sk하이닉스",), limit=50))
    assert spaced not in whole_only, "반례가 서지 않는다 — 통째 낱말만으로도 걸리면 이 시험은 아무것도 가르지 않는다"
    parts = _lane_documents(db, query_mod.fts_lane(text, keywords=("sk하이닉스", "하이닉스", "sk"), limit=50))
    assert spaced in parts
    result = retrieval.retrieve(db, reader, raw_query="SK하이닉스 장비 교체 계획 알려줘", gateway=_gateway())
    assert result.keywords[:3] == ("sk하이닉스", "하이닉스", "sk")
    assert _titles(result)[0] == "고객 장비", _titles(result)


def test_document_level_retrieval_folds_chunks_and_counts_documents(db, reader, weighted_world):
    """문서 단위(`distinct_documents`)는 문서마다 한 줄이고, 세기는 같은 조건 · 같은 권한 절로 문서를 센다."""
    result = retrieval.retrieve(db, reader, raw_query="프로젝트 현황판", gateway=_gateway(), distinct_documents=True,
                                top_k=5)
    ids = [c.document_id for c in result.citations]
    assert len(ids) == len(set(ids)) == 5
    counted = retrieval.count_matching_documents(db, reader, text="프로젝트 현황판", words=result.keywords,
                                                 expanded=result.expanded)
    assert counted is not None and counted.documents == counted.total == 11
    assert counted.with_every_word == 11
    second = retrieval.retrieve(db, reader, raw_query="프로젝트 현황판", gateway=_gateway(), distinct_documents=True,
                                top_k=5, offset=5)
    assert not set(ids) & {c.document_id for c in second.citations}, "쪽을 넘겼는데 같은 문서가 또 나왔다"


def test_workspace_search_splits_mixed_tokens_but_the_search_screen_keeps_its_rule(db, app, make_user, make_ticket,
                                                                                    portal_project, fake_clock):
    """「SK하이닉스」 — 도우미의 통합 검색(`match="any"`)은 조각 「하이닉스」로 「하이닉스 장비 교체」 티켓을 찾는다. 통합 검색
    화면(`match="all"`, P-123)은 낱말을 뽑지 않으므로 예전처럼 통째 구절만 찾는다 — 이 변경이 화면을 바꾸지 않았다는 반례다."""
    from app.core.scope import principal_from_user
    from app.search import service as search_service
    from app.search.indexer import reindex_all

    viewer = make_user(email="kw-ws@goodmit.co.kr", role="user", display_name="ws")
    viewer.org_id = DEFAULT_ORG_ID
    make_ticket(project=portal_project, title="하이닉스 장비 교체")
    db.commit()
    reindex_all(db, tickets=app.state.repositories.tickets, now=fake_clock.now())
    db.commit()
    principal = principal_from_user(db, viewer)
    ai = search_service.search(db, raw_query="SK하이닉스", principal=principal, match=search_service.MATCH_ANY)
    screen = search_service.search(db, raw_query="SK하이닉스", principal=principal)
    titles = [hit["title"] for group in ai["groups"] for hit in group["items"]]
    assert "하이닉스 장비 교체" in titles
    assert screen["total"] == 0, "통합 검색 화면의 규칙이 바뀌었다(P-123)"
