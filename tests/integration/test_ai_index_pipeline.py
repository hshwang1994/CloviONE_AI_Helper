"""색인 파이프라인 — 본문과 첨부가 chunk 가 되고 벡터가 붙는다 (S9 · D-203).

## 🔴 이 파일의 Exit 성질

**생성 Adapter 가 비활성인 상태에서 파싱·색인·임베딩이 정상이다.** 그것이 P-18 의
완료 조건이고, 여기 있는 시험 전부가 `generate_adapter=None` 인 Gateway 로 돈다.

그리고 그 반대편도 함께 든다: **임베딩 모델까지 없으면** chunk 는 만들어지고 벡터
칸이 NULL 로 남는다. 그 상태가 정상이라는 것을 못박아야 「모델이 없으면 색인이
멈춘다」는 잘못된 구현으로 흐르지 않는다.
"""

from __future__ import annotations

import io
import zipfile

import pytest
from sqlalchemy import select

from app.ai import catalog
from app.ai.gateway import contract
from app.ai.index import service as index_service
from app.ai.models import (
    ANCHOR_BLOCK,
    ANCHOR_SLIDE,
    SOURCE_DOCUMENT,
    SOURCE_FILE,
    STATE_FAILED,
    STATE_OK,
    STATE_PENDING,
    AiIndexState,
    DocumentChunk,
)
from app.core.errors import StorageUnavailableError
from app.knowledge import attachments, versions
from app.knowledge.models import Document, KnowledgeSpace
from app.org.constants import DEFAULT_ORG_ID
from app.storage import service as storage_service

pytestmark = pytest.mark.integration

_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_P = "http://schemas.openxmlformats.org/presentationml/2006/main"


class FakeEmbed(contract.EmbedAdapter):
    """벡터를 **결정적으로** 만든다. 글이 같으면 벡터도 같다.

    실제 모델을 시험 전제로 만들지 않는다(465MB · 8 vCPU). 진짜 모델로 도는 것은
    테스트 서버 실검증이 본다 — 여기서 보는 것은 **파이프라인의 배선**이다.
    """

    def __init__(self, *, available: bool = True):
        self.name = "fake"
        self.model = catalog.DEFAULT_EMBEDDING_MODEL_ID
        self.dim = catalog.VECTOR_DIM
        self._available = available
        self.calls = 0
        self.texts: list[str] = []

    def capability(self):
        if not self._available:
            return contract.unavailable(
                contract.CAP_EMBED, contract.STATUS_MODEL_MISSING, model=self.model
            )
        return contract.available(contract.CAP_EMBED, model=self.model)

    def embed(self, texts, *, kind=catalog.KIND_PASSAGE):
        self.calls += 1
        self.texts.extend(texts)
        vectors = tuple(
            tuple(((hash(t) >> (i % 16)) % 97) / 97.0 or 0.01 for i in range(self.dim))
            for t in texts
        )
        return contract.EmbedResult(
            status=contract.STATUS_OK, model=self.model, dim=self.dim, vectors=vectors
        )


def _gateway(*, embed_available: bool = True, adapter=None) -> contract.Gateway:
    # 🔴 `generate_adapter` 가 없다. 그것이 이 파일의 전제다.
    return contract.Gateway(
        enabled=True,
        embed_adapter=adapter or FakeEmbed(available=embed_available),
        generate_adapter=None,
    )


def _doc(body: str) -> dict:
    return {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": body}]},
        ],
    }


def _pptx(slides) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        # 🔴 `ppt/presentation.xml` 이 있어야 S8 의 판정기가 이것을 PPTX 로 본다
        # (`app/core/uploads.py::_sniff_zip_family` — 확장자도 선언도 안 믿고 **실제로
        # 들어 있는 항목**을 본다). 없으면 업로드 자체가 거절되고, 그러면 이 시험은
        # 색인이 아니라 업로드를 시험하게 된다.
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
def storage(db, settings):
    provider = storage_service.ensure_default_provider(db, settings)
    db.flush()
    return provider


