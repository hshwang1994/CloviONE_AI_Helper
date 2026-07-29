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
    from fastapi.testclient import TestClient

    from tests.conftest import DEFAULT_TEST_PASSWORD

    sysadmin_csrf = login_as("system_admin")
    _set_maintenance(client, sysadmin_csrf, True)

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
