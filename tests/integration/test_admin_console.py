import pytest

pytestmark = pytest.mark.integration


def test_admin_page_renders_for_operator(client, login_as):
    login_as("operator")
    r = client.get("/admin")
    assert r.status_code == 200
    # /admin은 이제 React 콘솔 셸을 서빙한다(제목 '관리자 콘솔', root 컨테이너, 외부 번들).
    assert "관리자 콘솔" in r.text
    assert 'id="root"' in r.text
    assert "/static/react/assets/" in r.text
    # CSP compliance: 인라인 스크립트/핸들러 없음(외부 번들만).
    assert "onclick=" not in r.text.lower()
    assert r.headers.get("Cache-Control") == "no-store"


def test_admin_page_renders_for_all_privileged_roles(client, login_as):
    for role in ["operator", "admin", "auditor", "system_admin"]:
        login_as(role, email=f"{role}-console@goodmit.co.kr")
        assert client.get("/admin").status_code == 200


def test_regular_user_redirected_from_admin(client, make_user):
    from tests.conftest import DEFAULT_TEST_PASSWORD

    make_user("plain@goodmit.co.kr")
    client.post("/login", json={"email": "plain@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD})
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"


def test_unauthenticated_admin_redirects_to_login(client):
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code == 303
    # ?next=/admin lets login() send the user back to /admin after they sign in
    # (app/main.py PageAuthRequired handler) instead of always dropping them on "/".
    assert r.headers["location"] == "/login?next=%2Fadmin"


def test_must_change_password_redirected(client, make_user):
    from tests.conftest import DEFAULT_TEST_PASSWORD

    make_user("mc-admin@goodmit.co.kr", role="admin", must_change_password=True)
    client.post("/login", json={"email": "mc-admin@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD})
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/change-password"


def test_operator_can_open_admin_console(client, login_as):
    # 사용자/관리자 전환은 이제 React가 클라이언트에서 그린다(HTML 링크 아님). 운영자가
    # 실제로 관리자 콘솔에 들어갈 수 있는지는 /admin 200으로 확인한다.
    login_as("operator")
    assert client.get("/admin").status_code == 200


def test_regular_user_cannot_reach_admin(client, make_user):
    # 일반 사용자의 관리자 차단은 링크 숨김이 아니라 서버 리다이렉트로 강제된다(권한은 서버가 판단).
    from tests.conftest import DEFAULT_TEST_PASSWORD

    make_user("nolink@goodmit.co.kr")
    client.post("/login", json={"email": "nolink@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD})
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"