@pytest.fixture()
def document(db, storage):
    space = KnowledgeSpace(
        org_id=DEFAULT_ORG_ID, name="설계 공간", slug="design", owner_kind="organization"
    )
    db.add(space)
    db.flush()
    doc = Document(space_id=space.id, title="보안 정책 회의록")
    db.add(doc)
    db.flush()
    versions.snapshot(
        db, doc, _doc("보안 정책은 이렇게 정합니다. " * 12), author_id=None
    )
    db.flush()
    return doc


def _run(db, gateway):
    return index_service.run_once(db, gateway=gateway, limit=20)


def _chunks(db, document_id):
    return list(
        db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.ordinal)
        ).scalars().all()
    )


def _state(db, document_id) -> AiIndexState:
    return db.execute(
        select(AiIndexState).where(AiIndexState.document_id == document_id)
    ).scalar_one()


# ── 본문 ─────────────────────────────────────────────────────────────────────


def test_a_saved_document_becomes_chunks_with_block_anchors(db, document):
    gateway = _gateway()
    assert _run(db, gateway) == 1
    rows = _chunks(db, document.id)
    assert rows
    assert all(r.source_kind == SOURCE_DOCUMENT for r in rows)
    assert all(r.anchor_kind == ANCHOR_BLOCK for r in rows)
    # 앵커는 **블록 id** 다. 「이 문서 어딘가」가 아니라 「이 블록」을 가리킨다(D-198).
    assert all(r.anchor_ref for r in rows)
    assert "보안 정책" in rows[0].text_body


def test_the_title_rides_on_the_first_chunk_only(db, document):
    """전 chunk 에 얹으면 같은 문장이 chunk 수만큼 반복되어, 제목만으로 문서 전체가 뜬다."""
    _run(db, _gateway())
    rows = _chunks(db, document.id)
    assert rows[0].text_body.startswith("보안 정책 회의록")
    assert sum(1 for r in rows if r.text_body.startswith("보안 정책 회의록")) == 1


def test_every_chunk_gets_a_vector_and_says_what_made_it(db, document):
    _run(db, _gateway())
    for row in _chunks(db, document.id):
        assert row.embedding is not None
        assert len(row.embedding) == catalog.VECTOR_DIM
        assert row.embedded_at is not None
        # 벡터가 있으면 **무엇으로 만들었는지도 있다.** 없으면 모델을 바꾼 날 어느
        # 벡터가 옛것인지 가릴 수가 없다.
        assert row.embedding_model == catalog.DEFAULT_EMBEDDING_MODEL_ID
        assert row.embedding_version == catalog.EMBEDDING_VERSION


def test_the_state_row_records_what_it_indexed(db, document):
    _run(db, _gateway())
    state = _state(db, document.id)
    assert state.status == STATE_OK
    assert state.indexed_version_id == document.current_version_id
    assert state.chunk_count == len(_chunks(db, document.id))
    assert state.embedded_count == state.chunk_count
    assert state.parser_version == catalog.PARSER_VERSION


# ── 🔴 모델이 없어도 색인은 돈다 ────────────────────────────────────────────


def test_without_an_embedding_model_chunks_still_stand_with_null_vectors(db, document):
    """**그 상태가 정상이다.** 키워드 검색은 이미 되고, 모델이 생기면 그때 채운다."""
    _run(db, _gateway(embed_available=False))
    rows = _chunks(db, document.id)
    assert rows
    assert all(r.embedding is None and r.embedded_at is None for r in rows)
    state = _state(db, document.id)
    assert state.status == STATE_OK
    assert state.chunk_count == len(rows)
    assert state.embedded_count == 0


