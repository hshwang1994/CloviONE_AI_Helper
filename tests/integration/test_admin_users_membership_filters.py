"""사용자 목록의 조직 필터 넷과 조직 트리의 수 (계획 3.6, D-510, BACKLOG P-104).

조직 관리 화면의 구성원 목록은 8명 미리보기였다. 사용자 목록 API 가 조직으로도, 하위 부서까지로도,
소속 종류로도 거를 수 없었기 때문이다. 못박는 것:

  * `include_descendants` 는 자기와 그 아래 부서의 사람이다(조상은 아니다).
  * `membership_kind` 는 부서 · 조직 직속 · 미지정을 가른다. 미지정은 정합성 화면과 같은 정의다.
  * `org_id` 는 범위 밖 조직을 없는 조직과 같은 422 로 답한다.
  * `state` 는 활성 · 비활성 · 보관을 가르고 옛 `archived=true` 와 같이 동작한다.
  * CSV 내보내기는 같은 문장이다.
  * 트리의 수는 지금 일하는 사람만 세고, 조직 줄은 조직 직속과 미지정을 따로 센다.
"""

from __future__ import annotations

import pytest

from app.core.models_base import utcnow
from app.org.constants import DEFAULT_ORG_ID
from app.org.models import Department
from app.users.models import ADMIN_SCOPE_ORG, MEMBERSHIP_UNASSIGNED

pytestmark = pytest.mark.integration


@pytest.fixture()
def people(db, make_user):
    hq = Department(id="m-hq", name="필터 본부", org_id=DEFAULT_ORG_ID)
    dev = Department(id="m-dev", name="필터 개발팀", org_id=DEFAULT_ORG_ID, parent_id="m-hq")
    fe = Department(id="m-fe", name="필터 프런트팀", org_id=DEFAULT_ORG_ID, parent_id="m-dev")
    db.add_all([hq, dev, fe])
    db.commit()

    def person(email, name, dept=None, membership="department", **kw):
        user = make_user(email=email, display_name=name, membership=membership if not dept else "department", **kw)
        user.department_id = dept
        user.org_id = DEFAULT_ORG_ID
        return user

    rows = {
        "hq": person("m-hq@goodmit.co.kr", "본부 사람", "m-hq"),
        "dev": person("m-dev@goodmit.co.kr", "개발 사람", "m-dev"),
        "fe": person("m-fe@goodmit.co.kr", "프런트 사람", "m-fe"),
        "direct": person("m-direct@goodmit.co.kr", "직속 사람", membership="organization"),
        "none": person("m-none@goodmit.co.kr", "미지정 사람", membership=MEMBERSHIP_UNASSIGNED),
        "off": person("m-off@goodmit.co.kr", "비활성 사람", "m-dev", active=False),
        "gone": person("m-gone@goodmit.co.kr", "보관 사람", "m-dev"),
    }
    rows["gone"].archived_at = utcnow()
    db.commit()
    return {k: v.id for k, v in rows.items()}


def _names(client, **params):
    r = client.get("/api/admin/users", params={"page_size": 100, **params})
    assert r.status_code == 200, r.text
    return {u["display_name"] for u in r.json()["items"]}


def test_descendants_are_the_branch_below_not_above(client, login_as, people):
    login_as("system_admin")
    assert _names(client, department_id="m-dev", state="active") == {"개발 사람"}
    assert _names(client, department_id="m-dev", include_descendants="true", state="active") == {"개발 사람", "프런트 사람"}
    assert _names(client, department_id="m-hq", include_descendants="true", state="active") == {
        "본부 사람", "개발 사람", "프런트 사람",
    }
    # 상태를 안 주면 옛 목록 그대로 비활성 계정도 담긴다(보관 계정은 빠진다).
    assert _names(client, department_id="m-dev") == {"개발 사람", "비활성 사람"}


def test_membership_kind_splits_direct_from_unassigned(client, login_as, people):
    login_as("system_admin")
    assert "직속 사람" in _names(client, membership_kind="organization")
    assert "미지정 사람" not in _names(client, membership_kind="organization")
    unassigned = _names(client, membership_kind="unassigned")
    assert "미지정 사람" in unassigned and "직속 사람" not in unassigned
    assert "본부 사람" in _names(client, membership_kind="department")
    r = client.get("/api/admin/users", params={"membership_kind": "nobody"})
    assert r.status_code == 422


def test_state_filter_and_the_old_archived_flag_agree(client, login_as, people):
    login_as("system_admin")
    assert "비활성 사람" in _names(client, state="inactive")
    assert "비활성 사람" not in _names(client, state="active")
    assert _names(client, state="archived") == _names(client, archived="true") == {"보관 사람"}
    assert client.get("/api/admin/users", params={"state": "deleted"}).status_code == 422


def test_org_filter_refuses_an_org_outside_the_scope(client, db, login_as, make_user, two_orgs):
    login_as("system_admin")
    assert "B사람" in _names(client, org_id=two_orgs.org_b_id)
    assert "B사람" not in _names(client, org_id=two_orgs.org_a_id)
    assert client.get("/api/admin/users", params={"org_id": "no-such-org"}).status_code == 422

    scoped = make_user(email="org-scoped@goodmit.co.kr", role="admin", display_name="조직 관리자")
    scoped.org_id = DEFAULT_ORG_ID
    scoped.admin_scope = ADMIN_SCOPE_ORG
    scoped.scope_org_id = DEFAULT_ORG_ID
    db.commit()
    login_as("admin", email="org-scoped@goodmit.co.kr")
    r = client.get("/api/admin/users", params={"org_id": two_orgs.org_b_id})
    assert r.status_code == 422, "범위 밖 조직을 있는 것처럼 답했다"


def test_csv_export_uses_the_same_filters(client, login_as, people):
    csrf = login_as("system_admin")
    r = client.get("/api/admin/users/export/csv", params={"department_id": "m-hq", "include_descendants": "true"},
                   headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    body = r.content.decode("utf-8-sig")
    assert "m-fe@goodmit.co.kr" in body and "m-direct@goodmit.co.kr" not in body


def test_the_tree_counts_working_people_and_splits_the_org_row(client, login_as, people):
    login_as("system_admin")
    rows = {r["id"]: r for r in client.get("/api/admin/departments/tree").json()["items"]}
    assert rows["m-dev"]["user_count"] == 1, "비활성 · 보관 계정까지 셌다"
    assert rows["m-hq"]["subtree_user_count"] == 3
    org = rows[DEFAULT_ORG_ID]
    assert org["unassigned_count"] >= 1
    assert org["organization_direct_count"] >= 1
    assert org["user_count"] == org["organization_direct_count"], "조직 직속과 미지정을 한 수로 셌다"
