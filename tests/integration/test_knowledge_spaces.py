"""지식 공간의 소유를 바꾸는 길 (org-05).

부서 삭제가 409 로 막을 때 관리자에게 시키는 조치가 바로 이것이다 — 「먼저 다른 부서로
옮기거나」. 그런데 그 조치의 한 갈래(소유를 조직으로 되돌리기)가 500 이었다.

원인은 `update_space` 가 **보낸 것과 안 보낸 것을 구별하지 않은 것**이다. `fields[key] is
not None` 인 것만 반영해서 `{"owner_kind": "organization", "owner_dept_id": null}` 의 뒤쪽
절반이 조용히 버려졌고, 「부서 소유가 아닌데 부서 id 는 남은」 행이 DB 의 짝 제약
(`ck_kspace_dept_pair`)에 부딪혀 원인이 안 적힌 500 이 났다.

그래서 이 파일은 세 가지를 본다: 되돌리기가 되는가, 짝이 안 맞는 요청이 422 로 답하는가,
그리고 그 정리를 끝낸 부서가 실제로 지워지는가(길이 끝까지 이어지는가).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


@pytest.fixture()
def admin_csrf(login_as):
    return login_as("admin")


@pytest.fixture()
def dept_space(client, admin_csrf):
    """부서 하나 + 그 부서가 소유한 공간 하나."""
    dept_id = client.post(
        "/api/admin/departments", json={"name": "자료팀"}, headers=_headers(admin_csrf)
    ).json()["department"]["id"]
    space = client.post(
        "/api/knowledge/spaces",
        json={
            "name": "자료팀 공간", "slug": "data-team-space",
            "owner_kind": "department", "owner_dept_id": dept_id,
        },
        headers=_headers(admin_csrf),
    )
    assert space.status_code == 200, space.text
    return {"dept_id": dept_id, "space_id": space.json()["id"]}


def test_giving_a_space_back_to_the_organization_clears_the_department(
    client, admin_csrf, dept_space
):
    """🔴 500 이었다 — 소유 종류만 바뀌고 부서 id 가 남아 DB 의 짝 제약이 깨졌다."""
    r = client.patch(
        f"/api/knowledge/spaces/{dept_space['space_id']}",
        json={"owner_kind": "organization", "owner_dept_id": None},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200, f"부서 삭제가 안내하는 조치가 막혀 있다: {r.text}"
    assert r.json()["owner_kind"] == "organization"
    assert r.json()["owner_dept_id"] is None, "소유는 조직인데 부서 id 가 남았다"


def test_the_partner_id_is_cleared_even_when_the_request_omits_it(
    client, admin_csrf, dept_space
):
    """`owner_kind` 만 보내도 짝이 되는 칸은 서비스가 정리한다.

    사용자가 「소유를 조직으로」라고 말한 뜻이 그것이고, 그 정리를 화면에 시키면 화면마다
    다르게 한다.
    """
    r = client.patch(
        f"/api/knowledge/spaces/{dept_space['space_id']}",
        json={"owner_kind": "organization"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200, r.text
    assert r.json()["owner_dept_id"] is None


def test_the_department_can_actually_be_deleted_after_the_space_is_handed_over(
    client, admin_csrf, dept_space
):
    """길이 끝까지 이어지는가 — 409 → 정리 → 삭제까지 한 번에 밟는다."""
    blocked = client.delete(
        f"/api/admin/departments/{dept_space['dept_id']}", headers=_headers(admin_csrf)
    )
    assert blocked.status_code == 409, blocked.text
    assert "지식 공간" in blocked.json()["error"]["message"]

    assert client.patch(
        f"/api/knowledge/spaces/{dept_space['space_id']}",
        json={"owner_kind": "organization", "owner_dept_id": None},
        headers=_headers(admin_csrf),
    ).status_code == 200

    r = client.delete(
        f"/api/admin/departments/{dept_space['dept_id']}", headers=_headers(admin_csrf)
    )
    assert r.status_code == 200, f"안내대로 정리했는데도 부서를 못 지운다: {r.text}"


def test_a_department_owned_space_without_a_department_is_refused_not_a_500(
    client, admin_csrf, dept_space
):
    """짝이 안 맞는 요청은 **422 로 이유를 말한다.** 5xx 는 사용자에게 아무 말도 안 한다."""
    r = client.patch(
        f"/api/knowledge/spaces/{dept_space['space_id']}",
        json={"owner_kind": "department", "owner_dept_id": None},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422, f"짝이 깨진 채 저장을 시도했다: {r.status_code} {r.text}"
    assert "부서" in r.json()["error"]["message"]


def test_an_unknown_department_is_refused_not_a_500(client, admin_csrf, dept_space):
    """없는 부서 id 를 그대로 저장하면 FK 가 500 을 낸다 — 그 500 에는 원인이 없다."""
    r = client.patch(
        f"/api/knowledge/spaces/{dept_space['space_id']}",
        json={"owner_kind": "department", "owner_dept_id": "no-such-dept"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422, f"{r.status_code} {r.text}"
    assert r.json()["error"]["message"] == "알 수 없는 부서입니다."


def test_moving_a_space_to_another_department_still_works(client, admin_csrf, dept_space):
    """오탐 방지 — 소유 종류를 유지한 채 부서만 옮기는 것은 예전 그대로다."""
    other_id = client.post(
        "/api/admin/departments", json={"name": "인프라팀"}, headers=_headers(admin_csrf)
    ).json()["department"]["id"]

    r = client.patch(
        f"/api/knowledge/spaces/{dept_space['space_id']}",
        json={"owner_dept_id": other_id},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200, r.text
    assert r.json()["owner_dept_id"] == other_id
    assert r.json()["owner_kind"] == "department", "종류를 안 보냈는데 종류가 바뀌었다"


def test_renaming_a_space_does_not_disturb_its_owner(client, admin_csrf, dept_space):
    """오탐 방지 — 이름만 고치는 흔한 저장이 소유를 건드리면 안 된다."""
    r = client.patch(
        f"/api/knowledge/spaces/{dept_space['space_id']}",
        json={"name": "자료팀 공간(개명)"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "자료팀 공간(개명)"
    assert r.json()["owner_dept_id"] == dept_space["dept_id"]


def test_an_explicit_null_owner_kind_is_refused(client, admin_csrf, dept_space):
    """소유 종류는 **비울 수 있는 칸이 아니다.**

    「보낸 것은 null 이어도 반영한다」로 바꾸면서 이 칸이 함께 딸려 왔다 — `owner_kind` 는
    NOT NULL 이라 그대로 flush 하면 원인이 안 적힌 500 이고, 그것은 이 변경이 없애려던
    바로 그 500 이다. 소유를 없앤다는 뜻은 `unset` 이라는 값으로 말한다.
    """
    r = client.patch(
        f"/api/knowledge/spaces/{dept_space['space_id']}",
        json={"owner_kind": None},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422, f"NOT NULL 칸에 null 을 그대로 저장했다: {r.status_code} {r.text}"
    got = client.get(
        f"/api/knowledge/spaces/{dept_space['space_id']}", headers=_headers(admin_csrf)
    ).json()
    assert got["owner_kind"] == "department", "거절해 놓고 소유를 건드렸다"


def test_owner_can_be_handed_over_to_nobody_with_the_unset_value(
    client, admin_csrf, dept_space
):
    """오탐 방지 — 「소유 없음」을 말하는 길은 막지 않는다(`unset` 이 그 값이다)."""
    r = client.patch(
        f"/api/knowledge/spaces/{dept_space['space_id']}",
        json={"owner_kind": "unset"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200, r.text
    assert r.json()["owner_kind"] == "unset"
    assert r.json()["owner_dept_id"] is None, "소유가 없는데 부서 id 가 남았다"


# ── 만드는 길도 같은 문을 지난다 (R4-02) ──────────────────────────────────────
#
# 짝 맞추기(`_settle_owner_pair`)를 수정에만 걸어 두면, 같은 제약을 같은 모양으로 어기는
# 생성이 그대로 500 을 낸다. 제약은 하나이므로 문도 하나다 (CLAUDE.md §5).


def test_creating_a_department_owned_space_without_a_department_is_refused_not_a_500(
    client, admin_csrf
):
    """짝이 안 맞는 **생성**도 422 로 이유를 말한다. 5xx 는 사용자에게 아무 말도 안 한다."""
    r = client.post(
        "/api/knowledge/spaces",
        json={"name": "짝 없는 공간", "slug": "pairless-space", "owner_kind": "department"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422, f"짝이 깨진 채 저장을 시도했다: {r.status_code} {r.text}"
    assert "부서" in r.json()["error"]["message"]


def test_creating_a_project_owned_space_without_a_project_is_refused_not_a_500(
    client, admin_csrf
):
    """프로젝트 갈래도 같다 — 같은 제약이 같은 모양으로 깨진다."""
    r = client.post(
        "/api/knowledge/spaces",
        json={"name": "짝 없는 공간", "slug": "pairless-project", "owner_kind": "project"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422, f"{r.status_code} {r.text}"
    assert "프로젝트" in r.json()["error"]["message"]


def test_creating_a_space_with_an_unknown_department_is_refused_not_a_500(
    client, admin_csrf
):
    """없는 부서 id 는 FK 에서 500 이 된다 — 그 500 에는 원인이 없다."""
    r = client.post(
        "/api/knowledge/spaces",
        json={"name": "없는 부서 공간", "slug": "ghost-dept-space",
              "owner_kind": "department", "owner_dept_id": "no-such-dept"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422, f"{r.status_code} {r.text}"
    assert r.json()["error"]["message"] == "알 수 없는 부서입니다."


def test_creating_an_organization_owned_space_still_works(client, admin_csrf, dept_space):
    """오탐 방지 — 짝이 필요 없는 갈래의 생성은 예전 그대로다.

    그리고 짝이 필요 없는 갈래에 부서 id 를 얹어 보내면 서비스가 그것을 정리한다
    (수정 경로가 하는 것과 같다).
    """
    r = client.post(
        "/api/knowledge/spaces",
        json={"name": "조직 공통 공간", "slug": "org-common-space",
              "owner_kind": "organization", "owner_dept_id": dept_space["dept_id"]},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200, r.text
    assert r.json()["owner_kind"] == "organization"
    assert r.json()["owner_dept_id"] is None, "조직 소유인데 부서 id 가 남았다"


def test_creating_a_department_owned_space_with_its_department_still_works(
    client, admin_csrf, dept_space
):
    """오탐 방지 — 짝이 맞는 생성은 그대로 200 이다(막기만 하면 전부 422 로도 초록이 된다)."""
    r = client.post(
        "/api/knowledge/spaces",
        json={"name": "자료팀 두번째 공간", "slug": "data-team-second",
              "owner_kind": "department", "owner_dept_id": dept_space["dept_id"]},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200, r.text
    assert r.json()["owner_dept_id"] == dept_space["dept_id"]


def test_an_explicit_null_name_is_refused(client, admin_csrf, dept_space):
    """비울 수 없는 칸에 `null` 이 오면 거절한다.

    조용히 버리면 화면은 「저장했습니다」를 띄우고 값은 그대로다 — 사용자가 보는 것과
    저장된 것이 다르다.
    """
    r = client.patch(
        f"/api/knowledge/spaces/{dept_space['space_id']}",
        json={"name": None},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422, f"{r.status_code} {r.text}"
    got = client.get(
        f"/api/knowledge/spaces/{dept_space['space_id']}", headers=_headers(admin_csrf)
    ).json()
    assert got["name"] == "자료팀 공간", "거절해 놓고 이름을 건드렸다"
