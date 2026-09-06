"""qa-contract-change: notion-mapping 자동 조회(/verify)가 S11 로 사라졌다. 그 응답 모양을 보던 단언을 「라우트가 없다(404)」로 바꿨다 — 남겨 두면 눌러도 아무 일도 안 일어나는 버튼이 된다. 단언 하나가 줄었지만 지키는 것은 더 강해졌다: 상태 값이 아니라 존재 자체를 못 박는다."""

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


def test_notion_mapping_verify_is_gone(client, admin_csrf, make_user):
    """자동 조회는 n8n 워크플로가 하던 일이라 S11 이 걷어냈다. 남긴 채로 두면
    「눌러도 아무 일도 안 일어나는 버튼」이 된다 — 라우트 자체가 없어야 한다."""
    target = make_user("notion@goodmit.co.kr")
    r = client.post(
        f"/api/admin/users/{target.id}/notion-mapping/verify", headers=_headers(admin_csrf)
    )
    assert r.status_code == 404


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


# ── P-61: 「부서 없음」 센티널 ───────────────────────────────────────────────
#
# 조직 콘솔의 「부서 미지정 N명」 타일이 그 사람들만 거른 사용자 목록을 열어야 한다.
# `department_id` 는 등호 비교뿐이라 IS NULL 을 말할 수 없었고, 페이지로 나뉜 목록을
# 화면에서 거르면 첫 쪽 밖 인원이 빠진 거짓 목록이 된다 — 그래서 서버가 센티널을 받는다.

def _seed_department_mix(client, csrf):
    """부서 없는 둘 + 부서 있는 하나. 이메일 앞머리(`nodept-`)로 세 사람만 골라낼 수 있다."""
    r = client.post("/api/admin/departments", json={"name": "센티널팀"}, headers=_headers(csrf))
    assert r.status_code == 201, r.text
    dept_id = r.json()["department"]["id"]
    for i in (1, 2):
        r = _create(client, csrf, email=f"nodept-{i}@goodmit.co.kr", display_name=f"미배정{i}")
        assert r.status_code == 201, r.text
    r = _create(
        client, csrf, email="nodept-3@goodmit.co.kr", display_name="배정됨", department_id=dept_id
    )
    assert r.status_code == 201, r.text
    return dept_id


