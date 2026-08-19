"""Per-page geometry / DOM / console assertions.

Everything that needs the live DOM is collected in one ``page.evaluate`` pass
(``PROBE_JS``) so a page is only measured once; the Python side turns those raw
measurements into pass / fail / skip verdicts per assertion class.

Assertion classes (these strings are what ``--fail-on`` accepts):

  auth_ok                 the route actually rendered, not a /login bounce
  theme_applied           <html data-theme> matches the theme we forced
  horizontal_overflow     documentElement.scrollWidth <= clientWidth + 1
  console_errors          console.error / console message type "error"
  page_errors             uncaught exceptions (Playwright "pageerror")
  broken_images           <img> with naturalWidth === 0 after load
  duplicate_ids           the same id used by more than one element
  tiny_text               (width >= 2200 only) rendered text under 12 CSS px
  narrow_main             (width >= 3840 only) content column < 60% of viewport
  vertical_text_collapse  글자가 3자 미만/줄로 끊겨 세로로 흐르는 상태(줄 수로 직접 측정)
  fab_overlap             떠 있는 요소(마스코트 FAB 등)가 버튼·입력을 덮어 못 누르게 됨
  image_cropped           사용자가 올린 이미지를 object-fit:cover 로 잘라 보여줌
  content_clipped         스크롤할 수 없는 상자 안에서 내용이 넘쳐 잘림
  rail_wider_than_prose   상세 화면 곁열이 본문보다 넓다

레이아웃·콘텐츠 축(전부 advisory 로 시작한다 — `--fail-on` 기본값은 비어 있다):

  equal_column_split      폭은 똑같이 나눴는데 두 트랙이 요구하는 폭은 배 이상 다르다
  column_width_vs_content 한 열은 접히는데 다른 열은 절반이 비어 있다(폭 1200 이상)
  header_cell_alignment_mismatch  `th` 정렬이 그 열 `td` 들의 정렬과 다르다
  numeric_alignment       숫자 열이 우정렬이 아니거나 `tabular-nums` 가 없다
  isolated_control_row    윗줄에 들어갈 자리가 있는데도 컨트롤 하나가 아랫줄로 밀렸다
  control_baseline_mismatch  한 줄 안에서 컨트롤 높이(같은 종류)나 중심선이 어긋난다
  oversized_empty_surface 큰 상자가 거의 비었거나 내용이 왼쪽에만 몰려 있다
  dead_blank_region       스크롤도 안 되는 화면에서 아래/오른쪽이 굶주린 채 비어 있다
  plain_dropdown_for_entity  기수가 무한히 자라는 대상을 검색 없는 드롭다운으로 고르게 한다
  detail_side_imbalance   2열 중 한쪽이 동났는데 그 공간을 회수하지 않았다(폭 1366 이상)
  surface_repetition      같은 톤의 면이 구조적으로 반복된다(목록은 정상이라 제외한다)
  brand_presence          브랜드 색이 제품 표면에 실제로 쓰이는가 (`capture.py` 가 채운다)
  mascot_visible_size     마스코트가 **보이는 크기**로 나오는가 (`capture.py` 가 채운다)
"""

from __future__ import annotations

import re
from typing import Any

# Only applied at very wide viewports — a 12px floor is a HiDPI/4K legibility
# rule, not something to enforce on a 390px phone.
TINY_TEXT_MIN_VIEWPORT = 2200
TINY_TEXT_MIN_PX = 12.0
# The "4K에서 양옆이 텅 빈다" check.
NARROW_MAIN_MIN_VIEWPORT = 3840
NARROW_MAIN_MIN_RATIO = 0.60

# 열 폭 비교는 넓은 화면에서만 뜻이 있다. 900 미만은 표가 카드로 접히고, 900~1200 은
# 한글 본문이 원래 접히는 폭이라 "열이 좁아서 접혔다"고 말할 근거가 없다.
COLUMN_CONTENT_MIN_VIEWPORT = 1200
# 2열 상세가 실제로 2열로 서는 폭. 이보다 좁으면 한 열로 접혀 좌우 불균형이라는 것이 없다.
DETAIL_IMBALANCE_MIN_VIEWPORT = 1366

# `plain_dropdown_for_entity` 의 대상 어휘. **기수가 무한히 자라는 타입만** 담은 닫힌 목록이다.
# 상태·역할·우선순위·난이도·테마처럼 값 집합이 닫힌 select 는 애초에 대상이 아니므로
# 옵션 개수를 셀 필요가 없다 — 개수를 세는 방식은 MUI 메뉴가 열기 전에는 DOM 에 없어서
# 어차피 못 센다. 목록을 늘릴 때는 "이 타입은 데이터가 쌓이면 계속 늘어나는가"만 묻는다.
ENTITY_TERMS = (
    "프로젝트", "담당자", "사용자", "부서", "조직", "직책", "티켓", "문서", "게시글",
    "러너", "워크플로", "프롬프트", "정책", "템플릿", "일정", "연동", "채팅방",
    "승인자", "요청자", "작성자", "대상자",
)

CLASSES = (
    "auth_ok", "theme_applied", "horizontal_overflow", "console_errors", "page_errors",
    "broken_images", "duplicate_ids", "tiny_text", "narrow_main", "vertical_text_collapse",
    "fab_overlap", "image_cropped", "content_clipped", "rail_wider_than_prose",
    # 레이아웃·콘텐츠 축. 전부 advisory 로 시작한다 — 등록은 하되 `run.py` 의 기본
    # `--fail-on` 은 비워 둔다(Wave 별 승격은 나중이다). 그래도 여기 넣어야 요약표와
    # `--fail-on` 이 이 검사들을 볼 수 있다.
    "equal_column_split", "column_width_vs_content", "header_cell_alignment_mismatch",
    "numeric_alignment", "isolated_control_row", "control_baseline_mismatch",
    "oversized_empty_surface", "dead_blank_region", "plain_dropdown_for_entity",
    "detail_side_imbalance", "surface_repetition",
    # 브랜드·마스코트는 별도 모듈이 `capture.py` 에서 채운다(대비 검사와 같은 구조다).
    # 이름만 등록해 둔다 — 등록하지 않으면 그쪽이 값을 채워도 요약표에 안 나온다.
    "brand_presence", "mascot_visible_size",
    # 모달 검사(`interact.py`). `--modals` 로 켜야 값이 채워지고, 안 켜면 전부 skip 이다.
    # 목록에 넣어 두는 이유는 요약표와 `--fail-on` 이 이 튜플만 알기 때문이다 —
    # 여기 없으면 검사가 돌아도 리포트에 안 나온다(실제로 그래서 안 보였다).
    "modal_footer_outside_actions", "modal_full_width_buttons", "modal_offscreen",
    "modal_no_close", "modal_cannot_close", "modal_radius", "modal_width_spread",
    # CTR-05: WCAG 텍스트 대비(scripts/ui_qa/contrast.py). 이 축이 없으면 CTR-01/02/04류
    # 결함이 전 페이지 통과로 영원히 남는다 — 21개 검사 중 이것만 색을 본다.
    "contrast",
)

# 사용자가 올린 이미지를 비율을 무시하고 잘라 보여주는 것을 잡는다.
# 실제 결함: 자유게시판 첨부 썸네일이 objectFit:"cover" + aspect-ratio:1/1 이라 정사각형이
# 아닌 이미지를 전부 잘라냈다("이미지가 잘리고 콘텐츠 영역만 보인다" — 사용자 지시 §5).
# 장식용 일러스트(마스코트·빈화면 그림)는 aria-hidden 이거나 alt="" 라 대상이 아니다.
IMAGE_CROP_MIN_LOSS = 0.15   # 원본 면적의 15% 넘게 잘리면 결함으로 본다

MAX_SAMPLES = 5

