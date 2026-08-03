"""온라인 점 — chat_room_members.last_seen 을 nullable 로 (PLAN Phase 3 §F)

Revision ID: 0029
Revises: 0026
Create Date: 2026-08-03

**왜 컬럼 하나의 nullable 을 바꾸려고 마이그레이션을 하나 쓰는가.**

`last_seen` 은 '이 방을 마지막으로 본 시각'인데, NOT NULL 이라 멤버 행을 만들 때 무언가를
넣어야 했고 그 값이 `joined_at`(= 그때의 now)이었다. 그래서 **방금 초대된 사람이 초대된 줄도
모르는 채로 2분 동안 '이 대화 보는 중'으로 켜져 있었다** — 온라인 점을 붙이는 순간 그 값이
화면에 나가는 사실이 되고, 없는 사람을 있다고 말하는 표시가 된다.

`joined_at` 과 비교해서 걸러 볼 수도 있지만(`last_seen > joined_at` 이면 본 적 있음) 그러면
'처음 한 번은 스로틀을 무시하고 써야 한다'는 예외가 생기고, 시계가 멈춘 환경에서는 그 예외가
**폴링마다 쓰기**로 변한다(이 앱에서 가장 뜨거운 경로다). NULL 은 그 모든 것을 없앤다:

  * `is_online(None, …)` → False — 본 적 없는 사람은 꺼진 점;
  * `should_touch(None, …)` → True — **첫 폴링에서 즉시** 한 번 쓰고, 그 뒤로는 30초 스로틀이
    정상 동작한다(app/core/presence.py 가 이미 이 규약으로 쓰여 있다).

기존 행은 건드리지 않는다 — 값이 이미 있고, 그 값은 실제로 마지막으로 본 시각이다.
시드·백필이 없으므로 타임스탬프 함정(CLAUDE.md §8, SQLite STRFTIME '%f')과 무관하다.

**downgrade**: NOT NULL 로 되돌리기 전에 NULL 을 `joined_at` 으로 채운다(그러지 않으면 제약을
붙일 수 없다). 파이썬에서 값을 만들지 않고 같은 행의 컬럼을 복사하는 UPDATE 라 시각 표현이
새로 생기지 않는다. 되돌린 뒤에는 초대 직후 2분 동안 '보는 중'으로 보이는 옛 동작으로 돌아간다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029"
# 머지 시점의 실제 head. 머리가 둘이면 `alembic upgrade head` 가
# "Multiple head revisions are present" 로 죽는다 — 배포 실패다.
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite 는 컬럼 제약을 직접 바꿀 수 없어 batch(테이블 재생성)로 간다.
    # 유니크(uq_chat_member)와 FK 는 반영(reflection)으로 그대로 옮겨진다.
    with op.batch_alter_table("chat_room_members") as batch:
        batch.alter_column("last_seen", existing_type=sa.DateTime(), nullable=True)


def downgrade() -> None:
    # NULL 이 하나라도 있으면 NOT NULL 을 붙일 수 없다 — 같은 행의 joined_at 으로 채운다.
    op.execute(
        "UPDATE chat_room_members SET last_seen = joined_at WHERE last_seen IS NULL"
    )
    with op.batch_alter_table("chat_room_members") as batch:
        batch.alter_column("last_seen", existing_type=sa.DateTime(), nullable=False)
