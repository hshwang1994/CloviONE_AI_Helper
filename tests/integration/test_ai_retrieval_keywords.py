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