PROBE_JS = r"""
(config) => {
  const de = document.documentElement;
  const MAX = config.maxSamples || 5;
  const out = {
    url: location.href,
    theme: de.getAttribute('data-theme'),
    viewport: { w: window.innerWidth, h: window.innerHeight, dpr: window.devicePixelRatio },
  };

  // --- small helpers -------------------------------------------------------
  function cssPath(el) {
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && parts.length < 4) {
      let part = node.tagName.toLowerCase();
      if (node.id) { parts.unshift(part + '#' + node.id); break; }
      const cls = (node.getAttribute('class') || '').trim().split(/\s+/).filter(Boolean).slice(0, 2);
      if (cls.length) part += '.' + cls.join('.');
      parts.unshift(part);
      node = node.parentElement;
    }
    return parts.join(' > ');
  }
  function snippet(el) {
    return (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 60);
  }
  function visible(el, rect) {
    if (rect.width <= 0 || rect.height <= 0) return false;
    const cs = getComputedStyle(el);
    return cs.visibility !== 'hidden' && cs.display !== 'none' && cs.opacity !== '0';
  }
  // Real "1ch" per distinct font shorthand, measured once and cached — the
  // 2ch threshold is meaningless if we guess it from font-size alone.
  const chCache = new Map();
  const meter = document.createElement('span');
  meter.setAttribute('aria-hidden', 'true');
  meter.style.cssText = 'position:absolute;left:-9999px;top:-9999px;white-space:pre;visibility:hidden';
  document.body && document.body.appendChild(meter);
  function chWidth(fontShorthand) {
    if (chCache.has(fontShorthand)) return chCache.get(fontShorthand);
    let w = 8;
    try {
      meter.style.font = fontShorthand;
      meter.textContent = '00000000';
      w = meter.getBoundingClientRect().width / 8;
    } catch (e) { /* keep fallback */ }
    if (!isFinite(w) || w <= 0) w = 8;
    chCache.set(fontShorthand, w);
    return w;
  }

  /* --- 공용 측정 헬퍼 -----------------------------------------------------
   *
   * 셋 다 "상자가 얼마나 크냐" 가 아니라 "실제로 렌더된 것이 얼마냐" 를 잰다. 상자 크기로
   * 증상을 짐작하는 검사가 이 저장소에서 이미 여러 번 거짓 통과를 냈다
   * (vertical_text_collapse 주석 참고 — 폭 임계값만 보다가 표 한 열이 2~3자씩 으스러진
   * 페이지를 30/30 통과로 보고했다). */

  // 렌더된 줄들의 기하. `getClientRects()` 는 '줄' 이 아니라 '텍스트 조각' 마다 사각형을
  // 주므로(한 줄에 인라인 자식이 셋이면 사각형도 셋) top 으로 묶어야 사람이 보는 줄 수가
  // 된다. bucket 은 같은 줄로 볼 top 오차다 — 글꼴 크기가 섞인 줄은 top 이 몇 px 어긋난다.
  // rowsOf/inkSpanOf 가 이 하나를 나눠 쓴다. getClientRects 는 싸지 않아서 같은 요소를
  // 두 번 재지 않는다.
  function lineMetrics(el, bucket) {
    const b = bucket == null ? 8 : bucket;
    const rects = [];
    try {
      const range = document.createRange();
      range.selectNodeContents(el);
      for (const r of range.getClientRects()) {
        if (r.width > 0.5 && r.height > 0.5) rects.push(r);
      }
    } catch (e) { return { lines: 0, span: 0 }; }
    if (!rects.length) return { lines: 0, span: 0 };
    if (b <= 1) {
      // bucket 1 은 예전 vertical_text_collapse 구현과 정확히 같은 계산이다(회귀 방지).
      const tops = new Set();
      let lo = Infinity, hi = -Infinity;
      for (const r of rects) {
        tops.add(Math.round(r.top));
        if (r.left < lo) lo = r.left;
        if (r.right > hi) hi = r.right;
      }
      return { lines: tops.size, span: hi - lo };
    }
    rects.sort((x, y) => x.top - y.top);
    let lines = 1, span = 0, anchor = rects[0].top, lo = rects[0].left, hi = rects[0].right;
    for (const r of rects) {
      if (r.top - anchor > b) {
        if (hi - lo > span) span = hi - lo;
        lines++; anchor = r.top; lo = r.left; hi = r.right;
      } else {
        if (r.left < lo) lo = r.left;
        if (r.right > hi) hi = r.right;
      }
    }
    return { lines: lines, span: Math.max(span, hi - lo) };
  }
  function rowsOf(el, bucket) { return lineMetrics(el, bucket).lines; }
  // 렌더된 줄 중 **가장 넓은 줄** 의 잉크 폭. 상자 폭이 아니라 글자가 실제로 차지한 폭이다.
  function inkSpanOf(el) { return lineMetrics(el, 8).span; }

  /* 이 요소가 **요구하는** 폭.
   *
   * 상자 폭은 레이아웃이 '준' 폭이라 강제된 값이 그대로 나온다. 요구 폭은 콘텐츠 쪽 사실이라
   * "폭은 똑같은데 요구는 배로 다르다" 를 말할 수 있다 — equal_column_split 의 근거가 그것이다.
   * 한 줄이면 실측 잉크 폭이 곧 요구다. 여러 줄이면 한 줄에 담았을 때의 폭,
   * 즉 (글자수 / 줄수) x 실측 1ch 로 본다. */
  function demandOf(el) {
    const text = (el.textContent || '').replace(/\s+/g, ' ').trim();
    if (!text) return 0;
    const m = lineMetrics(el, 8);
    if (m.lines <= 1) return m.span;
    const cs = getComputedStyle(el);
    const ch = chWidth(cs.font || (cs.fontSize + ' ' + cs.fontFamily));
    return (text.length / m.lines) * ch;
  }

  // 잉크 격자의 칸 크기. 화면 폭에 비례시켜 4K 에서도 칸 수가 폭발하지 않게 한다.
  const INK_CELL = Math.max(24, Math.floor(window.innerWidth / 60));
  const BORDER_SIDES = ['Top', 'Right', 'Bottom', 'Left'];
  /* 페이지 한 장에 허용할 총 노드 방문 수. 넘으면 측정을 **포기하고** ratio:null 을 돌려준다 —
   * 중간에 끊긴 격자는 실제보다 비어 보이므로, 그 값을 쓰면 없는 결함을 만들어 낸다. */
  let inkBudget = 14000;

  /* padding box 를 cell px 격자로 나누고 **보이는 잎 노드가 닿는 칸** 을 센다.
   *
   * 겹치는 사각형의 합집합 면적을 정확히 구하려면 스윕라인이 필요하고, 화면 하나에 상자가
   * 수천 개면 그 비용이 프로브 전체보다 크다. "이 영역이 비었는가" 를 묻는 데는 +-cell
   * 정밀도로 충분하다.
   *
   * 잎만 세는 것이 핵심이다. 조상 상자를 잉크로 세면 무엇이든 100% 채워진 것으로 읽혀
   * 이 격자를 쓰는 이유 자체가 사라진다. 그래서 텍스트·그림·캔버스·SVG 와 **테두리 띠** 만
   * 센다(배경색은 잉크가 아니다 — 흰 카드가 비어 있다는 것이 바로 우리가 찾는 상태다). */
  function inkGrid(el, cell) {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    const bl = parseFloat(cs.borderLeftWidth) || 0, bt = parseFloat(cs.borderTopWidth) || 0;
    const brw = parseFloat(cs.borderRightWidth) || 0, bbw = parseFloat(cs.borderBottomWidth) || 0;
    const x0 = r.left + bl, y0 = r.top + bt;
    const w = r.width - bl - brw, h = r.height - bt - bbw;
    if (!(w > 0 && h > 0)) {
      return { cells: 0, inked: 0, ratio: null, bbox: null, box: null, cell: cell,
               note: '상자 크기가 0이다' };
    }
    const cols = Math.max(1, Math.ceil(w / cell)), rows = Math.max(1, Math.ceil(h / cell));
    if (cols * rows > 60000) {
      return { cells: cols * rows, inked: 0, ratio: null, bbox: null, box: null, cell: cell,
               note: '격자가 너무 크다' };
    }
    const grid = new Uint8Array(cols * rows);
    let inked = 0, ix0 = Infinity, iy0 = Infinity, ix1 = -Infinity, iy1 = -Infinity;
    function mark(left, top, right, bottom) {
      const L = Math.max(left, x0), T = Math.max(top, y0);
      const R = Math.min(right, x0 + w), B = Math.min(bottom, y0 + h);
      if (!(R > L && B > T)) return;
      if (L < ix0) ix0 = L;
      if (T < iy0) iy0 = T;
      if (R > ix1) ix1 = R;
      if (B > iy1) iy1 = B;
      const c0 = Math.max(0, Math.floor((L - x0) / cell));
      const c1 = Math.min(cols - 1, Math.floor((R - x0 - 0.001) / cell));
      const r0 = Math.max(0, Math.floor((T - y0) / cell));
      const r1 = Math.min(rows - 1, Math.floor((B - y0 - 0.001) / cell));
      for (let yy = r0; yy <= r1; yy++) {
        const base = yy * cols;
        for (let xx = c0; xx <= c1; xx++) {
          if (!grid[base + xx]) { grid[base + xx] = 1; inked++; }
        }
      }
    }
    const range = document.createRange();
    const stack = [el];
    let truncated = false;
    while (stack.length && !truncated) {
      const node = stack.pop();
      for (const child of node.childNodes) {
        if (inkBudget <= 0) { truncated = true; break; }
        if (child.nodeType === 3) {
          if (!child.nodeValue || !child.nodeValue.trim()) continue;
          inkBudget--;
          try {
            range.selectNodeContents(child);
            for (const tr of range.getClientRects()) {
              if (tr.width > 0.5 && tr.height > 0.5) mark(tr.left, tr.top, tr.right, tr.bottom);
            }
          } catch (e) { /* 못 재는 조각은 잉크로 세지 않는다 */ }
          continue;
        }
        if (child.nodeType !== 1) continue;
        const tag = (child.tagName || '').toUpperCase();
        if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT' || tag === 'TEMPLATE') continue;
        inkBudget--;
        const s = getComputedStyle(child);
        if (s.display === 'none' || s.visibility === 'hidden') continue;
        if (parseFloat(s.opacity || '1') < 0.05) continue;
        const cr = child.getBoundingClientRect();
        if (cr.width <= 0 || cr.height <= 0) continue;
        if (cr.right < x0 || cr.bottom < y0 || cr.left > x0 + w || cr.top > y0 + h) continue;
        if (tag === 'IMG' || tag === 'SVG' || tag === 'CANVAS' || tag === 'VIDEO' || tag === 'PICTURE') {
          mark(cr.left, cr.top, cr.right, cr.bottom);   // 그림은 상자 전체가 잉크다
          continue;                                     // 내부(path 등)는 볼 필요가 없다
        }
        for (const side of BORDER_SIDES) {
          const style = s['border' + side + 'Style'];
          if (style === 'none' || style === 'hidden') continue;
          const bw = parseFloat(s['border' + side + 'Width']) || 0;
          if (bw <= 0) continue;
          if (side === 'Top') mark(cr.left, cr.top, cr.right, cr.top + bw);
          else if (side === 'Bottom') mark(cr.left, cr.bottom - bw, cr.right, cr.bottom);
          else if (side === 'Left') mark(cr.left, cr.top, cr.left + bw, cr.bottom);
          else mark(cr.right - bw, cr.top, cr.right, cr.bottom);
        }
        stack.push(child);
      }
    }
    return {
      cells: cols * rows, inked: inked,
      ratio: truncated ? null : inked / (cols * rows),
      bbox: (inked && !truncated) ? { x: ix0, y: iy0, w: ix1 - ix0, h: iy1 - iy0 } : null,
      box: { x: x0, y: y0, w: w, h: h },
      cell: cell, truncated: truncated,
      note: truncated ? '노드 예산 소진 — 부분 측정이라 판정하지 않는다' : '',
    };
  }

  // --- horizontal overflow -------------------------------------------------
  out.overflow = {
    scrollWidth: de.scrollWidth,
    clientWidth: de.clientWidth,
    bodyScrollWidth: document.body ? document.body.scrollWidth : 0,
    offenders: [],
  };
  if (de.scrollWidth > de.clientWidth + 1) {
    const limit = de.clientWidth + 1;
    const all = document.body ? document.body.querySelectorAll('*') : [];
    for (const el of all) {
      const r = el.getBoundingClientRect();
      if (!visible(el, r)) continue;
      const right = r.right + window.scrollX;
      if (right > limit) {
        out.overflow.offenders.push({
          selector: cssPath(el), right: Math.round(right),
          width: Math.round(r.width), text: snippet(el),
        });
        if (out.overflow.offenders.length >= MAX) break;
      }
    }
  }

  // --- main content width (4K empty-sides check) ---------------------------
  // #main-content fills the space next to the sidebar, so measuring only that
  // never sees the cap that actually strands the pixels. The column users read
  // is capped further in: the legacy shell caps .c-content at
  // max-width:min(2040px,100%) and the MUI shell caps a class-less <Box>.
  // "usedWidth" — the union of every visible, non-fixed box inside the main
  // region — measures the horizontal extent the layout actually occupies and
  // does not depend on any class name, so it survives the redesign.
  const mainEl = document.querySelector('#main-content') || document.querySelector('main');
  const contentEl = mainEl
    ? (mainEl.querySelector('.c-content') || mainEl.querySelector('.c-chat-embed'))
    : document.querySelector('.c-content');
  function widthOf(el) { return el ? Math.round(el.getBoundingClientRect().width) : null; }
  let minLeft = Infinity, maxRight = -Infinity, counted = 0;
  if (mainEl) {
    for (const el of mainEl.querySelectorAll('*')) {
      const r = el.getBoundingClientRect();
      if (r.width <= 0 || r.height <= 0) continue;
      const cs = getComputedStyle(el);
      if (cs.visibility === 'hidden' || cs.display === 'none') continue;
      if (cs.position === 'fixed') continue;  // modals/drawers are not the column
      minLeft = Math.min(minLeft, r.left);
      maxRight = Math.max(maxRight, r.right);
      counted++;
    }
  }
  out.main = {
    found: !!mainEl,
    mainSelector: mainEl ? cssPath(mainEl) : null,
    mainWidth: widthOf(mainEl),
    contentSelector: contentEl ? cssPath(contentEl) : null,
    contentWidth: widthOf(contentEl),
    usedWidth: counted ? Math.round(maxRight - minLeft) : null,
    usedElements: counted,
    viewportWidth: window.innerWidth,
  };

  // --- duplicate ids -------------------------------------------------------
  const idCounts = new Map();
  for (const el of document.querySelectorAll('[id]')) {
    const id = el.id;
    if (!id) continue;
    idCounts.set(id, (idCounts.get(id) || 0) + 1);
  }
  out.duplicateIds = [...idCounts.entries()]
    .filter(([, n]) => n > 1)
    .map(([id, n]) => ({ id, count: n }))
    .slice(0, MAX * 2);

  // --- broken images -------------------------------------------------------
  out.brokenImages = [];
  for (const img of document.images) {
    const src = img.currentSrc || img.getAttribute('src') || '';
    if (!src) continue;
    if (img.complete && img.naturalWidth === 0) {
      out.brokenImages.push({ src: src.slice(0, 160), selector: cssPath(img) });
      if (out.brokenImages.length >= MAX) break;
    }
  }

  // --- 내용이 잘려 보이는가(overflow:hidden 인데 안이 넘침) -------------------
  //
  // 사용자 지시 §7: "화면 일부가 잘리는 문제". 스크롤이 되면 잘린 것이 아니라 접힌 것이므로
  // **스크롤할 수 없는데 넘치는** 경우만 센다(overflow hidden/clip). 그게 사용자가 볼 방법이
  // 없는 상태다.
  //
  // 넘침을 1px 이 아니라 넉넉히 잡는 이유: 그림자·포커스 링·자간 반올림으로 1~2px 넘치는 것은
  // 흔하고 아무도 못 알아챈다. 한 줄(약 24px) 넘게 잘릴 때만 결함으로 본다.
  /* 상세 화면의 두 열 격자에서 곁열이 본문보다 넓은가 (Q1/W1/K-T6).
   *
   * 본문은 산문이라 78ch 에서 멈추는 것이 옳다. 잘못됐던 것은 **남는 폭을 전부 곁열에 준
   * 것**이다: 1920px 에서 본문 743 / 레일 825, 3840px 에서 929 / 2001(레일이 2.15배).
   * 사용자가 "티켓 상세 본문이 속성보다 좁다" 고 지적했다.
   *
   * 넓은 화면에서만 의미가 있다 — 좁으면 한 열로 접히고, 그때는 비율이라는 것이 없다. */
  out.railRatio = [];
  {
    for (const el of document.querySelectorAll('#main-content div, #main-content section')) {
      const cs = getComputedStyle(el);
      if (cs.display !== 'grid') continue;
      const kids = [...el.children].filter((k) => k.getBoundingClientRect().width > 0);
      if (kids.length !== 2) continue;
      const a = Math.round(kids[0].getBoundingClientRect().width);
      const b = Math.round(kids[1].getBoundingClientRect().width);
      // 본문 열이라 부를 만한 크기여야 한다. 툴바·라벨 격자를 잡으면 무의미한 값이 나온다.
      if (a < 300 || b < 200) continue;
      /* **산문 열이 있는 격자만** 본다.
       *
       * 산문 상한(PROSE_MAX_WIDTH = 78ch)은 자식이 아니라 **격자 트랙**에 걸려 있다
       * (`minmax(0, 78ch) …`). 그래서 자식의 computed maxWidth 를 보면 늘 `none` 이고,
       * 그걸 조건으로 걸었더니 검사가 아무것도 잡지 못하게 됐다 — 결함을 되돌려도
       * 통과했다. 트랙 폭을 보고 판단한다.
       *
       * 첫 트랙이 78ch 근처(≈ 본문 한 줄 폭)에서 멈춰 있으면 산문 열이다. 채팅방처럼
       * '목록 + 대화' 인 2열은 첫 열이 320px 로 훨씬 좁아 여기 걸리지 않는다. */
      const rootFont = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
      const proseLo = rootFont * 30;   // ≈ 480px — 이보다 좁으면 목록·사이드 열이다
      const proseHi = rootFont * 62;   // ≈ 992px — 이보다 넓으면 상한이 안 걸린 것이다
      if (a < proseLo || a > proseHi) continue;
      out.railRatio.push({ prose: a, rail: b, ratio: Math.round((b / a) * 100) / 100 });
    }
  }

  out.clipped = [];
  {
    const MIN_CLIP = 24;
    // button/header/footer/nav 도 본다. 이 앱은 카드형 버튼(Paper component="button")을
    // 쓰고, 셸의 고정 높이 상자들이 header/footer/nav 에 산다 — div 만 훑으면 그것들이
    // 검사 밖에 남는다.
    const nodes = document.querySelectorAll(
      'div, section, article, main, aside, li, td, p, button, header, footer, nav');
    for (const el of nodes) {
      if (out.clipped.length >= MAX) break;
      const cs = getComputedStyle(el);
      const hideY = cs.overflowY === 'hidden' || cs.overflowY === 'clip';
      const hideX = cs.overflowX === 'hidden' || cs.overflowX === 'clip';
      if (!hideY && !hideX) continue;
      // 닫힌 모바일 드로어(예: 대화 목록 사이드바)는 position:absolute + translateX(-100%) +
      // inert 로 화면 밖에 둔다. transform 은 시각적으로만 옮길 뿐이라, 조상의 scrollWidth
      // 계산에는 여전히 잡혀 이 조상이 "안 보이는데 잘렸다"고 오검출된다 — 실제로는
      // inert(포커스도 스크린리더도 못 닿는다) 라 사용자가 볼 방법 자체가 없다. 오탐이라
      // Chrome E2E 실측(2026-08-15)으로 확인했다: 조상 자체는 onscreen=true·화면은 멀쩡한데
      // scrollWidth 초과분이 정확히 이 inert 자식의 폭이었다.
      if (el.querySelector('[inert]')) continue;
      const overY = hideY ? el.scrollHeight - el.clientHeight : 0;
      const overX = hideX ? el.scrollWidth - el.clientWidth : 0;
      if (overY < MIN_CLIP && overX < MIN_CLIP) continue;
      const r = el.getBoundingClientRect();
      if (r.width < 24 || r.height < 24) continue;
      // 말줄임(ellipsis)은 **의도된** 자르기다 — 잘렸다는 사실이 …로 화면에 보이고 title 로
      // 원문을 준다. 결함이 아니라 설계다.
      if (cs.textOverflow === 'ellipsis') continue;
      const text = (el.innerText || '').trim();
      if (!text) continue;   // 그림·장식만 든 상자는 이 검사의 대상이 아니다
      out.clipped.push({
        selector: cssPath(el), overY: Math.round(overY), overX: Math.round(overX),
        box: Math.round(r.width) + 'x' + Math.round(r.height), text: text.slice(0, 50),
      });
    }
  }

  // --- 사용자 이미지가 잘려 보이는가 ---------------------------------------
  //
  // object-fit:cover 는 상자를 채우려고 **원본을 잘라낸다**. 아바타처럼 얼굴만 보이면 되는
  // 자리에서는 맞지만, 사용자가 올린 첨부·본문 이미지에 쓰면 내용이 잘려 나간다.
  // 실제로 자유게시판 첨부가 cover + 1:1 이라 정사각형이 아닌 그림을 전부 잘랐다.
  //
  // 장식(aria-hidden 이거나 alt="")은 제외한다 — 마스코트·빈화면 일러스트는 잘려도
  // 정보가 사라지지 않고, 오히려 꽉 채우는 편이 맞는 경우가 많다.
  out.croppedImages = [];
  for (const img of document.images) {
    if (out.croppedImages.length >= MAX) break;
    if (!img.naturalWidth || !img.naturalHeight) continue;
    if (img.getAttribute('aria-hidden') === 'true') continue;
    if (!(img.getAttribute('alt') || '').trim()) continue;   // 장식
    const cs = getComputedStyle(img);
    if (cs.objectFit !== 'cover') continue;
    const r = img.getBoundingClientRect();
    if (r.width < 8 || r.height < 8) continue;
    // cover 는 상자를 덮도록 확대한 뒤 넘치는 쪽을 자른다. 남는 비율을 면적으로 계산한다.
    const scale = Math.max(r.width / img.naturalWidth, r.height / img.naturalHeight);
    const shownW = Math.min(img.naturalWidth * scale, r.width);
    const shownH = Math.min(img.naturalHeight * scale, r.height);
    const lost = 1 - (shownW * shownH) / (img.naturalWidth * scale * img.naturalHeight * scale);
    if (lost < config.imageCropMinLoss) continue;
    out.croppedImages.push({
      selector: cssPath(img), alt: (img.getAttribute('alt') || '').slice(0, 40),
      natural: img.naturalWidth + 'x' + img.naturalHeight,
      box: Math.round(r.width) + 'x' + Math.round(r.height),
      lostPct: Math.round(lost * 100),
    });
  }

  // --- text walk: tiny text + vertical collapse ----------------------------
  out.tinyText = [];
  out.verticalCollapse = [];
  const wantTiny = window.innerWidth >= config.tinyTextMinViewport;
  const all = document.body ? document.body.querySelectorAll('*') : [];
  for (const el of all) {
    const tag = el.tagName;
    if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT' || tag === 'SVG') continue;
    // Only leaf-ish text holders: at least one direct non-blank text node.
    let ownText = '';
    for (const node of el.childNodes) {
      if (node.nodeType === 3) ownText += node.nodeValue;
    }
    ownText = ownText.replace(/\s+/g, ' ').trim();
    if (!ownText) continue;
    const rect = el.getBoundingClientRect();
    if (!visible(el, rect)) continue;
    const cs = getComputedStyle(el);
    const fontSize = parseFloat(cs.fontSize) || 0;

    if (wantTiny && fontSize > 0 && fontSize < config.tinyTextMinPx) {
      if (out.tinyText.length < MAX) {
        out.tinyText.push({
          selector: cssPath(el), fontSize: Math.round(fontSize * 100) / 100,
          text: ownText.slice(0, 60),
        });
      }
      out.tinyTextCount = (out.tinyTextCount || 0) + 1;
    }

    // Vertical collapse: 글자가 몇 자씩 끊겨 세로로 흐르는 상태.
    //
    // 처음에는 '폭이 2자 미만인 상자'만 봤는데, 실제 사례를 놓쳤다 — 표의 한 열이 몇 px로
    // 굶으면서 셀마다 2~3자씩 줄바꿈되고 페이지가 3,896px까지 늘어났는데도 30/30 통과로
    // 보고했다. 폭 임계값은 증상을 짐작하는 방식이라 이런 걸 놓친다.
    //
    // 그래서 증상을 직접 잰다: 텍스트에 Range를 씌워 줄 상자 개수를 세고 '줄당 글자 수'를
    // 구한다. 그게 사람이 보는 것이고, 폰트나 여백이나 폭이 어디서 사라졌는지 가정할 필요가 없다.
    if (ownText.length >= 2) {
      const ch = chWidth(cs.font || (cs.fontSize + ' ' + cs.fontFamily));
      const lineHeight = parseFloat(cs.lineHeight) || fontSize * 1.2;
      let charsPerLine = null;
      let lines = 0;
      // 요소 전체 텍스트로 센다 — Range는 자식까지 덮으므로 직접 텍스트만 세면 분모가 틀린다.
      const fullText = (el.textContent || '').replace(/\s+/g, ' ').trim();
      if (fullText.length >= 6) {
        // getClientRects()는 '줄'이 아니라 '텍스트 조각'마다 사각형을 준다. 한 줄에 인라인
        // 자식이 셋이면 사각형도 셋이라, 그대로 세면 멀쩡한 줄을 3줄로 오해한다(실제로
        // 폭 1000px짜리 항목이 3줄로 잡혔다). rowsOf 가 상단 좌표로 묶어 준다 —
        // bucket 1 은 이 검사가 원래 쓰던 계산과 정확히 같다. 측정 불가면 0 이 돌아오고,
        // 그때는 아래 폭 기준으로만 판단한다.
        lines = rowsOf(el, 1);
        if (lines > 1) charsPerLine = fullText.length / lines;
      }
      const narrowBox = rect.width > 0 && rect.width < ch * 2 && rect.height >= lineHeight * 2;
      // '세로로 흐른다'는 것은 **좁은 상자**에서만 일어난다. 폭이 넉넉하면 줄당 글자 수가
      // 적게 나올 수 없다 — 그런 값이 나왔다면 레이아웃이 아니라 측정이 튄 것이다.
      // 실제로 폭 1918px(한 줄에 ~197자 들어감) 요소가 '3줄 2.7자/줄'로 잡혔다. 자식이
      // 세로로 쌓인 컨테이너였고, 그건 글자가 으스러진 것이 아니라 그냥 여러 줄이다.
      // 12자도 못 담는 상자만 후보로 둔다(원래 잡으려던 결함은 24px·8px/ch 였다).
      const couldHoldAWord = ch > 0 && rect.width >= ch * 12;
      const shredded = !couldHoldAWord && charsPerLine != null && lines >= 3 && charsPerLine < 3;
      if (narrowBox || shredded) {
        if (out.verticalCollapse.length < MAX) {
          out.verticalCollapse.push({
            selector: cssPath(el), width: Math.round(rect.width * 10) / 10,
            ch: Math.round(ch * 10) / 10, height: Math.round(rect.height),
            lines: lines,
            charsPerLine: charsPerLine == null ? null : Math.round(charsPerLine * 10) / 10,
            text: ownText.slice(0, 40),
          });
        }
        out.verticalCollapseCount = (out.verticalCollapseCount || 0) + 1;
      }
    }
  }
  out.tinyTextCount = out.tinyTextCount || 0;
  out.verticalCollapseCount = out.verticalCollapseCount || 0;
  out.tinyTextChecked = wantTiny;

  // --- 떠 있는 요소가 조작 컨트롤을 덮는가 ---------------------------------
  // 마스코트 FAB 같은 position:fixed 요소는 문서 흐름 밖에 있어서, 화면마다 하단 여백을
  // 얼마나 뒀는지와 무관하게 그 위에 얹힌다. 셸에 여백을 줘도 화면이 100vh 계산으로
  // 자체 높이를 잡으면 그 여백을 벗어난다 — 실제로 놀이방 채팅의 '보내기' 버튼이
  // FAB 밑에 깔렸다. 눈으로 보기 전에는 아무 검사도 이걸 잡지 못했다.
  //
  // 겹침 자체보다 **누를 수 없게 되는 것**이 문제이므로, 겹친 지점에서
  // elementFromPoint 가 그 컨트롤을 돌려주는지까지 본다. 살짝 스치기만 하고 여전히
  // 누를 수 있으면 통과다.
  //
  // 스크롤 맨 위에서만 재면 부족하다. 화면 하단에 붙는 컨트롤은 **끝까지 내렸을 때**
  // 비로소 FAB 과 만난다. 그래서 현재 위치와 맨 아래 두 지점에서 재고 합친다.
  // 프로브는 스크린샷보다 먼저 돌기 때문에(capture.py), 잰 뒤 스크롤을 정확히 되돌린다.
  out.fabOverlap = [];
  // 컨트롤별로 '한 번이라도 눌린 적이 있는가'. 스크롤 지점마다 새로 재고, 전부 훑은 뒤에
  // 판정을 정한다 — 어느 한 지점에서 덮였다는 사실만으로 '누를 방법이 없다'고 하면 안 된다.
  const clickableSomewhere = new Set();
  const floaters = Array.from(document.querySelectorAll('body *')).filter((el) => {
    const cs = getComputedStyle(el);
    if (cs.position !== 'fixed' || cs.display === 'none' || cs.visibility === 'hidden') return false;
    if (parseFloat(cs.opacity || '1') < 0.1) return false;
    const r = el.getBoundingClientRect();
    // 전면 오버레이(모달 배경 등)는 대상이 아니다 — 덮는 게 목적인 요소다.
    return r.width > 8 && r.height > 8 && r.width < innerWidth * 0.5 && r.height < innerHeight * 0.5;
  });
  const seenCovered = new Set();
  function scanCovered(where) {
    const controls = document.querySelectorAll('button, a[href], input, select, textarea, [role="button"]');
    for (const el of controls) {
      if (out.fabOverlap.length >= MAX) return;
      const r = el.getBoundingClientRect();
      if (r.width < 4 || r.height < 4) continue;
      if (r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth) continue;
      for (const f of floaters) {
        if (f === el || f.contains(el) || el.contains(f)) continue;
        const fr = f.getBoundingClientRect();
        const ox = Math.min(r.right, fr.right) - Math.max(r.left, fr.left);
        const oy = Math.min(r.bottom, fr.bottom) - Math.max(r.top, fr.top);
        if (ox <= 0 || oy <= 0) continue;
        // 겹친 영역의 한가운데를 눌러 본다. 그 컨트롤이 안 나오면 실제로 가려진 것이다.
        const px = Math.max(r.left, fr.left) + ox / 2;
        const py = Math.max(r.top, fr.top) + oy / 2;
        // 겹치는 자리가 뷰포트 **밖**이면 애초에 아무도 못 누르는 지점이다. 그런데
        // elementFromPoint 는 화면 밖 좌표에 늘 null 을 돌려주므로, 걸러내지 않으면
        // "가려졌다"로 잘못 잡힌다. 실제로 스킵링크('본문 바로가기' — 평소 top:8 에
        // translateY(-200%) 로 화면 위에 숨어 있다)가 긴 목록의 맨 위 줄과 y<0 에서
        // 겹쳐 오탐이 났다. 눈에 보이지도, 눌리지도 않는 겹침은 결함이 아니다.
        if (px < 0 || py < 0 || px > innerWidth || py > innerHeight) continue;
        const coveredPct = Math.round((ox * oy) / (r.width * r.height) * 100);
        const hit = document.elementFromPoint(px, py);
        const stillClickable = !!(hit && (hit === el || el.contains(hit)));
        /* **제출 버튼이 크게 덮인 경우는 눌리더라도 결함이다.**
         *
         * 원래 규칙("겹치기만 하면 통과, 못 누르면 실패")은 옳다 — 긴 표의 어떤 행은 늘
         * FAB 밑을 지나가므로 겹침을 전부 실패로 세면 게이트가 곧 무시된다.
         *
         * 그런데 실측해 보니 새 티켓의 '티켓 만들기'가 1440 이하에서 **45px(약 47%) 덮이는데도**
         * 가운데가 남아 있어 이 검사를 통과했다. 사용자 눈에는 버튼이 반쯤 잘려 보이고, 덮인
         * 쪽을 누르면 엉뚱한 것이 눌린다. 이 저장소가 같은 함정을 이미 세 번 밟았고
         * (놀이방 '보내기', AI 채팅 '전송', 새 티켓 '티켓 만들기') 셋 다 제출 버튼이었다.
         *
         * 그래서 **제출 컨트롤에 한해** 면적 기준을 더한다. 한 페이지에 많아야 한둘이라
         * 소음이 되지 않고, 정확히 세 번 터진 그 자리를 짚는다. */
        const isSubmit = (el.getAttribute('type') || '').toLowerCase() === 'submit';
        const heavySubmit = isSubmit && coveredPct >= 25;
        const key = cssPath(el) + '|' + snippet(el);
        // **어느 스크롤 위치에서든 한 번이라도 눌렸다면** 사용자는 그 컨트롤에 닿을 수 있다.
        // 이걸 기록해 두고 마지막에 판정을 되돌린다(아래 clickableSomewhere 참고).
        if (stillClickable) clickableSomewhere.add(key);
        if (stillClickable && !heavySubmit) continue;  // 여전히 눌리고 크게 가리지도 않는다
        if (seenCovered.has(key)) continue;
        seenCovered.add(key);
        // **스크롤로 비켜낼 수 있는가**로 피해의 크기가 갈린다.
        //   못 비킨다 — 화면에 고정된 컨트롤이 영구히 안 눌린다. 사용자는 방법이 없다.
        //               (놀이방 채팅의 '보내기'가 그랬다: sticky 레일 맨 아래에 붙어 있었다.)
        //   비킬 수 있다 — 긴 표의 어떤 행이 잠시 FAB 밑에 놓인 것뿐이다. 조금 굴리면
        //               눌린다. 떠 있는 버튼을 쓰는 이상 어느 행인가는 늘 밑에 놓이므로,
        //               이걸 실패로 치면 '표가 긴 화면 = 영구 실패'가 되어 게이트가 죽는다.
        // 그래서 전자만 실패로 세고 후자는 기록만 한다.
        // sticky 조상이 있다고 곧바로 '못 비킨다'로 보지 않는다. sticky 는 **붙기 전까지는
        // 같이 움직인다** — 놀이방 채팅 레일이 그렇고, 끝까지 내리면 '보내기'가 FAB 밖으로
        // 나온다. 실제 판정은 아래 스크롤 훑기 결과(clickableSomewhere)로 되돌린다.
        let pinned = true;
        for (let node = el; node && node !== document.body; node = node.parentElement) {
          const pos = getComputedStyle(node).position;
          if (pos === 'fixed') { pinned = true; break; }
          pinned = false;
        }
        const scrollable = de.scrollHeight > de.clientHeight + 1
          || Array.from(document.querySelectorAll('#main-content, main, .c-content'))
               .some((s) => s.scrollHeight > s.clientHeight + 1);
        out.fabOverlap.push({
          key: key,
          control: cssPath(el), text: snippet(el), floater: cssPath(f), where: where,
          coveredPct: coveredPct,
          at: [Math.round(px), Math.round(py)],
          // 못 누르거나(기존 규칙), 제출 버튼이 25% 넘게 덮였거나(새 규칙).
          unreachable: (!stillClickable && (pinned || !scrollable)) || heavySubmit,
          heavySubmit: heavySubmit,
        });
        break;
      }
    }
  }
  /* 제출 버튼이 떠 있는 요소의 **세로 통로**에 놓여 있는가 — 스크롤을 흉내내지 않고 판정한다.
   *
   * 스크롤해 가며 재는 방식은 근본적으로 표본추출이라, 70px 짜리 FAB 밑을 지나가는 버튼을
   * 지점 사이에서 놓친다(25% 간격이면 한 걸음이 수백 px 이다). 실제로 새 티켓의 '티켓 만들기'가
   * 그렇게 빠져나가 검사가 통과했다.
   *
   * 고정 요소는 뷰포트에 붙어 있고 컨트롤은 스크롤을 따라 움직인다. 그러니 **가로 범위가
   * 겹치고 페이지가 스크롤된다면**, 그 컨트롤은 어느 스크롤 위치에선가 반드시 그 요소 밑을
   * 지난다 — 지점을 찍어 볼 필요가 없다. 대상은 제출 컨트롤로 좁힌다(§scanCovered 주석 참고). */
  function scanSubmitBand() {
    // 실제로 스크롤하는 요소를 찾는다(이 앱은 문서가 아니라 #main-content 가 구르기도 한다).
    let sc = null, over = 0;
    for (const el of [de, document.body, ...document.querySelectorAll('#main-content, main, .c-content')]) {
      if (!el) continue;
      const o = el.scrollHeight - el.clientHeight;
      if (o > over) { over = o; sc = el; }
    }
    if (!sc || over <= 1) return;
    const isDoc = (sc === de || sc === document.body);
    const y = isDoc ? window.scrollY : sc.scrollTop;

    for (const el of document.querySelectorAll('button[type="submit"], input[type="submit"]')) {
      if (out.fabOverlap.length >= MAX) return;
      const r = el.getBoundingClientRect();
      if (r.width < 4 || r.height < 4) continue;
      for (const f of floaters) {
        if (f === el || f.contains(el) || el.contains(f)) continue;
        const fr = f.getBoundingClientRect();
        const ox = Math.min(r.right, fr.right) - Math.max(r.left, fr.left);
        if (ox <= 0) continue;
        const pct = Math.round((ox / r.width) * 100);
        if (pct < 25) continue;   // 살짝 스치는 정도는 세지 않는다

        /* **그 컨트롤이 정말 저 띠까지 내려올 수 있는가.**
         *
         * 가로가 겹친다고 다 걸리는 게 아니다. 페이지 맨 위에 있는 컨트롤(검색 폼의 '검색'
         * 버튼)은 스크롤하면 위로 사라질 뿐, 아래쪽 FAB 띠로는 절대 내려오지 않는다.
         * 첫 판에서 그걸 놓쳐 검색 화면 3개를 오탐으로 잡았다.
         *
         * 스크롤을 0..over 로 굴리면 이 컨트롤의 화면 y 는 [top-(over-y), top+y] 를 훑는다.
         * 그 구간이 띠와 만날 때만 실제로 덮인다. */
        const reachTop = r.top - (over - y);
        const reachBottom = r.bottom + y;
        if (reachBottom < fr.top || reachTop > fr.bottom) continue;

        const key = 'band|' + cssPath(el);
        if (seenCovered.has(key)) continue;
        seenCovered.add(key);
        out.fabOverlap.push({
          control: cssPath(el), text: snippet(el), floater: cssPath(f), where: '세로 통로',
          coveredPct: pct, at: [Math.round(fr.left + 1), Math.round(fr.top + 1)],
          unreachable: true, submitBand: true,
        });
        break;
      }
    }
  }
  scanSubmitBand();
  scanCovered('현재 위치');
  // 맨 아래로 내려 한 번 더.
  //
  // 문서가 스크롤한다고 가정하면 안 된다. 이 앱의 셸은 자신을 뷰포트에 고정하고
  // **#main-content 가 스크롤**한다(capture.py 의 _SCROLL_METRICS_JS 도 같은 이유로
  // 컨테이너를 따로 찾는다). window.scrollTo 만 부르면 아무 일도 일어나지 않아,
  // 검사가 통과했다고 착각하게 된다 — 실제로 그렇게 헛돌았다.
  let scroller = null, maxOver = 0;
  for (const el of [de, document.body, ...document.querySelectorAll('#main-content, main, .c-content')]) {
    if (!el) continue;
    const over = el.scrollHeight - el.clientHeight;
    if (over > maxOver) { maxOver = over; scroller = el; }
  }
  if (scroller && maxOver > 1 && out.fabOverlap.length < MAX) {
    const isDoc = (scroller === de || scroller === document.body);
    const y0 = isDoc ? window.scrollY : scroller.scrollTop;
    const setY = (y) => { if (isDoc) window.scrollTo(0, y); else scroller.scrollTop = y; };
    /* **중간 스크롤 위치까지 훑는다.**
     *
     * 예전에는 '현재 위치'와 '맨 아래' 두 곳만 쟀다. 그런데 셸이 본문 아래에 여백을 주기
     * 때문에 맨 아래에서는 FAB 밑이 비어 있고, 정작 덮이는 것은 **스크롤 중간**이다 —
     * 긴 폼의 제출 버튼이 화면 우하단을 지나가는 그 순간. 새 티켓 화면의 '티켓 만들기'가
     * 정확히 그랬는데 이 검사는 통과하고 있었다(거짓 통과).
     *
     * 25% 간격으로 네 지점을 더 본다. 촘촘히 훑으면 페이지당 시간이 늘고, 이보다 성기면
     * 화면 한 장 높이(=FAB 이 덮을 수 있는 구간)를 건너뛴다. */
    const stops = [0.25, 0.5, 0.75, 1.0];
    for (const f of stops) {
      if (out.fabOverlap.length >= MAX) break;
      setY(Math.round(maxOver * f));
      void de.getBoundingClientRect();  // 레이아웃 강제 반영
      scanCovered(f >= 1 ? '맨 아래' : ('스크롤 ' + Math.round(f * 100) + '%'));
    }
    setY(y0);  // 스크린샷이 뒤에 찍힌다 — 원래 위치로 되돌린다
    void de.getBoundingClientRect();
  }
  /* 훑기가 끝났다. **한 번이라도 눌린 적이 있는 컨트롤은 '누를 방법이 없다'가 아니다.**
   * 이걸 넣기 전에는 sticky 조상이 있다는 이유만으로 실패로 셌고, 놀이방 채팅의 '보내기'가
   * 그렇게 거짓 실패했다 — 끝까지 내리면 실제로는 눌린다(측정으로 확인).
   * 다만 두 가지는 되돌리지 않는다:
   *   - submitBand — 스크롤을 흉내내지 않고 기하로 판정한 것이라 표본추출의 영향을 안 받는다.
   *   - heavySubmit — 눌리더라도 제출 버튼이 25% 넘게 가려지면 그 자체가 결함이다. */
  for (const o of out.fabOverlap) {
    if (o.submitBand || o.heavySubmit) continue;
    if (clickableSomewhere.has(o.key)) o.unreachable = false;
  }
  out.fabScroller = scroller ? cssPath(scroller) : null;
  out.fabScrollOver = Math.round(maxOver);
  out.fabOverlapCount = out.fabOverlap.length;

  /* --- 레이아웃·콘텐츠 축 11종 -------------------------------------------
   *
   * 아래 검사들은 전부 "상자가 크다/작다" 가 아니라 "**요구와 공급이 어긋났다**" 를 잰다.
   * 그래야 정상 패턴(좁은 화면의 줄바꿈, 카드 목록, 짧은 설정 폼)과 결함을 가른다.
   * 표본은 MAX 개까지만 담는다 — 세부는 리포트용이고 판정은 있/없음이다. */
  const MAIN = mainEl || document.body;
  const CTRL_SEL = 'button, a[href], input, select, textarea, [role="button"],'
    + ' [role="combobox"], [role="switch"], .MuiInputBase-root, .MuiButtonBase-root';

  /* 페이지 단위 잉크 격자는 **가장 먼저** 잰다.
   *
   * 잉크 예산(inkBudget)은 프로브 전체가 나눠 쓰는 전역 값이다. 지금 순서대로 7번(표면)이
   * 큰 상자 12개를 훑고 나면 8번(dead_blank_region)이 예산이 마른 채 도착해 ratio:null 을
   * 받고 영원히 skip 으로 떨어진다 — 페이지 전체를 보는 유일한 검사가 그렇게 죽는다.
   * 이 격자는 어차피 한 번은 재야 하므로 순서만 바꾸면 총비용은 그대로다.
   *
   * 페이지가 스크롤되면 dead_blank_region 은 애초에 대상이 아니므로 그때는 재지 않는다 —
   * 그 예산은 표면 검사 쪽에 남긴다. */
  let pageOverflowY = 0;
  for (const el of [de, document.body, ...document.querySelectorAll('#main-content, main, .c-content')]) {
    if (!el) continue;
    pageOverflowY = Math.max(pageOverflowY, el.scrollHeight - el.clientHeight);
  }
  const MAIN_INK = pageOverflowY > 1 ? null : inkGrid(MAIN, INK_CELL);

  // 직접 자식들을 **화면에서 같은 줄** 로 묶는다. top 만 보고 묶으면 높이가 다른 컨트롤
  // (버튼 36px / 입력 40px)이 다른 줄로 갈라진다 — 세로 범위가 절반 넘게 겹치면 같은 줄이다.
  function flowRows(container) {
    const kids = [];
    for (const k of container.children) {
      const r = k.getBoundingClientRect();
      if (!visible(k, r)) continue;
      kids.push({ el: k, r: r });
    }
    kids.sort((a, b) => (a.r.top - b.r.top) || (a.r.left - b.r.left));
    const rows = [];
    for (const k of kids) {
      const row = rows.length ? rows[rows.length - 1] : null;
      if (row) {
        const top = Math.max(row.top, k.r.top), bottom = Math.min(row.bottom, k.r.bottom);
        const minH = Math.min(row.bottom - row.top, k.r.height);
        if (minH > 0 && bottom - top > minH * 0.5) {
          row.items.push(k);
          row.top = Math.min(row.top, k.r.top);
          row.bottom = Math.max(row.bottom, k.r.bottom);
          row.left = Math.min(row.left, k.r.left);
          row.right = Math.max(row.right, k.r.right);
          continue;
        }
      }
      rows.push({ items: [k], top: k.r.top, bottom: k.r.bottom, left: k.r.left, right: k.r.right });
    }
    return rows;
  }

  // computed textAlign 은 설정하지 않으면 'start'/'end' 로 나온다 — 방향에 맞춰 좌/우로 편다.
  // 'left' 와 'start' 를 다른 값으로 취급하면 정렬 불일치가 온 페이지에서 거짓으로 뜬다.
  function alignOf(el) {
    const cs = getComputedStyle(el);
    const a = cs.textAlign;
    const rtl = cs.direction === 'rtl';
    if (a === 'start') return rtl ? 'right' : 'left';
    if (a === 'end') return rtl ? 'left' : 'right';
    return a;
  }

  // --- 1) equal_column_split ------------------------------------------------
  /* 격자가 폭을 **똑같이** 나눠 놓았는데 두 트랙이 요구하는 폭은 전혀 다른 경우.
   *
   * 트랙이 content-sized 였다면 폭이 같다는 건 요구도 같다는 뜻이다. 그러니 "폭은 같은데
   * 요구 비가 2.5배 이상" 은 그 자체로 `1fr 1fr` 을 강제한 증거다. 여기에 "굶는 쪽은 접히고
   * 남는 쪽은 절반이 빈다" 를 더해, 폭을 옮기면 실제로 나아지는 경우만 남긴다.
   * 7일 달력(SchedulerCalendar)·게임판(LadderBoard)처럼 **같아야 하는** 격자는
   * data-equal-grid 로 뺀다. */
  out.equalColumnSplit = [];
  out.equalColumnSplitChecked = 0;
  for (const el of MAIN.querySelectorAll('div, section, ul, ol')) {
    if (out.equalColumnSplit.length >= MAX) break;
    const cs = getComputedStyle(el);
    if (cs.display !== 'grid' && cs.display !== 'inline-grid') continue;
    if (el.closest('[data-equal-grid]')) continue;
    const rows = flowRows(el);
    if (!rows.length) continue;
    const tracks = rows[0].items;
    if (tracks.length < 2) continue;
    let wMin = Infinity, wMax = -Infinity, tooNarrow = false;
    for (const t of tracks) {
      if (t.r.width < 160) { tooNarrow = true; break; }
      wMin = Math.min(wMin, t.r.width);
      wMax = Math.max(wMax, t.r.width);
    }
    if (tooNarrow) continue;
    // 폭이 애초에 다르면 이 결함이 아니다 — 재서 확인한 것이므로 pass 로 센다.
    if (!(wMin > 0) || wMax / wMin > 1.02) { out.equalColumnSplitChecked++; continue; }
    let hungry = null, roomy = null;
    for (const t of tracks) {
      const info = { el: t.el, w: t.r.width, demand: demandOf(t.el), lines: rowsOf(t.el) };
      if (!hungry || info.demand > hungry.demand) hungry = info;
      if (!roomy || info.demand < roomy.demand) roomy = info;
    }
    // 글자가 없는 트랙(차트·그림만 든 칸)은 요구 폭을 잴 방법이 없다. 못 잰 것을 pass 로
    // 세면 요약표의 통과 수가 실제로 확인한 격자 수와 어긋난다 — 세지 않고 넘어간다.
    if (!(roomy.demand > 0)) continue;
    out.equalColumnSplitChecked++;
    if (hungry.demand / roomy.demand < 2.5) continue;
    const freeRatio = roomy.w > 0 ? 1 - Math.min(1, roomy.demand / roomy.w) : 0;
    if (!(hungry.lines >= 2 && freeRatio >= 0.5)) continue;
    out.equalColumnSplit.push({
      selector: cssPath(el), tracks: tracks.length,
      widths: tracks.map((t) => Math.round(t.r.width)),
      demandRatio: Math.round((hungry.demand / roomy.demand) * 100) / 100,
      hungryLines: hungry.lines,
      freeRatio: Math.round(freeRatio * 100) / 100,
      hungryText: snippet(hungry.el), roomyText: snippet(roomy.el),
    });
  }

  // --- 표 한 장을 열 단위로 한 번만 잰다 -------------------------------------
  /* 아래 세 검사(열 폭 / 헤더 정렬 / 숫자 정렬)가 같은 측정을 나눠 쓴다. 표는 셀이 많아
   * 따로 세 번 훑으면 그만큼 비싸다. 행은 앞쪽 일부만 본다 — 열의 성질(무엇이 접히는가,
   * 어떻게 정렬되는가)은 앞 몇십 행이면 드러나고, 전부 훑으면 페이지당 시간이 무너진다. */
  const tableColumns = [];
  {
    const TABLE_MAX = 3, TABLE_ROWS = 25;
    const tables = [];
    for (const t of MAIN.querySelectorAll('table')) {
      const r = t.getBoundingClientRect();
      if (visible(t, r) && r.width > 200) tables.push(t);
      if (tables.length >= TABLE_MAX) break;
    }
    for (const table of tables) {
      const headRow = table.querySelector('thead tr') || table.querySelector('tr');
      if (!headRow) continue;
      const heads = [];
      for (const c of headRow.children) {
        if (c.tagName === 'TH' || c.tagName === 'TD') heads.push(c);
      }
      if (!heads.length) continue;
      const cols = heads.map((th, i) => ({
        table: table, index: i, th: th,
        header: snippet(th).slice(0, 24) || ('#' + (i + 1)),
        headerAlign: alignOf(th),
        width: th.getBoundingClientRect().width,
        cells: [], texts: [], aligns: [], wrapped: 0, filled: 0, ink: 0,
      }));
      let seenRows = 0;
      for (const tr of table.querySelectorAll('tbody tr')) {
        if (seenRows >= TABLE_ROWS) break;
        const rr = tr.getBoundingClientRect();
        if (rr.width <= 0 || rr.height <= 0) continue;
        seenRows++;
        const tds = [];
        for (const c of tr.children) {
          if (c.tagName === 'TD' || c.tagName === 'TH') tds.push(c);
        }
        for (let i = 0; i < cols.length && i < tds.length; i++) {
          const td = tds[i];
          const text = (td.textContent || '').replace(/\s+/g, ' ').trim();
          cols[i].cells.push(td);
          cols[i].texts.push(text);
          cols[i].aligns.push(alignOf(td));
          if (!text) continue;
          const m = lineMetrics(td, 8);
          if (m.lines >= 2) cols[i].wrapped++;
          cols[i].filled++;
          if (m.span > cols[i].ink) cols[i].ink = m.span;
        }
      }
      for (const c of cols) {
        // fill 은 **셀 잉크와 헤더 잉크의 max** 다. 헤더가 길어서 넓어진 열을 slack 이라
        // 부르면 "헤더를 줄여라" 가 아니라 "이 열을 줄여라" 라는 틀린 결론이 나온다.
        c.ink = Math.max(c.ink, inkSpanOf(c.th));
        c.wrapRate = c.filled ? c.wrapped / c.filled : 0;
        c.fill = c.width > 0 ? Math.min(1, c.ink / c.width) : 1;
        c.slackPx = Math.max(0, c.width - c.ink);
        const tally = new Map();
        for (const a of c.aligns) tally.set(a, (tally.get(a) || 0) + 1);
        let mode = null, best = -1;
        for (const entry of tally) {
          if (entry[1] > best) { best = entry[1]; mode = entry[0]; }
        }
        c.bodyAlign = mode;
        c.bodyAlignShare = c.aligns.length ? best / c.aligns.length : 0;
        tableColumns.push(c);
      }
    }
  }

  // --- 2) column_width_vs_content -------------------------------------------
  /* 한 열은 접히는데 다른 열은 절반이 비어 있다 — 폭이 잘못 배분된 상태다.
   * 좁은 화면에서는 발화하지 않는다(config.columnContentMinViewport 참고): 900 미만은 표가
   * 카드로 접히고, 900~1200 은 한글이 원래 접히는 폭이라 열 폭 탓을 할 근거가 없다. */
  out.columnWidthVsContent = [];
  out.columnWidthVsContentChecked = 0;
  if (window.innerWidth >= config.columnContentMinViewport) {
    const byTable = new Map();
    for (const c of tableColumns) {
      if (!byTable.has(c.table)) byTable.set(c.table, []);
      byTable.get(c.table).push(c);
    }
    for (const entry of byTable) {
      if (out.columnWidthVsContent.length >= MAX) break;
      const table = entry[0], cols = entry[1];
      if (cols.length < 2) continue;
      out.columnWidthVsContentChecked++;
      let a = null;
      for (const c of cols) {
        if (c.filled < 2 || c.wrapRate < 0.5) continue;
        if (!a || c.wrapRate > a.wrapRate) a = c;
      }
      if (!a) continue;
      let b = null;
      for (const c of cols) {
        if (c === a) continue;
        if (c.fill > 0.45 || c.slackPx < 96 || c.slackPx < 0.5 * a.width) continue;
        if (!b || c.slackPx > b.slackPx) b = c;
      }
      if (!b) continue;
      out.columnWidthVsContent.push({
        selector: cssPath(table),
        starvedColumn: a.header, starvedWidth: Math.round(a.width),
        wrapRate: Math.round(a.wrapRate * 100) / 100,
        slackColumn: b.header, slackWidth: Math.round(b.width),
        fill: Math.round(b.fill * 100) / 100, slackPx: Math.round(b.slackPx),
      });
    }
  }

  // --- 3) header_cell_alignment_mismatch ------------------------------------
  /* `th` 정렬과 그 열 `td` 들의 최빈 정렬이 다르면 언제나 결함이다 — 머리와 몸이 다른 축에
   * 붙어 눈이 열을 따라 내려가지 못한다. 억제 수단을 두지 않는다.
   *
   * 실제로 그런 경로가 있다: kit.css 는 둘 다 left 로 두는데 kit.jsx 의 DataTable 이
   * head/body 에 `align` 을 따로 넘겨서, 한쪽만 설정되면 그대로 어긋난다. */
  out.headerCellAlignment = [];
  out.headerCellAlignmentChecked = 0;
  for (const c of tableColumns) {
    if (out.headerCellAlignment.length >= MAX) break;
    if (c.aligns.length < 2 || !c.bodyAlign) continue;
    out.headerCellAlignmentChecked++;
    if (c.bodyAlign === c.headerAlign) continue;
    out.headerCellAlignment.push({
      selector: cssPath(c.th), column: c.header,
      header: c.headerAlign, body: c.bodyAlign,
      bodyShare: Math.round(c.bodyAlignShare * 100),
    });
  }

  // --- 4) numeric_alignment -------------------------------------------------
  /* 숫자 열은 우정렬 + tabular-nums 여야 자릿수가 세로로 맞고, 그래야 값을 **비교** 할 수 있다.
   * 억제 수단을 두지 않는다.
   *
   * 오탐의 근원은 '숫자처럼 생겼지만 숫자가 아닌 것' 이다. 티켓번호·포트·버전은 크기를
   * 비교하지 않으므로 우정렬이 오히려 틀렸다 — 날짜·시각·전화·버전은 정규식으로 배제하고,
   * 그 밖의 식별자형은 data-col-role="identifier" 로 면제한다. */
  // 단위가 붙어도 숫자 열이다("1,240건"). 단위 뒤에 다른 글자가 오면 숫자가 아니다.
  const NUM_RE = /^[+-]?[₩$€£]?\s*\d[\d,\s]*(\.\d+)?\s*(%|원|건|개|명|점|회|초|분|시간|일|ms|s|B|KB|MB|GB|TB)?$/;
  const DATE_RE = /^\d{4}\s*[-./년]/;
  const TIME_RE = /\d{1,2}:\d{2}/;
  const PHONE_RE = /^0\d{1,2}-\d{3,4}-\d{4}$/;
  const VER_RE = /^v?\d+\.\d+\.\d+/;
  out.numericAlignment = [];
  out.numericAlignmentChecked = 0;
  for (const c of tableColumns) {
    if (out.numericAlignment.length >= MAX) break;
    if (c.th.closest('[data-col-role="identifier"]')) continue;
    const texts = c.texts.filter((t) => t);
    if (texts.length < 3) continue;
    let excluded = 0, numeric = 0;
    for (const t of texts) {
      if (DATE_RE.test(t) || TIME_RE.test(t) || PHONE_RE.test(t) || VER_RE.test(t)) { excluded++; continue; }
      if (NUM_RE.test(t)) numeric++;
    }
    if (excluded / texts.length >= 0.2) continue;   // 날짜·시각·전화·버전 열이다
    if (numeric / texts.length < 0.8) continue;
    out.numericAlignmentChecked++;
    let sample = c.th;
    for (const td of c.cells) {
      if ((td.textContent || '').trim()) { sample = td; break; }
    }
    const scs = getComputedStyle(sample);
    const tabular = (scs.fontVariantNumeric || '').indexOf('tabular-nums') >= 0
      || (scs.fontFeatureSettings || '').indexOf('tnum') >= 0;
    const right = c.bodyAlign === 'right';
    if (right && tabular) continue;
    out.numericAlignment.push({
      selector: cssPath(sample), column: c.header,
      align: c.bodyAlign, tabular: tabular,
      numericShare: Math.round((numeric / texts.length) * 100),
      reason: right ? 'tabular-nums 가 없다' : (tabular ? '우정렬이 아니다' : '우정렬도 tabular-nums 도 없다'),
    });
  }

  // --- 5) isolated_control_row ----------------------------------------------
  /* 컨트롤 하나가 아랫줄로 밀려 줄 하나를 통째로 쓰는 상태.
   *
   * 좁은 화면의 정상적인 wrap 과 가르는 것이 전부다. 그래서 "윗줄에 **실제로 들어갈 자리가
   * 있었다**" 를 증명한다 — 윗줄 여유가 이 줄이 쓰는 폭 + gap 보다 크고, 그 여유가 120px 이상.
   * 좁은 화면은 여유가 없어 발화하지 않는다. 의도적으로 줄을 나눈 곳은
   * data-control-row="separate" 로 뺀다. */
  out.isolatedControlRow = [];
  out.isolatedControlRowChecked = 0;
  function isControlHolder(el) {
    if (el.matches(CTRL_SEL)) return true;
    if (!el.querySelector(CTRL_SEL)) return false;
    // 자기 글자를 가진 상자는 '컨트롤 한 개' 가 아니라 '컨트롤이 든 콘텐츠' 다.
    let own = '';
    for (const n of el.childNodes) if (n.nodeType === 3) own += n.nodeValue;
    return !own.trim();
  }
  for (const container of MAIN.querySelectorAll('div, section, form, header, nav')) {
    if (out.isolatedControlRow.length >= MAX) break;
    if (container.children.length < 2) continue;
    const ccs = getComputedStyle(container);
    if (ccs.display !== 'flex' && ccs.display !== 'inline-flex'
        && ccs.display !== 'grid' && ccs.display !== 'block') continue;
    if (container.closest('[data-control-row="separate"]')) continue;
    /* 한 줄에 **설 수 없었던** 것은 밀려난 것이 아니다.
     *
     * 세로로 쌓이는 것이 정상인 구조(flex-direction:column, flex-wrap:nowrap)를 여기서 뺀다.
     * 이 갈래가 없으면 '라벨 위 / 컨트롤 아래' 라는 폼의 기본형과 MUI FormControl
     * (inline-flex + column) 이 전부 결함으로 잡힌다 — 실측으로 확인했다. */
    const flexish = ccs.display === 'flex' || ccs.display === 'inline-flex';
    if (flexish) {
      if ((ccs.flexDirection || 'row').indexOf('column') === 0) continue;
      if (ccs.flexWrap === 'nowrap') continue;
    }
    const cr = container.getBoundingClientRect();
    const inner = cr.width - (parseFloat(ccs.paddingLeft) || 0) - (parseFloat(ccs.paddingRight) || 0);
    if (inner < 320) continue;
    const rows = flowRows(container);
    if (rows.length < 2) continue;
    const gap = parseFloat(ccs.columnGap) || parseFloat(ccs.gap) || 8;
    for (let i = 1; i < rows.length; i++) {
      if (out.isolatedControlRow.length >= MAX) break;
      const R = rows[i], P = rows[i - 1];
      // block 흐름에서는 자식이 block-level 이면 같은 줄에 설 방법이 애초에 없다. 여유 폭이
      // 아무리 많아도 '밀려난' 것이 아니라 '쌓인' 것이다 — 그것까지 세면 제품의 모든
      // 세로 폼이 이 검사에 걸린다.
      if (!flexish && ccs.display !== 'grid') {
        let inlineOnly = true;
        for (const it of R.items.concat(P.items)) {
          const ds = getComputedStyle(it.el);
          if (ds.display.indexOf('inline') !== 0 && ds.cssFloat === 'none') { inlineOnly = false; break; }
        }
        if (!inlineOnly) continue;
      }
      let allControls = true, optedOut = false;
      for (const it of R.items) {
        if (!isControlHolder(it.el)) { allControls = false; break; }
        if (it.el.closest('[data-control-row="separate"]')) { optedOut = true; break; }
      }
      if (!allControls || optedOut) continue;
      const usedR = R.right - R.left;
      if (!(R.items.length === 1 || usedR < inner * 0.4)) continue;
      out.isolatedControlRowChecked++;
      const freeP = inner - (P.right - P.left);
      if (freeP < 120 || freeP < usedR + gap) continue;
      out.isolatedControlRow.push({
        selector: cssPath(container),
        control: snippet(R.items[0].el) || cssPath(R.items[0].el),
        rowUsed: Math.round(usedR), prevFree: Math.round(freeP),
        containerWidth: Math.round(inner), gap: Math.round(gap),
      });
    }
  }

  // --- 6) control_baseline_mismatch -----------------------------------------
  /* 한 줄에 놓인 컨트롤들이 어긋난 상태. 2부 규칙이 옳은 모델이다 —
   * **높이는 같은 종류끼리** (버튼끼리 4px 이상 다르면 그냥 어긋난 것),
   * **중심선은 종류를 넘어** (버튼과 입력은 높이가 달라도 되지만 중심은 맞아야 한다).
   *
   * MUI 는 TextField 를 FormControl > InputBase > input 로 감싸고 helperText 가 붙으면
   * **바깥 wrapper 만** 세로로 늘어난다. 그걸 재면 옆 버튼과 높이가 다르다고 나오는데
   * 화면에서는 정확히 나란하다 — 그래서 안쪽 .MuiInputBase-root 를 잰다. */
  out.controlBaseline = [];
  out.controlBaselineChecked = 0;
  function measureBox(el) {
    const inner = (el.classList && el.classList.contains('MuiInputBase-root'))
      ? el : el.querySelector('.MuiInputBase-root');
    const r = (inner || el).getBoundingClientRect();
    return (r.width > 0 && r.height > 0) ? r : null;
  }
  function kindOf(el) {
    const tag = el.tagName;
    const role = (el.getAttribute('role') || '').toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (type === 'checkbox' || type === 'radio' || role === 'switch' || role === 'checkbox') return '토글';
    if (tag === 'BUTTON' || role === 'button' || type === 'submit' || type === 'button') return '버튼';
    if (tag === 'A') return '링크';
    if (tag === 'SELECT' || role === 'combobox' || role === 'listbox') return '선택';
    if (tag === 'INPUT' || tag === 'TEXTAREA') return '입력';
    if (el.classList && el.classList.contains('MuiInputBase-root')) return '입력';
    return '기타';
  }
  for (const container of MAIN.querySelectorAll('div, section, form, header, nav, td, li')) {
    if (out.controlBaseline.length >= MAX) break;
    const ccs = getComputedStyle(container);
    if (ccs.display !== 'flex' && ccs.display !== 'inline-flex' && ccs.display !== 'grid') continue;
    for (const row of flowRows(container)) {
      if (out.controlBaseline.length >= MAX) break;
      const controls = [];
      for (const it of row.items) {
        const ctl = it.el.matches(CTRL_SEL) ? it.el : it.el.querySelector(CTRL_SEL);
        if (!ctl) continue;
        const box = measureBox(ctl);
        if (!box || box.width < 16 || box.height < 12) continue;
        controls.push({ el: ctl, kind: kindOf(ctl), box: box });
      }
      if (controls.length < 2) continue;
      out.controlBaselineChecked++;
      let worst = null;
      const byKind = new Map();
      for (const c of controls) {
        if (!byKind.has(c.kind)) byKind.set(c.kind, []);
        byKind.get(c.kind).push(c);
      }
      for (const entry of byKind) {
        const group = entry[1];
        if (group.length < 2) continue;
        let hi = -Infinity, lo = Infinity, tall = null, short = null;
        for (const g of group) {
          if (g.box.height > hi) { hi = g.box.height; tall = g; }
          if (g.box.height < lo) { lo = g.box.height; short = g; }
        }
        const d = hi - lo;
        if (d > 4 && (!worst || d > worst.delta)) {
          worst = { reason: '높이', kind: entry[0], delta: Math.round(d * 10) / 10,
                    a: snippet(tall.el) || cssPath(tall.el),
                    b: snippet(short.el) || cssPath(short.el) };
        }
      }
      let cyHi = -Infinity, cyLo = Infinity, low = null, high = null;
      for (const c of controls) {
        const cy = c.box.top + c.box.height / 2;
        if (cy > cyHi) { cyHi = cy; low = c; }
        if (cy < cyLo) { cyLo = cy; high = c; }
      }
      const cd = cyHi - cyLo;
      if (cd > 3 && (!worst || cd > worst.delta)) {
        worst = { reason: '중심선', kind: '(종류 무관)', delta: Math.round(cd * 10) / 10,
                  a: snippet(high.el) || cssPath(high.el),
                  b: snippet(low.el) || cssPath(low.el) };
      }
      if (!worst) continue;
      out.controlBaseline.push({
        selector: cssPath(container), reason: worst.reason, kind: worst.kind,
        delta: worst.delta, controls: controls.length, a: worst.a, b: worst.b,
      });
    }
  }

  // --- 7) oversized_empty_surface -------------------------------------------
  /* 큰 면이 거의 비었거나, 내용이 왼쪽에만 몰려 오른쪽이 통째로 남은 상태.
   *
   * 두 번째 분기가 "큰 사각형 좌측에 컨트롤 3개" 를 직격한다 — 잉크 비율만 보면 그 화면은
   * 통과한다(잉크는 있다). 몰려 있다는 사실은 **잉크 bbox 의 폭** 으로만 드러난다.
   *
   * EmptyState 하위는 제외한다. 빈 화면이 **완성돼 보이길** 원하지 빽빽하길 원하는 게
   * 아니라서, 그쪽은 dead_blank_region 이 페이지 단위로 본다. 스켈레톤도 제외한다 —
   * 로딩 중인 화면을 비었다고 말하면 그건 그냥 타이밍을 잰 것이다. */
  out.oversizedEmptySurface = [];
  out.oversizedEmptySurfaceChecked = 0;
  {
    const EXCLUDE = '.k-empty, [data-empty-state], .MuiSkeleton-root,'
      + ' [class*="skeleton"], [class*="k-skel"]';
    const surfaces = [];
    for (const el of MAIN.querySelectorAll('div, section, article, aside')) {
      const r = el.getBoundingClientRect();
      if (r.width < 280 || r.height < 160 || r.width * r.height < 120000) continue;
      if (!visible(el, r)) continue;
      if (el.closest(EXCLUDE) || el.querySelector(EXCLUDE)) continue;
      // 스크롤되는 상자는 '빈' 것이 아니라 '접힌' 것이다.
      if (el.scrollHeight > el.clientHeight + 1) continue;
      const cs = getComputedStyle(el);
      const bg = cs.backgroundColor;
      const painted = ((parseFloat(cs.borderTopWidth) || 0) > 0 && cs.borderTopStyle !== 'none')
        || cs.boxShadow !== 'none'
        || (!!bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent');
      if (!painted) continue;
      surfaces.push({ el: el, r: r, area: r.width * r.height });
    }
    // 겹쳐 쌓인 카드를 전부 재면 잉크 예산이 순식간에 마른다. 큰 것부터 12개만 본다.
    surfaces.sort((a, b) => b.area - a.area);
    for (const s of surfaces.slice(0, 12)) {
      if (out.oversizedEmptySurface.length >= MAX) break;
      const g = inkGrid(s.el, INK_CELL);
      if (g.ratio == null) continue;   // 측정 실패는 결함이 아니다
      out.oversizedEmptySurfaceChecked++;
      const emptyArea = g.box.w * g.box.h * (1 - g.ratio);
      const bboxRatio = (g.bbox && g.box.w > 0) ? g.bbox.w / g.box.w : 0;
      const sparse = g.ratio < 0.18 && emptyArea >= 200000;
      const stranded = g.box.w > 700 && bboxRatio < 0.45;
      if (!sparse && !stranded) continue;
      out.oversizedEmptySurface.push({
        selector: cssPath(s.el),
        box: Math.round(g.box.w) + 'x' + Math.round(g.box.h),
        coverage: Math.round(g.ratio * 1000) / 1000,
        emptyArea: Math.round(emptyArea),
        contentWidthRatio: Math.round(bboxRatio * 100) / 100,
        reason: sparse ? '내용이 상자를 못 채운다' : '내용이 한쪽에만 몰려 있다',
        text: snippet(s.el),
      });
    }
  }

  // --- 8) dead_blank_region -------------------------------------------------
  /* 스크롤도 안 되는 화면에서 아래나 오른쪽이 통째로 남은 상태.
   *
   * `unsatisfiedDemand` 가 이 검사의 전부다. 짧은 페이지가 하단이 비는 것은 결함이 아니다 —
   * 필드 3개짜리 설정 폼은 넓혀 봐야 채울 것이 없다. 그래서 **굶주린 콘텐츠**(줄바꿈,
   * 실제로 활성인 말줄임, 2페이지 이상 pager, 내부 스크롤) 가 하나라도 있어야 발화한다.
   * 그 폼은 굶주린 것이 없어 앞 두 분기에 걸리지 않고, inkRatio 도 0.25 를 넘어 극단 분기도
   * 피한다. */
  out.deadBlankRegion = null;
  out.deadBlankRegionChecked = false;
  out.deadBlankNote = '';
  {
    // 스크롤 여부와 페이지 격자는 프로브 앞머리에서 이미 쟀다(잉크 예산 우선권 때문이다).
    if (pageOverflowY > 1 || !MAIN_INK) {
      out.deadBlankNote = '페이지가 스크롤된다 — 아래는 빈 것이 아니라 이어진다';
    } else {
      const g = MAIN_INK;
      if (g.ratio == null) {
        out.deadBlankNote = g.note || '잉크 격자를 재지 못했다';
      } else if (!g.bbox) {
        out.deadBlankNote = '본문에 잉크가 하나도 없다 — 이 검사의 대상이 아니다';
      } else {
        const demand = { wrapped: 0, ellipsis: 0, pager: 0, innerScroll: 0 };
        let visits = 0;
        for (const el of MAIN.querySelectorAll('*')) {
          if (visits++ > 2500) break;
          const r = el.getBoundingClientRect();
          if (r.width <= 0 || r.height <= 0) continue;
          const cs = getComputedStyle(el);
          if (cs.visibility === 'hidden' || cs.display === 'none') continue;
          // 말줄임은 **실제로 잘리고 있을 때만** 굶주림이다. textOverflow 만 걸려 있고
          // 넘치지 않으면 아무것도 감춰지지 않았다.
          if (cs.textOverflow === 'ellipsis' && el.scrollWidth > el.clientWidth + 1) demand.ellipsis++;
          if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll') && el.scrollHeight > el.clientHeight + 1) demand.innerScroll++;
          if ((cs.overflowX === 'auto' || cs.overflowX === 'scroll') && el.scrollWidth > el.clientWidth + 1) demand.innerScroll++;
          if (!demand.wrapped) {
            let own = '';
            for (const n of el.childNodes) if (n.nodeType === 3) own += n.nodeValue;
            if (own.trim().length >= 12 && cs.whiteSpace !== 'nowrap' && cs.whiteSpace !== 'pre') {
              // 줄 상자를 세는 대신 높이로 본다 — 여기 오는 요소가 수천 개라 Range 를
              // 매번 씌우면 이 검사 하나가 프로브 전체보다 비싸진다.
              //
              // 단, **콘텐츠 상자** 높이로 재야 한다. 테두리 상자(rect.height)로 재면
              // `padding:24px` 짜리 한 줄 제목이 '두 줄로 접힌 글' 로 잡힌다. 제품 화면에는
              // 패딩 붙은 제목·문단이 어디에나 있으므로 그러면 unsatisfiedDemand 가 늘 참이
              // 되고, 이 검사의 오탐 분리 규칙 자체가 꺼진다 — 실측으로 확인했다(한 줄짜리
              // 패딩 제목 두 개뿐인 화면이 dead_blank_region FAIL 로 나왔다).
              const lh = parseFloat(cs.lineHeight) || (parseFloat(cs.fontSize) || 16) * 1.2;
              const padT = parseFloat(cs.paddingTop) || 0, padB = parseFloat(cs.paddingBottom) || 0;
              const bdT = parseFloat(cs.borderTopWidth) || 0, bdB = parseFloat(cs.borderBottomWidth) || 0;
              // clientHeight 는 인라인 요소에서 0 이라 그때만 테두리 상자에서 되짚는다.
              const contentH = (el.clientHeight || (r.height - bdT - bdB)) - padT - padB;
              if (lh > 0 && contentH >= lh * 1.8) demand.wrapped++;
            }
          }
        }
        let pagerItems = 0;
        for (const li of MAIN.querySelectorAll('.MuiPagination-ul > li')) { pagerItems++; if (pagerItems > 3) break; }
        if (pagerItems > 3) demand.pager++;
        if (!demand.pager) {
          for (const b of MAIN.querySelectorAll('button, [role="button"]')) {
            const label = ((b.textContent || '') + ' ' + (b.getAttribute('aria-label') || '')).trim();
            if (!/다음|더\s*보기|next|more/i.test(label)) continue;
            if (b.disabled || b.getAttribute('aria-disabled') === 'true') continue;
            demand.pager++;
            break;
          }
        }
        out.deadBlankRegionChecked = true;
        out.deadBlankRegion = {
          bottomBlank: (g.box.y + g.box.h - (g.bbox.y + g.bbox.h)) / g.box.h,
          rightBlank: (g.box.x + g.box.w - (g.bbox.x + g.bbox.w)) / g.box.w,
          inkRatio: g.ratio,
          demand: demand,
          unsatisfied: (demand.wrapped + demand.ellipsis + demand.pager + demand.innerScroll) > 0,
          box: Math.round(g.box.w) + 'x' + Math.round(g.box.h),
          bbox: Math.round(g.bbox.w) + 'x' + Math.round(g.bbox.h),
        };
      }
    }
  }

  // --- 9) plain_dropdown_for_entity -----------------------------------------
  /* 기수가 무한히 자라는 대상을 검색 없는 드롭다운으로 고르게 하는 자리.
   *
   * **옵션 개수를 세지 않는다.** MUI 메뉴는 열기 전에는 DOM 에 없어 셀 수도 없고, 더 중요하게는
   * config.entityTerms 자체가 "데이터가 쌓이면 계속 늘어나는 타입" 만 모아 둔 닫힌 목록이다.
   * 상태·역할·우선순위처럼 값 집합이 닫힌 select 는 애초에 여기 걸리지 않는다.
   * 실제로 닫혀 있는데 어휘가 겹치는 경우만 data-entity-select="closed" 로 뺀다. */
  out.plainDropdown = [];
  out.plainDropdownChecked = 0;
  function labelTextOf(el) {
    // 라벨 후보를 모아 잇는다 — 어느 하나만 보면(예: aria-label 만) 컨트롤 절반이 이름 없는
    // 것으로 보여 검사가 조용히 통과한다.
    const parts = [];
    const push = (s) => { if (s) parts.push(String(s)); };
    push(el.getAttribute('aria-label'));
    push(el.getAttribute('placeholder'));
    push(el.getAttribute('title'));
    const by = el.getAttribute('aria-labelledby');
    if (by) {
      for (const id of by.split(/\s+/)) {
        const t = document.getElementById(id);
        if (t) push(t.textContent);
      }
    }
    if (el.id) {
      try {
        const lab = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
        if (lab) push(lab.textContent);
      } catch (e) { /* 이상한 id 는 그냥 라벨 없는 것으로 본다 */ }
    }
    const form = el.closest('.MuiFormControl-root, .MuiTextField-root, label');
    if (form) {
      const lab = form.querySelector('label, .MuiInputLabel-root, .MuiFormLabel-root');
      // `<label>담당자 <select>…</select></label>` 처럼 라벨이 컨트롤을 **감싸는** 형태는
      // 안쪽에 라벨 요소가 따로 없다. 이 갈래를 빠뜨리면 네이티브 select 절반이 이름 없는
      // 컨트롤로 보여 검사가 조용히 통과한다(실측으로 확인).
      if (lab) push(lab.textContent);
      else if (form.tagName === 'LABEL') push(form.textContent);
    }
    const inner = el.querySelector('input');
    if (inner) {
      push(inner.getAttribute('placeholder'));
      push(inner.getAttribute('aria-label'));
    }
    return parts.join(' ').replace(/\s+/g, ' ').trim();
  }
  for (const el of MAIN.querySelectorAll('select, [role="combobox"], [role="listbox"]')) {
    if (out.plainDropdown.length >= MAX) break;
    const r = el.getBoundingClientRect();
    if (!visible(el, r)) continue;
    if (el.closest('[data-entity-select="closed"]')) continue;
    const label = labelTextOf(el);
    if (!label) continue;
    let term = null;
    for (const t of (config.entityTerms || [])) {
      if (label.indexOf(t) >= 0) { term = t; break; }
    }
    if (!term) continue;
    out.plainDropdownChecked++;
    const auto = el.getAttribute('aria-autocomplete');
    // MUI Select 는 값 전달용 <input class="MuiSelect-nativeInput" aria-hidden> 을 숨겨 둔다.
    // 그걸 '검색 입력' 으로 세면 정확히 잡아야 할 것이 전부 통과한다.
    const typeable = el.querySelector(
      'input:not([type="hidden"]):not([aria-hidden="true"]):not(.MuiSelect-nativeInput)');
    const searchable = auto === 'list' || auto === 'both' || !!typeable
      || !!el.closest('.MuiAutocomplete-root');
    if (searchable) continue;
    out.plainDropdown.push({
      selector: cssPath(el), term: term, label: label.slice(0, 40),
      tag: el.tagName.toLowerCase(),
    });
  }

  // --- 10) detail_side_imbalance --------------------------------------------
  /* 2열 중 한쪽이 동났는데 그 공간을 회수하지 않은 상태.
   *
   * rail_wider_than_prose 가 "곁열이 본문을 이긴다" 를 잡는다면 이건 양방향이다 — 어느 쪽이든
   * 내용이 없는데 폭과 높이를 그대로 차지하고 있으면 화면 절반이 죽는다. 세 조건을 모두
   * 요구한다: 잉크 면적 비가 극단(<=0.15), 빈 쪽의 빈 면적이 실제로 크고(>=250,000px^2),
   * 높이 차도 절반 이상. 하나만 보면 짧은 곁열이 전부 걸린다. */
  out.detailSideImbalance = [];
  out.detailSideImbalanceChecked = 0;
  if (window.innerWidth >= config.detailImbalanceMinViewport) {
    for (const el of MAIN.querySelectorAll('div, section')) {
      if (out.detailSideImbalance.length >= MAX) break;
      const cs = getComputedStyle(el);
      if (cs.display !== 'grid' && cs.display !== 'inline-grid') continue;
      const kids = [];
      for (const k of el.children) {
        const kr = k.getBoundingClientRect();
        if (kr.width > 0 && kr.height > 0) kids.push({ el: k, r: kr });
      }
      if (kids.length !== 2) continue;
      const ra = kids[0].r, rb = kids[1].r;
      if (Math.abs(ra.top - rb.top) > 24) continue;   // 나란히 선 두 열일 때만
      if (ra.width < 240 || rb.width < 240) continue;
      const ga = inkGrid(kids[0].el, INK_CELL), gb = inkGrid(kids[1].el, INK_CELL);
      if (ga.ratio == null || gb.ratio == null) continue;
      out.detailSideImbalanceChecked++;
      const areaA = ga.inked * ga.cell * ga.cell, areaB = gb.inked * gb.cell * gb.cell;
      const lo = Math.min(areaA, areaB), hi = Math.max(areaA, areaB);
      if (!(hi > 0) || lo / hi > 0.15) continue;
      const emptyG = areaA < areaB ? ga : gb;
      const emptyArea = emptyG.box.w * emptyG.box.h * (1 - emptyG.ratio);
      if (emptyArea < 250000) continue;
      /* 높이 차는 **상자** 가 아니라 **잉크** 로 잰다.
       *
       * 2열 격자는 기본이 align-items:stretch 라 한쪽이 텅 비어도 상자 높이는 똑같다.
       * 상자로 재면 이 검사는 사실상 발화할 수 없다 — 실측에서 빈 면적 641,174px^2 ·
       * 잉크 비 0.00 인 격자가 '높이가 같다' 는 이유로 통과했다(같은 상자를
       * oversized_empty_surface 는 결함으로 잡았다). 사양이 말하는 "한쪽이 동났다" 는
       * 내용이 끝난 지점을 뜻하므로 잉크 bbox 높이가 그 값이다. */
      const inkHa = ga.bbox ? ga.bbox.h : 0, inkHb = gb.bbox ? gb.bbox.h : 0;
      const tallest = Math.max(inkHa, inkHb);
      if (!(tallest > 0)) continue;
      if (Math.abs(inkHa - inkHb) < 0.5 * tallest) continue;
      out.detailSideImbalance.push({
        selector: cssPath(el),
        left: Math.round(ra.width) + 'x' + Math.round(ra.height),
        right: Math.round(rb.width) + 'x' + Math.round(rb.height),
        inkRatio: Math.round((lo / hi) * 1000) / 1000,
        emptyArea: Math.round(emptyArea),
        emptySide: areaA < areaB ? '왼쪽' : '오른쪽',
      });
    }
  }

  // --- 11) surface_repetition -----------------------------------------------
  /* 같은 톤의 면이 잔뜩 반복되는 상태.
   *
   * **목록인가 구조인가** 를 가르는 것이 이 검사의 전부다. 같은 카드가 여덟 개인 것은
   * 목록에서는 정상이고(그래야 훑을 수 있다) 페이지 골격에서는 결함이다("동일 형태 흰 카드 8개").
   * 그래서 li / role=list 하위 / 행 열기 affordance 를 하나라도 가지면 목록으로 보고 빠진다 —
   * 놀이방 카드 격자와 채팅방 목록이 여기서 터지면 안 된다. 각자 고유 heading 을 갖고
   * 내비게이션이 없는 경우만 '구조' 다. */
  out.surfaceRepetition = [];
  out.surfaceRepetitionChecked = 0;
  {
    const groups = new Map();
    // `a` 를 빼면 링크 카드 격자가 아예 후보에 안 들어와, 목록/구조 판별자가 **돌지도 않은 채**
    // 조용히 넘어간다(요약에는 skip 으로 나온다 — 통과가 아니라 미실행이다). 링크 카드는
    // 어차피 아래에서 목록으로 분류돼 빠지지만, 그건 판별자가 그렇게 판정한 결과여야 한다.
    for (const el of MAIN.querySelectorAll('div, section, article, li, a')) {
      const r = el.getBoundingClientRect();
      if (r.width < 120 || r.height < 64 || r.width * r.height < 12000) continue;
      if (!visible(el, r)) continue;
      const cs = getComputedStyle(el);
      const bg = cs.backgroundColor;
      const hasBg = !!bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent';
      const hasBorder = cs.borderTopStyle !== 'none' && (parseFloat(cs.borderTopWidth) || 0) > 0;
      if (!hasBg && !hasBorder && cs.boxShadow === 'none') continue;
      const sig = [bg, cs.borderTopWidth, cs.borderTopColor, cs.borderRadius, cs.boxShadow,
                   Math.round(r.width / 100)].join('|');
      if (!groups.has(sig)) groups.set(sig, []);
      groups.get(sig).push({ el: el, r: r });
    }
    const vw = window.innerWidth;
    const threshold = vw < 1200 ? 6 : (vw < 1920 ? 8 : 10);
    const mainRect = MAIN.getBoundingClientRect();
    const mainArea = mainRect.width * mainRect.height;
    for (const entry of groups) {
      if (out.surfaceRepetition.length >= MAX) break;
      const members = entry[1];
      if (members.length < threshold) continue;
      out.surfaceRepetitionChecked++;
      let area = 0;
      for (const m of members) area += m.r.width * m.r.height;
      if (!(mainArea > 0) || area / mainArea < 0.35) continue;
      let listish = false, headed = 0;
      for (const m of members) {
        if (m.el.tagName === 'LI'
            || m.el.closest('ul, ol, table, [role="list"], [role="listbox"], [role="menu"]')
            || m.el.matches('a[href]') || m.el.querySelector('a[href]')
            || m.el.getAttribute('role') === 'button' || m.el.querySelector('[role="button"]')
            || m.el.hasAttribute('aria-expanded') || m.el.querySelector('[aria-expanded]')) {
          listish = true;
          break;
        }
        if (m.el.querySelector('h1, h2, h3, h4, h5, h6, [role="heading"]')) headed++;
      }
      if (listish || headed < members.length) continue;
      out.surfaceRepetition.push({
        selector: cssPath(members[0].el), count: members.length, threshold: threshold,
        areaShare: Math.round((area / mainArea) * 100),
        signature: entry[0].slice(0, 80),
        text: snippet(members[0].el),
      });
    }
  }

  // --- app-level state worth recording (not a failure by itself) -----------
  const denied = document.querySelector('.k-empty-title');
  out.emptyTitle = denied ? snippet(denied) : null;
  out.hasErrorState = !!document.querySelector('.k-error, .k-errorstate');
  out.stillLoading = !!document.querySelector('.k-skel');

  meter.remove && meter.remove();
  return out;
}
"""


