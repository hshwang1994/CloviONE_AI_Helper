"""Hybrid Retrieval — 세 레인이 돌고, 융합되고, 인용이 그 자리를 가리킨다 (S10).

## 이 파일의 Exit 성질

**생성 Adapter 가 비활성인 상태에서 검색과 인용이 정상이다.** 그것이 S10 의 Exit 조건
하나이고, 여기 있는 시험 대부분이 `generate_adapter=None` 인 Gateway 로 돈다.

권한 축은 여기 없다 — `tests/security/test_ai_retrieval_permission.py` 가 본다.
두 관심사를 한 파일에 섞으면 「권한 시험이 있다」는 말이 절반만 사실이 된다.
"""

from __future__ import annotations

import io
import zipfile

import pytest
from sqlalchemy import select

from app.ai import catalog
from app.ai.gateway import contract
from app.ai.index import service as index_service
from app.ai.models import SOURCE_DOCUMENT, SOURCE_FILE, DocumentChunk
from app.ai.retrieval import answer as answer_mod
from app.ai.retrieval import fusion
from app.ai.retrieval import service as retrieval
from app.knowledge import attachments, blocks, versions
from app.knowledge.models import Document, DocumentVersion, KnowledgeSpace
from app.org.constants import DEFAULT_ORG_ID
from app.storage import service as storage_service

pytestmark = pytest.mark.integration

_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_P = "http://schemas.openxmlformats.org/presentationml/2006/main"


# ── 가짜 모델 둘 ─────────────────────────────────────────────────────────────


class ScriptedEmbed(contract.EmbedAdapter):
    """**주제표**로 벡터를 만든다. 글자가 안 겹쳐도 같은 주제면 가깝다.

    실제 모델을 시험 전제로 만들지 않는다(465MB · 8 vCPU · 세션 로드 2.3초). 진짜
    모델로 도는 것은 테스트 서버 실검증이 본다 — 여기서 보는 것은 **배선**이다.

    그래도 「의미 검색이 낱말 검색이 못 찾는 것을 찾는다」는 성질은 여기서 봐야 한다.
    그래서 무작위 해시가 아니라 주제표를 쓴다: `topics` 에 적힌 말이 글에 있으면 그
    주제 축이 1 이 된다. 아무 주제에도 안 걸리는 글은 마지막 축 하나만 1 이라 모든
    주제와 등거리다.
    """

    def __init__(self, topics: dict[str, tuple[str, ...]], *, available: bool = True):
        self.name = "scripted"
        self.model = catalog.DEFAULT_EMBEDDING_MODEL_ID
        self.dim = catalog.VECTOR_DIM
        self._topics = topics
        self._axis = {name: index for index, name in enumerate(sorted(topics))}
        self._available = available
        self.kinds: list[str] = []

    def capability(self):
        if not self._available:
            return contract.unavailable(
                contract.CAP_EMBED, contract.STATUS_MODEL_MISSING, model=self.model
            )
        return contract.available(contract.CAP_EMBED, model=self.model)

    def _vector(self, text: str) -> tuple[float, ...]:
        values = [0.0] * self.dim
        for name, words in self._topics.items():
            if any(word in text for word in words):
                values[self._axis[name]] = 1.0
        if not any(values):
            values[-1] = 1.0
        norm = sum(v * v for v in values) ** 0.5
        return tuple(v / norm for v in values)

    def embed(self, texts, *, kind=catalog.KIND_PASSAGE):
        self.kinds.append(kind)
        return contract.EmbedResult(
            status=contract.STATUS_OK, model=self.model, dim=self.dim,
            vectors=tuple(self._vector(t) for t in texts),
        )


class ScriptedGenerate(contract.GenerateAdapter):
    """받은 (system, user) 쌍을 그대로 들고 있는다. **무엇이 넘어갔는지가 시험 대상이다.**"""

    def __init__(self, *, status: str = contract.STATUS_OK, text: str = "답변입니다 [1]."):
        self.name = "scripted"
        self.model = "scripted-model"
        self._status = status
        self._text = text
        self.calls: list[tuple[str, str]] = []

    def capability(self):
        if self._status != contract.STATUS_OK:
            return contract.unavailable(contract.CAP_GENERATE, self._status, model=self.model)
        return contract.available(contract.CAP_GENERATE, model=self.model)

    def generate(self, *, system: str, user: str):
        self.calls.append((system, user))
        return contract.GenerateResult(
            status=self._status, model=self.model,
            text=self._text if self._status == contract.STATUS_OK else None,
        )


TOPICS = {
    # 「연차」와 「휴가」는 트라이그램이 하나도 안 겹친다. 그것이 의미 검색의 자리다.
    "leave": ("연차", "휴가", "반차"),
    "security": ("보안", "접근 통제"),
}


