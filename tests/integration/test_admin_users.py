import pytest

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration


@pytest.fixture()
def admin_csrf(login_as):
    return login_as("admin")


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


def _create(client, csrf, email="new-user@goodmit.co.kr", **overrides):
    payload = {"email": email, "display_name": "신규 사용자", "role": "user", **overrides}
    return client.post("/api/admin/users", json=payload, headers=_headers(csrf))


def test_create_user_returns_temp_password_once(client, admin_csrf, db):
    r = _create(client, admin_csrf)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["email"] == "new-user@goodmit.co.kr"
    temp = body["temp_password"]
    assert temp and len(temp) >= 12

    # The temp password must not appear in any audit row.
    from app.audit.models import AuditLog

    rows = db.query(AuditLog).all()
    assert rows, "audit row missing"
    for row in rows:
        blob = (row.before_json or "") + (row.after_json or "")
        assert temp not in blob
        assert "password_hash" not in blob

    # New user can log in with the temp password and must change it.
    login = client.post(
        "/login", json={"email": "new-user@goodmit.co.kr", "password": temp}
    )
    # (admin session cookie gets replaced — acceptable within this test)
    assert login.status_code == 200
    assert login.json()["must_change_password"] is True


def test_create_user_with_admin_chosen_password(client, admin_csrf):
    r = _create(
        client, admin_csrf, email="chosen@goodmit.co.kr", password="Chosen-Pass-12!"
    )
    assert r.status_code == 201
    assert "temp_password" not in r.json()


def test_create_user_weak_admin_password_rejected(client, admin_csrf):
    r = _create(client, admin_csrf, email="weak@goodmit.co.kr", password="weak")
    assert r.status_code == 422


def test_create_duplicate_email_conflict(client, admin_csrf):
    assert _create(client, admin_csrf, email="dup@goodmit.co.kr").status_code == 201
    r = _create(client, admin_csrf, email="dup@goodmit.co.kr")
    assert r.status_code == 409


