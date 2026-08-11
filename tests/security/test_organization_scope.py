"""조직 목록·단건·수정도 범위를 지킨다.

## 왜 남아 있었나

같은 파일(`app/org/router.py`) 안에서 **부서·직책은 범위를 지나는데 조직 자체는 안 지났다.**
`GET /api/admin/organizations` 가 `select(Organization)` 그대로였다.

멀티테넌트에서 조직 목록은 곧 **테넌트 명부**다 — 이름·식별자(slug)·부서 수·인원수가 함께
나간다. 다른 고객사의 **존재와 규모**가 콘솔 쓰기 권한자 누구에게나 보이면 안 된다.
부서 트리를 막아 놓고 이 경로를 열어 두면 가린 정보가 그대로 새어 나간다.

부서 범위 관리자도 자기 조직만 본다 — 부서는 조직 안에 있고, 그 사람이 다른 조직의 존재를
알아야 할 이유가 없다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.security


@pytest.fixture()
def two(db, make_user):
    """조직 둘 + 조직 A 로 좁혀진 관리자."""
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Organization

    other = Organization(slug="tenant-z", name="다른회사", status="active")
    db.add(other)
    db.commit()

    boss = make_user("orgscope-boss@goodmit.co.kr", role="admin", display_name="A조직관리자")
    boss.org_id = DEFAULT_ORG_ID
    boss.admin_scope = "org"
    boss.scope_org_id = DEFAULT_ORG_ID
    db.commit()
    return {"mine": DEFAULT_ORG_ID, "theirs": other.id}


def test_the_list_shows_only_my_organization(client, login_as, two):
    login_as("admin", email="orgscope-boss@goodmit.co.kr")
    items = client.get("/api/admin/organizations").json()["items"]
    ids = {i["id"] for i in items}
    assert two["mine"] in ids, "자기 조직이 안 보인다"
    assert two["theirs"] not in ids, f"다른 테넌트의 존재와 규모가 보인다: {items}"


def test_another_organization_is_404_by_id(client, login_as, two):
    """목록만 가려서는 소용없다 — 상세는 id 를 직접 받는다."""
    login_as("admin", email="orgscope-boss@goodmit.co.kr")
    r = client.get(f"/api/admin/organizations/{two['theirs']}")
    assert r.status_code == 404, f"다른 조직이 id 하나로 열린다: {r.status_code} {r.text}"


def test_another_organization_cannot_be_changed(client, login_as, db, two):
    """정지는 **그 조직 전원의 로그인을 끊는다** — 범위 밖에서 되면 안 된다."""
    from app.org.models import Organization

    csrf = login_as("admin", email="orgscope-boss@goodmit.co.kr")
    r = client.patch(
        f"/api/admin/organizations/{two['theirs']}",
        json={"status": "suspended"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 404, f"다른 조직을 정지시킬 수 있다: {r.status_code} {r.text}"
    db.expire_all()
    assert db.get(Organization, two["theirs"]).status == "active", (
        "404 를 주면서 실제로는 정지시켰다"
    )


def test_my_own_organization_still_works(client, login_as, two):
    """오탐 방지 — 좁히느라 자기 조직까지 못 보면 그건 기능 고장이다."""
    csrf = login_as("admin", email="orgscope-boss@goodmit.co.kr")
    assert client.get(f"/api/admin/organizations/{two['mine']}").status_code == 200
    r = client.patch(
        f"/api/admin/organizations/{two['mine']}",
        json={"name": "굿모닝아이텍(수정)"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, f"자기 조직을 못 고친다: {r.text}"


def test_a_global_admin_still_sees_every_tenant(client, login_as, two):
    """포탈 운영자는 전 테넌트를 봐야 한다 — 안 그러면 조직을 만들고 관리할 수 없다."""
    login_as("system_admin")
    ids = {i["id"] for i in client.get("/api/admin/organizations").json()["items"]}
    assert {two["mine"], two["theirs"]} <= ids, f"전역 관리자가 조직을 못 본다: {ids}"


def test_a_name_in_another_organization_is_not_revealed_by_conflict(
    client, login_as, db, two
):
    """🔴 목록·트리를 다 가려 놓고 **409 한 줄로 이름을 확인**할 수 있었다.

    중복 검사(`find_by_name`)가 전역이라, 남의 조직 부서 이름을 추측해 POST 하면
    `409 "이미 있는 부서입니다: <이름>"` 이 돌아왔다. 실제 유니크 제약은 `(org_id, name)` 인데
    검사만 넓었던 것이다 — **막는 것 없이 정보만 흘리는** 모양이다.

    이제 같은 이름이 다른 조직에 있어도 내 조직에서는 그냥 만들어진다(제약이 그렇게 돼 있다).
    """
    from app.org.models import Department

    db.add(Department(name="비밀프로젝트팀", org_id=two["theirs"]))
    db.commit()

    csrf = login_as("admin", email="orgscope-boss@goodmit.co.kr")
    r = client.post(
        "/api/admin/departments",
        json={"name": "비밀프로젝트팀"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code != 409, (
        f"다른 조직에 그 이름이 있다는 사실이 409 로 드러난다: {r.text}"
    )
    assert r.status_code == 201, f"내 조직에는 만들 수 있어야 한다: {r.status_code} {r.text}"


def test_a_duplicate_inside_my_own_organization_is_still_rejected(
    client, login_as, db, two
):
    """오탐 방지 — 같은 조직 안 중복은 여전히 막아야 한다(그게 이 검사의 본래 목적이다)."""
    csrf = login_as("admin", email="orgscope-boss@goodmit.co.kr")
    first = client.post(
        "/api/admin/departments", json={"name": "중복테스트팀"},
        headers={"X-CSRF-Token": csrf},
    )
    assert first.status_code == 201, first.text
    again = client.post(
        "/api/admin/departments", json={"name": "중복테스트팀"},
        headers={"X-CSRF-Token": csrf},
    )
    assert again.status_code == 409, f"같은 조직 안 중복이 통과했다: {again.status_code}"


def test_org_scoped_admin_cannot_create_a_new_tenant(client, login_as, two):
    """UA-11: 조직 생성은 새 테넌트를 여는 일이라 전역 관리자만 할 수 있어야 한다.
    이 라우터는 `require_roles(*CONSOLE_WRITE_ROLES)`(role="admin"이면 통과)만 걸려
    있었는데, role과 admin_scope는 서로 다른 축이라 자기 조직 하나로 좁혀진 admin도
    role 검사는 그냥 통과한다 — 그래서 부서/직책과 달리 조직 자체를 만드는 이 경로에
    scope 검사가 아예 없었다(principal조차 안 받았다)."""
    csrf = login_as("admin", email="orgscope-boss@goodmit.co.kr")
    r = client.post(
        "/api/admin/organizations",
        json={"name": "새 테넌트", "slug": "sneaky-tenant"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 403, r.text


def test_global_admin_can_still_create_a_tenant(client, login_as):
    """회귀 방지 — 포탈 운영자는 여전히 조직을 만들 수 있어야 한다."""
    csrf = login_as("system_admin")
    r = client.post(
        "/api/admin/organizations",
        json={"name": "새 테넌트", "slug": "legit-tenant"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 201, r.text
