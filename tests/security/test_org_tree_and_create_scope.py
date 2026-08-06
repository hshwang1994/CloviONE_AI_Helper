"""조직도(부서·직책)의 범위 — 목록·트리·생성이 **같은 판정 하나**를 쓴다.

전수 스윕이 실측으로 찾은 세 가지를 고정한다.

## 1) 목록이 부서 범위 관리자에게 통째로 비었다 (닫히는 쪽으로 틀린 것)

`list_items` 가 `scope_filter(scope, org_column=...)` 를 **`dept_column` 없이** 불렀다.
`app/core/scope.py::scope_filter` 는 부서 범위인데 걸 부서 컬럼이 없으면 `MATCH_NOTHING`
으로 떨어진다(fail-closed). 그래서 부서 범위 관리자가 `GET /api/admin/departments` 를 열면
`items: []`, `GET /api/admin/job-titles` 도 `items: []` 였다.

유출은 아니지만 **기능 고장**이고, 특히 직책은 그 파일 주석이 "직책은 조직 단위 어휘라
부서로 나누지 않는다(그러면 자기 팀에 없는 직책을 아무에게도 못 준다)"고 적어 둔 것과
정반대로 동작했다. 그래서 이 파일은 **보여야 하는 것이 보이는지**부터 본다 —
'안 보인다'만 검사하면 전부 404 로 만들어도 초록이 된다.

## 2) `/tree` 에 범위가 없었다

핸들러가 `principal` 을 아예 받지 않고 `tree_rows(db, active=active)` 를 그대로 불렀다.
목록에서 가린 것이 옆 경로로 그대로 샌다 — 그것도 더 많이(조직 이름·부서 계층 path·
상위 부서·인원수).

## 3) 생성에 범위가 없었다

`payload.org_id` / `payload.parent_id` 를 **존재 여부만** 보고 범위는 안 봤다. 부서 범위
관리자가 남의 조직에, 남의 부서 밑에 부서를 만들 수 있었고, 만들어 놓으면 자기 목록에는
안 보이는 유령 행이 남는다.

## 각 테스트는 게이트 하나만 겨냥한다

이 작업에서 "게이트를 뗐는데도 다른 이유로 막혀 테스트가 통과"하는 일이 실제로 두 번
나왔다. 그래서 생성 테스트는 조직 축과 상위 부서 축을 **따로** 시험하고, 상위 부서 쪽은
일부러 **조직 범위** 관리자로 시험한다(부서 범위였다면 '내 서브트리 밖' 판정에도 함께
걸려서 무엇이 막았는지 알 수 없다).
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

pytestmark = pytest.mark.security

BOSS_EMAIL = "orgb@goodmit.co.kr"


@dataclass(frozen=True)
class Chart:
    """조직 B 의 조직도 한 벌 + 그 안의 '내 팀'만 관리하는 관리자."""

    boss: object
    sub: object       # 내 팀의 하위 부서 (내 서브트리 안)
    sibling: object   # 같은 조직이지만 내 서브트리 밖


@pytest.fixture()
def chart(db, two_orgs) -> Chart:
    from app.org.models import Department, JobTitle

    sub = Department(name="B팀 하위", parent_id=two_orgs.dept_b.id, org_id=two_orgs.org_b_id)
    sibling = Department(name="B조직 다른팀", org_id=two_orgs.org_b_id)
    db.add_all([sub, sibling])
    # 직책은 부서가 없다 — 조직만 다르다. 부서 범위 관리자에게도 보여야 한다.
    db.add_all([
        JobTitle(name="B조직 팀장", org_id=two_orgs.org_b_id),
        JobTitle(name="A조직 사원", org_id=two_orgs.org_a_id),
    ])

    boss = two_orgs.user_b
    boss.role = "admin"
    boss.admin_scope = "dept"
    boss.scope_dept_id = two_orgs.dept_b.id
    db.commit()
    return Chart(boss=boss, sub=sub, sibling=sibling)


def _scope_boss_to_org(db, chart: Chart, org_id: str) -> None:
    """부서 범위 → 조직 범위. 상위 부서 판정만 남기고 서브트리 판정을 치운다."""
    chart.boss.admin_scope = "org"
    chart.boss.scope_org_id = org_id
    chart.boss.scope_dept_id = None
    db.commit()


def _departments(db):
    from sqlalchemy import select

    from app.org.models import Department

    db.expire_all()
    return {d.name: d for d in db.execute(select(Department)).scalars().all()}


# ── 1) 목록이 실제로 나온다 ───────────────────────────────────────────────────


def test_a_department_scoped_admin_actually_gets_a_department_list(
    client, login_as, chart, two_orgs
):
    """실측: `items: []` 였다. 자기 서브트리는 **보여야** 하고, 그 밖은 안 보여야 한다."""
    login_as("admin", email=BOSS_EMAIL)
    response = client.get("/api/admin/departments")
    assert response.status_code == 200, response.text
    names = {row["name"] for row in response.json()["items"]}

    assert names, "부서 범위 관리자에게 부서 목록이 통째로 비어 있다"
    assert "B팀" in names, f"자기 부서가 안 보인다: {names}"
    assert "B팀 하위" in names, f"자기 하위 부서가 안 보인다: {names}"
    assert "B조직 다른팀" not in names, f"같은 조직이어도 내 서브트리 밖이다: {names}"
    assert "A팀" not in names, f"다른 조직의 조직도가 보인다: {names}"


def test_job_titles_are_not_split_by_department(client, login_as, chart):
    """직책은 조직 단위 어휘다 — 부서로 나누면 자기 팀에 없는 직책을 아무에게도 못 준다.

    조직 축은 그대로 걸린다(다른 조직 직책은 안 보인다).
    """
    login_as("admin", email=BOSS_EMAIL)
    response = client.get("/api/admin/job-titles")
    assert response.status_code == 200, response.text
    names = {row["name"] for row in response.json()["items"]}

    assert "B조직 팀장" in names, f"직책 목록이 비었다 - 사용자에게 직책을 줄 수 없다: {names}"
    assert "A조직 사원" not in names, f"다른 조직 직책이 보인다: {names}"


# ── 2) 트리도 같은 판정을 지난다 ──────────────────────────────────────────────


def test_the_tree_does_not_hand_out_another_organization(
    client, login_as, chart, two_orgs
):
    """`/tree` 는 목록보다 **더 많이** 준다: 조직 이름, 부서 계층 path, 상위 부서, 인원수."""
    login_as("admin", email=BOSS_EMAIL)
    response = client.get("/api/admin/departments/tree")
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    ids = {row["id"] for row in items}
    names = {row["name"] for row in items}

    assert "B팀" in names, f"자기 부서가 트리에 없다: {names}"
    assert two_orgs.org_a_id not in ids, f"다른 조직 행이 그대로 나온다: {names}"
    assert "굿모닝아이텍" not in names, f"다른 조직 이름이 나온다: {names}"
    assert "A팀" not in names, f"다른 조직 부서가 나온다: {names}"
    assert "B조직 다른팀" not in names, f"트리가 목록과 다른 판정을 쓴다: {names}"
    # path 는 조직 이름을 앞에 붙인다 - 이름 자체를 안 줘야 계층도 안 샌다.
    assert "굿모닝아이텍" not in response.text


# ── 3) 생성에도 같은 판정을 건다 ──────────────────────────────────────────────


def test_you_cannot_create_a_department_in_another_organization(
    client, login_as, chart, two_orgs, db
):
    """`org_id` 만 겨냥한다 - 상위 부서는 안 보낸다(막는 것이 하나뿐이어야 한다)."""
    csrf = login_as("admin", email=BOSS_EMAIL)
    response = client.post(
        "/api/admin/departments",
        json={"name": "몰래만든팀", "org_id": two_orgs.org_a_id},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 403, (
        f"부서 범위 관리자가 남의 조직에 부서를 만든다: {response.status_code} "
        f"{response.text[:200]}"
    )
    assert "몰래만든팀" not in _departments(db), "거절해 놓고 행은 실제로 남았다"


def test_you_cannot_hang_a_new_department_under_another_organizations_department(
    client, login_as, chart, two_orgs, db
):
    """상위 부서 축만 겨냥한다 - 그래서 **조직 범위** 관리자로 시험한다.

    부서 범위였다면 '내 서브트리 밖' 판정에도 함께 걸려서, 상위 부서 판정을 떼어도
    테스트가 통과한다(무엇이 막았는지 알 수 없는 초록불).

    **422 이고 메시지는 '알 수 없는 상위 부서'** 다. 여기만 다른 오류를 주면 남의 부서
    id 를 찍어 보며 존재를 확인할 수 있다(범위 밖은 없는 것과 똑같이 답한다).
    """
    _scope_boss_to_org(db, chart, two_orgs.org_b_id)
    csrf = login_as("admin", email=BOSS_EMAIL)
    response = client.post(
        "/api/admin/departments",
        json={"name": "끼워넣기팀", "parent_id": two_orgs.dept_a.id},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 422, (
        f"남의 조직 부서 밑에 부서가 만들어진다: {response.status_code} "
        f"{response.text[:200]}"
    )
    assert "몰래" not in response.text and "권한" not in response.text, (
        f"범위 밖과 없는 id 의 응답이 다르면 존재가 드러난다: {response.text[:200]}"
    )
    assert "끼워넣기팀" not in _departments(db), "거절해 놓고 행은 실제로 남았다"


def test_you_cannot_move_a_department_under_another_organization(
    client, login_as, chart, two_orgs, db
):
    """생성만 막으면 수정으로 같은 일을 한다 - 상위 부서 판정은 두 경로가 함께 쓴다."""
    _scope_boss_to_org(db, chart, two_orgs.org_b_id)
    csrf = login_as("admin", email=BOSS_EMAIL)
    response = client.patch(
        f"/api/admin/departments/{two_orgs.dept_b.id}",
        json={"parent_id": two_orgs.dept_a.id},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 422, (
        f"자기 부서를 남의 조직 밑으로 옮길 수 있다: {response.status_code} "
        f"{response.text[:200]}"
    )
    assert _departments(db)["B팀"].parent_id is None, "422 를 냈지만 이미 썼다"


# ── 오탐 방지 — 막기만 하면 전부 404 로 만들어도 초록이 된다 ──────────────────


def test_what_a_department_admin_creates_shows_up_in_their_own_list(
    client, login_as, chart, two_orgs
):
    """유령 행 방지. 자기 서브트리 안에는 **만들 수 있어야** 하고, 만든 것이 보여야 한다."""
    csrf = login_as("admin", email=BOSS_EMAIL)
    response = client.post(
        "/api/admin/departments",
        json={"name": "B팀 신설", "parent_id": two_orgs.dept_b.id},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201, f"자기 팀 아래에도 못 만든다: {response.text[:200]}"

    names = {row["name"] for row in client.get("/api/admin/departments").json()["items"]}
    assert "B팀 신설" in names, f"만들어 놓고 자기 목록에서는 안 보인다(유령 행): {names}"


def test_a_department_admin_can_still_add_a_job_title(client, login_as, chart):
    """직책은 조직 단위 어휘다 - 부서 범위 관리자도 자기 조직에 추가할 수 있어야 하고,
    그 결과가 자기 목록에 보여야 한다(조직을 안 보내면 자기 조직에 만든다)."""
    csrf = login_as("admin", email=BOSS_EMAIL)
    response = client.post(
        "/api/admin/job-titles",
        json={"name": "B조직 대리"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201, f"직책을 못 만든다: {response.text[:200]}"

    names = {row["name"] for row in client.get("/api/admin/job-titles").json()["items"]}
    assert "B조직 대리" in names, f"만들어 놓고 자기 목록에서는 안 보인다(유령 행): {names}"


def test_a_global_admin_still_sees_and_creates_everything(
    client, login_as, chart, two_orgs, db
):
    """전역 관리자에게는 아무것도 달라지지 않아야 한다."""
    csrf = login_as("system_admin")

    names = {row["name"] for row in client.get("/api/admin/departments").json()["items"]}
    assert {"A팀", "B팀", "B조직 다른팀"} <= names, f"전역 관리자가 조직도를 다 못 본다: {names}"

    tree_names = {row["name"] for row in client.get("/api/admin/departments/tree").json()["items"]}
    assert {"굿모닝아이텍", "두번째조직"} <= tree_names, f"트리에서 조직이 빠졌다: {tree_names}"

    response = client.post(
        "/api/admin/departments",
        json={"name": "전역이만든팀", "org_id": two_orgs.org_b_id},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201, f"전역 관리자가 부서를 못 만든다: {response.text[:200]}"
    assert _departments(db)["전역이만든팀"].org_id == two_orgs.org_b_id
