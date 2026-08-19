"""브랜드 색이 화면에 **실제로 나오는지** 실측한다 — 21개 검사에 없는 축이다.

`theme_applied` 는 다크 클래스가 붙었는지만 보고, `contrast` 는 읽히는지만 본다. 둘 다
"이 화면이 이 제품처럼 보이는가"는 한 번도 묻지 않는다. 그래서 chrome 이 전부 무채색이 되어도
전 페이지가 초록으로 나온다.

측정 대상은 7개 role 이다. 각 role 을 **어떤 선택자로 잡는지는 소스에서 정했다** —
`app/AppShell.jsx`(AppBar·사이드바·nav 활성), `ui/kit.jsx`(Button variant·`.k-readout`),
`ui/theme.js`(토큰), `screens/chat/MessageThread.jsx`(도우미 말풍선).

  header          상단바가 칠하는 면
  nav_active      현재 선택된 메뉴 항목이 칠하는 색(앞머리 2px 레일이 그 색을 나른다)
  primary_action  주요 행동 버튼의 면
  ai_surface      AI 영역의 면(도우미 말풍선 / 클로비 드로어)
  highlight       그 화면을 지배하는 판독값의 글자색
  selected_state  목록·탭·행의 선택 상태 면(내비게이션은 nav_active 몫이라 제외한다)
  focus_ring      키보드 포커스 링

판정:
  * Brand 계열 = 색상각 222~278도 그리고 채도 S>=0.25(light) / 0.18(dark)
  * 배경 role(header·ai_surface·selected_state)은 Canvas 배경과 ΔE(CIE76)>10 이어야
    "면이 존재한다"고 센다 — 캔버스와 같은 색을 칠하는 것은 칠하지 않는 것과 같다
  * 7개 중 **4개 미만이면 fail**
  * `nav_active` 나 `primary_action` 이 무채색(S<0.08, 또는 채널 폭이 0.06 미만)이면
    **무조건 fail** — 채널 폭 조건이 왜 필요한지는 `NEUTRAL_SPREAD_MIN` 주석 참고

찾지 못한 role 은 `unknown` 이고 **통과로 세지 않는다**. 그라디언트는 stop 을 파싱해 각 stop
색으로 판정하고, 파싱하지 못하면 역시 `unknown` 이다 — 모르는 것을 안다고 하지 않는다.

**이 검사는 현재 빌드에서 실패하는 것이 정상이다.** `AppShell.jsx` 가 "chrome 은 발광하지
않는다"는 주석과 함께 AppBar 를 `sidebar.bg`(캔버스 계열 무채색)로 두고 있고, `.k-readout` 의
판독값은 `text.primary` 이며, 사이드바 선택 항목의 면은 `transparent` 다. 그 결정들이 새 지시
("Global Header·Primary Action·AI 영역·Key Metric 에서 제품 정체성이 느껴져야 한다")와 정면으로
충돌한다. **통과시키려고 임계값을 만지지 마라** — 측정이 그 충돌을 가시화하는 것이 목적이다.

새 의존성 없이 sRGB→HSL, sRGB→XYZ→Lab, CIE76 을 이 모듈 안에서 직접 계산한다.
"""

from __future__ import annotations

import math
import re

# --------------------------------------------------------------------------- #
# 판정 상수 — 임의로 느슨하게 바꾸지 않는다(모듈 최상단 주석 참고)
# --------------------------------------------------------------------------- #
ROLES = (
    "header", "nav_active", "primary_action", "ai_surface",
    "highlight", "selected_state", "focus_ring",
)

# 배경 role 은 "칠했다"만으로 부족하다 — 캔버스와 구분돼야 존재한다.
BG_ROLES = frozenset({"header", "ai_surface", "selected_state"})

# 이 둘이 무채색이면 나머지가 몇 개든 실패다. 현재 선택과 주요 행동은 제품이 채도를 쓰기로
# 한 세 자리 중 둘이고, 여기가 회색이면 "브랜드가 있다"는 말 자체가 성립하지 않는다.
MUST_BE_CHROMATIC = ("nav_active", "primary_action")

BRAND_HUE_MIN, BRAND_HUE_MAX = 222.0, 278.0
# 다크에서 기준을 낮추는 이유: 어두운 면 위 강조색은 명도를 올리려고 채도를 내주고, 그 값이
# 팔레트 정본에 이미 들어 있다(theme.js accent light #5B54B8 → dark #A99CF5).
SAT_MIN = {"light": 0.25, "dark": 0.18}
ACHROMATIC_MAX_S = 0.08
BG_DELTA_E_MIN = 10.0
MIN_PRESENT_ROLES = 4

