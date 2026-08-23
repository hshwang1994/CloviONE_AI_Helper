"""채팅이 **제품 안에서** 답한다 — 권한이 먼저 걸린다 (S11 · D-202 · D-256).

qa-contract-replaced-by: tests/integration/test_chat_handler.py
qa-contract-replaced-by: tests/integration/test_chat_ticket_routing_contract.py
qa-contract-replaced-by: tests/integration/test_chat_notion_refusal.py
qa-contract-replaced-by: tests/unit/test_chat_extract_text.py

## 왜 옛 시험 넷을 이 파일이 대신하는가

넷 다 **n8n 웹훅으로 나가는 HTTP 계약**을 고정하고 있었다 — 어떤 본문을 POST 하는지,
5xx 는 재시도인지, 응답의 어느 키를 답으로 읽는지, 매핑 안 된 사용자의 요청도 넘기는지.
S11 이 그 경로를 걷어냈으니 같은 계약을 다른 파일에 옮겨 적을 수는 없다.

지켜야 할 계약은 그대로 있고 **더 세졌다**: 옛 경로는 Notion 작업 DB 전량을 러너에 넘기고
요청자를 필터로 쓰지 않았다. 새 경로는 `effective_visibility_clause` 가 만든 후보 집합
안에서만 검색한다. 그래서 이 파일의 중심 시험은 「답변에 안 나왔다」가 아니라
**「모델에게 넘어간 문자열에 없다」**를 본다(D-202 가 그렇게 쓰라고 적어 뒀다).
"""

from __future__ import annotations

import json

import pytest

from app.ai import catalog
from app.ai.gateway import contract
from app.ai.index import service as index_service
from app.conversations.models import PROC_DONE, PROC_FAILED, Message
from app.jobs.handlers.chat_message import handle_chat_message
from app.jobs.worker import Worker, WorkerContext
from app.knowledge import versions
from app.knowledge.models import Document, KnowledgeSpace
from app.org.constants import DEFAULT_ORG_ID

pytestmark = pytest.mark.integration

MSG_ID = "h0123456789abcdef0123456789abcdef"


# ── 가짜 모델 둘 ─────────────────────────────────────────────────────────────


class TopicEmbed(contract.EmbedAdapter):
    """**주제표**로 벡터를 만든다 (`test_ai_retrieval.py::ScriptedEmbed` 와 같은 발상).

    모든 글을 같은 벡터로 만들면 벡터 레인이 **무엇에나 답을 준다** — 그러면 「근거가
    없다」를 시험할 수 없다. 주제에 안 걸리는 글은 마지막 축 하나만 1 이라 어느 주제와도
    멀고, 그 거리(√2)가 벡터 레인 상한(D-261)을 훌쩍 넘는다.
    """

    TOPICS = {"leave": ("연차", "휴가", "반차", "보상금")}

    def __init__(self):
        self.name = "topic"
        self.model = catalog.DEFAULT_EMBEDDING_MODEL_ID
        self.dim = catalog.VECTOR_DIM

    def capability(self):
        return contract.available(contract.CAP_EMBED, model=self.model)

    def _vector(self, text: str) -> tuple[float, ...]:
        values = [0.0] * self.dim
        for axis, (_, words) in enumerate(sorted(self.TOPICS.items())):
            if any(word in text for word in words):
                values[axis] = 1.0
        if not any(values):
            values[-1] = 1.0
        norm = sum(v * v for v in values) ** 0.5
        return tuple(v / norm for v in values)

    def embed(self, texts, *, kind=catalog.KIND_PASSAGE):
        return contract.EmbedResult(
            status=contract.STATUS_OK, model=self.model, dim=self.dim,
            vectors=tuple(self._vector(t) for t in texts),
        )


class ScriptedGenerate(contract.GenerateAdapter):
    """넘어온 (system, user) 쌍을 그대로 들고 있는다. **그것이 시험 대상이다.**"""

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


def _gateway(generate) -> contract.Gateway:
    return contract.Gateway(
        enabled=True, embed_adapter=TopicEmbed(), generate_adapter=generate
    )


# ── 세계 ─────────────────────────────────────────────────────────────────────


def _body(*paragraphs: str) -> dict:
    return {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": p}]}
            for p in paragraphs
        ],
    }


@pytest.fixture()
def chatter(db, make_user):
    # **일반 사용자다.** admin 은 `confidential` 을 여는 권한을 갖고 있어서
    # (app/authz/visibility.py) 아래 권한 시험이 아무것도 증명하지 못한다.
    user = make_user("chatter@goodmit.co.kr", role="user", display_name="채팅 사용자")
    user.org_id = DEFAULT_ORG_ID
    db.flush()
    return user


@pytest.fixture()
def space(db):
    row = KnowledgeSpace(
        org_id=DEFAULT_ORG_ID, name="사내 규정", slug="rules", owner_kind="organization"
    )
    db.add(row)
    db.flush()
    return row


