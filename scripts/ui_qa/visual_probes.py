"""시각 규율 프로브 (F7 · D-553) — 카드 규율 · 보라 면적 · 첫 화면 데이터를 실브라우저에서 잰다.

`kit_measure.py` 는 부품 치수를, `composition_checks.py` 는 부품 조합을 잰다. 둘이 모두 초록이어도 화면은 카드가 겹겹이 쌓이고,
보라 면이 넓게 깔리고, 데이터가 첫 화면 아래로 밀릴 수 있다. 이 모듈은 그 셋을 실패로 잡고(아래 `VISUAL_CHECKS`), 사람이 눈으로
판정할 때 곁에 둘 수를 함께 낸다(`VISUAL_REPORTS` — 실패가 아니라 대조표에 적는 값).

    nested_card         카드 안 카드. `Surface` 가 다는 `data-surface="plate"` 안의 `plate`(판 안의 판은 저절로 `plate>none` 으로
                        눕으므로, 걸리는 것은 그 규칙을 비껴간 진짜 겹판이다)와, 판 안에서 카드 모양(네 테두리 · 둥글기 8 이상 ·
                        160×56 이상)을 손으로 그린 상자
    brand_area          보라 계열 바탕 면적. 선택 상태 · 단추 · 탐색 셸 · 그림(svg) 밖의 면만 센다. 뷰포트의 3% 를 넘거나 한
                        요소가 1.5% 를 넘으면 실패(보라는 선택 상태와 주 동작에만 쓴다 — F7 색 쓰임표)
    first_data_visible  첫 데이터 요소(표 머리 · 폼 칸 · 트리 행 · 체크리스트 행)의 윗변이 1920×1080 에서 440 · 1366×768 에서 420
                        이하인가(루트 글자 18 · 20px 구간은 그 비율을 곱한다). 데이터 요소가 없는 화면은 표본 0 이다

    surface_count       (보고) 첫 화면에 걸친 테두리 판 수
    status_color_count  (보고) 첫 화면에 보이는 상태색 갈래 수(성공 · 주의 · 오류 · 안내)
    empty_plate         (보고) 판 높이의 절반 넘게 비어 있는 판

## 판정 규율

- 표본 수(`checked`)를 같이 적는다. 표본 0 은 통과가 아니라 미실행이다.
- 맞는 견본(`fixtures/visual/good.html`)은 하나도 걸리면 안 되고 틀린 견본(`bad.html`)은 `SELFTEST_EXPECT_BAD` 만큼 걸려야
  한다(`tests/unit/test_ui_visual_probes.py` 가 헤드리스 브라우저로 잰다). 첫 「위반」은 위양성부터 의심한다.
"""

from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "visual"

VISUAL_CHECKS = ("nested_card", "brand_area", "first_data_visible")
VISUAL_REPORTS = ("surface_count", "status_color_count", "empty_plate")

# 시각 규율의 값. 여기 숫자를 바꾸는 것은 규율을 바꾸는 일이다(`docs/DECISIONS.md` D-553).
VISUAL_CONTRACT = {
    "brandTotalPct": 3.0,
    "brandOnePct": 1.5,
    "firstDataTop": {"tall": 440, "short": 420},
    "tallViewport": 1000,
    "nestedRadius": 8,
    "nestedMinW": 160,
    "nestedMinH": 56,
    "emptyPlateRatio": 0.5,
    "emptyPlateMinH": 200,
}

