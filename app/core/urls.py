"""Shared same-origin-path validation for post-login/post-action redirects.

Extracted from app/auth/router.py's ``_safe_next_path`` (round28 audit E) so
app/core/errors.py's no-JS login fallback can apply the exact same
open-redirect guard instead of re-deriving (and risking drifting from) it.
"""

from __future__ import annotations


def safe_next_path(value: str) -> str | None:
    """same-origin 상대 경로만 통과시킨다(open-redirect 방지, §7 체크리스트) — 절대 URL이나
    "//evil.com" 같은 프로토콜-상대 형태, /login 자기 자신(무한 루프)은 버린다.

    "/\\evil.com"(첫 글자 뒤가 백슬래시)도 막는다 — http(s) 같은 특수 스킴에서는 브라우저가
    경로 시작 직후의 "/" 또는 "\\" 두 번째 글자를 "//"와 동일하게 authority(호스트) 시작으로
    해석한다(WHATWG URL 표준, CWE-601). "//"만 막고 "/\\"를 놓치면 우회된다."""
    v = (value or "").strip()
    if not v or not v.startswith("/") or v == "/login":
        return None
    if len(v) > 1 and v[1] in "/\\":
        return None
    return v
