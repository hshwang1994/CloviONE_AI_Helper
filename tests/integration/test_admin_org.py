"""부서·직책 목록 관리.

지금까지 users.department/title은 자유 입력 문자열이었다 — 'ClovirONE팀'과
'ClovirOne팀'이 서로 다른 부서가 되고, 부서 이름이 바뀌면 전 직원의 행을 하나씩
고쳐야 했다. 목록을 따로 두고 FK로 참조하면 "한 곳만 고치면 전원에 반영"이 성립한다.
그 약속이 실제로 지켜지는지가 이 파일의 핵심(test_rename_*)이다.
"""

import pytest

pytestmark = pytest.mark.integration


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


@pytest.fixture()
def admin_csrf(login_as):
    return login_as("admin")


def _mk_dept(client, csrf, name="ClovirONE팀"):
    return client.post("/api/admin/departments", json={"name": name}, headers=_headers(csrf))


def _mk_title(client, csrf, name="팀장"):
    return client.post("/api/admin/job-titles", json={"name": name}, headers=_headers(csrf))


# --------------------------------------------------------------- 부서 CRUD

def test_create_and_list_department(client, admin_csrf):
    r = _mk_dept(client, admin_csrf)
    assert r.status_code == 201, r.text
    assert r.json()["department"]["name"] == "ClovirONE팀"
    assert r.json()["department"]["active"] is True

    r = client.get("/api/admin/departments", headers=_headers(admin_csrf))
    assert [d["name"] for d in r.json()["items"]] == ["ClovirONE팀"]


def test_duplicate_department_name_rejected(client, admin_csrf):
    """이름이 유일하지 않으면 목록을 만든 의미가 없다 — 같은 부서가 둘이 된다."""
    assert _mk_dept(client, admin_csrf).status_code == 201
    r = _mk_dept(client, admin_csrf)
    assert r.status_code == 409, r.text


def test_duplicate_department_name_rejected_ignoring_whitespace(client, admin_csrf):
    assert _mk_dept(client, admin_csrf, name="영업팀").status_code == 201
    r = _mk_dept(client, admin_csrf, name="  영업팀  ")
    assert r.status_code == 409, r.text


def test_blank_department_name_rejected(client, admin_csrf):
    r = _mk_dept(client, admin_csrf, name="   ")
    assert r.status_code == 422


def test_rename_department_reflects_on_every_user(client, admin_csrf):
    """사용자가 원한 바로 그것 — 부서명을 한 곳에서 고치면 전원에 반영된다."""
    dept_id = _mk_dept(client, admin_csrf).json()["department"]["id"]
    for i in range(3):
        r = client.post(
            "/api/admin/users",
            json={
                "email": f"member{i}@goodmit.co.kr", "display_name": f"팀원{i}",
                "role": "user", "department_id": dept_id,
            },
            headers=_headers(admin_csrf),
        )
        assert r.status_code == 201, r.text

    r = client.patch(
        f"/api/admin/departments/{dept_id}",
        json={"name": "클로비원팀"}, headers=_headers(admin_csrf),
    )
    assert r.status_code == 200, r.text

    r = client.get("/api/admin/users", params={"q": "member"}, headers=_headers(admin_csrf))
    depts = [u["department"] for u in r.json()["items"]]
    assert depts == ["클로비원팀"] * 3, f"한 곳을 고쳤는데 전원에 반영되지 않았다: {depts}"


