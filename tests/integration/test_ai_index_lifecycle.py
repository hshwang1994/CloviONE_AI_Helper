"""Index Lifecycle — 무엇이 색인을 낡게 만드는가 (S9 · D-203).

## 신호와 훑기를 **둘 다** 쓴다

문서를 저장할 때 상태 행을 `pending` 으로 만든다(신호). 그리고 색인 레인이 주기적으로
낡은 행을 훑는다(안전망). 신호 하나만 믿으면 신호를 빠뜨린 문서가 **영원히** 옛
내용으로 남고, 그것이 가장 알아채기 어려운 결함이다 — 오류가 안 나고, 화면도 멀쩡하고,
검색 결과만 3년 전 문장이다.

## 🔴 그리고 **권한 변경은 여기 없다**

권한이 바뀌어도 이 파일의 어떤 시험도 재색인을 기대하지 않는다. 그것이 D-203 이다:
권한은 인덱스에 안 구워져 있고, 질의 시각에 판정된다. 그 성질의 구조적 증거는
`tests/unit/test_ai_domain_seed.py` 가 컬럼 목록으로 든다.
"""

from __future__ import annotations

import io
import zipfile

import pytest
from sqlalchemy import select

from app.ai import catalog
from app.ai.gateway import contract
from app.ai.index import service as index_service
from app.ai.models import STATE_OK, STATE_PENDING, AiIndexState
from app.knowledge import attachments, versions
from app.knowledge.models import Document, KnowledgeSpace
from app.org.constants import DEFAULT_ORG_ID
from app.storage import service as storage_service

pytestmark = pytest.mark.integration

_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_P = "http://schemas.openxmlformats.org/presentationml/2006/main"


class FakeEmbed(contract.EmbedAdapter):
    name = "fake"
    model = catalog.DEFAULT_EMBEDDING_MODEL_ID
    dim = catalog.VECTOR_DIM

    def capability(self):
        return contract.available(contract.CAP_EMBED, model=self.model)

    def embed(self, texts, *, kind=catalog.KIND_PASSAGE):
        return contract.EmbedResult(
            status=contract.STATUS_OK, model=self.model, dim=self.dim,
            vectors=tuple(tuple(0.1 for _ in range(self.dim)) for _ in texts),
        )


def _gateway() -> contract.Gateway:
    return contract.Gateway(enabled=True, embed_adapter=FakeEmbed(), generate_adapter=None)


