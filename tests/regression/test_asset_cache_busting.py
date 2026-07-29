"""정적 파일 주소에 지문이 붙는지.

배포해도 화면이 그대로인 문제가 있었다. nginx와 앱이 정적 파일을 한 시간 캐시하는데
주소가 고정이라 브라우저가 파일이 바뀐 것을 알 수 없었다. 사용자에게 새로고침을
부탁하는 것은 해결이 아니다.
"""

import pytest

pytestmark = pytest.mark.regression


def test_login_page_stamps_its_css_and_js(client):
    html = client.get("/login").text
    # 지문 없이 부르면 배포해도 옛 파일이 그대로 쓰인다.
    assert "/static/css/tokens.css?v=" in html
    assert "/static/css/login.css?v=" in html
    assert "/static/js/login.js?v=" in html
    assert 'href="/static/css/tokens.css"' not in html


def test_stamp_changes_when_the_file_changes(tmp_path):
    from app.core.assets import AssetVersions

    static = tmp_path / "static"
    (static / "css").mkdir(parents=True)
    target = static / "css" / "x.css"
    target.write_text("a{}", encoding="utf-8")

    assets = AssetVersions(static, cache=False)
    first = assets.stamp("/static/css/x.css")
    assert "?v=" in first

    target.write_text("a{color:red}", encoding="utf-8")
    second = assets.stamp("/static/css/x.css")
    assert second != first, "파일이 바뀌면 주소도 바뀌어야 브라우저가 새로 받는다"


def test_stamp_changes_without_restart_in_production_config(tmp_path):
    """운영 설정(cache=True)에서도 파일이 바뀌면 지문이 바뀐다.

    이게 깨졌던 적이 있다. 위 테스트가 cache=False로만 확인해서 통과하는 동안,
    운영은 cache=True라 지문이 프로세스 수명 내내 고정이었다. 그런데
    docs/MAINTENANCE_PLAYBOOK.md §1과 CLAUDE.md §6은 정적 파일만 바꿀 때
    재시작하지 말라고 안내한다. 문서대로 하면 캐시 버스팅이 통째로 무효가 되고
    사용자는 옛 화면을 계속 본다 — 캐시 버스팅을 만든 이유가 바로 그 증상이었다.
    """
    from app.core.assets import AssetVersions

    static = tmp_path / "static"
    (static / "css").mkdir(parents=True)
    target = static / "css" / "y.css"
    target.write_text("a{}", encoding="utf-8")

    assets = AssetVersions(static, cache=True)   # 운영과 같은 설정
    first = assets.stamp("/static/css/y.css")

    # 배포가 파일만 교체한 상황. 프로세스는 살아 있다.
    import os

    target.write_text("a{color:red}", encoding="utf-8")
    stat = target.stat()
    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))

    second = assets.stamp("/static/css/y.css")
    assert second != first, (
        "재시작 없이 파일만 바꿔도 지문이 바뀌어야 한다. "
        "문서가 그렇게 하라고 안내하고, 안 바뀌면 사용자는 옛 화면을 계속 본다."
    )


def test_missing_file_does_not_break_the_page(tmp_path):
    from app.core.assets import AssetVersions

    static = tmp_path / "static"
    static.mkdir()
    assets = AssetVersions(static, cache=False)
    # 지문을 못 만든다고 화면이 죽으면 안 된다. 주소를 그대로 돌려준다.
    assert assets.stamp("/static/css/none.css") == "/static/css/none.css"


def test_stamp_refuses_paths_outside_static(tmp_path):
    from app.core.assets import AssetVersions

    static = tmp_path / "static"
    static.mkdir()
    (tmp_path / "secret.txt").write_text("s", encoding="utf-8")
    assets = AssetVersions(static, cache=False)
    escaped = assets.stamp("/static/../secret.txt")
    assert "?v=" not in escaped, "static 밖의 파일을 지문 대상으로 삼으면 안 된다"


def test_static_html_shell_is_no_store(client):
    """SPA 진입 HTML(/static/react/index.html)은 해시된 자산 주소를 담고 있어 절대 캐시하면
    안 된다 — max-age로 캐시되면 배포로 자산 해시가 바뀌어도 브라우저가 옛 index.html을 붙들어
    옛 번들만 계속 로드한다(실제로 사용자가 옛 번들을 본 원인). 해시 자산은 캐시가 안전하다."""
    r = client.get("/static/react/index.html")
    assert r.headers.get("cache-control") == "no-store"


def test_static_hashed_asset_is_cacheable(client):
    """반대로 내용 해시가 붙은 자산(JS/CSS)은 오래 캐시되어야 한다(주소가 곧 내용이라 안전)."""
    import re
    html = client.get("/static/react/index.html").text
    m = re.search(r"/static/react/assets/[A-Za-z0-9_.-]+\.js", html)
    assert m, "index.html이 해시된 JS 자산을 참조해야 한다"
    r = client.get(m.group(0))
    cc = r.headers.get("cache-control", "")
    assert "max-age" in cc and "no-store" not in cc
