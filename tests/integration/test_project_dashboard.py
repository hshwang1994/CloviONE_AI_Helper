"""프로젝트 대시보드 - **집계가 페이지네이션과 무관하게 정확한가**.

이 파일이 지키는 것은 숫자 하나가 아니라 '무엇을 세는 표본인가' 다. 이 저장소가 겪은
함정이 정확히 그 자리에 있다:

  1. 목록은 20건씩 잘린다(`PageParams`). 화면이 그 한 장을 세면 "총 22건인데 대시보드는
     20건 기준" 이 된다 - 숫자가 그럴듯해서 아무도 신고하지 않는다. 그래서 표본을 **22건**
     으로 두고 상한(20)에 걸리는지 본다.
  2. `health_score` 가 NULL 인 것은 '아직 안 쟀다' 지 나쁜 것이 아니다. 하위로 세면 새로
     만든 프로젝트가 전부 빨갛게 떠서 진짜 차질이 그 안에 묻힌다.
  3. `progress_pct` 가 NULL 인 것을 0 으로 세면 프로젝트를 만들 때마다 팀 평균이 떨어지고,
     그 하락에는 아무 의미가 없다.

표본은 값이 **서로 다른 것**을 쓴다. 같은 값을 늘어놓으면 평균을 안 세고 상수를 돌려주는
구현도 통과한다.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.org.constants import DEFAULT_ORG_ID
from app.projects.models import Project, ProjectMilestone

pytestmark = pytest.mark.integration

NOW = datetime(2026, 7, 14, 0, 0, 0)
BOSS_EMAIL = "prj-dash@goodmit.co.kr"

# 판정 기준일. 마일스톤 지연을 이 날짜로 가른다.
TODAY = "2026-07-14"

# 페이지 상한(20)보다 큰 표본. 이 숫자가 이 파일의 존재 이유다.
PROJECT_COUNT = 22


def _project(db, *, name, status="active", progress=None, health=None,
             notion_status=None, archived=None, dept_id=None):
    row = Project(
        name=name,
        org_id=DEFAULT_ORG_ID,
        dept_id=dept_id,
        status=status,
        progress_pct=progress,
        health_score=health,
        notion_status=notion_status,
        archived_at=archived,
        created_at=NOW,
        updated_at=NOW,
    )
    db.add(row)
    return row


def _milestone(db, project, *, name, due_on, status="planned"):
    row = ProjectMilestone(
        project_id=project.id,
        name=name,
        due_on=due_on,
        status=status,
        sort_order=0,
        created_at=NOW,
        updated_at=NOW,
    )
    db.add(row)
    return row


@pytest.fixture()
def boss(db, make_user):
    user = make_user(BOSS_EMAIL, role="admin", display_name="관리자")
    user.admin_scope = "global"
    db.commit()
    return user


def _hdr(login_as):
    return {"X-CSRF-Token": login_as("admin", email=BOSS_EMAIL)}


def _dashboard(client, login_as):
    r = client.get("/api/projects/dashboard", headers=_hdr(login_as))
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture()
def world(db, boss):
    """22건. 상태·진행률·헬스가 **서로 다르게** 섞여 있다.

    구성(보관 제외 22건):
      * active   12건 - 그중 4건은 헬스 45/50/55/59(하위), 3건은 헬스 NULL(못 잼)
      * done      5건
      * on_hold   3건
      * planned   2건
    진행률은 12건만 계산돼 있고 10건은 NULL 이다.
    """
    projects = []
    # 하위 헬스 4건. 60 미만이고 값이 전부 다르다(정렬까지 본다).
    for i, score in enumerate((45, 50, 55, 59)):
        projects.append(_project(
            db, name=f"하위-{i}", status="active", health=score, progress=float(10 + i),
        ))
    # 경계값 60 은 하위가 **아니다**(미만이지 이하가 아니다).
    projects.append(_project(db, name="경계-60", status="active", health=60, progress=20.0))
    # 헬스를 아직 안 잰 것 3건. 하위로 세면 안 된다.
    for i in range(3):
        projects.append(_project(db, name=f"미측정-{i}", status="active", health=None))
    # 나머지 active 4건은 건강하다.
    for i in range(4):
        projects.append(_project(
            db, name=f"건강-{i}", status="active", health=80 + i, progress=float(50 + i),
        ))
    for i in range(5):
        projects.append(_project(
            db, name=f"완료-{i}", status="done", health=95, progress=100.0,
        ))
    for i in range(3):
        projects.append(_project(db, name=f"보류-{i}", status="on_hold", health=70))
    for i in range(2):
        projects.append(_project(db, name=f"계획-{i}", status="planned", health=None))

    # 보관된 것은 어느 숫자에도 들어가지 않는다.
    archived = _project(db, name="보관됨", status="active", health=10, progress=5.0,
                        archived=NOW)
    db.commit()

    # 마일스톤: 지연 3건 + 지연이 아닌 것 3건.
    live = projects[0]
    _milestone(db, live, name="지난 기한 1", due_on="2026-07-01")
    _milestone(db, live, name="지난 기한 2", due_on="2026-07-13")
    _milestone(db, projects[1], name="지난 기한 3", due_on="2026-06-01")
    # 오늘이 기한이면 아직 늦은 것이 아니다(자정까지 남았다).
    _milestone(db, live, name="오늘 기한", due_on=TODAY)
    # 이미 결론이 난 일은 지연이 아니다.
    _milestone(db, live, name="늦었지만 완료", due_on="2026-07-01", status="done")
    # 기한이 없으면 늦을 수가 없다.
    _milestone(db, live, name="기한 없음", due_on=None)
    # 보관된 프로젝트의 지난 기한은 세지 않는다.
    _milestone(db, archived, name="보관 프로젝트의 지난 기한", due_on="2026-05-01")
    db.commit()

    return {"total": PROJECT_COUNT}


def test_the_dashboard_counts_all_projects_not_just_the_first_page(
    client, login_as, world
):
    """🔴 20건 상한에 걸리면 22 가 아니라 20 이 나온다 - 이 화면이 존재하는 이유다."""
    body = _dashboard(client, login_as)

    assert body["total"] == PROJECT_COUNT, (
        f"페이지 한 장(20건)만 세고 있다: total={body['total']}"
    )
    # 상태별 합이 전체와 맞아야 한다. 한쪽만 잘리면 여기서 갈라진다.
    assert sum(body["by_status"].values()) == PROJECT_COUNT, body["by_status"]


def test_status_counts_are_exact(client, login_as, world):
    counts = _dashboard(client, login_as)["by_status"]

    assert counts["active"] == 12, counts
    assert counts["done"] == 5, counts
    assert counts["on_hold"] == 3, counts
    assert counts["planned"] == 2, counts


def test_an_archived_project_is_in_no_number(client, login_as, world):
    """보관은 소프트 삭제다. 목록에서 빠진 것이 대시보드에만 남으면 두 화면이 갈라진다."""
    body = _dashboard(client, login_as)

    names = [p["name"] for p in body["health"]["trouble"]["items"]]
    assert "보관됨" not in names, f"보관된 프로젝트가 차질 목록에 있다: {names}"
    assert body["total"] == PROJECT_COUNT
    ms_names = [m["name"] for m in body["milestones"]["overdue"]["items"]]
    assert "보관 프로젝트의 지난 기한" not in ms_names, ms_names


def test_health_null_is_not_counted_as_low(client, login_as, world):
    """🔴 아직 안 잰 것과 재 봤더니 나쁜 것은 다른 사실이다."""
    health = _dashboard(client, login_as)["health"]

    # 45/50/55/59 네 건만 하위다. 60 은 미만이 아니고, NULL 5건(미측정 3 + 계획 2)은 아니다.
    assert health["trouble"]["count"] == 4, (
        f"NULL 이나 경계값 60 이 하위로 섞였다: {health['trouble']}"
    )
    assert health["unscored"] == 5, (
        f"못 잰 건수를 따로 세지 않는다: {health['unscored']}"
    )


def test_trouble_items_carry_the_reason(client, login_as, world):
    """"차질 4건" 만 보면 그것을 본 팀장이 할 수 있는 일이 없다. 이유가 곧 할 일 목록이다."""
    items = _dashboard(client, login_as)["health"]["trouble"]["items"]

    assert items, "차질이 4건인데 목록이 비어 있다"
    assert items[0]["health_score"] == 45, f"나쁜 것이 위로 오지 않는다: {items}"
    assert items[0]["reasons"], f"이유 없이 점수만 낸다: {items[0]}"


def test_a_notion_trouble_project_is_low_even_without_a_score(client, login_as, db, world):
    """사람이 직접 '차질' 이라고 적어 둔 것은 점수가 없어도 봐야 한다."""
    before = _dashboard(client, login_as)["health"]["trouble"]["count"]

    _project(db, name="노션이 차질이라 함", status="active", health=None,
             notion_status="차질")
    db.commit()

    after = _dashboard(client, login_as)["health"]["trouble"]["count"]
    assert after == before + 1, f"노션 차질을 안 센다: {before} -> {after}"


def test_the_average_progress_ignores_nulls_rather_than_counting_them_as_zero(
    client, login_as, world
):
    """🔴 NULL 을 0 으로 세면 프로젝트를 만들 때마다 평균이 떨어진다(의미 없는 하락)."""
    progress = _dashboard(client, login_as)["progress"]

    # 계산된 것: 10,11,12,13(하위 4건) + 20(경계) + 50,51,52,53(건강 4건) + 100×5
    values = [10, 11, 12, 13, 20, 50, 51, 52, 53] + [100] * 5
    assert progress["counted"] == len(values), (
        f"표본 수가 다르다: {progress}"
    )
    assert progress["not_counted"] == PROJECT_COUNT - len(values), progress
    assert progress["average_pct"] == pytest.approx(
        round(sum(values) / len(values), 1)
    ), f"NULL 을 0 으로 세고 있다(그러면 평균이 더 낮게 나온다): {progress}"


def test_the_average_is_null_when_nothing_has_been_computed(client, login_as, db, boss):
    """셀 것이 없으면 0% 가 아니라 '없음' 이다. 0 은 '세어 봤더니 0' 이라는 뜻이다."""
    _project(db, name="아직 안 잰 프로젝트", status="active")
    db.commit()

    progress = _dashboard(client, login_as)["progress"]
    assert progress["average_pct"] is None, f"세지 않은 것을 0% 라고 답한다: {progress}"
    assert progress["counted"] == 0, progress


def test_overdue_milestones_are_exact_and_respect_the_boundary(client, login_as, world):
    """기한이 오늘이면 아직 늦지 않았고, 완료·기한 없음은 지연이 아니다."""
    overdue = _dashboard(client, login_as)["milestones"]["overdue"]

    assert overdue["count"] == 3, f"경계나 완료가 섞였다: {overdue}"
    names = [m["name"] for m in overdue["items"]]
    assert "오늘 기한" not in names, names
    assert "늦었지만 완료" not in names, names
    assert "기한 없음" not in names, names
    # 기한이 빠른 것부터. 순서가 흔들리면 상한으로 자를 때 다른 줄이 잘린다.
    assert [m["due_on"] for m in overdue["items"]] == [
        "2026-06-01", "2026-07-01", "2026-07-13",
    ], overdue["items"]
    # 마일스톤 이름만으로는 어느 프로젝트 것인지 알 수 없다.
    assert all(m["project_name"] for m in overdue["items"]), overdue["items"]


def test_the_item_list_is_capped_but_the_count_is_not(client, login_as, db, world):
    """`count` 는 진짜 총계이고 `items` 만 잘린다 - "12건" 이라 쓰고 5줄을 그리는 어긋남이
    구조적으로 안 생기게."""
    for i in range(9):
        _project(db, name=f"추가 지연 {i}", status="active", health=30)
    db.commit()

    trouble = _dashboard(client, login_as)["health"]["trouble"]
    assert trouble["count"] == 13, trouble["count"]
    assert len(trouble["items"]) <= 5, len(trouble["items"])


def test_out_of_scope_projects_are_in_no_number(client, login_as, db, make_user, boss):
    """범위 밖은 목록에서 안 보인다. 대시보드 숫자에 섞이면 목록에 범위를 건 의미가 없다.

    ⚠️ **범위 밖 표본을 제대로 만들어야 한다.** 예전에는 부서를 지정하지 않은 프로젝트를
    심고 "부서가 없는 관리자는 아무것도 못 본다" 에 기댔다. 0060 에서 부서 없는 프로젝트는
    **조직 공통**이고 조직 직속인 사람에게는 정상으로 보인다 — 그 표본으로는 범위가 걸리는지
    아닌지를 구별할 수 없다. 그래서 이 사람이 속하지 않은 **다른 부서**의 프로젝트를 심는다.
    """
    from app.org.models import Department

    theirs = Department(name="남의 본부", org_id=DEFAULT_ORG_ID)
    db.add(theirs)
    db.flush()

    other = make_user("prj-dash-dept@goodmit.co.kr", role="admin", display_name="부서장")
    other.admin_scope = "dept"
    other.department_id = mine_dept(db).id
    db.commit()

    _project(db, name="남의 부서 프로젝트", status="active", health=10, dept_id=theirs.id)
    db.commit()

    hdr = {"X-CSRF-Token": login_as("admin", email="prj-dash-dept@goodmit.co.kr")}
    body = client.get("/api/projects/dashboard", headers=hdr).json()

    assert body["total"] == 0, f"범위 밖 프로젝트가 집계에 섞였다: {body}"
    assert body["health"]["trouble"]["count"] == 0, body["health"]


def mine_dept(db):
    """이 사람이 속할 부서. 남의 부서와 **형제**여야 한다 — 조상/후손이면 줄기 규칙상
    정상으로 보이고, 그러면 위 시험이 범위를 재는 것이 아니라 계층을 재게 된다."""
    from app.org.models import Department

    row = Department(name="우리 본부", org_id=DEFAULT_ORG_ID)
    db.add(row)
    db.flush()
    return row


def test_the_dashboard_route_is_not_swallowed_by_the_project_id_route(client, login_as, boss):
    """`/{project_id}` 가 먼저 선언되면 'dashboard' 가 프로젝트 id 로 잡혀 404 가 된다.

    그때 증상은 "그 프로젝트가 없다" 라서 원인이 라우팅이라는 것을 아무도 못 찾는다.
    """
    r = client.get("/api/projects/dashboard", headers=_hdr(login_as))
    assert r.status_code == 200, r.text
    assert "by_status" in r.json(), r.json()