def _verdict(status: str, count: int = 0, samples: Any = None, note: str = "") -> dict:
    result = {"status": status, "count": count}
    if samples:
        result["samples"] = samples[:MAX_SAMPLES]
    if note:
        result["note"] = note
    return result


def evaluate(page, *, expected_theme: str, viewport_width: int) -> dict:
    """Run the probe in the page and return the raw measurement dict."""
    return page.evaluate(PROBE_JS, {
        "maxSamples": MAX_SAMPLES,
        "tinyTextMinViewport": TINY_TEXT_MIN_VIEWPORT,
        "tinyTextMinPx": TINY_TEXT_MIN_PX,
        "imageCropMinLoss": IMAGE_CROP_MIN_LOSS,
        "expectedTheme": expected_theme,
        "viewportWidth": viewport_width,
        "columnContentMinViewport": COLUMN_CONTENT_MIN_VIEWPORT,
        "detailImbalanceMinViewport": DETAIL_IMBALANCE_MIN_VIEWPORT,
        "entityTerms": list(ENTITY_TERMS),
    })


def compile_ignores(patterns: list[str] | None) -> list[re.Pattern]:
    return [re.compile(p) for p in (patterns or [])]


def _filter_messages(messages: list[str], ignores: list[re.Pattern]) -> list[str]:
    if not ignores:
        return messages
    return [m for m in messages if not any(p.search(m) for p in ignores)]