def _gateway(*, embed=True, generate=None) -> contract.Gateway:
    # `embed=False` 는 **모델 파일을 안 넣은 설치**다(어댑터는 있고 파일이 없다). 그것이
    # 실제로 흔한 상태이고, 「어댑터 자체가 없다」와는 운영자가 할 일이 다르다.
    return contract.Gateway(
        enabled=True,
        embed_adapter=ScriptedEmbed(TOPICS, available=embed),
        generate_adapter=generate,
    )


# ── 세계 ─────────────────────────────────────────────────────────────────────


def _doc(*paragraphs: str) -> dict:
    return {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": p}]}
            for p in paragraphs
        ],
    }


def _pptx(slides) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("ppt/presentation.xml", "<p:presentation/>")
        for index, texts in enumerate(slides, start=1):
            runs = "".join(f"<a:p><a:r><a:t>{t}</a:t></a:r></a:p>" for t in texts)
            archive.writestr(
                f"ppt/slides/slide{index}.xml",
                f'<p:sld xmlns:a="{_A}" xmlns:p="{_P}"><p:cSld><p:spTree>{runs}'
                "</p:spTree></p:cSld></p:sld>",
            )
    return buf.getvalue()


@pytest.fixture()
def space(db):
    row = KnowledgeSpace(
        org_id=DEFAULT_ORG_ID, name="사내 규정", slug="rules", owner_kind="organization"
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture()
def reader(db, make_user):
    user = make_user(email="reader@goodmit.co.kr", role="admin", display_name="reader")
    user.org_id = DEFAULT_ORG_ID
    db.flush()
    return user


def _make_doc(db, space, title, *paragraphs, archived=False):
    doc = Document(space_id=space.id, title=title, archived=archived)
    db.add(doc)
    db.flush()
    versions.snapshot(db, doc, _doc(*paragraphs), author_id=None)
    db.flush()
    return doc


def _index(db, gateway):
    index_service.run_once(db, gateway=gateway, limit=50)
    db.flush()


@pytest.fixture()
def world(db, space):
    """세 문서. 트라이그램·FTS·의미가 각각 다른 것을 고르게 심는다."""
    made = {
        "leave": _make_doc(
            db, space, "연차 사용 안내",
            "연차는 남은 일수 안에서 자유롭게 씁니다. " * 3,
        ),
        "vacation": _make_doc(
            db, space, "여름 휴가 운영",
            "휴가 신청은 팀장 승인을 받습니다. " * 3,
        ),
        "security": _make_doc(
            db, space, "보안 정책",
            "보안 정책은 접근 통제부터 정합니다. " * 3,
        ),
    }
    return made


# ── 세 레인 ──────────────────────────────────────────────────────────────────


def test_all_three_lanes_answer_and_the_counts_are_reported(db, reader, world):
    gateway = _gateway()
    _index(db, gateway)
    result = retrieval.retrieve(db, reader, raw_query="연차", gateway=gateway)
    assert result.lane_counts[fusion.LANE_TRGM] > 0
    assert result.lane_counts[fusion.LANE_FTS] > 0
    assert result.lane_counts[fusion.LANE_VECTOR] > 0
    assert result.semantic is True


def test_semantic_finds_what_the_word_lanes_cannot(db, reader, world):
    """「연차」로 물으면 글자가 하나도 안 겹치는 「휴가」 문서도 후보에 든다.

    이것이 벡터 레인을 두는 이유 전부다. 키워드만으로는 이 문서가 **후보에도 안 든다**.
    """
    gateway = _gateway()
    _index(db, gateway)
    result = retrieval.retrieve(db, reader, raw_query="연차", gateway=gateway)
    documents = {c.document_id for c in result.citations}
    assert world["vacation"].id in documents
    assert world["leave"].id in documents
    # 다른 주제는 안 끌려온다 — 「전부 다 나온다」는 검색이 아니다.
    assert world["security"].id not in documents


def test_the_query_is_embedded_as_a_query_not_as_a_passage(db, reader, world):
    """접두사를 안 붙이면 **오류가 하나도 안 나고** 품질만 조용히 떨어진다(S9)."""
    adapter = ScriptedEmbed(TOPICS)
    gateway = contract.Gateway(enabled=True, embed_adapter=adapter, generate_adapter=None)
    _index(db, gateway)
    adapter.kinds.clear()
    retrieval.retrieve(db, reader, raw_query="연차", gateway=gateway)
    assert adapter.kinds == [catalog.KIND_QUERY]


def test_without_an_embedding_model_the_word_lanes_still_answer(db, reader, world):
    """모델이 없는 설치도 검색이 된다. 그 사실을 `vector_status` 가 말한다."""
    _index(db, _gateway())
    blind = _gateway(embed=False)
    result = retrieval.retrieve(db, reader, raw_query="연차", gateway=blind)
    assert result.citations
    assert result.semantic is False
    assert result.vector_status == contract.STATUS_MODEL_MISSING
    assert fusion.LANE_VECTOR not in result.lane_counts
    assert result.as_dict()["vector_notice"]


def test_an_empty_query_asks_the_database_nothing(db, reader, world):
    result = retrieval.retrieve(db, reader, raw_query="   ", gateway=_gateway())
    assert result.empty
    assert result.lane_counts == {}


# ── 인용 ─────────────────────────────────────────────────────────────────────


def test_a_citation_points_at_the_block_it_came_from(db, reader, world):
    gateway = _gateway()
    _index(db, gateway)
    result = retrieval.retrieve(db, reader, raw_query="연차", gateway=gateway)
    hit = next(c for c in result.citations if c.document_id == world["leave"].id)
    assert hit.source_kind == SOURCE_DOCUMENT
    assert hit.route.startswith(f"/knowledge/{world['leave'].id}?block=")
    # 앵커가 진짜 그 문서의 블록 id 다 — 링크가 아무 문자열이나 들고 있으면 안 된다.
    version = db.get(DocumentVersion, world["leave"].current_version_id)
    assert hit.anchor_ref in blocks.block_ids(version.body)
    assert hit.document_title == "연차 사용 안내"


def test_an_attachment_citation_names_the_file_and_the_slide(db, reader, space, settings):
    storage_service.ensure_default_provider(db, settings)
    db.flush()
    doc = _make_doc(db, space, "발표 자료", "첨부를 보세요.")
    attachments.attach(
        db, doc, filename="설명회.pptx", content=_pptx([["표지"], ["연차 제도 요약"]])
    )
    db.flush()
    gateway = _gateway()
    _index(db, gateway)

    result = retrieval.retrieve(db, reader, raw_query="연차 제도", gateway=gateway)
    hit = next(c for c in result.citations if c.source_kind == SOURCE_FILE)
    assert hit.filename == "설명회.pptx"
    assert "슬라이드" in hit.where
    # 파일 chunk 도 **부모 문서**로 데려간다. 첨부의 가시성은 부모가 지킨다(D-253).
    assert hit.route == f"/knowledge/{doc.id}"


def test_archived_documents_are_not_evidence(db, reader, space):
    gateway = _gateway()
    live = _make_doc(db, space, "현행 연차 규정", "연차는 이렇게 씁니다. " * 3)
    old = _make_doc(db, space, "옛 연차 규정", "연차는 이렇게 씁니다. " * 3, archived=True)
    _index(db, gateway)
    # 보관된 문서도 색인은 된다 — 보관을 풀면 곧바로 검색되어야 하기 때문이다.
    assert db.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == old.id)
    ).scalars().first() is not None

    result = retrieval.retrieve(db, reader, raw_query="연차", gateway=gateway)
    documents = {c.document_id for c in result.citations}
    assert live.id in documents
    assert old.id not in documents


