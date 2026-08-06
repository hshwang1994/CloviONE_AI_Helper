"""뜨거운 질의 인덱스 (M1) — 모델과 마이그레이션이 같은 것을 말한다.

인덱스는 **없어도 화면이 멀쩡하다.** 느려질 뿐이고 그 느려짐은 데이터가 쌓인 뒤에야
나타난다 — 그래서 빠뜨려도 아무도 안 알아챈다. 검사로 고정한다.

특히 `notifications` 는 **복합**이라야 뜻이 있다. `user_id` 단일은 이미 있는데 안읽음
개수는 `user_id = ? AND read_at IS NULL` 이고 **모든 화면에서 60초마다** 폴링된다.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.regression

EXPECTED = {
    "notifications": ("ix_notifications_user_unread", ["user_id", "read_at"]),
    "board_posts": ("ix_board_posts_created_at", ["created_at"]),
    "conversations": ("ix_conversations_updated_at", ["updated_at"]),
    "schedule_runs": ("ix_schedule_runs_created_at", ["created_at"]),
    "audit_logs": ("ix_audit_logs_object_id", ["object_id"]),
}


@pytest.mark.parametrize("table", sorted(EXPECTED))
def test_the_index_exists_after_migration(db, table):
    name, cols = EXPECTED[table]
    insp = sa.inspect(db.get_bind())
    found = {i["name"]: list(i["column_names"]) for i in insp.get_indexes(table)}
    assert name in found, f"{table} 에 {name} 이 없다 (있는 것: {sorted(found)})"
    assert found[name] == cols, f"{name} 의 열이 다르다: {found[name]} != {cols}"
