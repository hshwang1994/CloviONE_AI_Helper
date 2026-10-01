"""AI 도우미 한 차례 — 도구 왕복의 사용 기록 · 제공자 능력 · 정책 대상 옮기기 (D-535 · D-537).

Revision ID: 0044_assistant_tools
Revises: 0043_mail_delivery_recipient

## 무엇이 바뀌나

- `ai_usage_records` 에 `rounds` · `tool_calls`(SMALLINT), `tool_names_json`(TEXT, 도구 이름만), `mode`(VARCHAR 16 —
  tools · search_only). 사람의 AI 요청 한 번이 한 행이고(D-537), 도우미 한 차례는 제공자를 여러 번 부르므로 그 모양을 이
  칸들이 말한다.
- `ai_credential_state.capabilities_json` — 지금 설정(지문)으로 제공자 · 모델이 도구를 받는가(`{"tools": "ok|unsupported",
  "model", "checked_at", "fingerprint"}`). 도구를 거절하는 요금제 · 모델에는 서버 검색 뒤 도구 없는 한 번의 호출로 대신한다.
- **정책 대상 옮기기**: 옛 형식이 아닌 정책의 `applies_to_json` 에서 `chat.answer` · `workspace.ask` 를 `assistant.chat` 으로
  바꾸고 중복을 지운다(`["*"]` 는 그대로). 이것을 빼면 채팅이 새 액션 이름으로 나가는 순간 개인정보 가리기 같은 정책이
  조용히 꺼진다 — 정책 엔진은 액션 키로 맞춘다(`app/ai/policy/engine.py`).
- 사용처 `answer`(질문 답변)는 은퇴한다. 보관되지 않은 그 사용처의 지시문을 보관하고 까닭을 적는다.

## 되돌리기

칸을 지우고, 정책 대상의 `assistant.chat` 을 `["chat.answer", "workspace.ask"]` 로 되돌린다. 보관한 지시문은 보관 그대로
둔다(0040 과 같은 처리 — 되살리면 어느 것을 발행할지 사람이 정해야 한다).
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa
from alembic import op

revision = "0044_assistant_tools"
down_revision = "0043_mail_delivery_recipient"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.0044")

OLD_ACTIONS = ("chat.answer", "workspace.ask")
NEW_ACTION = "assistant.chat"
RETIRED_SLOT = "answer"
RETIRED_NOTE = "AI 도우미가 도구를 쓰는 방식으로 바뀌어 보관했습니다."


def _targets(raw) -> list | None:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except ValueError:
            return None
        return value if isinstance(value, list) else None
    return None


def upgrade() -> None:
    op.add_column("ai_usage_records", sa.Column("rounds", sa.SmallInteger(), nullable=True))
    op.add_column("ai_usage_records", sa.Column("tool_calls", sa.SmallInteger(), nullable=True))
    op.add_column("ai_usage_records", sa.Column("tool_names_json", sa.Text(), nullable=True))
    op.add_column("ai_usage_records", sa.Column("mode", sa.String(16), nullable=True))
    op.add_column("ai_credential_state", sa.Column("capabilities_json", sa.Text(), nullable=True))

    conn = op.get_bind()
    moved = 0
    rows = conn.execute(sa.text("SELECT id, applies_to_json FROM policies WHERE kind <> 'legacy'")).all()
    for policy_id, raw in rows:
        targets = _targets(raw)
        if not targets or targets == ["*"] or not any(t in OLD_ACTIONS for t in targets):
            continue
        out: list[str] = []
        for target in targets:
            value = NEW_ACTION if target in OLD_ACTIONS else target
            if value not in out:
                out.append(value)
        conn.execute(
            sa.text("UPDATE policies SET applies_to_json = CAST(:v AS jsonb) WHERE id = :id"),
            {"v": json.dumps(out), "id": policy_id},
        )
        moved += 1
    logger.info("0044: 정책 %s건의 대상을 %s 으로 옮겼다", moved, NEW_ACTION)

    archived = conn.execute(
        sa.text(
            "UPDATE prompts SET status = 'archived', "
            "purpose = CASE WHEN purpose IS NULL OR purpose = '' THEN :note ELSE purpose || ' ' || :note END "
            "WHERE slot = :slot AND status <> 'archived'"
        ),
        {"slot": RETIRED_SLOT, "note": RETIRED_NOTE},
    ).rowcount
    logger.info("0044: 은퇴한 사용처(%s)의 지시문 %s건을 보관했다", RETIRED_SLOT, archived)


def downgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, applies_to_json FROM policies WHERE kind <> 'legacy'")).all()
    for policy_id, raw in rows:
        targets = _targets(raw)
        if not targets or NEW_ACTION not in targets:
            continue
        out: list[str] = []
        for target in targets:
            for value in (OLD_ACTIONS if target == NEW_ACTION else (target,)):
                if value not in out:
                    out.append(value)
        conn.execute(
            sa.text("UPDATE policies SET applies_to_json = CAST(:v AS jsonb) WHERE id = :id"),
            {"v": json.dumps(out), "id": policy_id},
        )
    op.drop_column("ai_credential_state", "capabilities_json")
    op.drop_column("ai_usage_records", "mode")
    op.drop_column("ai_usage_records", "tool_names_json")
    op.drop_column("ai_usage_records", "tool_calls")
    op.drop_column("ai_usage_records", "rounds")