def classify(probe: dict, *, expected_theme: str, viewport_width: int, final_url: str,
             console_errors: list[str], page_errors: list[str],
             ignores: list[re.Pattern] | None = None, public: bool = False) -> dict:
    """Turn one page's raw measurements into per-class verdicts."""
    ignores = ignores or []
    results: dict[str, dict] = {}

    # auth_ok — a bounce to /login means the capture is worthless, say so loudly.
    # 로그인 화면 자체를 찍는 경우에는 /login 이 정상이고, 오히려 **거기 머물러야** 한다.
    if public:
        results["auth_ok"] = (
            _verdict("pass") if "/login" in final_url
            else _verdict("fail", 1, [final_url], "로그인 화면을 찍으려 했는데 다른 곳으로 갔다")
        )
    elif "/login" in final_url:
        results["auth_ok"] = _verdict("fail", 1, [final_url], "세션 없음 → 로그인 화면으로 튕김")
    elif "/change-password" in final_url:
        results["auth_ok"] = _verdict("fail", 1, [final_url], "비밀번호 변경 강제 상태")
    else:
        results["auth_ok"] = _verdict("pass")

    actual_theme = probe.get("theme")
    # 로그인 화면은 승인된 디자인 원본이 **라이트 고정**이다(브랜드 히어로 + 흰 폼 패널).
    # data-theme 이 정말 없으므로 pass 라고 하면 거짓말이고, fail 이라고 하면 고칠 것이 없는
    # 결함이 매번 뜬다 — 이유를 남기고 건너뛴다.
    if public:
        results["theme_applied"] = _verdict(
            "skip", 0, [], "로그인 화면은 라이트 고정(승인된 디자인 원본) — 테마를 따르지 않는다")
    else:
        results["theme_applied"] = (
            _verdict("pass") if actual_theme == expected_theme
            else _verdict("fail", 1, [f"data-theme={actual_theme!r} (기대: {expected_theme!r})"])
        )

    overflow = probe.get("overflow") or {}
    scroll_w = overflow.get("scrollWidth", 0)
    client_w = overflow.get("clientWidth", 0)
    if scroll_w > client_w + 1:
        results["horizontal_overflow"] = _verdict(
            "fail", scroll_w - client_w,
            [f"{o['selector']} right={o['right']} w={o['width']} «{o['text']}»"
             for o in overflow.get("offenders", [])],
            f"scrollWidth={scroll_w} > clientWidth={client_w}",
        )
    else:
        results["horizontal_overflow"] = _verdict(
            "pass", 0, None, f"scrollWidth={scroll_w} <= clientWidth={client_w}+1")

    console_errors = _filter_messages(console_errors, ignores)
    page_errors = _filter_messages(page_errors, ignores)
    results["console_errors"] = (
        _verdict("fail", len(console_errors), console_errors) if console_errors
        else _verdict("pass")
    )
    results["page_errors"] = (
        _verdict("fail", len(page_errors), page_errors) if page_errors else _verdict("pass")
    )

    broken = probe.get("brokenImages") or []
    results["broken_images"] = (
        _verdict("fail", len(broken), [f"{b['selector']} src={b['src']}" for b in broken])
        if broken else _verdict("pass")
    )

    dupes = probe.get("duplicateIds") or []
    results["duplicate_ids"] = (
        _verdict("fail", len(dupes), [f"#{d['id']} x{d['count']}" for d in dupes])
        if dupes else _verdict("pass")
    )

    # 상세 화면 곁열이 본문보다 넓으면 실패. 같은 폭이면(1.0) 통과 — 두 열을 반씩 쓰는
    # 화면도 있을 수 있고, 문제는 "곁열이 본문을 **이기는** 것" 이다.
    rails = [r for r in (probe.get("railRatio") or []) if r["ratio"] > 1.0]
    results["rail_wider_than_prose"] = (
        _verdict(
            "fail", len(rails),
            [f"본문 {r['prose']}px / 곁열 {r['rail']}px (곁열이 {r['ratio']}배)" for r in rails],
            "산문 폭 상한은 옳지만 남는 폭을 곁열이 전부 가져가면 본문이 더 좁아진다",
        )
        if rails else _verdict("pass")
    )

    # 사용자가 올린 이미지를 잘라 보여주는 자리. 장식(aria-hidden/alt="")은 프로브에서 이미 뺐다.
    # 스크롤로 볼 수 없는 잘림. 스크롤이 되면 접힌 것이지 잘린 것이 아니다.
    clipped = probe.get("clipped") or []
    results["content_clipped"] = (
        _verdict(
            "fail", len(clipped),
            [f"{c['selector']} 상자 {c['box']} 안에서"
             f"{' 세로 ' + str(c['overY']) + 'px' if c['overY'] else ''}"
             f"{' 가로 ' + str(c['overX']) + 'px' if c['overX'] else ''} 넘침 «{c['text']}»"
             for c in clipped],
            "overflow 가 hidden 이라 스크롤로도 볼 수 없다 — 사용자에게는 그냥 잘린 화면이다",
        )
        if clipped else _verdict("pass")
    )

    cropped = probe.get("croppedImages") or []
    results["image_cropped"] = (
        _verdict(
            "fail", len(cropped),
            [f"{c['selector']} «{c['alt']}» 원본 {c['natural']} → 상자 {c['box']}"
             f" (object-fit:cover 로 {c['lostPct']}% 잘림)" for c in cropped],
            "사용자가 올린 이미지가 잘려 보인다 — 상자를 채우려고 원본을 자르고 있다",
        )
        if cropped else _verdict("pass")
    )

    if viewport_width < TINY_TEXT_MIN_VIEWPORT:
        results["tiny_text"] = _verdict(
            "skip", 0, None, f"뷰포트 폭 {viewport_width} < {TINY_TEXT_MIN_VIEWPORT}")
    else:
        tiny = probe.get("tinyText") or []
        count = probe.get("tinyTextCount", len(tiny))
        results["tiny_text"] = (
            _verdict("fail", count,
                     [f"{t['selector']} {t['fontSize']}px «{t['text']}»" for t in tiny],
                     f"{TINY_TEXT_MIN_PX}px 미만 텍스트")
            if count else _verdict("pass", 0, None, f"{TINY_TEXT_MIN_PX}px 미만 없음")
        )

    main = probe.get("main") or {}
    if viewport_width < NARROW_MAIN_MIN_VIEWPORT:
        results["narrow_main"] = _verdict(
            "skip", 0, None, f"뷰포트 폭 {viewport_width} < {NARROW_MAIN_MIN_VIEWPORT}")
    elif not main.get("found"):
        results["narrow_main"] = _verdict("fail", 1, None, "#main-content / <main> 를 찾지 못함")
    else:
        vp = main.get("viewportWidth") or viewport_width
        widths = [w for w in (main.get("usedWidth"), main.get("contentWidth")) if w]
        measured = min(widths) if widths else (main.get("mainWidth") or 0)
        ratio = (measured / vp) if vp else 0.0
        note = (f"used={main.get('usedWidth')}px, content={main.get('contentWidth')}px "
                f"({main.get('contentSelector')}), main={main.get('mainWidth')}px, "
                f"viewport={vp}px, ratio={ratio:.2%}")
        results["narrow_main"] = (
            _verdict("pass", 0, None, note) if ratio >= NARROW_MAIN_MIN_RATIO
            else _verdict("fail", 1, None, note)
        )

    collapse = probe.get("verticalCollapse") or []
    collapse_count = probe.get("verticalCollapseCount", len(collapse))
    collapse_samples = [
        f"{c['selector']} w={c['width']}px (~{c['ch']}px/ch) h={c['height']}"
        f" lines={c.get('lines')} chars/line={c.get('charsPerLine')} «{c['text']}»"
        for c in collapse
    ]
    results["vertical_text_collapse"] = (
        _verdict("fail", collapse_count, collapse_samples)
        if collapse_count else _verdict("pass")
    )

    # 떠 있는 요소가 컨트롤을 덮어 **누를 수 없게** 만든 경우만 실패다. 살짝 스치기만 하고
    # 여전히 눌리면(elementFromPoint 가 그 컨트롤을 돌려주면) 프로브 단계에서 걸러진다.
    # 스크롤로 비켜낼 수 없는 겹침만 실패다. 비킬 수 있는 것(긴 표의 한 행이 잠깐 FAB
    # 밑에 놓이는 경우)은 떠 있는 버튼을 쓰는 이상 늘 하나쯤 생기므로 note 로만 남긴다 —
    # 그걸 실패로 세면 '표가 긴 화면 = 영구 실패'가 되어 게이트가 곧 무시된다.
    overlap = probe.get("fabOverlap") or []
    blocking = [o for o in overlap if o.get("unreachable")]
    reachable = [o for o in overlap if not o.get("unreachable")]

    def _fmt(o: dict) -> str:
        return (
            f"[{o.get('where', '?')}] {o['control']} «{o['text']}» 를 {o['floater']} 가"
            f" {o['coveredPct']}% 덮음 (({o['at'][0]},{o['at'][1]}) 에서 클릭이 가로채짐)"
        )

    note = ""
    if reachable:
        note = (
            f"스크롤하면 비켜나는 겹침 {len(reachable)}건은 실패로 세지 않았다: "
            + " / ".join(f"«{o['text']}»" for o in reachable[:3])
        )
    results["fab_overlap"] = (
        _verdict("fail", len(blocking), [_fmt(o) for o in blocking],
                 "스크롤해도 비켜나지 않는다 — 사용자는 이 컨트롤을 누를 방법이 없다")
        if blocking else _verdict("pass", 0, None, note)
    )

    # ── 레이아웃·콘텐츠 축 11종 ──────────────────────────────────────────────
    #
    # 전부 advisory 다(`CLASSES` 주석 참고). 판정 규칙은 하나로 통일한다:
    #   후보를 하나도 못 봤다  → skip + 왜 못 봤는지
    #   후보를 봤고 결함 없음  → pass
    #   결함 있음              → fail
    # "후보가 없다" 를 pass 로 세면 요약표의 통과 수가 실제로 확인한 화면 수와 어긋난다 —
    # 이 저장소가 `tiny_text`/`narrow_main` 에서 이미 겪은 착시다(QA-10·QA-13).
    def _advisory(name: str, items: list, checked: int, fmt, fail_note: str,
                  skip_note: str, pass_note: str = "") -> None:
        if not checked:
            results[name] = _verdict("skip", 0, None, skip_note)
        elif items:
            results[name] = _verdict("fail", len(items), [fmt(i) for i in items], fail_note)
        else:
            results[name] = _verdict("pass", 0, None, pass_note or f"후보 {checked}건 확인")

    _advisory(
        "equal_column_split",
        probe.get("equalColumnSplit") or [], probe.get("equalColumnSplitChecked", 0),
        lambda s: (f"{s['selector']} 트랙 {s['tracks']}개 {s['widths']}px — 요구 폭은"
                   f" {s['demandRatio']}배 차이인데 폭은 같다"
                   f" (굶는 쪽 {s['hungryLines']}줄로 접힘,"
                   f" 남는 쪽 {round(s['freeRatio'] * 100)}% 빔) «{s['hungryText']}»"),
        "폭을 똑같이 나눠 한쪽은 접히고 한쪽은 비었다 — 트랙을 내용 요구에 맞춰야 한다",
        "2트랙 이상·각 160px 이상인 격자가 이 화면에 없다",
    )

    if viewport_width < COLUMN_CONTENT_MIN_VIEWPORT:
        results["column_width_vs_content"] = _verdict(
            "skip", 0, None,
            f"뷰포트 폭 {viewport_width} < {COLUMN_CONTENT_MIN_VIEWPORT}"
            " — 이 아래는 표가 카드로 접히거나 한글이 원래 접히는 폭이다")
    else:
        _advisory(
            "column_width_vs_content",
            probe.get("columnWidthVsContent") or [], probe.get("columnWidthVsContentChecked", 0),
            lambda s: (f"{s['selector']} «{s['starvedColumn']}» {s['starvedWidth']}px 가"
                       f" {round(s['wrapRate'] * 100)}% 접히는데"
                       f" «{s['slackColumn']}» {s['slackWidth']}px 는"
                       f" {round(s['fill'] * 100)}%만 차 있다 (여유 {s['slackPx']}px)"),
            "남는 열의 여유를 접히는 열로 옮기면 그대로 해결된다",
            "열이 2개 이상인 표가 이 화면에 없다",
        )

    _advisory(
        "header_cell_alignment_mismatch",
        probe.get("headerCellAlignment") or [], probe.get("headerCellAlignmentChecked", 0),
        lambda s: (f"{s['selector']} «{s['column']}» 머리는 {s['header']} 인데"
                   f" 몸은 {s['body']} ({s['bodyShare']}%)"),
        "머리와 몸이 다른 축에 붙어 눈이 열을 따라 내려가지 못한다",
        "본문 셀이 2개 이상인 표 열이 이 화면에 없다",
    )

    _advisory(
        "numeric_alignment",
        probe.get("numericAlignment") or [], probe.get("numericAlignmentChecked", 0),
        lambda s: (f"{s['selector']} «{s['column']}» (숫자 {s['numericShare']}%)"
                   f" 정렬={s['align']} tabular={s['tabular']} — {s['reason']}"),
        "자릿수가 세로로 안 맞으면 값을 비교할 수 없다 — 우정렬 + tabular-nums 가 있어야 한다",
        "숫자 열(비어있지 않은 셀의 80% 이상이 숫자)이 이 화면에 없다",
    )

    _advisory(
        "isolated_control_row",
        probe.get("isolatedControlRow") or [], probe.get("isolatedControlRowChecked", 0),
        lambda s: (f"{s['selector']} «{s['control']}» 가 자기 줄({s['rowUsed']}px)을 쓰는데"
                   f" 윗줄 여유는 {s['prevFree']}px 다 (컨테이너 {s['containerWidth']}px,"
                   f" gap {s['gap']}px)"),
        "윗줄에 들어갈 자리가 있는데 밀려났다 — 좁아서 접힌 것이 아니다",
        "컨트롤만 있는 두 번째 줄이 이 화면에 없다",
    )

    _advisory(
        "control_baseline_mismatch",
        probe.get("controlBaseline") or [], probe.get("controlBaselineChecked", 0),
        lambda s: (f"{s['selector']} {s['reason']} 차이 {s['delta']}px"
                   f" [{s['kind']}] 컨트롤 {s['controls']}개 «{s['a']}» vs «{s['b']}»"),
        "한 줄 안에서 같은 종류끼리 높이가 다르거나 중심선이 어긋났다",
        "컨트롤이 2개 이상 놓인 줄이 이 화면에 없다",
    )

    _advisory(
        "oversized_empty_surface",
        probe.get("oversizedEmptySurface") or [], probe.get("oversizedEmptySurfaceChecked", 0),
        lambda s: (f"{s['selector']} {s['box']} 잉크 {round(s['coverage'] * 100)}%"
                   f" (빈 면적 {s['emptyArea']:,}px², 내용 폭 비 {s['contentWidthRatio']})"
                   f" — {s['reason']} «{s['text']}»"),
        "큰 면이 비어 있다 — 상자를 줄이거나 그 자리에 들어갈 것을 넣어야 한다",
        "이 화면에 측정할 만한 크기의 면이 없다",
    )

    dead = probe.get("deadBlankRegion")
    if not probe.get("deadBlankRegionChecked") or not dead:
        results["dead_blank_region"] = _verdict(
            "skip", 0, None, probe.get("deadBlankNote") or "본문 영역을 재지 못했다")
    else:
        bottom = dead.get("bottomBlank") or 0.0
        right = dead.get("rightBlank") or 0.0
        ink = dead.get("inkRatio") or 0.0
        starving = bool(dead.get("unsatisfied"))
        demand = dead.get("demand") or {}
        note = (f"본문 {dead.get('box')} / 잉크 {dead.get('bbox')}"
                f" — 하단 공백 {bottom:.0%}, 우측 공백 {right:.0%}, 잉크 {ink:.0%},"
                f" 굶주린 콘텐츠 {'있음' if starving else '없음'} {demand}")
        # 극단 분기는 굶주림을 묻지 않는다 — 화면의 절반 이상이 비었는데 잉크가 25% 밑이면
        # 무엇이 들어갈지와 무관하게 그 화면은 완성돼 보이지 않는다.
        extreme = bottom >= 0.55 and ink <= 0.25
        starved_bottom = bottom >= 0.35 and ink <= 0.45 and starving
        starved_right = right >= 0.30 and ink <= 0.45 and starving
        if extreme or starved_bottom or starved_right:
            results["dead_blank_region"] = _verdict(
                "fail", 1, [note],
                "스크롤되지 않는 화면인데 남은 공간을 회수하지 않았다")
        else:
            results["dead_blank_region"] = _verdict("pass", 0, None, note)

    _advisory(
        "plain_dropdown_for_entity",
        probe.get("plainDropdown") or [], probe.get("plainDropdownChecked", 0),
        lambda s: (f"{s['selector']} <{s['tag']}> «{s['label']}» — '{s['term']}' 는"
                   f" 기수가 무한히 자라는 대상인데 검색할 수 없다"),
        "데이터가 쌓이면 이 드롭다운은 못 쓰게 된다 — 검색 가능한 선택기여야 한다",
        "entity 어휘에 걸리는 드롭다운이 이 화면에 없다",
    )

    if viewport_width < DETAIL_IMBALANCE_MIN_VIEWPORT:
        results["detail_side_imbalance"] = _verdict(
            "skip", 0, None,
            f"뷰포트 폭 {viewport_width} < {DETAIL_IMBALANCE_MIN_VIEWPORT}"
            " — 이 아래는 한 열로 접혀 좌우 불균형이라는 것이 없다")
    else:
        _advisory(
            "detail_side_imbalance",
            probe.get("detailSideImbalance") or [], probe.get("detailSideImbalanceChecked", 0),
            lambda s: (f"{s['selector']} {s['left']} / {s['right']} —"
                       f" {s['emptySide']}이 동났다 (잉크 면적 비 {s['inkRatio']},"
                       f" 빈 면적 {s['emptyArea']:,}px²)"),
            "한쪽이 동났는데 그 공간을 회수하지 않았다 — 화면 절반이 죽는다",
            "나란히 선 2열 격자가 이 화면에 없다",
        )

    _advisory(
        "surface_repetition",
        probe.get("surfaceRepetition") or [], probe.get("surfaceRepetitionChecked", 0),
        lambda s: (f"{s['selector']} 같은 톤의 면 {s['count']}개"
                   f" (임계 {s['threshold']}, 본문의 {s['areaShare']}%) «{s['text']}»"),
        "목록이 아닌데 같은 면이 반복된다 — 위계 없이 같은 카드를 늘어놓은 상태다",
        "임계 이상 반복되는 동일 톤 면 그룹이 이 화면에 없다",
    )

    return results


def summarize(per_page: list[dict]) -> dict:
    """Aggregate ``{class: {pass, fail, skip}}`` over every captured page."""
    totals = {c: {"pass": 0, "fail": 0, "skip": 0} for c in CLASSES}
    for page_result in per_page:
        for name, verdict in (page_result.get("assertions") or {}).items():
            bucket = totals.setdefault(name, {"pass": 0, "fail": 0, "skip": 0})
            bucket[verdict.get("status", "skip")] = bucket.get(verdict.get("status", "skip"), 0) + 1
    return totals
