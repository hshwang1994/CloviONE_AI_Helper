"""전역 AI 상한의 '현재 사용' 표시가 실제 판정과 같은 축을 봐야 한다 (UB-02).

`enforce()`는 전역 상한도 **사용자별**로 판정한다(`quotas/service.py::enforce` — 항상
`used(user_id=...)`를 쓴다, 전사 합계를 세는 잠금이 없어서다). 그런데 목록 API는 전역
행의 '현재 사용'에 `used_all`(전 사용자 합계)을 넣었다 — 상한 100에 50명이 3회씩 쓰면
"150/100 — 상한 도달"을 보여주는데, 실제로는 아무도 안 막힌다(각자 3회뿐이라 개인
상한 판정을 아무도 못 넘는다).
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.observability.models import UsageEvent
from app.quotas.models import AiQuota
from app.quotas.service import EVENT_AI_CALL

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 10, 3, 0, 0)  # KST 2026-08-10 정오


def _h(csrf):
    return {"X-CSRF-Token": csrf}


def _events(db, *, user_id, count, when=NOW):
    for _ in range(count):
        db.add(UsageEvent(user_id=user_id, event=EVENT_AI_CALL, created_at=when))


def test_global_row_used_is_the_busiest_users_count_not_the_sum(
    client, login_as, make_user, db
):
    csrf = login_as("system_admin")
    u1 = make_user("quota-busy@goodmit.co.kr", role="user")
    u2 = make_user("quota-quiet1@goodmit.co.kr", role="user")
    u3 = make_user("quota-quiet2@goodmit.co.kr", role="user")
    db.add(AiQuota(
        scope_type="global", user_id="", period="day", max_calls=100,
        created_at=NOW, updated_at=NOW,
    ))
    # 세 사람 합쳐 12회지만, 어느 한 명도 5회를 넘지 않는다 — 개인별 판정으로는
    # 아무도 상한(100)에 조금도 가깝지 않다.
    _events(db, user_id=u1.id, count=5)
    _events(db, user_id=u2.id, count=4)
    _events(db, user_id=u3.id, count=3)
    db.commit()

    body = client.get("/api/admin/ai-quotas", headers=_h(csrf)).json()
    row = next(i for i in body["items"] if i["scope_type"] == "global" and i["period"] == "day")
    assert row["used"] == 5, f"합계(12)가 아니라 최다 사용자 값(5)이어야 한다: {row['used']}"


def test_global_row_used_reaches_the_limit_when_one_user_actually_would_be_blocked(
    client, login_as, make_user, db
):
    """반대 방향도 맞아야 한다 — 한 명이라도 상한에 닿으면 화면이 그걸 보여줘야 한다."""
    csrf = login_as("system_admin")
    heavy = make_user("quota-heavy@goodmit.co.kr", role="user")
    db.add(AiQuota(
        scope_type="global", user_id="", period="day", max_calls=3,
        created_at=NOW, updated_at=NOW,
    ))
    _events(db, user_id=heavy.id, count=3)
    db.commit()

    body = client.get("/api/admin/ai-quotas", headers=_h(csrf)).json()
    row = next(i for i in body["items"] if i["scope_type"] == "global" and i["period"] == "day")
    assert row["used"] == 3 == row["max_calls"], (
        f"실제로 막히는 사용자가 있는데 화면이 상한 도달을 안 보여준다: {row}"
    )


def test_per_user_row_used_is_unaffected(client, login_as, make_user, db):
    """회귀 없음 — 사용자 전용 행은 예전처럼 그 사람의 개인 합계 그대로다."""
    csrf = login_as("system_admin")
    target = make_user("quota-solo@goodmit.co.kr", role="user")
    other = make_user("quota-other@goodmit.co.kr", role="user")
    db.add(AiQuota(
        scope_type="user", user_id=target.id, period="day", max_calls=10,
        created_at=NOW, updated_at=NOW,
    ))
    _events(db, user_id=target.id, count=4)
    _events(db, user_id=other.id, count=9)  # 남의 사용량이 섞이면 안 된다
    db.commit()

    body = client.get("/api/admin/ai-quotas", headers=_h(csrf)).json()
    row = next(i for i in body["items"] if i["scope_type"] == "user" and i["user_id"] == target.id)
    assert row["used"] == 4, f"사용자 전용 행에 남의 사용량이 섞였다: {row}"
