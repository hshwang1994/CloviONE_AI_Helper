"""회의록 — 정한 것과 그래서 할 일이 화면을 닫아도 남는다.

Revision ID: 0020_sprint_decisions
Revises: 0019_avatar_default_and_crop
Create Date: 2026-08-27

## 무엇이 문제였나

스프린트 회의 화면은 **읽기 전용 집계**였다. 숫자와 막대는 잘 보였는데, 정작 회의에서
정한 것은 어디에도 안 남았다 — 다음 주에 「지난주에 뭐 하기로 했지」를 물으면 아무도
답할 수 없었고, 그래서 같은 이야기가 매주 다시 나왔다.

## 왜 티켓으로 대신하지 않는가

「Action 은 티켓으로 만들면 되지 않나」가 첫 안이었다. 실제 회의에서 나오는 할 일의
절반은 티켓이 될 만한 크기가 아니다(「A 팀에 물어본다」, 「다음 회차 범위를 다시
본다」). 티켓으로 만들도록 강요하면 사람들은 **아무것도 안 적는다** — 적는 비용이
말하는 비용보다 크면 기록은 사라진다.

대신 `ticket_id` 를 선택으로 둔다. 티켓이 될 만한 것은 이어 두고, 아닌 것은 문장으로
남는다.

## 왜 표 하나인가

결정(decision)과 할 일(action)을 따로 두고 싶어진다. 그런데 회의록에서 그 둘은
**붙어 있다** — 「이번 회차는 결제 모듈을 뺀다(결정), 그래서 예상 WD 를 다시 잰다(할 일)」.
표를 가르면 화면이 둘을 시간순으로 합칠 방법이 없고, 합치는 코드를 화면마다 다시 쓰게
된다. `kind` 한 칸이면 된다.

## 비우는 칸이 셋이다

`ticket_id` · `assignee_user_id` · `due_date` 전부 nullable 이다. 회의 중에 다 안
정해지기 때문이다. 필수로 만들면 「담당자 미정」인 결정을 적을 수 없고, 그러면 그
결정은 아예 안 적힌다.

외래키의 `ON DELETE` 가 둘 다 `SET NULL` 인 것도 같은 생각이다. 걸어 둔 티켓이나
사람이 사라졌다고 회의록 줄이 함께 사라지면 기록에 구멍이 난다 — 사라지는 것은
연결이지 문장이 아니다. 회차 자체가 지워지면 그때는 `CASCADE` 다: 없는 회의의 회의록은
아무 뜻이 없다.

## 기존 행

없다. 새 표다. 기존 데이터를 읽지도 고치지도 않는다.

## 되감기

되감을 수 있다. 표 하나를 지운다 — 다른 표는 안 건드린다.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0020_sprint_decisions'
down_revision = '0019_avatar_default_and_crop'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sprint_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "sprint_id", sa.String(36),
            sa.ForeignKey("sprints.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False, server_default="decision"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "ticket_id", sa.String(36),
            sa.ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "assignee_user_id", sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("done", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "author_user_id", sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('decision', 'action')", name="ck_sprint_decisions_kind"
        ),
    )
    # 회의록은 적은 순서대로 읽는다. 회차별 시간순이 **유일한** 접근 패턴이라 이 하나면 된다.
    op.create_index("ix_sprint_decisions_feed", "sprint_decisions", ["sprint_id", "created_at"])
    op.create_index("ix_sprint_decisions_sprint_id", "sprint_decisions", ["sprint_id"])
    op.create_index("ix_sprint_decisions_ticket_id", "sprint_decisions", ["ticket_id"])
    op.create_index(
        "ix_sprint_decisions_assignee_user_id", "sprint_decisions", ["assignee_user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_sprint_decisions_assignee_user_id", table_name="sprint_decisions")
    op.drop_index("ix_sprint_decisions_ticket_id", table_name="sprint_decisions")
    op.drop_index("ix_sprint_decisions_sprint_id", table_name="sprint_decisions")
    op.drop_index("ix_sprint_decisions_feed", table_name="sprint_decisions")
    op.drop_table("sprint_decisions")