# HSL 채도는 아주 어둡거나 아주 밝은 색에서 **부풀어 오른다**. 본문 글자색 `#171A1F` 는 채널
# 폭이 8/255 밖에 안 되는 사실상 검정인데 S 는 0.148 로 나오고, 상단바 `#E7EAEE` 는 폭 7/255
# 인데 S 0.171 이다. S 만 보면 "무채색이면 무조건 실패" 규칙이 본문 글자색 하나로 무력화되고,
# 반대로 아주 옅은 라벤더 워시가 "브랜드 색"으로 통과한다. 채널 폭이 이보다 좁으면 눈에는
# 회색이다 — 두 조건을 함께 걸어야 두 방향의 오탐이 모두 막힌다.
NEUTRAL_SPREAD_MIN = 0.06

# 알파가 이보다 작으면 그 후보는 **아무 것도 칠하지 않는다**. 이 문턱이 없으면 MUI 가 요소마다
# 다는 투명 `::before` 가 뒷면 색을 그대로 합성해 돌려주고, 브랜드 면 위에 놓인 요소는 전부
# "브랜드다"로 통과한다 — 컨테이너의 색을 자기 색이라고 부르는 위양성이다.
PAINT_MIN_ALPHA = 0.03

# 어디에도 불투명한 캔버스가 없을 때 쓰는 기본 면. 브라우저가 실제로 칠하는 색이다
# (`color-scheme` 에 따라 흰색 또는 거의 검정). 이 값이 틀리면 배경 role 의 ΔE 판정이
# 통째로 어긋나므로, 가정을 썼다는 사실을 verdict note 에 반드시 남긴다.
CANVAS_FALLBACK = {"light": (255.0, 255.0, 255.0), "dark": (18.0, 18.0, 18.0)}

MAX_SAMPLES = 7          # role 이 7개다. 전부 보여야 어디가 비었는지 읽힌다.
FOCUS_MAX_TABS = 8

# --------------------------------------------------------------------------- #
# 브라우저 쪽 측정
# --------------------------------------------------------------------------- #
# 두 프로브가 같은 헬퍼를 쓴다. 문자열을 합쳐 쓰는 이유는 한쪽만 고쳐 두 프로브의 가시성·뒷면
# 판정이 어긋나는 일을 막기 위해서다.
_JS_HELPERS = r"""
  const _vis = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden') return false;
    return (parseFloat(st.opacity) || 0) > 0.05;
  };
  const _alphaOf = (css) => {
    const m = /rgba?\(([^)]+)\)/.exec(css || '');
    if (!m) return null;
    const p = m[1].split(/[,\/\s]+/).filter(Boolean).map(parseFloat);
    return p.length > 3 ? p[3] : 1;
  };
  /* 페이지의 캔버스. `body` 만 보면 안 된다 — 캔버스를 `html` 에만 칠하고 `body` 는
     투명으로 두는 배치가 흔하고, 그러면 `getComputedStyle(body).backgroundColor` 가
     `rgba(0,0,0,0)` 로 나온다. 그 값을 그대로 캔버스라고 부르면 **검정**이 되어,
     "배경 role 은 캔버스와 ΔE>10" 이라는 유일한 안전장치가 통째로 무력화된다.
     (실측 확인: 캔버스와 **똑같은 색**인 상단바가 ΔE18.2 로 '있음' 판정을 받고
     전체 판정이 fail→pass 로 뒤집혔다.) 못 찾으면 빈 문자열이고, 파이썬 쪽이
     테마에 맞는 기본값을 쓰면서 그 사실을 note 에 남긴다. */
  const _canvasBg = () => {
    for (const n of [document.body, document.documentElement]) {
      if (!n) continue;
      const c = getComputedStyle(n).backgroundColor;
      if (_alphaOf(c) >= 0.99) return { value: c, from: n === document.body ? 'body' : 'html' };
    }
    return { value: '', from: '' };
  };
  /* 합성에 쓸 뒷면 — 반투명 색을 그대로 판정하면 alpha .06 워시가 원색으로 읽힌다.
     자기 자신은 빼고 조상 중 처음 만나는 **불투명** 배경을 쓴다. */
  const _backdrop = (el) => {
    let n = el ? el.parentElement : null;
    while (n) {
      const st = getComputedStyle(n);
      if (_alphaOf(st.backgroundColor) >= 0.99) return st.backgroundColor;
      n = n.parentElement;
    }
    return _canvasBg().value;
  };
  const _desc = (el) => {
    if (!el) return '';
    const cls = (el.getAttribute('class') || '').trim().split(/\s+/).filter(Boolean).slice(0, 2);
    return el.tagName.toLowerCase() + (cls.length ? '.' + cls.join('.') : '');
  };
"""