def _set_domains(client, csrf, domains):
    """허용 도메인을 실제로 설정한다.

    🔴 이 준비가 없으면 이 테스트는 **아무것도 검사하지 않는다.** 고객사 고유값을 소스
    기본값에서 비운 뒤로(P1) 허용 도메인의 기본값은 **빈 목록 = 제한 없음** 이다. 그래서
    설정 없이 부르면 어떤 도메인이든 통과하고, 예전 기대(422)는 그냥 틀린 기대가 된다.
    """
    r = client.put("/api/admin/settings/allowed_email_domains",
                   json={"value": domains}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text


def test_create_wrong_domain_rejected(client, admin_csrf):
    """도메인 제한을 **걸어 둔 상태**에서 다른 도메인은 거절된다."""
    _set_domains(client, admin_csrf, ["goodmit.co.kr"])
    r = _create(client, admin_csrf, email="outsider@evil.example.com")
    assert r.status_code == 422, f"제한을 걸었는데 통과했다: {r.status_code} {r.text}"


def test_the_allowed_domain_still_works_when_the_restriction_is_on(client, admin_csrf):
    """오탐 방지 - 좁히느라 허용 도메인까지 막으면 그건 기능 고장이다."""
    _set_domains(client, admin_csrf, ["goodmit.co.kr"])
    assert _create(client, admin_csrf, email="inside@goodmit.co.kr").status_code == 201


def test_no_configured_domains_means_no_restriction(client, admin_csrf):
    """🔴 빈 목록의 뜻을 못박는다 (P1).

    반대로 잡으면(빈 목록 = 아무도 불가) 설치 직후 **첫 관리자 계정조차 못 만든다.**
    설정 화면 안내문과 `create_user` 의 분기가 이미 '제한 없음' 으로 일치한다.
    """
    r = _create(client, admin_csrf, email="anyone@example.org")
    assert r.status_code == 201, f"제한을 안 걸었는데 거절했다: {r.status_code} {r.text}"


def test_create_unknown_role_rejected(client, admin_csrf):
    r = _create(client, admin_csrf, email="role@goodmit.co.kr", role="superroot")
    assert r.status_code == 422


def test_list_users_search_and_filters(client, admin_csrf):
    _create(client, admin_csrf, email="kim.dev@goodmit.co.kr", display_name="김개발")
    _create(
        client, admin_csrf, email="lee.ops@goodmit.co.kr",
        display_name="이운영", role="operator",
    )

    r = client.get("/api/admin/users", params={"q": "kim.dev"}, headers=_headers(admin_csrf))
    assert r.status_code == 200
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["email"] == "kim.dev@goodmit.co.kr"

    r = client.get("/api/admin/users", params={"role": "operator"}, headers=_headers(admin_csrf))
    emails = [u["email"] for u in r.json()["items"]]
    assert emails == ["lee.ops@goodmit.co.kr"]

    r = client.get(
        "/api/admin/users", params={"page_size": 1, "page": 1}, headers=_headers(admin_csrf)
    )
    assert len(r.json()["items"]) == 1
    assert r.json()["total"] >= 3  # admin + 2 created


# ── ADM-06R: "지금 잠긴 사람만 보기" ─────────────────────────────────────────
#
# 화면·배지("잠김")·잠금 해제 버튼은 이미 다 있었는데 필터가 없었다 — 관리자가 잠긴
# 계정을 찾으려면 전체 목록을 눈으로 훑어야 했다.

def test_locked_filter_finds_a_locked_account(client, admin_csrf, app, settings):
    from fastapi.testclient import TestClient

    created = _create(client, admin_csrf, email="locked-filter@goodmit.co.kr").json()
    other = _create(client, admin_csrf, email="not-locked@goodmit.co.kr").json()

    with TestClient(app, raise_server_exceptions=False) as attacker:
        for _ in range(settings.login_max_failures):
            attacker.post(
                "/login", json={"email": "locked-filter@goodmit.co.kr", "password": "Wrong-1x!"}
            )

    r = client.get("/api/admin/users", params={"locked": "true"}, headers=_headers(admin_csrf))
    assert r.status_code == 200, r.text
    emails = [u["email"] for u in r.json()["items"]]
    assert "locked-filter@goodmit.co.kr" in emails
    assert "not-locked@goodmit.co.kr" not in emails
    assert all(u["locked"] for u in r.json()["items"])

    r = client.get("/api/admin/users", params={"locked": "false"}, headers=_headers(admin_csrf))
    emails = [u["email"] for u in r.json()["items"]]
    assert "not-locked@goodmit.co.kr" in emails
    assert "locked-filter@goodmit.co.kr" not in emails

    # 해제하면 잠김 필터에서 빠지고 안 잠김 필터로 옮겨간다.
    client.post(
        f"/api/admin/users/{created['user']['id']}/unlock", headers=_headers(admin_csrf)
    )
    r = client.get("/api/admin/users", params={"locked": "true"}, headers=_headers(admin_csrf))
    assert "locked-filter@goodmit.co.kr" not in [u["email"] for u in r.json()["items"]]


def test_locked_filter_also_applies_to_csv_export(client, admin_csrf, app, settings):
    """목록·CSV가 다른 문장을 쓰면 화면엔 필터가 걸리는데 내보낸 파일엔 전원이 담긴다."""
    from fastapi.testclient import TestClient

    _create(client, admin_csrf, email="csv-locked@goodmit.co.kr")
    _create(client, admin_csrf, email="csv-not-locked@goodmit.co.kr")
    with TestClient(app, raise_server_exceptions=False) as attacker:
        for _ in range(settings.login_max_failures):
            attacker.post(
                "/login", json={"email": "csv-locked@goodmit.co.kr", "password": "Wrong-1x!"}
            )

    r = client.get(
        "/api/admin/users/export/csv", params={"locked": "true"}, headers=_headers(admin_csrf)
    )
    assert r.status_code == 200
    assert "csv-locked@goodmit.co.kr" in r.text
    assert "csv-not-locked@goodmit.co.kr" not in r.text


def test_patch_user_updates_fields(client, admin_csrf):
    # 부서는 이제 자유 문자열이 아니라 명부(app/org)의 항목을 가리킨다.
    dept_id = client.post(
        "/api/admin/departments", json={"name": "기술사업본부"}, headers=_headers(admin_csrf)
    ).json()["department"]["id"]

    created = _create(client, admin_csrf, email="patch@goodmit.co.kr").json()["user"]
    r = client.patch(
        f"/api/admin/users/{created['id']}",
        json={"display_name": "변경된 이름", "department_id": dept_id},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200
    assert r.json()["user"]["display_name"] == "변경된 이름"
    assert r.json()["user"]["department"] == "기술사업본부"


def test_patch_user_rejects_legacy_free_text_department(client, admin_csrf):
    """옛 방식({"department": "영업팀"})은 조용히 무시되면 안 된다 — 부르는 쪽은 200을
    받고 부서가 바뀌었다고 믿지만 실제로는 아무 일도 일어나지 않는다."""
    created = _create(client, admin_csrf, email="legacy@goodmit.co.kr").json()["user"]
    r = client.patch(
        f"/api/admin/users/{created['id']}",
        json={"department": "기술사업본부"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422, r.text


def test_disable_user_revokes_sessions(app, client, admin_csrf, make_user):
    from fastapi.testclient import TestClient

    target = make_user("victim@goodmit.co.kr")
    with TestClient(app, raise_server_exceptions=False) as victim:
        victim.post(
            "/login",
            json={"email": "victim@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD},
        )
        assert victim.get("/api/me").status_code == 200

        r = client.post(
            f"/api/admin/users/{target.id}/disable", headers=_headers(admin_csrf)
        )
        assert r.status_code == 200
        assert victim.get("/api/me").status_code == 401

    # Disabled user cannot log back in; re-enable restores access.
    r = client.post(f"/api/admin/users/{target.id}/enable", headers=_headers(admin_csrf))
    assert r.status_code == 200


def test_cannot_disable_last_system_admin(client, login_as, db):
    csrf = login_as("system_admin")
    from app.users.models import User

    me = db.query(User).filter(User.role == "system_admin").one()
    r = client.post(f"/api/admin/users/{me.id}/disable", headers=_headers(csrf))
    assert r.status_code == 409


def test_cannot_demote_last_system_admin(client, login_as, db):
    csrf = login_as("system_admin")
    from app.users.models import User

    me = db.query(User).filter(User.role == "system_admin").one()
    r = client.patch(
        f"/api/admin/users/{me.id}", json={"role": "user"}, headers=_headers(csrf)
    )
    assert r.status_code == 409


def test_reset_password_flow(client, admin_csrf, app):
    from fastapi.testclient import TestClient

    created = _create(client, admin_csrf, email="reset@goodmit.co.kr").json()
    user_id = created["user"]["id"]

    r = client.post(
        f"/api/admin/users/{user_id}/reset-password", headers=_headers(admin_csrf)
    )
    assert r.status_code == 200
    new_temp = r.json()["temp_password"]
    assert new_temp != created["temp_password"]

    with TestClient(app, raise_server_exceptions=False) as fresh:
        # Old temp password dead, new temp password works.
        old = fresh.post(
            "/login",
            json={"email": "reset@goodmit.co.kr", "password": created["temp_password"]},
        )
        assert old.status_code == 401
        new = fresh.post(
            "/login", json={"email": "reset@goodmit.co.kr", "password": new_temp}
        )
        assert new.status_code == 200
        assert new.json()["must_change_password"] is True


def test_unlock_endpoint(client, admin_csrf, app, settings):
    from fastapi.testclient import TestClient

    created = _create(client, admin_csrf, email="locked@goodmit.co.kr").json()
    temp = created["temp_password"]

    with TestClient(app, raise_server_exceptions=False) as attacker:
        for _ in range(settings.login_max_failures):
            attacker.post(
                "/login", json={"email": "locked@goodmit.co.kr", "password": "Wrong-1x!"}
            )
        locked = attacker.post(
            "/login", json={"email": "locked@goodmit.co.kr", "password": temp}
        )
        assert locked.json()["error"]["code"] == "account_locked"

    r = client.post(
        f"/api/admin/users/{created['user']['id']}/unlock", headers=_headers(admin_csrf)
    )
    assert r.status_code == 200

    with TestClient(app, raise_server_exceptions=False) as fresh:
        assert (
            fresh.post(
                "/login", json={"email": "locked@goodmit.co.kr", "password": temp}
            ).status_code
            == 200
        )


def test_sessions_listing_and_revoke(client, admin_csrf, app, make_user):
    from fastapi.testclient import TestClient

    target = make_user("sess@goodmit.co.kr")
    with TestClient(app, raise_server_exceptions=False) as other:
        other.post(
            "/login", json={"email": "sess@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
        )
        r = client.get(
            f"/api/admin/users/{target.id}/sessions", headers=_headers(admin_csrf)
        )
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1

        r = client.post(
            f"/api/admin/users/{target.id}/revoke-sessions", headers=_headers(admin_csrf)
        )
        assert r.json()["revoked_count"] == 1
        assert other.get("/api/me").status_code == 401


def test_list_sessions_authority_boundary(client, login_as, make_user):
    # admin은 상위 권한(system_admin) 계정의 세션 메타데이터도 조회할 수 없다(정찰 차단).
    target = make_user("sa-target@goodmit.co.kr", role="system_admin")
    admin_csrf = login_as("admin")
    r = client.get(
        f"/api/admin/users/{target.id}/sessions", headers=_headers(admin_csrf)
    )
    assert r.status_code == 403


def test_notion_mapping_verify_returns_status(client, admin_csrf, make_user):
    target = make_user("notion@goodmit.co.kr")
    r = client.post(
        f"/api/admin/users/{target.id}/notion-mapping/verify", headers=_headers(admin_csrf)
    )
    assert r.status_code == 200
    # No mapping workflow configured in this test → unmapped with a clear reason.
    assert r.json()["mapping"]["status"] == "unmapped"


def test_unknown_user_id_404(client, admin_csrf):
    r = client.get("/api/admin/users/no-such-id", headers=_headers(admin_csrf))
    assert r.status_code == 404


def test_patch_admin_role_change_preserves_other_fields(client, admin_csrf, login_as):
    """admin이 역할을 'admin'으로 올리며 이름·부서도 함께 바꾸면, 역할만 승인 대기로 걸리고
    다른 필드가 조용히 유실되던 결함(round16 제품 스윕). 비-role 필드는 즉시 적용돼야 한다."""
    dept_id = client.post(
        "/api/admin/departments", json={"name": "플랫폼팀"}, headers=_headers(admin_csrf)
    ).json()["department"]["id"]
    created = _create(client, admin_csrf, email="promote@goodmit.co.kr").json()["user"]
    r = client.patch(
        f"/api/admin/users/{created['id']}",
        json={"role": "admin", "display_name": "승격 대상", "department_id": dept_id},
        headers=_headers(admin_csrf),
    )
    # 역할 승격은 승인 대기(202)로 걸린다.
    assert r.status_code == 202, r.text
    # 그러나 이름·부서는 즉시 반영돼야 한다(유실 금지).
    detail = client.get(f"/api/admin/users/{created['id']}", headers=_headers(admin_csrf)).json()
    assert detail["display_name"] == "승격 대상", detail
    assert detail["department"] == "플랫폼팀", detail
    assert detail["role"] == "user", detail  # 역할 자체는 아직 승인 전
