import pytest

pytestmark = pytest.mark.integration

MSG_ID = "mm123456789abcdef0123456789abcdef"


def _set_maintenance(client, sysadmin_csrf, on: bool):
    r = client.put(
        "/api/admin/settings/maintenance_mode",
        json={"value": on},
        headers={"X-CSRF-Token": sysadmin_csrf},
    )
    assert r.status_code == 200


def test_maintenance_blocks_regular_user_messages(app, client, login_as, make_user):
    """대화는 **점검 모드를 켜기 전에** 만든다.

    예전에는 켠 뒤에 만들었는데, 그때는 `POST /api/conversations` 가 게이트 밖이라 통과했다.
    이제 그것도 막히므로(그게 맞다) 준비 단계를 앞으로 옮겼다.
    """
    from fastapi.testclient import TestClient

    from tests.conftest import DEFAULT_TEST_PASSWORD

    make_user("blocked@goodmit.co.kr")
    with TestClient(app, raise_server_exceptions=False) as user_client:
        user_client.post(
            "/login",
            json={"email": "blocked@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD},
        )
        csrf = user_client.get("/api/me").json()["csrf_token"]
        conv = user_client.post(
            "/api/conversations", json={}, headers={"X-CSRF-Token": csrf}
        ).json()["conversation"]

        sysadmin_csrf = login_as("system_admin")
        _set_maintenance(client, sysadmin_csrf, True)

        r = user_client.post(
            f"/api/conversations/{conv['id']}/messages",
            json={"content": "점검 중 메시지", "client_message_id": MSG_ID},
            headers={"X-CSRF-Token": csrf},
        )
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "maintenance_mode"


def test_maintenance_allows_operator(app, client, login_as, make_user):
    from fastapi.testclient import TestClient

    from tests.conftest import DEFAULT_TEST_PASSWORD

    sysadmin_csrf = login_as("system_admin")
    _set_maintenance(client, sysadmin_csrf, True)

    make_user("op@goodmit.co.kr", role="operator")
    with TestClient(app, raise_server_exceptions=False) as op_client:
        op_client.post(
            "/login", json={"email": "op@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
        )
        csrf = op_client.get("/api/me").json()["csrf_token"]
        conv = op_client.post(
            "/api/conversations", json={}, headers={"X-CSRF-Token": csrf}
        ).json()["conversation"]
        r = op_client.post(
            f"/api/conversations/{conv['id']}/messages",
            json={"content": "운영자 메시지", "client_message_id": MSG_ID},
            headers={"X-CSRF-Token": csrf},
        )
        assert r.status_code == 202


def test_turning_maintenance_off_restores_access(app, client, login_as, make_user):
    from fastapi.testclient import TestClient

    from tests.conftest import DEFAULT_TEST_PASSWORD

    sysadmin_csrf = login_as("system_admin")
    _set_maintenance(client, sysadmin_csrf, True)
    _set_maintenance(client, sysadmin_csrf, False)

    make_user("restored@goodmit.co.kr")
    with TestClient(app, raise_server_exceptions=False) as user_client:
        user_client.post(
            "/login",
            json={"email": "restored@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD},
        )
        csrf = user_client.get("/api/me").json()["csrf_token"]
        conv = user_client.post(
            "/api/conversations", json={}, headers={"X-CSRF-Token": csrf}
        ).json()["conversation"]
        r = user_client.post(
            f"/api/conversations/{conv['id']}/messages",
            json={"content": "복구 후 메시지", "client_message_id": MSG_ID},
            headers={"X-CSRF-Token": csrf},
        )
        assert r.status_code == 202


# ── 점검 모드가 실제로 막는 범위 (N1/X6) ──────────────────────────────────────
# 게이트가 걸린 곳이 AI 채팅 2개뿐이라, 화면이 "티켓 생성, 변경 등이 차단됩니다" 라고
# 말하는 동안 티켓·게시판·문서·팀채팅은 그대로 열려 있었다. 위 테스트들이 AI 채팅만
# 쳤기 때문에 구조적으로 볼 수 없던 구멍이다. 여기서 대표 경로를 직접 확인한다.
# (전수 커버리지는 tests/security/test_maintenance_coverage.py 가 의존성 그래프로 본다.)


def _user_client(app, make_user, email, role="user"):
    from fastapi.testclient import TestClient

    from tests.conftest import DEFAULT_TEST_PASSWORD

    make_user(email, role=role)
    c = TestClient(app, raise_server_exceptions=False)
    c.post("/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD})
    return c, c.get("/api/me").json()["csrf_token"]


def test_maintenance_blocks_ticket_writes(app, client, login_as, make_user):
    """화면이 예시로 들던 바로 그것 — 티켓 생성."""
    uc, csrf = _user_client(app, make_user, "t-block@goodmit.co.kr")
    with uc:
        _set_maintenance(client, login_as("system_admin"), True)
        r = uc.post(
            "/api/tickets",
            json={"title": "점검 중 티켓", "project_id": "p1"},
            headers={"X-CSRF-Token": csrf},
        )
        assert r.status_code == 503, r.text
        assert r.json()["error"]["code"] == "maintenance_mode"


def test_maintenance_blocks_board_writes(app, client, login_as, make_user):
    uc, csrf = _user_client(app, make_user, "b-block@goodmit.co.kr")
    with uc:
        _set_maintenance(client, login_as("system_admin"), True)
        r = uc.post(
            "/api/board/posts",
            json={"title": "점검 중 글", "body": "본문"},
            headers={"X-CSRF-Token": csrf},
        )
        assert r.status_code == 503, r.text


def test_maintenance_never_blocks_reads(app, client, login_as, make_user):
    """읽기는 막지 않는다 — 점검 중에도 보던 것은 볼 수 있어야 한다.

    라우터 단위로 게이트를 걸었으므로 이 확인이 없으면 GET 까지 503 이 될 수 있다.
    """
    uc, _ = _user_client(app, make_user, "r-ok@goodmit.co.kr")
    with uc:
        _set_maintenance(client, login_as("system_admin"), True)
        for path in ("/api/tickets/mine", "/api/board/posts", "/api/trash"):
            assert uc.get(path).status_code == 200, f"{path} 읽기가 막혔다"