BRAND_PROBE_JS = r"""() => {
""" + _JS_HELPERS + r"""
  /* role → 선택자. 앞쪽이 더 확실한 근거다. `data-brand-role` 은 화면이 스스로 선언하는
     길이고(추론보다 언제나 낫다), 그 뒤는 소스에서 확인한 실제 구조다. */
  const ROLE_SPEC = {
    header: {
      kind: 'bg',
      sel: ['[data-brand-role="header"]', 'header.MuiAppBar-root', '.MuiAppBar-root',
            'header[role="banner"]', 'header'],
    },
    nav_active: {
      kind: 'ink',
      sel: ['[data-brand-role="nav-active"]',
            'nav [aria-current="page"]', '[role="navigation"] [aria-current="page"]',
            'aside [aria-current="page"]', '#app-sidebar [aria-current="page"]',
            'nav .Mui-selected', 'aside .Mui-selected', '#app-sidebar .Mui-selected'],
    },
    primary_action: {
      kind: 'ink',
      sel: ['[data-brand-role="primary-action"]', '.MuiButton-containedPrimary',
            '.MuiFab-primary', 'button.MuiButton-contained', '.MuiButton-contained'],
    },
    highlight: {
      kind: 'ink',
      sel: ['[data-brand-role="highlight"]', '.k-readout', '.k-metrics', '.k-metabar'],
      /* `.k-readout` 는 칸이지 판독값이 아니다. 그 화면을 지배하는 숫자는 **칸 안에서 가장
         큰 글자**다(kit.jsx MetricStrip: 값은 readout/title, 라벨은 bodySm). */
      refine: (el) => {
        let best = el, bestSize = -1;
        for (const n of el.querySelectorAll('*')) {
          if (!_vis(n)) continue;
          const own = [...n.childNodes].some((c) => c.nodeType === 3 && c.textContent.trim());
          if (!own) continue;
          const s = parseFloat(getComputedStyle(n).fontSize) || 0;
          if (s > bestSize) { bestSize = s; best = n; }
        }
        return best;
      },
    },
    selected_state: {
      kind: 'bg',
      sel: ['[data-brand-role="selected-state"]',
            '[role="tab"][aria-selected="true"]', '[role="row"][aria-selected="true"]',
            'tr[aria-selected="true"]', '[role="option"][aria-selected="true"]',
            '[aria-selected="true"]', '[aria-pressed="true"]', '.Mui-selected'],
      /* 내비게이션의 선택은 nav_active 몫이다. 빼지 않으면 같은 요소가 두 role 로 두 번
         세어져, 사이드바 하나로 정족수 4 중 2를 채우는 위양성이 된다. */
      notInside: 'nav, aside, [role="navigation"], #app-sidebar, header, .MuiAppBar-root',
    },
  };

  const pickOne = (spec) => {
    for (const s of spec.sel) {
      let list;
      try { list = document.querySelectorAll(s); } catch (e) { continue; }
      for (const el of list) {
        if (!_vis(el)) continue;
        if (spec.notInside && el.closest(spec.notInside)) continue;
        return { el: spec.refine ? spec.refine(el) : el, sel: s };
      }
    }
    return null;
  };

  /* 이 요소가 실제로 칠하는 것들을 우선순위대로 모은다.
     ink role 에서 의사요소를 먼저 보는 이유: 이 앱의 nav 활성 표현은 요소 배경이 아니라
     `&::before` 의 2px 레일이다(AppShell.jsx). 요소 배경만 보면 `transparent` 라
     "선택 색이 없다"는 정반대 결론이 나온다. */
  const paintsOf = (el, kind) => {
    const out = [];
    const push = (what, value) => {
      if (value && value !== 'none' && value !== 'normal') out.push({ what, value });
    };
    if (kind === 'ink') {
      for (const pseudo of ['::before', '::after']) {
        const ps = getComputedStyle(el, pseudo);
        // content 가 없으면 그 의사요소는 그려지지 않는다 — 값이 있어도 화면에 없는 색이다.
        if (!ps || ps.content === 'none' || ps.content === 'normal') continue;
        push(pseudo + ' background-image', ps.backgroundImage);
        push(pseudo + ' background-color', ps.backgroundColor);
      }
    }
    const st = getComputedStyle(el);
    push('background-image', st.backgroundImage);
    push('background-color', st.backgroundColor);
    if (kind === 'ink') push('color', st.color);
    return out;
  };

  /* AI 영역은 클래스도 data 속성도 없다. 화자 구분용 스크린리더 전용 라벨이 유일하게
     안정적인 표지다(MessageThread.jsx: `<span class="sr-only">도우미: </span>` 이 말풍선
     Paper 의 첫 자식). 못 찾으면 unknown 이고 그것이 정확한 보고다 — 채팅이 없는 화면에
     AI 면이 없는 것은 결함이 아니라 사실이다. */
  const pickAiSurface = () => {
    const explicit = pickOne({
      kind: 'bg', sel: ['[data-brand-role="ai-surface"]', '[data-ai-surface]'],
    });
    if (explicit) return explicit;
    for (const sr of document.querySelectorAll('.sr-only')) {
      if (!/도우미/.test(sr.textContent || '')) continue;
      const surface = sr.parentElement;
      if (_vis(surface)) return { el: surface, sel: '.sr-only(도우미) 의 부모 말풍선' };
    }
    return null;
  };

  const roles = {};
  for (const name of Object.keys(ROLE_SPEC)) {
    const spec = ROLE_SPEC[name];
    const hit = pickOne(spec);
    if (!hit) {
      roles[name] = { found: false, note: '이 화면에서 해당 요소를 찾지 못함' };
      continue;
    }
    roles[name] = {
      found: true, kind: spec.kind, selector: hit.sel, element: _desc(hit.el),
      candidates: paintsOf(hit.el, spec.kind), backdrop: _backdrop(hit.el),
    };
  }
  const ai = pickAiSurface();
  roles.ai_surface = ai
    ? { found: true, kind: 'bg', selector: ai.sel, element: _desc(ai.el),
        candidates: paintsOf(ai.el, 'bg'), backdrop: _backdrop(ai.el) }
    : { found: false, note: 'AI 면(도우미 말풍선/클로비 드로어)이 이 화면에 없음' };

  const canvas = _canvasBg();
  return {
    theme: document.documentElement.getAttribute('data-theme') || '',
    canvas: canvas.value,
    canvasFrom: canvas.from,
    roles,
  };
}"""

