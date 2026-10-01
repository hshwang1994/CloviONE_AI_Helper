"""🔴 AI 도우미 한 차례 = 사용 기록 한 행 = 한도 한 칸 (D-537).

제공자를 여러 번 부르는 차례도 사람의 요청 한 번이다. 한도는 성공한 차례만 세고, 하루 한도를 다 쓰면 다음 전송은 잡을 만들기
전에 429 로 막히며 그 사실이 `blocked_quota` 행으로 남는다. 실패한 차례는 한도를 쓰지 않는다.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select

from app.ai.models import AiUsageRecord
from app.ai.providers import base
from app.jobs.handlers.chat_message import handle_chat_message
from app.jobs.worker import Worker, WorkerContext
from tests.fakes.ai import ScriptedToolAdapter, install_runtime, tool_call

# 막힌 요청의 `blocked_quota` 행은 제품이 별도 세션으로 커밋해 요청 롤백 뒤에도 남는다 - 공유 계층에서는 그 세션이
# 같은 커넥션의 SAVEPOINT 라 함께 되감긴다(tests/conftest.py 의 다섯째 경우). 그래서 자기 DB 에서 돈다.
pytestmark = [pytest.mark.integration, pytest.mark.real_db]


@pytest.fixture()
def capped(db, make_user):
    from app.quotas.models import AiQuota

    user = make_user("turncap@goodmit.co.kr", role="user", display_name="한도사용자")
    db.add(AiQuota(scope_type="user", user_id=user.id, period="day", max_calls=1,
                   created_at=datetime(2026, 8, 1), updated_at=datetime(2026, 8, 1)))
    db.commit()
    return user


def _worker(app, settings, fake_clock, adapter):
    runtime = install_runtime(app, adapter)
    ctx = WorkerContext(settings=settings, clock=fake_clock, outbound_client=app.state.outbound_client,
                        extras={"ai_runtime": runtime, "session_factory": app.state.session_factory,
                                "settings_cache": app.state.settings_cache})
    return Worker(app.state.session_factory, fake_clock, {"chat_message": handle_chat_message}, ctx,
                  poll_interval=0.01)


def _send(client, csrf, conversation_id, message_id, text="질문"):
    return client.post(f"/api/conversations/{conversation_id}/messages",
                       json={"content": text, "client_message_id": message_id}, headers={"X-CSRF-Token": csrf})


def _rows(db, user_id):
    db.expire_all()
    return db.execute(select(AiUsageRecord).where(AiUsageRecord.user_id == user_id)
                      .order_by(AiUsageRecord.created_at)).scalars().all()


def test_a_three_round_turn_spends_exactly_one_slot_and_the_next_send_is_refused(
        app, client, login_as, db, settings, fake_clock, capped):
    worker = _worker(app, settings, fake_clock, ScriptedToolAdapter([
        tool_call("my_work", {"view": "assigned", "include_done": None}),
        tool_call("my_approvals", {"box": "todo"}),
        "정리했습니다.",
    ]))
    csrf = login_as("user", email="turncap@goodmit.co.kr")
    conversation = client.post("/api/conversations", json={}, headers={"X-CSRF-Token": csrf}).json()["conversation"]

    assert _send(client, csrf, conversation["id"], "q" * 32).status_code == 202
    worker.run_once()
    rows = _rows(db, capped.id)
    assert [(r.action_key, r.status, r.rounds) for r in rows] == [("assistant.chat", "ok", 3)]

    refused = _send(client, csrf, conversation["id"], "r" * 32)
    assert refused.status_code == 429
    assert [r.status for r in _rows(db, capped.id)] == ["ok", "blocked_quota"]


def test_a_failed_turn_does_not_spend_the_slot(app, client, login_as, db, settings, fake_clock, capped):
    worker = _worker(app, settings, fake_clock, ScriptedToolAdapter([
        base.converse_failure(base.ERROR_TRANSIENT, "timeout"), "둘째에는 답합니다.",
    ]))
    csrf = login_as("user", email="turncap@goodmit.co.kr")
    conversation = client.post("/api/conversations", json={}, headers={"X-CSRF-Token": csrf}).json()["conversation"]

    assert _send(client, csrf, conversation["id"], "s" * 32).status_code == 202
    worker.run_once()
    assert [r.status for r in _rows(db, capped.id)] == ["error"]

    # 실패한 차례는 한 칸을 쓰지 않았다 - 같은 날 다시 보낼 수 있다.
    assert _send(client, csrf, conversation["id"], "t" * 32).status_code == 202
    worker.run_once()
    assert [r.status for r in _rows(db, capped.id)] == ["error", "ok"]
