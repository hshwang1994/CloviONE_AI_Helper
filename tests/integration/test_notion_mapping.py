"""qa-contract-change: 자동 조회(/verify)와 그 뒤의 충돌 해결이 S11 로 사라졌다 — n8n 워크플로가 하던 일이라 부를 곳이 없고, 충돌 상태를 만들 수 있는 경로 자체가 없어졌다. 남은 것은 사람이 직접 지정하는 길(수동 연결·해제)과 목록·검색·범위 단언 전부이고 그쪽은 한 글자도 안 바뀌었다."""

"""Notion user mapping (spec §12, §31.3)."""

import pytest

pytestmark = pytest.mark.integration



@pytest.fixture()
def admin_csrf(login_as):
    return login_as("admin")


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


# S11 이 자동 조회(`/sync`·`/verify`)와 그 뒤의 충돌 해결을 걷어냈다 — n8n 워크플로가
# 하던 일이라 부를 곳이 사라졌다. 남은 것은 **사람이 직접 지정하는 길** 하나이고 아래가
# 그것을 본다. 매핑 데이터 자체는 Notion Runtime 과 함께 S14 다.


def test_manual_map_and_unmap(client, admin_csrf, make_user):
    user = make_user("manual@goodmit.co.kr")
    r = client.post(
        f"/api/admin/notion-mapping/{user.id}/map",
        json={"notion_user_id": "manual12345678", "notion_email": "manual@goodmit.co.kr"},
        headers=_headers(admin_csrf),
    )
    assert r.json()["mapping"]["status"] == "verified"
    assert r.json()["mapping"]["source"] == "manual"

    r = client.post(
        f"/api/admin/notion-mapping/{user.id}/unmap", headers=_headers(admin_csrf)
    )
    assert r.json()["mapping"]["status"] == "unmapped"


def test_profile_shows_mapping_status(client, login_as, make_user, admin_csrf):
    # Admin maps a user, then that user sees verified status on their profile.
    user = make_user("selfview@goodmit.co.kr")
    client.post(
        f"/api/admin/notion-mapping/{user.id}/map",
        json={"notion_user_id": "self12345678"},
        headers=_headers(admin_csrf),
    )
    login_as("user", email="selfview@goodmit.co.kr")
    r = client.get("/api/profile")
    assert r.json()["notion_mapping_status"] == "verified"


def test_regular_user_cannot_access_mapping_admin(client, login_as):
    login_as("user")
    assert client.get("/api/admin/notion-mapping").status_code == 403


def test_list_includes_users_without_a_mapping_row(client, admin_csrf, make_user):
    """매핑 행이 없는 사용자도 목록에 나와야 관리자가 연결을 시작할 수 있다."""
    user = make_user("nomap@goodmit.co.kr", display_name="김미매핑")
    r = client.get("/api/admin/notion-mapping")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    row = next(i for i in body["items"] if i["user_id"] == user.id)
    assert row["status"] == "unmapped"
    assert row["user_email"] == "nomap@goodmit.co.kr"
    assert row["user_display_name"] == "김미매핑"


def test_list_filters_by_user_ids(client, admin_csrf, make_user):
    wanted = make_user("wanted@goodmit.co.kr")
    make_user("other@goodmit.co.kr")
    r = client.get(f"/api/admin/notion-mapping?user_ids={wanted.id}")
    assert [i["user_id"] for i in r.json()["items"]] == [wanted.id]


def test_list_search_by_display_name_is_case_insensitive(client, admin_csrf, make_user, db):
    """이메일 검색처럼 이름 검색도 SQL에서 대소문자를 가리면 안 된다.

    SQLite의 LIKE/lower()는 ASCII만 대소문자를 접어 준다 - ASCII 표본만으로 응답을 보면
    구현이 `func.lower()`를 빠뜨려도 SQLite가 알아서 맞춰 줘서 초록불이 나온다(가짜 안전,
    Postgres 등 다른 백엔드에서는 그대로 재현된다). 그래서 응답이 아니라 실제로 나간 SQL을
    본다: email 쪽처럼 display_name 쪽도 `lower(...)`로 감싸져 있어야 한다.
    """
    make_user("sqlcheck@goodmit.co.kr", display_name="SqlCheck")

    from sqlalchemy import event

    engine = db.get_bind()
    statements: list[str] = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        if "user_notion_mappings" in statement:
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        r = client.get("/api/admin/notion-mapping", params={"q": "sqlcheck"})
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

    assert r.status_code == 200
    assert statements, "notion-mapping 목록 SQL을 못 잡았다"
    list_stmt = statements[0].lower()
    assert "lower(users.email)" in list_stmt
    assert "lower(users.display_name)" in list_stmt, (
        "display_name 검색이 email 검색과 달리 lower()로 감싸지지 않았다"
    )


def test_list_filters_by_q_and_status(client, admin_csrf, make_user):
    user = make_user("findme@goodmit.co.kr")
    client.post(
        f"/api/admin/notion-mapping/{user.id}/map",
        json={"notion_user_id": "findme12345678"},
        headers=_headers(admin_csrf),
    )
    r = client.get("/api/admin/notion-mapping?q=findme")
    assert [i["user_id"] for i in r.json()["items"]] == [user.id]
    assert r.json()["items"][0]["status"] == "verified"

    verified = client.get("/api/admin/notion-mapping?status=verified").json()["items"]
    assert user.id in [i["user_id"] for i in verified]
    unmapped = client.get("/api/admin/notion-mapping?status=unmapped").json()["items"]
    assert user.id not in [i["user_id"] for i in unmapped]


def test_list_is_paginated(client, admin_csrf, make_user):
    for i in range(3):
        make_user(f"page{i}@goodmit.co.kr")
    body = client.get("/api/admin/notion-mapping?page=1&page_size=2").json()
    assert len(body["items"]) == 2
    assert body["page_size"] == 2
    assert body["total"] >= 4  # 3 + admin


def test_auditor_can_resolve_actor_identity(client, login_as, make_user):
    """감사 로그의 행위자 UUID를 사람으로 읽으려면 auditor도 디렉터리를 읽어야 한다."""
    user = make_user("actor@goodmit.co.kr", display_name="행위자")
    login_as("auditor")
    r = client.get(f"/api/admin/notion-mapping?user_ids={user.id}")
    assert r.status_code == 200
    assert r.json()["items"][0]["user_display_name"] == "행위자"
