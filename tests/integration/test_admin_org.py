"""부서·직책 목록 관리.

지금까지 users.department/title은 자유 입력 문자열이었다 — 'ClovirONE팀'과
'ClovirOne팀'이 서로 다른 부서가 되고, 부서 이름이 바뀌면 전 직원의 행을 하나씩
고쳐야 했다. 목록을 따로 두고 FK로 참조하면 "한 곳만 고치면 전원에 반영"이 성립한다.
그 약속이 실제로 지켜지는지가 이 파일의 핵심(test_rename_*)이다.

qa-contract-change: 팀 채팅방과 옛 문서 기록이 부서 삭제를 409 로 막던 계약을 「삭제와 같은 트랜잭션에서 그 두 참조의 부서 연결만 끊는다」로 바꿨다. 막아 두면 제품 안에 빠져나갈 길이 없었다 —
팀 방은 부서원이 채팅 목록을 한 번만 열어도 자동으로 생기는데 방장이 없어 아무도 파할 수
없고 방의 부서를 바꾸는 API 도 화면도 없다(org-04·xc-02). 옛 문서 기록은 휴지통 영구
삭제를 지나도 행이 남아 부서를 영원히 잠갔다(xc-03). 그래서 그 두 시험은 「막는가」가
아니라 「끊고 지우되 행은 살아남는가」를 본다.

qa-contract-change: 자기 조직 비활성화 거절 문구가 「정지할 수 있습니다」에서 「비활성화할 수 있습니다」로 바뀌었다 — 버튼·확인 창·판의 안내가 전부 「비활성화」인데 서버만 다른 낱말을 써서, 거절을 읽은 관리자가 자기가 누른 것과 거절당한 것이 같은 동작인지 다시 생각해야 했다.
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
    # 사람은 「명」으로 센다 — 같은 문장 뒤쪽이 보관 계정을 「명」으로 세므로, 앞을 「건」으로
    # 세면 한 문장이 같은 사람을 두 단위로 말하고 읽는 사람은 같은 행인지 알 수 없다.
    assert "소속 사용자 2명" in err["message"], (
        f"사람을 「건」으로 센다: {err['message']}"
    )
    assert err["details"]["user_count"] == 2
    # 대안을 알려 준다 — 막기만 하면 사용자는 다음에 뭘 해야 할지 모른다.
    assert "비활성" in err["message"]

    # 그리고 실제로 아무도 잃지 않았다.
    r = client.get("/api/admin/users", params={"q": "user0@"}, headers=_headers(admin_csrf))
    assert r.json()["items"][0]["department"] == "ClovirONE팀"


def test_delete_department_counts_archived_users_too(client, admin_csrf):
    """보관된 사용자도 그 부서를 쥐고 있다 — 안 세면 FK가 가리키는 행을 지우게 된다.

    그리고 **그 사람이 보관 계정이라는 것을 말해 준다** (org-08). 인원 목록은 활성 계정만
    보여 주므로, 안 말하면 관리자는 「0명인데 왜 못 지우지」에서 멈춘다.
    """
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
    assert "보관된 계정 1명" in r.json()["error"]["message"], (
        f"활성 목록에 없는 그 한 명을 찾을 길이 없다: {r.json()['error']['message']}"
    )
    # 한 문장이 같은 사람을 두 단위로 세면 1건과 1명이 같은 행인지 알 수 없다.
    assert "소속 사용자 1명" in r.json()["error"]["message"], (
        f"앞은 「건」, 뒤는 「명」으로 같은 사람을 센다: {r.json()['error']['message']}"
    )
    precheck = client.get(
        f"/api/admin/departments/{dept_id}", headers=_headers(admin_csrf)
    ).json()["department"]["delete_precheck"]
    assert precheck["blockers"][0]["archived_count"] == 1, (
        f"화면이 보관 계정을 갈라 말할 근거가 응답에 없다: {precheck}"
    )


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


# ── 부서 삭제가 놓치던 참조 둘 ────────────────────────────────────────────────
#
# `dependents` 는 사용자·하위 부서·프로젝트·지식 공간·문서·관리 범위를 셌지만 두 표를
# 빠뜨렸다. 옛 문서 미러(`document_cache.owner_dept_id`)는 FK 가 살아 있어 DB 가 삭제를
# 거절했고(사용자가 보는 것은 원인이 안 적힌 500), 팀 채팅방(`chat_rooms.department_id`)은
# FK 가 없어 없는 부서를 가리키는 방이 조용히 남았다.
#
# 그 둘을 세기 시작하자 이번에는 **풀 수 없는 막다른 길**이 생겼다. 그래서 지금은 세되
# 막지 않는다 — 삭제와 같은 트랜잭션에서 연결만 끊고 행은 남긴다(모듈 머리의
# `qa-contract-change` 참조). 방에 든 대화도, 이관 기록도 부서 하나 때문에 없앨 것이 아니다.

def _mk_legacy_document(db, dept_id, page_id):
    from app.team_docs.models import OWNER_DEPARTMENT, DocumentCache

    db.add(DocumentCache(
        notion_page_id=page_id, title="옛 문서",
        owner_kind=OWNER_DEPARTMENT, owner_dept_id=dept_id,
    ))
    db.commit()


def _mk_team_room(db, dept_id, title):
    from app.team_chat.models import ROOM_GROUP, ChatRoom

    db.add(ChatRoom(kind=ROOM_GROUP, title=title, is_global=False, department_id=dept_id))
    db.commit()


def test_deleting_a_department_detaches_the_legacy_document_instead_of_refusing(
    client, admin_csrf, db
):
    """옛 문서 기록은 삭제를 막지 않고 **연결만 끊긴다** (xc-03).

    막던 시절에는 빠져나갈 길이 없었다 — 그 행은 화면에 존재하지도 않고, 휴지통 영구
    삭제를 지나도 `archived=true` 로만 바뀌어 부서를 계속 잠갔다.
    """
    from app.team_docs.models import DocumentCache

    dept_id = _mk_dept(client, admin_csrf, name="옛문서팀").json()["department"]["id"]
    _mk_legacy_document(db, dept_id, "legacy-doc-1")

    r = client.delete(f"/api/admin/departments/{dept_id}", headers=_headers(admin_csrf))
    assert r.status_code == 200, f"화면에 없는 행이 부서를 영원히 잠근다: {r.text}"
    assert r.json()["detached"]["legacy_documents"] == 1
    assert "옛 문서 기록" in r.json()["message"], (
        f"무엇을 끊었는지 말하지 않는다: {r.json()}"
    )

    # 부서는 사라지고, 기록은 남되 부서를 안 가리킨다 — 끊는 것이지 지우는 것이 아니다.
    assert client.get(
        f"/api/admin/departments/{dept_id}", headers=_headers(admin_csrf)
    ).status_code == 404
    db.expire_all()
    row = db.query(DocumentCache).filter(
        DocumentCache.notion_page_id == "legacy-doc-1"
    ).one()
    assert row.owner_dept_id is None, "부서를 지우면서 기록의 소속을 안 끊었다"
    assert row.owner_kind == "unset", (
        f"「부서 소유인데 부서가 없다」는 행이 남았다: {row.owner_kind}"
    )


def test_deleting_a_department_detaches_the_team_chat_room_instead_of_refusing(
    client, admin_csrf, db
):
    """팀 방은 삭제를 막지 않고 **부서 연결만 끊긴다** (org-04 · xc-02).

    방에는 사람들이 쓴 대화가 들어 있으므로 지우지 않는다. 그리고 막아 두면 그 부서는
    제품의 어떤 경로로도 지울 수 없었다 — 방장이 없어 아무도 파할 수 없기 때문이다.
    """
    from app.team_chat.models import ChatRoom

    dept_id = _mk_dept(client, admin_csrf, name="채팅팀").json()["department"]["id"]
    _mk_team_room(db, dept_id, "채팅팀 방")

    r = client.delete(f"/api/admin/departments/{dept_id}", headers=_headers(admin_csrf))
    assert r.status_code == 200, f"팀 방 하나가 부서를 영원히 잠근다: {r.text}"
    assert r.json()["detached"]["chat_rooms"] == 1
    assert "팀 채팅방" in r.json()["message"], f"무엇을 끊었는지 말하지 않는다: {r.json()}"

    db.expire_all()
    room = db.query(ChatRoom).filter(ChatRoom.title == "채팅팀 방").one()
    assert room.department_id is None, "없는 부서를 가리키는 유령 참조가 남았다"
    assert room.deleted_at is None, "대화가 든 방을 함께 지워 버렸다"


def test_delete_department_ignores_documents_and_rooms_of_other_departments(
    client, admin_csrf, db
):
    """오탐 방지 — 남의 부서에 매달린 옛 문서·채팅방은 건드리지 않는다."""
    from app.team_chat.models import ChatRoom
    from app.team_docs.models import DocumentCache

    other_id = _mk_dept(client, admin_csrf, name="남의팀").json()["department"]["id"]
    mine_id = _mk_dept(client, admin_csrf, name="빈팀").json()["department"]["id"]
    _mk_legacy_document(db, other_id, "legacy-doc-other")
    _mk_team_room(db, other_id, "남의팀 방")

    r = client.delete(f"/api/admin/departments/{mine_id}", headers=_headers(admin_csrf))
    assert r.status_code == 200, r.text
    assert "detached" not in r.json(), f"끊을 것이 없는데 끊었다고 말한다: {r.json()}"
    names = [
        d["name"]
        for d in client.get("/api/admin/departments", headers=_headers(admin_csrf)).json()["items"]
    ]
    assert names == ["남의팀"]

    db.expire_all()
    assert db.query(DocumentCache).filter(
        DocumentCache.notion_page_id == "legacy-doc-other"
    ).one().owner_dept_id == other_id, "남의 부서 기록까지 끊었다"
    assert db.query(ChatRoom).filter(
        ChatRoom.title == "남의팀 방"
    ).one().department_id == other_id, "남의 부서 방까지 끊었다"


def test_a_project_still_blocks_the_delete_and_says_what_is_archived(
    client, admin_csrf, db, make_project
):
    """지우면 조용히 깨지는 갈래는 그대로 막는다 — 그리고 **보관된 것을 말한다** (xc-04).

    보관된 프로젝트는 프로젝트 화면에 안 보이는데 삭제는 막는다. 「프로젝트 1건」이라고만
    답하면 관리자는 그 1건을 끝내 찾지 못한다.
    """
    from datetime import datetime

    dept_id = _mk_dept(client, admin_csrf, name="프로젝트팀").json()["department"]["id"]
    project = make_project(name="정리할 프로젝트", dept=dept_id)

    r = client.delete(f"/api/admin/departments/{dept_id}", headers=_headers(admin_csrf))
    assert r.status_code == 409, f"프로젝트가 매달린 부서를 지웠다: {r.text}"
    err = r.json()["error"]
    assert err["details"]["projects"] == 1
    assert "보관" not in err["message"], (
        f"보관되지도 않은 프로젝트를 보관됐다고 말한다: {err['message']}"
    )

    # 이제 그 프로젝트를 보관한다 — 화면에서 사라지지만 여전히 막는다.
    project.archived_at = datetime(2026, 9, 1)
    db.commit()
    r = client.delete(f"/api/admin/departments/{dept_id}", headers=_headers(admin_csrf))
    assert r.status_code == 409, r.text
    err = r.json()["error"]
    assert err["details"]["archived"]["projects"] == 1, (
        f"무엇이 보관된 것인지 응답이 말하지 않는다: {err['details']}"
    )
    assert "보관된 프로젝트 1건" in err["message"], (
        f"화면에서 못 찾을 1건을 그냥 「프로젝트 1건」이라고만 말한다: {err['message']}"
    )


def test_the_department_detail_says_whether_it_can_be_deleted(
    client, admin_csrf, db, make_project
):
    """삭제 판정은 **서버가 한 번** 내리고 상세 응답이 그것을 싣는다 (org-01).

    화면이 인원과 하위 부서만 세던 시절에는 「지금 삭제할 수 있습니다」라고 말해 놓고
    누르면 409 였다.
    """
    dept_id = _mk_dept(client, admin_csrf, name="판정팀").json()["department"]["id"]

    # 아무것도 안 매달린 부서는 지울 수 있다고 말한다(오탐 방지).
    body = client.get(
        f"/api/admin/departments/{dept_id}", headers=_headers(admin_csrf)
    ).json()["department"]
    assert body["delete_precheck"]["deletable"] is True
    assert body["delete_precheck"]["blockers"] == []

    make_project(name="판정용 프로젝트", dept=dept_id)
    _mk_team_room(db, dept_id, "판정팀 방")

    precheck = client.get(
        f"/api/admin/departments/{dept_id}", headers=_headers(admin_csrf)
    ).json()["department"]["delete_precheck"]
    assert precheck["deletable"] is False, (
        f"프로젝트가 매달렸는데 지울 수 있다고 말한다: {precheck}"
    )
    kinds = {b["kind"]: b for b in precheck["blockers"]}
    assert kinds["projects"]["count"] == 1
    assert kinds["projects"]["label"] == "프로젝트", "서버와 화면이 라벨을 두 벌 갖는다"
    assert "프로젝트 1건" in precheck["reason"], (
        f"무엇 때문에 못 지우는지 한 문장으로 말하지 않는다: {precheck['reason']}"
    )
    # 막지 않는 갈래는 blockers 가 아니라 detachables 다 — 화면이 둘을 다르게 말해야 한다.
    assert [d["kind"] for d in precheck["detachables"]] == ["chat_rooms"]

    # 판정과 실행이 **같은 문장**을 쓴다.
    r = client.delete(f"/api/admin/departments/{dept_id}", headers=_headers(admin_csrf))
    assert r.status_code == 409, r.text
    assert r.json()["error"]["message"] == precheck["reason"], (
        "안내와 실제 거절이 다른 말을 한다 — 그 어긋남이 org-01 의 본체다"
    )


def test_a_noop_patch_leaves_no_audit_row(client, admin_csrf, db):
    """바뀐 것이 없으면 감사 행도 없다 (org-13).

    감사 로그는 「무엇이 언제 바뀌었나」를 읽는 곳이다. before 와 after 가 글자까지 같은
    '수정' 행이 쌓이면 조사자가 그 시각에 무언가 일어난 줄 알고 시간을 쓴다.
    """
    from app.audit.models import AuditLog

    dept_id = _mk_dept(client, admin_csrf, name="무변경팀").json()["department"]["id"]

    def rows():
        db.expire_all()
        return db.query(AuditLog).filter(
            AuditLog.object_type == "department",
            AuditLog.object_id == dept_id,
            AuditLog.action == "department.update",
        ).count()

    assert rows() == 0
    assert client.patch(
        f"/api/admin/departments/{dept_id}", json={}, headers=_headers(admin_csrf)
    ).status_code == 200, "빈 본문 PATCH 는 200 그대로다 — 응답이 아니라 기록의 문제다"
    assert client.patch(
        f"/api/admin/departments/{dept_id}", json={"name": "무변경팀"},
        headers=_headers(admin_csrf),
    ).status_code == 200
    assert rows() == 0, "아무것도 안 바뀐 PATCH 가 감사 행을 남겼다"

    # 오탐 방지 — 진짜로 바뀌면 반드시 남는다.
    assert client.patch(
        f"/api/admin/departments/{dept_id}", json={"name": "바뀐팀"},
        headers=_headers(admin_csrf),
    ).status_code == 200
    assert rows() == 1, "실제 변경이 감사 로그에서 사라졌다"


def test_an_inactive_department_cannot_be_a_new_parent(client, admin_csrf):
    """비활성 부서 아래에 새 부서를 걸 수 없다 (xb-08).

    「비활성」은 새로 고를 수 없다는 뜻이다 — 사용자·직책 배정에는 그 규칙이 있는데 트리
    편집에만 없어서, 정리한 부서 밑에 새 부서가 생기고 어느 진단에도 안 걸렸다.
    """
    dead_id = _mk_dept(client, admin_csrf, name="정리된본부").json()["department"]["id"]
    assert client.patch(
        f"/api/admin/departments/{dead_id}", json={"active": False},
        headers=_headers(admin_csrf),
    ).status_code == 200

    r = client.post(
        "/api/admin/departments", json={"name": "새하위팀", "parent_id": dead_id},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422, f"비활성 부서 아래에 부서가 생겼다: {r.status_code} {r.text}"
    assert "비활성" in r.json()["error"]["message"]

    mover_id = _mk_dept(client, admin_csrf, name="옮길팀").json()["department"]["id"]
    r = client.patch(
        f"/api/admin/departments/{mover_id}", json={"parent_id": dead_id},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422, f"생성만 막으면 수정으로 같은 일을 한다: {r.text}"

    # 오탐 방지 1 — 살아 있는 부서 아래에는 그대로 만들 수 있다.
    alive_id = _mk_dept(client, admin_csrf, name="살아있는본부").json()["department"]["id"]
    assert client.post(
        "/api/admin/departments", json={"name": "정상하위팀", "parent_id": alive_id},
        headers=_headers(admin_csrf),
    ).status_code == 201


def test_a_department_under_an_inactive_parent_can_still_be_renamed(client, admin_csrf, db):
    """오탐 방지 2 — 이미 비활성 부모 밑에 있는 부서는 이름을 고칠 수 있어야 한다.

    수정 폼은 이름만 고칠 때에도 지금 부모를 그대로 다시 보낸다. 여기서 막으면 그 부서는
    이름조차 못 고친다(`resolve_assignable` 의 `allow_current` 와 같은 이유).
    """
    parent_id = _mk_dept(client, admin_csrf, name="곧비활성본부").json()["department"]["id"]
    child_id = client.post(
        "/api/admin/departments", json={"name": "매달린팀", "parent_id": parent_id},
        headers=_headers(admin_csrf),
    ).json()["department"]["id"]
    client.patch(
        f"/api/admin/departments/{parent_id}", json={"active": False},
        headers=_headers(admin_csrf),
    )

    r = client.patch(
        f"/api/admin/departments/{child_id}",
        json={"name": "이름바꾼팀", "parent_id": parent_id},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200, f"부모가 비활성이라 이름조차 못 고친다: {r.text}"
    assert r.json()["department"]["name"] == "이름바꾼팀"


# ── 조직 명부의 충돌 응답 ────────────────────────────────────────────────────
#
# 같은 콘솔 안에서 같은 사건(이미 있는 이름·식별자)이 두 코드로 나오면 API 를 쓰는 쪽
# (스크립트·가져오기·연동)의 분기가 틀린다.

def test_duplicate_organization_slug_is_a_conflict(client, login_as):
    """식별자 중복은 409 다 (org-10) — 부서·직책 중복이 같은 답을 준다."""
    csrf = login_as("system_admin")
    first = client.post(
        "/api/admin/organizations", json={"name": "첫조직", "slug": "dup-slug"},
        headers=_headers(csrf),
    )
    assert first.status_code == 201, first.text
    again = client.post(
        "/api/admin/organizations", json={"name": "다른이름", "slug": "dup-slug"},
        headers=_headers(csrf),
    )
    assert again.status_code == 409, f"충돌이 422 로 나온다: {again.status_code} {again.text}"
    assert "dup-slug" in again.json()["error"]["message"]


def test_duplicate_organization_name_is_a_conflict(client, login_as):
    """이름이 같은 조직 둘은 화면에서 구별할 수 없다 (org-11).

    조직은 테넌트 경계다 — 같은 라벨 두 개 중 하나를 골라 부서를 만들면 그 부서가 어느
    회사에 붙었는지 화면만 봐서는 알 수 없다.
    """
    csrf = login_as("system_admin")
    assert client.post(
        "/api/admin/organizations", json={"name": "같은이름조직", "slug": "same-a"},
        headers=_headers(csrf),
    ).status_code == 201
    again = client.post(
        "/api/admin/organizations", json={"name": "같은이름조직", "slug": "same-b"},
        headers=_headers(csrf),
    )
    assert again.status_code == 409, f"이름이 똑같은 조직이 또 생겼다: {again.text}"

    # 대소문자만 다른 이름도 사람 눈에는 같은 이름이다.
    assert client.post(
        "/api/admin/organizations", json={"name": "Tenant", "slug": "case-a"},
        headers=_headers(csrf),
    ).status_code == 201
    assert client.post(
        "/api/admin/organizations", json={"name": "tenant", "slug": "case-b"},
        headers=_headers(csrf),
    ).status_code == 409

    # 오탐 방지 — 다른 이름은 그대로 만들어지고, 자기 이름으로 다시 저장해도 막히지 않는다.
    made = client.post(
        "/api/admin/organizations", json={"name": "고유한조직", "slug": "unique-c"},
        headers=_headers(csrf),
    )
    assert made.status_code == 201, made.text
    assert client.patch(
        f"/api/admin/organizations/{made.json()['organization']['id']}",
        json={"name": "고유한조직"}, headers=_headers(csrf),
    ).status_code == 200, "자기 이름을 그대로 다시 저장했는데 중복이라고 막는다"


# ── 자기 조직 정지는 포탈 운영자만 ───────────────────────────────────────────
#
# 정지는 그 조직 구성원의 세션을 즉시 전부 끊는다(`system_admin` 예외). 일반 관리자가
# 자기 조직을 정지시키면 그 요청을 낸 세션까지 끊겨, 정지를 건 사람도 풀 사람도 조직 안에
# 없는 상태가 된다.

def _suspend(client, csrf, org_id):
    return client.patch(
        f"/api/admin/organizations/{org_id}",
        json={"status": "suspended"},
        headers=_headers(csrf),
    )


def test_an_admin_cannot_suspend_their_own_organization(client, admin_csrf):
    from app.org.constants import DEFAULT_ORG_ID

    r = _suspend(client, admin_csrf, DEFAULT_ORG_ID)
    assert r.status_code == 403, (
        f"관리자가 자기 조직을 정지시켰다 — 자기 세션까지 끊긴다: {r.status_code} {r.text}"
    )
    # 화면이 이 동작을 부르는 이름은 「비활성화」 하나다(OrgDetailPanel.jsx 의 버튼·확인
    # 창·안내). 서버만 「정지」라고 답하면 같은 동작을 두 이름으로 말하게 된다.
    assert r.json()["error"]["message"] == "자기 조직은 시스템 관리자만 비활성화할 수 있습니다."

    # 거부는 아무것도 바꾸지 않는다 — 조직도, 요청한 사람의 세션도.
    assert client.get("/api/me").status_code == 200, "거부하면서 관리자의 세션을 끊었다"
    r = client.get(f"/api/admin/organizations/{DEFAULT_ORG_ID}", headers=_headers(admin_csrf))
    assert r.status_code == 200, r.text
    assert r.json()["organization"]["status"] == "active", "403 을 주면서 실제로는 정지시켰다"


def test_the_portal_operator_can_suspend_the_same_organization(client, login_as):
    """오탐 방지 — 포탈 운영자는 자기 조직도 정지시킬 수 있다(끊기지 않는 유일한 역할이다)."""
    from app.org.constants import DEFAULT_ORG_ID

    csrf = login_as("system_admin")
    r = _suspend(client, csrf, DEFAULT_ORG_ID)
    assert r.status_code == 200, r.text
    assert r.json()["organization"]["status"] == "suspended"
    assert client.get("/api/me").status_code == 200, "운영자가 자기 자신을 잠갔다"


def test_an_admin_can_still_suspend_another_organization(client, admin_csrf, two_orgs):
    """다른 조직 정지는 예전 계약 그대로다 — 자기 세션이 끊기지 않으니 막을 이유가 없다."""
    r = _suspend(client, admin_csrf, two_orgs.org_b_id)
    assert r.status_code == 200, r.text
    assert r.json()["organization"]["status"] == "suspended"
    assert client.get("/api/me").status_code == 200


# ── 조직 상세가 「수정할 수 있는가」를 스스로 말한다 (R4-03) ──────────────────
#
# `PATCH /api/admin/organizations/{id}` 는 전체 범위 관리자만 지난다. 그런데 조직 상세 판은
# 범위를 좁힌 관리자에게도 자기 조직 행을 그려 주므로, 화면이 그 판정을 알 길이 없으면
# 「수정」 버튼을 그려 놓고 저장할 때 403 을 준다 — 같은 판이 「비활성화」에 대해서는 이미
# 판정을 재현하고 안내까지 붙인다(OrgDetailPanel.jsx). 판정의 정본은 서버라(D-194) 화면이
# 다시 계산하는 대신 응답이 답을 싣는다.


def _scoped_org_admin(make_user, db, scope_dept_name="범위팀"):
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    dept = Department(name=scope_dept_name, org_id=DEFAULT_ORG_ID)
    db.add(dept)
    db.flush()
    boss = make_user("orgedit-boss@goodmit.co.kr", role="admin", display_name="부서관리자")
    boss.org_id = DEFAULT_ORG_ID
    boss.department_id = dept.id
    boss.admin_scope = "dept"
    boss.scope_dept_id = dept.id
    db.commit()
    return boss


def test_a_scoped_admin_is_told_they_cannot_edit_the_organization(
    client, login_as, db, make_user
):
    """🔴 화면은 「수정」을 그리고 서버는 403 을 준다 — 응답이 그 판정을 싣지 않았다."""
    from app.org.constants import DEFAULT_ORG_ID

    _scoped_org_admin(make_user, db)
    csrf = login_as("admin", email="orgedit-boss@goodmit.co.kr")

    detail = client.get(
        f"/api/admin/organizations/{DEFAULT_ORG_ID}", headers=_headers(csrf)
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["organization"]["can_edit"] is False, (
        "화면이 「수정」 버튼을 감출 근거가 응답에 없다"
    )

    listed = client.get("/api/admin/organizations", headers=_headers(csrf))
    assert listed.status_code == 200, listed.text
    assert [o["can_edit"] for o in listed.json()["items"]] == [False], (
        "목록과 상세가 다른 말을 한다"
    )

    # 그리고 그 답은 서버가 실제로 하는 판정과 같다 — 눌러 보기 전과 눌러 본 뒤가 같다.
    saved = client.patch(
        f"/api/admin/organizations/{DEFAULT_ORG_ID}",
        json={"name": "몰래 개명"},
        headers=_headers(csrf),
    )
    assert saved.status_code == 403, saved.text


def test_a_global_admin_is_told_they_can_edit_the_organization(client, admin_csrf):
    """오탐 방지 — 전체 범위 관리자에게는 아무것도 달라지지 않는다.

    막기만 하면 전부 `false` 로 채워도 초록이 된다.
    """
    from app.org.constants import DEFAULT_ORG_ID

    detail = client.get(
        f"/api/admin/organizations/{DEFAULT_ORG_ID}", headers=_headers(admin_csrf)
    )
    assert detail.json()["organization"]["can_edit"] is True, detail.text

    listed = client.get("/api/admin/organizations", headers=_headers(admin_csrf))
    assert all(o["can_edit"] is True for o in listed.json()["items"]), listed.text

    saved = client.patch(
        f"/api/admin/organizations/{DEFAULT_ORG_ID}",
        json={"name": "개명한 조직"},
        headers=_headers(admin_csrf),
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["organization"]["can_edit"] is True
