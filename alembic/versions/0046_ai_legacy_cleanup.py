"""옛 · 죽은 AI 데이터 정리 — 화면이 DB 의 역사를 추측하게 하지 않는다 (계획 A7, D-544).

Revision ID: 0046_ai_legacy_cleanup
Revises: 0045_chatgpt_paste_login

## 분류와 처리

| 분류 | 판정 | 처리 |
|---|---|---|
| 연결 없는 초안 | 초안 + 사용처 없음 | 보관 + 「사용처가 없는 초안이라 보관했습니다.」 |
| 죽은 시드 | 보관 + 사용처 없음 + 만든 사람 없음 + 옛 시드 내용(`당신은 ClovirONE…`) + 호출 기록의 `prompt_id` 참조 없음 | 지운다 |
| 관리자가 쓴 연결 없는 보관본 | 보관 + 사용처 없음 + 만든 사람 있음 | 그대로(기능 화면에서 닿지 않는다) |
| `usage_events` 의 `ai.call` | 0039 가 이미 `ai_usage_records` 로 옮겼다 | 지운다 |
| `conversations.backend_conversation_id` | 옛 실행기의 대화 id - 읽는 곳이 없다 | 열을 지운다 |

런타임에서 쓰는 지시문, 유효한 초안, 보관 역사, 정책(옛 형식 원본 포함), 0039 가 옮긴 사용 기록은 건드리지 않는다. 정책의
옛 형식 원본은 API 가 기본에서 숨긴다(D-542). 한 번뿐인 알림 유형 `ai_policy_migrated` 는 알림 설정의 유형 목록에서 빠진다(코드).

단계마다 바꾼 수를 로그로 남긴다(0040 · 0041 방식). 랩 실측(P0, `INVENTORY/13_UX_AI_MAIL_BASELINE.md`): 죽은 시드 0행 ·
`ai.call` 40행 · 옛 실행기 대화 id 를 가진 대화 63건.

## 되돌리기

열을 nullable 로 되살린다. 지운 행(죽은 시드 · `ai.call` 사건)과 열의 값은 되살릴 수 없다 - 업그레이드 스냅숏(D-524)이 복구
길이다. 보관한 초안은 보관 그대로 둔다(0040 과 같은 처리 - 되살리면 어느 것을 쓸지 사람이 정해야 한다).
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "0046_ai_legacy_cleanup"
down_revision = "0045_chatgpt_paste_login"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

SLOTLESS_NOTE = "사용처가 없는 초안이라 보관했습니다."
SEED_PREFIX = "당신은 ClovirONE%"


def upgrade() -> None:
    bind = op.get_bind()
    archived = bind.execute(sa.text(
        "UPDATE prompts SET status = 'archived', "
        "purpose = CASE WHEN purpose IS NULL OR purpose = '' THEN :note ELSE purpose || ' ' || :note END "
        "WHERE status = 'draft' AND (slot IS NULL OR slot = '')"
    ), {"note": SLOTLESS_NOTE}).rowcount
    logger.info("0046: 사용처가 없는 초안 %s건을 보관했다", archived)

    deleted = bind.execute(sa.text(
        "DELETE FROM prompts p WHERE p.status = 'archived' AND (p.slot IS NULL OR p.slot = '') "
        "AND p.created_by IS NULL AND p.content LIKE :seed "
        "AND NOT EXISTS (SELECT 1 FROM ai_usage_records r WHERE r.prompt_id = p.id)"
    ), {"seed": SEED_PREFIX}).rowcount
    logger.info("0046: 참조도 만든 사람도 없는 옛 시드 프롬프트 %s건을 지웠다", deleted)

    events = bind.execute(sa.text("DELETE FROM usage_events WHERE event = 'ai.call'")).rowcount
    logger.info("0046: 옮긴 뒤 남은 ai.call 사용 사건 %s건을 지웠다", events)

    carried = bind.execute(sa.text(
        "SELECT count(*) FROM conversations WHERE backend_conversation_id IS NOT NULL"
    )).scalar_one()
    op.drop_column("conversations", "backend_conversation_id")
    logger.info("0046: 옛 실행기 대화 id 열을 지웠다(값이 있던 대화 %s건)", carried)


def downgrade() -> None:
    op.add_column("conversations", sa.Column("backend_conversation_id", sa.String(128), nullable=True))
