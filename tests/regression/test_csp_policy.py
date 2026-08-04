"""CSP 계약 — 2026-08-04 에 **의도적으로** 외부 리소스를 열었다.

## 무엇이 바뀌었나

예전 이 파일은 정확히 반대를 지켰다: `script-src 'self'` 가 열리면 실패하고, 어떤 지시자든
`https:` 출처가 들어가면 실패했다. 사내 LAN 전용이라는 전제였다.

사용자가 그 전제를 명시적으로 걷어냈다(2026-08-04):
  "CDN과 외부 라이브러리 사용을 금지하지 않는다 … 기존 CSP나 보안 설정을 유지하기 위해
   구현 수준을 낮추거나 기능을 포기하지 마라. 사내망 차단 여부도 현재 작업의 제약 조건으로
   판단하지 말고, 우선 가장 완성도 높은 형태로 구현하라."

그래서 옛 단언을 **지우지 않고 뒤집었다**. 지우면 "CSP 계약이 있었다"는 사실 자체가 사라져,
다음 사람이 이 완화를 사고로 오해하고 되돌린다(그러면 CDN 자산이 조용히 안 뜬다).
여기 남겨 두면 왜 열렸는지가 코드에 남는다.

## 지금 이 파일이 지키는 것

완화되지 **않아야** 하는 것들이다. 외부 리소스 로딩과 아무 관계가 없어서, 함께 풀 이유가
없었던 방어들이다:
  - object-src 'none'      — 플러그인 실행
  - base-uri 'self'        — <base> 주입으로 상대경로를 통째로 납치하는 공격
  - frame-ancestors 'none' — 클릭재킹
  - form-action 'self'     — 폼 전송지 탈취(비밀번호가 남의 서버로 간다)
그리고 CSP 헤더가 아예 사라지지 않았는지.
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


def test_external_resources_are_allowed_on_purpose(client):
    """CDN 스크립트·스타일·폰트·이미지가 실제로 허용돼 있는지.

    이게 실패하면 누군가 완화를 되돌린 것이다 — 그 순간 CDN 자산이 조용히 안 뜬다
    (화면은 뜨는데 아이콘과 차트만 사라지는, 원인을 찾기 어려운 형태로).
    """
    d = _csp_of(client)
    for directive in ("script-src", "style-src", "font-src", "img-src", "connect-src"):
        assert "https:" in d.get(directive, []), (
            f"{directive} 에서 https: 가 빠졌다 — 외부 리소스 허용은 2026-08-04 사용자 지시다"
        )


def test_inline_and_eval_are_allowed_for_third_party_libraries(client):
    """차트·애니메이션 라이브러리 일부가 인라인 스타일과 런타임 컴파일을 쓴다."""
    d = _csp_of(client)
    assert "'unsafe-inline'" in d.get("script-src", [])
    assert "'unsafe-eval'" in d.get("script-src", [])
    # MUI/Emotion 이 런타임에 <style> 을 주입하고 style="" 속성을 직접 쓴다.
    assert "'unsafe-inline'" in d.get("style-src", [])


def test_core_protections_survive(client):
    """외부 리소스와 무관한 방어는 함께 풀리지 않았다."""
    d = _csp_of(client)
    assert d.get("object-src") == ["'none'"], "플러그인 실행 차단이 풀렸다"
    assert d.get("frame-ancestors") == ["'none'"], "클릭재킹 방어가 풀렸다"
    assert d.get("base-uri") == ["'self'"], "<base> 주입 방어가 풀렸다"
    assert d.get("form-action") == ["'self'"], (
        "폼 전송지 제한이 풀렸다 — 로그인 폼이 남의 서버로 비밀번호를 보낼 수 있게 된다"
    )
