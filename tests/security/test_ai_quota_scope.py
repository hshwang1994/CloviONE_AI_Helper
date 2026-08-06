"""AI 쿼터 **쓰기**도 범위를 지킨다 (3순위 IDOR).

읽기(`GET /usage`)는 이미 `get_scoped_user_or_404` 를 지나는데 **쓰기는 `user_id` 를 그대로
받았다.** 목록에서 가려 놓은 사람을 id 하나로 뚫는 전형적인 IDOR 이고, 결과가 특히 나쁘다:

* 남의 팀 사람의 상한을 **0 으로 만들면 그 사람의 AI 가 멈춘다** — 당사자는 429 만 보고
  이유를 모른다(N2 가 지적한 대로 쿼터 소진 알림도 없다).
* 반대로 크게 올리면 **조직의 AI 비용**을 태운다.

그리고 **전역 쿼터**는 포탈 전체에 걸린다. 부서 관리자가 그걸 0 으로 만들면 **전 사용자의
AI 가 멈춘다** — 범위를 좁혀 놓고 이 문을 열어 두면 좁힌 의미가 없다. 여기서만 404 가 아니라
**403** 인 이유는, 그 행의 존재는 목록에서 이미 보이기 때문이다(자기 사람들에게도 걸리는
상한이라 보여야 한다). 문제는 존재가 아니라 권한이다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.security


@pytest.fixture()
def world(db, make_user):
    """부서 둘 + 각 팀 사람 + 우리 팀만 관리하는 관리자."""
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.commit()

    mate = make_user("q-mate@goodmit.co.kr", role="user", display_name="동료")
    victim = make_user("q-victim@goodmit.co.kr", role="user", display_name="남")
    boss = make_user("q-boss@goodmit.co.kr", role="admin", display_name="팀관리자")
    mate.department_id = mine.id
    victim.department_id = theirs.id
    boss.department_id = mine.id
    boss.admin_scope = "dept"
    boss.scope_dept_id = mine.id
    db.commit()
    return {"mate": mate.id, "victim": victim.id}


def _hdr(login_as):
    return {"X-CSRF-Token": login_as("admin", email="q-boss@goodmit.co.kr")}


def test_a_scoped_admin_cannot_throttle_another_teams_person(client, login_as, world):
    hdr = _hdr(login_as)
    r = client.post(
        "/api/admin/ai-quotas",
        json={"scope_type": "user", "user_id": world["victim"], "period": "day", "max_calls": 0},
        headers=hdr,
    )
    assert r.status_code == 404, f"남의 팀 사람의 AI 상한을 걸 수 있다: {r.status_code} {r.text}"


def test_a_scoped_admin_can_still_manage_their_own_team(client, login_as, world):
    """오탐 방지 — 자기 팀 사람 쿼터까지 못 걸면 그건 기능 고장이다."""
    hdr = _hdr(login_as)
    r = client.post(
        "/api/admin/ai-quotas",
        json={"scope_type": "user", "user_id": world["mate"], "period": "day", "max_calls": 50},
        headers=hdr,
    )
    assert r.status_code == 201, f"자기 팀 사람에게 쿼터를 걸 수 없다: {r.status_code} {r.text}"


def test_a_scoped_admin_cannot_stop_the_whole_portal(client, login_as, world):
    """전역 쿼터 0 = **전 사용자의 AI 정지**. 부서 관리자의 권한이 아니다."""
    hdr = _hdr(login_as)
    r = client.post(
        "/api/admin/ai-quotas",
        json={"scope_type": "global", "period": "day", "max_calls": 0},
        headers=hdr,
    )
    assert r.status_code == 403, f"부서 관리자가 전역 쿼터를 만들었다: {r.status_code} {r.text}"


def test_an_existing_row_cannot_be_edited_across_scopes(client, login_as, db, world):
    """목록만 가려서는 소용없다 — 수정·삭제는 **행 id** 를 직접 받는다."""
    from datetime import datetime

    from app.quotas.models import AiQuota

    row = AiQuota(
        scope_type="user", user_id=world["victim"], period="day", max_calls=100,
        created_at=datetime(2026, 8, 1), updated_at=datetime(2026, 8, 1),
    )
    db.add(row)
    db.commit()
    row_id = row.id

    hdr = _hdr(login_as)
    r = client.patch(f"/api/admin/ai-quotas/{row_id}", json={"max_calls": 0}, headers=hdr)
    assert r.status_code == 404, f"남의 팀 쿼터가 수정됐다: {r.status_code} {r.text}"

    r = client.delete(f"/api/admin/ai-quotas/{row_id}", headers=hdr)
    assert r.status_code == 404, f"남의 팀 쿼터가 삭제됐다: {r.status_code} {r.text}"

    db.expire_all()
    assert db.get(AiQuota, row_id) is not None, "남의 팀 쿼터가 실제로 사라졌다"


def test_the_list_hides_other_teams_people_but_keeps_the_global_row(
    client, login_as, db, world
):
    """사용자 쿼터에는 **누가 얼마나 쓰는지**가 이름과 함께 실린다.

    전역 행은 남긴다 — 그 상한은 이 관리자의 사람들에게도 걸리므로 가리면 화면이 거짓말한다.
    """
    from datetime import datetime

    from app.quotas.models import GLOBAL_USER_ID, AiQuota

    db.add_all([
        AiQuota(scope_type="user", user_id=world["victim"], period="day", max_calls=7,
                created_at=datetime(2026, 8, 1), updated_at=datetime(2026, 8, 1)),
        AiQuota(scope_type="user", user_id=world["mate"], period="day", max_calls=9,
                created_at=datetime(2026, 8, 1), updated_at=datetime(2026, 8, 1)),
        AiQuota(scope_type="global", user_id=GLOBAL_USER_ID, period="day", max_calls=999,
                created_at=datetime(2026, 8, 1), updated_at=datetime(2026, 8, 1)),
    ])
    db.commit()

    _hdr(login_as)
    items = client.get("/api/admin/ai-quotas").json()["items"]
    seen = {i.get("user_id") for i in items}

    assert world["mate"] in seen, "자기 팀 사람의 쿼터가 안 보인다"
    assert world["victim"] not in seen, "남의 팀 사람의 AI 사용량이 이름과 함께 보인다"
    assert any(i["scope_type"] == "global" for i in items), (
        "전역 쿼터가 사라졌다 — 내 사람들에게도 걸리는 상한인데 화면이 그걸 숨긴다"
    )