VISUAL_JS = r"""
(C) => {
  const scope = C.scope ? document.querySelector(C.scope) : null;
  if (C.scope && !scope) return { error: 'scope not found: ' + C.scope };
  const root = scope || document.querySelector('#main-content') || document.body;
  const out = {};
  const check = (n) => (out[n] = out[n] || { checked: 0, failed: 0, bad: [] });
  const fail = (n, sample) => { const c = check(n); c.failed++; if (c.bad.length < 12) c.bad.push(sample); };
  const shown = (el) => {
    if (!el || !el.getBoundingClientRect) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    const st = getComputedStyle(el);
    return st.visibility !== 'hidden' && st.display !== 'none' && st.opacity !== '0';
  };
  const inOverlay = (el) => !!el.closest('.MuiDialog-root, .MuiDrawer-root, .MuiPopover-root, .MuiMenu-root, [role=tooltip]');
  const inShell = (el) => !!el.closest('.MuiAppBar-root, #app-sidebar, [data-app-shell], nav');
  const rect = (el) => el.getBoundingClientRect();
  const text = (el) => ((el.innerText || el.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim()).slice(0, 40);
  const where = (el) => { const r = rect(el); return { text: text(el), x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) }; };
  const vw = innerWidth, vh = innerHeight, view = vw * vh;
  const rootPx = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
  const R = rootPx / 16;
  const visibleArea = (r) => Math.max(0, Math.min(r.right, vw) - Math.max(r.left, 0)) * Math.max(0, Math.min(r.bottom, vh) - Math.max(r.top, 0));

  const rgb = (c) => {
    const s = String(c || '').trim();
    let m = s.match(/^#([0-9a-f]{6})$/i);
    if (m) return { r: parseInt(m[1].slice(0, 2), 16), g: parseInt(m[1].slice(2, 4), 16), b: parseInt(m[1].slice(4, 6), 16), a: 1 };
    m = s.match(/rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+%?))?/);
    if (!m) return null;
    let a = m[4] == null ? 1 : parseFloat(m[4]);
    if (m[4] && m[4].endsWith('%')) a = a / 100;
    return { r: +m[1], g: +m[2], b: +m[3], a };
  };
  const hsl = ({ r, g, b }) => {
    const R1 = r / 255, G1 = g / 255, B1 = b / 255;
    const max = Math.max(R1, G1, B1), min = Math.min(R1, G1, B1);
    const l = (max + min) / 2;
    if (max === min) return { h: 0, s: 0, l };
    const d = max - min;
    const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    let h;
    if (max === R1) h = ((G1 - B1) / d + (G1 < B1 ? 6 : 0));
    else if (max === G1) h = (B1 - R1) / d + 2;
    else h = (R1 - G1) / d + 4;
    return { h: h * 60, s, l };
  };
  const cssVar = (name) => String(getComputedStyle(document.documentElement).getPropertyValue(name) || '').trim();
  const sameColor = (a, b) => a && b && Math.abs(a.r - b.r) <= 3 && Math.abs(a.g - b.g) <= 3 && Math.abs(a.b - b.b) <= 3;

  // ── 카드 안 카드 ────────────────────────────────────────────────────────
  const plates = [...root.querySelectorAll('[data-surface="plate"]')].filter((el) => shown(el) && !inOverlay(el) && !inShell(el));
  const NOT_CARD = 'input, textarea, select, button, fieldset, table, img, svg, pre, code, [role=button], [role=dialog], '
    + '.MuiInputBase-root, .MuiOutlinedInput-root, .MuiChip-root, .MuiAvatar-root, .k-callout, [data-table-placement], '
    + '[data-list-surface], [data-editor-box], [data-allow-nested], [data-surface]';
  for (const p of plates) {
    /* 부품 갤러리처럼 견본 틀 안에 판을 세우는 카탈로그는 `data-allow-nested` 를 단다 — 그 안의 판은 세지 않는다. */
    if (p.closest('[data-allow-nested]')) continue;
    check('nested_card').checked++;
    const outer = p.parentElement ? p.parentElement.closest('[data-surface="plate"]') : null;
    if (outer && !inOverlay(outer)) { fail('nested_card', { ...where(p), problem: '판 안의 판(표지)' }); continue; }
    for (const el of p.querySelectorAll('div, section, article, aside, li')) {
      if (el.matches(NOT_CARD) || el.closest('.k-callout, [data-editor-box], [data-allow-nested], [data-table-placement], [data-list-surface]')) continue;
      const st = getComputedStyle(el);
      const sides = ['Top', 'Right', 'Bottom', 'Left'];
      if (sides.some((k) => (parseFloat(st['border' + k + 'Width']) || 0) < 1 || st['border' + k + 'Style'] === 'none')) continue;
      if ((parseFloat(st.borderTopLeftRadius) || 0) < C.nestedRadius * R - 0.5) continue;
      if (!shown(el)) continue;
      const r = rect(el);
      if (r.width < C.nestedMinW || r.height < C.nestedMinH) continue;
      fail('nested_card', { ...where(el), problem: '판 안에 카드 모양 상자' });
    }
  }

  // ── 보라 면적 ───────────────────────────────────────────────────────────
  const prim = rgb(cssVar('--color-primary') || C.primary || '#5a4fcf');
  const primHue = prim ? hsl(prim).h : 245;
  const isBrand = (c) => {
    const v = rgb(c);
    if (!v || v.a < 0.5) return false;
    const h = hsl(v);
    const dh = Math.min(Math.abs(h.h - primHue), 360 - Math.abs(h.h - primHue));
    return h.s >= 0.45 && h.l <= 0.985 && dh <= 25;
  };
  const NOT_SURFACE = 'button, a, input, label, svg, [role=button], [role=tab], [role=switch], [role=option], [role=menuitem], '
    + '[role=radio], [role=checkbox], [aria-selected="true"], [aria-current], [aria-pressed="true"], [aria-checked="true"], '
    + '.Mui-selected, .Mui-checked, .MuiSwitch-root, .MuiChip-root, .MuiLinearProgress-root, .MuiCircularProgress-root, '
    + '.MuiAvatar-root, [data-allow-brand]';
  check('brand_area').checked++;
  let brandTotal = 0;
  const brandBig = [];
  const counted = new Set();
  for (const el of root.querySelectorAll('*')) {
    if (inShell(el) || inOverlay(el)) continue;
    if (el.closest(NOT_SURFACE)) continue;
    const st = getComputedStyle(el);
    if (!isBrand(st.backgroundColor)) continue;
    if (!shown(el)) continue;
    let up = el.parentElement, nested = false;
    while (up && up !== root) { if (counted.has(up)) { nested = true; break; } up = up.parentElement; }
    if (nested) continue;
    counted.add(el);
    const a = visibleArea(rect(el));
    if (!a) continue;
    brandTotal += a;
    const pct = (a / view) * 100;
    if (pct > C.brandOnePct) brandBig.push({ ...where(el), pct: Math.round(pct * 10) / 10 });
  }
  const brandPct = Math.round((brandTotal / view) * 1000) / 10;
  if (brandPct > C.brandTotalPct) fail('brand_area', { problem: '보라 바탕 합 ' + brandPct + '%', pct: brandPct });
  for (const b of brandBig) fail('brand_area', { ...b, problem: '보라 바탕 한 면 ' + b.pct + '%' });
  out.brand_pct = brandPct;

  // ── 첫 화면 데이터 ──────────────────────────────────────────────────────
  const DATA = 'thead, [role=columnheader], [data-form-field], [role=treeitem], [data-checklist-row]';
  const firsts = [...root.querySelectorAll(DATA)].filter((el) => shown(el) && !inOverlay(el) && !inShell(el));
  if (firsts.length) {
    check('first_data_visible').checked++;
    const top = Math.min(...firsts.map((el) => rect(el).top + scrollY));
    const limit = (vh >= C.tallViewport ? C.firstDataTop.tall : C.firstDataTop.short) * R;
    if (top > limit) fail('first_data_visible', { problem: '첫 데이터 윗변 ' + Math.round(top) + ' > ' + Math.round(limit), top: Math.round(top), limit: Math.round(limit) });
    out.first_data_top = Math.round(top);
  }

  // ── 사람 판정용 보고 ────────────────────────────────────────────────────
  const firstScreen = (el) => { const r = rect(el); return r.top < vh && r.bottom > 0; };
  const surfaces = [...root.querySelectorAll('[data-surface="plate"], [data-list-surface]')]
    .filter((el) => shown(el) && !inOverlay(el) && !inShell(el) && firstScreen(el));
  const statusVars = ['success', 'warning', 'error', 'info'].map((k) => [k, rgb(cssVar('--color-' + k))]).filter(([, v]) => v);
  const tones = new Set();
  for (const el of root.querySelectorAll('svg, [data-status-dot], [data-tone], .k-badge, .MuiChip-root')) {
    if (!shown(el) || inShell(el) || inOverlay(el) || !firstScreen(el)) continue;
    const tone = el.getAttribute('data-tone');
    if (tone && tone !== 'neutral' && tone !== 'muted') { tones.add(tone === 'danger' ? 'error' : tone === 'warn' ? 'warning' : tone); continue; }
    const st = getComputedStyle(el);
    for (const c of [st.color, st.backgroundColor, st.fill]) {
      const v = rgb(c);
      const hit = statusVars.find(([, s]) => sameColor(v, s));
      if (hit) tones.add(hit[0]);
    }
  }
  const empties = [];
  for (const p of surfaces) {
    const r = rect(p);
    if (r.height < C.emptyPlateMinH) continue;
    let bottom = r.top;
    const walker = document.createTreeWalker(p, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      if (n.nodeType === 3) {
        if (!n.textContent.trim()) continue;
        const rg = document.createRange();
        rg.selectNodeContents(n);
        for (const rr of rg.getClientRects()) if (rr.height >= 1) bottom = Math.max(bottom, rr.bottom);
      } else if (n.matches('input, textarea, button, img, svg, table, canvas, [role=img]') && shown(n)) {
        bottom = Math.max(bottom, rect(n).bottom);
      }
    }
    const used = (bottom - r.top) / r.height;
    if (used < C.emptyPlateRatio) empties.push({ ...where(p), used: Math.round(used * 100) });
  }
  out.visual_report = {
    surface_count: surfaces.length,
    status_color_count: tones.size,
    status_colors: [...tones].sort(),
    empty_plate: empties.length,
    empty_plates: empties.slice(0, 6),
    brand_pct: brandPct,
  };
  return out;
}
"""

