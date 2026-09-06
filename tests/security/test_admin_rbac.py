import pytest

pytestmark = pytest.mark.security


@pytest.mark.parametrize("role", ["user", "operator", "auditor"])
def test_non_admin_roles_cannot_list_users(client, login_as, role):
    csrf = login_as(role)
    r = client.get("/api/admin/users", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 403


@pytest.mark.parametrize("role", ["user", "operator", "auditor"])
def test_non_admin_roles_cannot_create_users(client, login_as, role):
    csrf = login_as(role)
    r = client.post(
        "/api/admin/users",
        json={"email": "sneak@goodmit.co.kr", "display_name": "몰래"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 403


def test_admin_mutations_require_csrf(client, login_as):
    login_as("admin")
    r = client.post(
        "/api/admin/users",
        json={"email": "nocsrf@goodmit.co.kr", "display_name": "노토큰"},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"


def test_unauthenticated_admin_api_rejected(client):
    assert client.get("/api/admin/users").status_code == 401


@pytest.mark.parametrize(
    ("role", "expected"),
    [("user", 403), ("operator", 403), ("auditor", 200), ("admin", 200), ("system_admin", 200)],
)
def test_audit_read_role_matrix(client, login_as, role, expected):
    login_as(role)
    r = client.get("/api/admin/audit")
    assert r.status_code == expected


# ── 사람 찾기(FP-D) — 콘솔 읽기 역할이 여는 읽기 전용 후보 목록 ──────────────
#
# 승인·감사·대리 접속·쿼터 화면이 사람 필터를 `/api/admin/users`(admin 이상)로 채우는
# 바람에 운영자·감사자는 화면마다 403 을 맞고 빈 필터를 봤다. 이 경로는 그 다섯 화면이
# 쓰는 문이고, 그래서 `USER_MANAGE` 가 아니라 `CONSOLE_READ_ROLES` 여야 한다.

PEOPLE_KEYS = {"id", "display_name", "email", "active", "archived", "department_name"}


@pytest.mark.parametrize(
    ("role", "expected"),
    [("user", 403), ("operator", 200), ("auditor", 200), ("admin", 200), ("system_admin", 200)],
)
def test_people_lookup_role_matrix(client, login_as, role, expected):
    login_as(role)
    r = client.get("/api/admin/people")
    assert r.status_code == expected


def test_people_lookup_rejects_unauthenticated(client):
    assert client.get("/api/admin/people").status_code == 401


def test_people_lookup_exposes_only_identity_fields(client, login_as, make_user):
    """운영자가 이 문으로 상위 계정을 정찰할 수 있으면 사용자 관리 게이트가 반쪽이 된다.

    역할·잠금·비밀번호 해시·관리 범위는 어느 행에도 없어야 한다 — 키 집합을 등호로 못박는다.
    """
    make_user("sysadm-target@goodmit.co.kr", role="system_admin", display_name="최고관리자")
    login_as("operator")
    r = client.get("/api/admin/people")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 2, "운영자 자신과 대상 계정이 함께 보여야 한다"
    for item in items:
        assert set(item.keys()) == PEOPLE_KEYS
    assert "password_hash" not in r.text
    assert "system_admin" not in r.text, "역할이 실려 나갔다"


def test_people_lookup_q_filters_by_name_or_email_substring(client, login_as, make_user):
    make_user("hong-a@goodmit.co.kr", display_name="홍길동")
    make_user("kim-b@goodmit.co.kr", display_name="김철수")
    make_user("kim-a@goodmit.co.kr", display_name="김철수")
    login_as("operator")

    r = client.get("/api/admin/people", params={"q": "길동"})
    assert r.status_code == 200
    assert [i["display_name"] for i in r.json()["items"]] == ["홍길동"]

    # 이메일도 대소문자 없이 걸린다. 동명이인은 이메일 순으로 안정 정렬된다.
    r = client.get("/api/admin/people", params={"q": "KIM-"})
    assert r.status_code == 200
    assert [(i["display_name"], i["email"]) for i in r.json()["items"]] == [
        ("김철수", "kim-a@goodmit.co.kr"),
        ("김철수", "kim-b@goodmit.co.kr"),
    ]

    # 반례 — 아무도 안 걸리는 검색어는 빈 목록이지 오류가 아니다.
    r = client.get("/api/admin/people", params={"q": "이런사람없음"})
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_people_lookup_includes_archived_by_default_and_can_exclude(
    client, db, login_as, make_user
):
    """감사 로그는 퇴사자를 계속 가리킨다 — 기본은 싣고 표시만 구분한다."""
    from app.users.service import archive_user

    gone = make_user("gone@goodmit.co.kr", display_name="퇴사자")
    archive_user(
        db, gone, session_service=client.app.state.session_service,
        actor_role="system_admin", now=client.app.state.clock.now(),
    )
    db.commit()
    login_as("auditor")

    r = client.get("/api/admin/people", params={"q": "gone@"})
    assert r.status_code == 200
    assert [(i["email"], i["archived"]) for i in r.json()["items"]] == [
        ("gone@goodmit.co.kr", True)
    ]

    r = client.get("/api/admin/people", params={"q": "gone@", "include_archived": "false"})
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_people_lookup_limit_is_capped(client, login_as, make_user):
    make_user("one@goodmit.co.kr", display_name="가")
    make_user("two@goodmit.co.kr", display_name="나")
    login_as("operator")

    r = client.get("/api/admin/people", params={"limit": 1})
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1

    assert client.get("/api/admin/people", params={"limit": 501}).status_code == 422
    assert client.get("/api/admin/people", params={"limit": 0}).status_code == 422


def test_people_lookup_says_when_it_cut_the_list(client, login_as, make_user):
    """상한에서 잘린 사실을 안 적으면, 그 뒤의 사람은 화면에서 **존재하지 않는 사람**이 된다.

    후보 목록은 한 번에 받아 화면 안에서 거른다(`DataScreen` 의 refLists) — 잘린 뒤의
    이름은 검색해도 안 나오고, 오류도 빈 목록도 아니라 아무도 그 사실을 모른다.
    """
    make_user("cut-one@goodmit.co.kr", display_name="가나")
    make_user("cut-two@goodmit.co.kr", display_name="다라")
    login_as("operator")

    r = client.get("/api/admin/people", params={"q": "cut-", "limit": 1})
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 1
    assert body["truncated"] is True, "잘라 놓고 잘랐다고 말하지 않았다"
    assert body["total"] == 2, f"몇 명 중 몇 명인지 말할 수 없다: {body}"
    assert body["limit"] == 1


def test_people_lookup_does_not_claim_truncation_when_it_fits(client, login_as, make_user):
    """반례 — 다 실었으면 잘렸다고 말하지 않는다. 총원도 실은 수와 같다."""
    make_user("whole-one@goodmit.co.kr", display_name="마바")
    login_as("operator")

    body = client.get("/api/admin/people", params={"q": "whole-"}).json()
    assert body["truncated"] is False
    assert body["total"] == len(body["items"]) == 1


def test_people_lookup_can_drop_inactive_accounts(client, login_as, make_user):
    """새로 지정하는 폼은 서버가 거절할 사람을 후보로 세우면 안 된다 (AI 상한·승인 위임).

    비활성 계정에 AI 상한을 걸면 422 다(`app/quotas/router.py`) — 그 규칙과 후보 규칙이
    같은 축을 써야 폼이 반드시 실패하는 선택지를 권하지 않는다.
    """
    make_user("onleave@goodmit.co.kr", display_name="휴직자", active=False)
    login_as("operator")

    default_body = client.get("/api/admin/people", params={"q": "onleave@"}).json()
    assert [(i["email"], i["active"]) for i in default_body["items"]] == [
        ("onleave@goodmit.co.kr", False)
    ], "기본은 예전 그대로 싣는다 — 감사 필터는 그 사람도 골라야 한다"

    dropped = client.get(
        "/api/admin/people", params={"q": "onleave@", "include_inactive": "false"}
    ).json()
    assert dropped["items"] == []


def test_people_lookup_keeps_active_accounts_when_dropping_inactive(
    client, login_as, make_user
):
    """반례 — `include_inactive=false` 가 살아 있는 계정까지 걷어 가지 않는다."""
    make_user("still-here@goodmit.co.kr", display_name="재직자")
    login_as("operator")

    body = client.get(
        "/api/admin/people", params={"q": "still-here@", "include_inactive": "false"}
    ).json()
    assert [i["email"] for i in body["items"]] == ["still-here@goodmit.co.kr"]