# 포커스 링은 정적으로 못 읽는다 — `:focus-visible` 은 **실제 키보드 조작**에만 붙는다.
# `el.focus()` 만으로는 Chromium 이 :focus-visible 을 주지 않는 경우가 많아서, 파이썬 쪽에서
# 진짜 Tab 을 눌러 가며 이 프로브로 확인한다.
FOCUS_PROBE_JS = r"""() => {
""" + _JS_HELPERS + r"""
  const el = document.activeElement;
  if (!el || el === document.body || el === document.documentElement) {
    return { ok: false, why: '포커스가 어디에도 걸리지 않음' };
  }
  const st = getComputedStyle(el);
  const width = parseFloat(st.outlineWidth) || 0;
  let focusVisible = null;
  try { focusVisible = el.matches(':focus-visible'); } catch (e) { focusVisible = null; }
  const drawn = focusVisible === true && width > 0 && st.outlineStyle !== 'none';
  return {
    ok: drawn,
    why: drawn ? '' : (focusVisible === true ? 'outline 을 그리지 않음' : ':focus-visible 아님'),
    element: _desc(el), outlineColor: st.outlineColor, outlineWidth: width,
    outlineStyle: st.outlineStyle, backdrop: _backdrop(el),
  };
}"""

# Tab 으로 못 잡았을 때의 마지막 수단 — 스타일시트에 적힌 규칙을 읽는다. 이것은 **측정이
# 아니라 선언**이라, 읽어서 보고는 하되 `present` 로 세지 않는다(`declaration_only`).
# 세어 버리면 포커스 링이 실제로는 안 그려지는 화면에서도 테마가 어딘가 적어 둔 규칙 하나로
# 정족수 4 중 1이 채워진다 — 하지 않은 측정을 한 척하는 가장 흔한 경로다.
FOCUS_CSS_SCAN_JS = r"""() => {
  const hits = [];
  for (const sheet of document.styleSheets) {
    let rules = null;
    try { rules = sheet.cssRules; } catch (e) { continue; }   // 교차 출처 시트
    if (!rules) continue;
    for (const rule of rules) {
      const sel = rule.selectorText || '';
      if (!/focus-visible|Mui-focusVisible/i.test(sel)) continue;
      if (!rule.style) continue;
      const raw = (rule.style.getPropertyValue('outline-color')
                   || rule.style.getPropertyValue('outline') || '').trim();
      if (!raw) continue;
      hits.push({ what: 'stylesheet ' + sel.slice(0, 60), value: raw });
      if (hits.length >= 6) return hits;
    }
  }
  return hits;
}"""


