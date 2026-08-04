import pytest

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration


def test_login_page_renders(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "로그인" in r.text
    # 워드마크는 인라인 SVG다(_wordmark.html). 한때 이 줄이 파일 이름
    # "clovirone-wordmark"를 핀으로 잡았는데, 그건 브랜드가 **읽히는지**가 아니라
    # 어떤 파일을 골랐는지를 검사한 것이었다. 파일을 고르는 방식이 바로 두 번 틀린 원인이다
    # (흰 카드에 흰 글자 → 고친 뒤 다크 카드에 어두운 글자, 둘 다 대비 1.00).
    # 지금은 글자가 currentColor를 따르므로 면이 바뀌어도 따라간다. 검사할 것은 이름의 존재다.
    assert 'class="wordmark' in r.text, "브랜드 워드마크가 렌더되지 않았다"
    assert "ClovirAssist" in r.text, "브랜드 이름이 화면에 없다"


def test_login_page_redirects_when_already_authenticated(client, login_as):
    login_as("user")
    r = client.get("/login", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"


def test_index_serves_react_shell_for_authenticated_user(client, make_user):
    # 홈(채팅)은 이제 React 셸이 서빙한다. 이름·데이터는 React가 /api/me로 채우므로 HTML엔
    # 없다 — 셸이 맞게 왔는지(root 컨테이너 + 번들 스크립트)와 no-store만 확인한다.
    make_user("home@goodmit.co.kr", display_name="홈사용자")
    client.post("/login", json={"email": "home@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD})
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert 'id="root"' in r.text
    assert "/static/react/assets/" in r.text
    assert r.headers.get("Cache-Control") == "no-store"


def test_index_redirects_must_change_user_to_change_password(client, make_user):
    make_user("mustchange@goodmit.co.kr", must_change_password=True)
    client.post(
        "/login",
        json={"email": "mustchange@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD},
    )
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/change-password"


def test_change_password_page_renders(client, login_as):
    login_as("user")
    r = client.get("/change-password")
    assert r.status_code == 200
    assert "비밀번호 변경" in r.text


def test_static_files_served_with_cache_header(client):
    r = client.get("/static/css/tokens.css")
    assert r.status_code == 200
    assert r.headers["Cache-Control"] == "public, max-age=3600"
