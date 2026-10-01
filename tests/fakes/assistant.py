"""AI 도우미 한 차례를 시험에서 돌린다 — 진짜 런타임 · 진짜 도구 · 가짜 제공자 (D-535).

HTTP 와 워커를 거치지 않고 `app.ai.assistant.turn.run` 을 바로 부른다. 대화와 사용자 메시지 행은 여기서 심는다.
제공자가 무엇을 받았는지는 돌려준 어댑터(`ScriptedToolAdapter`)가 들고 있다.

    reply, adapter = run_turn(app, db, user, "연차 며칠이야?", [tool_call("search_documents", {"query": "연차"}), "답"])
"""

from __future__ import annotations

import uuid

from app.ai.gateway import contract


def tool_env(app, user, *, gateway=None):
    from app.ai.assistant import catalog

    return catalog.ToolEnv(
        session_factory=app.state.session_factory, user_id=user.id, settings=app.state.settings,
        outbound=app.state.outbound_client, gateway=gateway or contract.Gateway(enabled=True, embed_adapter=None),
        settings_cache=app.state.settings_cache, now=app.state.clock.now(),
    )


def run_turn(app, db, user, question: str, turns, *, gateway=None, screen_context=None, adapter=None):
    """(TurnReply, 어댑터). ``turns`` 는 `ScriptedToolAdapter` 의 대본이다(``adapter`` 를 주면 그것을 쓴다)."""
    from app.ai.assistant import turn as turn_mod
    from app.conversations.models import PROC_PROCESSING, ROLE_USER_MSG, Conversation, Message
    from tests.fakes.ai import ScriptedToolAdapter, install_runtime

    adapter = adapter or ScriptedToolAdapter(turns)
    runtime = install_runtime(app, adapter)
    conversation = Conversation(user_id=user.id, title="시험 대화")
    db.add(conversation)
    db.flush()
    message = Message(conversation_id=conversation.id, message_id=f"m{uuid.uuid4().hex}", role=ROLE_USER_MSG,
                      content=question, processing_status=PROC_PROCESSING)
    db.add(message)
    db.commit()
    now = app.state.clock.now()
    reply = turn_mod.run(
        db, owner=user, user_message=message, conversation_id=conversation.id, runtime=runtime,
        env=tool_env(app, user, gateway=gateway), screen_context=screen_context, today=now.date(), job_id=None,
        progress=None,
    )
    return reply, adapter
