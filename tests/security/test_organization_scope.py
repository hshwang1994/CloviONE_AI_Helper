"""조직 목록·단건·수정도 범위를 지킨다.

## 왜 남아 있었나

같은 파일(`app/org/router.py`) 안에서 **부서·직책은 범위를 지나는데 조직 자체는 안 지났다.**
`GET /api/admin/organizations` 가 `select(Organization)` 그대로였다.

멀티테넌트에서 조직 목록은 곧 **테넌트 명부**다 — 이름·식별자(slug)·부서 수·인원수가 함께
나간다. 다른 고객사의 **존재와 규모**가 콘솔 쓰기 권한자 누구에게나 보이면 안 된다.
부서 트리를 막아 놓고 이 경로를 열어 두면 가린 정보가 그대로 새어 나간다.

부서 범위 관리자도 자기 조직만 본다 — 부서는 조직 안에 있고, 그 사람이 다른 조직의 존재를
알아야 할 이유가 없다.

qa-contract-change: 「부서 범위 관리자는 상위 칸을 비워 저장할 수 없다」던 계약을 「범위 밖으로 **옮기는** 것만 막는다」로 좁힌다. 이미 최상위인 부서에 빈 상위를 다시 보내는 것은 이동이 아니라 무변경 저장이고, 그것까지 막으면 자기 범위의 뿌리가 최상위인 관리자는 그 부서의 이름조차 고칠 수 없었다(R4-05). 진짜 이동을 막는 단언은 그대로 남고, 새 시험이 무변경 저장과 이름 변경을 함께 잰다.

qa-contract-change: 「자기 조직 정보는 부서 범위 관리자도 고칠 수 있다」던 계약을 「조직 정보는 전체 범위 관리자만 바꿀 수 있다」로 바꿨다. 조직 이름은 테넌트의 정체라 로그인 화면·머리·프로필·감사
로그에 그대로 나가는데, 부서 하나를 맡은 관리자가 회사 이름을 바꾸면 전 구성원의 화면이
함께 바뀌고 되돌릴 사람은 전역 관리자뿐이다. 같은 라우터의 생성(403)·정지(403)가 이미 그
문을 지나므로 이름 변경만 예외일 이유가 없다(org-07 · xa-02). 조회는 그대로 200 이다.
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


def test_my_own_organization_is_readable_but_not_editable(client, login_as, db, two):
    """조회는 그대로, 수정은 전역 관리자만 (org-07).

    좁히느라 자기 조직까지 **못 보면** 그건 기능 고장이다 — 그래서 GET 은 200 이다.
    그러나 조직 이름을 바꾸는 것은 테넌트의 정체를 바꾸는 일이라 같은 라우터의 생성·정지와
    같은 문을 지나야 한다.
    """
    from app.org.models import Organization

    csrf = login_as("admin", email="orgscope-boss@goodmit.co.kr")
    assert client.get(f"/api/admin/organizations/{two['mine']}").status_code == 200
    before = db.get(Organization, two["mine"]).name
    r = client.patch(
        f"/api/admin/organizations/{two['mine']}",
        json={"name": "굿모닝아이텍(수정)"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 403, f"범위 관리자가 회사 이름을 바꾼다: {r.status_code} {r.text}"
    assert r.json()["error"]["message"] == "조직 정보는 전체 범위 관리자만 바꿀 수 있습니다."
    db.expire_all()
    assert db.get(Organization, two["mine"]).name == before, "403 을 주면서 실제로는 바꿨다"


def test_a_global_admin_can_still_rename_an_organization(client, login_as, db, two):
    """오탐 방지 — 포탈 운영자는 여전히 조직 이름을 고칠 수 있어야 한다."""
    from app.org.models import Organization

    csrf = login_as("system_admin")
    r = client.patch(
        f"/api/admin/organizations/{two['mine']}",
        json={"name": "굿모닝아이텍(개명)"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, f"전역 관리자가 조직을 못 고친다: {r.text}"
    db.expire_all()
    assert db.get(Organization, two["mine"]).name == "굿모닝아이텍(개명)"


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


# ── 부서 범위 관리자는 자기 서브트리 밖으로 부서를 밀어낼 수 없다 (org-06) ────
#
# 생성은 403 인데 수정은 200 이었다. 「상위 부서 = (최상위)」로 저장하면 그 부서가 조직
# 최상위로 올라가는데, 최상위 부서는 어느 서브트리에도 안 들어가므로 그 순간 자기 관리
# 범위 밖이 된다 — 저장 직후 상세가 404 로 바뀌고 되돌릴 사람은 전역 관리자뿐이다.

BOSS = "deptscope-boss@goodmit.co.kr"


@pytest.fixture()
def subtree(db, make_user):
    """부서 하나를 맡은 관리자 + 그 서브트리 + 범위 밖 부서 하나."""
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    root = Department(name="서비스운영팀", org_id=DEFAULT_ORG_ID)
    outside = Department(name="플랫폼개발팀", org_id=DEFAULT_ORG_ID)
    db.add_all([root, outside])
    db.flush()
    child = Department(name="운영1팀", parent_id=root.id, org_id=DEFAULT_ORG_ID)
    sibling = Department(name="운영2팀", parent_id=root.id, org_id=DEFAULT_ORG_ID)
    db.add_all([child, sibling])

    boss = make_user(BOSS, role="admin", display_name="부서관리자")
    boss.org_id = DEFAULT_ORG_ID
    boss.department_id = root.id
    boss.admin_scope = "dept"
    boss.scope_dept_id = root.id
    db.commit()
    return {
        "root": root.id, "child": child.id, "sibling": sibling.id, "outside": outside.id,
    }


def test_a_dept_scoped_admin_cannot_push_a_department_to_the_top_level(
    client, login_as, db, subtree
):
    """🔴 저장 한 번으로 자기 부서를 범위 밖으로 내보내고 스스로 잠갔다."""
    from app.org.models import Department

    csrf = login_as("admin", email=BOSS)
    r = client.patch(
        f"/api/admin/departments/{subtree['child']}",
        json={"parent_id": ""},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 403, (
        f"범위 관리자가 부서를 조직 최상위로 밀어냈다: {r.status_code} {r.text}"
    )
    db.expire_all()
    assert db.get(Department, subtree["child"]).parent_id == subtree["root"], (
        "403 을 주면서 이미 옮겼다"
    )


def test_saving_an_already_top_level_department_is_not_a_move(
    client, login_as, db, subtree
):
    """이미 최상위인 부서의 수정 폼은 상위 칸이 빈 채로 다시 저장된다 — 그것은 이동이 아니다.

    막는 규칙은 「범위 밖으로 **옮기는 것**」이고, 이 요청은 아무것도 옮기지 않는다. 무변경
    저장까지 403 으로 막으면 자기 범위의 뿌리가 최상위인 관리자는 그 부서의 이름조차 고칠 수
    없다 — 바로 아래 이름 변경이 그 사실을 함께 잰다. 진짜 이동(부모가 있는 부서를 최상위로)은
    위 시험이 그대로 403 으로 못박는다.
    """
    from app.org.models import Department

    csrf = login_as("admin", email=BOSS)
    r = client.patch(
        f"/api/admin/departments/{subtree['root']}",
        json={"parent_id": ""},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, f"무변경 저장이 막혔다: {r.status_code} {r.text}"
    db.expire_all()
    root = db.get(Department, subtree["root"])
    assert root.parent_id is None, "최상위였던 부서가 저장 뒤에 부모를 얻었다"
    assert root.org_id is not None

    r = client.patch(
        f"/api/admin/departments/{subtree['root']}",
        json={"parent_id": "", "name": "서비스운영팀(개명)"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, f"자기 범위의 뿌리를 이름조차 못 고친다: {r.text}"
    db.expire_all()
    assert db.get(Department, subtree["root"]).name == "서비스운영팀(개명)"


def test_a_dept_scoped_admin_can_still_rearrange_inside_their_scope(
    client, login_as, db, subtree
):
    """오탐 방지 — 자기 서브트리 안에서의 이동과 수정은 그대로 된다.

    막기만 하면 전부 403 으로 만들어도 초록이 된다.
    """
    from app.org.models import Department

    csrf = login_as("admin", email=BOSS)
    r = client.patch(
        f"/api/admin/departments/{subtree['sibling']}",
        json={"parent_id": subtree["child"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, f"자기 서브트리 안에서도 못 옮긴다: {r.text}"
    db.expire_all()
    assert db.get(Department, subtree["sibling"]).parent_id == subtree["child"]

    r = client.patch(
        f"/api/admin/departments/{subtree['child']}",
        json={"name": "운영1팀(개명)"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, f"이름조차 못 고친다: {r.text}"


def test_a_global_admin_can_still_move_a_department_to_the_top_level(
    client, login_as, db, subtree
):
    """오탐 방지 — 전역 관리자에게는 아무것도 달라지지 않는다."""
    from app.org.models import Department

    csrf = login_as("system_admin")
    r = client.patch(
        f"/api/admin/departments/{subtree['child']}",
        json={"parent_id": ""},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, f"전역 관리자가 부서를 최상위로 못 올린다: {r.text}"
    db.expire_all()
    assert db.get(Department, subtree["child"]).parent_id is None


# ── 한 화면의 두 숫자가 같은 모집단을 센다 (org-12) ──────────────────────────


def test_a_scoped_admin_sees_only_the_counts_they_can_see(
    client, login_as, db, make_user, subtree
):
    """조직 상세 판의 숫자가 트리와 같은 범위를 센다.

    예전에는 요약 타일이 「1 부서」, 같은 화면의 조직 판이 「3 부서」였다 — 관리자는 어느
    쪽을 믿을지 알 수 없고, 「내가 못 보는 부서가 둘 더 있다」는 사실 자체가 범위 밖이다.
    """
    login_as("admin", email=BOSS)
    row = client.get("/api/admin/organizations").json()["items"][0]
    tree = client.get("/api/admin/departments/tree").json()["items"]
    visible = [t for t in tree if t["kind"] == "department"]

    assert row["department_count"] == len(visible), (
        f"트리에는 {len(visible)}개인데 조직 판은 {row['department_count']}개라고 말한다"
    )
    assert row["department_count"] == 3, "서브트리(뿌리+자식 둘)만 세어야 한다"

    # 범위 밖 부서에 사람을 넣어도 이 관리자가 보는 인원은 늘지 않는다.
    before = row["user_count"]
    outsider = make_user("outsider-count@goodmit.co.kr", role="user", display_name="범위밖")
    outsider.department_id = subtree["outside"]
    db.commit()
    after = client.get("/api/admin/organizations").json()["items"][0]["user_count"]
    assert after == before, f"범위 밖 인원이 숫자로 샌다: {before} -> {after}"


def test_a_global_admin_still_gets_the_whole_organization_count(
    client, login_as, db, make_user, subtree
):
    """오탐 방지 — 전역 관리자에게는 조직 전체가 보여야 한다(그게 그 사람의 일이다)."""
    login_as("system_admin")
    row = client.get("/api/admin/organizations").json()["items"][0]
    assert row["department_count"] == 4, (
        f"범위를 걸면서 전역 관리자의 숫자까지 좁혔다: {row}"
    )

    before = row["user_count"]
    outsider = make_user("outsider-global@goodmit.co.kr", role="user", display_name="범위밖")
    outsider.department_id = subtree["outside"]
    db.commit()
    after = client.get("/api/admin/organizations").json()["items"][0]["user_count"]
    assert after == before + 1, f"전역 관리자가 새 사람을 못 센다: {before} -> {after}"
