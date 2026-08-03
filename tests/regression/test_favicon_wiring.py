"""파비콘은 파일이 있는 것과 걸려 있는 것이 다르다.

전체 사이즈의 파비콘 세트(ico/16/32/48/64/apple-touch/android-chrome)가 디스크에 다 있는데
`<link rel="icon">` 한 줄만 걸려 있던 적이 있다. 파일이 있으니 "됐다"고 보이지만, 실제로는
탭 아이콘이 흐리게 나오고 모바일 홈화면 추가는 기본 아이콘으로 떨어진다.

그래서 이 테스트는 세 가지를 따로 본다:
  1. HTML에 링크가 걸려 있는가            (걸었나)
  2. 그 경로의 파일이 실제로 있는가        (가리키는 곳이 있나)
  3. SPA 셸과 서버 렌더 페이지가 같은 세트를 쓰는가  (한쪽만 고치는 실수 방지)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.regression

ROOT = Path(__file__).resolve().parents[2]
BRAND = ROOT / "app" / "static" / "brand"
SPA_SHELL = ROOT / "app" / "static" / "react" / "index.html"


def _disk_path(url: str) -> Path:
    """URL /static/... 은 app/static/... 에서 서빙된다(app/main.py의 StaticFiles 마운트)."""
    return ROOT / "app" / Path(url.lstrip("/"))

REQUIRED_HREFS = [
    "/static/brand/favicon/favicon.ico",
    "/static/brand/favicon/favicon-32x32.png",
    "/static/brand/favicon/favicon-16x16.png",
    "/static/brand/favicon/apple-touch-icon.png",
    "/static/brand/site.webmanifest",
]


def _hrefs(html: str) -> set[str]:
    """asset() 캐시버스팅 쿼리(?v=...)를 떼고 순수 경로만 본다."""
    found = set()
    for m in re.finditer(r'href="([^"]+)"', html):
        found.add(m.group(1).split("?")[0])
    return found


def test_server_rendered_pages_link_the_full_icon_set(client):
    html = client.get("/login").text
    hrefs = _hrefs(html)
    missing = [h for h in REQUIRED_HREFS if h not in hrefs]
    assert not missing, f"/login에 안 걸린 아이콘 링크: {missing}"


@pytest.mark.skipif(not SPA_SHELL.exists(), reason="SPA 셸이 아직 빌드되지 않음")
def test_spa_shell_links_the_same_icon_set():
    """Vite base가 /static/react/ 라서 경로가 다시 쓰이면 여기서 잡힌다."""
    html = SPA_SHELL.read_text(encoding="utf-8")
    hrefs = _hrefs(html)
    missing = [h for h in REQUIRED_HREFS if h not in hrefs]
    assert not missing, (
        f"빌드된 SPA 셸에 안 걸렸거나 경로가 다시 쓰인 링크: {missing}. "
        f"셸에 있는 href: {sorted(h for h in hrefs if 'brand' in h or 'favicon' in h)}"
    )


def test_every_linked_icon_file_exists_on_disk():
    for href in REQUIRED_HREFS:
        path = _disk_path(href)
        assert path.exists(), f"링크는 있는데 파일이 없다: {href} → {path}"


def test_webmanifest_is_valid_and_its_icons_exist():
    manifest_path = BRAND / "site.webmanifest"
    assert manifest_path.exists(), "site.webmanifest가 없다"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data.get("name") and data.get("short_name"), "manifest에 이름이 없다"
    icons = data.get("icons") or []
    assert icons, "manifest에 아이콘이 하나도 없다"
    for icon in icons:
        src = icon["src"]
        path = _disk_path(src)
        assert path.exists(), f"manifest가 없는 파일을 가리킨다: {src}"