def _measure_focus_ring(page, *, max_tabs: int = FOCUS_MAX_TABS) -> dict:
    """실제로 Tab 을 눌러 포커스 링 색을 잰다. 누른 상태는 되돌린다.

    스크린샷은 이 함수가 불리기 전에 이미 찍혔으므로(capture.py 의 순서) 화면 상태를 건드려도
    캡처가 오염되지 않는다. 그래도 스크롤과 포커스는 원래대로 돌려놓는다 — 이 뒤에 모달
    탐색(`interact.py`)이 돌기 때문이다.
    """
    try:
        saved = page.evaluate("() => [window.scrollX, window.scrollY]")
    except Exception:  # noqa: BLE001
        saved = [0, 0]
    found, presses = None, 0
    try:
        for i in range(max_tabs):
            page.keyboard.press("Tab")
            presses = i + 1
            probe = page.evaluate(FOCUS_PROBE_JS)
            if probe.get("ok"):
                found = probe
                break
    except Exception as exc:  # noqa: BLE001 — 포커스 측정 실패가 나머지 6개를 버리게 하면 안 된다
        return {"found": False, "note": f"Tab 측정 실패: {type(exc).__name__}: {exc}"}
    finally:
        try:
            page.evaluate(
                "([x, y]) => { const a = document.activeElement;"
                " if (a && a.blur) a.blur(); window.scrollTo(x, y); }", saved)
        except Exception:  # noqa: BLE001
            pass

    if found:
        return {
            "found": True, "kind": "ink",
            "selector": f"Tab {presses}회 후 포커스", "element": found.get("element", ""),
            "candidates": [{"what": "outline-color", "value": found.get("outlineColor")}],
            "backdrop": found.get("backdrop"),
        }

    try:
        hits = page.evaluate(FOCUS_CSS_SCAN_JS) or []
    except Exception as exc:  # noqa: BLE001
        return {"found": False,
                "note": f"Tab {presses}회로 못 잡고 스타일시트도 못 읽음: {exc}"}
    if not hits:
        return {"found": False,
                "note": f"Tab {presses}회로 포커스 링을 못 봤고 스타일시트에도 규칙이 없음"}
    return {
        "found": True, "kind": "ink", "selector": hits[0].get("what", "stylesheet"),
        "element": "", "candidates": hits, "backdrop": None,
        "declaration_only": True,
        "note": (f"Tab {presses}회로는 포커스 링을 못 봤다. 스타일시트 선언에는 "
                 + ", ".join(str(h.get("value"))[:24] for h in hits[:2])
                 + " 라고 적혀 있지만 그린 것을 본 적은 없다"),
    }


def evaluate_brand(page) -> dict:
    """이미 열려 있는 페이지에서 7개 role 의 색을 잰다(추가 네비게이션 없음)."""
    probe = page.evaluate(BRAND_PROBE_JS)
    roles = probe.setdefault("roles", {})
    roles["focus_ring"] = _measure_focus_ring(page)
    return probe


# --------------------------------------------------------------------------- #
# 색 계산 — 새 의존성 없이 직접 구현한다
# --------------------------------------------------------------------------- #
# 그라디언트 stop, `outline` 단축 속성, 평범한 색을 한 번에 훑는다. 하나의 정규식으로 합친
# 이유는 순서 때문이다 — 두 번 훑으면 stop 순서가 섞인다.
_COLOR_RE = re.compile(r"#[0-9A-Fa-f]{3,8}\b|\brgba?\([^)]*\)|\btransparent\b", re.I)
_NUM_RE = re.compile(r"[-+]?[0-9]*\.?[0-9]+%?")


def _clamp(value: float, low: float = 0.0, high: float = 255.0) -> float:
    return low if value < low else high if value > high else value


