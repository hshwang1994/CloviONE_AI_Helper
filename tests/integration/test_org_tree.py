"""조직도 트리 — 0024 의 `Department.parent_id` 를 실제로 쓰는 첫 화면 (Phase 6).

0024 가 부모 컬럼을 심었지만 그 값을 지정할 수도, 볼 수도 없었다. 여기서 못박는 것:

  * 트리가 **평탄화된 행 목록**으로 나온다(관리 목록 화면 하나가 그대로 그린다).
  * 서브트리 인원 합계가 맞는다 — 부서를 지울지 말지 판단하는 근거다.
  * **사이클을 만들 수 없다.** 자기 자손을 부모로 지정하면 그 덩어리가 조직도의 루트에서
    통째로 사라진다(그리고 `department_subtree_ids` 는 무한 루프 방어만 할 뿐 데이터를
    고쳐 주지 않는다).
  * `/tree` 가 `/{item_id}` 에 **가려지지 않는다**(정적 경로가 경로 파라미터에 먹히는 함정).
  * 직책에는 상위 개념이 없다 — parent_id 를 보내면 조용히 무시되지 않고 거절된다.
"""

from __future__ import annotations

import pytest

from app.org.models import Department
from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration


@pytest.fixture()
def admin(client, make_user):
    make_user(email="boss@goodmit.co.kr", role="system_admin", display_name="관리자")
    response = client.post(
        "/login", json={"email": "boss@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


@pytest.fixture()
def tree(db, make_user):
    """본부 > 개발팀 > 프런트팀, 그리고 별개의 영업팀. 인원은 잎에만 둔다."""
    rows = [
        Department(id="d-hq", name="본부", parent_id=None),
        Department(id="d-dev", name="개발팀", parent_id="d-hq"),
        Department(id="d-fe", name="프런트팀", parent_id="d-dev"),
        Department(id="d-sales", name="영업팀", parent_id=None),
    ]
    for row in rows:
        db.add(row)
    db.commit()
    for index, dept in enumerate(("d-fe", "d-fe", "d-dev", "d-sales")):
        user = make_user(email=f"t{index}@goodmit.co.kr", display_name=f"사람{index}")
        user.department_id = dept
        db.add(user)
    db.commit()
    return {r.id: r.name for r in rows}


def _items(client):
    response = client.get("/api/admin/departments/tree")
    assert response.status_code == 200, response.text
    return response.json()["items"]


def test_tree_route_is_not_shadowed_by_the_id_route(client, admin, tree):
    """`/{item_id}` 가 먼저 선언돼 있으면 이 경로는 영영 '부서를 찾을 수 없습니다'만 돌려준다."""
    response = client.get("/api/admin/departments/tree")
    assert response.status_code == 200, response.text
    assert "items" in response.json()


def test_rows_come_out_in_depth_first_order_with_a_readable_path(client, admin, tree):
    rows = {r["id"]: r for r in _items(client)}
    assert rows["d-hq"]["depth"] == 0
    assert rows["d-dev"]["depth"] == 1
    assert rows["d-fe"]["depth"] == 2
    assert rows["d-fe"]["path"] == "본부 › 개발팀 › 프런트팀"
    assert rows["d-fe"]["parent_name"] == "개발팀"

    order = [r["id"] for r in _items(client)]
    # 부모 바로 뒤에 자식이 온다(들여쓴 표가 곧 트리가 되는 조건).
    assert order.index("d-hq") < order.index("d-dev") < order.index("d-fe")


def test_subtree_counts_roll_up(client, admin, tree):
    rows = {r["id"]: r for r in _items(client)}
    assert rows["d-fe"]["user_count"] == 2
    assert rows["d-dev"]["user_count"] == 1
    assert rows["d-dev"]["subtree_user_count"] == 3      # 개발팀 1 + 프런트팀 2
    assert rows["d-hq"]["subtree_user_count"] == 3       # 본부 0 + 아래 3
    assert rows["d-sales"]["subtree_user_count"] == 1


def test_a_department_can_be_moved_under_another(client, admin, tree, db):
    response = client.patch(
        "/api/admin/departments/d-sales", json={"parent_id": "d-hq"},
        headers={"X-CSRF-Token": admin},
    )
    assert response.status_code == 200, response.text
    assert response.json()["department"]["parent_id"] == "d-hq"

    db.expire_all()
    assert db.get(Department, "d-sales").parent_id == "d-hq"


def test_a_cycle_is_refused(client, admin, tree, db):
    """개발팀을 자기 손자(프런트팀) 밑으로 넣으면 그 가지가 통째로 사라진다."""
    response = client.patch(
        "/api/admin/departments/d-dev", json={"parent_id": "d-fe"},
        headers={"X-CSRF-Token": admin},
    )
    assert response.status_code == 422, response.text
    db.expire_all()
    assert db.get(Department, "d-dev").parent_id == "d-hq", "422 를 냈지만 이미 썼다"


def test_a_department_cannot_be_its_own_parent(client, admin, tree):
    response = client.patch(
        "/api/admin/departments/d-dev", json={"parent_id": "d-dev"},
        headers={"X-CSRF-Token": admin},
    )
    assert response.status_code == 422, response.text


def test_parent_can_be_cleared_back_to_top_level(client, admin, tree, db):
    response = client.patch(
        "/api/admin/departments/d-fe", json={"parent_id": None},
        headers={"X-CSRF-Token": admin},
    )
    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.get(Department, "d-fe").parent_id is None


def test_creating_with_a_parent_works(client, admin, tree, db):
    response = client.post(
        "/api/admin/departments", json={"name": "백엔드팀", "parent_id": "d-dev"},
        headers={"X-CSRF-Token": admin},
    )
    assert response.status_code == 201, response.text
    assert response.json()["department"]["parent_id"] == "d-dev"


def test_an_unknown_parent_is_refused(client, admin, tree):
    response = client.post(
        "/api/admin/departments", json={"name": "유령팀", "parent_id": "no-such-dept"},
        headers={"X-CSRF-Token": admin},
    )
    assert response.status_code == 422, response.text


def test_job_titles_have_no_tree(client, admin):
    """직책 스키마가 parent_id 를 받아 주면 그 값이 **조용히 무시**된다(성공 토스트까지 뜬다)."""
    assert client.get("/api/admin/job-titles/tree").status_code == 404
    response = client.post(
        "/api/admin/job-titles", json={"name": "팀장", "parent_id": "d-dev"},
        headers={"X-CSRF-Token": admin},
    )
    assert response.status_code == 422, response.text


def test_an_orphaned_department_still_shows_up(client, admin, db):
    """부모가 필터로 빠져도 자식이 화면에서 사라지면 안 된다(조용한 소실이 가장 나쁜 실패다)."""
    db.add(Department(id="d-a", name="상위", parent_id=None, active=False))
    db.add(Department(id="d-b", name="하위", parent_id="d-a", active=True))
    db.commit()
    rows = client.get("/api/admin/departments/tree?active=true").json()["items"]
    ids = {r["id"] for r in rows}
    assert "d-a" not in ids
    assert "d-b" in ids
