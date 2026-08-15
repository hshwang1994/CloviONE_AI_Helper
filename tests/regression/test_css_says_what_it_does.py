"""CSS 주석은 CSS가 실제로 하는 일을 말해야 한다.

주석은 실행되지 않으므로 조용히 썩는다. 이 저장소에서 실제로 세 번 썩었다:

  1. `--sidebar-active-fg /* 6.51 */` — 실제 5.24. 6.51은 어느 면에서도 나온 적이 없다.
  2. `--sidebar-muted /* 5.09 */` — 5.09는 **배지 틴트 위**에서 계산한 값이다(그 주석은 옳다).
     사이드바가 흰 면이 되면서 같은 토큰의 대비가 6.01로 바뀌었는데 숫자는 배지에서
     복사돼 남았다. **다른 면에서 잰 값을 옮겨 적은 것**이 이 결함의 정체다.
  3. `--sidebar-text /* 21.0 */` — 21.0은 순수 흑백(#000 on #FFF)에서만 나오는 이론 최대치다.
     #333333은 흰 면에서 12.63이 최대다. 잉크 시절(16.99)의 값도 아니다.

그래서 이 테스트는 **주석의 숫자를 사람이 관리하지 않는다**. tokens.css에서 색을 직접 읽어
WCAG 대비를 계산하고, 주석이 그 값과 다르면 실패한다. 색을 바꾸면 주석도 같이 고치라고
말해 주는 것이 목적이다.

`숫자를 손으로 고치지 말고, 색을 바꿨으면 이 테스트가 시키는 값을 넣어라.`
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.regression

ROOT = Path(__file__).resolve().parents[2]
CSS_DIR = ROOT / "app" / "static" / "css"
TOKENS = CSS_DIR / "tokens.css"


# ---------- WCAG 2.x 대비 ----------
# 입력은 hex뿐이라 채널은 0~255다. (color-mix는 브라우저가 0~1 실수로 돌려주지만
# 여기서는 CSS 소스를 직접 읽으므로 그 함정에 걸리지 않는다. 알파만 0~1이다.)

def _lin(c8: float) -> float:
    c = c8 / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _rgb(hx: str) -> tuple[float, float, float]:
    h = hx.lstrip("#")
    return tuple(float(int(h[i:i + 2], 16)) for i in (0, 2, 4))  # type: ignore[return-value]


def _lum(rgb: tuple[float, float, float]) -> float:
    r, g, b = rgb
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(fg: tuple[float, float, float], bg: tuple[float, float, float]) -> float:
    a, b = _lum(fg), _lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def composite(fg: tuple[float, float, float], alpha: float,
              bg: tuple[float, float, float]) -> tuple[float, float, float]:
    """알파 합성. alpha는 0~1이다(색 채널만 0~255).

    합성 결과를 **정수 채널로 반올림**한다. 브라우저가 그렇게 그리기 때문이다.
    이 선택은 추측이 아니라 검증했다 — 이미 옳다고 확인된 틴트 주석 세 개에 두 모델을
    모두 대 보면 정수 모델만 전부 맞는다:
        --badge-neutral-fg 라이트 12%  주석 5.09 → 정수 5.0855 / 실수 5.0984
        --badge-info-fg    라이트 14%  주석 4.99 → 정수 4.9913 / 실수 5.0051
        --badge-info-fg    다크  14%  주석 5.27 → 정수 5.2729 / 실수 5.2990
    실수 모델은 셋 다 0.01~0.03씩 빗나간다. 소수 둘째 자리를 다투는 값이라 모델이 곧 답이다.
    """
    return tuple(round(alpha * fg[i] + (1 - alpha) * bg[i]) for i in range(3))  # type: ignore[return-value]


# ---------- tokens.css 파싱 ----------

_BLOCK_RE = {
    "light": re.compile(r"^:root\s*\{(.*?)^\}", re.S | re.M),
    "dark": re.compile(r"^\[data-theme=\"dark\"\]\s*\{(.*?)^\}", re.S | re.M),
}
_DECL_RE = re.compile(r"^\s*(--[a-z0-9-]+)\s*:\s*([^;]+?)\s*;(.*)$", re.M)
_RATIO_RE = re.compile(r"(?<![\d.])(\d{1,2}\.\d{1,2})(?![\d.])")


def _blocks() -> dict:
    src = TOKENS.read_text(encoding="utf-8")
    # 구조 검사 — 정규식만 믿으면 깨진 CSS도 통과한다.
    assert src.count("{") == src.count("}"), "tokens.css 중괄호가 안 맞는다"
    # :root{ · [data-theme="dark"]{ · @media(...){ · 그 안의 :root:not([data-theme]){ = 4
    # (PA-RC-0010 — 서버 렌더 페이지용 OS-선호 매체 질의 블록 추가로 2에서 늘었다).
    assert src.count("{") == 4, f"tokens.css 블록 수가 예상과 다르다(4여야 한다): {src.count('{')}"
    out = {}
    for theme, rx in _BLOCK_RE.items():
        m = rx.search(src)
        assert m, f"{theme} 블록을 못 찾았다 — tokens.css 구조가 바뀌었다"
        out[theme] = m.group(1)
    return out


def _decls(block: str) -> dict:
    """토큰 -> (값, 그 줄의 나머지=주석)"""
    return {m.group(1): (m.group(2), m.group(3)) for m in _DECL_RE.finditer(block)}


def _resolve(token: str, decls: dict, light: dict, seen=()) -> str:
    """var() 사슬을 hex까지 따라간다. 다크에 없으면 라이트로 떨어진다(CSS 상속과 같다)."""
    assert token not in seen, f"var() 순환: {token}"
    raw = decls.get(token, light.get(token, (None, None)))[0]
    assert raw, f"{token}을 tokens.css에서 못 찾았다"
    m = re.fullmatch(r"var\((--[a-z0-9-]+)\)", raw.strip())
    if m:
        return _resolve(m.group(1), decls, light, seen + (token,))
    return raw.strip()


def _surface(value: str, base: tuple | None, decls: dict, light: dict) -> tuple[float, float, float]:
    """면의 실제 렌더 색. color-mix(X a%, transparent)는 base 위에 합성해야 진짜 면이 된다."""
    # color-mix 안쪽도 var()일 수 있다 — 먼저 hex로 풀어 놓는다.
    value = re.sub(r"var\((--[a-z0-9-]+)\)",
                   lambda m: _resolve(m.group(1), decls, light), value.strip())
    if value.startswith("#"):
        return _rgb(value)
    m = re.fullmatch(
        r"color-mix\(in srgb,\s*(#[0-9A-Fa-f]{6})\s+(\d+)%,\s*transparent\)", value)
    assert m, f"면 색을 해석 못 했다: {value!r}"
    assert base is not None, f"{value!r}는 투명 틴트다 — 어떤 면 위인지 알아야 한다"
    return composite(_rgb(m.group(1)), int(m.group(2)) / 100, base)


# (테마, 글자 토큰, 면 토큰, 틴트가 얹히는 바탕) — '무엇을 무엇 위에 그리는가'는 설계 의도다.
# 숫자가 아니라 이 관계를 테스트가 들고 있고, 색과 대비는 CSS에서 계산한다.
CASES = [
    ("light", "--sidebar-text", "--sidebar-bg", None),
    ("light", "--sidebar-muted", "--sidebar-bg", None),
    ("light", "--sidebar-active-fg", "--sidebar-active-bg", None),
    ("dark", "--sidebar-active-fg", "--sidebar-active-bg", "--sidebar-bg"),
    # PA-RC-0010 — 서버 렌더 페이지(forgot/reset-password)의 본문 글자/배경. 로그인 성공
    # 전에는 다른 어떤 화면도 이 조합을 그린 적이 없었다(다크가 아예 안 켜졌으므로).
    ("light", "--color-text", "--color-bg", None),
    ("dark", "--color-text", "--color-bg", None),
]


@pytest.mark.parametrize("theme,fg_tok,bg_tok,base_tok", CASES)
def test_contrast_comment_matches_the_colors(theme, fg_tok, bg_tok, base_tok):
    blocks = _blocks()
    light = _decls(blocks["light"])
    decls = light if theme == "light" else _decls(blocks[theme])

    fg = _rgb(_resolve(fg_tok, decls, light))
    base = _rgb(_resolve(base_tok, decls, light)) if base_tok else None
    bg = _surface(_resolve(bg_tok, decls, light), base, decls, light)
    computed = contrast(fg, bg)

    # 주석은 그 토큰이 '선언된' 블록의 줄에 있다.
    comment = decls.get(fg_tok, (None, None))[1] or ""
    found = _RATIO_RE.findall(comment)
    assert len(found) == 1, (
        f"[{theme}] {fg_tok}: 주석에서 대비 숫자를 정확히 하나 찾지 못했다({found}). "
        f"실제 대비는 {computed:.2f}다. 주석에 그 값을 적어라."
    )
    claimed = float(found[0])
    assert abs(claimed - computed) <= 0.01, (
        f"[{theme}] {fg_tok} on {bg_tok}: 주석은 {claimed}라고 하는데 실제로는 {computed:.2f}다.\n"
        f"  글자 rgb{tuple(round(c) for c in fg)} / 면 rgb{tuple(round(c, 1) for c in bg)}\n"
        f"  주석의 숫자를 {computed:.2f}로 고쳐라(색을 바꾸지 말고)."
    )


def test_dark_media_query_block_matches_the_data_theme_dark_block_exactly():
    """PA-RC-0010 — 서버 렌더 페이지(OS 선호 매체 질의)와 SPA(`[data-theme="dark"]`, JS)가
    같은 다크 값을 써야 한다. CSS 커스텀 프로퍼티는 선택자 간 참조가 안 돼(전처리기 없이) 두
    블록이 값을 나란히 손으로 들고 있다 — 하나만 고치면 여기서 잡힌다."""
    src = TOKENS.read_text(encoding="utf-8")
    attr_decls = {k: v[0] for k, v in _decls(_blocks()["dark"]).items()}

    media = _media_block(src, "@media (prefers-color-scheme: dark)")
    m = re.search(r":root:not\(\[data-theme\]\)\s*\{(.*)\}\s*$", media, re.S)
    assert m, "다크 media 블록 안에서 :root:not([data-theme])를 못 찾았다"
    media_decls = {k: v[0] for k, v in _decls(m.group(1)).items()}

    assert media_decls == attr_decls, (
        "@media (prefers-color-scheme: dark)와 [data-theme=\"dark\"]가 어긋났다 — 한쪽만 "
        "고쳤다.\n"
        f"  media에만 있음: {sorted(set(media_decls) - set(attr_decls))}\n"
        f"  속성 선택자에만 있음: {sorted(set(attr_decls) - set(media_decls))}\n"
        f"  값이 다른 키: {sorted(k for k in media_decls.keys() & attr_decls.keys() if media_decls[k] != attr_decls[k])}"
    )


def _media_block(src: str, query: str) -> str:
    """@media 블록을 중괄호를 세어 잘라낸다.

    정규식으로 `[^}]*`를 쓰면 첫 중첩 규칙에서 끊긴다. 실제로 그 실수 때문에 이 테스트가
    데스크톱 `.sidebar { z-index: 1 }`(그림자용 쌓임 맥락)을 드로어 층으로 잘못 읽었다.
    드로어의 40은 모바일 분기 안에만 있다.
    """
    start = src.find(query)
    assert start != -1, f"{query} 블록을 못 찾았다"
    i = src.index("{", start)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i + 1:j]
    raise AssertionError(f"{query} 블록의 중괄호가 안 닫혔다")


def test_base_css_has_no_rules_nothing_renders():
    """죽은 규칙은 다음 사람에게 '이 화면이 있다'고 거짓말한다.

    `.password-row`는 어떤 템플릿도 JS도 만들지 않는다. 비밀번호 화면은 `.field`를 쓴다.
    """
    base = (CSS_DIR / "base.css").read_text(encoding="utf-8")
    selectors = set(re.findall(r"^\.([a-z0-9-]+)", base, re.M))
    assert selectors, "base.css에서 클래스 선택자를 하나도 못 찾았다 — 파서가 깨졌다"

    haystack = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in [*(ROOT / "app" / "templates_html").rglob("*.html"),
                  *(ROOT / "app" / "static" / "js").rglob("*.js")]
    )
    assert "auth-card" in haystack, "템플릿을 못 읽었다 — 이 테스트는 무엇도 검사하지 못한다"

    dead = sorted(s for s in selectors if s not in haystack)
    assert not dead, f"base.css에 렌더되지 않는 죽은 규칙이 있다: {dead}"
