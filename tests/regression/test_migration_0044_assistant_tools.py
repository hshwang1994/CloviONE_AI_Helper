"""0044 — AI 도우미 한 차례의 사용 기록 칸 · 제공자 능력 · 정책 대상 옮기기 (D-535 · D-537).

못박는 성질:
1. 옛 형식이 아닌 정책의 대상에서 `chat.answer` · `workspace.ask` 가 `assistant.chat` 하나가 된다(중복 없이). 이것을
   빼면 채팅이 새 액션 이름으로 나가는 순간 개인정보 가리기가 조용히 꺼진다.
2. `["*"]` · 다른 액션 · 옛 형식(`legacy`) 정책은 그대로다.
3. 은퇴한 사용처(`answer`)의 보관 아닌 지시문은 보관되고 까닭이 적힌다. 다른 사용처의 지시문은 그대로다.
4. 사용 기록에 `rounds` · `tool_calls` · `tool_names_json` · `mode`, 연결 상태에 `capabilities_json` 이 생긴다.
5. 내리면 칸이 사라지고 대상이 옛 두 이름으로 돌아간다. 다시 올려도 같은 결과다(재실행 무해).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest
import sqlalchemy as sa

from tests.regression.test_migration_0041_ai_policies import _alembic, _engine

pytestmark = pytest.mark.regression

BEFORE = "0043_mail_delivery_recipient"
TARGET = "0044_assistant_tools"
WHEN = datetime(2026, 9, 1, 0, 0, 0)
USAGE_COLUMNS = {"rounds", "tool_calls", "tool_names_json", "mode"}


def _policy(conn, *, name: str, kind: str, targets: list[str], status: str = "published") -> str:
    row_id = str(uuid.uuid4())
    conn.execute(sa.text(
        "INSERT INTO policies (id, name, version, kind, applies_to_json, content_json, status, created_at) "
        "VALUES (:id, :name, 1, :kind, CAST(:targets AS jsonb), CAST('{}' AS jsonb), :status, :at)"
    ), {"id": row_id, "name": name, "kind": kind, "targets": json.dumps(targets), "status": status, "at": WHEN})
    return row_id


def _prompt(conn, *, name: str, slot: str, status: str, purpose: str | None = None) -> str:
    row_id = str(uuid.uuid4())
    conn.execute(sa.text(
        "INSERT INTO prompts (id, name, purpose, version, content, slot, status, created_at) "
        "VALUES (:id, :name, :purpose, 1, '지시문입니다.', :slot, :status, :at)"
    ), {"id": row_id, "name": name, "purpose": purpose, "slot": slot, "status": status, "at": WHEN})
    return row_id


def _targets(conn) -> dict[str, list]:
    rows = conn.execute(sa.text("SELECT id, applies_to_json FROM policies")).all()
    return {row_id: (raw if isinstance(raw, list) else json.loads(raw)) for row_id, raw in rows}


def _prompts(conn) -> dict[str, tuple]:
    return {row_id: (status, purpose) for row_id, status, purpose in
            conn.execute(sa.text("SELECT id, status, purpose FROM prompts")).all()}


@pytest.mark.real_db
def test_policy_targets_move_to_the_assistant_and_the_answer_use_retires(db, db_url):
    engine = _engine(db, db_url)
    try:
        _alembic(db_url, "downgrade", BEFORE)
        with engine.begin() as conn:
            conn.execute(sa.text("DELETE FROM policies"))
            conn.execute(sa.text("DELETE FROM prompts"))
            both = _policy(conn, name="개인정보", kind="data_protection", targets=["chat.answer", "workspace.ask"])
            mixed = _policy(conn, name="짧게", kind="content", targets=["workspace.ask", "home.narrative"])
            star = _policy(conn, name="전부", kind="content", targets=["*"])
            other = _policy(conn, name="초안", kind="approval", targets=["workspace.draft"])
            legacy = _policy(conn, name="옛것", kind="legacy", targets=["chat.answer"], status="archived")
            answer_live = _prompt(conn, name="답변", slot="answer", status="published", purpose="채팅 답")
            answer_draft = _prompt(conn, name="답변 초안", slot="answer", status="draft")
            answer_old = _prompt(conn, name="답변 옛것", slot="answer", status="archived", purpose="그대로")
            draft_live = _prompt(conn, name="초안", slot="draft", status="published")
        _alembic(db_url, "upgrade", TARGET)
        with engine.begin() as conn:
            targets = _targets(conn)
            prompts = _prompts(conn)
            usage = {c["name"] for c in sa.inspect(conn).get_columns("ai_usage_records")}
            state = {c["name"] for c in sa.inspect(conn).get_columns("ai_credential_state")}
        assert targets[both] == ["assistant.chat"], "옛 두 이름이 새 이름 하나로 합쳐지지 않았다"
        assert targets[mixed] == ["assistant.chat", "home.narrative"]
        assert targets[star] == ["*"] and targets[other] == ["workspace.draft"]
        assert targets[legacy] == ["chat.answer"], "옛 형식 정책을 건드렸다"
        note = "AI 도우미가 도구를 쓰는 방식으로 바뀌어 보관했습니다."
        assert prompts[answer_live] == ("archived", f"채팅 답 {note}")
        assert prompts[answer_draft] == ("archived", note)
        assert prompts[answer_old] == ("archived", "그대로"), "이미 보관된 지시문의 까닭을 덮었다"
        assert prompts[draft_live][0] == "published"
        assert USAGE_COLUMNS <= usage and "capabilities_json" in state

        _alembic(db_url, "downgrade", BEFORE)
        with engine.begin() as conn:
            targets = _targets(conn)
            usage = {c["name"] for c in sa.inspect(conn).get_columns("ai_usage_records")}
            state = {c["name"] for c in sa.inspect(conn).get_columns("ai_credential_state")}
        assert targets[both] == ["chat.answer", "workspace.ask"]
        assert targets[mixed] == ["chat.answer", "workspace.ask", "home.narrative"]
        assert not (USAGE_COLUMNS & usage) and "capabilities_json" not in state

        _alembic(db_url, "upgrade", TARGET)
        with engine.begin() as conn:
            again = _targets(conn)
        assert again[both] == ["assistant.chat"] and again[mixed] == ["assistant.chat", "home.narrative"]
    finally:
        _alembic(db_url, "upgrade", "head")
        engine.dispose()
