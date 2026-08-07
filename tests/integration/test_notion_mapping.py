"""Notion user mapping (spec §12, §31.3)."""

import pytest

pytestmark = pytest.mark.integration

MAP_URL = "http://127.0.0.1:5678/webhook/notion-map"


@pytest.fixture()
def admin_csrf(login_as):
    return login_as("admin")


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


@pytest.fixture()
def mapping_workflow(client, admin_csrf):
    """Register the reserved mapping workflow."""
    return client.post(
        "/api/admin/workflows",
        json={
            "name": "notion-user-mapping",
            "webhook_url": MAP_URL,
            "http_method": "POST",
            "operation_mode": "read",
        },
        headers=_headers(admin_csrf),
    ).json()["workflow"]["id"]


def test_verify_exactly_one_match_is_verified(
    client, admin_csrf, make_user, mapping_workflow, fake_http
):
    user = make_user("mapme@goodmit.co.kr")
    fake_http.on(
        MAP_URL,
        json_body={"matches": [{"notion_user_id": "abcd1234efgh", "notion_email": "mapme@goodmit.co.kr"}]},
    )
    r = client.post(
        f"/api/admin/notion-mapping/{user.id}/verify", headers=_headers(admin_csrf)
    )
    assert r.status_code == 200
    m = r.json()["mapping"]
    assert m["status"] == "verified"
    assert m["notion_user_id_masked"] == "abcd…efgh"  # masked, never full id


def test_verify_zero_matches_unmapped(
    client, admin_csrf, make_user, mapping_workflow, fake_http
):
    user = make_user("nomatch@goodmit.co.kr")
    fake_http.on(MAP_URL, json_body={"matches": []})
    r = client.post(
        f"/api/admin/notion-mapping/{user.id}/verify", headers=_headers(admin_csrf)
    )
    assert r.json()["mapping"]["status"] == "unmapped"


def test_verify_multiple_matches_conflict(
    client, admin_csrf, make_user, mapping_workflow, fake_http
):
    user = make_user("conflict@goodmit.co.kr")
    fake_http.on(
        MAP_URL,
        json_body={"matches": [
            {"notion_user_id": "aaaa1111bbbb", "notion_email": "c@x"},
            {"notion_user_id": "cccc2222dddd", "notion_email": "c@y"},
        ]},
    )
    r = client.post(
        f"/api/admin/notion-mapping/{user.id}/verify", headers=_headers(admin_csrf)
    )
    m = r.json()["mapping"]
    assert m["status"] == "conflict"
    assert len(m["candidates"]) == 2


def test_no_mapping_workflow_configured(client, admin_csrf, make_user):
    user = make_user("noworkflow@goodmit.co.kr")
    r = client.post(
        f"/api/admin/notion-mapping/{user.id}/verify", headers=_headers(admin_csrf)
    )
    assert r.json()["mapping"]["status"] == "unmapped"
    assert "구성" in r.json()["mapping"]["error_message"]


def test_verify_failure_does_not_fake_a_fresh_timestamp(
    client, admin_csrf, make_user, mapping_workflow, fake_http
):
    """조회 자체가 실패했는데 '방금 확인함'처럼 보이면 안 된다.

    n8n 호출이 예외를 던지면 error_message는 실패를 말하는데 last_verified_at이 지금
    시각으로 찍히면, 화면은 '막 검증했는데 실패'가 아니라 '방금 검증됨' 처럼 보인다.
    """
    user = make_user("verifyfail@goodmit.co.kr")
    fake_http.on_connect_error(MAP_URL)
    r = client.post(
        f"/api/admin/notion-mapping/{user.id}/verify", headers=_headers(admin_csrf)
    )
    assert r.status_code == 200
    m = r.json()["mapping"]
    assert m["last_verified_at"] is None
    assert m["error_message"]


def test_verify_failure_keeps_the_previous_verified_at(
    client, admin_csrf, make_user, mapping_workflow, fake_http
):
    """예전엔 성공했던 매핑이 나중에 실패한 재조회로 '방금 확인함'을 새로 얻으면 안 된다."""
    user = make_user("staleverify@goodmit.co.kr")
    fake_http.on(
        MAP_URL,
        json_body={
            "matches": [
                {"notion_user_id": "abcd1234efgh", "notion_email": "staleverify@goodmit.co.kr"}
            ]
        },
    )
    ok = client.post(
        f"/api/admin/notion-mapping/{user.id}/verify", headers=_headers(admin_csrf)
    ).json()["mapping"]
    assert ok["status"] == "verified"
    first_verified_at = ok["last_verified_at"]
    assert first_verified_at

    client.app.state.clock.advance(60)
    fake_http.on_connect_error(MAP_URL)
    failed = client.post(
        f"/api/admin/notion-mapping/{user.id}/verify", headers=_headers(admin_csrf)
    ).json()["mapping"]
    assert failed["last_verified_at"] == first_verified_at, (
        "실패한 조회가 last_verified_at을 새로 찍었다"
    )
    assert failed["error_message"]
    # 상태·매핑 id는 실패 전 값 그대로 남아야 한다 - 실패가 멀쩡한 매핑을 지우면 안 된다.
    assert failed["status"] == "verified"


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


def test_resolve_conflict_picks_candidate(
    client, admin_csrf, make_user, mapping_workflow, fake_http
):
    user = make_user("resolve@goodmit.co.kr")
    fake_http.on(
        MAP_URL,
        json_body={"matches": [
            {"notion_user_id": "pick1111aaaa", "notion_email": "r@x"},
            {"notion_user_id": "pick2222bbbb", "notion_email": "r@y"},
        ]},
    )
    client.post(f"/api/admin/notion-mapping/{user.id}/verify", headers=_headers(admin_csrf))
    r = client.post(
        f"/api/admin/notion-mapping/{user.id}/resolve-conflict",
        json={"notion_user_id": "pick2222bbbb"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200
    assert r.json()["mapping"]["status"] == "verified"


def test_resolve_conflict_rejects_non_candidate(
    client, admin_csrf, make_user, mapping_workflow, fake_http
):
    user = make_user("badresolve@goodmit.co.kr")
    fake_http.on(
        MAP_URL,
        json_body={"matches": [
            {"notion_user_id": "aaaa1111cccc", "notion_email": "x"},
            {"notion_user_id": "bbbb2222dddd", "notion_email": "y"},
        ]},
    )
    client.post(f"/api/admin/notion-mapping/{user.id}/verify", headers=_headers(admin_csrf))
    r = client.post(
        f"/api/admin/notion-mapping/{user.id}/resolve-conflict",
        json={"notion_user_id": "notacandidate99"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422


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
