"""채팅방을 부서에 묶는 열 — '내 팀' 기본 방 (Q6).

지금 기본으로 만들어져 있는 방은 **전체 채팅** 하나다(`is_global`). 그런데 사람들이
매일 쓰는 단위는 회사 전체가 아니라 **자기 팀**이다(사용자 지적 Q6:
"홈 및 채팅방에 default 로 만들어진 방은 기본적으로 내 팀임").

그래서 부서마다 방 하나를 둔다. `chat_rooms.department_id` 가 그 연결이고, 값이 있으면
"이 부서의 팀 방" 이다(그룹 방과 같은 종류라 메시지·멤버·읽음 커서 로직을 그대로 쓴다 —
방 종류를 새로 만들면 그 모든 경로에 분기가 하나씩 는다).

**행은 여기서 만들지 않는다.** 부서가 있는 사용자가 방 목록을 열 때 서비스가 게으르게
만든다(`service.ensure_team_room`). 마이그레이션이 만들면 그 뒤에 생기는 부서에는
방이 없고, 부서가 생길 때마다 마이그레이션을 하나씩 더 써야 한다.

유니크 제약을 걸지 않는 이유: 부서가 지워졌다 다시 생기거나 방이 soft-delete 된 경우까지
DB 제약으로 다루면 복구 경로가 막힌다. 대신 `ensure_team_room` 이 SAVEPOINT 로 경합을
흡수한다(1:1 방의 `dm_key` 와 같은 관용).

Revision ID: 0039
Revises: 0038
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("chat_rooms") as batch:
        batch.add_column(sa.Column("department_id", sa.String(length=36), nullable=True))
    # 방 목록을 열 때마다 "내 부서의 팀 방" 을 찾는다 — 그 조회가 인덱스를 타야 한다.
    op.create_index("ix_chat_rooms_department_id", "chat_rooms", ["department_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_rooms_department_id", table_name="chat_rooms")
    with op.batch_alter_table("chat_rooms") as batch:
        batch.drop_column("department_id")