def test_department_none_sentinel_lists_only_users_without_a_department(client, admin_csrf):
    dept_id = _seed_department_mix(client, admin_csrf)

    r = client.get(
        "/api/admin/users", params={"q": "nodept-", "department_id": "none"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert sorted(u["email"] for u in body["items"]) == [
        "nodept-1@goodmit.co.kr", "nodept-2@goodmit.co.kr",
    ]
    assert [u["department_id"] for u in body["items"]] == [None, None]

    # q 없이도 같은 조건이다 — 부서가 없는 관리자 자신은 들어오고, 부서가 있는 사람은 빠진다.
    r = client.get(
        "/api/admin/users", params={"department_id": "none"}, headers=_headers(admin_csrf)
    )
    assert r.status_code == 200, r.text
    emails = {u["email"] for u in r.json()["items"]}
    assert "admin@goodmit.co.kr" in emails
    assert "nodept-3@goodmit.co.kr" not in emails

    # 오탐 방지 — 실제 부서 id 는 예전처럼 그 부서 사람만 돌려준다.
    r = client.get(
        "/api/admin/users", params={"q": "nodept-", "department_id": dept_id},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 1
    assert [u["email"] for u in r.json()["items"]] == ["nodept-3@goodmit.co.kr"]


def test_department_none_sentinel_also_applies_to_csv_export(client, admin_csrf):
    """목록과 CSV 가 같은 문장을 쓴다 — 화면에서 미배정만 걸고 내보냈는데 파일에 전원이
    담기면 안 된다."""
    import csv
    import io

    _seed_department_mix(client, admin_csrf)
    params = {"q": "nodept-", "department_id": "none"}
    listed = sorted(
        u["email"]
        for u in client.get(
            "/api/admin/users", params=params, headers=_headers(admin_csrf)
        ).json()["items"]
    )

    r = client.get("/api/admin/users/export/csv", params=params, headers=_headers(admin_csrf))
    assert r.status_code == 200, r.text
    rows = list(csv.reader(io.StringIO(r.text.lstrip("\ufeff"))))
    header, data = rows[0], rows[1:]
    assert header[0] == "이메일"
    assert len(data) == 2
    assert sorted(row[0] for row in data) == listed
    assert listed == ["nodept-1@goodmit.co.kr", "nodept-2@goodmit.co.kr"]
    assert "nodept-3@goodmit.co.kr" not in r.text


# ── 같은 이메일 동시 생성 (users-01 / xd-01) ─────────────────────────────────
#
# 직렬 중복은 409 인데 경합에서만 IntegrityError 가 그대로 500 으로 샜다. 사전 검사
# (`get_user_by_email`)는 검사 시점의 사실이라, 같은 이메일 두 요청이 겹치면 둘 다 그
# 검사를 통과하고 진 쪽의 INSERT 가 `ix_users_email` 에 걸린다. 부서·직책·조직 생성이
# 이미 쓰는 SAVEPOINT 관용구(app/org/service.py::create_item)를 여기에도 건다.
#
# 실제 스레드 대신 유니크 위반을 주입하는 이유는 tests/fakes/pgerrors.py 가 설명한다 —
# 판정 기준이 SQLSTATE 라, 그 값을 실은 예외 하나면 이 경로를 정확히 태울 수 있다.

def _losing_add(exc):
    def _add(_instance):
        raise exc
    return _add


def test_losing_an_email_insert_race_answers_like_the_serial_duplicate(
    db, settings, monkeypatch
):
    from app.core.errors import ConflictError
    from app.users.service import create_user
    from tests.fakes.pgerrors import unique_violation

    monkeypatch.setattr(
        db, "add",
        _losing_add(unique_violation("INSERT INTO users", constraint="ix_users_email")),
    )

    with pytest.raises(ConflictError) as caught:
        create_user(
            db, email="race@goodmit.co.kr", display_name="레이스",
            password=DEFAULT_TEST_PASSWORD, settings=settings, actor_role="system_admin",
        )
    # 조금 늦게 도착한 요청(사전 검사에서 걸린 쪽)과 **같은 문구**여야 한다.
    assert caught.value.message == "이미 등록된 이메일입니다."


def test_a_foreign_key_violation_is_not_disguised_as_a_duplicate(db, settings, monkeypatch):
    """반대 방향 증명 — 이메일 유니크가 아닌 위반은 경합이 아니라 데이터 버그다(D-191).

    여기서 삼키면 FK 버그가 "가끔 409" 로 위장하고 영영 안 보인다.
    """
    from sqlalchemy.exc import IntegrityError

    from app.users.service import create_user
    from tests.fakes.pgerrors import foreign_key_violation

    monkeypatch.setattr(db, "add", _losing_add(foreign_key_violation("INSERT INTO users")))

    with pytest.raises(IntegrityError):
        create_user(
            db, email="fk@goodmit.co.kr", display_name="에프케이",
            password=DEFAULT_TEST_PASSWORD, settings=settings, actor_role="system_admin",
        )


def test_losing_the_race_to_an_archived_account_still_offers_the_restore(
    client, admin_csrf, make_user, db, settings, monkeypatch
):
    """진 쪽은 **이긴 행을 읽어** 안내를 고른다 — 보관된 계정이 그 주소를 쥐고 있으면
    다음 행동(복구)까지 알려 준다. 사전 검사가 이미 그렇게 답하므로 경합도 같아야 한다.

    사전 검사를 한 번만 '못 본 것'으로 만들어 경합을 정확히 재현한다: 이긴 쪽이 우리
    검사 직후에 커밋한 상황이다.
    """
    import app.users.service as service
    from app.users.service import ArchivedEmailConflictError
    from tests.fakes.pgerrors import unique_violation

    target = make_user("raced-archive@goodmit.co.kr")
    assert client.post(
        f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf)
    ).status_code == 200

    real = service.get_user_by_email
    seen = []

    def _blind_first_call(session, email):
        seen.append(email)
        return None if len(seen) == 1 else real(session, email)

    monkeypatch.setattr(service, "get_user_by_email", _blind_first_call)
    monkeypatch.setattr(
        db, "add",
        _losing_add(unique_violation("INSERT INTO users", constraint="ix_users_email")),
    )

    with pytest.raises(ArchivedEmailConflictError) as caught:
        service.create_user(
            db, email="raced-archive@goodmit.co.kr", display_name="다시 온 사람",
            password=DEFAULT_TEST_PASSWORD, settings=settings, actor_role="system_admin",
        )
    assert caught.value.details["archived_user_id"] == target.id


def test_an_ordinary_create_still_succeeds(client, admin_csrf):
    """오탐 방지 — 경합 처리를 넣었다고 평범한 생성이 막히면 안 된다."""
    r = _create(client, admin_csrf, email="not-a-race@goodmit.co.kr")
    assert r.status_code == 201, r.text
    assert r.json()["user"]["email"] == "not-a-race@goodmit.co.kr"


# ── 부서와 소속 종류는 언제나 같은 말을 한다 (users-02) ──────────────────────
#
# 관계(`department_ref`)에 대입한 값은 flush 전까지 FK 컬럼에 안 들어간다. 그 컬럼을 읽어
# 소속 종류를 정하고 있어서, 부서를 비워도 `membership_kind` 가 'department' 로 남았다 —
# 그 사람 화면의 「소속 미지정」 안내가 뜨지 않아, 조직 데이터가 전부 비어 있는데 이유를
# 알려 주는 줄이 어디에도 없는 상태가 된다.

def _make_department(client, csrf, name):
    r = client.post("/api/admin/departments", json={"name": name}, headers=_headers(csrf))
    assert r.status_code == 201, r.text
    return r.json()["department"]["id"]


def test_clearing_the_department_turns_the_membership_kind_to_unassigned(client, admin_csrf, db):
    from app.audit.models import AuditLog

    dept_id = _make_department(client, admin_csrf, "소속검사팀")
    created = _create(
        client, admin_csrf, email="membership@goodmit.co.kr", department_id=dept_id
    ).json()["user"]
    assert created["membership_kind"] == "department"

    r = client.patch(
        f"/api/admin/users/{created['id']}",
        json={"department_id": None},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200, r.text
    assert r.json()["user"]["department_id"] is None
    assert r.json()["user"]["membership_kind"] == "unassigned"

    detail = client.get(
        f"/api/admin/users/{created['id']}", headers=_headers(admin_csrf)
    ).json()
    assert detail["membership_kind"] == "unassigned"

    # 감사 기록도 사실과 같아야 한다 — "누가 이 계정을 어디에 붙였나" 를 되짚는 근거다.
    row = db.query(AuditLog).filter(
        AuditLog.action == "user.update", AuditLog.object_id == created["id"]
    ).one()
    assert '"membership_kind": "unassigned"' in row.after_json


def test_assigning_a_department_turns_the_membership_kind_to_department(client, admin_csrf):
    """반대 방향 — 부서를 주면 그 즉시 부서 소속이다(같은 자리, 같은 함정)."""
    dept_id = _make_department(client, admin_csrf, "소속검사팀2")
    created = _create(client, admin_csrf, email="membership2@goodmit.co.kr").json()["user"]
    assert created["membership_kind"] == "unassigned"

    r = client.patch(
        f"/api/admin/users/{created['id']}",
        json={"department_id": dept_id},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200, r.text
    assert r.json()["user"]["membership_kind"] == "department"


def test_clearing_the_department_and_declaring_organization_in_one_request(client, admin_csrf):
    """한 요청에 둘을 함께 보내면 **사람이 명시한 값**이 이긴다 — 옛 FK 값을 읽던 시절에는
    "부서가 배정된 계정은 부서 소속입니다" 로 거절당했다."""
    dept_id = _make_department(client, admin_csrf, "소속검사팀3")
    created = _create(
        client, admin_csrf, email="membership3@goodmit.co.kr", department_id=dept_id
    ).json()["user"]

    r = client.patch(
        f"/api/admin/users/{created['id']}",
        json={"department_id": None, "membership_kind": "organization"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200, r.text
    assert r.json()["user"]["membership_kind"] == "organization"


def test_a_contradicting_membership_kind_is_still_refused(client, admin_csrf):
    """오탐 방지 — 부서를 그대로 둔 채 조직 직속으로 바꾸는 모순은 여전히 422 다."""
    dept_id = _make_department(client, admin_csrf, "소속검사팀4")
    created = _create(
        client, admin_csrf, email="membership4@goodmit.co.kr", department_id=dept_id
    ).json()["user"]

    r = client.patch(
        f"/api/admin/users/{created['id']}",
        json={"membership_kind": "organization"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422, r.text


# ── 모르는 소속 종류는 생성도 거절한다 (xb-13) ───────────────────────────────

def test_create_refuses_an_unknown_membership_kind(client, admin_csrf):
    """수정은 422 인데 생성만 조용히 '미지정' 으로 바꿨다 — 보낸 쪽은 자기 값이 저장됐다고
    믿고 화면은 다른 상태를 그린다."""
    r = _create(
        client, admin_csrf, email="badkind@goodmit.co.kr", membership_kind="__nope__"
    )
    assert r.status_code == 422, r.text
    assert "소속 종류" in r.json()["error"]["message"]


def test_create_still_accepts_a_known_membership_kind(client, admin_csrf):
    r = _create(
        client, admin_csrf, email="goodkind@goodmit.co.kr", membership_kind="organization"
    )
    assert r.status_code == 201, r.text
    assert r.json()["user"]["membership_kind"] == "organization"


# ── 모르는 필터 값은 조용히 삼키지 않는다 (xa-11) ────────────────────────────
#
# `role=foo` 는 422 인데 `department_id=garbage` 는 200 빈 목록이었다. 빈 목록은 화면에서
# 「일치하는 항목이 없습니다」로 보이고, 그것은 「그 부서에 사람이 없다」와 구별되지 않는다.

def test_an_unknown_department_filter_is_refused(client, admin_csrf):
    r = client.get(
        "/api/admin/users", params={"department_id": "garbage"}, headers=_headers(admin_csrf)
    )
    assert r.status_code == 422, r.text
    assert "부서" in r.json()["error"]["message"]


def test_an_unknown_title_filter_is_refused(client, admin_csrf):
    r = client.get(
        "/api/admin/users", params={"title_id": "garbage"}, headers=_headers(admin_csrf)
    )
    assert r.status_code == 422, r.text
    assert "직책" in r.json()["error"]["message"]


def test_an_unknown_department_filter_is_refused_on_the_csv_export_too(client, admin_csrf):
    """목록과 CSV 는 같은 문장을 쓴다 — 한쪽만 막으면 그 계약이 깨진다."""
    r = client.get(
        "/api/admin/users/export/csv", params={"department_id": "garbage"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422, r.text


def test_known_department_filters_still_work(client, admin_csrf):
    """오탐 방지 — 실재하는 부서 id 와 `none` 센티널은 그대로 200 이다."""
    dept_id = _make_department(client, admin_csrf, "필터검사팀")
    assert _create(
        client, admin_csrf, email="filter-1@goodmit.co.kr", department_id=dept_id
    ).status_code == 201

    r = client.get(
        "/api/admin/users", params={"department_id": dept_id}, headers=_headers(admin_csrf)
    )
    assert r.status_code == 200, r.text
    assert [u["email"] for u in r.json()["items"]] == ["filter-1@goodmit.co.kr"]

    r = client.get(
        "/api/admin/users", params={"department_id": "none"}, headers=_headers(admin_csrf)
    )
    assert r.status_code == 200, r.text


# ── 관리 범위가 안 쓰는 대상 id (xb-19) ──────────────────────────────────────

def test_a_target_org_the_scope_does_not_use_is_refused(client, admin_csrf, make_user):
    """전역 범위는 대상 id 를 안 쓴다. 조용히 None 으로 덮으면 보낸 쪽은 저장됐다고 믿는다."""
    target = make_user("scope-noise@goodmit.co.kr", role="admin")
    r = client.patch(
        f"/api/admin/users/{target.id}",
        json={"admin_scope": "global", "scope_org_id": "00000000-0000-4000-8000-00000000dead"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422, r.text
    assert "대상 조직" in r.json()["error"]["message"]


def test_a_target_dept_the_scope_does_not_use_is_refused(client, admin_csrf, make_user):
    target = make_user("scope-noise2@goodmit.co.kr", role="admin")
    dept_id = _make_department(client, admin_csrf, "범위잡음팀")
    r = client.patch(
        f"/api/admin/users/{target.id}",
        json={"admin_scope": "global", "scope_dept_id": dept_id},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422, r.text
    assert "대상 부서" in r.json()["error"]["message"]


def test_an_inactive_department_cannot_become_a_management_scope(client, admin_csrf, make_user):
    """비활성 부서는 사람에게 배정할 수 없다(resolve_assignable) — 관리 범위도 같다."""
    dept_id = _make_department(client, admin_csrf, "폐지될팀")
    assert client.patch(
        f"/api/admin/departments/{dept_id}", json={"active": False},
        headers=_headers(admin_csrf),
    ).status_code == 200

    target = make_user("scope-dead-dept@goodmit.co.kr", role="admin")
    r = client.patch(
        f"/api/admin/users/{target.id}",
        json={"admin_scope": "dept", "scope_dept_id": dept_id},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422, r.text
    assert "비활성" in r.json()["error"]["message"]


def test_an_active_department_is_still_accepted_as_a_management_scope(
    client, admin_csrf, make_user
):
    """오탐 방지 — 살아 있는 부서로 범위를 좁히는 것은 그대로 동작해야 한다."""
    dept_id = _make_department(client, admin_csrf, "살아있는팀")
    target = make_user("scope-live-dept@goodmit.co.kr", role="admin")

    r = client.patch(
        f"/api/admin/users/{target.id}",
        json={"admin_scope": "dept", "scope_dept_id": dept_id},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200, r.text
    assert r.json()["user"]["scope_dept_id"] == dept_id

    # 그 부서가 나중에 비활성이 돼도 **이미 걸린 범위**를 다시 보내는 것은 막지 않는다 —
    # 안 그러면 그 관리자의 이름 한 줄 고치는 저장이 통째로 막힌다.
    assert client.patch(
        f"/api/admin/departments/{dept_id}", json={"active": False},
        headers=_headers(admin_csrf),
    ).status_code == 200
    r = client.patch(
        f"/api/admin/users/{target.id}",
        json={"admin_scope": "dept", "scope_dept_id": dept_id, "display_name": "이름만 변경"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200, r.text
