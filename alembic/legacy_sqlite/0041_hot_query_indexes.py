"""커지는 표의 뜨거운 질의에 인덱스를 붙인다 (M1).

전부 **실측으로 없는 것만** 넣는다(있는 것을 또 만들지 않는다):

| 표 | 열 | 어느 질의가 쓰는가 |
|---|---|---|
| `notifications` | `(user_id, read_at)` | 안읽음 개수 — **모든 화면에서 60초마다** 폴링된다 |
| `board_posts` | `created_at` | 게시판 기본 정렬(최신순) |
| `conversations` | `updated_at` | AI 대화 목록 정렬(운영 63건, 계속 는다) |
| `schedule_runs` | `created_at` | 실행 이력 + 보존 정리의 cutoff 비교 |
| `audit_logs` | `object_id` | "이 사용자에게 일어난 모든 일" — 조사할 때 가장 먼저 치는 질의 |

`notifications` 는 **복합**이라야 뜻이 있다. `user_id` 단일 인덱스는 이미 있는데, 안읽음
개수는 `user_id = ? AND read_at IS NULL` 이라 그 사람의 전 알림을 훑은 뒤 걸러낸다 —
알림이 쌓일수록 폴링 한 번이 무거워진다.

인덱스는 쓰기를 조금 느리게 한다. 그래서 '있으면 좋은' 것이 아니라 **뜨거운 읽기 질의가
실제로 쓰는** 것만 넣었다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None

_INDEXES = [
    ("ix_notifications_user_unread", "notifications", ["user_id", "read_at"]),
    ("ix_board_posts_created_at", "board_posts", ["created_at"]),
    ("ix_conversations_updated_at", "conversations", ["updated_at"]),
    ("ix_schedule_runs_created_at", "schedule_runs", ["created_at"]),
    ("ix_audit_logs_object_id", "audit_logs", ["object_id"]),
]


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    tables = set(insp.get_table_names())
    for name, table, cols in _INDEXES:
        if table not in tables:
            continue
        have = {i["name"] for i in insp.get_indexes(table)}
        if name not in have:
            op.create_index(name, table, cols)


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    tables = set(insp.get_table_names())
    for name, table, _cols in _INDEXES:
        if table not in tables:
            continue
        if name in {i["name"] for i in insp.get_indexes(table)}:
            op.drop_index(name, table_name=table)