def _parse_color(text):
    """CSS 색 하나를 `(r, g, b, a)` 로. 읽지 못하면 None(= 모른다)."""
    if not text:
        return None
    token = str(text).strip()
    if token.lower() == "transparent":
        return (0.0, 0.0, 0.0, 0.0)
    if token.startswith("#"):
        digits = token[1:]
        if len(digits) in (3, 4):
            digits = "".join(c * 2 for c in digits)
        if len(digits) not in (6, 8):
            return None
        try:
            parts = [int(digits[i:i + 2], 16) for i in range(0, len(digits), 2)]
        except ValueError:
            return None
        alpha = parts[3] / 255.0 if len(parts) == 4 else 1.0
        return (float(parts[0]), float(parts[1]), float(parts[2]), alpha)
    if token.lower().startswith(("rgb(", "rgba(")):
        try:
            inner = token[token.index("(") + 1:token.rindex(")")]
        except ValueError:
            return None
        nums = _NUM_RE.findall(inner)
        if len(nums) < 3:
            return None

        def _chan(raw: str) -> float:
            return _clamp(float(raw[:-1]) * 255.0 / 100.0 if raw.endswith("%") else float(raw))

        try:
            channels = [_chan(n) for n in nums[:3]]
            alpha = 1.0
            if len(nums) > 3:
                raw = nums[3]
                alpha = float(raw[:-1]) / 100.0 if raw.endswith("%") else float(raw)
        except ValueError:
            return None
        return (channels[0], channels[1], channels[2], _clamp(alpha, 0.0, 1.0))
    return None                      # 이름 있는 색 등 — 모르는 것은 모른다고 한다


def _colors_in(css):
    """한 CSS 값 안의 모든 색을 문서 순서대로. 그라디언트는 stop 색 전부를 낸다.

    색을 하나도 못 읽으면 None 이다 — `url(...)` 배경이나 이름 있는 색이 여기 해당한다.
    빈 목록과 반드시 구분해야 한다: 빈 목록은 "칠하지 않는다", None 은 "못 읽었다"다.
    """
    if not css:
        return None
    text = str(css).strip()
    if text in ("none", "normal", "auto", ""):
        return None
    out = []
    for match in _COLOR_RE.finditer(text):
        parsed = _parse_color(match.group(0))
        if parsed is not None:
            out.append(parsed)
    return out or None


def _composite(fg, backdrop):
    """반투명 색을 뒷면 위에 얹은 실제 색. 이것을 빼면 alpha .06 워시가 원색으로 읽힌다."""
    a = fg[3]
    return tuple(fg[i] * a + backdrop[i] * (1.0 - a) for i in range(3))


def _hsl(rgb):
    r, g, b = (v / 255.0 for v in rgb)
    hi, lo = max(r, g, b), min(r, g, b)
    light = (hi + lo) / 2.0
    delta = hi - lo
    if delta <= 1e-9:
        return 0.0, 0.0, light
    sat = delta / (2.0 - hi - lo) if light > 0.5 else delta / (hi + lo)
    if hi == r:
        hue = 60.0 * (((g - b) / delta) % 6.0)
    elif hi == g:
        hue = 60.0 * (((b - r) / delta) + 2.0)
    else:
        hue = 60.0 * (((r - g) / delta) + 4.0)
    return hue % 360.0, sat, light


_D65 = (0.95047, 1.0, 1.08883)


def _lab(rgb):
    """sRGB → CIE L*a*b*. ΔE 는 지각 균등 공간에서만 뜻이 있다(sRGB 거리로는 못 잰다)."""
    def _linear(channel: float) -> float:
        c = channel / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (_linear(v) for v in rgb)
    x = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041

    def _f(t: float) -> float:
        return t ** (1.0 / 3.0) if t > 216.0 / 24389.0 else (841.0 / 108.0) * t + 4.0 / 29.0

    fx, fy, fz = _f(x / _D65[0]), _f(y / _D65[1]), _f(z / _D65[2])
    return 116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz)


def _delta_e76(a, b) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _spread(rgb) -> float:
    """채널 폭 (max-min)/255 — HSL 채도가 부풀어 오르는 구간을 걸러 내는 짝(NEUTRAL_SPREAD_MIN)."""
    return (max(rgb) - min(rgb)) / 255.0


def _is_chromatic(sat: float, spread: float) -> bool:
    return sat >= ACHROMATIC_MAX_S and spread >= NEUTRAL_SPREAD_MIN


