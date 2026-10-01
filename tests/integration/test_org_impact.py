"""조직 · 부서 영향 확인 (O1 · D-533).

조직 관리 화면은 「삭제」 · 「비활성화」를 누를 때 `/impact` 에 묻는다. 여기서 지키는 성질:

* 진행 · 예정 회차는 부서 삭제를 **막는다** — `sprints.department_id` 는 `SET NULL` 이라, 막지 않으면 그 팀의 열린 회차가
  조용히 「팀 미정」이 되어 팀 사람들 화면에서 사라진다.
* 닫힌 회차는 **떼어 낸다** — 회차의 팀은 바꿀 수 없어서 닫힌 회차까지 막으면 지울 수 없는 부서가 생긴다. 떼어 낼 때 이름이
  조직 안 팀 미정 회차와 겹치면(`uq_sprints_name`) 옛 부서 이름을 붙인다.
* 판정과 실행이 같다 — `/impact` 가 「지울 수 없다」고 하면 DELETE 는 409 이고 같은 문장이다.
* 비활성화 영향은 지워지지 않고 남는 것들의 수다(보관 계정 · 보관 프로젝트는 세지 않는다).
* 조직 정지 영향은 **실제로 로그아웃될 사람**이다 — 보관 · 비활성 계정과 시스템 관리자는 빠진다.
* 범위 밖 대상의 `/impact` 는 없는 대상과 같은 404 다(면제 없는 권한 음성 시험).
"""
from datetime import date, datetime, timedelta

import pytest

pytestmark = pytest.mark.integration

TODAY = date(2026, 10, 1)


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


@pytest.fixture()
def admin_csrf(login_as):
    return login_as("admin")


def _mk_dept(client, csrf, name, parent_id=None):
    r = client.post("/api/admin/departments", json={"name": name, "parent_id": parent_id}, headers=_headers(csrf))
    assert r.status_code == 201, r.text
    return r.json()["department"]["id"]


def _sprint(db, name, dept_id, state, *, days=0):
    from app.org.constants import DEFAULT_ORG_ID
    from app.work.models import Sprint

    row = Sprint(
        name=name, department_id=dept_id, org_id=DEFAULT_ORG_ID,
        starts_on=TODAY + timedelta(days=days), ends_on=TODAY + timedelta(days=days + 7), state=state,
    )
    db.add(row)
    db.commit()
    return row.id


def _impact(client, dept_id):
    r = client.get(f"/api/admin/departments/{dept_id}/impact")
    assert r.status_code == 200, r.text
    return r.json()


# ── 회차 ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("state", ["planned", "active"])
def test_an_open_sprint_blocks_the_delete(client, admin_csrf, db, state):
    dept_id = _mk_dept(client, admin_csrf, "회차팀")
    _sprint(db, "10-1", dept_id, state)

    verdict = _impact(client, dept_id)["delete"]
    assert verdict["deletable"] is False
    blockers = {b["kind"]: b for b in verdict["blockers"]}
    assert blockers["open_sprints"]["count"] == 1
    assert blockers["open_sprints"]["unit"] == "개"
    assert blockers["open_sprints"]["label"] == "진행 중이거나 예정된 회차"

    r = client.delete(f"/api/admin/departments/{dept_id}", headers=_headers(admin_csrf))
    assert r.status_code == 409, f"열린 회차가 있는 부서를 지웠다: {r.text}"
    # 판정과 실행이 같은 문장을 쓴다 — 창이 말한 것과 눌러서 받는 거절이 다르면 그 어긋남이 결함이다.
    assert r.json()["error"]["message"] == verdict["reason"]
    assert "진행 중이거나 예정된 회차 1개가 연결되어 있어" in verdict["reason"], verdict["reason"]


