"""AI 작업공간 API — 검색 · 질의 · 문서 초안 (S10).

여기서 보는 것은 **HTTP 경계**다: 게이트가 걸려 있는가, 쿼터를 언제 세는가, 생성이
막혀 있을 때 화면이 무엇을 받는가, 초안이 실제로 `source_type=AI` 문서가 되는가.

Retrieval 자체의 성질은 `test_ai_retrieval.py`, 권한 음성 시험은
`tests/security/test_ai_retrieval_permission.py` 가 본다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.ai import catalog
from app.ai.gateway import contract
from app.ai.index import service as index_service
from app.knowledge import versions
from app.knowledge.models import (
    SOURCE_AI,
    VSRC_AI,
    Document,
    DocumentVersion,
    KnowledgeSpace,
)
from app.observability.models import UsageEvent
from app.org.constants import DEFAULT_ORG_ID

pytestmark = pytest.mark.integration


class FlatEmbed(contract.EmbedAdapter):
    """모든 글을 같은 벡터로. 여기서 벡터 레인은 배선 확인용이다."""

    def __init__(self):
        self.name = "flat"
        self.model = catalog.DEFAULT_EMBEDDING_MODEL_ID
        self.dim = catalog.VECTOR_DIM

    def capability(self):
        return contract.available(contract.CAP_EMBED, model=self.model)

    def embed(self, texts, *, kind=catalog.KIND_PASSAGE):
        one = tuple([1.0] + [0.0] * (self.dim - 1))
        return contract.EmbedResult(
            status=contract.STATUS_OK, model=self.model, dim=self.dim,
            vectors=tuple(one for _ in texts),
        )


class Generator(contract.GenerateAdapter):
    def __init__(self, *, status=contract.STATUS_OK, text="초안 첫 문단.\n\n둘째 문단 [1]."):
        self.name = "scripted"
        self.model = "scripted-model"
        self._status = status
        self._text = text
        self.calls = 0

    def capability(self):
        if self._status != contract.STATUS_OK:
            return contract.unavailable(contract.CAP_GENERATE, self._status, model=self.model)
        return contract.available(contract.CAP_GENERATE, model=self.model)

    def generate(self, *, system: str, user: str):  # noqa: ARG002
        self.calls += 1
        return contract.GenerateResult(
            status=self._status, model=self.model,
            text=self._text if self._status == contract.STATUS_OK else None,
        )


def _install(app, *, generate=None, embed=True) -> contract.Gateway:
    gateway = contract.Gateway(
        enabled=True,
        embed_adapter=FlatEmbed() if embed else None,
        generate_adapter=generate,
    )
    app.state.ai_gateway = gateway
    return gateway


@pytest.fixture()
def seeded(db, app):
    space = KnowledgeSpace(
        org_id=DEFAULT_ORG_ID, name="사내 규정", slug="rules", owner_kind="organization"
    )
    db.add(space)
    db.flush()
    doc = Document(space_id=space.id, title="연차 사용 안내")
    db.add(doc)
    db.flush()
    versions.snapshot(
        db, doc,
        {"type": "doc", "content": [{
            "type": "paragraph",
            "content": [{"type": "text", "text": "연차는 남은 일수 안에서 씁니다. " * 4}],
        }]},
        author_id=None,
    )
    db.flush()
    index_service.run_once(db, gateway=_install(app), limit=20)
    db.commit()
    return {"space": space, "document": doc}


def _ai_calls(db) -> int:
    return int(
        db.execute(
            select(func.count()).select_from(UsageEvent).where(UsageEvent.event == "ai.call")
        ).scalar_one()
    )


# ── status ───────────────────────────────────────────────────────────────────


def test_status_says_what_works_and_what_does_not(client, app, login_as, seeded):
    login_as("user")
    _install(app, generate=Generator(status=contract.STATUS_NOT_LOGGED_IN))

    body = client.get("/api/ai/status").json()
    assert body["capabilities"]["embed"]["available"] is True
    assert body["capabilities"]["generate"]["available"] is False
    # 「안 됩니다」로 끝내지 않는다 — 운영자가 무엇을 해야 하는지가 상태에 있다.
    assert body["capabilities"]["generate"]["status"] == contract.STATUS_NOT_LOGGED_IN
    assert body["capabilities"]["generate"]["notice"]
    # 리랭커는 **일부러** 없다 (D-212 · D-255).
    assert body["capabilities"]["rerank"]["status"] == contract.STATUS_UNSUPPORTED
    assert body["index"]["chunks"] > 0


def test_status_needs_a_session(client, seeded):
    assert client.get("/api/ai/status").status_code == 401


# ── search ───────────────────────────────────────────────────────────────────


def test_search_answers_while_generation_is_blocked(client, app, login_as, db, seeded):
    """🔴 S10 Exit — 생성 Provider 차단 시 검색/인용이 계속 동작한다."""
    login_as("user")
    blocked = Generator(status=contract.STATUS_NOT_LOGGED_IN)
    _install(app, generate=blocked)

    before = _ai_calls(db)
    body = client.get("/api/ai/search", params={"q": "연차"}).json()
    assert body["citations"]
    assert body["citations"][0]["route"].startswith("/knowledge/")
    assert body["citations"][0]["where"]
    assert blocked.calls == 0
    # 검색은 쿼터를 안 쓴다 — 거기서 도는 임베딩은 서버 CPU 이지 구독 호출이 아니다.
    assert _ai_calls(db) == before


def test_search_does_not_ship_the_whole_chunk_to_the_browser(client, app, login_as, seeded):
    login_as("user")
    _install(app)
    body = client.get("/api/ai/search", params={"q": "연차"}).json()
    assert "text_for_context" not in body["citations"][0]
    assert "excerpt" in body["citations"][0]


# ── ask ──────────────────────────────────────────────────────────────────────


def test_ask_needs_csrf(client, login_as, app, seeded):
    login_as("user")
    _install(app, generate=Generator())
    response = client.post("/api/ai/ask", json={"question": "연차"})
    assert response.status_code == 403


def test_ask_returns_the_answer_with_its_evidence(client, app, login_as, db, seeded):
    csrf = login_as("user")
    _install(app, generate=Generator(text="연차는 남은 일수 안에서 씁니다 [1]."))

    before = _ai_calls(db)
    body = client.post(
        "/api/ai/ask", json={"question": "연차"}, headers={"X-CSRF-Token": csrf}
    ).json()
    assert body["answer"] == "연차는 남은 일수 안에서 씁니다 [1]."
    assert body["citations"]
    assert body["notice"] is None
    assert _ai_calls(db) == before + 1


def test_a_failed_generation_does_not_spend_the_quota(client, app, login_as, db, seeded):
    """모델이 죽은 날 사용자가 답을 못 받고 상한만 잃으면 안 된다."""
    csrf = login_as("user")
    _install(app, generate=Generator(status=contract.STATUS_TIMEOUT))

    before = _ai_calls(db)
    body = client.post(
        "/api/ai/ask", json={"question": "연차"}, headers={"X-CSRF-Token": csrf}
    ).json()
    assert body["answer"] is None
    assert body["notice"]
    assert body["citations"]          # 근거는 그대로 나간다
    assert _ai_calls(db) == before


# ── 문서 초안 ────────────────────────────────────────────────────────────────


def test_a_draft_becomes_a_document_marked_as_ai_made(client, app, login_as, db, seeded):
    csrf = login_as("user")
    _install(app, generate=Generator(text="첫 문단입니다.\n\n둘째 문단입니다."))

    body = client.post(
        "/api/ai/documents",
        json={
            "space_id": seeded["space"].id,
            "title": "연차 안내 초안",
            "instruction": "연차 규정을 정리해 주세요",
        },
        headers={"X-CSRF-Token": csrf},
    ).json()
    assert body["document"]["route"] == f"/knowledge/{body['document']['id']}"

    made = db.get(Document, body["document"]["id"])
    assert made.source_type == SOURCE_AI
    version = db.get(DocumentVersion, made.current_version_id)
    # 판에도 AI 로 만들었다는 사실이 남는다 — 「AI 가 만든 문서」와 「AI 로 고친 판」은
    # 다른 사실이고 둘 다 기록돼야 한다.
    assert version.source == VSRC_AI
    assert version.ai_used is True
    # 줄글이 문단 둘이 됐다.
    assert len(version.body["content"]) == 2


def test_a_failed_draft_leaves_no_empty_document(client, app, login_as, db, seeded):
    """제목만 있는 껍데기가 쌓이면 사람은 그것이 실패의 흔적인 줄 모른다."""
    csrf = login_as("user")
    _install(app, generate=Generator(status=contract.STATUS_NOT_LOGGED_IN))

    before = int(db.execute(select(func.count()).select_from(Document)).scalar_one())
    body = client.post(
        "/api/ai/documents",
        json={
            "space_id": seeded["space"].id,
            "title": "만들어지면 안 되는 문서",
            "instruction": "연차 규정을 정리해 주세요",
        },
        headers={"X-CSRF-Token": csrf},
    ).json()
    assert body["document"] is None
    assert body["notice"]
    assert int(db.execute(select(func.count()).select_from(Document)).scalar_one()) == before


def test_a_draft_without_evidence_is_not_written_either(client, app, login_as, db, seeded):
    """근거가 0 이면 모델을 아예 안 부른다 — 빈 Context 로 부르면 모델은 지어낸다.

    임베딩을 끄고 본다. 벡터 레인은 **언제나** 최근접 이웃을 내놓으므로(거리 상한이
    그것을 막는다) 「후보 0」을 키워드 두 레인으로 보는 편이 이 성질에 정확하다.
    """
    csrf = login_as("user")
    generator = Generator()
    _install(app, generate=generator, embed=False)

    body = client.post(
        "/api/ai/documents",
        json={
            "space_id": seeded["space"].id,
            "title": "근거 없는 초안",
            "instruction": "존재하지않는낱말조합xyz",
        },
        headers={"X-CSRF-Token": csrf},
    ).json()
    assert body["document"] is None
    assert generator.calls == 0