# --------------------------------------------------------------------------- #
# 판정
# --------------------------------------------------------------------------- #
def _fmt_rgb(rgb) -> str:
    return "#%02X%02X%02X" % tuple(int(round(_clamp(v))) for v in rgb)


def _resolve_role(role: str, entry, canvas_rgb, sat_min: float) -> dict:
    """한 role 의 **실제 색 하나**를 고르고 브랜드 여부를 판정한다.

    후보가 여럿인 이유는 브랜드를 나르는 속성이 role 마다 다르기 때문이다(nav 활성은
    `::before` 배경, 주요 행동은 자기 배경, 판독값은 글자색). 고르는 규칙은 세 단계다:

      1. 브랜드 조건을 만족하는 후보가 있으면 그것 — 그라디언트 stop 중 하나만 브랜드여도
         그 면은 브랜드를 나른다.
      2. 없으면 채도가 있는 첫 후보 — "무채색인가"는 무조건 실패를 부르는 판정이라,
         가장 유리한 후보로 말해야 한다.
      3. 그것도 없으면 첫 후보.
    """
    if not entry or not entry.get("found"):
        note = (entry or {}).get("note") or "요소를 찾지 못함"
        return {"role": role, "state": "unknown", "why": note}
    if entry.get("declaration_only"):
        # 선언은 증거로 남기되 판정에는 넣지 않는다 — 그린 것을 보지 못했다.
        return {"role": role, "state": "unknown",
                "why": entry.get("note") or "스타일시트 선언만 있고 렌더는 확인 못 함"}

    is_bg = role in BG_ROLES
    # 뒷면은 **불투명할 때만** 믿는다. `transparent` 도 파싱에는 성공하므로(=(0,0,0,0))
    # 값이 있다는 이유로 쓰면 검정 위에 합성하게 된다 — 캔버스로 되돌리는 편이 정확하다.
    backdrop = _parse_color(entry.get("backdrop"))
    backdrop_rgb = (backdrop[:3] if backdrop is not None and backdrop[3] >= 0.99
                    else canvas_rgb)

    scored = []
    unreadable = []
    readable_any = False
    for cand in entry.get("candidates") or []:
        colors = _colors_in(cand.get("value"))
        if colors is None:
            unreadable.append(f"{cand.get('what')}={str(cand.get('value'))[:36]}")
            continue
        readable_any = True
        for color in colors:
            if color[3] < PAINT_MIN_ALPHA:
                continue                      # 칠하지 않는 것은 색이 아니다
            rgb = _composite(color, backdrop_rgb)
            hue, sat, _unused = _hsl(rgb)
            spread = _spread(rgb)
            delta_e = _delta_e76(_lab(rgb), _lab(canvas_rgb))
            scored.append({
                "what": cand.get("what"), "rgb": rgb, "hue": hue, "sat": sat,
                "spread": spread, "deltaE": delta_e,
                "brand": (BRAND_HUE_MIN <= hue <= BRAND_HUE_MAX and sat >= sat_min
                          and spread >= NEUTRAL_SPREAD_MIN
                          and (not is_bg or delta_e > BG_DELTA_E_MIN)),
            })

    if not scored:
        if unreadable and not readable_any:
            return {"role": role, "state": "unknown",
                    "why": "색을 읽지 못함 (" + ", ".join(unreadable[:2]) + ")"}
        if not is_bg:
            return {"role": role, "state": "unknown", "why": "칠하는 색이 없음"}
        # 배경 role 이 아무 것도 칠하지 않으면 그 면은 **뒷면 그대로**다. 이것은 모르는 것이
        # 아니라 알아낸 사실이고(선택 상태에 면이 없다), ΔE 가 그 사실을 그대로 말한다.
        hue, sat, _unused = _hsl(backdrop_rgb)
        scored = [{
            "what": "면을 칠하지 않음(뒷면 그대로)", "rgb": backdrop_rgb, "hue": hue,
            "sat": sat, "spread": _spread(backdrop_rgb),
            "deltaE": _delta_e76(_lab(backdrop_rgb), _lab(canvas_rgb)),
            "brand": False,
        }]

    chosen = next((s for s in scored if s["brand"]), None)
    if chosen is None:
        chosen = next((s for s in scored if _is_chromatic(s["sat"], s["spread"])), scored[0])
    return {
        "role": role, "state": "present" if chosen["brand"] else "absent",
        "hex": _fmt_rgb(chosen["rgb"]), "hue": round(chosen["hue"], 1),
        "sat": round(chosen["sat"], 3), "spread": round(chosen["spread"], 3),
        "deltaE": round(chosen["deltaE"], 1),
        "chromatic": _is_chromatic(chosen["sat"], chosen["spread"]),
        "what": chosen["what"], "selector": entry.get("selector", ""),
        "element": entry.get("element", ""),
    }


