"""로그인 화면의 시각·동작 계약을 고정한다.

이 화면은 승인된 디자인 원본
(reference/approved-login-baseline/static-login/)을 그대로 옮긴 것이다. "가능하면 개선"의
대상이 아니라 보존 대상이다. 그런데 보존해야 할 것들이 전부 **조용히 썩는 종류**다:

  · <form>의 action/method — 지우면 화면은 멀쩡해 보이는데, JS가 죽은 브라우저에서
    네이티브 제출이 GET이 되어 비밀번호가 URL과 nginx 접근 로그에 남는다. 원본 정적본에는
    데모라 action이 아예 없었으므로, 다음에 원본을 다시 대조하는 사람이 "원본엔 없는데"
    하며 지울 가능성이 실재한다.
  · 마스코트 8상태와 고정 시선 좌표 — 특히 privacy의 [-3.6, 0]은 "비밀번호를 치는 동안
    일부러 딴 데를 본다"는 의도된 표현이다. 숫자 하나만 바뀌어도 그 의미가 사라지는데
    화면은 여전히 '동작'한다. 테스트가 없으면 아무도 모른다.
  · 4K 블록과 clamp() — 이 제품에서 유일하게 4K를 실제로 겨냥해 만든 부분이고 나머지
    화면의 기준이다. 리팩터링 중에 통째로 사라져도 1080p 모니터에서는 아무 증상이 없다.

브라우저 렌더 검증(8상태 실제 전이, 뷰포트별 스크린샷, 콘솔 오류 0)은 dist/login-qa/의
Playwright 스크립트가 따로 한다. 여기서는 서버 렌더 HTML과 소스에서 확인할 수 있는 것만
본다 — CI에서 브라우저 없이 매번 도는 것이 이 파일의 목적이다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.regression

ROOT = Path(__file__).resolve().parents[2]
CSS_DIR = ROOT / "app" / "static" / "css"
JS_DIR = ROOT / "app" / "static" / "js"
LOGIN_CSS = CSS_DIR / "login.css"
CLOVI_JS = JS_DIR / "clovi-login.js"

# 원본 script.js의 stateMessages 키와 동수·동명이어야 한다.
STATES = ("welcome", "idle", "greeting", "email", "privacy", "loading", "success", "error")


def _login_css() -> str:
    """주석을 걷어낸 login.css.

    파일 머리말이 이 테스트가 세는 것들을 그대로 인용한다("clamp() 23개",
    "@media (min-width: 2200px)..."). 주석을 그대로 세면 설명 한 줄이 규칙 하나로 잡힌다 —
    실제로 이 테스트가 처음에 그렇게 틀렸다. 세는 것은 실행되는 CSS뿐이다.
    """
    return re.sub(r"/\*.*?\*/", "", LOGIN_CSS.read_text(encoding="utf-8"), flags=re.S)


def _login_html(client) -> str:
    r = client.get("/login")
    assert r.status_code == 200, f"/login → {r.status_code}"
    return r.text


def _form_tag(html: str) -> str:
    m = re.search(r"<form[^>]*id=\"login-form\"[^>]*>", html)
    assert m, "로그인 폼(<form id=\"login-form\">)을 못 찾았다"
    return m.group(0)


# ────────────────────────────────────────────────────────────────────────────
# 1. no-JS 폴백 계약 — 비밀번호가 URL로 새지 않는다
# ────────────────────────────────────────────────────────────────────────────

def test_form_posts_natively_without_javascript(client):
    """action과 method가 둘 다 있어야 네이티브 제출이 POST가 된다.

    method를 빼면 HTML 기본값이 GET이다. 그러면 JS가 실행되지 않은 브라우저에서
    비밀번호가 ?password=... 로 주소창과 접근 로그에 찍힌다. action을 빼면 현재 URL로
    보내는데, /login?expired=1&next=... 같은 쿼리가 붙어 있던 경우 그 주소로 간다.
    """
    tag = _form_tag(_login_html(client))
    assert re.search(r'method="post"', tag, re.I), (
        f"폼에 method=\"post\"가 없다 — 기본값 GET이면 비밀번호가 URL에 실린다: {tag}"
    )
    assert re.search(r'action="/login"', tag), (
        f"폼에 action=\"/login\"이 없다 — JS 없이 제출하면 갈 곳이 불분명하다: {tag}"
    )
    assert not re.search(r'method="get"', tag, re.I), f"폼이 GET으로 제출된다: {tag}"


def test_password_field_is_inside_that_form(client):
    """폼 밖에 있으면 위의 method=post가 비밀번호를 지켜 주지 못한다."""
    html = _login_html(client)
    start = html.index('<form')
    end = html.index("</form>", start)
    body = html[start:end]
    assert 'id="password"' in body and 'type="password"' in body, (
        "비밀번호 칸이 <form> 안에 없다"
    )
    assert 'id="email"' in body, "이메일 칸이 <form> 안에 없다"


def test_server_side_login_error_is_rendered_for_the_no_js_path(client):
    """no-JS 폴백이 실패하면 /login?error=<code>로 돌아온다 — 그 경로엔 JS가 없다.

    서버가 #login-error를 채우지 않으면 그 사용자는 '왜 안 되는지' 를 볼 방법이 없다.
    """
    html = client.get("/login?error=invalid_credentials").text
    assert 'id="login-error"' in html
    m = re.search(r'<div[^>]*id="login-error"[^>]*>(.*?)</div>', html, re.S)
    assert m and m.group(1).strip(), "error=<code>로 왔는데 #login-error가 비어 있다"


def test_next_target_survives_the_no_js_submit(client):
    """세션 만료 리다이렉트의 목적지는 hidden input으로 폼에 실린다.

    login.js는 이 값을 JSON 본문에 넣고, JS가 없으면 폼 인코딩 본문으로 그대로 간다.
    """
    html = client.get("/login?next=/admin&expired=1").text
    assert re.search(r'<input[^>]*id="login-next"[^>]*name="next"[^>]*value="/admin"', html), (
        "next hidden input이 없다 — 로그인 후 원래 화면으로 못 돌아간다"
    )
    assert "세션이 만료" in html, "expired=1인데 세션 만료 안내가 없다"


# ────────────────────────────────────────────────────────────────────────────
# 2. 두 자바스크립트 계층의 접합부
# ────────────────────────────────────────────────────────────────────────────

def test_network_layer_loads_before_the_presentation_layer(client):
    """순서가 곧 계약이다.

    clovi-login.js의 submit 핸들러는 login.js가 이미 판정을 끝낸 DOM(버튼 disabled,
    aria-invalid)을 읽는다. 순서가 뒤집히면 표정이 검증 결과보다 먼저 정해져,
    입력이 틀렸는데 '로그인 중' 표정이 뜬다.
    """
    html = _login_html(client)
    net = html.find("/static/js/login.js")
    ui = html.find("/static/js/clovi-login.js")
    assert net != -1, "login.js가 안 걸려 있다"
    assert ui != -1, "clovi-login.js가 안 걸려 있다"
    assert net < ui, "clovi-login.js가 login.js보다 먼저 로드된다 — 접합부가 뒤집혔다"


def test_ids_the_network_layer_reaches_for_are_all_present(client):
    """login.js가 getElementById로 잡는 것들. 하나만 사라져도 폼이 조용히 죽는다.

    실제로 그런 적이 있어서 login.js 자신이 크리티컬 목록을 두고 방어한다 —
    여기서는 템플릿 쪽에서 같은 목록을 지킨다.
    """
    html = _login_html(client)
    for element_id in (
        "login-form", "email", "password", "login-error", "login-submit",
        "login-submit-label", "toggle-password", "server-status", "caps-hint", "login-hint",
    ):
        assert f'id="{element_id}"' in html, f"login.js가 찾는 #{element_id}가 템플릿에 없다"


def test_support_email_reaches_the_hint_element(client):
    """login.js의 setLoginHint가 mailto를 조립하려면 이 속성이 있어야 한다."""
    html = _login_html(client)
    assert re.search(r'id="login-hint"[^>]*data-support-email="', html), (
        "#login-hint에 data-support-email이 없다 — 계정 문의 링크가 만들어지지 않는다"
    )


def test_presentation_layer_does_not_duplicate_the_network_layer(client):
    """표현 계층이 자기 fetch를 들면 두 파일이 서로 다른 서버 계약을 말하게 된다."""
    js = CLOVI_JS.read_text(encoding="utf-8")
    code = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    code = re.sub(r"^\s*//.*$", "", code, flags=re.M)
    for banned in ("fetch(", "XMLHttpRequest", "location.href", "location.assign"):
        assert banned not in code, (
            f"clovi-login.js가 {banned}를 쓴다 — 네트워크/이동은 login.js만 한다"
        )


# ────────────────────────────────────────────────────────────────────────────
# 3. 마스코트 8상태 — 이름 · 문구 · 고정 시선 · 지속 시간
# ────────────────────────────────────────────────────────────────────────────

def test_all_eight_states_exist_with_their_own_message():
    js = CLOVI_JS.read_text(encoding="utf-8")
    block = re.search(r"const STATE_MESSAGES = \{(.*?)\n  \};", js, re.S)
    assert block, "STATE_MESSAGES를 못 찾았다 — 상태 기계가 사라졌거나 형태가 바뀌었다"
    found = dict(re.findall(r'(\w+):\s*"([^"]+)"', block.group(1)))
    assert set(found) == set(STATES), (
        f"상태 8가지가 아니다. 있는 것: {sorted(found)} / 있어야 할 것: {sorted(STATES)}"
    )
    assert len(set(found.values())) == len(STATES), (
        f"말풍선 문구가 중복된다 — 상태마다 다른 말을 해야 한다: {found}"
    )
    # 상태 기계를 밖에서 구동할 수 있어야 'greeting'처럼 UI 트리거가 없는 상태도 검증된다.
    assert "window.cloviLogin" in js, "상태 기계를 구동할 훅이 없다"


@pytest.mark.parametrize("state,x,y", [
    ("email", "3.8", "1.0"),
    ("privacy", "-3.6", "0"),
    ("loading", "0", "0"),
    ("error", "-1.8", "1.6"),
])
def test_fixed_gaze_offsets_are_exactly_the_approved_numbers(state, x, y):
    """privacy의 -3.6은 오타가 아니다 — 비밀번호를 치는 동안 일부러 딴 데를 본다.

    이 숫자들은 app/static/brand/login/mascot-lock.json의 maximumEyeOffsetCssPx
    (x 4.0 / y 2.5) 안에 있어야 한다. 벗어나면 눈 픽셀이 캐노니컬 원화를 벗어난다.
    """
    js = CLOVI_JS.read_text(encoding="utf-8")
    block = re.search(r"const FIXED_GAZE = \{(.*?)\n  \};", js, re.S)
    assert block, "FIXED_GAZE를 못 찾았다"
    m = re.search(rf"{state}:\s*\[\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\]", block.group(1))
    assert m, f"{state}의 고정 시선이 없다"
    assert (m.group(1), m.group(2)) == (x, y), (
        f"{state}의 시선이 [{m.group(1)}, {m.group(2)}]다. 승인된 값은 [{x}, {y}]다."
    )
    assert abs(float(m.group(1))) <= 4.0 and abs(float(m.group(2))) <= 2.5, (
        f"{state}의 시선이 mascot-lock.json의 허용 범위를 벗어났다"
    )


def test_state_durations_are_preserved():
    """전이 시간이 바뀌면 같은 화면이 다른 리듬으로 움직인다."""
    js = CLOVI_JS.read_text(encoding="utf-8")
    # welcome은 780ms 뒤 '쉬는 상태'로. 원본에선 언제나 idle이었지만 이 저장소의 login.js는
    # 넓은 화면에서 이메일 칸에 초점을 준다 — 그 초점 이벤트는 이 파일이 로드되기 전에
    # 지나갔으므로, 만료 시점에 activeElement를 보고 email/privacy/idle을 고른다.
    assert 'setCloviState("welcome", { duration: 780, after: restingState })' in js
    assert 'if (document.activeElement === email) return "email";' in js
    # 검증 실패는 650ms 뒤 문제가 있던 칸으로. 서버 실패는 850ms 뒤 idle로.
    assert 'duration: 650, after: emailInvalid ? "email" : "privacy"' in js
    assert 'duration: 850, after: "idle"' in js


def test_pointer_tracking_is_limited_to_idle():
    """다른 상태에는 고정 좌표가 있다 — 포인터가 그걸 덮으면 표현이 깨진다."""
    js = CLOVI_JS.read_text(encoding="utf-8")
    assert 'if (!latestPointer || cloviState !== "idle") return;' in js, (
        "renderPointer가 idle 밖에서도 눈을 움직인다"
    )
    # 눈이 움직일 수 있는 최대치(원본 값이자 mascot-lock의 상한).
    assert "normalizedX * 4" in js and "normalizedY * 2.5" in js


# ────────────────────────────────────────────────────────────────────────────
# 4. CSS — 눈 애니메이션, 4K 블록, clamp
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("state,rule", [
    ("welcome", "eye-welcome 720ms"),
    ("greeting", "eye-welcome 720ms"),
    ("loading", "eye-working 880ms"),
    ("success", "eye-success 760ms"),
    ("error", "eye-error 340ms"),
])
def test_state_animations_keep_their_timing(state, rule):
    css = LOGIN_CSS.read_text(encoding="utf-8")
    assert f'[data-state="{state}"]' in css, f"{state} 상태의 CSS 규칙이 사라졌다"
    assert rule in css, f"{state}의 애니메이션이 '{rule}'가 아니다"


def test_privacy_state_dims_the_eyes_instead_of_animating_them():
    """privacy는 애니메이션이 아니라 '눈을 내리깐' 정적 표현이다(opacity .7 + 채도 down)."""
    css = LOGIN_CSS.read_text(encoding="utf-8")
    assert '.clovi-stage[data-state="privacy"] .clovi-eyes-layer { opacity: .7; ' \
           'filter: saturate(.82) brightness(.88); }' in css


def test_the_4k_block_survives():
    """이 제품에서 유일하게 4K를 실제로 겨냥해 만든 블록이고 나머지 화면의 기준이다.

    1080p 모니터에서는 이게 통째로 사라져도 아무 증상이 없다 — 그래서 테스트가 지킨다.
    """
    css = _login_css()
    query = "@media (min-width: 2200px) and (min-height: 1200px)"
    assert query in css, "4K 블록이 사라졌다"
    start = css.index(query)
    depth, block = 0, ""
    for i in range(css.index("{", start), len(css)):
        block += css[i]
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                break
    assert block.count("clamp(") == 16, (
        f"4K 블록의 clamp()가 16개가 아니다: {block.count('clamp(')}"
    )
    for selector in (".login-shell", ".hero-logo", ".clovi-stage", ".form-container",
                     ".panel-logo", ".input-wrap", ".login-button"):
        assert selector in block, f"4K 블록에서 {selector} 조정이 빠졌다"


def test_clamp_rule_count_matches_the_approved_design():
    """원본 styles.css의 clamp()는 23개다. 줄어들면 반응형 타이포가 어딘가 굳었다는 뜻이다."""
    css = _login_css()
    assert css.count("clamp(") == 23, (
        f"clamp() 규칙이 {css.count('clamp(')}개다. 승인된 원본은 23개다."
    )


def test_paused_animations_when_the_tab_is_hidden():
    """보이지 않는 탭에서 눈이 계속 깜빡이면 배터리만 먹는다."""
    auth = (CSS_DIR / "auth.css").read_text(encoding="utf-8")
    assert ".is-paused *" in auth and "animation-play-state: paused" in auth
    js = CLOVI_JS.read_text(encoding="utf-8")
    assert 'classList.toggle("is-paused", document.hidden)' in js


def test_login_screen_stays_light_and_self_contained(client):
    """로그인은 인증 전이라 라이트 고정이다(히어로가 그 전제로 설계돼 있다).

    test_theme_on_all_authed_pages.py가 반대편(비밀번호 변경은 테마를 따라간다)을 본다.
    """
    html = _login_html(client)
    assert "/static/js/theme.js" not in html
    assert "/static/css/auth.css?v=" in html, "공유 표면 언어(auth.css)가 안 걸렸다"
    assert "color-scheme: light" in LOGIN_CSS.read_text(encoding="utf-8")


def test_mascot_uses_only_the_canonical_layers(client):
    """마스코트 규칙(app/static/brand/login/mascot-lock.json §rules):
    프레임/레이어를 런타임에 합성하지 않는다 — 눈 픽셀만 움직인다."""
    html = _login_html(client)
    assert "/static/brand/login/clovi-canonical-eye-base.png" in html
    assert "/static/brand/login/clovi-canonical-eyes-layer.png" in html
    assert "brand/mascot/frames" not in html and "brand/mascot/layers" not in html
