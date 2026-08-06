"""프로젝트의 **목록, 상세, 수정, 삭제가 전부** 범위를 지킨다 (저장소 불변 규칙 1).

이 저장소는 같은 실수를 네 번 했다: 목록에는 범위를 걸고 같은 모듈의 단건, 쓰기에는 안
걸었다(`scripts/check_scope_gates.py` 가 그 목록을 들고 있다). 그래서 여기서는 네 경로를
따로따로 두드린다. 목록만 확인하는 테스트는 정확히 그 결함 상태를 통과시킨다.

프로젝트에서 새는 것이 조회로 끝나지 않는다:

* **상세**에는 남의 팀의 목표, 일정, 진행률, 건강도가 실린다. 조직도보다 민감하다.
* **수정**은 남의 팀 계획을 바꾼다. 특히 `dept_id` 를 바꾸면 그 프로젝트는 **내 범위에서
  사라져 되돌릴 수도 없다** - 읽기 유출보다 나쁘다.
* **삭제(보관)** 는 남의 팀 프로젝트를 목록에서 조용히 없앤다.

범위 밖은 **403 이 아니라 404** 다. 403 은 "그 id 는 존재한다"를 알려 주므로 id 를 찍어
보며 응답 코드를 세면 남의 부서 프로젝트를 통째로 열거할 수 있다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.security

BOSS_EMAIL = "prj-boss@goodmit.co.kr"


@pytest.fixture()
def world(db, make_user):
    """부서 둘 + 우리 팀만 관리하는 관리자 + 각 팀의 프로젝트 하나씩."""
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department
    from app.projects.models import Project

    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.commit()

    boss = make_user(BOSS_EMAIL, role="admin", display_name="팀관리자")
    boss.department_id = mine.id
    boss.admin_scope = "dept"
    boss.scope_dept_id = mine.id
    db.commit()

    projects = {
        "mine": Project(
            name="우리팀 프로젝트", dept_id=mine.id, org_id=DEFAULT_ORG_ID,
            goal="우리 팀 목표",
        ),
        "theirs": Project(
            name="남의팀 프로젝트", dept_id=theirs.id, org_id=DEFAULT_ORG_ID,
            goal="남의 팀 상반기 목표와 일정",
        ),
    }
    db.add_all(list(projects.values()))
    db.commit()
    return {
        "mine_dept": mine.id,
        "theirs_dept": theirs.id,
        "mine": projects["mine"].id,
        "theirs": projects["theirs"].id,
    }


def _hdr(login_as):
    return {"X-CSRF-Token": login_as("admin", email=BOSS_EMAIL)}


def _project(db, project_id):
    from app.projects.models import Project

    db.expire_all()
    return db.get(Project, project_id)


def test_the_list_does_not_leak_another_teams_project(client, login_as, world):
    _hdr(login_as)
    rows = client.get("/api/projects").json()["items"]
    ids = {row["id"] for row in rows}
    assert world["theirs"] not in ids, "목록에 남의 팀 프로젝트가 있다"
    assert world["mine"] in ids, "오탐 방지 - 자기 팀 프로젝트가 목록에 없다"


def test_the_detail_of_another_teams_project_is_404(client, login_as, world):
    """상세에는 남의 팀의 목표와 일정이 실린다."""
    r = client.get(f"/api/projects/{world['theirs']}", headers=_hdr(login_as))
    assert r.status_code == 404, f"남의 팀 프로젝트 상세가 열린다: {r.status_code} {r.text}"
    assert "남의 팀" not in r.text, "404 응답 본문에 내용이 새어 나갔다"


def test_updating_another_teams_project_is_404_and_changes_nothing(
    client, login_as, db, world
):
    """404 를 돌려주고도 값이 바뀌면 아무것도 막지 못한 것이다."""
    r = client.patch(
        f"/api/projects/{world['theirs']}",
        json={"name": "탈취됨"},
        headers=_hdr(login_as),
    )
    assert r.status_code == 404, f"남의 팀 프로젝트를 수정할 수 있다: {r.status_code} {r.text}"
    assert _project(db, world["theirs"]).name == "남의팀 프로젝트", (
        "404 를 돌려주고도 남의 팀 프로젝트가 실제로 바뀌었다"
    )


def test_deleting_another_teams_project_is_404_and_changes_nothing(
    client, login_as, db, world
):
    r = client.delete(f"/api/projects/{world['theirs']}", headers=_hdr(login_as))
    assert r.status_code == 404, f"남의 팀 프로젝트를 삭제할 수 있다: {r.status_code} {r.text}"
    assert _project(db, world["theirs"]).archived_at is None, (
        "404 를 돌려주고도 남의 팀 프로젝트가 실제로 보관됐다"
    )


def test_the_progress_of_another_teams_project_is_404(client, login_as, world):
    """진행률에도 남의 팀 작업 수와 공수가 실린다 - 계산 근거가 곧 표본 정보다."""
    r = client.get(f"/api/projects/{world['theirs']}/progress", headers=_hdr(login_as))
    assert r.status_code == 404, f"남의 팀 진행률이 열린다: {r.status_code} {r.text}"


def test_a_project_cannot_be_created_into_another_teams_department(
    client, login_as, db, world
):
    """쓰기가 범위 **밖으로 나가는 것**도 막는다. 읽기만 막으면 남의 팀에 심을 수 있다."""
    from app.projects.models import Project

    r = client.post(
        "/api/projects",
        json={"name": "심어 놓기", "dept_id": world["theirs_dept"]},
        headers=_hdr(login_as),
    )
    assert r.status_code == 404, f"남의 팀 부서로 프로젝트를 만들 수 있다: {r.status_code} {r.text}"

    db.expire_all()
    planted = db.query(Project).filter(Project.name == "심어 놓기").all()
    assert planted == [], "404 를 돌려주고도 행이 실제로 만들어졌다"


def test_my_own_project_cannot_be_moved_out_of_my_scope(client, login_as, db, world):
    """옮기는 순간 내 범위에서 사라져 **되돌릴 수도 없다** - 읽기 유출보다 나쁘다."""
    r = client.patch(
        f"/api/projects/{world['mine']}",
        json={"dept_id": world["theirs_dept"]},
        headers=_hdr(login_as),
    )
    assert r.status_code == 404, f"내 프로젝트를 남의 팀으로 옮길 수 있다: {r.status_code} {r.text}"
    assert _project(db, world["mine"]).dept_id == world["mine_dept"], (
        "404 를 돌려주고도 부서가 실제로 바뀌었다"
    )


def test_my_own_team_still_works(client, login_as, db, world):
    """오탐 방지 - 자기 범위가 막히면 그건 보안이 아니라 기능 고장이다."""
    hdr = _hdr(login_as)

    r = client.get(f"/api/projects/{world['mine']}", headers=hdr)
    assert r.status_code == 200, f"자기 팀 프로젝트 상세를 못 본다: {r.status_code} {r.text}"

    r = client.patch(
        f"/api/projects/{world['mine']}", json={"name": "이름 변경"}, headers=hdr
    )
    assert r.status_code == 200, f"자기 팀 프로젝트를 못 고친다: {r.status_code} {r.text}"
    assert _project(db, world["mine"]).name == "이름 변경"

    r = client.get(f"/api/projects/{world['mine']}/progress", headers=hdr)
    assert r.status_code == 200, f"자기 팀 진행률을 못 본다: {r.status_code} {r.text}"

    r = client.delete(f"/api/projects/{world['mine']}", headers=hdr)
    assert r.status_code == 200, f"자기 팀 프로젝트를 못 보관한다: {r.status_code} {r.text}"
    assert _project(db, world["mine"]).archived_at is not None


def test_a_new_project_lands_in_the_creators_department(client, login_as, db, world):
    """부서를 안 주면 만든 사람의 부서가 된다.

    비워 두면 `dept_id IS NULL` 이 되어 **만든 사람 본인도 목록에서 못 찾는다**. 증상이
    "권한 없음" 이 아니라 "목록이 비어 있음" 이라 원인을 찾기가 어렵다.
    """
    r = client.post("/api/projects", json={"name": "새 프로젝트"}, headers=_hdr(login_as))
    assert r.status_code == 200, f"자기 팀에 프로젝트를 못 만든다: {r.status_code} {r.text}"
    assert r.json()["project"]["dept_id"] == world["mine_dept"]

    rows = client.get("/api/projects").json()["items"]
    assert r.json()["project"]["id"] in {row["id"] for row in rows}, (
        "방금 만든 프로젝트가 자기 목록에 안 보인다"
    )


def test_a_global_admin_still_sees_everything(client, login_as, world):
    """전역 관리자까지 좁히면 운영이 멈춘다."""
    hdr = {"X-CSRF-Token": login_as("system_admin")}
    rows = client.get("/api/projects").json()["items"]
    assert {world["mine"], world["theirs"]} <= {row["id"] for row in rows}

    r = client.get(f"/api/projects/{world['theirs']}", headers=hdr)
    assert r.status_code == 200, f"전역 관리자가 상세를 못 본다: {r.status_code} {r.text}"


def test_a_regular_user_without_a_department_is_not_narrowed(
    client, login_as, db, make_user, world
):
    """기존 폴백 규칙: **부서가 없으면 안 좁힌다**(`app/core/scope.py::build_scope`).

    반대로 하면 부서를 아직 배정하지 않은 신규 입사자가 아무것도 못 보는 계정이 된다.
    이 규칙을 프로젝트만 다르게 구현하면 화면마다 답이 달라진다.
    """
    newbie = make_user("prj-newbie@goodmit.co.kr", role="user", display_name="신입")
    newbie.department_id = None
    db.commit()

    login_as("user", email="prj-newbie@goodmit.co.kr")
    rows = client.get("/api/projects").json()["items"]
    assert {world["mine"], world["theirs"]} <= {row["id"] for row in rows}, (
        "부서 없는 사용자에게 프로젝트가 안 보인다 - 폴백 규칙과 어긋난다"
    )
