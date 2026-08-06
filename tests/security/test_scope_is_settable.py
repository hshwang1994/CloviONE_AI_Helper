"""관리 범위(`admin_scope`)를 **제품의 API 로** 설정할 수 있다 (F2 / T3).

## 왜 이 파일이 필요한가

저장소에 범위(scope) 보안 테스트가 넷 있고 전부 초록이다. 그런데 그 넷은 모두 이렇게 시작한다:

    user.admin_scope = scope        # tests/security/test_scope_idor_matrix.py 등

**제품에는 이 값을 넣는 길이 없다.** 스키마·라우터·화면 어디에도 `admin_scope` 가 없고,
모델과 `app/core/scope.py`(읽는 쪽)만 있다. 그래서 그 네 파일은 `scope.py` 의 **읽기 쪽을
훌륭하게 증명하면서, 쓰기 쪽이 존재하지 않는다는 사실을 정확히 그 대입문으로 가린다.**

결과: **부서 관리자가 존재할 수 없는데 부서 관리자 IDOR 매트릭스가 100% 초록이다.**
그리고 `test_migration_0024_org_scope.py` 는 그 상태를
`test_admin_scope_defaults_to_global_so_existing_admins_keep_working` 라는 이름으로
**정답처럼 못박아 놓았다.**

이 테스트는 그 구멍 하나만 본다: 관리자가 화면/API 로 다른 관리자의 범위를 실제로 좁힐 수
있는가. 통과하면 나머지 네 파일이 비로소 무언가를 증명하게 된다.

## 누가 바꿀 수 있는가

역할 변경과 **같은 급**이다 — 범위를 넓히는 것은 권한을 주는 일이다. 그래서 역할 변경과
같은 게이트를 지난다(`system_admin` 만, 그리고 승인 경로가 있으면 그쪽으로).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.security


def _scope_of(app, user_id):
    from app.users.models import User

    with app.state.session_factory() as db:
        u = db.get(User, user_id)
        return (u.admin_scope, u.scope_org_id, u.scope_dept_id)


def test_a_department_admin_can_actually_be_created(client, login_as, make_user, app, db):
    """부서 관리자를 **만들 수 있어야** 한다 — 지금은 만들 방법이 UI·API 에 전무하다."""
    # 부서를 직접 만든다. 마이그레이션 0038 은 `ClovirONE팀` 이 이미 있는 환경에서만
    # 손대도록 일부러 만들어져 있어(없는 조직 구조를 지어내지 않는다) 새 DB 에는 부서가 없다.
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    dept = Department(name="범위검사팀", org_id=DEFAULT_ORG_ID)
    db.add(dept)
    db.commit()

    target = make_user("deptadmin@goodmit.co.kr", role="admin")
    csrf = login_as("system_admin")

    r = client.patch(
        f"/api/admin/users/{target.id}",
        json={"admin_scope": "dept", "scope_dept_id": dept.id},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code in (200, 202), f"범위를 설정할 수 없다: {r.status_code} {r.text[:200]}"
    if r.status_code == 200:
        assert _scope_of(app, target.id) == ("dept", None, dept.id)


def test_the_scope_comes_back_in_the_user_payload(client, login_as, make_user):
    """화면이 지금 값을 보여 줄 수 있어야 한다 — 설정만 되고 안 보이면 확인이 불가능하다."""
    target = make_user("scopeview@goodmit.co.kr", role="admin")
    login_as("system_admin")

    body = client.get(f"/api/admin/users/{target.id}").json()
    row = body.get("user", body)
    assert "admin_scope" in row, f"사용자 payload 에 범위가 없다: {sorted(row)[:15]}"


def test_an_unknown_scope_value_is_refused(client, login_as, make_user):
    """`scope.py` 는 모르는 값을 만나면 `MATCH_NOTHING` 으로 떨어진다 — 즉 오타 하나가
    그 관리자의 화면을 통째로 비운다. 경계에서 거른다."""
    target = make_user("scopebad@goodmit.co.kr", role="admin")
    csrf = login_as("system_admin")

    r = client.patch(
        f"/api/admin/users/{target.id}",
        json={"admin_scope": "galaxy"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 422, f"모르는 범위 값이 통과했다: {r.status_code}"


def test_a_dept_scope_without_a_department_is_refused(client, login_as, make_user):
    """`dept` 인데 대상 부서가 없으면 그 관리자는 **아무것도 못 보는 계정**이 된다.
    설정하는 쪽에서 막지 않으면 나중에 '화면이 비어요' 로만 나타난다."""
    target = make_user("scopehalf@goodmit.co.kr", role="admin")
    csrf = login_as("system_admin")

    r = client.patch(
        f"/api/admin/users/{target.id}",
        json={"admin_scope": "dept"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 422, f"대상 없는 dept 범위가 통과했다: {r.status_code}"


def test_a_scope_set_through_the_api_actually_narrows_what_that_admin_sees(
    client, login_as, make_user, db
):
    """**쓰기와 읽기를 잇는다.**

    `app/core/scope.py` 의 읽기 쪽은 기존 테스트 넷이 이미 증명했다 — 다만 그 넷은 값을
    손으로 대입해서 넣었다. 이제 **제품 경로로 넣은 값**이 같은 결과를 내는지 본다.
    이게 통과해야 비로소 그 넷이 무언가를 증명하는 테스트가 된다.
    """
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.commit()

    inside = make_user("inside@goodmit.co.kr", role="user")
    outside = make_user("outside@goodmit.co.kr", role="user")
    scoped = make_user("scoped-admin@goodmit.co.kr", role="admin")
    for u, dept in ((inside, mine), (outside, theirs), (scoped, mine)):
        u.department_id = dept.id
    db.commit()

    csrf = login_as("system_admin")
    r = client.patch(
        f"/api/admin/users/{scoped.id}",
        json={"admin_scope": "dept", "scope_dept_id": mine.id},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text

    # 그 관리자로 로그인해 사용자 목록을 본다.
    login_as("admin", email="scoped-admin@goodmit.co.kr")
    emails = {row["email"] for row in client.get("/api/admin/users").json()["items"]}

    assert "inside@goodmit.co.kr" in emails, "자기 부서 사람이 안 보인다 — 범위가 너무 좁다"
    assert "outside@goodmit.co.kr" not in emails, (
        "남의 부서 사람이 보인다 — 제품 경로로 넣은 범위가 읽기에 걸리지 않는다"
    )


def test_the_scope_shows_up_in_my_own_profile_payload(client, login_as, make_user, db):
    """화면이 스코프 바를 그리려면 `/api/me` 가 그 값을 줘야 한다 (S4 / A8).

    범위를 걸어 목록이 좁아지는데 **왜 좁아졌는지 화면이 말하지 않으면** 사용자는
    "왜 이것만 보이지" 를 알 수 없고, 그건 결함으로 신고된다.
    """
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    dept = Department(name="범위표시팀", org_id=DEFAULT_ORG_ID)
    db.add(dept)
    db.commit()

    target = make_user("scopeme@goodmit.co.kr", role="admin")
    csrf = login_as("system_admin")
    client.patch(f"/api/admin/users/{target.id}",
                 json={"admin_scope": "dept", "scope_dept_id": dept.id},
                 headers={"X-CSRF-Token": csrf})

    login_as("admin", email="scopeme@goodmit.co.kr")
    me = client.get("/api/me").json()["user"]

    assert me.get("admin_scope") == "dept", f"/api/me 가 범위를 안 준다: {sorted(me)}"
    assert me.get("scope_dept_id") == dept.id
