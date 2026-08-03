"""워드마크는 놓인 면의 색을 따라간다.

같은 함정을 반대 방향으로 두 번 밟았다:
  1차 — 흰 글자 워드마크(clovirone-wordmark.svg)를 흰 카드에 얹어 브랜드 이름이 안 보였다.
        고치려고 어두운 글자 파일(-dark.svg)로 바꿨다.
  2차 — 비밀번호 변경 화면에 테마를 적용하자 카드가 잉크색(#141B34)이 되면서 그 어두운
        글자(#141B34)가 대비 1.00으로 묻혔다. 1차 수정이 2차 결함을 만든 것이다.

원인은 색이 아니라 **구조**다. `<img src>`로 넣은 SVG는 CSS가 안쪽에 닿지 못해서, 면이
바뀔 때마다 사람이 파일을 골라 끼워야 했다. 고르는 한 세 번째가 온다.

지금은 인라인 SVG(_wordmark.html)라 글자가 currentColor를 따르고 CSS가 면에 맞춰 정한다.
이 테스트는 그 구조가 유지되는지 본다 — 파일 이름이 아니라.
"""

import re

import pytest

pytestmark = pytest.mark.regression

_LOGO_PAGES = [("/login", None), ("/change-password", "user")]


def _page(client, login_as, path, role):
    if role:
        login_as(role)
    r = client.get(path)
    assert r.status_code == 200, f"{path} → {r.status_code}"
    return r.text


@pytest.mark.parametrize("path,role", _LOGO_PAGES)
def test_wordmark_is_inline_so_css_can_color_it(client, login_as, path, role):
    html = _page(client, login_as, path, role)
    assert 'class="wordmark' in html, f"{path}: 워드마크가 인라인 SVG로 렌더되지 않았다"
    assert 'fill="currentColor"' in html, (
        f"{path}: 글자가 currentColor를 안 쓴다 — 면이 바뀌면 또 묻힌다"
    )


@pytest.mark.parametrize("path,role", _LOGO_PAGES)
def test_wordmark_does_not_pin_a_theme_specific_file(client, login_as, path, role):
    """파일을 고르는 방식으로 돌아가면 이 테스트가 먼저 깨진다."""
    html = _page(client, login_as, path, role)
    for banned in ("clovirone-wordmark.svg", "clovirone-wordmark-dark.svg"):
        assert banned not in html, (
            f"{path}: {banned}를 다시 끼웠다. 면이 바뀌면 사람이 그때마다 골라야 하고, "
            "그래서 두 번 틀렸다. CSS가 색을 정하게 두어라."
        )


def test_wordmark_glyph_color_is_not_hardcoded_in_the_partial():
    """부제까지 포함해 색이 토큰에서 와야 한다."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    svg = (root / "app" / "templates_html" / "_wordmark.html").read_text(encoding="utf-8")
    body = re.sub(r"\{#.*?#\}", "", svg, flags=re.S)   # 주석의 설명은 색이 아니다
    text_fills = re.findall(r'<text[^>]*fill="([^"]+)"', body)
    assert text_fills == ["currentColor"], f"글자 색이 고정돼 있다: {text_fills}"
    # 마크의 색은 브랜드 자산이라 어느 면에서도 같아야 한다 — 이건 의도된 고정이다.
    # (2026-08 재설계로 마크가 4색 사각형에서 네잎클로버 그라디언트로 바뀌었다. 모양을
    #  고정하던 옛 단언 대신, '고정된 브랜드 색이 실제로 들어 있는지'라는 원래 의도를 본다.)
    stop_colors = re.findall(r'stop-color="(#[0-9A-Fa-f]{6})"', body)
    assert len(stop_colors) >= 4, f"브랜드 마크 색이 비었다: {stop_colors}"


def test_login_and_spa_draw_the_same_brand_mark():
    """로그인 전후로 로고가 달라지면 안 된다.

    로그인은 이 Jinja 파셜을, 로그인 이후 SPA는 frontend/src/ui/BrandLogo.jsx를 쓴다.
    실제로 한동안 한쪽은 4색 사각형, 다른 쪽은 네잎클로버를 그리고 있었다 — 사용자 입장에서는
    로그인했더니 다른 서비스로 넘어온 것처럼 보인다. 두 파일이 같은 path를 쓰는지 본다.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    jinja = (root / "app" / "templates_html" / "_wordmark.html").read_text(encoding="utf-8")
    spa = (root / "frontend" / "src" / "ui" / "BrandLogo.jsx").read_text(encoding="utf-8")
    # 클로버 잎 하나의 path — 마크의 정체성이다. 네 잎은 이걸 회전해 쓴다.
    leaf = "M64 64C56 54 38 50 34 33C30 17 42 7 54 11C60 13 63 18 64 24"
    assert leaf in jinja, "로그인 워드마크가 새 클로버 마크를 쓰지 않는다"
    assert leaf in spa, "SPA 로고가 새 클로버 마크를 쓰지 않는다"
