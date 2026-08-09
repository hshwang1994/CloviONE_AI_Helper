"""사용자·관리자가 넣은 링크가 안전한 스킴인지 판정한다 (SEC1).

**왜 서버에 있어야 하나.** 프런트에 `safeExternal()` 이 있고 테스트도 있지만, 그건 화면 모듈
안에 숨어 있어서 세 sink 중 한 곳에만 붙어 있었다. 그리고 방어가 클라이언트에만 있으면
API 를 직접 부르는 순간 무의미하다 — **경계는 서버다.** 화면 쪽 검사는 이중 방어로 남긴다.

**무엇이 뚫려 있었나.** 공지(`announcements`)의 `link_url` 은 길이만 검사하고 그대로 저장·반환됐다.
그 배너는 `audience=all` 이면 **전 사용자에게** 뜬다. `admin`(system_admin 아님)이
`javascript:` 페이로드를 넣으면, `system_admin` 이 한 번 누르는 순간 그 세션에서 실행된다 —
"admin 이상 계정 생성은 system_admin 만" 이라는 통제를 무력화하는 권한 상승 경로다.
운영 실측(2026-08-05) 기준 사용자 15명 중 **admin 이 12명**이라 노출면이 좁지 않다.

세 겹이 전부 없었다:

  1. 서버: 길이만 검사(`max_length=500`).
  2. React: react-dom 18.3.1 의 `sanitizeURL` 은 **개발 빌드 전용 `console.error`** 다.
     운영 빌드에서는 아무 일도 하지 않는다.
  3. CSP: `script-src` 에 `'unsafe-inline'` 이 들어가면서 `javascript:` URI 가 실행 가능해졌다.

그래서 여기서 막는다.
"""

from __future__ import annotations

# http/https 만 허용한다. 상대 경로도 받지 않는다 — 이 값은 "외부 문서로 나가는 링크"이고,
# 앱 내부 이동은 라우터가 한다. 허용 목록을 좁게 두는 편이 판정이 명확하다.
ALLOWED_SCHEMES = ("http://", "https://")

_LEADING_CONTROL_CHARS = "\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\x0c\r"


def _clean(value: str) -> str:
    """공백·선행 제어문자를 지운 표준형 — 검사와 저장이 **같은 함수**로 이 형태를
    만들어야 한다(CORE-11). 예전엔 `is_safe_external_url`만 이 정리를 하고
    `normalize_external_url`은 `.strip()`만 했다 — 검증이 통과시킨 문자열과 실제로
    저장·렌더되는 문자열이 갈라져, 오늘은 무해해도(`\\x01https://…`는 브라우저가 여전히
    http(s)로 읽는다) 스킴 검사가 더 정교해질 다음번엔 두 형태가 다시 벌어질 발판이었다.
    """
    return value.strip().lstrip(_LEADING_CONTROL_CHARS)


def is_safe_external_url(value: str | None) -> bool:
    """`http(s)://` 로 시작하는가. 그 외(`javascript:`·`data:`·`vbscript:`·상대경로)는 전부 거짓."""
    if not isinstance(value, str):
        return False
    # 선행 공백·제어문자로 스킴 검사를 우회하는 고전적인 수법을 먼저 지운다
    # (`\x01javascript:` 같은 값은 브라우저가 관대하게 해석한다).
    return _clean(value).lower().startswith(ALLOWED_SCHEMES)


def normalize_external_url(value: str | None) -> str | None:
    """저장하기 좋은 모양으로. 빈 값이면 None, 안전하지 않으면 예외를 부르는 쪽에 맡긴다."""
    if value is None:
        return None
    cleaned = _clean(value)
    return cleaned or None