def test_rename_title_reflects_on_every_user(client, admin_csrf):
    title_id = _mk_title(client, admin_csrf).json()["job_title"]["id"]
    r = client.post(
        "/api/admin/users",
        json={
            "email": "lead@goodmit.co.kr", "display_name": "리더",
            "role": "user", "title_id": title_id,
        },
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 201, r.text

    client.patch(
        f"/api/admin/job-titles/{title_id}", json={"name": "파트장"}, headers=_headers(admin_csrf)
    )
    r = client.get("/api/admin/users", params={"q": "lead@"}, headers=_headers(admin_csrf))
    assert r.json()["items"][0]["title"] == "파트장"


def test_list_reports_user_count(client, admin_csrf):
    dept_id = _mk_dept(client, admin_csrf).json()["department"]["id"]
    client.post(
        "/api/admin/users",
        json={"email": "counted@goodmit.co.kr", "display_name": "한명",
              "role": "user", "department_id": dept_id},
        headers=_headers(admin_csrf),
    )
    r = client.get("/api/admin/departments", headers=_headers(admin_csrf))
    assert r.json()["items"][0]["user_count"] == 1


# ── UA-20R: 삭제 확인이 하위 부서 수도 말해야 한다 ─────────────────────────────
#
# parent_id는 ondelete="SET NULL"이라(모델 주석) 부모를 지워도 자식은 안 지워지고
# 최상위로 올라온다 — 데이터 유실은 아니지만, 3단 트리가 클릭 한 번에 평탄해지는 것을
# 관리자가 지우기 전에 알아야 한다. 예전 확인 문구는 인원수만 말하고 자식 부서 수는
# 전혀 말하지 않았다.

def test_list_reports_child_department_count(client, admin_csrf):
    parent_id = _mk_dept(client, admin_csrf, name="본부").json()["department"]["id"]
    for name in ("개발팀", "운영팀"):
        r = client.post(
            "/api/admin/departments",
            json={"name": name, "parent_id": parent_id},
            headers=_headers(admin_csrf),
        )
        assert r.status_code == 201, r.text

    r = client.get("/api/admin/departments", headers=_headers(admin_csrf))
    by_name = {d["name"]: d for d in r.json()["items"]}
    assert by_name["본부"]["child_department_count"] == 2
    assert by_name["개발팀"]["child_department_count"] == 0, "자식이 없는 부서는 0이어야 한다"


def test_get_single_department_reports_child_department_count(client, admin_csrf):
    parent_id = _mk_dept(client, admin_csrf, name="본부2").json()["department"]["id"]
    client.post(
        "/api/admin/departments",
        json={"name": "하위팀", "parent_id": parent_id},
        headers=_headers(admin_csrf),
    )
    r = client.get(f"/api/admin/departments/{parent_id}", headers=_headers(admin_csrf))
    assert r.json()["department"]["child_department_count"] == 1


def test_job_titles_do_not_carry_child_department_count(client, admin_csrf):
    """직책엔 트리가 없다 — 이 필드가 새는 것 자체가 '직책도 계층이 있나?' 하는 오해를 만든다."""
    _mk_title(client, admin_csrf)
    r = client.get("/api/admin/job-titles", headers=_headers(admin_csrf))
    assert "child_department_count" not in r.json()["items"][0]


def test_deleting_a_parent_department_is_refused_while_children_exist(client, admin_csrf):
    """하위 부서가 있으면 **지울 수 없다** (0060 §33).

    예전에는 지워졌고, `ondelete="SET NULL"` 덕에 자식은 사라지지 않고 최상위로 올라왔다 —
    데이터는 안 잃지만 3단 조직도가 클릭 한 번에 평탄해졌다. 0060 에서 부서는 조회 범위의
    축(줄기 = 조상 ∪ 자기 ∪ 후손)이 됐다: 부모가 사라지면 그 아래 사람들이 보던 상위 부서
    공통 업무가 통째로 사라지고, 반대로 자식이 최상위가 되면서 **같은 조직의 다른 최상위
    부서와 나란히** 놓인다. 어느 쪽도 오류를 내지 않는다.

    그래서 확인 문구로 알리는 대신 막는다. 되돌릴 수 없는 권한 변화를 "정말 지울까요?"
    한 줄로 위임하지 않는다.
    """
    parent_id = _mk_dept(client, admin_csrf, name="본부3").json()["department"]["id"]
    child_id = client.post(
        "/api/admin/departments",
        json={"name": "하위팀3", "parent_id": parent_id},
        headers=_headers(admin_csrf),
    ).json()["department"]["id"]

    r = client.delete(f"/api/admin/departments/{parent_id}", headers=_headers(admin_csrf))
    assert r.status_code == 409, r.text
    err = r.json()["error"]
    assert err["details"]["child_departments"] == 1
    assert "하위 부서" in err["message"], f"무엇 때문에 막혔는지 말하지 않는다: {err['message']}"

    # 막는 것으로 끝나면 안 된다 — 자식을 먼저 옮기면 지울 수 있어야 한다.
    client.patch(
        f"/api/admin/departments/{child_id}", json={"parent_id": None},
        headers=_headers(admin_csrf),
    )
    r = client.delete(f"/api/admin/departments/{parent_id}", headers=_headers(admin_csrf))
    assert r.status_code == 200, f"자식을 옮겼는데도 못 지운다: {r.text}"
    assert client.get(
        f"/api/admin/departments/{child_id}", headers=_headers(admin_csrf)
    ).status_code == 200, "자식 부서까지 함께 지워졌다 — 데이터 유실"


def test_delete_unused_department_succeeds(client, admin_csrf):
    dept_id = _mk_dept(client, admin_csrf, name="없어질팀").json()["department"]["id"]
    r = client.delete(f"/api/admin/departments/{dept_id}", headers=_headers(admin_csrf))
    assert r.status_code == 200, r.text
    assert client.get("/api/admin/departments", headers=_headers(admin_csrf)).json()["items"] == []


def test_delete_department_in_use_is_refused_and_says_how_many(client, admin_csrf):
    """조용히 실패하거나 남의 부서를 지워 버리면 안 된다 — 몇 명이 쓰는지 알려 준다."""
    dept_id = _mk_dept(client, admin_csrf).json()["department"]["id"]
    for i in range(2):
        client.post(
            "/api/admin/users",
            json={"email": f"user{i}@goodmit.co.kr", "display_name": f"직원{i}",
                  "role": "user", "department_id": dept_id},
            headers=_headers(admin_csrf),
        )

    r = client.delete(f"/api/admin/departments/{dept_id}", headers=_headers(admin_csrf))
    assert r.status_code == 409, r.text
    err = r.json()["error"]
    assert "2" in err["message"], f"몇 명이 쓰는지 알려 주지 않는다: {err['message']}"
    assert err["details"]["user_count"] == 2
    # 대안을 알려 준다 — 막기만 하면 사용자는 다음에 뭘 해야 할지 모른다.
    assert "비활성" in err["message"]

    # 그리고 실제로 아무도 잃지 않았다.
    r = client.get("/api/admin/users", params={"q": "user0@"}, headers=_headers(admin_csrf))
    assert r.json()["items"][0]["department"] == "ClovirONE팀"


def test_delete_department_counts_archived_users_too(client, admin_csrf):
    """보관된 사용자도 그 부서를 쥐고 있다 — 안 세면 FK가 가리키는 행을 지우게 된다."""
    dept_id = _mk_dept(client, admin_csrf).json()["department"]["id"]
    uid = client.post(
        "/api/admin/users",
        json={"email": "hidden@goodmit.co.kr", "display_name": "보관될 사람",
              "role": "user", "department_id": dept_id},
        headers=_headers(admin_csrf),
    ).json()["user"]["id"]
    client.post(f"/api/admin/users/{uid}/archive", headers=_headers(admin_csrf))

    r = client.delete(f"/api/admin/departments/{dept_id}", headers=_headers(admin_csrf))
    assert r.status_code == 409, "보관된 사용자가 쓰는 부서를 지워 버렸다"


def test_deactivate_department_keeps_existing_users(client, admin_csrf):
    """쓰는 사람이 있으면 '비활성'이 정답 — 새로 고를 수는 없지만 기존은 그대로다."""
    dept_id = _mk_dept(client, admin_csrf).json()["department"]["id"]
    client.post(
        "/api/admin/users",
        json={"email": "keeper@goodmit.co.kr", "display_name": "유지",
              "role": "user", "department_id": dept_id},
        headers=_headers(admin_csrf),
    )
    r = client.patch(
        f"/api/admin/departments/{dept_id}", json={"active": False}, headers=_headers(admin_csrf)
    )
    assert r.status_code == 200, r.text

    r = client.get("/api/admin/users", params={"q": "keeper@"}, headers=_headers(admin_csrf))
    assert r.json()["items"][0]["department"] == "ClovirONE팀", "기존 사용자의 부서가 사라졌다"

    # 새로 고를 수 있는 목록에서는 빠진다.
    r = client.get("/api/admin/departments", params={"active": "true"}, headers=_headers(admin_csrf))
    assert r.json()["items"] == []


def test_cannot_assign_inactive_department_to_user(client, admin_csrf):
    """비활성 부서를 새로 고를 수 있으면 '비활성'이 아무 뜻도 없다."""
    dept_id = _mk_dept(client, admin_csrf).json()["department"]["id"]
    client.patch(
        f"/api/admin/departments/{dept_id}", json={"active": False}, headers=_headers(admin_csrf)
    )
    r = client.post(
        "/api/admin/users",
        json={"email": "nope@goodmit.co.kr", "display_name": "안됨",
              "role": "user", "department_id": dept_id},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422, r.text


def test_unknown_department_id_rejected(client, admin_csrf):
    r = client.post(
        "/api/admin/users",
        json={"email": "ghost@goodmit.co.kr", "display_name": "유령",
              "role": "user", "department_id": "no-such-dept"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422, r.text


def test_user_response_carries_ids_and_names(client, admin_csrf):
    """이름이 나가야 표에 보이고, id가 나가야 수정 폼이 지금 값을 고를 수 있다."""
    dept_id = _mk_dept(client, admin_csrf).json()["department"]["id"]
    title_id = _mk_title(client, admin_csrf).json()["job_title"]["id"]
    body = client.post(
        "/api/admin/users",
        json={"email": "full@goodmit.co.kr", "display_name": "전체",
              "role": "user", "department_id": dept_id, "title_id": title_id},
        headers=_headers(admin_csrf),
    ).json()["user"]
    assert body["department"] == "ClovirONE팀"
    assert body["title"] == "팀장"
    assert body["department_id"] == dept_id
    assert body["title_id"] == title_id


def test_patch_user_can_clear_department(client, admin_csrf):
    dept_id = _mk_dept(client, admin_csrf).json()["department"]["id"]
    uid = client.post(
        "/api/admin/users",
        json={"email": "clearme@goodmit.co.kr", "display_name": "지움",
              "role": "user", "department_id": dept_id},
        headers=_headers(admin_csrf),
    ).json()["user"]["id"]

    r = client.patch(
        f"/api/admin/users/{uid}", json={"department_id": None}, headers=_headers(admin_csrf)
    )
    assert r.status_code == 200, r.text
    assert r.json()["user"]["department"] is None


def test_profile_shows_department_name(client, admin_csrf, login_as):
    """/api/me와 /api/profile도 이름을 보여 줘야 한다 — id만 나가면 사람이 못 읽는다."""
    dept_id = _mk_dept(client, admin_csrf, name="지원팀").json()["department"]["id"]
    r = client.get("/api/admin/users", params={"q": "admin@"}, headers=_headers(admin_csrf))
    uid = r.json()["items"][0]["id"]
    client.patch(
        f"/api/admin/users/{uid}", json={"department_id": dept_id}, headers=_headers(admin_csrf)
    )
    assert client.get("/api/me").json()["user"]["department"] == "지원팀"
    assert client.get("/api/profile").json()["department"] == "지원팀"


# --------------------------------------------------------------- 권한 / 감사

@pytest.mark.parametrize("path", ["/api/admin/departments", "/api/admin/job-titles"])
def test_create_requires_csrf(client, login_as, path):
    login_as("admin", email="nocsrf@goodmit.co.kr")
    r = client.post(path, json={"name": "몰래팀"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"


@pytest.mark.parametrize("role", ["user", "operator", "auditor"])
def test_non_admin_cannot_create_department(client, login_as, role):
    csrf = login_as(role, email=f"{role}-org@goodmit.co.kr")
    r = client.post("/api/admin/departments", json={"name": "침입팀"}, headers=_headers(csrf))
    assert r.status_code == 403


@pytest.mark.parametrize("role", ["user", "operator"])
def test_non_admin_cannot_list_departments(client, login_as, role):
    csrf = login_as(role, email=f"{role}-list@goodmit.co.kr")
    r = client.get("/api/admin/departments", headers=_headers(csrf))
    assert r.status_code == 403


def test_department_changes_are_audited(client, admin_csrf, db):
    from app.audit.models import AuditLog

    dept_id = _mk_dept(client, admin_csrf, name="감사팀").json()["department"]["id"]
    client.patch(
        f"/api/admin/departments/{dept_id}", json={"name": "감사실"}, headers=_headers(admin_csrf)
    )
    client.delete(f"/api/admin/departments/{dept_id}", headers=_headers(admin_csrf))

    actions = [
        r.action for r in db.query(AuditLog).filter(AuditLog.object_type == "department").all()
    ]
    assert "department.create" in actions
    assert "department.update" in actions
    assert "department.delete" in actions


def test_job_title_crud_mirrors_department(client, admin_csrf):
    r = _mk_title(client, admin_csrf)
    assert r.status_code == 201
    tid = r.json()["job_title"]["id"]
    assert _mk_title(client, admin_csrf).status_code == 409  # 중복
    assert client.patch(
        f"/api/admin/job-titles/{tid}", json={"name": "수석"}, headers=_headers(admin_csrf)
    ).status_code == 200
    assert client.delete(
        f"/api/admin/job-titles/{tid}", headers=_headers(admin_csrf)
    ).status_code == 200


def test_unknown_department_404(client, admin_csrf):
    assert client.patch(
        "/api/admin/departments/nope", json={"name": "x"}, headers=_headers(admin_csrf)
    ).status_code == 404
    assert client.delete(
        "/api/admin/departments/nope", headers=_headers(admin_csrf)
    ).status_code == 404
