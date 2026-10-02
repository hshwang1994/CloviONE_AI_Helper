"""공통 부품의 **치수 · 줄바꿈 · 관계**를 실브라우저에서 잰다 (핸드오프 §0-1 · §0-3 · §0-9).

`run.py` 의 검사는 「화면이 깨졌는가」를 본다(넘침 · 잘림 · 대비). 이 하네스는 그보다 좁고
딱딱한 질문을 한다 — **정본 부품이 계약값으로 서 있는가.** 버튼 높이 집합이 {34, 30} 인가,
세그먼티드가 34/3/28 인가, 필터 칸이 34 이고 라벨이 칸 안에 있는가, 같은 줄의 입력칸 윗변이
같은가, 카드 발의 면과 위 선을 그리는 요소가 하나뿐인가.

## 쓰는 법

    python -m scripts.ui_qa.local_capture --harness kit_measure \\
        --routes user_kit user_knowledge --viewports 1920x1080 1366x768 1200x900 \\
        --measure-label a-r1 --fail-on button_height segmented filter_cell

    python -m scripts.ui_qa.local_capture --harness kit_measure --selftest

`--label` · `--themes` 는 `local_capture` 가 먹는 이름이라 `--measure-label` · `--measure-themes`
를 쓴다.

`--open-modals` 를 주면 화면마다 여는 단추를 눌러 모달을 차례로 열고(`interact.open_modals` — 파괴 동작은 누르지
않는다) **열린 모달 안만** 같은 검사로 잰다. 모달 제목 · 닫기 · 모서리 · 발 · 모달 안 단추가 여기서 표본을 얻는다
(화면만 열어서는 `modal` · `floating_radius` 표본이 0 이다).

## 판정 규율 (자작 프로브는 양방향으로 틀린다)

- 검사마다 **표본 수(`checked`)** 를 같이 적는다. `--fail-on` 에 건 검사가 표본 0 이면 통과가
  아니라 미실행이다 — 종료 코드 2.
- `--selftest` 는 갤러리 위에 **일부러 틀린 견본**(40px 버튼 · 두 줄 버튼 · 점 있는 배지 ·
  600 태그 · 24px 건수 칩 · 36px 필터 칸 · 노치 라벨 · 7px 막대 스위치 · 끝을 넘은 손잡이 ·
  고르지 않은 여백 · 34 높이 누르는 자리 · 타원 트랙 · 그림만 맞고 input 이 34 인 스위치)과
  **맞는 견본**을 끼워 넣고, 틀린 것은
  전부 잡히고 맞는 것은 하나도 안 잡히는지 본다. 이것이 초록이 아니면 제품 판정에 쓰지 않는다.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OUT_BASE = REPO_ROOT / "dist" / "ui-qa"

from scripts.ui_qa.composition_checks import (  # noqa: E402
    COMPOSITION_CHECKS, COMPOSITION_CONTRACT, COMPOSITION_JS, expect_for, selftest_html, selftest_verdict,
)
from scripts.ui_qa import visual_probes  # noqa: E402
from scripts.ui_qa.visual_probes import VISUAL_CHECKS, VISUAL_CONTRACT, VISUAL_JS  # noqa: E402
MASCOT_BOUNDS = REPO_ROOT / "app" / "static" / "brand" / "mascot" / "mascot-bounds.json"


def _mascot_hfrac() -> dict[str, float]:
    try:
        data = json.loads(MASCOT_BOUNDS.read_text(encoding="utf-8"))
        return {name: float(entry.get("hfrac") or 1) for name, entry in data.get("assets", {}).items()}
    except Exception:  # noqa: BLE001
        return {}

# 핸드오프 README · DECISIONS 의 확정값. 여기 숫자를 바꾸는 것은 계약을 바꾸는 일이다.
CONTRACT = {
    "buttonHeights": [34, 30],
    "segmented": {"outer": 34, "pad": 3, "inner": 28},
    "statusChip": 30,
    "filterChip": 26,
    "calloutSingle": 50,
    # 동작이 든 한 줄 상자(D-528) — 동작 30 + 위아래 여백 + 테두리. 아이콘 · 첫 줄 · 동작이 한 가운데선(±1)에 선다.
    "calloutAction": 30,
    "calloutSingleAction": 56,
    "calloutCompactAction": 46,
    "calloutIcon": 16,
    "calloutIconTop": 3,
    "badge": {"h": 22, "px": 8, "r": 4, "w": 600},
    "tag": {"h": 22, "r": 6, "w": 400},
    "filterCell": 34,
    # 필터 면 밖의 검색 칸 폭. 면 안이면 아래 계단이 정한다 — [필터 면 내용 폭 rem 이상, 칸 폭 rem], 큰 계단부터, 어느 계단에도
    # 못 미치면 제 줄 전체(D-530, `FilterBar.jsx::SEARCH_SLOT_STEPS` · `composition_checks.py` 와 같은 수).
    "searchSlot": 320,
    "searchSlotSteps": [[64, 20], [44, 16]],
    "table": {"head": 40, "row": 48, "group": 36, "footer": 44},
    "cardPadding": 20,
    "modal": {"radius": 8, "titleSize": 17, "titleWeight": 700, "close": 30},
    "floatingRadius": 8,
    "countChip": {"default": 20, "compact": 18},
    "picker": {"h": 32, "avatar": 22},
    "mascot": {"pageMin": 112, "pageMax": 132, "region": 72},
    "chat": {"list": 296, "bubbleMax": 0.68, "composerRadius": 10, "avatar": 34, "stack": 26},
    # 스위치(D-525) — 보이는 트랙 38×22 · 손잡이 16, 누르는 자리 44 이상, 줄이 보는 높이 34, 초점 링(2 + offset 2) 자리 4.
    "switch": {"trackW": 38, "trackH": 22, "thumb": 16, "hit": 44, "layoutH": 34, "ring": 4},
    "tol": 1,
}

# 계약값은 루트 글자 16px 기준 px 다. 2560 구간은 루트가 18px 라 rem 으로 정한 치수가 1.125 배로 선다 — 같은 비율로 곱해서 잰다
# (`composition_checks.py` 가 이미 `R = rootPx / 16` 을 곱하는 것과 같다). 곱하지 않는 것: 글자 굵기 · 비율 · 허용 오차, rem 으로
# 적은 계단, 스스로 루트 비율을 곱하는 스위치(`swScale`), px 로 정하는 마스코트 박스(`Mascot.jsx::mascotBoxPx`), 채팅 틀.
# 허용 오차(`tol`)도 곱한다 — 테두리 1px 처럼 rem 이 아닌 조각이 남아 루트 18px 에서 비례값과 1px 남짓 어긋난다.
# 둥글기(`RADIUS` 토큰)는 px 라 루트 글자를 따라 자라지 않는다 — 곱하면 2560 의 모달 모서리 8px 가 9 로 걸린다.
_UNSCALED_KEYS = frozenset({"w", "titleWeight", "bubbleMax", "searchSlotSteps", "switch", "mascot", "chat",
                            "radius", "r", "floatingRadius", "composerRadius"})


def contract_for(root_px: float | None) -> dict:
    """루트 글자 크기에 맞춘 계약값 사본."""
    k = (root_px or 16) / 16
    if abs(k - 1) < 1e-6:
        return dict(CONTRACT)

    def walk(key, value):
        if key in _UNSCALED_KEYS or isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return round(value * k, 3)
        if isinstance(value, list):
            return [walk(None, v) for v in value]
        if isinstance(value, dict):
            return {kk: walk(kk, vv) for kk, vv in value.items()}
        return value

    return {key: walk(key, value) for key, value in CONTRACT.items()}


CHECKS = (
    "button_height", "button_wrap", "button_clip", "icon_button_height", "segmented",
    "status_chip", "callout", "badge", "tag", "filter_cell", "filter_notched", "search_slot",
    "filter_switch", "filter_toggle", "filter_surface", "filter_row_tops", "table_heights",
    "table_align", "card_padding", "modal", "floating_radius", "count_chip", "picker_option",
    "empty_layout", "error_icon", "mascot_size", "card_row_tops", "page_head_overlap",
    "footer_owner", "variant_height", "form_field_rows", "chat_layout", "switch_geometry",
)
# 부품 치수(위) + 조합(`composition_checks.py`) + 시각 규율(`visual_probes.py`, F7). 셋을 한 표로 보고한다 — 치수 PASS 를
# 조합 · 시각 PASS 로 읽지 않게.
ALL_CHECKS = CHECKS + COMPOSITION_CHECKS + VISUAL_CHECKS

MEASURE_JS = r"""
(C) => {
  const scope = C.scope ? document.querySelector(C.scope) : document.body;
  if (!scope) return { error: 'scope not found: ' + C.scope };
  const tol = C.tol;
  const out = {};
  const check = (name) => (out[name] = out[name] || { checked: 0, bad: [] });
  const fail = (name, sample) => { const c = check(name); if (c.bad.length < 12) c.bad.push(sample); c.failed = (c.failed || 0) + 1; };
  const shown = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    const st = getComputedStyle(el);
    return st.visibility !== 'hidden' && st.display !== 'none' && st.opacity !== '0';
  };
  const all = (sel) => [...scope.querySelectorAll(sel)].filter(shown);
  const px = (v) => parseFloat(v) || 0;
  const hOf = (el) => Math.round(el.getBoundingClientRect().height * 10) / 10;
  const near = (a, b, t) => Math.abs(a - b) <= (t == null ? tol : t);
  const text = (el) => ((el.innerText || el.getAttribute('aria-label') || el.getAttribute('title') || '')
    .replace(/\s+/g, ' ').trim()).slice(0, 40);
  const where = (el) => {
    const r = el.getBoundingClientRect();
    return { text: text(el), x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) };
  };
  const lineCount = (el) => {
    const tops = [];
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      if (!n.textContent.trim()) continue;
      const range = document.createRange();
      range.selectNodeContents(n);
      for (const r of range.getClientRects()) {
        if (r.width < 1 || r.height < 1) continue;
        const mid = r.top + r.height / 2;
        if (!tops.some((t) => Math.abs(t - mid) < 6)) tops.push(mid);
      }
    }
    return tops.length;
  };
  const transparent = (c) => !c || c === 'transparent' || /rgba\([^)]*,\s*0\)$/.test(c);
  const heightsHist = {};
  const bump = (h, k) => { h[k] = (h[k] || 0) + 1; };

  // ── 버튼 ────────────────────────────────────────────────────────────────
  const insideSegmented = (el) => !!el.closest('.k-segmented');
  // 셸(상단바 · 사이드바)은 `chrome.*` 토큰의 하우징이라 본문 부품 계약 밖이다.
  const inShell = (el) => !!el.closest('.MuiAppBar-root, #app-sidebar, .MuiDrawer-root, nav');
  const btns = all('.MuiButton-root').filter((el) => !insideSegmented(el) && !inShell(el));
  const hist = {};
  for (const b of btns) {
    const h = Math.round(hOf(b));
    bump(hist, h);
    check('button_height').checked++;
    if (!C.buttonHeights.some((v) => near(h, v))) fail('button_height', { ...where(b), got: h });
    check('button_wrap').checked++;
    if (lineCount(b) > 1) fail('button_wrap', { ...where(b), lines: lineCount(b) });
    check('button_clip').checked++;
    const clipped = b.scrollWidth > b.clientWidth + 1 || [...b.querySelectorAll('*')].some((c) => c.scrollWidth > c.clientWidth + 1 && getComputedStyle(c).overflow !== 'visible');
    if (clipped) {
      /* 말줄임을 **켠** 버튼(`truncate`: title + 라벨 칸 ellipsis)은 의도한 잘림이다. 그 밖의 잘림은
         정상 공간에서 라벨이 먹힌 것이다. */
      const label = b.querySelector(':scope > span');
      const optedIn = b.hasAttribute('title') && label && getComputedStyle(label).textOverflow === 'ellipsis';
      if (!optedIn) fail('button_clip', { ...where(b), constrained: !!b.closest('td,th,[role=cell]'), vw: innerWidth });
    }
  }
  out.button_hist = hist;
  const ibtns = all('.MuiIconButton-root').filter((el) => !el.closest('.MuiInputBase-root,.MuiAutocomplete-root,.MuiChip-root,.MuiSnackbar-root') && !inShell(el));
  const ihist = {};
  for (const b of ibtns) {
    const h = Math.round(hOf(b));
    bump(ihist, h);
    check('icon_button_height').checked++;
    if (!C.buttonHeights.some((v) => near(h, v))) fail('icon_button_height', { ...where(b), got: h });
  }
  out.icon_button_hist = ihist;

  // ── 세그먼티드 · 상태 칩 ────────────────────────────────────────────────
  for (const s of all('.k-segmented')) {
    check('segmented').checked++;
    const st = getComputedStyle(s);
    const inner = [...s.querySelectorAll('[role=tab],button')].filter(shown);
    const innerBad = inner.filter((i) => !near(hOf(i), C.segmented.inner)).map((i) => hOf(i));
    if (!near(hOf(s), C.segmented.outer) || !near(px(st.paddingTop), C.segmented.pad, 0.5) || innerBad.length) {
      fail('segmented', { ...where(s), outer: hOf(s), pad: st.paddingTop, inner: innerBad.slice(0, 3) });
    }
  }
  for (const s of all('.k-status-chip')) {
    check('status_chip').checked++;
    if (!near(hOf(s), C.statusChip)) fail('status_chip', { ...where(s), got: hOf(s) });
  }

  // ── 메시지 박스 ─────────────────────────────────────────────────────────
  const calloutBg = new Set();
  for (const c of all('.k-callout')) {
    if (c.tagName.toLowerCase() === 'p') continue; // inline 갈래는 상자가 아니다
    check('callout').checked++;
    const st = getComputedStyle(c);
    calloutBg.add(st.backgroundColor + '|' + st.borderTopColor);
    const problems = [];
    if (c.getAttribute('data-variant') !== 'bleed' && !near(px(st.borderLeftWidth), 1, 0.5)) problems.push('border-left ' + st.borderLeftWidth);
    const body = c.querySelector('.k-callout-body') || c;
    const icon = c.querySelector('svg');
    if (icon) {
      const ir = icon.getBoundingClientRect();
      if (!near(ir.width, C.calloutIcon) && !near(ir.width, 14)) problems.push('icon ' + Math.round(ir.width));
    }
    const compact = c.getAttribute('data-compact') === 'true' || px(st.paddingTop) < 10;
    const extraRows = c.querySelector('button,a[role=button],details,ul,ol') || (body.previousElementSibling && body.previousElementSibling.tagName !== 'svg');
    /* 전폭 띠(`bleed`)는 위 · 좌우 선이 없어 한 줄 높이가 테두리 하나만큼 낮다. */
    const singleWant = C.calloutSingle - (c.getAttribute('data-variant') === 'bleed' ? 1 : 0);
    if (!compact && lineCount(body) === 1 && !extraRows && !near(hOf(c), singleWant)) {
      problems.push('single-line height ' + hOf(c));
    }
    /* 동작이 든 상자(D-528) — 아이콘 · 첫 줄 · 동작이 한 가운데선에 선다. 첫 줄은 본문 첫 글자 줄 상자의 가운데다. */
    const actionBox = c.querySelector('.k-head-action');
    const firstLine = (() => {
      const w = document.createTreeWalker(body, NodeFilter.SHOW_TEXT);
      for (let n = w.nextNode(); n; n = w.nextNode()) {
        if (!n.textContent.trim()) continue;
        const rg = document.createRange();
        rg.selectNodeContents(n);
        const rs = [...rg.getClientRects()].filter((r) => r.width >= 1 && r.height >= 1);
        if (rs.length) return rs[0];
      }
      return null;
    })();
    const midOf = (r) => r.top + r.height / 2;
    if (actionBox && firstLine && shown(actionBox)) {
      const btn = actionBox.querySelector('button, a') || actionBox;
      const br = btn.getBoundingClientRect();
      const dAction = Math.abs(midOf(br) - midOf(firstLine));
      if (dAction > tol) problems.push('동작 가운데선 ' + dAction.toFixed(1));
      if (!near(br.height, C.calloutAction)) problems.push('동작 높이 ' + Math.round(br.height));
      if (icon) {
        const dIcon = Math.abs(midOf(icon.getBoundingClientRect()) - midOf(firstLine));
        if (dIcon > tol) problems.push('아이콘 가운데선 ' + dIcon.toFixed(1));
      }
      const plainRows = !c.querySelector('details,ul,ol') && lineCount(body) === 1;
      const want = compact ? C.calloutCompactAction : C.calloutSingleAction;
      if (plainRows && !near(hOf(c), want)) problems.push('동작 상자 높이 ' + hOf(c) + ' ≠ ' + want);
    }
    const role = c.getAttribute('role');
    if (role !== 'alert' && role !== 'status') problems.push('role ' + role);
    if (problems.length) fail('callout', { ...where(c), problems });
  }
  out.callout_backgrounds = [...calloutBg];

  // ── 배지 · 태그 · 건수 칩 ───────────────────────────────────────────────
  for (const b of all('.k-badge')) {
    const st = getComputedStyle(b);
    if (transparent(st.backgroundColor)) continue; // 면 없는 갈래는 점 + 낱말이다
    check('badge').checked++;
    const problems = [];
    if (!near(hOf(b), C.badge.h)) problems.push('h ' + hOf(b));
    if (!near(px(st.paddingLeft), C.badge.px, 1)) problems.push('px ' + st.paddingLeft);
    if (!near(px(st.borderTopLeftRadius), C.badge.r, 0.5)) problems.push('r ' + st.borderTopLeftRadius);
    if (String(st.fontWeight) !== String(C.badge.w)) problems.push('w ' + st.fontWeight);
    const dot = [...b.querySelectorAll('*')].find((d) => { const r = d.getBoundingClientRect(); const ds = getComputedStyle(d); return r.width > 2 && r.width <= 9 && near(r.width, r.height, 1) && px(ds.borderTopLeftRadius) >= r.width / 2 - 0.5 && !transparent(ds.backgroundColor); });
    if (dot) problems.push('dot inside');
    if (problems.length) fail('badge', { ...where(b), problems });
  }
  for (const t of all('.k-tag')) {
    check('tag').checked++;
    const st = getComputedStyle(t);
    const problems = [];
    if (!near(hOf(t), C.tag.h)) problems.push('h ' + hOf(t));
    if (!near(px(st.borderTopLeftRadius), C.tag.r, 0.5)) problems.push('r ' + st.borderTopLeftRadius);
    if (String(st.fontWeight) !== String(C.tag.w)) problems.push('w ' + st.fontWeight);
    if (transparent(st.backgroundColor)) problems.push('no surface');
    if (!near(px(st.borderTopWidth), 1, 0.5)) problems.push('border ' + st.borderTopWidth);
    if (problems.length) fail('tag', { ...where(t), problems });
  }
  for (const c of all('[data-count-chip]')) {
    check('count_chip').checked++;
    const want = c.getAttribute('data-count-chip') === 'compact' ? C.countChip.compact : C.countChip.default;
    if (!near(hOf(c), want)) fail('count_chip', { ...where(c), got: hOf(c), want });
  }

  // ── 필터 바 ─────────────────────────────────────────────────────────────
  const surfaces = all('[data-filter-surface]');
  for (const s of surfaces) {
    check('filter_surface').checked++;
    const st = getComputedStyle(s);
    const problems = [];
    if (!transparent(st.backgroundColor)) problems.push('background ' + st.backgroundColor);
    /* 다음 **흐름 안** 형제와 비교한다 — 화면 낭독 전용 제목(`sr-only`, absolute)은 flex 그릇(`.c-screen`) 안에서 그릇 첫머리에
       정적 자리를 잡아 겹친 것처럼 읽혔다(P3 실측: 사용자 화면). 흐름 밖 요소는 덮지 않는다. */
    let next = s.nextElementSibling;
    while (next && (!shown(next) || /^(absolute|fixed)$/.test(getComputedStyle(next).position))) next = next.nextElementSibling;
    if (next && next.getBoundingClientRect().top < s.getBoundingClientRect().bottom - 1) problems.push('overlaps next sibling');
    if (problems.length) fail('filter_surface', { ...where(s), problems });
    for (const sw of s.querySelectorAll('.MuiSwitch-root')) {
      if (!shown(sw)) continue;
      check('filter_switch').checked++;
      fail('filter_switch', where(sw.closest('label') || sw));
    }
    if (!s.querySelector('.MuiSwitch-root')) check('filter_switch').checked++;
    const rows = new Map();
    for (const f of s.querySelectorAll('[data-filter-kind]')) {
      if (!shown(f)) continue;
      const box = f.querySelector('.MuiInputBase-root') || f;
      check('filter_cell').checked++;
      if (!near(hOf(box), C.filterCell)) fail('filter_cell', { ...where(f), got: hOf(box), kind: f.getAttribute('data-filter-kind') });
      const legend = f.querySelector('legend > span');
      check('filter_notched').checked++;
      if (legend && legend.textContent.replace(/​/g, '').trim() && legend.getBoundingClientRect().width > 2) {
        fail('filter_notched', { ...where(f), label: legend.textContent.trim() });
      }
      const row = f.parentElement;
      if (!rows.has(row)) rows.set(row, []);
      rows.get(row).push(box.getBoundingClientRect());
      if (f.getAttribute('data-filter-kind') === 'search' && (f.parentElement.matches('[data-filter-row]') || f.closest('[data-filter-surface]'))) {
        check('search_slot').checked++;
        /* 면 안의 검색 칸은 필터 면의 내용 폭이 계단을 고른다(D-530) — 64rem 이상 20rem · 44 ~ 64rem 16rem · 그보다 좁으면 제 줄
           전체. 면 밖이면 계단을 못 보므로 20rem 이다. */
        const surf = f.closest('[data-filter-surface]');
        let want = C.searchSlot;
        if (surf) {
          const rp = px(getComputedStyle(document.documentElement).fontSize) || 16;
          const ss = getComputedStyle(surf);
          const inner = (surf.clientWidth - px(ss.paddingLeft) - px(ss.paddingRight)) / rp;
          const step = (C.searchSlotSteps || []).find(([minRem]) => inner >= minRem);
          want = step ? step[1] * rp : f.parentElement.getBoundingClientRect().width;
        }
        const got = f.getBoundingClientRect().width;
        if (innerWidth >= 900 && !near(got, want)) fail('search_slot', { ...where(f), got: Math.round(got), want: Math.round(want) });
      }
    }
    for (const [, rects] of rows) {
      // 같은 줄(윗변이 12px 안)끼리 묶어 윗변 차이를 본다
      const lines = [];
      for (const r of rects) {
        const line = lines.find((l) => Math.abs(l[0].top - r.top) < 12);
        if (line) line.push(r); else lines.push([r]);
      }
      for (const l of lines) {
        if (l.length < 2) continue;
        check('filter_row_tops').checked++;
        const tops = l.map((r) => r.top);
        if (Math.max(...tops) - Math.min(...tops) > tol) fail('filter_row_tops', { tops: tops.map((t) => Math.round(t)) });
      }
    }
    for (const t of s.querySelectorAll('[data-filter-toggle]')) {
      if (!shown(t)) continue;
      check('filter_toggle').checked++;
      const aria = t.hasAttribute('aria-pressed') || t.hasAttribute('aria-expanded');
      if (!near(hOf(t), C.filterCell) || !aria) fail('filter_toggle', { ...where(t), got: hOf(t), aria });
    }
  }

  // ── 표 ──────────────────────────────────────────────────────────────────
  for (const t of all('table')) {
    const head = t.querySelector('thead tr');
    if (!head) continue;
    check('table_heights').checked++;
    const problems = [];
    if (!near(hOf(head), C.table.head)) problems.push('head ' + hOf(head));
    const bodyRows = [...t.querySelectorAll('tbody tr')].filter((r) => shown(r) && !r.hasAttribute('data-group-row') && r.querySelectorAll('td').length > 1);
    const short = bodyRows.filter((r) => hOf(r) < C.table.row - tol).map((r) => hOf(r));
    if (short.length) problems.push('row<48 ' + short.slice(0, 3).join(','));
    const groups = [...t.querySelectorAll('[data-group-row]')].filter(shown).filter((g) => !near(hOf(g), C.table.group)).map((g) => hOf(g));
    if (groups.length) problems.push('group ' + groups.slice(0, 3).join(','));
    if (problems.length) fail('table_heights', { rows: bodyRows.length, problems });
    const ths = [...head.children];
    const first = bodyRows[0];
    if (first) {
      check('table_align').checked++;
      const tds = [...first.children];
      const mism = [];
      ths.forEach((th, i) => {
        const td = tds[i];
        if (!td) return;
        const a = getComputedStyle(th).textAlign, b = getComputedStyle(td).textAlign;
        const norm = (v) => (v === 'left' ? 'start' : v === 'right' ? 'end' : v);
        if (norm(a) !== norm(b)) mism.push(i + ':' + a + '/' + b);
      });
      if (mism.length) fail('table_align', { mism: mism.slice(0, 4) });
    }
  }

  // ── 카드 ────────────────────────────────────────────────────────────────
  const padHist = {};
  for (const c of all('.MuiCard-root')) {
    if (c.hasAttribute('data-card-kind')) continue; // 칸반 카드 등 자기 계약이 있는 판
    const st = getComputedStyle(c);
    const p = Math.round(px(st.paddingTop)) + '/' + Math.round(px(st.paddingLeft));
    bump(padHist, p);
    if (px(st.paddingTop) === 0 && px(st.paddingLeft) === 0) continue; // 목록 판(p:0)은 안쪽이 부품이다
    check('card_padding').checked++;
    if (!near(px(st.paddingLeft), C.cardPadding) || !near(px(st.paddingTop), C.cardPadding)) {
      fail('card_padding', { ...where(c), got: p });
    }
  }
  out.card_padding_hist = padHist;
  // 같은 부모 안에서 같은 줄에 선 카드의 윗변
  const parents = new Map();
  for (const c of all('.MuiCard-root')) {
    const p = c.parentElement;
    if (!p) continue;
    const d = getComputedStyle(p).display;
    if (!/grid|flex/.test(d)) continue;
    if (!parents.has(p)) parents.set(p, []);
    parents.get(p).push(c.getBoundingClientRect());
  }
  for (const [, rects] of parents) {
    const lines = [];
    for (const r of rects) {
      const line = lines.find((l) => Math.abs(l[0].top - r.top) < 24 && !l.some((x) => x.left === r.left));
      if (line) line.push(r); else lines.push([r]);
    }
    for (const l of lines) {
      if (l.length < 2) continue;
      check('card_row_tops').checked++;
      const tops = l.map((r) => r.top);
      if (Math.max(...tops) - Math.min(...tops) > tol) fail('card_row_tops', { tops: tops.map((t) => Math.round(t)) });
    }
  }

  // ── 페이지 머리 ─────────────────────────────────────────────────────────
  for (const h of all('.k-page-head')) {
    const title = h.querySelector('h1');
    const actions = h.querySelector('.k-page-actions');
    if (!title || !actions || !shown(actions)) continue;
    check('page_head_overlap').checked++;
    const a = title.getBoundingClientRect(), b = actions.getBoundingClientRect();
    const overlap = !(a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top);
    if (overlap) fail('page_head_overlap', { title: text(title), actions: text(actions) });
  }

  // ── 모달 · 떠 있는 것 ───────────────────────────────────────────────────
  for (const d of [...scope.querySelectorAll('.MuiDialog-paper')].filter(shown)) {
    check('modal').checked++;
    const st = getComputedStyle(d);
    const problems = [];
    if (!near(px(st.borderTopLeftRadius), C.modal.radius, 0.5)) problems.push('radius ' + st.borderTopLeftRadius);
    const title = d.querySelector('h2, .MuiDialogTitle-root');
    if (title) {
      const ts = getComputedStyle(title);
      if (!near(px(ts.fontSize), C.modal.titleSize, 0.5)) problems.push('title size ' + ts.fontSize);
      if (String(ts.fontWeight) !== String(C.modal.titleWeight)) problems.push('title weight ' + ts.fontWeight);
    }
    const close = d.querySelector('[aria-label="닫기"]');
    if (close && !near(hOf(close), C.modal.close)) problems.push('close ' + hOf(close));
    if (problems.length) fail('modal', { title: title ? text(title) : '', problems });
  }
  for (const p of [...scope.querySelectorAll('.MuiPopover-paper, .MuiMenu-paper, .noti-pop, .MuiSnackbarContent-root, .MuiAlert-root.k-toast')].filter(shown)) {
    check('floating_radius').checked++;
    const r = px(getComputedStyle(p).borderTopLeftRadius);
    if (!near(r, C.floatingRadius, 0.5)) fail('floating_radius', { cls: p.className.toString().slice(0, 60), r });
  }
  for (const f of all('[data-action-footer]')) {
    check('footer_owner').checked++;
    /* 발의 면 색과 **같은 면**에 위 선까지 가진 요소를 센다(발 자신 · 안쪽 · 바로 바깥). 모달 판처럼
       다른 면을 가진 바깥 상자는 발의 주인이 아니다. */
    const faceBg = getComputedStyle(f).backgroundColor;
    /* 발 안의 단추 · 입력은 면의 주인이 아니다 — 꺼진 보조 단추는 함몰면과 같은 색에 테두리를 든다(LLM 콘솔 「되돌리기」, UI 3차 P4). */
    const control = (el) => el !== f && el !== f.parentElement && !!el.closest('button, [role="button"], .MuiInputBase-root');
    const owners = [f.parentElement, f, ...f.querySelectorAll('*')]
      .filter(Boolean).filter((el) => !control(el))
      .filter((el) => { const s = getComputedStyle(el); return !transparent(s.backgroundColor) && s.backgroundColor === faceBg && px(s.borderTopWidth) >= 1; });
    if (owners.length !== 1) fail('footer_owner', { owners: owners.length, text: text(f) });
  }
  for (const o of all('[data-picker-option]')) {
    check('picker_option').checked++;
    const av = o.querySelector('.MuiAvatar-root, img');
    const problems = [];
    if (!near(hOf(o), C.picker.h)) problems.push('h ' + hOf(o));
    if (av && !near(av.getBoundingClientRect().width, C.picker.avatar)) problems.push('avatar ' + Math.round(av.getBoundingClientRect().width));
    if (problems.length) fail('picker_option', { ...where(o), problems });
  }

  // ── 빈 상태 · 오류 · 마스코트 ───────────────────────────────────────────
  for (const e of all('.k-empty[data-empty-layout], [data-error-layout]')) {
    const layout = e.getAttribute('data-empty-layout') || e.getAttribute('data-error-layout');
    const st = getComputedStyle(e);
    if (layout === 'region' || layout === 'card') {
      check('empty_layout').checked++;
      if (st.textAlign === 'center' || st.alignContent === 'center') fail('empty_layout', { ...where(e), layout, textAlign: st.textAlign, alignContent: st.alignContent });
    }
    if (e.hasAttribute('data-error-layout')) {
      check('error_icon').checked++;
      if (!e.querySelector('svg')) fail('error_icon', { ...where(e), layout });
    }
    const img = e.querySelector('img[data-mascot-context], img[src*="empty"], img[src*="state-"], img[src*="clovi"]');
    if (img && shown(img)) {
      check('mascot_size').checked++;
      /* 박스가 아니라 **보이는 캐릭터**를 잰다 — 자산마다 투명 여백이 달라 박스 = 보이는 크기 / hfrac 이다
         (`mascot-bounds.json`). 모르는 자산은 여백이 없다고 본다(크기를 부풀리지 않는다). */
      const file = (img.getAttribute('src') || '').split('/').pop();
      const hfrac = (C.mascotHfrac && C.mascotHfrac[file]) || 1;
      /* 배치 높이를 잰다 — 숨쉬기 · 등장 애니메이션의 `scale` 이 걸린 순간의 테두리 상자(getBoundingClientRect)는 계약 크기보다
         1 ~ 2px 크다(P17V 실측: 132 계약의 쉬는 클로비가 134 로 걸렸다). */
      const visible = (img.offsetHeight || img.getBoundingClientRect().height) * hfrac;
      const ok = layout === 'page' ? visible <= C.mascot.pageMax + tol : visible <= C.mascot.region + tol;
      if (!ok) fail('mascot_size', { ...where(e), layout, visible: Math.round(visible), file });
    }
  }

  // ── 폼 칸 격자 (§0-9 · 표 8) ────────────────────────────────────────────
  /* 같은 격자 안의 칸(`[data-form-field]`)을 줄로 묶어 잰다 — ① 같은 줄 입력칸의 윗변이 같은가, ② 라벨 줄이
     1.25rem(20) 인가, ③ 줄이 빈틈 없이 찼는가(줄은 격자 왼끝에서 시작하고 마지막 줄 말고는 격자 오른끝에서
     끝난다), ④ 화면 순서(줄 우선)가 DOM 순서와 같은가. 격자 폭과 줄마다 칸 폭은 기록으로 남긴다. */
  const rootPx = px(getComputedStyle(document.documentElement).fontSize) || 16;
  const fieldGrids = new Map();
  for (const cell of all('[data-form-field]')) {
    const g = cell.parentElement;
    if (!g) continue;
    if (!fieldGrids.has(g)) fieldGrids.set(g, []);
    fieldGrids.get(g).push(cell);
  }
  out.form_grids = [];
  for (const [g, cells] of fieldGrids) {
    const gr = g.getBoundingClientRect();
    const rows = [];
    for (const c of cells) {
      const r = c.getBoundingClientRect();
      const row = rows.find((x) => Math.abs(x.top - r.top) <= tol);
      if (row) row.cells.push(c); else rows.push({ top: r.top, cells: [c] });
    }
    rows.sort((a, b) => a.top - b.top);
    const leftOf = (c) => c.getBoundingClientRect().left;
    const visual = rows.flatMap((x) => [...x.cells].sort((a, b) => leftOf(a) - leftOf(b)));
    check('form_field_rows').checked++;
    const problems = [];
    if (visual.some((c, i) => c !== cells[i])) problems.push('order');
    rows.forEach((row, i) => {
      const fieldTops = row.cells.map((c) => (c.children[1] || c).getBoundingClientRect().top);
      if (Math.max(...fieldTops) - Math.min(...fieldTops) > tol) problems.push(`row ${i} field tops ${fieldTops.map(Math.round)}`);
      for (const c of row.cells) {
        const track = c.children[1] ? c.children[1].getBoundingClientRect().top - c.getBoundingClientRect().top : 0;
        if (!near(track, 1.25 * rootPx)) problems.push(`row ${i} label track ${Math.round(track)}`);
      }
      const rects = row.cells.map((c) => c.getBoundingClientRect()).sort((a, b) => a.left - b.left);
      if (!near(rects[0].left, gr.left)) problems.push(`row ${i} starts +${Math.round(rects[0].left - gr.left)}`);
      if (i < rows.length - 1 && !near(rects[rects.length - 1].right, gr.right)) problems.push(`row ${i} hole ${Math.round(gr.right - rects[rects.length - 1].right)}`);
    });
    const record = {
      w: Math.round(gr.width),
      rows: rows.map((row) => row.cells.map((c) => Math.round(c.getBoundingClientRect().width))),
      fieldH: rows.map((row) => row.cells.map((c) => (c.children[1] ? Math.round(c.children[1].getBoundingClientRect().height) : 0))),
    };
    out.form_grids.push(record);
    if (problems.length) fail('form_field_rows', { ...record, problems: problems.slice(0, 6) });
  }

  // ── 채팅방 (핸드오프 RULES §9 · `ui/chat.js::CHAT`) ────────────────────────
  /* 목록 판 296 · 말풍선 묶음이 스레드 폭의 68% 이하 · 상대 얼굴 34 · 머리 얼굴 26 · 입력 상자 모서리 10 ·
     머리 세 묶음이 서로 겹치지 않는가. 줄 자리가 없는 화면에서는 표본이 0 이다. */
  for (const layout of all('[data-chat-layout]')) {
    const cards = [...layout.children].filter((el) => el.classList.contains('MuiCard-root') && shown(el));
    if (cards.length < 2) continue;
    check('chat_layout').checked++;
    const w = cards[0].getBoundingClientRect().width;
    if (!near(w, C.chat.list)) fail('chat_layout', { what: 'list width', w: Math.round(w) });
  }
  for (const bubble of all('[data-chat-bubble]')) {
    const group = bubble.parentElement;
    const row = bubble.closest('[data-chat-row]');
    const log = row && row.parentElement;
    if (!group || !log) continue;
    check('chat_layout').checked++;
    const gw = group.getBoundingClientRect().width;
    const lw = log.getBoundingClientRect().width;
    if (gw > lw * C.chat.bubbleMax + tol) fail('chat_layout', { what: 'bubble group > 68%', group: Math.round(gw), log: Math.round(lw), text: text(bubble) });
    if (bubble.getBoundingClientRect().right > log.getBoundingClientRect().right + tol) fail('chat_layout', { what: 'bubble overflows log', text: text(bubble) });
  }
  for (const row of all('[data-chat-row="theirs"]')) {
    const av = row.querySelector('.k-avatar');
    if (!av || !shown(av)) continue;
    check('chat_layout').checked++;
    if (!near(av.getBoundingClientRect().width, C.chat.avatar)) fail('chat_layout', { what: 'avatar', w: Math.round(av.getBoundingClientRect().width) });
  }
  for (const item of all('[data-member-faces] [role="listitem"] .k-avatar')) {
    check('chat_layout').checked++;
    if (!near(item.getBoundingClientRect().width, C.chat.stack)) fail('chat_layout', { what: 'stack avatar', w: Math.round(item.getBoundingClientRect().width) });
  }
  for (const comp of all('[data-chat-composer]')) {
    check('chat_layout').checked++;
    const r = px(getComputedStyle(comp).borderTopLeftRadius);
    if (!near(r, C.chat.composerRadius, 0.5)) fail('chat_layout', { what: 'composer radius', r });
  }
  for (const head of all('[data-room-head]')) {
    const groups = [...head.querySelectorAll(':scope > [data-room-head-group]')].filter(shown).map((g) => [g.getAttribute('data-room-head-group'), g.getBoundingClientRect()]);
    if (groups.length < 2) continue;
    check('chat_layout').checked++;
    for (let i = 0; i < groups.length; i += 1) {
      for (let j = i + 1; j < groups.length; j += 1) {
        const a = groups[i][1], b = groups[j][1];
        const overlap = a.left < b.right - tol && b.left < a.right - tol && a.top < b.bottom - tol && b.top < a.bottom - tol;
        if (overlap) fail('chat_layout', { what: 'room head groups overlap', a: groups[i][0], b: groups[j][0] });
      }
    }
  }

  // ── 스위치 (D-525) ─────────────────────────────────────────────────────
  /* 보이는 스위치마다 잰다 — 손잡이가 트랙 안에 있고 여백이 위 · 아래 · 끝(꺼짐은 왼쪽, 켜짐은 오른쪽)에서 같은가,
     트랙이 완전한 알약이고 손잡이가 원인가, 트랙이 누르는 자리(루트) 가운데에 서고 초점 링이 루트 안에 들어오는가,
     누르는 자리가 44×44 이상이고 줄이 보는 높이(루트 + 바깥 여백)가 34 인가, 트랙 · 손잡이가 계약 크기인가.
     크기는 루트 글자(4K 레버)에 비례하고 링은 px 이다 — 옛 결함(루트 폭만 px)은 18 · 20px 루트에서만 드러났다. */
  const swScale = rootPx / 16;
  /* 브라우저가 실제로 쓰는 모서리 반지름. 계산값은 `50%` 를 퍼센트 그대로 내주므로 px 로 읽으면 50 이 되어 아무 모서리나
     통과한다 — 퍼센트를 상자 크기로 풀고, 이웃한 반지름의 합이 변보다 크면 전부 같은 비율로 줄이는 CSS 규칙까지 따른다. */
  const usedRadius = (el, r) => {
    const s = getComputedStyle(el);
    const pair = (v) => {
      const [a, b = a] = String(v).split(' ');
      const len = (x, d) => (x.endsWith('%') ? (parseFloat(x) / 100) * d : px(x));
      return [len(a, r.width), len(b, r.height)];
    };
    const tl = pair(s.borderTopLeftRadius), tr = pair(s.borderTopRightRadius);
    const br = pair(s.borderBottomRightRadius), bl = pair(s.borderBottomLeftRadius);
    const f = Math.min(1, r.width / ((tl[0] + tr[0]) || 1), r.width / ((bl[0] + br[0]) || 1),
      r.height / ((tl[1] + bl[1]) || 1), r.height / ((tr[1] + br[1]) || 1));
    return { x: tl[0] * f, y: tl[1] * f };
  };
  for (const sw of all('.MuiSwitch-root')) {
    check('switch_geometry').checked++;
    const track = sw.querySelector('.MuiSwitch-track');
    const thumb = sw.querySelector('.MuiSwitch-thumb');
    const base = sw.querySelector('.MuiSwitch-switchBase');
    const input = sw.querySelector('input');
    if (!track || !thumb || !base || !input) {
      fail('switch_geometry', { ...where(sw), problems: ['malformed switch'] });
      continue;
    }
    const R = sw.getBoundingClientRect();
    const T = track.getBoundingClientRect();
    const K = thumb.getBoundingClientRect();
    const I = input.getBoundingClientRect();
    const on = base.classList.contains('Mui-checked');
    const e = 0.6;
    const problems = [];
    if (K.left < T.left - e || K.right > T.right + e || K.top < T.top - e || K.bottom > T.bottom + e) problems.push('thumb outside track');
    const insets = [K.top - T.top, T.bottom - K.bottom, on ? T.right - K.right : K.left - T.left];
    if (Math.max(...insets) - Math.min(...insets) > e) problems.push('uneven inset ' + insets.map((v) => v.toFixed(1)).join('/'));
    const tr = usedRadius(track, T);
    if (Math.abs(tr.x - T.height / 2) > 0.5 || Math.abs(tr.y - T.height / 2) > 0.5) problems.push('track not a pill ' + tr.x.toFixed(1) + '/' + tr.y.toFixed(1));
    const kr = usedRadius(thumb, K);
    if (Math.abs(K.width - K.height) > 0.5 || Math.abs(kr.x - K.width / 2) > 0.5 || Math.abs(kr.y - K.height / 2) > 0.5) problems.push('thumb not round');
    if (Math.abs((T.top + T.bottom) / 2 - (R.top + R.bottom) / 2) > e
        || Math.abs((T.left + T.right) / 2 - (R.left + R.right) / 2) > e) problems.push('track off-center');
    const ring = C.switch.ring;
    if (T.left - ring < R.left - e || T.right + ring > R.right + e || T.top - ring < R.top - e || T.bottom + ring > R.bottom + e) problems.push('no room for focus ring');
    /* 누르는 자리는 루트가 아니라 **숨은 input** 이다 — 클릭을 받는 것은 input 이고, 루트의 overflow:hidden 이 그것을
       루트 안으로 자른다. 그래서 input 과 루트의 겹친 부분을 잰다. 루트가 자르지 않으면 input 이 줄 밖까지 클릭을 먹는다. */
    if (getComputedStyle(sw).overflow !== 'hidden') problems.push('root does not clip input');
    const hitW = Math.min(I.right, R.right) - Math.max(I.left, R.left);
    const hitH = Math.min(I.bottom, R.bottom) - Math.max(I.top, R.top);
    if (hitW < C.switch.hit * swScale - e || hitH < C.switch.hit * swScale - e) problems.push('hit ' + hitW.toFixed(1) + 'x' + hitH.toFixed(1));
    const rootStyle = getComputedStyle(sw);
    const layoutH = R.height + px(rootStyle.marginTop) + px(rootStyle.marginBottom);
    if (!near(layoutH, C.switch.layoutH * swScale)) problems.push('layout height ' + layoutH.toFixed(1));
    if (!near(T.width, C.switch.trackW * swScale) || !near(T.height, C.switch.trackH * swScale) || !near(K.width, C.switch.thumb * swScale)) {
      problems.push('size ' + T.width.toFixed(1) + 'x' + T.height.toFixed(1) + ' / ' + K.width.toFixed(1));
    }
    if (problems.length) {
      fail('switch_geometry', { ...where(sw), name: input.getAttribute('aria-label') || '', on, problems: problems.slice(0, 6) });
    }
  }

  // ── 같은 갈래의 높이 분산 ───────────────────────────────────────────────
  const variants = {
    'badge-face': all('.k-badge').filter((b) => !transparent(getComputedStyle(b).backgroundColor)),
    'tag': all('.k-tag'),
    'count-default': all('[data-count-chip]:not([data-count-chip=compact])'),
    'button-small': all('.MuiButton-sizeSmall').filter((el) => !insideSegmented(el) && !inShell(el)),
    'button-medium': all('.MuiButton-sizeMedium').filter((el) => !insideSegmented(el) && !inShell(el)),
  };
  for (const [name, els] of Object.entries(variants)) {
    if (els.length < 2) continue;
    check('variant_height').checked++;
    const hs = [...new Set(els.map((e) => Math.round(hOf(e))))];
    if (hs.length > 1) fail('variant_height', { variant: name, heights: hs.slice(0, 6) });
  }
  out.vw = innerWidth;
  return out;
}
"""

SELFTEST_HTML = r"""
(() => {
  const box = document.createElement('div');
  box.id = 'kit-selftest';
  box.style.cssText = 'position:absolute;left:0;top:0;width:1200px;background:#fff;z-index:99999;padding:16px;display:grid;gap:12px';
  /* 스위치 견본(D-525) — MUI 구조(루트 > switchBase > input + 손잡이, 그 형제 트랙)를 인라인 치수로 그린다. 기본값이 맞는
     견본이고, 틀린 견본은 값 하나씩만 어긋낸다 — 무엇을 잡았는지 한 가지로 읽히게. */
  const sw = ({ name, w = 50, h = 44, padY = 11, padX = 6, margin = -5, baseY = 14, baseX = 9, baseTop = 0, thumb = 16, travel = 0, radius = '999px', on = false }) =>
    `<span class="MuiSwitch-root" style="display:inline-flex;position:relative;box-sizing:border-box;width:${w}px;height:${h}px;padding:${padY}px ${padX}px;margin:${margin}px 0;overflow:hidden;vertical-align:middle;flex-shrink:0">`
    + `<span class="MuiSwitch-switchBase${on ? ' Mui-checked' : ''}" style="position:absolute;top:${baseTop}px;left:0;z-index:1;box-sizing:border-box;display:inline-flex;padding:${baseY}px ${baseX}px;transform:translateX(${travel}px)">`
    + `<input type="checkbox" role="switch" aria-label="${name}" style="position:absolute;top:0;left:-100%;width:300%;height:100%;margin:0;opacity:0">`
    + `<span class="MuiSwitch-thumb" style="display:block;width:${thumb}px;height:${thumb}px;border-radius:50%;background:#737b99"></span></span>`
    + `<span class="MuiSwitch-track" style="display:block;box-sizing:border-box;width:100%;height:100%;border-radius:${radius};border:1px solid #737b99"></span></span>`;
  box.innerHTML = `
    <div id="good">
      <button class="MuiButton-root MuiButton-sizeMedium" style="height:34px;white-space:nowrap;padding:0 12px">저장</button>
      <span class="k-badge" style="display:inline-flex;align-items:center;height:22px;padding:0 8px;border-radius:4px;font-weight:600;background:#e9edf9;font-size:12px">완료</span>
      <span class="k-tag" style="display:inline-flex;align-items:center;height:22px;padding:0 8px;border-radius:6px;font-weight:400;background:#fff;border:1px solid #dcdfec;font-size:12px">Docker</span>
      <span data-count-chip="" style="display:inline-flex;height:20px;padding:0 6px">3</span>
      <div style="display:grid;grid-template-columns:repeat(12,minmax(0,1fr));column-gap:20px;row-gap:20px;width:800px">
        ${[12, 6, 3, 3, 3, 3, 3, 3].map((n) => `<div data-form-field="" style="grid-column:span ${n};display:grid;grid-template-rows:20px minmax(36px,auto) auto"><span>칸</span><div style="height:36px;border:1px solid #ccc"></div><div></div></div>`).join('')}
      </div>
      <div class="MuiDialog-paper" style="width:400px;border-radius:8px;border:1px solid #ccc;padding:8px">
        <h2 style="margin:0;font-size:17px;font-weight:700">모달 제목</h2>
        <button aria-label="닫기" style="height:30px;width:30px">x</button>
      </div>
      <div class="MuiPopover-paper" style="width:120px;height:40px;border-radius:8px;border:1px solid #ccc"></div>
      <div data-action-footer="card" style="display:flex;gap:8px;justify-content:flex-end;padding:12px 20px;background:#f5f6fb;border-top:1px solid #e5e8f3">
        <button class="MuiButton-root MuiButton-sizeMedium" disabled style="height:34px;padding:0 12px;background:#f5f6fb;border:1px solid #dcdfec">되돌리기</button>
        <button class="MuiButton-root MuiButton-sizeMedium" style="height:34px;padding:0 12px;background:#5b4fd6;color:#fff;border:0">저장</button>
      </div>
      <div style="width:600px">
        <div data-chat-row="mine" style="display:grid;justify-items:end"><div style="display:flex;max-width:68%"><div data-chat-bubble="mine" style="width:fit-content;padding:10px 14px">짧은 말</div></div></div>
        <div data-chat-composer="" style="border:1px solid #ccc;border-radius:10px;height:60px"></div>
      </div>
      <div style="display:flex;gap:16px;align-items:center;padding:8px 0">${sw({ name: '맞는 꺼짐' })}${sw({ name: '맞는 켜짐', on: true, travel: 16 })}</div>
    </div>
    <div id="bad">
      <button class="MuiButton-root MuiButton-sizeMedium" style="height:40px;padding:0 12px">큰 버튼</button>
      <button class="MuiButton-root MuiButton-sizeSmall" style="width:60px;height:auto;min-height:30px;white-space:normal;padding:0 4px">아주 긴 두 줄 버튼 라벨</button>
      <span class="k-badge" style="display:inline-flex;align-items:center;gap:4px;height:22px;padding:0 8px;border-radius:4px;font-weight:600;background:#e9edf9;font-size:12px"><i style="display:inline-block;width:6px;height:6px;border-radius:50%;background:#1f5fbf"></i>점 배지</span>
      <span class="k-tag" style="display:inline-flex;align-items:center;height:22px;padding:0 8px;border-radius:6px;font-weight:600;background:#fff;border:1px solid #dcdfec;font-size:12px">굵은 태그</span>
      <span data-count-chip="" style="display:inline-flex;height:24px;padding:0 6px">12</span>
      <div data-filter-surface="" style="background:transparent">
        <div data-filter-row="" style="display:flex;gap:12px">
          <div data-filter-kind="enum" class="MuiFormControl-root"><div class="MuiInputBase-root" style="height:36px;width:160px;border:1px solid #ccc"><fieldset><legend><span>상태</span></legend></fieldset></div></div>
          <div data-filter-kind="search" class="MuiFormControl-root" style="width:500px"><div class="MuiInputBase-root" style="height:34px;border:1px solid #ccc"></div></div>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(12,minmax(0,1fr));column-gap:20px;row-gap:20px;width:800px">
        ${[12, 6, 3, 6].map((n) => `<div data-form-field="" style="grid-column:span ${n};display:grid;grid-template-rows:20px minmax(36px,auto) auto"><span>빈틈</span><div style="height:36px;border:1px solid #ccc"></div><div></div></div>`).join('')}
      </div>
      <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));column-gap:20px;width:600px">
        <div data-form-field="" style="display:grid;grid-template-rows:20px minmax(36px,auto) auto"><span>칸</span><div style="height:36px;border:1px solid #ccc"></div><div></div></div>
        <div data-form-field="" style="display:grid;grid-template-rows:28px minmax(36px,auto) auto"><span>어긋난 라벨</span><div style="height:36px;border:1px solid #ccc"></div><div></div></div>
      </div>
      <div class="MuiDialog-paper" style="width:400px;border-radius:14px;border:1px solid #ccc;padding:8px">
        <h2 style="margin:0;font-size:19px;font-weight:800">모달 제목</h2>
        <button aria-label="닫기" style="height:34px;width:34px">x</button>
      </div>
      <div class="MuiPopover-paper" style="width:120px;height:40px;border-radius:14px;border:1px solid #ccc"></div>
      <div style="background:#f5f6fb;border-top:1px solid #e5e8f3;padding:8px">
        <div data-action-footer="card" style="display:flex;justify-content:flex-end;padding:12px 20px;background:#f5f6fb;border-top:1px solid #e5e8f3"><button class="MuiButton-root MuiButton-sizeMedium" style="height:34px;padding:0 12px">두 겹 발</button></div>
      </div>
      <div style="width:600px">
        <div data-chat-row="mine" style="display:grid;justify-items:end"><div style="display:flex;max-width:90%"><div data-chat-bubble="mine" style="width:500px;padding:10px 14px">넓게 퍼진 말풍선</div></div></div>
        <div data-chat-composer="" style="border:1px solid #ccc;border-radius:20px;height:60px"></div>
      </div>
      <div style="display:flex;gap:16px;align-items:center;padding:8px 0">
        ${sw({ name: '옛 막대', w: 58, h: 34, padY: 7, padX: 12, margin: 0, baseY: 9, baseX: 14, radius: '7px', on: true, travel: 14 })}
        ${sw({ name: '끝을 넘은 손잡이', on: true, travel: 21 })}
        ${sw({ name: '고르지 않은 여백', baseX: 8 })}
        ${sw({ name: '좁은 누르는 자리', h: 34, padY: 6, margin: 0, baseY: 9 })}
        ${sw({ name: '타원 트랙', radius: '50%' })}
        ${sw({ name: '그림만 맞고 누르는 자리는 34', baseTop: 5, baseY: 9 })}
      </div>
    </div>`;
  document.body.appendChild(box);
  return true;
})()
"""

# 틀린 견본이 반드시 걸려야 하는 검사와 기대 최소 실패 수, 맞는 견본이 걸리면 안 되는 검사.
SELFTEST_EXPECT_BAD = {
    "button_height": 1, "button_wrap": 1, "badge": 1, "tag": 1, "count_chip": 1,
    "filter_cell": 1, "filter_notched": 1, "search_slot": 1, "form_field_rows": 2, "chat_layout": 2,
    "modal": 1, "floating_radius": 1, "footer_owner": 1, "switch_geometry": 6,
}


def _merge(total: dict, page_result: dict, where: str) -> None:
    for name in ALL_CHECKS:
        got = page_result.get(name)
        if not got:
            continue
        slot = total[name]
        slot["checked"] += got.get("checked", 0)
        slot["failed"] += got.get("failed", 0)
        for sample in got.get("bad", []):
            if len(slot["samples"]) < 40:
                slot["samples"].append({"at": where, **sample})


def selftest(args) -> int:
    from scripts.ui_qa import capture as cap, routes as routes_mod, tls
    from scripts.ui_qa.auth import ensure_session
    from playwright.sync_api import sync_playwright

    base = args.base_url or cap.DEFAULT_BASE_URL
    insecure = tls.apply_default_https_context()
    route = routes_mod.BY_ID["user_kit"]
    auth_dir = Path(args.auth_dir) if args.auth_dir else OUT_BASE / "auth-measure"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            session = ensure_session(browser, base, auth_dir, insecure=insecure, log=print)
            ctx = cap.new_context(browser, storage_state=session.storage_state, user_id=session.user_id,
                                  theme="light", viewport=cap.resolve_viewports(["1920x1080"])[0],
                                  insecure=insecure)
            page = ctx.new_page()
            page.goto(route.url(base, route.hash_path), wait_until="domcontentloaded", timeout=45_000)
            cap._settle(page, settle_ms=600, timeout_ms=45_000)
            page.evaluate(SELFTEST_HTML)
            good = page.evaluate(MEASURE_JS, {**CONTRACT, "scope": "#kit-selftest #good"})
            bad = page.evaluate(MEASURE_JS, {**CONTRACT, "scope": "#kit-selftest #bad"})
            # 조합 검사 견본은 따로 붙인다 — 부품 견본의 틀린 줄이 조합 판정에 섞이지 않게.
            page.evaluate("() => { const k = document.getElementById('kit-selftest'); if (k) k.remove(); }")
            page.evaluate(selftest_html())
            c_good = page.evaluate(COMPOSITION_JS, {**COMPOSITION_CONTRACT, "scope": "#compose-selftest #compose-good"})
            c_bad = page.evaluate(COMPOSITION_JS, {**COMPOSITION_CONTRACT, "scope": "#compose-selftest #compose-bad"})
            # 시각 규율 견본은 화면 전체를 쓰는 문서라 빈 쪽에 따로 연다(F7).
            v_page = ctx.new_page()
            v_page.set_viewport_size({"width": 1366, "height": 768})
            v_results = {}
            for kind in ("good", "bad"):
                v_page.set_content(visual_probes.fixture_html(kind), wait_until="load")
                v_results[kind] = v_page.evaluate(VISUAL_JS, {**VISUAL_CONTRACT, "scope": None})
            ctx.close()
        finally:
            browser.close()
    problems = []
    for name, want in SELFTEST_EXPECT_BAD.items():
        got = (bad.get(name) or {}).get("failed", 0)
        if got < want:
            problems.append(f"틀린 견본을 못 잡음: {name} (실패 {got} < {want})")
    for name in CHECKS:
        if (good.get(name) or {}).get("failed", 0):
            problems.append(f"맞는 견본을 잘못 잡음: {name} → {good[name]['bad'][:2]}")
    checked_good = sum((good.get(n) or {}).get("checked", 0) for n in CHECKS)
    if checked_good < 4:
        problems.append(f"맞는 견본 표본이 너무 적다({checked_good})")
    problems += [f"조합: {p}" for p in selftest_verdict(c_good, c_bad)]
    problems += [f"시각: {p}" for p in visual_probes.selftest_verdict(v_results["good"], v_results["bad"])]
    if problems:
        for p in problems:
            print("[SELFTEST] " + p)
        print("KIT_MEASURE_SELFTEST_FAILED")
        return 1
    c_checked = sum((c_good.get(n) or {}).get("checked", 0) for n in COMPOSITION_CHECKS)
    # 조합 틀린 견본 수는 **실제로 잡힌 검사 수**로 센다 — 검사 수에서 손으로 빼던 값은 견본이 늘어도 그대로였다.
    c_caught = sum(1 for n in COMPOSITION_CHECKS if (c_bad.get(n) or {}).get("failed"))
    print(f"KIT_MEASURE_SELFTEST_OK (부품 틀린 견본 {len(SELFTEST_EXPECT_BAD)}종 · 조합 틀린 견본 "
          f"{c_caught}종 전부 잡음, 맞는 견본 표본 {checked_good} + {c_checked} 오탐 0)")
    return 0


def measure(args) -> int:
    from scripts.ui_qa import capture as cap, routes as routes_mod, tls
    from scripts.ui_qa.auth import ensure_session
    from playwright.sync_api import sync_playwright

    base = args.base_url or cap.DEFAULT_BASE_URL
    insecure = tls.apply_default_https_context()
    routes = routes_mod.resolve(args.routes or ["user_kit"])
    viewports = cap.resolve_viewports(args.viewports or ["1920x1080"])
    themes = args.measure_themes or ["light"]
    out_root = Path(args.out_root) if args.out_root else OUT_BASE
    out_dir = out_root / args.measure_label
    auth_dir = Path(args.auth_dir) if args.auth_dir else OUT_BASE / "auth-measure"
    out_dir.mkdir(parents=True, exist_ok=True)
    total = defaultdict(lambda: {"checked": 0, "failed": 0, "samples": []})
    pages: dict[str, dict] = {}
    hfrac = _mascot_hfrac()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            session = ensure_session(browser, base, auth_dir, insecure=insecure, log=print)
            probe = browser.new_context(storage_state=session.storage_state, ignore_https_errors=insecure)
            hashes: dict[str, str] = {}
            try:
                for route in routes:
                    if route.is_detail:
                        found, note = cap.discover_detail_hash(probe, base, route, log=print)
                        if found:
                            hashes[route.id] = found
            finally:
                probe.close()
            for theme in themes:
                for viewport in viewports:
                    ctx = cap.new_context(browser, storage_state=session.storage_state,
                                          user_id=session.user_id, theme=theme, viewport=viewport,
                                          insecure=insecure)
                    page = ctx.new_page()
                    try:
                        for route in routes:
                            if route.is_public or not route.visible_to(session.role):
                                continue
                            if route.is_detail and route.id not in hashes:
                                continue
                            page.goto(route.url(base, hashes.get(route.id, route.hash_path)),
                                      wait_until="domcontentloaded", timeout=45_000)
                            cap._settle(page, settle_ms=args.settle_ms, timeout_ms=45_000)
                            # 마우스를 화면 구석으로 뺀다 — 앞 화면에서 모달을 열던 자리에 포인터가 남으면 그 아래 카드가
                            # hover 로 떠올라(`translateY(-2px)`) 같은 줄 카드의 윗선 검사가 거짓으로 걸린다(G 실측: 놀이 목록).
                            page.mouse.move(0, 0)
                            page.wait_for_timeout(120)
                            root_px = page.evaluate("parseFloat(getComputedStyle(document.documentElement).fontSize) || 16")
                            contract = contract_for(root_px)
                            result = page.evaluate(MEASURE_JS, {**contract, "scope": None, "mascotHfrac": hfrac})
                            composed = page.evaluate(COMPOSITION_JS, {**COMPOSITION_CONTRACT, "scope": None,
                                                                      "expect": expect_for(route.id)})
                            if isinstance(composed, dict) and not composed.get("error"):
                                result.update(composed)
                            looked = page.evaluate(VISUAL_JS, {**VISUAL_CONTRACT, "scope": None})
                            if isinstance(looked, dict) and not looked.get("error"):
                                result.update(looked)
                            key = f"{route.id}__{theme}__{viewport.name}"
                            pages[key] = result
                            _merge(total, result, key)
                            fails = [n for n in ALL_CHECKS if (result.get(n) or {}).get("failed")]
                            print(f"[measure] {key:<50} " + (", ".join(fails) if fails else "ok"), flush=True)
                            if args.open_modals:
                                from scripts.ui_qa import interact

                                def on_open(pg, opener, probe, _key=key, _contract=contract):
                                    got = pg.evaluate(MEASURE_JS, {**_contract, "scope": ".MuiDialog-root", "mascotHfrac": hfrac})
                                    if isinstance(got, dict) and not got.get("error"):
                                        where = f"{_key}__modal:{opener}"
                                        pages[where] = got
                                        _merge(total, got, where)
                                        bad = [n for n in CHECKS if (got.get(n) or {}).get("failed")]
                                        print(f"[measure]   모달 «{opener}» " + (", ".join(bad) if bad else "ok"), flush=True)

                                interact.open_modals(page, limit=6, on_open=on_open)
                    finally:
                        page.close()
                        ctx.close()
        finally:
            browser.close()

    summary = {name: {"checked": total[name]["checked"], "failed": total[name]["failed"]} for name in ALL_CHECKS}
    (out_dir / "measure.json").write_text(json.dumps(
        {"contract": CONTRACT, "composition_contract": COMPOSITION_CONTRACT, "visual_contract": VISUAL_CONTRACT,
         "summary": summary,
         "samples": {n: total[n]["samples"] for n in ALL_CHECKS}, "pages": pages},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print("")
    print(f"{'검사':<22} {'표본':>6} {'실패':>6}")
    for name in ALL_CHECKS:
        if name == COMPOSITION_CHECKS[0]:
            print("-- 조합 --")
        if name == VISUAL_CHECKS[0]:
            print("-- 시각 규율(F7) --")
        s = summary[name]
        mark = "  ← 표본 0" if s["checked"] == 0 else ""
        print(f"{name:<22} {s['checked']:>6} {s['failed']:>6}{mark}")
    fail_on = args.fail_on or []
    unknown = [n for n in fail_on if n not in ALL_CHECKS]
    if unknown:
        print("[FATAL] 모르는 검사 이름: " + ", ".join(unknown))
        return 2
    blind = [n for n in fail_on if summary[n]["checked"] == 0]
    failed = [n for n in fail_on if summary[n]["failed"]]
    for n in failed:
        for sample in total[n]["samples"][:6]:
            print(f"  ✗ {n}: {json.dumps(sample, ensure_ascii=False)[:300]}")
    print(f"measure.json : {out_dir / 'measure.json'}")
    if failed:
        print("KIT_MEASURE_FAILED: " + ", ".join(failed))
        return 1
    if blind:
        print("KIT_MEASURE_BLIND (표본 0 — 미실행): " + ", ".join(blind))
        return 2
    print("KIT_MEASURE_OK" + (f" (--fail-on {', '.join(fail_on)})" if fail_on else " (보고만)"))
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="공통 부품 계약 실측")
    ap.add_argument("--routes", nargs="*", default=None)
    ap.add_argument("--viewports", nargs="*", default=None)
    ap.add_argument("--measure-themes", nargs="*", default=None)
    ap.add_argument("--measure-label", default="kit-measure")
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--settle-ms", type=int, default=600)
    ap.add_argument("--open-modals", action="store_true",
                    help="화면마다 모달을 열어 열린 모달 안을 잰다(파괴 동작 단추는 누르지 않는다)")
    ap.add_argument("--fail-on", nargs="*", default=None, dest="fail_on")
    ap.add_argument("--out-root", default=None,
                    help="결과 뿌리(기본 dist/ui-qa). 원격 설치처를 잴 때는 dist/ui-qa-remote 처럼 따로 둔다")
    ap.add_argument("--auth-dir", default=None,
                    help="세션 캐시 자리(기본 dist/ui-qa/auth-measure). 원격 계정 캐시를 로컬 캐시와 섞지 않는다")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest(args)
    return measure(args)


if __name__ == "__main__":
    raise SystemExit(main())
