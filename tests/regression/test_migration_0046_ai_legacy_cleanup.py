"""0046 — 옛 · 죽은 AI 데이터 정리 (계획 A7, D-544).

못박는 성질:
1. 사용처가 없는 초안은 보관되고 까닭이 적힌다. 사용처가 있는 초안 · 발행본은 그대로다.
2. 죽은 시드(보관 · 사용처 없음 · 만든 사람 없음 · 옛 시드 내용 · 호출 기록 참조 없음)만 지운다. 호출 기록이 참조하는 시드와
   관리자가 쓴 연결 없는 보관본은 남는다.
3. `usage_events` 의 `ai.call` 만 지운다. 다른 사건은 남는다.
4. `conversations.backend_conversation_id` 열이 사라지고 대화 행은 남는다.
5. 내리면 열이 nullable 로 돌아오고, 다시 올려도 같은 결과다(재실행 무해).
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
import sqlalchemy as sa

from tests.regression.test_migration_0041_ai_policies import _alembic, _engine

pytestmark = pytest.mark.regression

BEFORE = "0045_chatgpt_paste_login"
TARGET = "0046_ai_legacy_cleanup"
WHEN = datetime(2026, 9, 1, 0, 0, 0)
SEED = "당신은 ClovirONE 의 업무 도우미입니다. 옛 시드 지시문입니다."


def _prompt(conn, *, name: str, status: str, slot: str | None, created_by: str | None, content: str = "지시문입니다.") -> str:
    row_id = str(uuid.uuid4())
    conn.execute(sa.text(
        "INSERT INTO prompts (id, name, purpose, version, content, slot, status, created_by, created_at) "
        "VALUES (:id, :name, NULL, 1, :content, :slot, :status, :by, :at)"
    ), {"id": row_id, "name": name, "content": content, "slot": slot, "status": status, "by": created_by, "at": WHEN})
    return row_id


def _usage_ref(conn, prompt_id: str) -> None:
    conn.execute(sa.text(
        "INSERT INTO ai_usage_records (id, created_at, actor_kind, action_key, status, prompt_id) "
        "VALUES (:id, :at, 'system', 'assistant.chat', 'ok', :pid)"
    ), {"id": str(uuid.uuid4()), "at": WHEN, "pid": prompt_id})


def _event(conn, name: str) -> str:
    row_id = str(uuid.uuid4())
    conn.execute(sa.text("INSERT INTO usage_events (id, event, created_at) VALUES (:id, :event, :at)"),
                 {"id": row_id, "event": name, "at": WHEN})
    return row_id


def _prompts(conn) -> dict[str, tuple]:
    return {row_id: (status, purpose) for row_id, status, purpose in
            conn.execute(sa.text("SELECT id, status, purpose FROM prompts")).all()}


@pytest.mark.real_db
def test_legacy_ai_rows_are_classified_and_cleaned(db, db_url, make_user):
    author = make_user("mig-0046-author@goodmit.co.kr", role="system_admin").id
    engine = _engine(db, db_url)
    try:
        _alembic(db_url, "downgrade", BEFORE)
        with engine.begin() as conn:
            slotless_draft = _prompt(conn, name="사용처 없는 초안", status="draft", slot=None, created_by=author)
            live_draft = _prompt(conn, name="도우미 초안", status="draft", slot="assistant", created_by=author)
            live_published = _prompt(conn, name="요약 지시문", status="published", slot="narrative", created_by=author)
            dead_seed = _prompt(conn, name="옛 시드", status="archived", slot=None, created_by=None, content=SEED)
            referenced_seed = _prompt(conn, name="참조된 시드", status="archived", slot=None, created_by=None, content=SEED)
            _usage_ref(conn, referenced_seed)
            admin_archive = _prompt(conn, name="관리자 보관본", status="archived", slot=None, created_by=author,
                                    content=SEED)
            ai_event = _event(conn, "ai.call")
            login_event = _event(conn, "auth.login")
            conversation = str(uuid.uuid4())
            conn.execute(sa.text(
                "INSERT INTO conversations (id, user_id, title, backend_conversation_id, archived, created_at, updated_at) "
                "VALUES (:id, :user, '옛 대화', 'runner-123', false, :at, :at)"
            ), {"id": conversation, "user": author, "at": WHEN})

        _alembic(db_url, "upgrade", TARGET)
        with engine.connect() as conn:
            rows = _prompts(conn)
            events = {row_id for (row_id,) in conn.execute(sa.text("SELECT id FROM usage_events")).all()}
            kept_conversation = conn.execute(sa.text("SELECT title FROM conversations WHERE id = :id"),
                                             {"id": conversation}).scalar_one()
        assert rows[slotless_draft][0] == "archived" and "사용처가 없는 초안이라 보관했습니다." in rows[slotless_draft][1]
        assert rows[live_draft] == ("draft", None) and rows[live_published] == ("published", None)
        assert dead_seed not in rows, "참조도 만든 사람도 없는 옛 시드는 지운다"
        assert referenced_seed in rows, "호출 기록이 참조하는 시드는 지우지 않는다"
        assert admin_archive in rows, "관리자가 쓴 보관본은 지우지 않는다"
        assert ai_event not in events and login_event in events
        assert kept_conversation == "옛 대화"
        columns = {c["name"] for c in sa.inspect(engine).get_columns("conversations")}
        assert "backend_conversation_id" not in columns

        _alembic(db_url, "downgrade", BEFORE)
        column = next(c for c in sa.inspect(engine).get_columns("conversations") if c["name"] == "backend_conversation_id")
        assert column["nullable"] is True
        _alembic(db_url, "upgrade", TARGET)
        _alembic(db_url, "upgrade", "head")
        with engine.connect() as conn:
            assert _prompts(conn)[live_draft] == ("draft", None), "다시 올려도 같은 결과다"
    finally:
        with engine.begin() as conn:
            conn.execute(sa.text("DELETE FROM conversations WHERE title = '옛 대화'"))
            conn.execute(sa.text("DELETE FROM ai_usage_records WHERE action_key = 'assistant.chat' AND actor_kind = 'system'"))
            conn.execute(sa.text("DELETE FROM usage_events WHERE event IN ('ai.call', 'auth.login')"))
            conn.execute(sa.text("DELETE FROM prompts"))
        engine.dispose()
