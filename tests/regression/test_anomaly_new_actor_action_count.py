"""UA-27: `new_actor_action` 소견의 `count`가 실제 발생 건수가 아니라 **새로 쓴 동작
종류의 수**였다. 같은 새 동작을 여러 번 해도 화면의 "건수" 열(다른 소견 4종은 전부 실제
이벤트 개수를 쓴다)에는 종류 수(보통 1)만 떴다 — 실제보다 훨씬 조용해 보인다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.audit.anomalies import detect
from app.audit.models import AuditLog

pytestmark = pytest.mark.regression

NOW = datetime(2026, 7, 13, 3, 0, 0)  # UTC 03:00 = KST 12:00, off_hours 규칙과 안 겹침


@pytest.fixture()
def actor(db, make_user):
    return make_user("ua27-actor@goodmit.co.kr", role="admin", display_name="UA27")


def test_new_actor_action_count_reflects_events_not_distinct_action_types(db, actor):
    # 비교 구간(30일 전~검사 시작)을 비워 두면 "전부 처음"으로 판정돼 소음만 나므로,
    # 비교 구간에 무관한 sensitive 동작 한 건을 심어 비교 구간 자체는 비어 있지 않게 한다.
    db.add(AuditLog(
        user_id=actor.id, action="user.enable", object_type="user", object_id=actor.id,
        result="success", created_at=NOW - timedelta(days=2),
    ))
    # 검사 창(최근 24시간) 안에서 **같은** 새 sensitive 동작을 세 번 한다.
    for i in range(3):
        db.add(AuditLog(
            user_id=actor.id, action="feature_flag.toggle", object_type="feature_flag",
            object_id="x", result="success", created_at=NOW - timedelta(hours=1) + timedelta(minutes=i),
        ))
    db.commit()

    result = detect(db, now=NOW, actor_ids=None)
    fresh = [f for f in result["findings"] if f["kind"] == "new_actor_action" and f["actor_id"] == actor.id]
    assert fresh, f"new_actor_action 소견이 안 잡혔다: {result['findings']}"
    assert fresh[0]["count"] == 3, (
        f"같은 새 동작을 3번 했는데 count가 실제 건수를 안 세고 있다: {fresh[0]}"
    )