# 틀린 견본이 반드시 걸려야 하는 검사와 최소 실패 수 — 표지 겹판 하나 · 손으로 그린 카드 모양 하나, 보라 합 · 한 면, 첫 데이터.
SELFTEST_EXPECT_BAD = {"nested_card": 2, "brand_area": 2, "first_data_visible": 1}
SELFTEST_EXPECT_REASONS = {
    "nested_card": ["판 안의 판(표지)", "판 안에 카드 모양 상자"],
    "brand_area": ["보라 바탕 합", "보라 바탕 한 면"],
    "first_data_visible": ["첫 데이터 윗변"],
}


def fixture_html(kind: str) -> str:
    """`good` · `bad` 견본 문서(고정 1366×768 화면 기준)."""
    return (FIXTURES / f"{kind}.html").read_text(encoding="utf-8")


def selftest_verdict(good: dict, bad: dict) -> list[str]:
    """맞는 견본 · 틀린 견본 실측을 받아 문제 목록을 돌려준다(빈 목록이면 통과)."""
    import json

    problems: list[str] = []
    for name, want in SELFTEST_EXPECT_BAD.items():
        got = (bad.get(name) or {}).get("failed", 0)
        if got < want:
            problems.append(f"틀린 견본을 못 잡음: {name} (실패 {got} < {want})")
    for name, words in SELFTEST_EXPECT_REASONS.items():
        blob = json.dumps((bad.get(name) or {}).get("bad", []), ensure_ascii=False)
        for w in words:
            if w not in blob:
                problems.append(f"틀린 견본의 사유가 빠짐: {name} «{w}»")
    for name in VISUAL_CHECKS:
        got = good.get(name) or {}
        if got.get("failed"):
            problems.append(f"맞는 견본을 잘못 잡음: {name} → {got.get('bad', [])[:2]}")
        if not got.get("checked"):
            problems.append(f"맞는 견본 표본 0: {name}")
    report = good.get("visual_report") or {}
    if report.get("surface_count", 0) < 1:
        problems.append("맞는 견본의 판 수 보고가 0 이다")
    bad_report = bad.get("visual_report") or {}
    if bad_report.get("empty_plate", 0) < 1:
        problems.append("틀린 견본의 빈 판을 보고하지 못함")
    if bad_report.get("status_color_count", 0) < 3:
        problems.append(f"틀린 견본의 상태색 갈래를 덜 셈({bad_report.get('status_color_count')})")
    return problems