def test_closed_sprints_are_detached_and_renamed_only_on_collision(client, admin_csrf, db):
    from app.work.models import Sprint

    dept_id = _mk_dept(client, admin_csrf, "닫힌회차팀")
    clash = _sprint(db, "9-2", dept_id, "closed", days=-30)
    plain = _sprint(db, "9-3", dept_id, "closed", days=-20)
    # 조직 안에 이미 팀 미정 「9-2」가 있다 — 떼어 낸 회차가 그 이름을 그대로 쓰면 유일 색인에 걸린다.
    _sprint(db, "9-2", None, "closed", days=-40)

    verdict = _impact(client, dept_id)["delete"]
    assert verdict["deletable"] is True, verdict
    assert [(d["kind"], d["count"], d["unit"]) for d in verdict["detachables"]] == [("closed_sprints", 2, "개")]

    r = client.delete(f"/api/admin/departments/{dept_id}", headers=_headers(admin_csrf))
    assert r.status_code == 200, r.text
    assert r.json()["detached"]["closed_sprints"] == 2
    assert "닫힌 회차 2개는 부서 연결만 끊고 그대로 두었습니다." in r.json()["message"]

    db.expire_all()
    renamed = db.get(Sprint, clash)
    kept = db.get(Sprint, plain)
    assert renamed.department_id is None and kept.department_id is None
    assert renamed.name == "9-2 (닫힌회차팀)", renamed.name
    assert kept.name == "9-3", "겹치지 않는 이름까지 바꿨다"


def test_closed_sprint_rename_finds_a_free_name_when_the_suffixed_name_is_taken(client, admin_csrf, db):
    from app.work.models import Sprint

    dept_id = _mk_dept(client, admin_csrf, "겹침팀")
    target = _sprint(db, "8-1", dept_id, "closed", days=-30)
    _sprint(db, "8-1", None, "closed", days=-60)
    _sprint(db, "8-1 (겹침팀)", None, "closed", days=-50)

    assert client.delete(f"/api/admin/departments/{dept_id}", headers=_headers(admin_csrf)).status_code == 200
    db.expire_all()
    assert db.get(Sprint, target).name == "8-1 (겹침팀 2)"


def test_sprints_of_other_departments_are_untouched(client, admin_csrf, db):
    from app.work.models import Sprint

    gone = _mk_dept(client, admin_csrf, "지울팀")
    other = _mk_dept(client, admin_csrf, "남을팀")
    keep_open = _sprint(db, "7-1", other, "active")
    keep_closed = _sprint(db, "7-0", other, "closed", days=-30)

    assert client.delete(f"/api/admin/departments/{gone}", headers=_headers(admin_csrf)).status_code == 200
    db.expire_all()
    assert db.get(Sprint, keep_open).department_id == other
    assert db.get(Sprint, keep_closed).department_id == other


# ── 비활성화 영향 ───────────────────────────────────────────────────────────

def test_deactivate_impact_counts_what_stays(client, admin_csrf, db, make_project, make_user):
    dept_id = _mk_dept(client, admin_csrf, "비활성화팀")
    _mk_dept(client, admin_csrf, "아래팀", parent_id=dept_id)
    for i, archived in enumerate((False, False, True)):
        u = make_user(f"stay{i}@goodmit.co.kr", role="user")
        u.department_id = dept_id
        if archived:
            u.archived_at = datetime(2026, 9, 1)
    db.commit()
    make_project(name="남는 프로젝트", dept=dept_id)
    archived_project = make_project(name="보관 프로젝트", dept=dept_id)
    archived_project.archived_at = datetime(2026, 9, 1)
    db.commit()
    _sprint(db, "6-1", dept_id, "planned", days=3)

    impact = _impact(client, dept_id)["deactivate"]
    assert impact == {
        "members": 2, "child_departments": 1, "projects": 1, "scoped_admins": 0, "open_sprints": 1,
    }, "보관된 사람 · 프로젝트까지 「그대로 남는 것」으로 셌다"


def test_impact_and_delete_agree_for_every_blocker(client, admin_csrf, db, make_project, make_user):
    """판정 함수 하나 — `/impact` 의 갈래와 409 의 `details` 가 같은 수를 말한다."""
    dept_id = _mk_dept(client, admin_csrf, "합의팀")
    _mk_dept(client, admin_csrf, "합의하위팀", parent_id=dept_id)
    u = make_user("agree@goodmit.co.kr", role="user")
    u.department_id = dept_id
    db.commit()
    make_project(name="합의 프로젝트", dept=dept_id)
    _sprint(db, "5-1", dept_id, "active")

    verdict = _impact(client, dept_id)["delete"]
    r = client.delete(f"/api/admin/departments/{dept_id}", headers=_headers(admin_csrf))
    assert r.status_code == 409
    details = r.json()["error"]["details"]
    for b in verdict["blockers"]:
        assert details[b["kind"]] == b["count"], (b, details)
    assert {b["kind"] for b in verdict["blockers"]} == {"users", "child_departments", "projects", "open_sprints"}
    units = {b["kind"]: b["unit"] for b in verdict["blockers"]}
    assert units == {"users": "명", "child_departments": "개", "projects": "개", "open_sprints": "개"}