def test_when_the_model_arrives_later_the_pending_chunks_are_filled(db, document):
    """모델이 나중에 생긴 설치의 따라잡기 경로. **다시 파싱하지 않는다.**"""
    _run(db, _gateway(embed_available=False))
    rows_before = _chunks(db, document.id)
    assert all(r.embedding is None for r in rows_before)
    ids_before = [r.id for r in rows_before]

    gateway = _gateway()
    versions_now = index_service.current_versions(gateway)
    filled = index_service.embed_pending(db, gateway=gateway, versions=versions_now)
    assert filled == len(rows_before)
    rows_after = _chunks(db, document.id)
    # chunk 행 자체는 그대로다 — 파싱을 다시 하지 않았다는 증거다.
    assert [r.id for r in rows_after] == ids_before
    assert all(r.embedding is not None for r in rows_after)
    assert _state(db, document.id).embedded_count == len(rows_after)


def test_a_model_that_is_missing_does_not_mark_the_document_failed(db, document):
    """모델이 없는 것은 결함이 아니다. 실패로 세면 대시보드가 매일 빨간불이 된다."""
    _run(db, _gateway(embed_available=False))
    assert _state(db, document.id).status == STATE_OK


# ── 첨부 ─────────────────────────────────────────────────────────────────────


def test_an_attachment_is_parsed_and_anchored_to_its_own_place(db, document, storage):
    attachments.attach(
        db, document, filename="발표.pptx",
        content=_pptx([
            # `chunking.MIN_CHARS` 보다 길어야 한다 — 짧은 조각은 「쪽 번호만 있는 쪽」
            # 으로 보고 버린다. 실제 슬라이드가 이보다 짧은 경우는 드물다.
            ["첫 슬라이드입니다. 여기에 회의 결정 사항을 적었습니다."],
            ["둘째 슬라이드입니다. 여기에는 남은 과제를 적었습니다."],
        ]),
    )
    db.flush()
    _run(db, _gateway())
    rows = _chunks(db, document.id)
    file_rows = [r for r in rows if r.source_kind == SOURCE_FILE]
    assert file_rows
    assert all(r.anchor_kind == ANCHOR_SLIDE for r in file_rows)
    assert {r.anchor_ref for r in file_rows} == {"1", "2"}
    # 🔴 첨부에서 나온 chunk 도 **부모 문서**를 가리킨다(D-253) — 그것이 권한을 묻는 자리다.
    assert all(r.document_id == document.id for r in file_rows)
    assert all(r.file_id for r in file_rows)


def test_an_image_attachment_is_skipped_without_failing(db, document, storage):
    """OCR 을 도입하지 않기로 했다. 그림에서 글자를 못 뽑는 것이 정상이다."""
    attachments.attach(
        db, document, filename="사진.png", content=b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    )
    db.flush()
    _run(db, _gateway())
    assert _state(db, document.id).status == STATE_OK
    assert all(r.source_kind == SOURCE_DOCUMENT for r in _chunks(db, document.id))


def test_a_file_chunk_never_spans_two_slides(db, document, storage):
    attachments.attach(
        db, document, filename="발표.pptx",
        content=_pptx([["가" * 100], ["나" * 100]]),
    )
    db.flush()
    _run(db, _gateway())
    for row in _chunks(db, document.id):
        assert not ("가" * 20 in row.text_body and "나" * 20 in row.text_body)


# ── 재사용 ───────────────────────────────────────────────────────────────────


def test_unchanged_chunks_are_not_embedded_again(db, document):
    """임베딩이 이 파이프라인에서 가장 비싼 단계다. 한 글자 고쳤다고 전부 다시
    만들면 그 비용이 곧 색인 시간이 된다."""
    adapter = FakeEmbed()
    gateway = _gateway(adapter=adapter)
    _run(db, gateway)
    first_texts = list(adapter.texts)
    assert first_texts

    # 같은 본문에 문단 하나를 더한다. 앞 문단의 chunk 는 글이 그대로다.
    body = {
        "type": "doc",
        "content": [
            {"type": "paragraph",
             "content": [{"type": "text", "text": "보안 정책은 이렇게 정합니다. " * 12}]},
            {"type": "paragraph",
             "content": [{"type": "text", "text": "새로 더한 문단입니다. " * 12}]},
        ],
    }
    versions.snapshot(db, document, body, author_id=None)
    db.flush()
    adapter.texts.clear()
    _run(db, gateway)
    # 두 번째 판에서 새로 임베딩한 글에는 **첫 판의 글이 없다**.
    assert adapter.texts
    assert not (set(adapter.texts) & set(first_texts))