def _seed_doc(db, space, title, *paragraphs):
    doc = Document(space_id=space.id, title=title, archived=False)
    db.add(doc)
    db.flush()
    versions.snapshot(db, doc, _body(*paragraphs), author_id=None)
    db.flush()
    return doc


@pytest.fixture()
def worker_for(app, settings, fake_clock):
    """가짜 Gateway 를 실은 워커. 잡 핸들러가 `ctx.extras["ai_gateway"]` 를 읽는다."""

    def build(gateway):
        ctx = WorkerContext(
            settings=settings,
            clock=fake_clock,
            outbound_client=app.state.outbound_client,
            extras={"ai_gateway": gateway},
        )
        return Worker(
            app.state.session_factory, fake_clock,
            {"chat_message": handle_chat_message}, ctx, poll_interval=0.01,
        )

    return build


@pytest.fixture()
def posted(client, login_as, chatter, db):
    db.commit()
    csrf = login_as("user", email="chatter@goodmit.co.kr")
    conv = client.post(
        "/api/conversations", json={}, headers={"X-CSRF-Token": csrf}
    ).json()["conversation"]
    return {"conversation_id": conv["id"], "csrf": csrf}


def _send(client, posted, content, *, message_id=MSG_ID):
    r = client.post(
        f"/api/conversations/{posted['conversation_id']}/messages",
        json={"content": content, "client_message_id": message_id},
        headers={"X-CSRF-Token": posted["csrf"]},
    )
    assert r.status_code == 202, r.text
    return r


def _replies(db, conversation_id):
    rows = db.execute(
        Message.__table__.select().where(
            Message.conversation_id == conversation_id
        ).order_by(Message.seq)
    ).mappings().all()
    return [r for r in rows if r["role"] == "assistant"]


def _user_message(db, conversation_id):
    rows = db.execute(
        Message.__table__.select().where(
            Message.conversation_id == conversation_id
        ).order_by(Message.seq)
    ).mappings().all()
    return next(r for r in rows if r["role"] == "user")


# ── 1. 답이 나온다, 그리고 근거가 함께 나온다 ────────────────────────────────


def test_the_answer_comes_back_with_its_citations(client, db, space, worker_for, posted):
    _seed_doc(db, space, "연차 규정", "연차는 입사 1년 뒤부터 15일이 생긴다.")
    gateway = _gateway(ScriptedGenerate(text="연차는 15일입니다 [1]."))
    index_service.run_once(db, gateway=gateway, limit=50)
    db.commit()

    _send(client, posted, "연차 며칠인가요")
    worker_for(gateway).run_once()

    replies = _replies(db, posted["conversation_id"])
    assert len(replies) == 1
    assert replies[0]["content"] == "연차는 15일입니다 [1]."
    stored = json.loads(replies[0]["structured_payload_json"])
    assert [c["document_title"] for c in stored["citations"]] == ["연차 규정"]
    # 인용은 **눌러서 갈 수 있는 주소**여야 한다 — 서버가 만든다(D-263).
    assert stored["citations"][0]["route"].startswith("/knowledge/")
    assert _user_message(db, posted["conversation_id"])["processing_status"] == PROC_DONE


def test_the_model_only_ever_sees_the_cited_text(client, db, space, worker_for, posted):
    """**Context 는 인용 밖을 못 본다.** 답변이 아니라 넘어간 문자열을 본다(D-202)."""
    _seed_doc(db, space, "연차 규정", "연차는 입사 1년 뒤부터 15일이 생긴다.")
    adapter = ScriptedGenerate()
    gateway = _gateway(adapter)
    index_service.run_once(db, gateway=gateway, limit=50)
    db.commit()

    _send(client, posted, "연차 며칠인가요")
    worker_for(gateway).run_once()

    assert len(adapter.calls) == 1
    system, user = adapter.calls[0]
    assert "연차는 입사 1년 뒤부터 15일이 생긴다." in user
    # 시스템 쪽에는 우리가 쓴 문장만 있다 — 문서 본문이 지시가 되는 자리를 안 만든다.
    assert "연차는 입사 1년 뒤부터" not in system


# ── 2. 권한이 검색보다 먼저 걸린다 (면제되지 않는 검증) ──────────────────────


