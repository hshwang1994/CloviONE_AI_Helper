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

## connect-src 만 다시 조였다 (2026-08-05)

완화의 목적은 **CDN·웹폰트·외부 라이브러리를 쓰는 것**이었다. 그건 script-src/style-src/
font-src/img-src/frame-src 로 달성된다. `connect-src` 는 거기에 아무 기여도 하지 않는다 —
저장소 전체에 외부 `fetch`/`XMLHttpRequest`/`WebSocket` 호출이 **한 줄도 없다**(확인함).

반면 열어 두면 XSS 가 났을 때 `/api/me`·`/api/admin/users`·감사 CSV 를 임의 호스트로 실어
보낼 수 있다. 얻는 것 없이 유출 경로만 여는 교환이라 되돌렸다. 폰트도 자체 호스팅으로
바꿨으므로(app/static/fonts/pretendard) 밖으로 나갈 일 자체가 없다.

**사용자 지시를 좁힌 것이 아니다** — 외부 리소스는 그대로 허용돼 있고, 아래 첫 테스트가
그것을 계속 지킨다. 다만 목적과 무관하게 함께 열렸던 한 지시자를 제자리로 돌렸다.
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

    `connect-src` 는 이 목록에 없다 — 위 모듈 주석 참조. 외부 리소스를 *가져오는* 것과
    데이터를 밖으로 *보내는* 것은 다른 일이고, 지시는 앞의 것이었다.
    """
    d = _csp_of(client)
    for directive in ("script-src", "style-src", "font-src", "img-src", "frame-src"):
        assert "https:" in d.get(directive, []), (
            f"{directive} 에서 https: 가 빠졌다 — 외부 리소스 허용은 2026-08-04 사용자 지시다"
        )


def test_connect_src_does_not_allow_exfiltration(client):
    """XSS 가 나도 데이터를 밖으로 실어 보낼 수 없다 (SEC1).

    앱이 외부로 XHR 을 쏘지 않으므로 'self' 로 잃는 기능이 없다. 누군가 다시 열려고 하면
    먼저 "정말 외부 API 를 호출하는 코드가 생겼는가"를 확인하게 만드는 자리다.
    """
    d = _csp_of(client)
    assert d.get("connect-src") == ["'self'"], (
        "connect-src 가 다시 열렸다 — XSS 시 /api/admin/users·감사 CSV 가 임의 호스트로 나간다"
    )


def test_fonts_are_self_hosted(client):
    """폰트 CSS 가 CDN 이 아니라 우리 static 에서 온다.

    예전 주소는 `pretendard@v1.3.9` — **불변 해시가 아니라 git 태그**였고 SRI 도 없었다.
    태그는 옮길 수 있으므로 업스트림이 한 번 손상되면 우리가 매기는 CSS 가 조용히 바뀐다.
    """
    html = client.get("/login").text
    assert "cdn.jsdelivr.net" not in html, "로그인 화면이 아직 CDN 폰트를 부른다"
    assert "/static/fonts/pretendard/" in html, "자체 호스팅 폰트를 부르지 않는다"


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
