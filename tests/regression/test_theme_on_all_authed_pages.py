"""로그인 이후 화면은 전부 테마를 따라간다.

비밀번호 변경 화면만 테마 적용 스크립트가 없어서, 다크로 쓰던 사용자가 그 화면에 가면
흰 화면을 맞았다. 채팅 → (흰 화면) → 채팅으로 돌아오는 꼴이었다. 첫 로그인한 신규
사용자가 반드시 거치는 화면이라 더 나빴다.

원인은 테마 로직이 chat.js와 admin/app.js에 복붙돼 있었고 이 화면만 빠진 것이다.
공용 theme.js로 뽑았고, 새 화면이 생길 때 같은 일이 반복되지 않도록 여기서 못 박는다.

로그인 화면은 대상이 아니다 — 인증 전이고 히어로가 라이트 고정으로 설계돼 있다.
"""

import pytest

pytestmark = pytest.mark.regression


def test_change_password_page_applies_the_stored_theme(client, login_as):
    login_as("user")
    html = client.get("/change-password").text
    assert "/static/js/theme.js" in html, (
        "비밀번호 변경 화면이 테마를 적용하지 않으면 다크 사용자가 흰 화면을 맞는다"
    )


def test_login_page_does_not_theme_itself(client):
    """로그인 화면은 인증 전이라 라이트 고정이다. 히어로가 그 전제로 설계돼 있다."""
    html = client.get("/login").text
    assert "/static/js/theme.js" not in html
