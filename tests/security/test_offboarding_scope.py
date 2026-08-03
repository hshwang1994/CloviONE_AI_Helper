"""오프보딩의 관리 범위 — **부서 관리자는 남의 부서 사람을 오프보딩할 수 없다** (Phase 6).

`tests/security/test_scope_idor_matrix.py` 가 사용자 단건에 대해 못박은 규칙을 오프보딩의 세
경로(미리보기 · 실행 · 되돌리기)에도 그대로 적용한다. 한 경로만 빠져도 그 경로가 곧 우회로다.

**403 이 아니라 404 다.** 403 은 "그 id 는 존재한다"를 알려 준다 — 남의 부서 사용자 id 를
넣어 보며 403/404 를 세면 조직도를 통째로 열거할 수 있다.

후임도 같은 규칙을 탄다: 범위 밖 사람에게 티켓을 떠넘길 수 있으면, 그 사람은 자기 화면에서
그 티켓이 어디서 왔는지 알 방법이 없다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.offboarding.models import OffboardingRun
from app.org.constants import DEFAULT_ORG_ID
from app.org.models import Department
from app.users.models import User

pytestmark = pytest.mark.security

PASSWORD = "Str0ng-Passw0rd!"
D_DEV = "obs-dept-dev"
D_SALES = "obs-dept-sales"


@pytest.fixture()
def org(db):
    for row in (
        Department(id=D_DEV, name="개발팀", org_id=DEFAULT_ORG_ID, parent_id=None),
        Department(id=D_SALES, name="영업팀", org_id=DEFAULT_ORG_ID, parent_id=None),
    ):
        db.add(row)
    db.commit()
    return {"dev": D_DEV, "sales": D_SALES}


@pytest.fixture()
def people(db, make_user, org):
    made = {}

    def _mk(key, email, role, *, dept, scope="global", scope_dept=None):
        user = make_user(email=email, role=role, display_name=key)
        user.department_id = dept
        user.admin_scope = scope
        user.scope_dept_id = scope_dept
        user.scope_org_id = DEFAULT_ORG_ID if scope != "global" else None
        db.add(user)
        made[key] = user

    _mk("dept_admin", "obs-da@goodmit.co.kr", "admin", dept=org["dev"],
        scope="dept", scope_dept=org["dev"])
    _mk("global_admin", "obs-ga@goodmit.co.kr", "system_admin", dept=org["dev"])
    _mk("dev_member", "obs-dev@goodmit.co.kr", "user", dept=org["dev"])
    _mk("sales_member", "obs-sales@goodmit.co.kr", "user", dept=org["sales"])
    db.commit()
    return {k: (v.id, v.email) for k, v in made.items()}


def _login(client, email):
    response = client.post("/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def test_preview_of_an_out_of_scope_user_is_404(client, people):
    _login(client, people["dept_admin"][1])
    response = client.get(f"/api/admin/offboarding/preview/{people['sales_member'][0]}")
    assert response.status_code == 404, response.text


def test_preview_inside_the_scope_still_works(client, people):
    """범위 검사가 '전부 막기'로 퇴화하지 않았는지 — 반대 방향 증명."""
    _login(client, people["dept_admin"][1])
    response = client.get(f"/api/admin/offboarding/preview/{people['dev_member'][0]}")
    assert response.status_code == 200, response.text


def test_running_against_an_out_of_scope_user_is_404_and_changes_nothing(client, people, db):
    csrf = _login(client, people["dept_admin"][1])
    response = client.post(
        f"/api/admin/offboarding/run/{people['sales_member'][0]}",
        json={"ticket_page_ids": [], "deactivate": True},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 404, response.text

    # 404 를 냈지만 이미 썼을 수도 있다 — DB 로 되짚는다.
    db.expire_all()
    assert db.get(User, people["sales_member"][0]).active is True
    assert db.execute(select(OffboardingRun)).scalars().all() == []


def test_an_out_of_scope_successor_is_404(client, people):
    """범위 밖 사람에게 티켓을 떠넘기는 우회로를 막는다."""
    csrf = _login(client, people["dept_admin"][1])
    response = client.post(
        f"/api/admin/offboarding/run/{people['dev_member'][0]}",
        json={
            "ticket_page_ids": [],
            "successor_user_id": people["sales_member"][0],
            "deactivate": True,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 404, response.text


def test_a_run_created_elsewhere_is_invisible_and_cannot_be_undone(client, people, db):
    """전역 관리자가 만든 '남의 부서' 실행 기록은 부서 관리자에게 존재하지 않아야 한다."""
    csrf = _login(client, people["global_admin"][1])
    created = client.post(
        f"/api/admin/offboarding/run/{people['sales_member'][0]}",
        json={"ticket_page_ids": [], "deactivate": True},
        headers={"X-CSRF-Token": csrf},
    )
    assert created.status_code == 200, created.text
    run_id = created.json()["run"]["id"]

    csrf = _login(client, people["dept_admin"][1])
    assert client.get("/api/admin/offboarding").json()["items"] == []
    assert client.get(f"/api/admin/offboarding/{run_id}").status_code == 404
    undo = client.post(
        f"/api/admin/offboarding/{run_id}/undo", headers={"X-CSRF-Token": csrf}
    )
    assert undo.status_code == 404, undo.text

    # 되돌리기가 404 로 막혔으면 계정도 그대로여야 한다.
    db.expire_all()
    assert db.get(User, people["sales_member"][0]).active is False


def test_out_of_scope_and_nonexistent_are_indistinguishable(client, people):
    """유출을 막는다는 것은 **두 응답이 구별되지 않는다**는 뜻이다."""
    _login(client, people["dept_admin"][1])
    out_of_scope = client.get(f"/api/admin/offboarding/preview/{people['sales_member'][0]}")
    nonexistent = client.get(
        "/api/admin/offboarding/preview/00000000-0000-4000-8000-0000deadbeef"
    )
    assert out_of_scope.status_code == nonexistent.status_code == 404

    def _strip(body: dict) -> dict:
        error = {k: v for k, v in body["error"].items() if k != "request_id"}
        return {**body, "error": error}

    assert _strip(out_of_scope.json()) == _strip(nonexistent.json())


def test_a_plain_user_cannot_reach_offboarding_at_all(client, people):
    """범위 이전의 방어선 — 역할 게이트."""
    _login(client, people["dev_member"][1])
    assert client.get("/api/admin/offboarding").status_code == 403
    assert client.get(
        f"/api/admin/offboarding/preview/{people['dev_member'][0]}"
    ).status_code == 403
