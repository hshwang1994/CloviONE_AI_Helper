"""CSP는 MUI를 위해 style만 열고, script는 끝까지 잠가둔다.

UI를 MUI로 전면 재설계하면서 `style-src`에 'unsafe-inline'을 허용했다. Emotion이 런타임에
<style>을 주입하고 Popper/Transition/Modal/Drawer가 요소에 style="" 속성을 직접 쓰기 때문에,
이걸 막으면 화면이 스타일 없이 뜨고 메뉴가 (0,0)에 렌더된다.

nonce는 답이 아니다. CSP3에서 소스 목록에 nonce가 있으면 'unsafe-inline'이 무시되는데 그 규칙이
inline style '속성'에도 적용돼서, nonce를 넣으면 <style> 태그는 통과해도 style="" 속성이 전부
막힌다 — 더 크게 깨진다.

이 테스트가 지키는 것은 **완화가 style에서 멈춘다**는 것이다. script-src가 열리는 순간
XSS 방어가 사라진다. "MUI가 안 돌아서" 같은 이유로 script-src에 손대면 여기서 먼저 깨진다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.regression


def _csp_directives(header: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for chunk in header.split(";"):
        parts = chunk.split()
        if parts:
            out[parts[0]] = parts[1:]
    return out


def _csp_of(client, path: str = "/login") -> dict[str, list[str]]:
    r = client.get(path)
    header = r.headers.get("Content-Security-Policy", "")
    assert header, f"{path}: CSP 헤더가 아예 없다"
    return _csp_directives(header)


def test_script_src_is_still_locked_down(client):
    """완화는 style에서 멈춘다. 여기가 열리면 XSS 방어가 사라진다."""
    d = _csp_of(client)
    assert "script-src" in d, "script-src 지시자가 사라졌다"
    assert d["script-src"] == ["'self'"], (
        f"script-src가 'self' 단독이 아니다: {d['script-src']}. "
        "MUI 때문에 완화해야 하는 것은 style-src뿐이다."
    )


def test_no_unsafe_eval_anywhere(client):
    d = _csp_of(client)
    for name, values in d.items():
        assert "'unsafe-eval'" not in values, f"{name}에 'unsafe-eval'이 들어갔다"


def test_style_src_allows_inline_for_mui(client):
    """의도된 완화. 이게 없으면 MUI 화면이 통째로 무스타일로 뜬다."""
    d = _csp_of(client)
    assert "'unsafe-inline'" in d.get("style-src", []), (
        "style-src에서 'unsafe-inline'이 빠졌다 — MUI/Emotion이 렌더되지 않는다"
    )
    assert "'self'" in d.get("style-src", []), "style-src에서 'self'가 빠졌다"


def test_no_external_origins_are_allowed(client):
    """사내 LAN 전용이다. 폰트·아이콘·스크립트를 CDN에서 받아오면 안 된다."""
    d = _csp_of(client)
    for name, values in d.items():
        for v in values:
            assert not v.startswith(("http://", "https://", "//")), (
                f"{name}에 외부 출처 {v}가 허용됐다 — 오프라인 사내망에서 깨지고 공급망 위험도 생긴다"
            )


def test_core_protections_survive(client):
    d = _csp_of(client)
    assert d.get("object-src") == ["'none'"]
    assert d.get("frame-ancestors") == ["'none'"]
    assert d.get("base-uri") == ["'self'"]
    assert d.get("form-action") == ["'self'"]
    assert d.get("default-src") == ["'self'"]