def test_a_document_the_user_cannot_see_never_reaches_the_model(
    client, db, make_user, worker_for, posted
):
    """옛 경로가 지키지 않던 바로 그 성질이다 — **이것이 S11 의 이유다.**

    확인 지점은 답변 문자열이 아니라 `generate()` 에 넘어간 `user` 다: 모델이 그 문장을
    안 쓰기로 했을 수도 있으므로 「답변에 안 나왔다」는 증거가 못 된다(D-202).
    """
    other = make_user("other@goodmit.co.kr", role="user", display_name="남")
    other.org_id = DEFAULT_ORG_ID
    mine = KnowledgeSpace(
        org_id=DEFAULT_ORG_ID, name="내 공간", slug="mine", owner_kind="organization"
    )
    db.add(mine)
    db.flush()
    _seed_doc(db, mine, "공개 규정", "연차는 15일이다.")
    # `confidential` 이 이 저장소의 **유일한 축소 원시연산**이다(D-231) — 만든 사람과
    # 명시 부여자에게만 보인다. 채팅 사용자는 둘 다 아니다.
    secret = _seed_doc(db, mine, "대외비 규정", "특별 연차 보상금은 300만원이다.")
    secret.confidential = True
    secret.created_by = other.id
    db.flush()

    adapter = ScriptedGenerate()
    gateway = _gateway(adapter)
    index_service.run_once(db, gateway=gateway, limit=50)
    db.commit()

    _send(client, posted, "연차 보상금 얼마인가요")
    worker_for(gateway).run_once()

    assert adapter.calls, "근거를 하나도 못 찾아 모델을 안 불렀다면 이 시험은 아무것도 증명하지 못한다"
    _, user_payload = adapter.calls[0]
    assert "300만원" not in user_payload
    assert "대외비 규정" not in user_payload


# ── 3. 세 갈래를 구별한다 ────────────────────────────────────────────────────


def test_no_evidence_is_an_answer_not_a_failure(client, db, space, worker_for, posted):
    """근거가 0 이면 **모델을 아예 안 부른다**. 그리고 그것은 실패가 아니다 —
    같은 질문을 다시 넣어도 같은 결과라 「다시 시도」를 켜 두면 헛수고다."""
    adapter = ScriptedGenerate()
    gateway = _gateway(adapter)
    db.commit()

    _send(client, posted, "사옥 주차장 배정 기준")
    worker_for(gateway).run_once()

    assert adapter.calls == []
    replies = _replies(db, posted["conversation_id"])
    assert len(replies) == 1
    assert "찾지 못했습니다" in replies[0]["content"]
    assert json.loads(replies[0]["structured_payload_json"])["no_evidence"] is True
    assert _user_message(db, posted["conversation_id"])["processing_status"] == PROC_DONE


def test_when_generation_is_blocked_the_citations_still_come_out(
    client, db, space, worker_for, posted
):
    """생성이 막혀도 근거로는 갈 수 있다(S10 Exit). 그리고 **왜 막혔는지** 말한다."""
    _seed_doc(db, space, "연차 규정", "연차는 입사 1년 뒤부터 15일이 생긴다.")
    gateway = _gateway(ScriptedGenerate(status=contract.STATUS_NOT_LOGGED_IN))
    index_service.run_once(db, gateway=_gateway(ScriptedGenerate()), limit=50)
    db.commit()

    _send(client, posted, "연차 며칠인가요")
    worker_for(gateway).run_once()

    replies = _replies(db, posted["conversation_id"])
    stored = json.loads(replies[0]["structured_payload_json"])
    assert stored["citations"], "생성이 막혔다고 인용까지 사라지면 안 된다"
    assert "로그인되어 있지 않습니다" in replies[0]["content"]
    # 이쪽은 재시도할 값이 있다 — 사용자 메시지를 실패로 남겨 '다시 시도'를 살린다.
    assert _user_message(db, posted["conversation_id"])["processing_status"] == PROC_FAILED


def test_generation_without_a_model_does_not_call_out_to_anything(
    client, db, space, worker_for, posted, fake_http
):
    """**아무 데도 HTTP 를 안 보낸다.** 옛 경로는 여기서 n8n 을 불렀다."""
    _seed_doc(db, space, "연차 규정", "연차는 15일이다.")
    gateway = _gateway(ScriptedGenerate())
    index_service.run_once(db, gateway=gateway, limit=50)
    db.commit()
    fake_http.requests.clear()

    _send(client, posted, "연차 며칠인가요")
    worker_for(gateway).run_once()

    assert fake_http.requests == [], f"채팅이 외부로 나갔다: {[str(r.url) for r in fake_http.requests]}"


# ── 4. 쿼터는 모델이 실제로 답한 경우만 센다 ─────────────────────────────────


def test_quota_counts_only_a_real_answer(client, db, space, chatter, worker_for, posted, fake_clock):
    from app.quotas.service import PERIOD_DAY, used

    _seed_doc(db, space, "연차 규정", "연차는 15일이다.")
    ok_gateway = _gateway(ScriptedGenerate())
    index_service.run_once(db, gateway=ok_gateway, limit=50)
    db.commit()
    now = fake_clock.now()

    # ① 근거가 없다 → 모델을 안 불렀으니 쿼터도 안 센다.
    _send(client, posted, "사옥 주차장 배정 기준", message_id="a" * 32)
    worker_for(_gateway(ScriptedGenerate())).run_once()
    before = used(db, user_id=chatter.id, period=PERIOD_DAY, now=now)

    # ② 실제로 답했다 → 한 번 센다.
    _send(client, posted, "연차 며칠인가요", message_id="b" * 32)
    worker_for(ok_gateway).run_once()
    after = used(db, user_id=chatter.id, period=PERIOD_DAY, now=now)

    assert before == 0
    assert after == 1
