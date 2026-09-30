"""AI 사용 통계도 관리 범위를 지킨다 (계획 3.11, D-517).

호출 기록은 누가 언제 AI 를 얼마나 썼는지를 말한다. 부서 범위 관리자가 다른 부서 사람의 사용량을 보면 한도 목록이
가려 둔 것을 통계가 드러낸다. 그래서 통계와 호출 기록은 한도 목록과 같은 판정을 쓴다: 자기 범위 사람의 호출만 보고,
사람이 아닌 호출(관리자의 연결 확인)은 전역 관리자만 본다. 일반 사용자는 이 API 에 닿지 못한다.
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.security


@pytest.fixture()
def world(db, make_user, fake_clock):
    """부서 둘, 각 팀 사람, 우리 팀만 관리하는 관리자, 그리고 호출 기록."""
    from app.ai.models import AiUsageRecord
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.commit()

    mate = make_user("u-mate@goodmit.co.kr", role="user", display_name="동료")
    other = make_user("u-other@goodmit.co.kr", role="user", display_name="남")
    boss = make_user("u-boss@goodmit.co.kr", role="admin", display_name="팀관리자")
    mate.department_id = mine.id
    other.department_id = theirs.id
    boss.department_id = mine.id
    boss.admin_scope = "dept"
    boss.scope_dept_id = mine.id
    now = fake_clock.now()
    for user_id, action in ((mate.id, "chat.answer"), (mate.id, "chat.answer"), (other.id, "chat.answer"),
                            (None, "system.connection_test")):
        db.add(AiUsageRecord(id=str(uuid.uuid4()), created_at=now, actor_kind="user" if user_id else "system",
                             user_id=user_id, action_key=action, status="ok"))
    db.commit()
    return {"mate": mate.id, "other": other.id}


def test_a_scoped_admin_sees_only_their_own_people(client, login_as, world):
    login_as("admin", email="u-boss@goodmit.co.kr")
    stats = client.get("/api/admin/ai/usage/stats", params={"group_by": "user"}).json()
    assert [i["key"] for i in stats["items"]] == [world["mate"]], "다른 부서나 시스템의 호출이 보였다"
    assert stats["totals"]["calls"] == 2

    records = client.get("/api/admin/ai/usage/records").json()
    assert records["total"] == 2 and {i["user_id"] for i in records["items"]} == {world["mate"]}
    probe = client.get("/api/admin/ai/usage/records", params={"user_id": world["other"]}).json()
    assert probe["total"] == 0, "사람 id 를 알면 다른 부서 사람의 기록을 볼 수 있다"


def test_a_global_admin_sees_everyone_and_the_system(client, login_as, world):
    login_as("system_admin", email="u-root@goodmit.co.kr")
    stats = client.get("/api/admin/ai/usage/stats").json()
    assert stats["totals"]["calls"] == 4


@pytest.mark.parametrize("path", ["/api/admin/ai/usage/stats", "/api/admin/ai/usage/records",
                                  "/api/admin/ai/usage/catalog"])
def test_a_regular_user_cannot_read_usage(client, login_as, world, path):
    login_as("user", email="u-mate@goodmit.co.kr")
    assert client.get(path).status_code == 403