def _pptx(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("ppt/presentation.xml", "<p:presentation/>")
        archive.writestr(
            "ppt/slides/slide1.xml",
            f'<p:sld xmlns:a="{_A}" xmlns:p="{_P}"><p:cSld><p:spTree>'
            f"<a:p><a:r><a:t>{text}</a:t></a:r></a:p></p:spTree></p:cSld></p:sld>",
        )
    return buf.getvalue()


def _body(text: str) -> dict:
    return {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


@pytest.fixture()
def document(db, settings):
    storage_service.ensure_default_provider(db, settings)
    db.flush()
    space = KnowledgeSpace(
        org_id=DEFAULT_ORG_ID, name="공간", slug="space", owner_kind="organization"
    )
    db.add(space)
    db.flush()
    doc = Document(space_id=space.id, title="원본 문서")
    db.add(doc)
    db.flush()
    versions.snapshot(db, doc, _body("첫 판의 본문입니다. " * 10), author_id=None)
    db.flush()
    return doc


def _state(db, document_id) -> AiIndexState:
    return db.execute(
        select(AiIndexState).where(AiIndexState.document_id == document_id)
    ).scalar_one()


def _settle(db):
    index_service.run_once(db, gateway=_gateway(), limit=20)


# ── 신호 ─────────────────────────────────────────────────────────────────────


def test_saving_a_document_queues_it(db, document):
    """`versions.snapshot` 하나가 신호를 낸다. **`current_version_id` 를 옮기는 곳이
    그 함수 하나**라, 새 저장 경로가 생겨도 신호를 빠뜨릴 자리가 없다."""
    assert _state(db, document.id).status == STATE_PENDING


def test_saving_again_requeues_an_already_indexed_document(db, document):
    _settle(db)
    assert _state(db, document.id).status == STATE_OK
    versions.snapshot(db, document, _body("둘째 판의 본문입니다. " * 10), author_id=None)
    db.flush()
    assert _state(db, document.id).status == STATE_PENDING


def test_saving_the_same_body_does_not_requeue(db, document):
    """같은 본문이면 판이 안 쌓인다(S7). 색인도 다시 돌 이유가 없다."""
    _settle(db)
    same = _body("첫 판의 본문입니다. " * 10)
    assert versions.snapshot(db, document, same, author_id=None) is None
    db.flush()
    assert _state(db, document.id).status == STATE_OK


def test_attaching_a_file_requeues_the_document(db, document):
    """본문이 그대로여도 첨부가 붙으면 색인은 낡는다."""
    _settle(db)
    attachments.attach(
        db, document, filename="발표.pptx", content=_pptx("붙인 슬라이드의 내용입니다.")
    )
    db.flush()
    assert _state(db, document.id).status == STATE_PENDING


def test_detaching_a_file_requeues_the_document(db, document):
    attachments.attach(
        db, document, filename="발표.pptx", content=_pptx("붙인 슬라이드의 내용입니다.")
    )
    db.flush()
    _settle(db)
    link = db.execute(
        select(attachments.DocumentAttachment).where(
            attachments.DocumentAttachment.document_id == document.id
        )
    ).scalar_one()
    attachments.detach(db, link)
    db.flush()
    assert _state(db, document.id).status == STATE_PENDING


def test_a_requeue_clears_the_old_failure_backoff(db, document):
    """방금 고친 문서를 한 시간 뒤에 보면 안 된다."""
    state = _state(db, document.id)
    index_service._fail(state, "무언가 실패했습니다.", now=index_service.utcnow())
    db.flush()
    assert state.next_attempt_at is not None
    index_service.enqueue(db, document.id)
    assert state.next_attempt_at is None
    assert state.attempts == 0
    assert state.last_error == ""


# ── 훑기 (안전망) ────────────────────────────────────────────────────────────


def test_a_document_with_no_state_row_is_found_by_the_sweep(db, document):
    """이관 직후·신호를 빠뜨린 문서가 여기 걸린다."""
    db.execute(AiIndexState.__table__.delete())
    db.flush()
    index_service.sweep_stale(db, versions=index_service.current_versions(_gateway()))
    assert _state(db, document.id).status == STATE_PENDING


def test_a_new_parser_version_makes_every_document_stale(db, document, monkeypatch):
    """파서를 고치면 같은 파일에서 다른 글이 나온다."""
    _settle(db)
    assert _state(db, document.id).status == STATE_OK
    monkeypatch.setattr(catalog, "PARSER_VERSION", "99")
    index_service.sweep_stale(db, versions=index_service.current_versions(_gateway()))
    assert _state(db, document.id).status == STATE_PENDING


def test_a_new_embedding_version_makes_every_document_stale(db, document, monkeypatch):
    """접두사·풀링·정규화가 바뀌면 어제 만든 벡터와 오늘 만든 벡터를 같은 공간에서
    비교할 수 없다."""
    _settle(db)
    monkeypatch.setattr(catalog, "EMBEDDING_VERSION", "99")
    index_service.sweep_stale(db, versions=index_service.current_versions(_gateway()))
    assert _state(db, document.id).status == STATE_PENDING


def test_an_installation_without_a_model_does_not_reindex_forever(db, document):
    """🔴 모델이 없는 설치에서 「임베딩 판이 안 맞는다」로 매 tick 마다 전 문서를 다시
    색인하면, **아무 벡터도 안 만들면서 CPU 만 태운다.** 그 상태에서도 최신은 최신이다.
    """
    empty = contract.Gateway(enabled=True, embed_adapter=None, generate_adapter=None)
    index_service.run_once(db, gateway=empty, limit=20)
    assert _state(db, document.id).status == STATE_OK
    index_service.sweep_stale(db, versions=index_service.current_versions(empty))
    assert _state(db, document.id).status == STATE_OK


def test_swapping_a_file_for_another_one_is_caught(db, document):
    """id 만 지문에 넣으면 같은 자리의 파일을 바꿔 끼웠을 때 안 잡힌다."""
    attachments.attach(db, document, filename="a.pptx", content=_pptx("첫 파일의 내용입니다."))
    db.flush()
    _settle(db)
    first = _state(db, document.id).attachment_fingerprint

    link = db.execute(
        select(attachments.DocumentAttachment).where(
            attachments.DocumentAttachment.document_id == document.id
        )
    ).scalar_one()
    attachments.detach(db, link)
    attachments.attach(db, document, filename="b.pptx", content=_pptx("둘째 파일의 내용입니다."))
    db.flush()
    _settle(db)
    assert _state(db, document.id).attachment_fingerprint != first


def test_the_fingerprint_of_no_attachments_is_still_a_value(db, document):
    """「없다」도 값이다. 빈 문자열로 두면 「아직 안 재 봤다」와 구별되지 않는다."""
    _settle(db)
    assert _state(db, document.id).attachment_fingerprint == index_service._EMPTY_FINGERPRINT
    assert len(index_service._EMPTY_FINGERPRINT) == 64


def test_the_sweep_asks_for_every_fingerprint_in_one_query(db, document):
    """문서마다 따로 물으면 문서 1,238건에 질의가 1,238번이고, 그것이 매 tick 마다
    돈다. 훑기는 안전망이지 부하가 아니다."""
    _settle(db)
    calls: list[int] = []
    original = index_service.attachment_fingerprints

    def counting(session, ids):
        ids = list(ids)
        calls.append(len(ids))
        return original(session, ids)

    index_service.attachment_fingerprints = counting
    try:
        index_service.sweep_stale(db, versions=index_service.current_versions(_gateway()))
    finally:
        index_service.attachment_fingerprints = original
    assert len(calls) == 1


def test_reindex_all_puts_every_document_back_in_the_queue(db, document):
    """모델을 바꿨을 때 부르는 그 함수다 — 재생성 경로를 항상 살려 둔다(D-203)."""
    _settle(db)
    assert index_service.enqueue_all(db) == 1
    assert _state(db, document.id).status == STATE_PENDING