# ── 생성 ─────────────────────────────────────────────────────────────────────


def test_search_and_citations_keep_working_while_generation_is_blocked(db, reader, world):
    """🔴 S10 Exit — 생성 Provider 차단 시 검색/인용이 계속 동작한다."""
    blocked = ScriptedGenerate(status=contract.STATUS_NOT_LOGGED_IN)
    gateway = _gateway(generate=blocked)
    _index(db, gateway)

    result = answer_mod.answer(db, reader, raw_query="연차", gateway=gateway)
    assert result.ok is False
    assert result.notice
    assert result.retrieval.citations          # 근거는 그대로 나간다
    assert blocked.calls == []                  # 못 쓰는 것을 부르지도 않는다
    body = result.as_dict()
    assert body["answer"] is None
    assert body["citations"]


def test_the_model_only_sees_the_retrieved_chunks(db, reader, world):
    """Context 는 인용 목록 밖을 못 본다 — 그것이 「권한이 먼저」의 다른 쪽 면이다."""
    generator = ScriptedGenerate()
    gateway = _gateway(generate=generator)
    _index(db, gateway)

    result = answer_mod.answer(db, reader, raw_query="연차", gateway=gateway)
    assert result.ok
    _system, user_message = generator.calls[0]
    for cite in result.retrieval.citations:
        assert cite.text_for_context[:20] in user_message
    assert "보안 정책은 접근 통제부터" not in user_message


def test_no_evidence_means_the_model_is_not_called_at_all(db, reader, world):
    """빈 Context 로 부르면 모델은 무언가를 지어내고, 그 문장에는 인용이 없다."""
    generator = ScriptedGenerate()
    gateway = _gateway(generate=generator)
    _index(db, gateway)

    result = answer_mod.answer(
        db, reader, raw_query="존재하지않는낱말조합xyz", gateway=gateway
    )
    assert result.status == contract.STATUS_EMPTY
    assert generator.calls == []


def test_the_context_is_numbered_so_the_answer_can_point_back(db, reader, world):
    generator = ScriptedGenerate()
    gateway = _gateway(generate=generator)
    _index(db, gateway)

    result = answer_mod.answer(db, reader, raw_query="연차", gateway=gateway)
    _system, user_message = generator.calls[0]
    assert "[1]" in user_message