def test_the_department_detail_no_longer_carries_the_verdict(client, admin_csrf):
    """고를 때마다 COUNT 열두어 번을 돌던 상세 응답의 판정은 걷었다 — 화면은 누를 때 `/impact` 에 묻는다."""
    dept_id = _mk_dept(client, admin_csrf, "가벼운팀")
    body = client.get(f"/api/admin/departments/{dept_id}").json()["department"]
    assert "delete_precheck" not in body


# ── 조직 정지 영향 ──────────────────────────────────────────────────────────

def test_suspend_impact_counts_only_people_who_will_be_signed_out(client, login_as, db, make_user, two_orgs):
    from app.org.models import Organization

    login_as("system_admin")
    org_b = two_orgs.org_b_id
    specs = [
        ("live1@goodmit.co.kr", "user", True, False),
        ("live2@goodmit.co.kr", "admin", True, False),
        ("off@goodmit.co.kr", "user", False, False),
        ("gone@goodmit.co.kr", "user", True, True),
        ("root@goodmit.co.kr", "system_admin", True, False),
    ]
    for email, role, active, archived in specs:
        u = make_user(email, role=role, active=active)
        u.org_id = org_b
        if archived:
            u.archived_at = datetime(2026, 9, 1)
    db.commit()

    r = client.get(f"/api/admin/organizations/{org_b}/impact")
    assert r.status_code == 200, r.text
    # two_orgs 의 B사람(활성 · 보통 사용자) 한 명이 이미 그 조직에 있다.
    assert r.json()["suspend"] == {
        "signed_out_users": 3, "exempt_system_admins": 1, "inactive_users": 1, "archived_users": 1,
    }
    # 목록의 인원도 지금 쓸 수 있는 계정만 센다 — 예전 수는 보관 · 비활성까지 세어 정지 창이 그 수를 「로그아웃될 사람」으로 말했다.
    row = next(o for o in client.get("/api/admin/organizations").json()["items"] if o["id"] == org_b)
    assert row["user_count"] == 4
    assert db.get(Organization, org_b) is not None


# ── 권한 음성(면제 없음) ────────────────────────────────────────────────────

def test_impact_of_an_out_of_scope_department_is_a_404(client, login_as, db, make_user):
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    mine = Department(name="내부서", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의부서", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.flush()
    boss = make_user("impact-boss@goodmit.co.kr", role="admin")
    boss.department_id = mine.id
    boss.admin_scope = "dept"
    boss.scope_dept_id = mine.id
    db.commit()

    login_as("admin", email="impact-boss@goodmit.co.kr")
    assert client.get(f"/api/admin/departments/{mine.id}/impact").status_code == 200
    out = client.get(f"/api/admin/departments/{theirs.id}/impact")
    ghost = client.get("/api/admin/departments/00000000-0000-0000-0000-000000000000/impact")
    assert out.status_code == 404, "범위 밖 부서의 영향이 보인다"
    assert ghost.status_code == 404
    # 범위 밖과 없는 것을 가를 수 없어야 한다 — 존재를 흘리지 않는다.
    assert out.json()["error"]["message"] == ghost.json()["error"]["message"]


def test_impact_of_another_organization_is_a_404(client, login_as, db, make_user, two_orgs):
    boss = make_user("org-a-boss@goodmit.co.kr", role="admin")
    boss.org_id = two_orgs.org_a_id
    boss.admin_scope = "org"
    db.commit()

    login_as("admin", email="org-a-boss@goodmit.co.kr")
    assert client.get(f"/api/admin/organizations/{two_orgs.org_b_id}/impact").status_code == 404
    assert client.get(f"/api/admin/departments/{two_orgs.dept_b.id}/impact").status_code == 404


def test_a_plain_user_cannot_read_impact(client, login_as, two_orgs):
    login_as("user")
    assert client.get(f"/api/admin/organizations/{two_orgs.org_a_id}/impact").status_code in (401, 403, 404)
    assert client.get(f"/api/admin/departments/{two_orgs.dept_a.id}/impact").status_code in (401, 403, 404)
