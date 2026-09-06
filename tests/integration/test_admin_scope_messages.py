"""관리 범위 거절 문구는 **화면의 어휘**로 말한다 (R5-07).

사용자 관리 화면의 관리 범위 선택지는 「전체」·「조직」·「부서」다(권한 매트릭스가 쓰는
`app/core/authz.py::SCOPE_LABELS` 가 그 이름의 정본이고, 화면의 드롭다운도 같은 어휘를
쓴다). 그런데 저장을 거절하는 문장은 `admin_scope` 컬럼 값을 그대로 실어
「관리 범위가 'global' 이면 …」 이라고 답했다 — 고른 사람은 그 영문 토큰을 어디서도 본
적이 없다. 서버가 화면 이름을 안 쓰면 사람은 두 어휘를 스스로 이어야 한다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture()
def admin_csrf(login_as):
    return login_as("system_admin")


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


def _message(response) -> str:
    return response.json()["error"]["message"]


def test_the_scope_refusal_names_the_scope_the_screen_names(client, admin_csrf, make_user):
    target = make_user("scope-copy-org@goodmit.co.kr", role="admin")

    r = client.patch(
        f"/api/admin/users/{target.id}",
        json={
            "admin_scope": "global",
            "scope_org_id": "00000000-0000-4000-8000-00000000dead",
        },
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422, r.text
    message = _message(r)
    assert "전체" in message, message
    assert "global" not in message, f"내부 값이 사용자 문장에 실렸다: {message!r}"
    assert message.endswith("."), f"완결된 문장이 아니다: {message!r}"


def test_the_dept_refusal_says_the_same_thing(client, admin_csrf, make_user):
    dept = client.post(
        "/api/admin/departments", json={"name": "문구검사팀"}, headers=_headers(admin_csrf)
    )
    assert dept.status_code == 201, dept.text
    target = make_user("scope-copy-dept@goodmit.co.kr", role="admin")

    r = client.patch(
        f"/api/admin/users/{target.id}",
        json={"admin_scope": "org", "scope_dept_id": dept.json()["department"]["id"]},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422, r.text
    message = _message(r)
    assert "조직" in message and "대상 부서" in message, message
    assert "org" not in message, f"내부 값이 사용자 문장에 실렸다: {message!r}"


def test_an_unknown_scope_lists_the_choices_in_korean(client, admin_csrf, make_user):
    target = make_user("scope-copy-unknown@goodmit.co.kr", role="admin")

    r = client.patch(
        f"/api/admin/users/{target.id}",
        json={"admin_scope": "globl"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422, r.text
    message = _message(r)
    for label in ("전체", "조직", "부서"):
        assert label in message, message
    for token in ("global", "org", "dept"):
        assert token not in message, f"고를 수 있는 값을 영문 키로 나열했다: {message!r}"


def test_a_scope_change_that_makes_sense_still_saves(client, admin_csrf, make_user):
    """반례 — 문구만 고쳤다. 짝이 맞는 요청은 그대로 저장된다."""
    dept = client.post(
        "/api/admin/departments", json={"name": "정상저장팀"}, headers=_headers(admin_csrf)
    )
    dept_id = dept.json()["department"]["id"]
    target = make_user("scope-copy-ok@goodmit.co.kr", role="admin")

    r = client.patch(
        f"/api/admin/users/{target.id}",
        json={"admin_scope": "dept", "scope_dept_id": dept_id},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200, r.text
    assert r.json()["user"]["admin_scope"] == "dept"
