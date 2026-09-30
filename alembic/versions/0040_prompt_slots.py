"""프롬프트 사용처와 세 단계 생명주기 (계획 3.8, D-518).

Revision ID: 0040_prompt_slots
Revises: 0039_ai_usage_records

## 무엇이 바뀌나

- `prompts.slot`: 프롬프트가 붙는 사용처(`app/ai/prompts/catalog.py`). 사용처마다 발행본은 하나다(부분 유니크).
  AI 런타임이 다음 호출부터 그 발행본을 쓰고, 없으면 기본 제공 지시문을 쓴다.
- `ai_usage_records.prompt_id`: 호출이 쓴 발행본의 행 id. 이름이 다른 두 프롬프트가 같은 버전 번호를 가질 수 있어
  (사용처, 버전)만으로는 가를 수 없다.
- 생명주기를 초안 → 발행 → 보관 셋으로 줄인다. 「테스트」와 「검토」는 상태 글자만 바꿀 뿐 아무것도 하지 않았다 -
  그 상태의 프롬프트와 정책은 초안으로 되돌린다.
- `schedules.prompt_id` 를 지운다. 스케줄은 더 이상 프롬프트를 가리킬 수 없다(S11 이 실행기와 함께 걷었다).

## 옛 프롬프트

런타임은 이 표를 한 번도 읽지 않았다. 그래서 지금 「발행」인 프롬프트도 실제로 쓰인 적이 없다. 이제부터 발행은
「이 사용처에서 지금 쓴다」는 뜻이므로 사용처가 없는 발행본은 보관한다(새 버전을 만들어 사용처를 고르면 다시 쓸 수
있다). 지워진 실행기를 위해 넣었던 시드 프롬프트는 상태와 관계없이 보관한다. 시드는 **내용의 모양**으로 찾는다 -
이름에는 가운뎃점이 있고, 관리자가 이름을 바꿨을 수 있다. 업그레이드가 AI 답을 몰래 바꾸지 않도록 어떤 옛 프롬프트도
사용처에 자동으로 붙이지 않는다.

## 되돌리기

구조만 되돌린다(칸과 인덱스, `schedules.prompt_id`). 초안으로 되돌린 상태와 보관한 옛 프롬프트는 되돌리지 않는다 -
어느 행이 「테스트」였는지는 이미 남아 있지 않고, 되돌린 코드도 초안에서 다시 올리면 된다.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "0040_prompt_slots"
down_revision = "0039_ai_usage_records"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.0040")

LEGACY_NOTE = "지워진 실행기용 프롬프트라 보관했습니다."
NO_SLOT_NOTE = "사용처가 없어 보관했습니다. 새 버전에서 사용처를 고르면 다시 쓸 수 있습니다."


def upgrade() -> None:
    op.add_column("prompts", sa.Column("slot", sa.String(32)))
    op.create_index("ix_prompts_slot", "prompts", ["slot"])
    op.create_index(
        "ux_prompts_slot_published", "prompts", ["slot"], unique=True,
        postgresql_where=sa.text("status = 'published' AND slot IS NOT NULL"),
    )
    op.add_column("ai_usage_records", sa.Column("prompt_id", sa.String(36)))

    conn = op.get_bind()
    for table in ("prompts", "policies"):
        moved = conn.execute(sa.text(
            f"UPDATE {table} SET status = 'draft' WHERE status IN ('test', 'review')"  # noqa: S608 - 표 이름은 상수
        )).rowcount
        logger.info("0040: %s 의 테스트 · 검토 상태 %s건을 초안으로 되돌렸다", table, moved)

    legacy = conn.execute(sa.text(
        "UPDATE prompts SET status = 'archived', "
        "purpose = CASE WHEN purpose IS NULL OR purpose = '' THEN :note ELSE :note || ' ' || purpose END "
        "WHERE content LIKE :shape AND status <> 'archived'"
    ), {"note": LEGACY_NOTE, "shape": "당신은 ClovirONE%"}).rowcount
    logger.info("0040: 지워진 실행기용 시드 프롬프트 %s건을 보관했다", legacy)

    unslotted = conn.execute(sa.text(
        "UPDATE prompts SET status = 'archived', "
        "purpose = CASE WHEN purpose IS NULL OR purpose = '' THEN :note ELSE :note || ' ' || purpose END "
        "WHERE status = 'published' AND slot IS NULL"
    ), {"note": NO_SLOT_NOTE}).rowcount
    logger.info("0040: 사용처 없이 발행돼 있던 프롬프트 %s건을 보관했다", unslotted)

    op.drop_column("schedules", "prompt_id")


def downgrade() -> None:
    op.add_column("schedules", sa.Column("prompt_id", sa.String(36)))
    op.drop_column("ai_usage_records", "prompt_id")
    op.drop_index("ux_prompts_slot_published", table_name="prompts")
    op.drop_index("ix_prompts_slot", table_name="prompts")
    op.drop_column("prompts", "slot")