def _sample_line(res: dict) -> str:
    if res["state"] == "unknown":
        return f"{res['role']}: 모름 — {res['why']}"
    mark = "있음" if res["state"] == "present" else "없음"
    where = res.get("element") or res.get("selector") or ""
    return (f"{res['role']}: {mark} {res['hex']} H{res['hue']} S{res['sat']}"
            f"(폭{res['spread']}) ΔE{res['deltaE']}"
            f" ({res['what']}{' @ ' + where if where else ''})")


def brand_verdict(probe: dict, *, max_samples: int = MAX_SAMPLES) -> dict:
    """`evaluate_brand()` 의 원시 측정을 `assertions._verdict()` 와 같은 모양으로 바꾼다.

    Playwright 없이 dict 만으로 검증할 수 있게 측정과 분리했다(`contrast.py` 와 같은 구조).
    """
    theme = (probe.get("theme") or "light").lower()
    sat_min = SAT_MIN.get(theme, SAT_MIN["light"])
    canvas = _parse_color(probe.get("canvas"))
    if canvas is not None and canvas[3] >= 0.99:
        canvas_rgb, canvas_note = canvas[:3], ""
    else:
        # 어디에도 불투명한 캔버스가 없으면 브라우저가 칠하는 기본 면을 쓴다. 추정이므로
        # 반드시 밝힌다 — 이 값이 배경 role 의 ΔE 판정을 좌우한다.
        canvas_rgb = CANVAS_FALLBACK.get(theme, CANVAS_FALLBACK["light"])
        canvas_note = (f"캔버스를 못 읽어 {theme or '라이트'} 기본값"
                       f" {_fmt_rgb(canvas_rgb)} 으로 가정함(ΔE 판정 주의)")
    roles = probe.get("roles") or {}

    resolved = [_resolve_role(name, roles.get(name), canvas_rgb, sat_min) for name in ROLES]
    measured = [r for r in resolved if r["state"] != "unknown"]
    present = [r for r in resolved if r["state"] == "present"]
    unknown = [r for r in resolved if r["state"] == "unknown"]

    if not measured:
        # 하나도 못 쟀으면 그것은 **디자인 결함이 아니라 측정 실패**다. 여기서 fail 을 내면
        # 렌더가 깨진 페이지와 브랜드가 빠진 페이지를 구분할 수 없게 된다.
        return {"status": "skip", "count": 0,
                "samples": [_sample_line(r) for r in resolved][:max_samples],
                "note": "7개 role 을 하나도 찾지 못했다 — 화면이 렌더되지 않았을 수 있다"}

    achromatic = [r for r in resolved
                  if r["role"] in MUST_BE_CHROMATIC and r["state"] != "unknown"
                  and not r["chromatic"]]
    failed = len(present) < MIN_PRESENT_ROLES or bool(achromatic)

    reasons = [f"브랜드 색이 나오는 role {len(present)}/{len(ROLES)}"
               f" (기준 {MIN_PRESENT_ROLES}개 이상, 모름 {len(unknown)}개는 통과로 세지 않음)"]
    if achromatic:
        reasons.append("무채색이면 무조건 실패인 role: "
                       + ", ".join(f"{r['role']}(S{r['sat']} 폭{r['spread']})"
                                   for r in achromatic))
    reasons.append(f"기준: 색상각 {BRAND_HUE_MIN:.0f}~{BRAND_HUE_MAX:.0f}도 · "
                   f"S>={sat_min} ({theme or '테마 미상'}) · 채널폭>={NEUTRAL_SPREAD_MIN} · "
                   f"배경 role 은 ΔE>{BG_DELTA_E_MIN:.0f}"
                   f" (캔버스 {_fmt_rgb(canvas_rgb)}"
                   f"{' @ ' + probe['canvasFrom'] if probe.get('canvasFrom') else ''})")
    if canvas_note:
        reasons.append(canvas_note)

    return {
        "status": "fail" if failed else "pass",
        "count": len(ROLES) - len(present),
        "samples": [_sample_line(r) for r in resolved][:max_samples],
        "note": " / ".join(reasons),
    }
