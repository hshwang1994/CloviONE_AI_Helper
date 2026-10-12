"""0049 — 축하 효과 스위치 (기능 개선 회차 P5, D-563).

## 무엇을 더하는가

`user_preferences.celebration_enabled` — 이 사람이 축포(게임 당첨자 발표 · 티켓 완료)를 끌 수 있는 스위치. 기본 켬.
OS 의 동작 줄이기 신호는 제품 결정(2026-09-03, `ui/motion.js`)대로 보지 않으므로, 끄는 자리는 이 칸 하나다.
행이 없는 사람은 켬이다(백필하지 않는다 — `UserPreference` 의 규칙).

## 되돌리기

칸을 지운다. 꺼 둔 사람의 선택을 잃는다(다시 켜진다).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0049_celebration_pref"
down_revision = "0048_mail_relay_tracking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_preferences",
        sa.Column("celebration_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_column("user_preferences", "celebration_enabled")