def test_changing_the_embedding_model_forces_a_full_reindex(db, document):
    """모델이 다르면 그 벡터는 다른 공간의 값이라 비교할 수 없다. 재사용은 비용을
    아끼는 일이지 정확도를 깎을 일이 아니다."""
    _run(db, _gateway())
    texts_before = {r.text_body for r in _chunks(db, document.id)}
    assert texts_before

    other = FakeEmbed()
    other.model = "다른/모델"
    gateway = _gateway(adapter=other)
    versions_now = index_service.current_versions(gateway)
    state = _state(db, document.id)
    index_service.index_one(db, state, gateway=gateway, versions=versions_now)
    db.flush()
    after = _chunks(db, document.id)
    assert after
    assert all(r.embedding_model == "다른/모델" for r in after)
    # 🔴 **글이 같아도 다시 임베딩했다.** 재사용 표를 모델로 안 갈랐다면 새 모델은
    # 한 글자도 안 태우고 옛 벡터가 새 모델 이름을 달고 남는다.
    assert texts_before <= set(other.texts)


# ── 실패 ─────────────────────────────────────────────────────────────────────


def test_an_unreachable_storage_is_a_retry_not_a_permanent_failure(db, document, storage, monkeypatch):
    """저장소가 안 붙은 것은 **결함이 아니라 상태**다."""
    attachments.attach(db, document, filename="발표.pptx", content=_pptx([["글"]]))
    db.flush()

    def unavailable(*_args, **_kwargs):
        raise StorageUnavailableError()

    monkeypatch.setattr(storage_service, "file_path", unavailable)
    _run(db, _gateway())
    state = _state(db, document.id)
    assert state.status == STATE_FAILED
    assert state.next_attempt_at is not None
    # 오류 문구에 경로가 안 샌다(OPS-05).
    assert "/" not in state.last_error and "\\" not in state.last_error


def test_a_failed_document_is_not_picked_up_again_immediately(db, document, storage, monkeypatch):
    """곧바로 다시 잡으면 못 읽는 파일 하나가 레인을 통째로 돌리고, 그 사이 다른
    문서는 한 건도 색인되지 않는다."""
    attachments.attach(db, document, filename="발표.pptx", content=_pptx([["글"]]))
    db.flush()
    monkeypatch.setattr(
        storage_service, "file_path",
        lambda *a, **k: (_ for _ in ()).throw(StorageUnavailableError()),
    )
    _run(db, _gateway())
    state = _state(db, document.id)
    attempts = state.attempts
    db.flush()
    _run(db, _gateway())
    assert _state(db, document.id).attempts == attempts


def test_deleting_a_document_removes_its_chunks(db, document):
    """파생 데이터라 남길 이유가 없다."""
    _run(db, _gateway())
    assert _chunks(db, document.id)
    db.delete(document)
    db.flush()
    assert _chunks(db, document.id) == []


# ── 상태 보고 ────────────────────────────────────────────────────────────────


def test_index_health_counts_what_the_dashboard_shows(db, document):
    _run(db, _gateway(embed_available=False))
    health = index_service.index_health(db)
    assert health["chunks"] > 0
    assert health["embedded"] == 0
    assert health["pending_embedding"] == health["chunks"]
    assert health["documents"]["ok"] == 1
    assert health["vector_index_recommended"] is False


def test_a_never_indexed_document_shows_up_as_pending(db, document):
    """훑기가 상태 행을 만든다 — 신호를 빠뜨린 문서의 안전망이다."""
    db.execute(AiIndexState.__table__.delete())
    db.flush()
    gateway = _gateway()
    index_service.sweep_stale(db, versions=index_service.current_versions(gateway))
    assert _state(db, document.id).status == STATE_PENDING
